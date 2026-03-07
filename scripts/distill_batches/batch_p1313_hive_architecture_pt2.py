"""Hive architecture training pairs (part 2a): witness ops, indexing, streaming."""

PAIRS = [
    (
        "hive_architecture/witness-price-feed",
        r'''How do I publish a price feed as a Hive witness using Python?''',
        r'''<think>
Witnesses must publish HBD/HIVE price feeds regularly so the blockchain can calculate conversions.
The operation is `feed_publish` with an exchange_rate containing base (HBD) and quote (HIVE).
I need to fetch a real market price, then broadcast the op signed with the witness active key.
Feeds should update every hour or when price moves >3% to avoid spamming.
Beem library provides the easiest interface for this.
</think>

```python
from beem import Hive
from beem.witness import Witness
import requests, time

WITNESS = "yourwitness"
WIF = "5K..."  # active key
INTERVAL = 3600  # seconds

def get_hive_price():
    r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                     params={"ids": "hive", "vs_currencies": "usd"}).json()
    return r["hive"]["usd"]

def publish_feed(hive, price):
    # base = 1 HBD worth of HIVE
    exchange_rate = {"base": "1.000 HBD", "quote": f"{1/price:.3f} HIVE"}
    hive.witness_feed_publish(exchange_rate, account=WITNESS)
    print(f"Published feed: 1 HBD = {1/price:.3f} HIVE (${price})")

hive = Hive(keys=[WIF], node=["https://api.hive.blog"])
last_price = 0
while True:
    price = get_hive_price()
    if abs(price - last_price) / max(last_price, 0.001) > 0.03 or last_price == 0:
        publish_feed(hive, price)
        last_price = price
    time.sleep(INTERVAL)
```'''
    ),
    (
        "hive_architecture/witness-monitoring-dashboard",
        r'''Build a custom witness monitoring dashboard that tracks missed blocks and feed age.''',
        r'''<think>
A witness monitor needs to poll the blockchain for the witness object, track total_missed over time,
check last_hbd_exchange_update age, and alert if feeds go stale (>12h) or blocks are missed.
Flask + a background thread works well for a lightweight dashboard.
Store historical data in SQLite for trend display.
The key API call is condenser_api.get_witness_by_account.
</think>

```python
from flask import Flask, jsonify
import requests, threading, time, sqlite3

app = Flask(__name__)
WITNESS = "yourwitness"
NODE = "https://api.hive.blog"
DB = "witness_monitor.db"

def init_db():
    with sqlite3.connect(DB) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS stats (
            ts INTEGER, missed INTEGER, feed_age_h REAL)""")

def rpc(method, params):
    r = requests.post(NODE, json={"jsonrpc":"2.0","method":method,"params":params,"id":1})
    return r.json()["result"]

def poll():
    while True:
        w = rpc("condenser_api.get_witness_by_account", [WITNESS])
        missed = w["total_missed"]
        from datetime import datetime
        feed_ts = datetime.strptime(w["last_hbd_exchange_update"], "%Y-%m-%dT%H:%M:%S")
        age_h = (datetime.utcnow() - feed_ts).total_seconds() / 3600
        with sqlite3.connect(DB) as conn:
            conn.execute("INSERT INTO stats VALUES (?,?,?)",
                         (int(time.time()), missed, round(age_h, 2)))
        if age_h > 12:
            print(f"ALERT: Feed stale ({age_h:.1f}h)")
        time.sleep(300)

@app.route("/api/status")
def status():
    with sqlite3.connect(DB) as conn:
        row = conn.execute("SELECT * FROM stats ORDER BY ts DESC LIMIT 1").fetchone()
    return jsonify({"ts": row[0], "missed": row[1], "feed_age_h": row[2]})

init_db()
threading.Thread(target=poll, daemon=True).start()
app.run(port=5050)
```'''
    ),
    (
        "hive_architecture/block-explorer-backend",
        r'''How would I build a simple block explorer backend for Hive in Python?''',
        r'''<think>
A block explorer backend needs endpoints for blocks, transactions, and accounts.
It should fetch from a Hive API node, cache results, and serve via REST.
The key RPC calls are block_api.get_block, condenser_api.get_accounts,
and account_history_api.get_account_history.
FastAPI is a good fit for async performance. Redis caching prevents hammering the node.
</think>

```python
from fastapi import FastAPI
from functools import lru_cache
import httpx

app = FastAPI()
NODE = "https://api.hive.blog"

async def rpc(method, params):
    async with httpx.AsyncClient() as c:
        r = await c.post(NODE, json={"jsonrpc":"2.0","method":method,"params":params,"id":1})
        return r.json()["result"]

@app.get("/block/{num}")
async def get_block(num: int):
    res = await rpc("block_api.get_block", {"block_num": num})
    b = res["block"]
    return {"num": num, "witness": b["witness"], "tx_count": len(b["transactions"]),
            "timestamp": b["timestamp"], "transactions": b["transactions"]}

@app.get("/account/{name}")
async def get_account(name: str):
    res = await rpc("condenser_api.get_accounts", [[name]])
    if not res:
        return {"error": "not found"}
    a = res[0]
    return {k: a[k] for k in ["name","balance","hbd_balance","vesting_shares",
                                "post_count","created"]}

@app.get("/account/{name}/history")
async def get_history(name: str, limit: int = 20):
    res = await rpc("account_history_api.get_account_history",
                    {"account": name, "start": -1, "limit": min(limit, 100)})
    return [{"index": h[0], "op": h[1]["op"]} for h in res.get("history", [])]
```'''
    ),
    (
        "hive_architecture/haf-transaction-indexing",
        r'''How does HAF (Hive Application Framework) work for transaction indexing, and how do I query it?''',
        r'''<think>
HAF replays the blockchain into PostgreSQL, giving apps SQL access to all operations.
It stores operations in hive.operations table with block_num, trx_in_block, op_pos, and body (jsonb).
Apps register as HAF apps and process blocks via hive.app_next_block().
This is far more efficient than polling the API for historical data.
Custom indexes on jsonb fields enable fast lookups by author, permlink, etc.
The key advantage is that HAF handles fork resolution automatically.
</think>

```sql
-- HAF stores all ops in hive.operations with jsonb body
-- Register your app context:
SELECT hive.app_create_context('my_indexer');

-- Process blocks in your app loop:
SELECT * FROM hive.app_next_block('my_indexer');

-- Query transfers to a specific account:
SELECT block_num, body
FROM hive.operations
WHERE op_type_id = 2  -- transfer_operation
  AND body->>'to' = 'someaccount'
ORDER BY block_num DESC
LIMIT 50;

-- Build a custom index for fast author lookups:
CREATE INDEX idx_comment_author ON hive.operations ((body->>'author'))
WHERE op_type_id = 1;  -- comment_operation

-- Python HAF app skeleton:
```

```python
import psycopg2

conn = psycopg2.connect("dbname=haf_block_log user=haf_admin")
cur = conn.cursor()

# Get latest indexed block
cur.execute("SELECT hive.app_get_current_block_num('my_indexer')")
current = cur.fetchone()[0]

# Process next block
cur.execute("SELECT * FROM hive.app_next_block('my_indexer')")
block = cur.fetchone()
if block:
    block_num = block[0]
    cur.execute("""SELECT body FROM hive.operations
                   WHERE block_num = %s AND op_type_id = 2""", (block_num,))
    for row in cur.fetchall():
        print(f"Transfer: {row[0]}")
    conn.commit()
```'''
    ),
    (
        "hive_architecture/custom-operation-parsing",
        r'''How do I parse and index custom_json operations from Hive for a specific app (e.g., Splinterlands)?''',
        r'''<think>
Custom JSON ops carry app-specific data with an `id` field identifying the dApp.
For Splinterlands the id is "sm_*" prefixed. The json field contains the payload as a string.
To index them, stream blocks and filter by op type and id prefix.
The tricky part is that json can be either a string or already-parsed object depending on the node.
Required_auths vs required_posting_auths tells you the auth level used.
</think>

```python
from beem.blockchain import Blockchain
import json

TARGET_ID = "sm_"  # Splinterlands prefix

def parse_custom_json(op):
    data = op.get("json", "{}")
    if isinstance(data, str):
        data = json.loads(data)
    return {
        "id": op["id"],
        "required_auths": op.get("required_auths", []),
        "required_posting_auths": op.get("required_posting_auths", []),
        "payload": data,
    }

bc = Blockchain(node="https://api.hive.blog")
stream = bc.stream(opNames=["custom_json"], raw_ops=False)

for op in stream:
    if not op["id"].startswith(TARGET_ID):
        continue
    parsed = parse_custom_json(op)
    user = (parsed["required_posting_auths"] or parsed["required_auths"])[0]
    action = parsed["id"].replace("sm_", "")
    print(f"[{op['block_num']}] {user} -> {action}: {parsed['payload']}")
```'''
    ),
    (
        "hive_architecture/streaming-api-realtime",
        r'''How do I build a streaming API that pushes real-time Hive block data to WebSocket clients?''',
        r'''<think>
A streaming API for Hive needs to tail new blocks and fan out to connected WebSocket clients.
Use beem's Blockchain.stream() or poll block_api in a loop, then broadcast via websockets library.
Clients should be able to subscribe to specific operation types to reduce noise.
An asyncio event loop manages both the block polling and client connections.
Keep a small buffer of recent blocks for clients that connect mid-stream.
</think>

```python
import asyncio, json, websockets
from beem.blockchain import Blockchain

clients = {}  # ws -> set of subscribed op types

async def register(ws):
    clients[ws] = set()  # empty = all ops
    try:
        async for msg in ws:
            data = json.loads(msg)
            if data.get("action") == "subscribe":
                clients[ws] = set(data.get("ops", []))
    finally:
        del clients[ws]

async def broadcast(block_data):
    for ws, ops_filter in list(clients.items()):
        if ops_filter:
            filtered = [t for t in block_data["txs"]
                        if any(op[0] in ops_filter for op in t["operations"])]
            if not filtered:
                continue
            block_data = {**block_data, "txs": filtered}
        try:
            await ws.send(json.dumps(block_data))
        except:
            del clients[ws]

async def poll_blocks():
    bc = Blockchain(node="https://api.hive.blog")
    for block in bc.blocks():
        data = {"num": block.block_num, "witness": block["witness"],
                "txs": block["transactions"]}
        await broadcast(data)
        await asyncio.sleep(0)

async def main():
    async with websockets.serve(register, "0.0.0.0", 8765):
        await poll_blocks()

asyncio.run(main())
```'''
    ),
    (
        "hive_architecture/node-performance-tuning",
        r'''What are the key performance tuning parameters for a Hive node (hived)?''',
        r'''<think>
Hive node performance depends on shared memory size, thread count, and plugin selection.
The shared-file-size must accommodate the entire state — too small causes crashes.
Plugins should be minimal for witnesses (only witness + p2p + minimal API).
Full API nodes need more RAM and benefit from read-ahead and SSD storage.
The webserver-thread-pool-size and p2p thread settings directly affect throughput.
Block log compression and pruning reduce disk usage significantly.
</think>

```ini
# config.ini key performance settings for hived

# Shared memory — witness needs ~24GB, full node ~64GB
shared-file-size = 24G
shared-file-dir = /dev/shm  # tmpfs for speed

# Thread tuning
webserver-thread-pool-size = 8   # API handler threads
p2p-max-connections = 50

# Witness: minimal plugins
plugin = witness p2p webserver condenser_api

# Full API: add heavy plugins only if needed
# plugin = account_history_api reputation_api market_history_api

# Block log management
block-log-split = -1         # auto-split at 2GB boundaries
enable-block-log-compression = true
block-log-compression-level = 15

# Flush writes less often (witness performance)
flush-state-interval = 1000

# P2P tuning
p2p-seed-node = api.hive.blog:2001
p2p-seed-node = seed.openhive.network:2001
```

```bash
# Monitor with:
curl -s http://127.0.0.1:8091 -d '{"jsonrpc":"2.0","method":"condenser_api.get_dynamic_global_properties","id":1}' | jq '.result.head_block_number'
```'''
    ),
    (
        "hive_architecture/postgres-data-export",
        r'''How can I export Hive blockchain data to PostgreSQL for analytics?''',
        r'''<think>
There are two approaches: use HAF (built-in) or build a custom streamer.
For custom export, stream blocks and insert ops into normalized tables.
Key tables: blocks, transactions, transfers, comments, votes.
Batch inserts with executemany and commit every N blocks for performance.
Use ON CONFLICT to handle re-processing after restarts.
A cursor table tracks the last processed block for resumability.
</think>

```python
import psycopg2, json
from beem.blockchain import Blockchain

conn = psycopg2.connect("dbname=hive_analytics user=postgres")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS transfers (
    block_num INT, trx_id TEXT, sender TEXT, receiver TEXT,
    amount TEXT, memo TEXT, ts TIMESTAMP,
    PRIMARY KEY (trx_id, sender, receiver));
CREATE TABLE IF NOT EXISTS cursor (id INT PRIMARY KEY, block_num INT);
INSERT INTO cursor VALUES (1, 0) ON CONFLICT DO NOTHING;
""")
conn.commit()

cur.execute("SELECT block_num FROM cursor WHERE id=1")
start = cur.fetchone()[0]

bc = Blockchain(node="https://api.hive.blog")
batch = []
for op in bc.stream(opNames=["transfer"], start=start, raw_ops=False):
    batch.append((op["block_num"], op["trx_id"], op["from"], op["to"],
                  op["amount"], op.get("memo",""), op["timestamp"]))
    if len(batch) >= 100:
        cur.executemany("""INSERT INTO transfers VALUES (%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT DO NOTHING""", batch)
        cur.execute("UPDATE cursor SET block_num=%s WHERE id=1", (batch[-1][0],))
        conn.commit()
        print(f"Indexed to block {batch[-1][0]}")
        batch = []
```'''
    ),
    (
        "hive_architecture/api-rate-limiting-nginx",
        r'''How do I set up Nginx as a reverse proxy for a Hive API node with rate limiting and caching?''',
        r'''<think>
Nginx in front of hived protects against abuse and caches frequent read calls.
Rate limiting uses limit_req_zone keyed on client IP.
Caching works well for read-only RPC methods like get_dynamic_global_properties.
POST body inspection is tricky — use lua or map to split cacheable vs non-cacheable.
A proxy_cache_key based on request body hash enables RPC-level caching.
SSL termination at Nginx offloads crypto from hived.
</think>

```nginx
# /etc/nginx/sites-enabled/hive-api.conf

limit_req_zone $binary_remote_addr zone=hiveapi:10m rate=10r/s;
proxy_cache_path /var/cache/nginx/hive levels=1:2 keys_zone=hivecache:50m
                 inactive=10s max_size=1g;

upstream hived {
    server 127.0.0.1:8091;
    keepalive 16;
}

server {
    listen 443 ssl http2;
    server_name api.mynode.com;
    ssl_certificate /etc/letsencrypt/live/api.mynode.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.mynode.com/privkey.pem;

    location / {
        limit_req zone=hiveapi burst=20 nodelay;

        # Cache GET-like RPC calls for 3 seconds
        proxy_cache hivecache;
        proxy_cache_key "$request_body";
        proxy_cache_valid 200 3s;
        proxy_cache_methods POST;  # RPC is POST-based

        proxy_pass http://hived;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Connection "";

        # Block broadcast (write) abuse
        if ($request_body ~* "broadcast_transaction") {
            set $limit_tag "broadcast";
        }
    }
}
```'''
    ),
    (
        "hive_architecture/witness-signing-key-rotation",
        r'''What is the procedure to safely rotate a Hive witness signing key without missing blocks?''',
        r'''<think>
Signing key rotation requires generating a new key pair, updating the witness on-chain,
then updating the node config — in that order to avoid missed blocks.
The witness_update operation sets the new signing key on the blockchain.
The node must be updated with the new private key in config.ini and restarted.
Timing is critical: update chain first, then node, within the same round.
Always test the new key on a non-producing node first if possible.
</think>

```python
from beem import Hive
from beem.account import Account
from beemgraphenebase.account import PrivateKey

WITNESS = "yourwitness"
ACTIVE_WIF = "5K..."  # active key to sign the update

# Step 1: Generate new signing key pair
new_private = PrivateKey()  # random new key
new_public = str(new_private.pubkey)
print(f"New private: {new_private}")
print(f"New public:  {new_public}")

# Step 2: Broadcast witness_update with new signing key
hive = Hive(keys=[ACTIVE_WIF], node=["https://api.hive.blog"])
hive.witness_update(
    signing_key=new_public,
    url="https://your.witness.url",
    props={"account_creation_fee": "3.000 HIVE", "maximum_block_size": 65536,
           "hbd_interest_rate": 2000},
    account=WITNESS
)
print("On-chain update broadcast. Waiting for confirmation...")

# Step 3: Update config.ini on the node (do this quickly)
# witness = "yourwitness"
# private-key = <new_private_key_here>
# Then: systemctl restart hived

# Step 4: Verify
import time; time.sleep(6)  # wait 2 blocks
from beem.witness import Witness
w = Witness(WITNESS, blockchain_instance=hive)
assert w["signing_key"] == new_public, "Key mismatch!"
print("Key rotation confirmed.")
```'''
    ),
    (
        "hive_architecture/multi-node-cluster",
        r'''How would I architect a multi-node Hive cluster with load balancing and failover for a production API service?''',
        r'''<think>
A production Hive API cluster needs multiple hived instances behind a load balancer.
HAProxy or Nginx can health-check nodes and route traffic to healthy ones.
Separate witness nodes from API nodes — witness should have minimal plugins.
Use at least 2 full API nodes with staggered replay for zero-downtime upgrades.
Health checks should verify head block recency (not just HTTP 200).
Geographic distribution helps with latency and disaster recovery.
</think>

```yaml
# docker-compose.yml — multi-node Hive cluster
services:
  hived-api-1:
    image: hiveio/hive:latest
    volumes: [./config-api.ini:/etc/hived/config.ini, ./blockchain:/blockchain]
    ports: ["8091:8091"]
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:8091/health"]
      interval: 10s

  hived-api-2:
    image: hiveio/hive:latest
    volumes: [./config-api.ini:/etc/hived/config.ini, ./blockchain2:/blockchain]
    ports: ["8092:8091"]
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:8091/health"]
      interval: 10s

  haproxy:
    image: haproxy:latest
    ports: ["443:443"]
    volumes: [./haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg]
```

```
# haproxy.cfg
backend hive_api
    option httpchk POST / HTTP/1.1\r\nContent-Type:\ application/json
    http-check send meth POST body "{\"jsonrpc\":\"2.0\",\"method\":\"condenser_api.get_dynamic_global_properties\",\"id\":1}"
    http-check expect rstring head_block_number
    server api1 hived-api-1:8091 check inter 5s fall 3
    server api2 hived-api-2:8091 check inter 5s fall 3 backup
```'''
    ),
    (
        "hive_architecture/disaster-recovery-witness",
        r'''What is a disaster recovery plan for a Hive witness node? How do I fail over quickly?''',
        r'''<think>
Witness DR requires a hot standby node that is fully synced but NOT producing blocks.
The standby has the same signing key in config but witness name commented out.
Failover means enabling the witness name on standby and disabling on primary.
Block log and shared memory snapshots speed up recovery of a dead node.
Key metric: time to failover must be under 63 seconds (one round) to avoid missing a block.
Automated monitoring with instant failover scripts is essential for top-20 witnesses.
</think>

```python
#!/usr/bin/env python3
"""Witness failover script — switches production to standby node."""
import subprocess, requests, sys, time

PRIMARY = "primary.witness.com"
STANDBY = "standby.witness.com"
CHECK_URL = "http://{}:8091"

def node_healthy(host):
    try:
        r = requests.post(CHECK_URL.format(host), timeout=3, json={
            "jsonrpc":"2.0","method":"condenser_api.get_dynamic_global_properties","id":1})
        head = r.json()["result"]["head_block_number"]
        return head > 0
    except:
        return False

def ssh_cmd(host, cmd):
    subprocess.run(["ssh", f"witness@{host}", cmd], check=True, timeout=10)

def failover():
    print("PRIMARY DOWN — initiating failover")
    # Enable witness on standby (uncomment witness line, restart)
    ssh_cmd(STANDBY, "sed -i 's/# witness/witness/' /etc/hived/config.ini")
    ssh_cmd(STANDBY, "systemctl restart hived")
    time.sleep(5)
    if node_healthy(STANDBY):
        print("STANDBY is now producing. Failover complete.")
    else:
        print("CRITICAL: Standby also unhealthy!", file=sys.stderr)
        sys.exit(1)

# Monitor loop
while True:
    if not node_healthy(PRIMARY):
        time.sleep(6)  # double-check after 2 blocks
        if not node_healthy(PRIMARY):
            failover()
            break
    time.sleep(3)
```'''
    ),
    (
        "hive_architecture/custom-condenser-plugin",
        r'''How would I create a custom API plugin for hived that exposes a new condenser-style endpoint?''',
        r'''<think>
Hived plugins are C++ shared libraries loaded at startup via config.ini.
A custom API plugin subclasses appbase::plugin, registers API methods via DEFINE_API.
The plugin lifecycle is: plugin_initialize -> plugin_startup -> plugin_shutdown.
Each API method takes a JSON params object and returns a JSON result.
Building requires the hived source tree and appbase framework.
This is expert-level — most teams use HAF or middleware instead.
</think>

```cpp
// plugins/custom_analytics/custom_analytics_plugin.hpp
#include <hive/app/plugin.hpp>
#include <hive/chain/database.hpp>

namespace hive { namespace plugins { namespace custom_analytics {

class custom_analytics_plugin : public appbase::plugin<custom_analytics_plugin> {
public:
    APPBASE_PLUGIN_REQUIRES((chain::chain_plugin)(webserver::webserver_plugin))

    static const std::string& name() {
        static std::string n = "custom_analytics_api"; return n;
    }

    void plugin_initialize(const boost::program_options::variables_map& opts) override;
    void plugin_startup() override;
    void plugin_shutdown() override;

    // Custom endpoint: get transfer volume for an account
    DECLARE_API(
        (get_transfer_volume)
    )
};

struct get_transfer_volume_args { std::string account; uint32_t days; };
struct get_transfer_volume_return { std::string total_sent; std::string total_received; };

}}} // namespace
```

```ini
# config.ini — load the custom plugin
plugin = custom_analytics_api
```

```bash
# Query the custom endpoint
curl -s http://localhost:8091 -d '{
  "jsonrpc":"2.0",
  "method":"custom_analytics_api.get_transfer_volume",
  "params":{"account":"alice","days":30},"id":1}'
```'''
    ),
]
