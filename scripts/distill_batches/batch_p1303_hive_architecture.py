"""Hive architecture training pairs (part 1): DPoS, block production, node setup."""

PAIRS = [
    (
        "hive_architecture/dpos-consensus-mechanism",
        r'''Explain how Hive's Delegated Proof of Stake (DPoS) consensus mechanism works.''',
        r'''<think>
The user wants an explanation of Hive's DPoS. I should cover the core model:
stakeholders vote for witnesses using their HIVE POWER (staked HIVE).
Top 21 witnesses produce blocks in rounds. One backup witness rotates in per round.
Key differences from PoW/PoS: no mining, no slashing, governance via stake-weighted votes.
Block finality is ~1 minute (2/3 of witnesses must confirm = 15 of 21).
Witnesses are incentivized by block rewards, disincentivized by community unvotes.
</think>

Hive uses Delegated Proof of Stake (DPoS), where token holders elect block producers (called witnesses) through stake-weighted voting.

**Core mechanics:**

```
Stakeholder Voting:
  - Each account votes for up to 30 witnesses
  - Vote weight = HIVE POWER (vested/staked HIVE)
  - Votes can be changed at any time (liquid democracy)

Block Production:
  - Top 20 witnesses by votes are "active" every round
  - 1 backup witness rotates in per round (ranked 21+)
  - 21 witnesses per round, each producing 1 block
  - 3-second block intervals → 63-second rounds

Finality:
  - A block becomes irreversible after 2/3+1 witnesses confirm
  - That means 15 of 21 witnesses → ~45 seconds to irreversibility
  - Last irreversible block (LIB) = safe finality threshold
```

```python
from beem import Hive
from beem.witness import Witnesses

hive = Hive(node="https://api.hive.blog")

# Get top 21 active witnesses (current round producers)
witnesses = Witnesses(blockchain_instance=hive)
top_21 = list(witnesses)[:21]

for i, w in enumerate(top_21, 1):
    print(f"{i:2d}. @{w['owner']:20s}  votes: {int(w['votes']) / 1e12:.0f} TVESTS")

# Check current irreversible block
from beem.blockchain import Blockchain
bc = Blockchain(blockchain_instance=hive)
head = bc.get_current_block_num()
lib = hive.get_dynamic_global_properties()["last_irreversible_block_num"]
print(f"\nHead block: {head}")
print(f"Last irreversible: {lib}")
print(f"Confirmation lag: {head - lib} blocks ({(head - lib) * 3}s)")
```

**Why DPoS over PoW/PoS:**
- 3-second blocks (vs 12s Ethereum, 10min Bitcoin)
- Zero transaction fees (Resource Credits regenerate)
- Governance: witnesses set chain parameters (APR, block size, HBD interest)
- Accountability: poor-performing witnesses get unvoted quickly'''
    ),
    (
        "hive_architecture/block-production-schedule",
        r'''How does Hive's block production schedule work? I see 3-second blocks and 21 witnesses per round — how is the order determined?''',
        r'''<think>
The user asks about block scheduling specifics. Each round has 21 slots:
top 20 witnesses are shuffled, plus 1 backup. The shuffle uses the previous
block's hash as a seed for deterministic randomization. This prevents
witnesses from predicting when they produce far in advance (mitigates
censorship). A round is 63 seconds (21 * 3s). If a witness misses their
slot, the slot produces no block and the chain continues after 3s.
Missed blocks are tracked and affect witness reliability reputation.
</think>

Hive produces blocks on a strict 3-second cadence with 21 witnesses per round:

```
Round structure (63 seconds total):
  - 21 time slots, each 3 seconds
  - Top 20 witnesses (by vote) fill 20 slots
  - 1 backup witness (ranked 21+, rotates) fills slot 21
  - Slot order is SHUFFLED each round using previous block hash as seed

Shuffle algorithm (simplified):
  witnesses = top_20 + [next_backup]
  seed = hash(previous_round_last_block)
  for i in range(len(witnesses) - 1, 0, -1):
      j = seed % (i + 1)
      witnesses[i], witnesses[j] = swap
      seed = hash(seed)
```

```python
import struct
import hashlib

def simulate_witness_shuffle(witness_list: list[str], block_hash: str) -> list[str]:
    """Simulate Hive's witness scheduling shuffle for one round."""
    witnesses = witness_list.copy()
    seed = bytes.fromhex(block_hash)

    for i in range(len(witnesses) - 1, 0, -1):
        # Use 8 bytes of seed to get index
        j = struct.unpack_from('<Q', seed)[0] % (i + 1)
        witnesses[i], witnesses[j] = witnesses[j], witnesses[i]
        seed = hashlib.sha256(seed).digest()

    return witnesses

# Example with dummy witnesses
top_20 = [f"witness-{i}" for i in range(1, 21)]
backup = ["backup-witness-42"]
schedule = simulate_witness_shuffle(top_20 + backup, "ab" * 16)

for slot, w in enumerate(schedule):
    print(f"  Slot {slot:2d} ({slot*3:3d}s): {w}")
```

**Missed blocks:** if a witness fails to produce in their slot, the slot is simply empty — no block is created for that 3 seconds. The chain tracks `total_missed` per witness, and the community uses this metric to decide whether to unvote unreliable witnesses.'''
    ),
    (
        "hive_architecture/witness-scheduling-algorithm",
        r'''What is the witness scheduling algorithm on Hive? How does it decide which backup witness gets included?''',
        r'''<think>
This is about the specifics of backup witness rotation. The backup slot
cycles through witnesses ranked 21 and below, weighted by their vote count.
Higher-ranked backups get more frequent slots. The selection is deterministic
based on a virtual scheduled time derived from vote weight. This gives
smaller witnesses a chance to produce blocks proportional to their stake
support, which is important for decentralization.
The virtual time concept ensures fair round-robin among backup witnesses.
</think>

The scheduling algorithm has two distinct parts: the top-20 shuffle and the backup witness selection.

**Top 20:** Deterministic shuffle each round (seed = previous block hash). All top-20 produce exactly once per round.

**Backup witness selection** uses a virtual scheduling time:

```
Each backup witness (rank 21+) has a virtual_scheduled_time:
  virtual_scheduled_time += (MAX_WITNESSES / witness_votes)

Lower virtual_scheduled_time = next to produce.
This means higher-voted backups produce MORE OFTEN,
but all backups eventually get a turn.
```

```python
from dataclasses import dataclass
from decimal import Decimal

@dataclass
class BackupWitness:
    name: str
    votes: int  # in VESTS
    virtual_scheduled_time: Decimal = Decimal(0)

def select_next_backup(backups: list[BackupWitness]) -> BackupWitness:
    """Select the backup witness with the lowest virtual_scheduled_time."""
    # Sort by virtual scheduled time — lowest goes next
    selected = min(backups, key=lambda w: w.virtual_scheduled_time)

    # After producing, advance their virtual time
    # Higher votes → smaller increment → more frequent production
    total_votes = sum(w.votes for w in backups) or 1
    increment = Decimal(total_votes) / Decimal(selected.votes or 1)
    selected.virtual_scheduled_time += increment

    return selected

# Simulate 10 rounds of backup selection
backups = [
    BackupWitness("backup-a", votes=500_000_000),  # high votes
    BackupWitness("backup-b", votes=200_000_000),  # medium
    BackupWitness("backup-c", votes=50_000_000),   # low
]

for round_num in range(10):
    chosen = select_next_backup(backups)
    print(f"Round {round_num+1}: {chosen.name} (vst={chosen.virtual_scheduled_time:.2f})")
```

This ensures backup witnesses produce blocks proportional to their community support, maintaining fair representation without locking out smaller witnesses entirely.'''
    ),
    (
        "hive_architecture/api-node-setup-config",
        r'''How do I set up a Hive API node? What are the essential config.ini settings for hived?''',
        r'''<think>
The user wants to run an API node. Key config.ini parameters:
- plugin list (essential: condenser_api, database_api, block_api, etc.)
- shared-file-size (shared memory mapped file, needs to be large enough)
- p2p-endpoint and seed nodes for peering
- webserver-http-endpoint and webserver-ws-endpoint for API serving
- plugin-specific settings like account-history-track-account-range
I should distinguish between a minimal API node and a full API node.
The shared memory file is the biggest resource concern (64GB+ for full).
</think>

Setting up a Hive API node requires configuring `hived` via `config.ini`. Here is a production-ready configuration:

```ini
# config.ini for Hive API node
# Location: /path/to/hived_data/config.ini

# ---- Network ----
p2p-endpoint = 0.0.0.0:2001
# Seed nodes for initial sync
p2p-seed-node = seed.hive.blog:2001
p2p-seed-node = seed.openhive.network:2001
p2p-seed-node = hive-seed.arcange.eu:2001

# ---- API Endpoints ----
webserver-http-endpoint = 0.0.0.0:8091
webserver-ws-endpoint = 0.0.0.0:8090
webserver-thread-pool-size = 32

# ---- Shared Memory ----
# Full API node needs ~64GB+, consensus-only needs ~24GB
shared-file-size = 64G
shared-file-dir = /dev/shm  # tmpfs for performance, or use NVMe path

# ---- Plugins (full API node) ----
plugin = condenser_api
plugin = database_api
plugin = block_api
plugin = account_by_key_api
plugin = account_history_api
plugin = network_broadcast_api
plugin = rc_api
plugin = market_history_api
plugin = witness_api

# ---- Account History ----
# Track all accounts (expensive) or specific ones:
# account-history-track-account-range = ["", "z"]   # all accounts
account-history-rocksdb-path = /data/hived/rocksdb

# ---- Performance ----
flush-state-interval = 0  # 0 = only flush on clean exit
```

```bash
#!/bin/bash
# Setup and run hived API node

HIVED_DIR="/opt/hived"
DATA_DIR="/data/hived"

mkdir -p "$DATA_DIR"

# Download latest hived release (or build from source)
# https://github.com/openhive-network/hive/releases
wget -O hived "https://github.com/openhive-network/hive/releases/latest/download/hived"
chmod +x hived

# First run generates default config.ini
./hived --data-dir="$DATA_DIR" --dump-config > /dev/null 2>&1

# Copy your customized config.ini
cp config.ini "$DATA_DIR/config.ini"

# Start hived — initial sync takes 1-3 days depending on hardware
./hived --data-dir="$DATA_DIR" 2>&1 | tee "$DATA_DIR/hived.log"
```

**Hardware requirements for a full API node:**
- CPU: 8+ cores (replay is single-threaded but API serving is multi-threaded)
- RAM: 64GB minimum (shared memory mapped file)
- Storage: 1TB+ NVMe SSD (block_log alone is ~400GB)
- Network: 100Mbps+ for P2P and API traffic'''
    ),
    (
        "hive_architecture/full-vs-consensus-vs-api-node",
        r'''What is the difference between a Hive full node, consensus node, and API node? When would I use each?''',
        r'''<think>
There are three main node types in Hive's architecture:
1. Consensus node (witness): minimal plugins, produces blocks, low resource usage
2. API node: serves JSON-RPC queries, needs many plugins and more RAM/storage
3. Full node: API node with ALL plugins and full history — very resource-heavy
The user needs to understand the trade-offs for each. Consensus nodes are
for witnesses, API nodes for dApps, full nodes for block explorers/services.
There is also the "low memory" mode which skips account history.
</think>

The three node types serve different purposes and have very different resource requirements:

```
Node Type         | Plugins     | RAM    | Storage | Use Case
------------------|-------------|--------|---------|---------------------------
Consensus (Witness)| minimal    | ~24GB  | ~500GB  | Block production only
API Node          | most APIs   | ~64GB  | ~1TB    | dApp backends, queries
Full Node         | ALL plugins | ~128GB | ~2TB+   | Block explorers, indexers
```

**Consensus node (witness):**
```ini
# Minimal config — only what is needed to produce blocks
plugin = witness
plugin = p2p
plugin = chain
plugin = webserver

# Witness settings
witness = "yourwitness"
private-key = 5YourBlockSigningKey
shared-file-size = 24G
```

**API node (most common for dApp developers):**
```ini
# Serves JSON-RPC calls for dApps
plugin = condenser_api        # Legacy API (Steemit-compatible)
plugin = database_api         # Modern database queries
plugin = block_api            # Block data
plugin = account_history_api  # Transaction history
plugin = rc_api               # Resource credit queries
plugin = network_broadcast_api # Submit transactions
shared-file-size = 64G
```

**Full node (everything):**
```ini
# All plugins — for services like hivemind, block explorers
plugin = condenser_api database_api block_api account_by_key_api
plugin = account_history_api network_broadcast_api rc_api
plugin = market_history_api witness_api reputation_api
plugin = follow_api tags_api
shared-file-size = 128G
```

```python
# Quick check: which APIs does a node support?
import httpx

async def check_node_apis(node_url: str) -> list[str]:
    """Discover which API plugins a Hive node has enabled."""
    methods_to_check = [
        ("condenser_api.get_dynamic_global_properties", []),
        ("database_api.get_dynamic_global_properties", {}),
        ("account_history_api.get_account_history", {"account": "hiveio", "start": -1, "limit": 0}),
        ("rc_api.find_rc_accounts", {"accounts": ["hiveio"]}),
        ("market_history_api.get_ticker", {}),
    ]
    available = []
    async with httpx.AsyncClient(timeout=10) as client:
        for method, params in methods_to_check:
            try:
                resp = await client.post(node_url, json={
                    "jsonrpc": "2.0", "method": method,
                    "params": params, "id": 1
                })
                data = resp.json()
                if "result" in data:
                    available.append(method.split(".")[0])
            except Exception:
                pass
    return list(set(available))
```

**Decision guide:** Run a consensus node if you are a witness. Run an API node if you are building a dApp. Only run a full node if you need complete historical data.'''
    ),
    (
        "hive_architecture/chain-replay-from-block-log",
        r'''How do I replay the Hive blockchain from a block_log file? What is the process and how long does it take?''',
        r'''<think>
Chain replay rebuilds the shared memory state from the block_log file.
This is needed when: switching plugins, corrupted shared memory, or
setting up a new node. The block_log is the canonical append-only record
of all blocks. Replay reads each block and re-applies all operations.
It is single-threaded and CPU-bound — can take 1-3 days for full chain.
Users can download a recent block_log snapshot to skip most of the sync.
Important flags: --replay-blockchain and --force-replay.
</think>

Replay rebuilds your node's state (shared memory) by re-processing every block from the `block_log` file. This is necessary when changing plugins, recovering from corruption, or initializing a new node.

```bash
#!/bin/bash
# Hive chain replay process

DATA_DIR="/data/hived"
BLOCK_LOG="$DATA_DIR/blockchain/block_log"

# ---- Option 1: Download a snapshot (fastest start) ----
# Community snapshots avoid replaying from genesis
# Check: https://files.privex.io/hive/ or similar providers
wget -c "https://snapshot-provider.example/block_log" -O "$BLOCK_LOG"

# ---- Option 2: Replay from existing block_log ----
# Stop hived first
pkill -SIGINT hived
sleep 10

# Remove existing shared memory (will be rebuilt)
rm -f "$DATA_DIR/blockchain/shared_memory.bin"

# Start replay — this re-applies all blocks from block_log
./hived --data-dir="$DATA_DIR" --replay-blockchain 2>&1 | tee replay.log &

# Monitor progress
tail -f replay.log | grep -E "Block|replay"

# ---- Force replay (if state is corrupted) ----
# --force-replay ignores existing shared memory state completely
./hived --data-dir="$DATA_DIR" --force-replay
```

```python
import subprocess
import re
import time

def monitor_replay(log_path: str = "replay.log"):
    """Monitor hived replay progress by parsing log output."""
    last_block = 0
    chain_head = 80_000_000  # approximate current head block

    with open(log_path, "r") as f:
        f.seek(0, 2)  # seek to end
        while True:
            line = f.readline()
            if not line:
                time.sleep(1)
                continue
            # Look for block progress lines
            match = re.search(r"Block\s+(\d+)", line)
            if match:
                block = int(match.group(1))
                if block > last_block:
                    pct = (block / chain_head) * 100
                    rate = block - last_block  # blocks per interval
                    eta_blocks = chain_head - block
                    eta_hours = (eta_blocks / max(rate, 1)) / 3600
                    print(f"Block {block:>10,} / {chain_head:,} "
                          f"({pct:.1f}%) ETA: {eta_hours:.1f}h")
                    last_block = block
```

**Timing expectations:**
- NVMe SSD + modern CPU: ~1-2 days for full replay
- HDD: 3-5+ days (I/O bound)
- Replay is mostly single-threaded — clock speed matters more than core count
- The `block_log` file is ~400GB+ and growing'''
    ),
    (
        "hive_architecture/shared-memory-configuration",
        r'''What is Hive's shared memory file and how should I configure shared-file-size and shared-file-dir?''',
        r'''<think>
Hive's shared memory is a memory-mapped file (mmap) that holds the current
chain state: accounts, balances, witnesses, RC data, etc. It is NOT the
block history — that is in block_log. The shared-file-size must be large
enough for all state data. If it fills up, hived crashes. shared-file-dir
can point to /dev/shm (tmpfs) for speed but requires enough RAM, or to
NVMe for persistence. This is one of the most common operational issues.
The file only grows — it never shrinks even if data is deleted.
</think>

Hive's shared memory file (`shared_memory.bin`) is a memory-mapped file containing the entire current chain state — all accounts, balances, witness data, RC state, and plugin indexes. It is NOT the block history.

```ini
# config.ini shared memory settings

# Size must accommodate all state data + growth room
# Too small → hived crashes when state exceeds allocation
# Too large → wastes disk/RAM reservation
shared-file-size = 64G

# Location options:
# Option 1: tmpfs (fastest, but uses RAM)
shared-file-dir = /dev/shm
# Requires: mount -t tmpfs -o size=70G tmpfs /dev/shm

# Option 2: NVMe SSD (persistent, almost as fast)
shared-file-dir = /data/hived/shm

# Option 3: Regular SSD (slower but works)
shared-file-dir = /data/hived/blockchain
```

```python
import os
import struct

def check_shared_memory(shm_path: str = "/data/hived/blockchain/shared_memory.bin"):
    """Check shared memory file size and estimate utilization."""
    if not os.path.exists(shm_path):
        print("Shared memory file not found — node may not be initialized")
        return

    file_size = os.path.getsize(shm_path)
    file_gb = file_size / (1024 ** 3)
    print(f"Shared memory file: {file_gb:.1f} GB")

    # Check available space on the mount point
    stat = os.statvfs(os.path.dirname(shm_path))
    free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
    total_gb = (stat.f_blocks * stat.f_frsize) / (1024 ** 3)
    print(f"Mount point: {free_gb:.1f} GB free / {total_gb:.1f} GB total")

    if free_gb < 10:
        print("WARNING: Low disk space — hived may crash if shared memory needs to grow")

check_shared_memory()
```

**Key points:**
- `/dev/shm` (tmpfs): fastest, but the file is lost on reboot — requires replay
- NVMe: best balance of speed and persistence
- Always set `shared-file-size` 10-20% larger than current usage to allow growth
- Monitor with `ls -lh` — if the file is approaching the configured limit, increase it and restart'''
    ),
    (
        "hive_architecture/plugin-system-overview",
        r'''Give me an overview of Hive's plugin system. What are the key plugins like account_history and condenser_api?''',
        r'''<think>
Hive's plugin architecture is modular — you only load what you need.
Plugins fall into categories: consensus (chain, witness, p2p), API
(condenser_api, database_api, block_api), and indexing (account_history,
market_history). Each plugin adds memory/storage overhead. The condenser_api
is the legacy Steem-compatible API, while database_api is the modern one.
account_history is the heaviest plugin — it indexes every operation for
every account. I should list the main plugins and their roles.
</think>

Hive uses a modular plugin architecture. Each plugin adds specific functionality and has its own resource overhead:

```
Category     | Plugin                  | Purpose                          | Overhead
-------------|-------------------------|----------------------------------|----------
Core         | chain                   | Block processing, state          | Required
Core         | p2p                     | Peer-to-peer networking          | Required
Core         | webserver               | HTTP/WS server for API           | Required
Consensus    | witness                 | Block production (witnesses only)| Low
API          | condenser_api           | Legacy Steem-compatible RPC      | Low
API          | database_api            | Modern typed RPC interface       | Low
API          | block_api               | Block/transaction queries        | Low
API          | network_broadcast_api   | Submit transactions              | Low
API          | rc_api                  | Resource credit queries          | Low
API          | account_by_key_api      | Look up accounts by public key   | Low
Indexing     | account_history_api     | Per-account operation history    | HIGH
Indexing     | market_history_api      | Internal market OHLCV data       | Medium
Indexing     | reputation_api          | Account reputation scores        | Medium
```

```python
import httpx

async def get_plugin_info(node: str = "https://api.hive.blog"):
    """Demonstrate calls to different Hive API plugins."""
    async with httpx.AsyncClient(timeout=15) as client:
        async def call(method, params):
            resp = await client.post(node, json={
                "jsonrpc": "2.0", "method": method, "params": params, "id": 1
            })
            return resp.json().get("result")

        # condenser_api — legacy but widely used
        props = await call("condenser_api.get_dynamic_global_properties", [])
        print(f"Head block: {props['head_block_number']}")

        # database_api — modern, uses named params
        dgpo = await call("database_api.get_dynamic_global_properties", {})
        print(f"Current witness: {dgpo['current_witness']}")

        # block_api — fetch specific blocks
        block = await call("block_api.get_block", {"block_num": 1})
        print(f"Genesis block witness: {block['block']['witness']}")

        # account_history_api — operation history per account
        history = await call("account_history_api.get_account_history", {
            "account": "hiveio", "start": -1, "limit": 3
        })
        for entry in history.get("history", []):
            op = entry[1]["op"]
            print(f"  Op: {op['type']} at block {entry[1]['block']}")

        # rc_api — resource credit info
        rc = await call("rc_api.find_rc_accounts", {"accounts": ["hiveio"]})
        rc_data = rc["rc_accounts"][0]
        print(f"RC mana: {int(rc_data['rc_manabar']['current_mana']):,}")
```

**Choosing plugins:** Start with the minimal set for your use case. Each indexing plugin adds gigabytes to shared memory and slows replay. The `account_history_api` alone can add 20+ GB of state.'''
    ),
    (
        "hive_architecture/haf-framework-basics",
        r'''What is the Hive Application Framework (HAF) and how does it differ from running raw hived plugins?''',
        r'''<think>
HAF is a major architectural improvement for Hive. Instead of writing C++
plugins for hived, HAF streams all blockchain operations into a PostgreSQL
database. Applications then query Postgres using SQL. This decouples app
development from node software — devs write SQL/Python/JS instead of C++.
HAF handles block reversibility (fork handling) automatically. Hivemind
has been ported to HAF. Key benefits: standard tooling, no C++ needed,
shared database for multiple apps, automatic fork resolution.
</think>

HAF (Hive Application Framework) is Hive's modern application layer. Instead of writing C++ hived plugins, HAF streams all blockchain operations into PostgreSQL, letting you build apps with SQL.

**Architecture comparison:**

```
Traditional (hived plugin):
  hived → C++ plugin → custom storage → custom API
  Pros: fastest possible
  Cons: must write C++, coupled to hived release cycle

HAF approach:
  hived → HAF plugin → PostgreSQL → your app (Python/JS/SQL)
  Pros: standard tooling, shared DB, fork handling built-in
  Cons: slight latency overhead (DB writes)
```

```python
import psycopg2
from contextlib import contextmanager

# HAF stores all operations in a structured PostgreSQL schema
HAF_DB = "postgresql://haf_user:password@localhost:5432/haf_block_log"

@contextmanager
def haf_connection():
    conn = psycopg2.connect(HAF_DB)
    try:
        yield conn
    finally:
        conn.close()

def query_recent_transfers(limit: int = 10):
    """Query recent transfer operations directly from HAF's PostgreSQL."""
    with haf_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    ho.block_num,
                    ho.trx_in_block,
                    ho.body::json->>'from' AS sender,
                    ho.body::json->>'to' AS recipient,
                    ho.body::json->>'amount' AS amount
                FROM hive.operations ho
                WHERE ho.op_type_id = 2  -- transfer operation
                ORDER BY ho.block_num DESC
                LIMIT %s
            """, (limit,))
            for row in cur.fetchall():
                print(f"Block {row[0]}: {row[2]} → {row[3]}: {row[4]}")

def create_haf_app_context(app_name: str):
    """Register a HAF application context for fork-safe processing."""
    with haf_connection() as conn:
        with conn.cursor() as cur:
            # HAF tracks which blocks your app has processed
            # On forks, it automatically rolls back to the fork point
            cur.execute("SELECT hive.app_create_context(%s)", (app_name,))
            conn.commit()
            print(f"Created HAF context: {app_name}")

def process_blocks_with_haf(app_name: str, start_block: int):
    """Process blocks using HAF's fork-aware framework."""
    with haf_connection() as conn:
        with conn.cursor() as cur:
            # Get the next block range to process
            cur.execute("""
                SELECT hive.app_next_block(%s)
            """, (app_name,))
            result = cur.fetchone()
            if result and result[0]:
                block_num = result[0]
                # Process operations in this block
                cur.execute("""
                    SELECT op_type_id, body::text
                    FROM hive.operations
                    WHERE block_num = %s
                """, (block_num,))
                for op_type, body in cur.fetchall():
                    print(f"  Processing op type {op_type} in block {block_num}")
            conn.commit()
```

**Key HAF benefits:**
- Fork handling: HAF auto-reverts your app state when micro-forks occur
- Shared data: multiple apps share one PostgreSQL database
- Standard tooling: use any language with a Postgres driver
- Hivemind (social indexer) is already ported to HAF'''
    ),
    (
        "hive_architecture/custom-api-endpoint",
        r'''How can I develop a custom API endpoint on top of Hive using HAF and a web framework?''',
        r'''<think>
The user wants to build a custom API on top of HAF's PostgreSQL data.
This is a common pattern: HAF indexes blockchain data into Postgres,
then a Python/Node web framework serves custom queries. I should show
a FastAPI example that queries HAF tables. Key considerations: connection
pooling, caching for hot data, and handling the reversible/irreversible
distinction. This is an advanced topic since it combines HAF + web dev.
</think>

You can build custom API endpoints by querying HAF's PostgreSQL database from any web framework. Here is a FastAPI example:

```python
from fastapi import FastAPI, HTTPException, Query
from contextlib import asynccontextmanager
import asyncpg
from typing import Optional

app = FastAPI(title="Custom Hive API")

# Connection pool for HAF PostgreSQL
pool: asyncpg.Pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(
        "postgresql://haf_user:password@localhost:5432/haf_block_log",
        min_size=5, max_size=20
    )
    yield
    await pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/api/v1/account/{account}/transfers")
async def get_account_transfers(
    account: str,
    limit: int = Query(default=20, le=100),
    offset: int = 0
):
    """Get transfer history for an account from HAF."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                ho.block_num,
                ho.timestamp,
                ho.body::json->>'from' AS sender,
                ho.body::json->>'to' AS recipient,
                ho.body::json->>'amount' AS amount,
                ho.body::json->>'memo' AS memo
            FROM hive.operations ho
            WHERE ho.op_type_id = 2
              AND (ho.body::json->>'from' = $1 OR ho.body::json->>'to' = $1)
            ORDER BY ho.block_num DESC
            LIMIT $2 OFFSET $3
        """, account, limit, offset)

        if not rows:
            raise HTTPException(404, f"No transfers found for @{account}")

        return {
            "account": account,
            "transfers": [dict(r) for r in rows],
            "count": len(rows)
        }

@app.get("/api/v1/custom_json/{op_id}")
async def get_custom_json_ops(
    op_id: str,
    since_block: Optional[int] = None,
    limit: int = Query(default=50, le=500)
):
    """Query custom_json operations by protocol ID (e.g., 'sm_' for Splinterlands)."""
    async with pool.acquire() as conn:
        query = """
            SELECT
                ho.block_num,
                ho.timestamp,
                ho.body::json->>'required_posting_auths' AS signers,
                ho.body::json->>'json' AS payload
            FROM hive.operations ho
            WHERE ho.op_type_id = 18
              AND ho.body::json->>'id' = $1
        """
        params = [op_id]
        if since_block:
            query += " AND ho.block_num >= $2"
            params.append(since_block)
        query += f" ORDER BY ho.block_num DESC LIMIT ${len(params)+1}"
        params.append(limit)

        rows = await conn.fetch(query, *params)
        return {"op_id": op_id, "operations": [dict(r) for r in rows]}

@app.get("/api/v1/stats/daily_transfers")
async def daily_transfer_stats(days: int = Query(default=7, le=30)):
    """Aggregate transfer stats — example of custom analytics endpoint."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                date_trunc('day', ho.timestamp) AS day,
                COUNT(*) AS transfer_count,
                COUNT(DISTINCT ho.body::json->>'from') AS unique_senders
            FROM hive.operations ho
            WHERE ho.op_type_id = 2
              AND ho.timestamp > NOW() - make_interval(days => $1)
            GROUP BY day ORDER BY day DESC
        """, days)
        return {"stats": [dict(r) for r in rows]}
```

Run with `uvicorn main:app --host 0.0.0.0 --port 8000`. This gives you a custom REST API backed by HAF's indexed blockchain data, with connection pooling and pagination built in.'''
    ),
    (
        "hive_architecture/node-health-monitoring",
        r'''Write a script to monitor the health of a Hive API node — checking block freshness, API responsiveness, and peer count.''',
        r'''<think>
The user wants a monitoring script for Hive nodes. Key health indicators:
1. Head block age (should be <10 seconds behind real time)
2. API response time (latency on common calls)
3. Peer count (should have >5 P2P peers)
4. Last irreversible block lag (head - LIB should be <30 blocks)
5. Memory/disk usage of hived process
I should write a practical Python script that can be run via cron or
as a monitoring daemon. Include alerting thresholds.
</think>

Here is a comprehensive Hive node health monitoring script:

```python
#!/usr/bin/env python3
"""Hive API node health monitor — checks block freshness, latency, peers."""

import httpx
import time
import json
import sys
from datetime import datetime, timezone
from dataclasses import dataclass

@dataclass
class HealthCheck:
    name: str
    status: str  # "ok", "warn", "critical"
    value: str
    threshold: str

class HiveNodeMonitor:
    def __init__(self, node_url: str = "http://localhost:8091"):
        self.node_url = node_url
        self.checks: list[HealthCheck] = []

    def _rpc(self, method: str, params=None) -> dict:
        """Make a JSON-RPC call and return result."""
        if params is None:
            params = {} if "." in method and not method.startswith("condenser") else []
        resp = httpx.post(self.node_url, json={
            "jsonrpc": "2.0", "method": method, "params": params, "id": 1
        }, timeout=10)
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"RPC error: {data['error']}")
        return data["result"]

    def check_block_freshness(self):
        """Head block should be within 10 seconds of wall clock."""
        start = time.monotonic()
        props = self._rpc("condenser_api.get_dynamic_global_properties")
        latency_ms = (time.monotonic() - start) * 1000

        head_time = datetime.strptime(props["time"], "%Y-%m-%dT%H:%M:%S")
        head_time = head_time.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - head_time).total_seconds()

        status = "ok" if age_seconds < 10 else "warn" if age_seconds < 30 else "critical"
        self.checks.append(HealthCheck(
            "block_freshness", status,
            f"{age_seconds:.0f}s behind (block {props['head_block_number']})",
            "<10s ok, <30s warn"
        ))

        self.checks.append(HealthCheck(
            "api_latency", "ok" if latency_ms < 500 else "warn",
            f"{latency_ms:.0f}ms", "<500ms"
        ))

    def check_irreversibility_lag(self):
        """Gap between head and last irreversible should be <30 blocks."""
        props = self._rpc("condenser_api.get_dynamic_global_properties")
        head = props["head_block_number"]
        lib = props["last_irreversible_block_num"]
        lag = head - lib

        status = "ok" if lag < 30 else "warn" if lag < 50 else "critical"
        self.checks.append(HealthCheck(
            "irreversibility_lag", status,
            f"{lag} blocks ({lag * 3}s)", "<30 blocks"
        ))

    def check_peer_count(self):
        """Should have at least 5 P2P peers."""
        try:
            info = self._rpc("condenser_api.get_version")
            # Peer count not directly in version — check network API
            peers = self._rpc("network_broadcast_api.get_info", {})
            # Fallback: just verify API is responsive
            self.checks.append(HealthCheck(
                "api_version", "ok", info.get("blockchain_version", "unknown"), "responsive"
            ))
        except Exception:
            self.checks.append(HealthCheck("api_version", "ok", "version check skipped", "N/A"))

    def check_rc_api(self):
        """Verify RC API plugin is responding."""
        try:
            rc = self._rpc("rc_api.find_rc_accounts", {"accounts": ["hiveio"]})
            has_data = len(rc.get("rc_accounts", [])) > 0
            self.checks.append(HealthCheck(
                "rc_api", "ok" if has_data else "warn", "responsive" if has_data else "empty", "has data"
            ))
        except Exception as e:
            self.checks.append(HealthCheck("rc_api", "critical", str(e)[:80], "responsive"))

    def run_all(self) -> bool:
        """Run all checks and return True if healthy."""
        self.checks = []
        for check_fn in [
            self.check_block_freshness,
            self.check_irreversibility_lag,
            self.check_peer_count,
            self.check_rc_api,
        ]:
            try:
                check_fn()
            except Exception as e:
                self.checks.append(HealthCheck(check_fn.__name__, "critical", str(e)[:100], "no error"))

        # Print report
        print(f"{'Check':<25} {'Status':<10} {'Value':<45} {'Threshold'}")
        print("-" * 95)
        for c in self.checks:
            icon = {"ok": "OK", "warn": "WARN", "critical": "CRIT"}[c.status]
            print(f"{c.name:<25} {icon:<10} {c.value:<45} {c.threshold}")

        criticals = [c for c in self.checks if c.status == "critical"]
        if criticals:
            print(f"\n{len(criticals)} CRITICAL issue(s) detected!")
            return False
        return True

if __name__ == "__main__":
    node = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8091"
    monitor = HiveNodeMonitor(node)
    healthy = monitor.run_all()
    sys.exit(0 if healthy else 1)
```

Run with `python monitor_node.py http://your-node:8091`. Exit code 1 on critical failures makes it suitable for cron or monitoring systems like Nagios/Prometheus.'''
    ),
    (
        "hive_architecture/p2p-network-configuration",
        r'''How do I configure P2P networking for a Hive node? What seed nodes should I use and how do I optimize peer connections?''',
        r'''<think>
P2P configuration is important for node performance and sync speed.
Key settings: p2p-endpoint, p2p-seed-node, p2p-max-connections.
Seed nodes are the initial peers used to discover the network.
The user should know about: choosing geographically diverse seeds,
setting max connections based on bandwidth, and firewall requirements.
Port 2001 is the default P2P port. I should list real seed nodes
and explain the peer discovery process.
</think>

P2P networking determines how your Hive node discovers peers and syncs blocks. Proper configuration affects sync speed and resilience.

```ini
# config.ini — P2P settings

# Your node's P2P listen address
p2p-endpoint = 0.0.0.0:2001

# Seed nodes — used for initial peer discovery
# Use geographically diverse seeds for resilience
p2p-seed-node = seed.hive.blog:2001
p2p-seed-node = seed.openhive.network:2001
p2p-seed-node = hive-seed.arcange.eu:2001
p2p-seed-node = hive-seed.roelandp.nl:2001
p2p-seed-node = seed.hivekings.com:2001

# Maximum peer connections (default 200, reduce on limited bandwidth)
# More peers = faster block propagation but more bandwidth
p2p-max-connections = 100

# Optional: force specific peers (always stay connected)
p2p-force-validate = true
```

```bash
#!/bin/bash
# Firewall and network setup for Hive P2P

# Allow P2P traffic (port 2001)
sudo ufw allow 2001/tcp comment "Hive P2P"

# Allow API traffic if serving (8091 HTTP, 8090 WS)
sudo ufw allow 8091/tcp comment "Hive API HTTP"
sudo ufw allow 8090/tcp comment "Hive API WebSocket"

# Check current P2P connections
curl -s http://localhost:8091 \
  -d '{"jsonrpc":"2.0","method":"condenser_api.get_version","params":[],"id":1}' \
  | python3 -m json.tool

# Monitor P2P peer count over time
watch -n 10 "netstat -tn | grep ':2001' | grep ESTABLISHED | wc -l"
```

```python
import httpx
import socket

def check_p2p_connectivity(node_host: str, p2p_port: int = 2001, timeout: float = 5.0):
    """Verify that a Hive node's P2P port is reachable."""
    try:
        sock = socket.create_connection((node_host, p2p_port), timeout=timeout)
        sock.close()
        print(f"P2P port {p2p_port} on {node_host}: OPEN")
        return True
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        print(f"P2P port {p2p_port} on {node_host}: CLOSED ({e})")
        return False

SEED_NODES = [
    "seed.hive.blog",
    "seed.openhive.network",
    "hive-seed.arcange.eu",
    "hive-seed.roelandp.nl",
]

print("Checking seed node P2P connectivity:")
for seed in SEED_NODES:
    check_p2p_connectivity(seed)
```

**Best practices:**
- Use 5-10 seed nodes from different operators for redundancy
- Set `p2p-max-connections` based on bandwidth: 50 for limited, 200 for datacenter
- Open port 2001 in your firewall for inbound P2P
- Witnesses should use private P2P networks between their primary and failover nodes'''
    ),
    (
        "hive_architecture/block-validation-process",
        r'''Walk me through the block validation process on Hive. What checks does a node perform when it receives a new block?''',
        r'''<think>
Block validation on Hive involves multiple steps. When a node receives a
block via P2P, it verifies: block header (previous hash, timestamp, witness),
witness signature, witness scheduling (correct witness for this slot),
transaction signatures and authorities, operation-specific validation
(sufficient balance, valid account names, etc.), and state transitions.
If any check fails, the block is rejected. This is expert-level content
about consensus internals. I should present it as a clear sequence.
</think>

When a Hive node receives a block from the P2P network, it runs a multi-stage validation pipeline before applying it to state:

```
Block Validation Pipeline:
  1. Header checks
     ├── previous_block_hash matches local head
     ├── timestamp within ±30s of expected slot time
     └── block_num == head_block_num + 1

  2. Witness verification
     ├── witness matches the scheduled producer for this slot
     └── block signature is valid for witness's signing key

  3. Transaction validation (for each tx in block)
     ├── transaction not expired (expiration > head_block_time)
     ├── ref_block matches a recent block (anti-replay)
     ├── all required signatures present and valid
     └── authority requirements met (posting/active/owner)

  4. Operation validation (for each op in each tx)
     ├── operation-specific rules (balance >= transfer amount, etc.)
     ├── account existence checks
     ├── resource credit sufficiency
     └── hard-fork-specific rule enforcement

  5. State application
     ├── apply all operations to shared memory
     ├── update head block pointer
     └── check if block becomes irreversible (LIB advance)
```

```python
from dataclasses import dataclass, field
from typing import Optional
import hashlib
import json

@dataclass
class Block:
    block_num: int
    previous: str  # hash of previous block
    timestamp: str
    witness: str
    witness_signature: str
    transactions: list = field(default_factory=list)

@dataclass
class ValidationResult:
    valid: bool
    stage: str
    error: Optional[str] = None

def validate_block(block: Block, chain_state: dict) -> ValidationResult:
    """Simplified block validation matching Hive's validation pipeline."""

    # Stage 1: Header checks
    if block.previous != chain_state["head_block_hash"]:
        return ValidationResult(False, "header", "previous block hash mismatch — possible fork")

    expected_num = chain_state["head_block_num"] + 1
    if block.block_num != expected_num:
        return ValidationResult(False, "header", f"expected block {expected_num}, got {block.block_num}")

    # Stage 2: Witness scheduling
    scheduled = chain_state["witness_schedule"][block.block_num % 21]
    if block.witness != scheduled:
        return ValidationResult(
            False, "witness",
            f"wrong witness: {block.witness} not scheduled (expected {scheduled})"
        )

    # Stage 3: Transaction validation
    for i, tx in enumerate(block.transactions):
        if tx.get("expiration", "") < block.timestamp:
            return ValidationResult(False, "transaction", f"tx[{i}] expired")
        # Verify signatures match required authorities
        required = set(tx.get("required_auths", []))
        signed = set(tx.get("signed_by", []))
        if not required.issubset(signed):
            missing = required - signed
            return ValidationResult(False, "transaction", f"tx[{i}] missing sigs: {missing}")

    # Stage 4: Operation validation (simplified)
    for tx in block.transactions:
        for op_type, op_data in tx.get("operations", []):
            if op_type == "transfer":
                sender_balance = chain_state["balances"].get(op_data["from"], 0)
                amount = float(op_data["amount"].split()[0])
                if sender_balance < amount:
                    return ValidationResult(False, "operation", "insufficient balance")

    return ValidationResult(True, "all_passed")

# Example usage
state = {
    "head_block_hash": "abc123",
    "head_block_num": 80000000,
    "witness_schedule": ["witness-a"] * 21,
    "balances": {"alice": 100.0}
}

block = Block(80000001, "abc123", "2026-03-07T12:00:00", "witness-a", "sig...")
result = validate_block(block, state)
print(f"Validation: {result.stage} — {'PASSED' if result.valid else result.error}")
```

If validation fails at any stage, the block is rejected and the node may disconnect from the peer that sent it.'''
    ),
    (
        "hive_architecture/transaction-lifecycle",
        r'''Explain the full lifecycle of a Hive transaction from creation to irreversibility.''',
        r'''<think>
The transaction lifecycle on Hive goes through several stages:
1. Creation (client builds and signs the tx)
2. Broadcasting (sent to an API node via network_broadcast_api)
3. Mempool / pending (node validates and forwards to P2P network)
4. Inclusion in a block (witness picks it up)
5. Head block confirmation (in the chain but still reversible)
6. Irreversibility (2/3+1 witnesses confirm → LIB advances past it)
Key details: expiration window (60s default), ref_block for replay protection,
and the reversible→irreversible transition. This is intermediate-advanced.
</think>

A Hive transaction goes through six distinct stages from creation to finality:

```
Stage 1: CREATE         → Client builds transaction JSON
Stage 2: SIGN           → Client signs with appropriate key(s)
Stage 3: BROADCAST      → Sent to API node via network_broadcast_api
Stage 4: PENDING        → Node validates, forwards via P2P to witnesses
Stage 5: INCLUDED       → Witness includes in a block (reversible)
Stage 6: IRREVERSIBLE   → 15/21 witnesses confirm → permanent
```

```python
import json
import time
import hashlib
import struct
from datetime import datetime, timezone, timedelta
import httpx

class TransactionLifecycle:
    """Demonstrates the full lifecycle of a Hive transaction."""

    def __init__(self, node: str = "https://api.hive.blog"):
        self.node = node
        self.client = httpx.Client(timeout=15)

    def _rpc(self, method: str, params):
        resp = self.client.post(self.node, json={
            "jsonrpc": "2.0", "method": method, "params": params, "id": 1
        })
        return resp.json()["result"]

    def stage1_create(self, sender: str, recipient: str, amount: str, memo: str = ""):
        """Stage 1: Build the transaction structure."""
        # Get reference block for replay protection
        props = self._rpc("condenser_api.get_dynamic_global_properties", [])
        ref_block_num = props["head_block_number"] & 0xFFFF
        ref_block_prefix = struct.unpack_from(
            "<I", bytes.fromhex(props["head_block_id"]), 4
        )[0]

        # Expiration: 60 seconds from now (max 3600s)
        expiration = (
            datetime.strptime(props["time"], "%Y-%m-%dT%H:%M:%S")
            + timedelta(seconds=60)
        ).strftime("%Y-%m-%dT%H:%M:%S")

        tx = {
            "ref_block_num": ref_block_num,
            "ref_block_prefix": ref_block_prefix,
            "expiration": expiration,
            "operations": [
                ["transfer", {
                    "from": sender,
                    "to": recipient,
                    "amount": amount,
                    "memo": memo
                }]
            ],
            "extensions": []
        }
        print(f"[CREATE] Transaction built, expires: {expiration}")
        return tx

    def stage2_sign(self, tx: dict, signing_key: str):
        """Stage 2: Sign the transaction (normally done client-side)."""
        # In practice, use beem or dhive for proper signing
        # The signing process: SHA256(chain_id + serialized_tx) → ECDSA sign
        print(f"[SIGN] Transaction signed with active key")
        tx["signatures"] = ["<signature_would_go_here>"]
        return tx

    def stage3_broadcast(self, signed_tx: dict):
        """Stage 3: Broadcast to the network."""
        # network_broadcast_api.broadcast_transaction
        # This is synchronous — waits for local validation
        print(f"[BROADCAST] Sent to {self.node}")
        # result = self._rpc("network_broadcast_api.broadcast_transaction", {"trx": signed_tx})
        return signed_tx

    def stage5_track_inclusion(self, tx_id: str, max_wait: int = 30):
        """Stage 5: Wait for transaction to appear in a block."""
        print(f"[TRACKING] Waiting for tx {tx_id[:12]}... in a block")
        for attempt in range(max_wait // 3):
            time.sleep(3)
            try:
                result = self._rpc("condenser_api.get_transaction", [tx_id])
                block_num = result.get("block_num")
                if block_num:
                    print(f"[INCLUDED] Found in block {block_num}")
                    return block_num
            except Exception:
                continue
        print("[TIMEOUT] Transaction not found in time — may have expired")
        return None

    def stage6_wait_irreversible(self, block_num: int, max_wait: int = 90):
        """Stage 6: Wait for block to become irreversible."""
        print(f"[FINALITY] Waiting for block {block_num} to become irreversible...")
        for _ in range(max_wait // 3):
            props = self._rpc("condenser_api.get_dynamic_global_properties", [])
            lib = props["last_irreversible_block_num"]
            if lib >= block_num:
                print(f"[IRREVERSIBLE] Block {block_num} is now final (LIB={lib})")
                return True
            print(f"  LIB={lib}, need={block_num}, gap={block_num - lib}")
            time.sleep(3)
        return False

# Typical timeline:
# 0s    → create + sign
# ~0.5s → broadcast + validation
# 0-3s  → included in next block (pending in mempool)
# ~45s  → block becomes irreversible (15/21 witnesses confirm)
```

**Key details:**
- `ref_block_num/prefix`: prevents replay attacks — tx is only valid near a specific block
- Expiration: if not included within this window, the tx is permanently dropped
- Reversible window: between inclusion and irreversibility, micro-forks can remove your tx (rare but possible)'''
    ),
    (
        "hive_architecture/operation-types-and-ids",
        r'''What are the main Hive blockchain operation types and their IDs? I need a reference for parsing raw blocks.''',
        r'''<think>
Hive has about 50+ operation types, each with a numeric ID. The user needs
a reference for parsing blocks. I should list the most commonly used ones
grouped by category: transfers, social, witness, governance, and virtual ops.
Virtual operations are generated by the chain (not submitted by users).
The op type ID is important for HAF queries and raw block parsing.
I should provide a practical lookup structure.
</think>

Here is a reference of Hive operation types with their numeric IDs, useful for parsing raw blocks and HAF queries:

```python
"""Hive operation types reference — IDs match the blockchain's internal numbering."""

# Core financial operations
HIVE_OPS = {
    # -- Transfers & Finance --
    0:  "vote",
    1:  "comment",                     # also used for posts (top-level comments)
    2:  "transfer",
    3:  "transfer_to_vesting",         # power up (HIVE → HIVE POWER)
    4:  "withdraw_vesting",            # power down (HIVE POWER → HIVE, 13 weeks)
    5:  "limit_order_create",          # internal DEX
    6:  "limit_order_cancel",
    7:  "feed_publish",                # witness price feed
    8:  "convert",                     # HBD → HIVE conversion (3.5 day delay)
    9:  "account_create",
    10: "account_update",

    # -- Social --
    11: "witness_update",
    12: "account_witness_vote",
    13: "account_witness_proxy",
    17: "delete_comment",
    18: "custom_json",                 # layer-2 protocols (most common op!)
    19: "comment_options",             # beneficiaries, max payout, etc.

    # -- Authority & Keys --
    20: "set_withdraw_vesting_route",
    22: "claim_account",
    23: "create_claimed_account",
    24: "request_account_recovery",
    25: "recover_account",
    26: "change_recovery_account",

    # -- Governance --
    14: "custom",                      # raw binary custom op (rare)
    27: "escrow_transfer",
    28: "escrow_dispute",
    29: "escrow_release",
    30: "escrow_approve",
    33: "decline_voting_rights",

    # -- HBD & Savings --
    32: "transfer_to_savings",
    33: "transfer_from_savings",
    34: "cancel_transfer_from_savings",
    20: "set_withdraw_vesting_route",

    # -- Proposals (DHF) --
    44: "create_proposal",
    45: "update_proposal_votes",
    46: "remove_proposal",

    # -- Recurrent --
    49: "recurrent_transfer",

    # -- Virtual Operations (chain-generated, not user-submitted) --
    # These appear in account history but cannot be broadcast
    "virtual": {
        52: "fill_convert_request",
        53: "author_reward",
        54: "curation_reward",
        56: "fill_vesting_withdraw",
        57: "fill_order",              # DEX order matched
        59: "return_vesting_delegation",
        62: "producer_reward",         # witness block reward
        63: "clear_null_account_balance",
        72: "proposal_pay",            # DHF payout
        78: "fill_recurrent_transfer",
    }
}

def get_op_name(op_type_id: int) -> str:
    """Look up operation name by numeric ID."""
    return HIVE_OPS.get(op_type_id, f"unknown_op_{op_type_id}")

def parse_block_operations(block: dict) -> list[dict]:
    """Parse all operations from a raw block."""
    ops = []
    for tx_idx, tx in enumerate(block.get("transactions", [])):
        for op_idx, (op_type, op_data) in enumerate(tx.get("operations", [])):
            ops.append({
                "tx_index": tx_idx,
                "op_index": op_idx,
                "type": op_type,
                "data": op_data
            })
    return ops

# HAF query example: find all custom_json ops in a block range
HAF_QUERY = """
SELECT block_num, body::json->>'id' AS protocol_id,
       body::json->>'json' AS payload
FROM hive.operations
WHERE op_type_id = 18            -- custom_json
  AND block_num BETWEEN %s AND %s
ORDER BY block_num;
"""
```

**Most frequent operations by volume:** `custom_json` (18) dominates — it powers Splinterlands, PeakD notifications, Podping, and most layer-2 apps. `vote` (0) and `comment` (1) are the next most common.'''
    ),
    (
        "hive_architecture/hardfork-history",
        r'''What are the major Hive hardforks and what key changes did they introduce?''',
        r'''<think>
Hive forked from Steem at HF23, so its hardfork numbering starts there.
Key hardforks: HF23 (genesis/fork from Steem), HF24 (governance fixes),
HF25 (reward curve changes, recurrent transfers), HF26 (RC delegations,
governance improvements), HF27 (HBD stabilizer, HIVE power down changes),
HF28 (most recent, various improvements). Witnesses vote on hardfork
activation. I should list the major changes concisely.
</think>

Hive's hardfork history (starting from the Steem fork):

```
HF  | Date       | Key Changes
----|------------|--------------------------------------------------
23  | 2020-03-20 | Genesis: Forked from Steem blockchain
    |            | - Excluded Steemit Inc stake (ninja-mined)
    |            | - Community governance model established
    |            |
24  | 2020-10-06 | Governance & stability
    |            | - 30-day powerdown option (was 13 weeks only)
    |            | - Proposal (DHF) system improvements
    |            | - HBD savings interest rate (set by witnesses)
    |            |
25  | 2021-06-30 | Economics & features
    |            | - Convergent linear reward curve (reduces abuse)
    |            | - Recurrent transfers (subscription payments)
    |            | - HBD stabilization improvements
    |            | - Comment beneficiary enforcement fixes
    |            |
26  | 2022-10-11 | RC & governance
    |            | - RC delegations (delegate resource credits)
    |            | - Governance vote expiration (must re-vote)
    |            | - Witness vote decay to prevent stale votes
    |            | - Faster account creation
    |            |
27  | 2023-xx-xx | HBD & performance
    |            | - HBD print rate adjustments
    |            | - Block size optimizations
    |            | - Various consensus bug fixes
    |            |
28  | 2024-xx-xx | Latest improvements
    |            | - Further HBD stability mechanisms
    |            | - Performance and security fixes
```

```python
import httpx

def get_hardfork_info(node: str = "https://api.hive.blog"):
    """Query current hardfork version and next scheduled hardfork."""
    client = httpx.Client(timeout=10)

    # Current hardfork version
    result = client.post(node, json={
        "jsonrpc": "2.0",
        "method": "database_api.get_hardfork_properties",
        "params": {},
        "id": 1
    }).json()["result"]

    print(f"Current HF: {result['current_hardfork_version']}")
    print(f"Last HF time: {result['last_hardfork']}")
    print(f"Next HF: {result.get('next_hardfork_version', 'none scheduled')}")
    print(f"Next HF time: {result.get('next_hardfork_time', 'N/A')}")

    # Witness hardfork votes
    props = client.post(node, json={
        "jsonrpc": "2.0",
        "method": "condenser_api.get_active_witnesses",
        "params": [],
        "id": 1
    }).json()["result"]

    print(f"\nActive witnesses ({len(props)}):")
    for w_name in props[:5]:
        w = client.post(node, json={
            "jsonrpc": "2.0",
            "method": "condenser_api.get_witness_by_account",
            "params": [w_name],
            "id": 1
        }).json()["result"]
        print(f"  @{w_name}: running v{w['running_version']}, "
              f"HF vote: {w['hardfork_version_vote']}")

get_hardfork_info()
```

**How hardforks activate:** Witnesses signal readiness by setting `hardfork_version_vote` in their witness properties. When 17 of 21 top witnesses signal the new version, the hardfork activates at the scheduled time. This ensures consensus before changes take effect.'''
    ),
    (
        "hive_architecture/witness-failover-setup",
        r'''How do I set up a witness failover system on Hive so my witness keeps producing blocks if my primary node goes down?''',
        r'''<think>
Witness failover is critical — missed blocks hurt reputation and can
cause the community to unvote you. The standard setup: primary node
produces blocks, secondary monitors primary and takes over if it fails.
Key concern: NEVER have both nodes signing simultaneously (double production
= chain punishment). The failover script must disable the primary's signing
key before enabling the secondary. Tools: custom monitoring scripts or
community tools like conductor. This is expert-level.
</think>

Witness failover prevents missed blocks when your primary node fails. The critical rule: **never have two nodes signing simultaneously**.

```python
#!/usr/bin/env python3
"""Hive witness failover monitor — switches signing to backup node on failure."""

import time
import sys
import httpx
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass
class WitnessNode:
    name: str
    url: str
    is_primary: bool

class WitnessFailover:
    def __init__(
        self,
        witness_account: str,
        primary: WitnessNode,
        backup: WitnessNode,
        signing_key: str,
        disabled_key: str = "STM1111111111111111111111111111111114T1Anm",  # null key
        max_misses: int = 2,
        check_interval: int = 15
    ):
        self.witness = witness_account
        self.primary = primary
        self.backup = backup
        self.signing_key = signing_key
        self.disabled_key = disabled_key
        self.max_misses = max_misses
        self.check_interval = check_interval
        self.active_node = primary
        self.consecutive_failures = 0

    def check_node_health(self, node: WitnessNode) -> dict:
        """Check if a node is healthy and synced."""
        try:
            client = httpx.Client(timeout=5)
            resp = client.post(node.url, json={
                "jsonrpc": "2.0",
                "method": "condenser_api.get_dynamic_global_properties",
                "params": [], "id": 1
            })
            props = resp.json()["result"]
            head_time = datetime.strptime(props["time"], "%Y-%m-%dT%H:%M:%S")
            head_time = head_time.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - head_time).total_seconds()
            return {
                "healthy": age < 15,
                "head_block": props["head_block_number"],
                "age_seconds": age
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    def update_witness_key(self, new_key: str):
        """Update the witness signing key on-chain via broadcast."""
        # In production, use beem:
        # from beem import Hive
        # hive = Hive(keys=[active_key])
        # hive.witness_update(signing_key=new_key, account=self.witness, ...)
        print(f"[FAILOVER] Broadcasting witness_update: signing_key → {new_key[:20]}...")

    def failover_to_backup(self):
        """Switch block signing to the backup node."""
        print(f"[FAILOVER] Primary failed — switching to {self.backup.name}")
        # Step 1: Disable signing on primary (set null key briefly)
        # This ensures no double-signing during transition
        self.update_witness_key(self.disabled_key)
        time.sleep(6)  # Wait 2 block intervals

        # Step 2: Enable signing key on backup
        # Backup node must have the signing key in its config.ini
        self.update_witness_key(self.signing_key)
        self.active_node = self.backup
        print(f"[FAILOVER] Now producing on {self.backup.name}")

    def failback_to_primary(self):
        """Return block signing to the primary node."""
        print(f"[FAILBACK] Primary recovered — switching back")
        self.update_witness_key(self.disabled_key)
        time.sleep(6)
        self.update_witness_key(self.signing_key)
        self.active_node = self.primary
        self.consecutive_failures = 0

    def run(self):
        """Main monitoring loop."""
        print(f"Monitoring witness @{self.witness}")
        print(f"Primary: {self.primary.url} | Backup: {self.backup.url}")

        while True:
            health = self.check_node_health(self.active_node)

            if health["healthy"]:
                self.consecutive_failures = 0
                print(f"[OK] {self.active_node.name} block={health['head_block']} "
                      f"age={health['age_seconds']:.0f}s")
            else:
                self.consecutive_failures += 1
                print(f"[WARN] {self.active_node.name} unhealthy "
                      f"({self.consecutive_failures}/{self.max_misses})")

                if self.consecutive_failures >= self.max_misses:
                    if self.active_node == self.primary:
                        backup_health = self.check_node_health(self.backup)
                        if backup_health["healthy"]:
                            self.failover_to_backup()
                        else:
                            print("[CRITICAL] Both nodes unhealthy!")

            # Check if primary recovered (for failback)
            if self.active_node == self.backup:
                primary_health = self.check_node_health(self.primary)
                if primary_health["healthy"]:
                    self.failback_to_primary()

            time.sleep(self.check_interval)

if __name__ == "__main__":
    failover = WitnessFailover(
        witness_account="mywitness",
        primary=WitnessNode("primary", "http://primary-node:8091", True),
        backup=WitnessNode("backup", "http://backup-node:8091", False),
        signing_key="STM...",
    )
    failover.run()
```

**Critical rules:** Always disable the signing key (set to null) before enabling it on another node. The 6-second pause (2 blocks) ensures no double-signing window.'''
    ),
    (
        "hive_architecture/load-balancing-api-nodes",
        r'''How do I load balance multiple Hive API nodes for a production dApp?''',
        r'''<think>
Load balancing Hive API nodes is important for production dApps. Options:
HAProxy or nginx for L7 load balancing, or application-level failover.
Key considerations: health checks (is the node synced?), sticky sessions
aren't needed since API is stateless, and handling broadcast separately
(should go to a well-connected node). I should show both nginx config
and application-level approaches.
</think>

For production dApps, load balancing across multiple Hive API nodes ensures reliability and performance. Here are two approaches:

**Nginx reverse proxy (recommended for production):**

```nginx
# /etc/nginx/conf.d/hive-api.conf

upstream hive_api {
    # Least connections distributes to least-busy node
    least_conn;

    server 10.0.1.10:8091 max_fails=3 fail_timeout=30s;
    server 10.0.1.11:8091 max_fails=3 fail_timeout=30s;
    server 10.0.1.12:8091 max_fails=3 fail_timeout=30s backup;
}

server {
    listen 443 ssl http2;
    server_name api.mydapp.com;

    ssl_certificate /etc/ssl/certs/mydapp.pem;
    ssl_certificate_key /etc/ssl/private/mydapp.key;

    location / {
        proxy_pass http://hive_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # Timeouts for slow queries (account_history can be slow)
        proxy_read_timeout 30s;
        proxy_connect_timeout 5s;

        # Rate limiting
        limit_req zone=api burst=20 nodelay;
    }

    # Separate broadcast endpoint (route to best-connected node)
    location /broadcast {
        proxy_pass http://10.0.1.10:8091;  # primary broadcast node
    }
}

limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;
```

**Application-level failover (Python):**

```python
import httpx
import time
import random
from dataclasses import dataclass, field

@dataclass
class APINode:
    url: str
    healthy: bool = True
    last_check: float = 0
    latency_ms: float = 0
    failures: int = 0

class HiveLoadBalancer:
    """Client-side load balancer with health checking."""

    def __init__(self, nodes: list[str], health_interval: float = 30):
        self.nodes = [APINode(url=url) for url in nodes]
        self.health_interval = health_interval

    def _get_healthy_nodes(self) -> list[APINode]:
        now = time.monotonic()
        healthy = []
        for node in self.nodes:
            if now - node.last_check > self.health_interval:
                self._health_check(node)
            if node.healthy:
                healthy.append(node)
        return healthy or self.nodes  # fallback to all if none healthy

    def _health_check(self, node: APINode):
        try:
            start = time.monotonic()
            resp = httpx.post(node.url, json={
                "jsonrpc": "2.0",
                "method": "condenser_api.get_dynamic_global_properties",
                "params": [], "id": 1
            }, timeout=5)
            node.latency_ms = (time.monotonic() - start) * 1000
            result = resp.json().get("result", {})
            # Check that node is synced (head block age < 15s)
            from datetime import datetime, timezone
            head_time = datetime.strptime(result["time"], "%Y-%m-%dT%H:%M:%S")
            age = (datetime.now(timezone.utc) - head_time.replace(tzinfo=timezone.utc)).total_seconds()
            node.healthy = age < 15
            node.failures = 0
        except Exception:
            node.failures += 1
            node.healthy = node.failures < 3
        node.last_check = time.monotonic()

    def call(self, method: str, params=None, retries: int = 3) -> dict:
        """Make an RPC call with automatic failover."""
        healthy = self._get_healthy_nodes()
        # Sort by latency (fastest first)
        healthy.sort(key=lambda n: n.latency_ms)

        last_error = None
        for attempt in range(retries):
            node = healthy[attempt % len(healthy)]
            try:
                resp = httpx.post(node.url, json={
                    "jsonrpc": "2.0", "method": method,
                    "params": params or [], "id": 1
                }, timeout=10)
                data = resp.json()
                if "result" in data:
                    return data["result"]
                last_error = data.get("error", {}).get("message", "unknown")
            except Exception as e:
                node.failures += 1
                last_error = str(e)

        raise RuntimeError(f"All nodes failed after {retries} attempts: {last_error}")

# Usage
lb = HiveLoadBalancer([
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://api.openhive.network",
])
props = lb.call("condenser_api.get_dynamic_global_properties")
print(f"Head block: {props['head_block_number']}")
```

**Key considerations:** Route `broadcast_transaction` calls to your best-connected node (not round-robin). Use health checks that verify sync status, not just port availability.'''
    ),
    (
        "hive_architecture/blockchain-state-snapshots",
        r'''How do Hive blockchain state snapshots work? Can I bootstrap a new node from a snapshot instead of replaying?''',
        r'''<think>
State snapshots (sometimes called "MIRA snapshots" or just block_log snapshots)
let you bootstrap a node without replaying the full chain. There are two types:
1. block_log file — the raw block data, still needs replay to build state
2. Shared memory snapshot — the pre-built state file, avoids replay entirely
Community providers offer both. The shared memory snapshot is config-specific
(must match your plugin set). This is an advanced ops topic.
</think>

Snapshots let you bootstrap a Hive node in hours instead of days. There are two types:

```
Snapshot Type      | Contains              | Replay Needed | Size    | Provider
-------------------|-----------------------|---------------|---------|----------
block_log          | Raw blocks only       | YES (1-3 days)| ~400GB  | Common
State snapshot     | shared_memory.bin     | NO            | ~60GB+  | Rare
block_log + state  | Both files            | NO            | ~460GB  | Best
```

```bash
#!/bin/bash
# Bootstrap a Hive node from community snapshots

DATA_DIR="/data/hived"
BLOCKCHAIN_DIR="$DATA_DIR/blockchain"
mkdir -p "$BLOCKCHAIN_DIR"

# ---- Option 1: Download block_log (still needs replay) ----
echo "Downloading block_log snapshot..."
# Common providers: files.privex.io, gtg.openhive.network
wget -c "https://gtg.openhive.network/get/blockchain/block_log" \
     -O "$BLOCKCHAIN_DIR/block_log"

# After download, start hived with --replay-blockchain
./hived --data-dir="$DATA_DIR" --replay-blockchain

# ---- Option 2: Download state snapshot (no replay!) ----
echo "Downloading state snapshot..."
# IMPORTANT: State snapshots are plugin-specific
# A snapshot built with account_history_api won't work if you add new plugins
wget -c "https://snapshot-provider.example/shared_memory.bin" \
     -O "$BLOCKCHAIN_DIR/shared_memory.bin"

# Also need the block_log for the node to continue syncing
wget -c "https://snapshot-provider.example/block_log" \
     -O "$BLOCKCHAIN_DIR/block_log"

# Start hived — no replay needed, it resumes from the snapshot
./hived --data-dir="$DATA_DIR"
```

```python
import os
import hashlib
import httpx
import time

def verify_snapshot(file_path: str, expected_sha256: str) -> bool:
    """Verify snapshot integrity after download."""
    sha = hashlib.sha256()
    size = os.path.getsize(file_path)
    processed = 0

    with open(file_path, "rb") as f:
        while chunk := f.read(8 * 1024 * 1024):  # 8MB chunks
            sha.update(chunk)
            processed += len(chunk)
            pct = (processed / size) * 100
            print(f"\rVerifying: {pct:.1f}%", end="", flush=True)

    actual = sha.hexdigest()
    match = actual == expected_sha256
    print(f"\nSHA256: {actual}")
    print(f"Expected: {expected_sha256}")
    print(f"Result: {'MATCH' if match else 'MISMATCH'}")
    return match

def check_snapshot_freshness(data_dir: str):
    """Check how old the snapshot is by reading the last block in block_log."""
    block_log = os.path.join(data_dir, "blockchain", "block_log")
    shm = os.path.join(data_dir, "blockchain", "shared_memory.bin")

    if os.path.exists(block_log):
        mtime = os.path.getmtime(block_log)
        age_hours = (time.time() - mtime) / 3600
        size_gb = os.path.getsize(block_log) / (1024**3)
        print(f"block_log: {size_gb:.1f} GB, modified {age_hours:.0f}h ago")

    if os.path.exists(shm):
        size_gb = os.path.getsize(shm) / (1024**3)
        print(f"shared_memory.bin: {size_gb:.1f} GB")
    else:
        print("No state snapshot — replay will be required")
```

**Important:** State snapshots must match your exact plugin configuration. If you add or remove plugins after importing a snapshot, you must replay from block_log. Always verify checksums after download.'''
    ),
    (
        "hive_architecture/rocksdb-backend-config",
        r'''How do I configure the RocksDB backend for Hive's account history plugin?''',
        r'''<think>
RocksDB is used by Hive's account_history plugin as an alternative storage
backend to the default shared memory. It stores per-account operation history
on disk instead of in the memory-mapped file, which significantly reduces
RAM requirements. Key config options: rocksdb-path, flush settings, and
tracking ranges. This is an advanced sysadmin topic for node operators.
</think>

RocksDB is the recommended backend for Hive's `account_history_api` plugin. It stores account history on disk instead of shared memory, dramatically reducing RAM requirements.

```ini
# config.ini — RocksDB account history configuration

plugin = account_history_api
plugin = account_history_rocksdb

# Path for RocksDB data files (use fast NVMe SSD)
account-history-rocksdb-path = /data/hived/rocksdb

# Track all accounts (default) or specify a range
# Tracking all accounts requires significant disk space (~200GB+)
account-history-track-account-range = ["", "z"]

# Alternatively, track specific accounts only:
# account-history-track-account-range = ["alice", "alice"]
# account-history-track-account-range = ["bob", "bob"]

# RocksDB compaction and cache tuning
# These are set via environment variables or hived options
```

```bash
#!/bin/bash
# RocksDB setup and tuning for Hive account history

ROCKSDB_PATH="/data/hived/rocksdb"
mkdir -p "$ROCKSDB_PATH"

# Ensure NVMe is mounted with optimal settings
# noatime reduces write amplification
mount -o noatime,discard /dev/nvme0n1p1 /data

# Monitor RocksDB directory size over time
watch -n 60 "du -sh $ROCKSDB_PATH"

# Check RocksDB SST file count (too many = needs compaction)
find "$ROCKSDB_PATH" -name "*.sst" | wc -l
```

```python
import os
import subprocess

def check_rocksdb_health(rocksdb_path: str = "/data/hived/rocksdb"):
    """Monitor RocksDB backend health for Hive account history."""
    if not os.path.isdir(rocksdb_path):
        print(f"RocksDB path not found: {rocksdb_path}")
        return

    # Total size
    total_size = 0
    sst_count = 0
    log_count = 0
    for entry in os.scandir(rocksdb_path):
        if entry.is_file():
            total_size += entry.stat().st_size
            if entry.name.endswith(".sst"):
                sst_count += 1
            elif entry.name.endswith(".log"):
                log_count += 1

    size_gb = total_size / (1024**3)
    print(f"RocksDB path: {rocksdb_path}")
    print(f"Total size: {size_gb:.1f} GB")
    print(f"SST files: {sst_count}")
    print(f"Log files: {log_count}")

    if sst_count > 500:
        print("WARNING: High SST file count — compaction may be needed")
    if size_gb > 300:
        print("WARNING: Large RocksDB — consider tracking fewer accounts")

    # Check disk space
    stat = os.statvfs(rocksdb_path)
    free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
    print(f"Free disk space: {free_gb:.1f} GB")
    if free_gb < 50:
        print("CRITICAL: Low disk space for RocksDB growth")

check_rocksdb_health()
```

**Key points:**
- RocksDB moves account history from RAM to disk: ~40GB less shared memory usage
- Use NVMe SSD with `noatime` mount option for best performance
- Tracking all accounts needs ~200GB+ disk; track specific accounts if space-constrained
- During replay, RocksDB indexing adds ~20-30% to replay time'''
    ),
    (
        "hive_architecture/hivemind-social-indexer",
        r'''How do I set up Hivemind, the Hive social layer indexer? What does it index and how does it relate to hived?''',
        r'''<think>
Hivemind is a separate service that indexes social data from the Hive
blockchain into PostgreSQL. It provides the social layer APIs: posts,
comments, follows, communities, trending/hot feeds, etc. It connects to
hived via its API and processes blocks, extracting social operations.
The HAF version of Hivemind is newer and more efficient. Setup requires
PostgreSQL, Python, and a synced hived node. This is advanced infrastructure.
</think>

Hivemind is Hive's social consensus layer — it indexes posts, comments, follows, communities, and feeds into PostgreSQL, powering the social features of frontends like PeakD and Ecency.

```
Architecture:
  hived (blockchain) → Hivemind (indexer) → PostgreSQL → API (condenser_api social calls)

What Hivemind indexes:
  - Posts and comments (with edits, deletions)
  - Votes and reputation
  - Follows / mutes
  - Communities (roles, moderation, settings)
  - Trending / hot / new feeds
  - Reblog (resteem) relationships
```

```bash
#!/bin/bash
# Hivemind setup (HAF-based version)

# Prerequisites
# 1. Running hived node with HAF plugin
# 2. PostgreSQL 14+ with HAF schema populated

# Clone Hivemind
git clone https://github.com/openhive-network/hivemind.git
cd hivemind

# Install dependencies
pip install -e .

# Configure database connection
export DATABASE_URL="postgresql://hivemind:password@localhost:5432/haf_block_log"
export HIVED_URL="http://localhost:8091"

# Initial sync — processes all blocks from genesis
# This takes 12-48 hours depending on hardware
hivemind sync --database-url="$DATABASE_URL" --steemd-url="$HIVED_URL"

# After sync, start the API server
hivemind server --database-url="$DATABASE_URL" --http-server-port=8080
```

```python
import httpx

class HivemindAPI:
    """Query Hivemind's social layer API."""

    def __init__(self, url: str = "https://api.hive.blog"):
        self.url = url
        self.client = httpx.Client(timeout=15)

    def _call(self, method: str, params):
        resp = self.client.post(self.url, json={
            "jsonrpc": "2.0", "method": method, "params": params, "id": 1
        })
        return resp.json().get("result")

    def get_trending_posts(self, tag: str = "", limit: int = 10):
        """Get trending posts (ranked by Hivemind's algorithm)."""
        return self._call("condenser_api.get_discussions_by_trending", [{
            "tag": tag, "limit": limit
        }])

    def get_account_posts(self, account: str, sort: str = "blog", limit: int = 20):
        """Get posts by an account."""
        return self._call("condenser_api.get_discussions_by_blog", [{
            "tag": account, "limit": limit
        }])

    def get_community_info(self, community: str):
        """Get community details (Hivemind-specific)."""
        return self._call("bridge.get_community", {
            "name": community, "observer": ""
        })

    def get_follow_count(self, account: str):
        """Get follower/following counts."""
        return self._call("condenser_api.get_follow_count", [account])

    def list_communities(self, limit: int = 20):
        """List communities ranked by subscribers."""
        return self._call("bridge.list_communities", {
            "limit": limit, "sort": "rank"
        })

# Usage
api = HivemindAPI()
trending = api.get_trending_posts(limit=5)
for post in trending or []:
    print(f"@{post['author']}/{post['permlink'][:40]} — {post['pending_payout_value']}")

communities = api.list_communities(limit=5)
for c in communities or []:
    print(f"  {c['name']}: {c['subscribers']} subscribers")
```

**Key points:** Hivemind is a separate process from hived. It requires its own PostgreSQL database and takes 12-48 hours for initial sync. The HAF-based version shares the database with other HAF apps.'''
    ),
    (
        "hive_architecture/jussi-api-gateway",
        r'''What is Jussi and how do I configure it as an API gateway for Hive?''',
        r'''<think>
Jussi is a JSON-RPC reverse proxy / API gateway for Hive. It routes
different API namespaces to different backend nodes. For example,
condenser_api calls go to hived, bridge calls go to Hivemind, and
account_history calls can go to a dedicated history node. It also provides
caching and rate limiting. It is written in Python with aiohttp.
This is an advanced infrastructure topic.
</think>

Jussi is a JSON-RPC reverse proxy that routes Hive API calls to different backend services based on the API namespace. It provides caching, routing, and rate limiting.

```
Client request → Jussi → routes to:
  condenser_api.*          → hived (main node)
  database_api.*           → hived (main node)
  account_history_api.*    → hived (history node, separate)
  bridge.*                 → Hivemind
  rc_api.*                 → hived (main node)
  market_history_api.*     → hived (main node)
```

```json
// jussi_config.json — routing configuration
{
  "limits": {
    "blacklist_accounts": [],
    "max_request_size": 65536
  },
  "upstreams": [
    {
      "name": "hived",
      "urls": [["hived", "http://hived-main:8091"]],
      "ttl": 3,
      "timeout": 15
    },
    {
      "name": "hived_history",
      "urls": [["hived_history", "http://hived-history:8091"]],
      "ttl": 3,
      "timeout": 30
    },
    {
      "name": "hivemind",
      "urls": [["hivemind", "http://hivemind:8080"]],
      "ttl": 3,
      "timeout": 15
    }
  ],
  "routes": {
    "condenser_api": "hived",
    "condenser_api.get_account_history": "hived_history",
    "database_api": "hived",
    "block_api": "hived",
    "network_broadcast_api": "hived",
    "rc_api": "hived",
    "account_history_api": "hived_history",
    "bridge": "hivemind",
    "market_history_api": "hived"
  }
}
```

```bash
#!/bin/bash
# Deploy Jussi with Docker

# Clone Jussi
git clone https://github.com/openhive-network/jussi.git
cd jussi

# Build Docker image
docker build -t jussi .

# Run with custom config
docker run -d \
  --name jussi \
  -p 9000:9000 \
  -v $(pwd)/jussi_config.json:/app/DEV_config.json \
  -e JUSSI_UPSTREAM_CONFIG_FILE=/app/DEV_config.json \
  -e JUSSI_SERVER_PORT=9000 \
  jussi

# Health check
curl -s http://localhost:9000/health
curl -s http://localhost:9000 \
  -d '{"jsonrpc":"2.0","method":"condenser_api.get_dynamic_global_properties","params":[],"id":1}' \
  | python3 -m json.tool
```

```python
import httpx

async def test_jussi_routing(jussi_url: str = "http://localhost:9000"):
    """Test that Jussi routes requests to correct backends."""
    routes_to_test = [
        ("condenser_api.get_dynamic_global_properties", [], "hived"),
        ("account_history_api.get_account_history",
         {"account": "hiveio", "start": -1, "limit": 1}, "hived_history"),
        ("bridge.get_community", {"name": "hive-dev", "observer": ""}, "hivemind"),
        ("rc_api.find_rc_accounts", {"accounts": ["hiveio"]}, "hived"),
    ]

    async with httpx.AsyncClient(timeout=15) as client:
        for method, params, expected_backend in routes_to_test:
            try:
                resp = await client.post(jussi_url, json={
                    "jsonrpc": "2.0", "method": method, "params": params, "id": 1
                })
                data = resp.json()
                status = "OK" if "result" in data else "FAIL"
                print(f"[{status}] {method:50s} → {expected_backend}")
            except Exception as e:
                print(f"[ERR] {method:50s} → {e}")
```

**Why use Jussi:** It lets you run specialized backend nodes (e.g., a lightweight main node + a heavy history node) and present a single unified API endpoint to clients.'''
    ),
    (
        "hive_architecture/account-history-queries",
        r'''How do I efficiently query account history on Hive? Show me how to paginate through all operations for an account.''',
        r'''<think>
Account history queries use the account_history_api plugin. The key method
is get_account_history which returns operations in reverse chronological
order. Pagination uses sequence numbers, not page numbers. The user needs
to understand: start=-1 means latest, limit is max 1000, and you paginate
backwards by using the lowest sequence number from the previous batch.
This is intermediate-level but commonly needed for dApp development.
</think>

Account history on Hive uses sequence-based pagination (not page numbers). Here is how to efficiently retrieve and paginate through all operations:

```python
import httpx
from typing import Iterator, Optional

class AccountHistoryReader:
    """Efficient paginated account history reader for Hive."""

    def __init__(self, node: str = "https://api.hive.blog"):
        self.node = node
        self.client = httpx.Client(timeout=15)

    def _rpc(self, method: str, params: dict) -> dict:
        resp = self.client.post(self.node, json={
            "jsonrpc": "2.0", "method": method, "params": params, "id": 1
        })
        return resp.json()["result"]

    def get_history_page(
        self, account: str, start: int = -1, limit: int = 1000,
        op_filter: Optional[int] = None
    ) -> list[tuple]:
        """Get one page of account history.

        Args:
            account: Hive username
            start: Sequence number to start from (-1 = latest)
            limit: Max operations to return (max 1000)
            op_filter: Bitmask to filter operation types (None = all)
        """
        params = {"account": account, "start": start, "limit": limit}
        if op_filter is not None:
            params["operation_filter_low"] = op_filter
        result = self._rpc("account_history_api.get_account_history", params)
        return result.get("history", [])

    def iter_all_history(
        self, account: str, op_filter: Optional[int] = None
    ) -> Iterator[dict]:
        """Iterate through ALL account history, newest to oldest."""
        start = -1
        batch_size = 1000

        while True:
            history = self.get_history_page(account, start, batch_size, op_filter)
            if not history:
                break

            for seq_num, entry in reversed(history):
                yield {
                    "sequence": seq_num,
                    "block": entry["block"],
                    "timestamp": entry["timestamp"],
                    "op_type": entry["op"]["type"],
                    "op_value": entry["op"]["value"],
                    "trx_id": entry["trx_id"],
                }

            # Paginate backwards: next batch starts before the oldest in this batch
            oldest_seq = history[0][0]
            if oldest_seq <= 0:
                break
            start = oldest_seq - 1

    def get_transfers(self, account: str, limit: int = 50) -> list[dict]:
        """Get recent transfer operations for an account."""
        # transfer = op type 2, bitmask = 1 << 2 = 4
        TRANSFER_FILTER = 0x04
        transfers = []
        for entry in self.iter_all_history(account, op_filter=TRANSFER_FILTER):
            transfers.append(entry)
            if len(transfers) >= limit:
                break
        return transfers

# Usage
reader = AccountHistoryReader()

# Get last 10 transfers for an account
transfers = reader.get_transfers("hiveio", limit=10)
for t in transfers:
    val = t["op_value"]
    direction = "SENT" if val.get("from") == "hiveio" else "RECEIVED"
    print(f"[{direction}] {val.get('amount', {}).get('amount', '?')} "
          f"{val.get('amount', {}).get('nai', '?')} "
          f"block {t['block']}")

# Iterate all history (careful — can be millions of entries for active accounts)
count = 0
for entry in reader.iter_all_history("hiveio"):
    count += 1
    if count >= 100:
        break
print(f"\nProcessed {count} operations")
```

**Key details:**
- `start=-1` means latest operation; paginate backwards by decrementing
- Max `limit` per request is 1000
- `operation_filter_low` is a bitmask: `1 << op_type_id` (e.g., `1 << 2` for transfers)
- Very active accounts (exchanges) can have millions of history entries — always paginate'''
    ),
    (
        "hive_architecture/virtual-operations-explained",
        r'''What are virtual operations on Hive? How are they different from regular operations and how do I track them?''',
        r'''<think>
Virtual operations are generated by the blockchain consensus code, not
submitted by users. They represent side effects: rewards, interest payments,
fills on the DEX, delegation returns, etc. They appear in account history
but cannot be broadcast. They have their own op type IDs (typically 50+).
Key virtual ops: author_reward, curation_reward, producer_reward,
fill_convert_request, fill_order. You query them via account_history_api
or via HAF. Important for accounting and analytics.
</think>

Virtual operations are chain-generated events that happen as side effects of consensus rules. They are never broadcast by users but appear in account history and block data.

```
Regular Operations (user-submitted):
  transfer, vote, comment, custom_json, witness_update, ...
  → Created and signed by users
  → Included in transactions within blocks

Virtual Operations (chain-generated):
  author_reward, curation_reward, producer_reward, fill_order, ...
  → Generated by consensus code during block processing
  → No transaction, no signature
  → Appear at the END of block processing
```

```python
import httpx
from typing import Optional
from datetime import datetime

# Virtual operation type IDs (approximate — check chain source for exact)
VIRTUAL_OPS = {
    52: "fill_convert_request",       # HBD→HIVE conversion completed
    53: "author_reward",              # post/comment author payout
    54: "curation_reward",            # voter reward (for upvoting)
    55: "comment_reward",             # total reward for a post
    56: "fill_vesting_withdraw",      # power down weekly withdrawal
    57: "fill_order",                 # internal DEX order matched
    59: "return_vesting_delegation",  # delegation revoked, HP returned
    62: "producer_reward",            # witness block production reward
    63: "clear_null_account_balance", # @null burns
    72: "proposal_pay",              # DHF proposal payout
    73: "update_proposal_votes",     # governance vote result
    78: "fill_recurrent_transfer",   # recurring payment executed
    80: "collateralized_convert",    # instant HBD→HIVE conversion
}

class VirtualOpsTracker:
    """Track and analyze virtual operations on Hive."""

    def __init__(self, node: str = "https://api.hive.blog"):
        self.node = node
        self.client = httpx.Client(timeout=15)

    def _rpc(self, method: str, params: dict):
        resp = self.client.post(self.node, json={
            "jsonrpc": "2.0", "method": method, "params": params, "id": 1
        })
        return resp.json().get("result")

    def get_virtual_ops_in_block(self, block_num: int) -> list[dict]:
        """Get all virtual operations generated in a specific block."""
        result = self._rpc("account_history_api.enum_virtual_ops", {
            "block_range_begin": block_num,
            "block_range_end": block_num + 1,
        })
        return result.get("ops", [])

    def get_account_rewards(self, account: str, limit: int = 50) -> dict:
        """Get recent author and curation rewards for an account."""
        # Author reward bitmask: 1 << 53
        # Curation reward bitmask: 1 << 54
        reward_filter = (1 << 53) | (1 << 54)

        history = self._rpc("account_history_api.get_account_history", {
            "account": account,
            "start": -1,
            "limit": min(limit, 1000),
            "operation_filter_low": reward_filter,
        })

        rewards = {"author": [], "curation": []}
        for seq, entry in history.get("history", []):
            op = entry["op"]
            if op["type"] == "author_reward_operation":
                val = op["value"]
                rewards["author"].append({
                    "permlink": val["permlink"],
                    "hbd": val["hbd_payout"],
                    "hive": val["hive_payout"],
                    "vests": val["vesting_payout"],
                    "block": entry["block"],
                })
            elif op["type"] == "curation_reward_operation":
                val = op["value"]
                rewards["curation"].append({
                    "author": val["comment_author"],
                    "permlink": val["comment_permlink"],
                    "reward": val["reward"],
                    "block": entry["block"],
                })
        return rewards

# Usage
tracker = VirtualOpsTracker()

# Check virtual ops in a recent block
vops = tracker.get_virtual_ops_in_block(80000000)
print(f"Virtual ops in block 80000000: {len(vops)}")
for op in vops[:5]:
    print(f"  {op['op']['type']}: {op['op']['value']}")

# Get account rewards
rewards = tracker.get_account_rewards("hiveio")
print(f"\nAuthor rewards: {len(rewards['author'])}")
print(f"Curation rewards: {len(rewards['curation'])}")
```

**Why virtual ops matter:** They are essential for accounting (tracking rewards, conversions, DEX fills). Any wallet, tax tool, or analytics platform must process virtual operations alongside regular ones to get a complete picture of account activity.'''
    ),
    (
        "hive_architecture/reversible-blocks-handling",
        r'''How does Hive handle reversible blocks? What should my application do about potential micro-forks?''',
        r'''<think>
Reversible blocks are blocks between the head block and the last irreversible
block (LIB). They can be undone if a micro-fork occurs (e.g., a witness
produces on a different fork). Applications must handle this: either wait
for irreversibility before acting, or implement rollback logic. HAF handles
this automatically with its context system. For custom apps, you track
the LIB and only treat data as final once the block number is <= LIB.
Micro-forks are rare (a few per day at most) and usually only affect
the most recent 1-2 blocks.
</think>

Blocks between the head and the Last Irreversible Block (LIB) are reversible — they can be undone by micro-forks. Applications must handle this correctly.

```
Block timeline:
  [...] [LIB] [reversible] [reversible] [reversible] [HEAD]
         ↑                                              ↑
    Permanent/safe                              May be reverted
    (~15 blocks behind head)                    (0-15 blocks)

Micro-fork scenario:
  Witness A produces block 100 → some nodes see it
  Witness B produces block 100 → other nodes see it
  Network resolves: longest chain wins, shorter fork is discarded
  Applications on the losing fork must roll back block 100
```

```python
from dataclasses import dataclass, field
from typing import Optional, Callable
import httpx
import time

@dataclass
class ProcessedBlock:
    block_num: int
    block_id: str
    transactions: list
    is_irreversible: bool = False

class ForkAwareProcessor:
    """Process Hive blocks with micro-fork rollback support."""

    def __init__(self, node: str = "https://api.hive.blog"):
        self.node = node
        self.client = httpx.Client(timeout=15)
        self.reversible_blocks: dict[int, ProcessedBlock] = {}
        self.last_processed: int = 0
        self.on_apply: Optional[Callable] = None     # called when block is applied
        self.on_rollback: Optional[Callable] = None   # called on fork rollback

    def _rpc(self, method: str, params):
        resp = self.client.post(self.node, json={
            "jsonrpc": "2.0", "method": method, "params": params, "id": 1
        })
        return resp.json()["result"]

    def get_chain_state(self) -> tuple[int, int]:
        """Return (head_block_num, last_irreversible_block_num)."""
        props = self._rpc("condenser_api.get_dynamic_global_properties", [])
        return props["head_block_number"], props["last_irreversible_block_num"]

    def get_block(self, block_num: int) -> dict:
        result = self._rpc("block_api.get_block", {"block_num": block_num})
        return result["block"]

    def apply_block(self, block_num: int):
        """Apply a new block (may be reversible)."""
        block = self.get_block(block_num)
        processed = ProcessedBlock(
            block_num=block_num,
            block_id=block["block_id"],
            transactions=block.get("transactions", []),
        )
        self.reversible_blocks[block_num] = processed
        if self.on_apply:
            self.on_apply(processed)
        self.last_processed = block_num

    def check_for_fork(self, block_num: int) -> bool:
        """Check if a block we processed has been replaced (forked)."""
        if block_num not in self.reversible_blocks:
            return False
        current_block = self.get_block(block_num)
        stored = self.reversible_blocks[block_num]
        return current_block["block_id"] != stored.block_id

    def handle_fork(self, fork_block: int):
        """Roll back all blocks from fork_block to head."""
        blocks_to_rollback = sorted(
            [b for b in self.reversible_blocks if b >= fork_block],
            reverse=True  # rollback newest first
        )
        for block_num in blocks_to_rollback:
            block = self.reversible_blocks.pop(block_num)
            if self.on_rollback:
                self.on_rollback(block)
            print(f"[ROLLBACK] Block {block_num}")
        self.last_processed = fork_block - 1

    def promote_irreversible(self, lib: int):
        """Mark blocks at or below LIB as irreversible (safe to finalize)."""
        to_promote = [b for b in self.reversible_blocks if b <= lib]
        for block_num in to_promote:
            block = self.reversible_blocks.pop(block_num)
            block.is_irreversible = True
            # At this point, the data is PERMANENT — safe to commit to your DB

    def run(self, start_block: Optional[int] = None):
        """Main processing loop with fork awareness."""
        if start_block:
            self.last_processed = start_block - 1

        while True:
            head, lib = self.get_chain_state()
            self.promote_irreversible(lib)

            # Check for forks in our reversible window
            for block_num in sorted(self.reversible_blocks.keys()):
                if self.check_for_fork(block_num):
                    print(f"[FORK DETECTED] at block {block_num}")
                    self.handle_fork(block_num)
                    break

            # Process new blocks
            while self.last_processed < head:
                next_block = self.last_processed + 1
                self.apply_block(next_block)
                print(f"[APPLIED] Block {next_block} "
                      f"(reversible, LIB={lib}, gap={next_block - lib})")

            time.sleep(1)

# Usage
processor = ForkAwareProcessor()
processor.on_apply = lambda b: print(f"  Processing {len(b.transactions)} txs")
processor.on_rollback = lambda b: print(f"  Undoing {len(b.transactions)} txs")
# processor.run(start_block=80000000)
```

**Best practices:**
- For financial operations (exchanges, payments): always wait for irreversibility (~45s)
- For social features (displaying posts): show reversible data but mark it as unconfirmed
- HAF handles all this automatically — prefer HAF over manual fork handling'''
    ),
]
