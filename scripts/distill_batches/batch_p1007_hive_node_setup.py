"""Hive blockchain training pairs: node setup and infrastructure."""

PAIRS = [
    (
        "hive/api-node-configuration",
        r'''How do I set up and configure a Hive API node for production use? Show the config.ini and Docker setup.''',
        r'''<think>
Setting up a Hive API node requires:
1. Sufficient hardware (16+ GB RAM for API node, 64+ GB for full node)
2. Proper plugin configuration for the APIs you need
3. Shared memory file configuration
4. P2P seed nodes for syncing

API nodes serve read requests. Full nodes with all plugins can serve any API call. Witness nodes only need the witness plugin and minimal APIs.

For production, you typically want:
- condenser_api (backward compat)
- database_api (modern queries)
- block_api (block data)
- account_history_api (transaction history)
- rc_api (resource credits)
- A reverse proxy (nginx) for HTTPS and rate limiting
</think>

Here is a complete guide to setting up a Hive API node for production:

```ini
# config.ini for a full API node
# Place in your hived data directory

# P2P configuration
p2p-endpoint = 0.0.0.0:2001
p2p-seed-node = seed.hive.blog:2001
p2p-seed-node = seed.openhive.network:2001
p2p-seed-node = hive-seed.roelandp.nl:2001
p2p-seed-node = seed.hiveseed.com:2001

# WebServer configuration
webserver-http-endpoint = 0.0.0.0:8091
webserver-ws-endpoint = 0.0.0.0:8090

# Plugins for full API node
plugin = condenser_api
plugin = database_api
plugin = block_api
plugin = account_history_api
plugin = account_history_rocksdb
plugin = rc_api
plugin = reputation_api
plugin = market_history_api
plugin = network_broadcast_api
plugin = witness_api
plugin = p2p
plugin = webserver
plugin = chain
plugin = account_by_key
plugin = account_by_key_api

# Shared memory configuration
# Adjust based on available RAM
shared-file-size = 24G
shared-file-dir = /dev/shm

# Account history (RocksDB backend is more efficient)
account-history-rocksdb-path = /data/hive/ah-rocksdb

# Replay optimization
flush-state-interval = 0

# Block log
block-data-export-file = NONE
```

Docker Compose setup:

```yaml
# docker-compose.yml
version: "3.8"
services:
  hived:
    image: hiveio/hive:latest
    container_name: hive-api-node
    restart: unless-stopped
    volumes:
      - ./data:/hive/data
      - /dev/shm:/dev/shm
    ports:
      - "2001:2001"   # P2P
      - "8090:8090"   # WebSocket API
      - "8091:8091"   # HTTP API
    command: >
      --data-dir=/hive/data
      --shared-file-dir=/dev/shm
    deploy:
      resources:
        limits:
          memory: 32G

  nginx:
    image: nginx:alpine
    container_name: hive-proxy
    restart: unless-stopped
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - hived
```

Nginx reverse proxy config:

```nginx
# nginx.conf
events { worker_connections 4096; }

http {
    upstream hive_api {
        server hived:8091;
        keepalive 32;
    }

    upstream hive_ws {
        server hived:8090;
    }

    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

    server {
        listen 443 ssl;
        server_name api.mynode.com;

        ssl_certificate /etc/nginx/certs/fullchain.pem;
        ssl_certificate_key /etc/nginx/certs/privkey.pem;

        location / {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://hive_api;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_read_timeout 30s;

            # CORS headers
            add_header Access-Control-Allow-Origin *;
            add_header Access-Control-Allow-Methods "POST, OPTIONS";
            add_header Access-Control-Allow-Headers "Content-Type";
        }

        location /ws {
            proxy_pass http://hive_ws;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
}
```

Hardware recommendations:
- API node: 16-32 GB RAM, 1 TB SSD, 4+ CPU cores
- Full node with account history: 32-64 GB RAM, 2 TB NVMe SSD
- Witness node: 16 GB RAM, 500 GB SSD (minimal plugins)
- Initial sync takes 2-3 days depending on hardware and network
'''
    ),
    (
        "hive/haf-framework",
        r'''What is HAF (Hive Application Framework) and how do I build applications on top of it?''',
        r'''HAF (Hive Application Framework) is a PostgreSQL-based framework that processes Hive blockchain data into SQL tables, enabling efficient application development. Instead of querying the blockchain API directly, you query a PostgreSQL database.

```python
# HAF application structure
# HAF stores all blockchain operations in PostgreSQL tables
# Your app registers for specific operation types and processes them

import psycopg2
import json

class HAFApplication:
    """Base class for HAF-based Hive applications."""

    def __init__(self, db_config, app_name):
        self.conn = psycopg2.connect(**db_config)
        self.app_name = app_name

    def setup(self):
        """Register the application with HAF."""
        with self.conn.cursor() as cur:
            # Create app-specific schema
            cur.execute(f"""
                CREATE SCHEMA IF NOT EXISTS {self.app_name};
            """)

            # Register with HAF context
            cur.execute("""
                SELECT haf.app_create_context(%s);
            """, (self.app_name,))

            self.conn.commit()

    def get_operations(self, op_type, start_block, end_block):
        """Query operations from HAF tables."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT
                    ho.block_num,
                    ho.trx_in_block,
                    ho.op_pos,
                    ho.timestamp,
                    ho.body
                FROM hive.operations_view ho
                WHERE ho.op_type_id = (
                    SELECT id FROM hive.operation_types
                    WHERE name = %s
                )
                AND ho.block_num BETWEEN %s AND %s
                ORDER BY ho.block_num, ho.trx_in_block, ho.op_pos;
            """, (op_type, start_block, end_block))
            return cur.fetchall()

    def process_block_range(self, start_block, end_block):
        """Process a range of blocks. Override in subclass."""
        raise NotImplementedError

    def get_last_processed_block(self):
        """Get the last block processed by this app."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT haf.app_get_current_block_num(%s);
            """, (self.app_name,))
            result = cur.fetchone()
            return result[0] if result else 0

    def run(self):
        """Main processing loop."""
        while True:
            last_block = self.get_last_processed_block()

            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT haf.app_next_block(%s);
                """, (self.app_name,))
                next_range = cur.fetchone()

            if next_range and next_range[0]:
                first_block, last_block = next_range[0]
                self.process_block_range(first_block, last_block)
                self.conn.commit()
            else:
                import time
                time.sleep(1)


# Example: Transfer tracking application
class TransferTracker(HAFApplication):
    def __init__(self, db_config):
        super().__init__(db_config, "transfer_tracker")

    def setup(self):
        super().setup()
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transfer_tracker.transfers (
                    id SERIAL PRIMARY KEY,
                    block_num BIGINT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    from_account TEXT NOT NULL,
                    to_account TEXT NOT NULL,
                    amount NUMERIC(20, 3) NOT NULL,
                    asset TEXT NOT NULL,
                    memo TEXT,
                    UNIQUE(block_num, from_account, to_account, amount, asset)
                );

                CREATE INDEX IF NOT EXISTS idx_transfers_from
                    ON transfer_tracker.transfers(from_account);
                CREATE INDEX IF NOT EXISTS idx_transfers_to
                    ON transfer_tracker.transfers(to_account);
                CREATE INDEX IF NOT EXISTS idx_transfers_block
                    ON transfer_tracker.transfers(block_num);
            """)
            self.conn.commit()

    def process_block_range(self, start_block, end_block):
        ops = self.get_operations(
            "transfer_operation", start_block, end_block
        )
        with self.conn.cursor() as cur:
            for block_num, trx, pos, timestamp, body in ops:
                data = json.loads(body)
                value = data.get("value", data)
                amount_str = value.get("amount", {})
                if isinstance(amount_str, dict):
                    amount = float(amount_str.get("amount", 0)) / (
                        10 ** amount_str.get("precision", 3))
                    asset = amount_str.get("nai", "HIVE")
                else:
                    parts = str(amount_str).split()
                    amount = float(parts[0])
                    asset = parts[1] if len(parts) > 1 else "HIVE"

                cur.execute("""
                    INSERT INTO transfer_tracker.transfers
                    (block_num, timestamp, from_account, to_account,
                     amount, asset, memo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING;
                """, (block_num, timestamp, value.get("from", ""),
                      value.get("to", ""), amount, asset,
                      value.get("memo", "")))

# Usage
# tracker = TransferTracker({
#     "host": "localhost", "port": 5432,
#     "dbname": "haf_db", "user": "haf_user"
# })
# tracker.setup()
# tracker.run()
```

HAF advantages over direct API queries:
- SQL queries are faster and more flexible than blockchain API calls
- No rate limiting issues
- Complex joins and aggregations are possible
- Automatic reindexing on chain replay
- Multiple apps can share the same HAF database
'''
    ),
    (
        "hive/load-balancing",
        r'''How do I set up load balancing across multiple Hive API nodes for high-availability dApp infrastructure?''',
        r'''Load balancing Hive API nodes ensures high availability and distributes request load. Here is a production setup:

```python
import requests
import time
import random
from concurrent.futures import ThreadPoolExecutor
import json

class HiveLoadBalancer:
    """Client-side load balancer for Hive API nodes."""

    def __init__(self, nodes):
        self.nodes = []
        for node in nodes:
            self.nodes.append({
                "url": node,
                "healthy": True,
                "latency": 0,
                "errors": 0,
                "last_check": 0,
                "weight": 1.0
            })
        self.health_check_interval = 30

    def _check_node_health(self, node):
        """Check if a node is healthy and measure latency."""
        try:
            start = time.time()
            resp = requests.post(
                node["url"],
                json={
                    "jsonrpc": "2.0",
                    "method": "condenser_api.get_dynamic_global_properties",
                    "params": [],
                    "id": 1
                },
                timeout=5
            )
            latency = time.time() - start

            if resp.status_code == 200:
                data = resp.json()
                if "result" in data:
                    node["healthy"] = True
                    node["latency"] = latency
                    node["errors"] = max(0, node["errors"] - 1)
                    # Check if node is synced
                    head_age = data["result"].get("time", "")
                    node["weight"] = 1.0 / max(latency, 0.01)
                    return True

            node["healthy"] = False
            node["errors"] += 1
        except Exception:
            node["healthy"] = False
            node["errors"] += 1
            node["latency"] = 999

        return False

    def health_check_all(self):
        """Check health of all nodes in parallel."""
        with ThreadPoolExecutor(max_workers=len(self.nodes)) as pool:
            pool.map(self._check_node_health, self.nodes)

        healthy = [n for n in self.nodes if n["healthy"]]
        total = len(self.nodes)
        print(f"Node health: {len(healthy)}/{total} healthy")
        for n in self.nodes:
            status = "OK" if n["healthy"] else "DOWN"
            print(f"  {n['url']:40s} {status} "
                  f"({n['latency']*1000:.0f}ms, {n['errors']} errors)")

    def get_node(self):
        """Get the best available node (weighted random)."""
        healthy = [n for n in self.nodes if n["healthy"]]
        if not healthy:
            # Fallback: try all nodes
            healthy = self.nodes

        # Weighted selection by inverse latency
        total_weight = sum(n["weight"] for n in healthy)
        r = random.uniform(0, total_weight)
        cumulative = 0
        for node in healthy:
            cumulative += node["weight"]
            if r <= cumulative:
                return node["url"]

        return healthy[0]["url"]

    def call(self, method, params=None, retries=3):
        """Make an API call with automatic failover."""
        last_error = None
        tried_nodes = set()

        for attempt in range(retries):
            node_url = self.get_node()
            tried_nodes.add(node_url)

            try:
                resp = requests.post(
                    node_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": method,
                        "params": params or {},
                        "id": 1
                    },
                    timeout=10
                )
                data = resp.json()
                if "result" in data:
                    return data["result"]
                if "error" in data:
                    last_error = data["error"]
            except Exception as e:
                last_error = str(e)
                # Mark node as potentially unhealthy
                for n in self.nodes:
                    if n["url"] == node_url:
                        n["errors"] += 1
                        if n["errors"] > 3:
                            n["healthy"] = False

        raise Exception(f"All retries failed. Last error: {last_error}")

# Usage
lb = HiveLoadBalancer([
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://api.openhive.network",
    "https://hive-api.arcange.eu",
    "https://api.hive.blue",
])

# Check node health
lb.health_check_all()

# Make API calls with automatic failover
props = lb.call("condenser_api.get_dynamic_global_properties")
print(f"Head block: {props['head_block_number']}")

accounts = lb.call("condenser_api.get_accounts", [["hiveio"]])
print(f"Account: {accounts[0]['name']}")
```

For server-side load balancing, use HAProxy or nginx upstream configuration with health checks. Client-side load balancing (shown above) is useful for dApps that connect directly to public API nodes. Always include multiple geographically distributed nodes for resilience.
'''
    ),
    (
        "hive/node-monitoring",
        r'''How do I monitor a Hive node's health, sync status, and performance metrics?''',
        r'''Here is a comprehensive monitoring solution for Hive nodes that tracks sync status, API responsiveness, and resource usage:

```python
import requests
import time
import json
from datetime import datetime

class HiveNodeMonitor:
    def __init__(self, node_url, name=""):
        self.url = node_url
        self.name = name or node_url
        self.metrics_history = []

    def rpc_call(self, method, params=None, timeout=10):
        """Make an RPC call and return result with timing."""
        start = time.time()
        try:
            resp = requests.post(self.url, json={
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
                "id": 1
            }, timeout=timeout)
            latency = time.time() - start
            data = resp.json()
            return data.get("result"), latency, None
        except Exception as e:
            latency = time.time() - start
            return None, latency, str(e)

    def check_sync_status(self):
        """Check if node is synced with the network."""
        result, latency, error = self.rpc_call(
            "condenser_api.get_dynamic_global_properties"
        )
        if error:
            return {"synced": False, "error": error}

        head_time = result.get("time", "")
        head_block = result.get("head_block_number", 0)
        lib = result.get("last_irreversible_block_num", 0)

        try:
            block_time = datetime.strptime(head_time, "%Y-%m-%dT%H:%M:%S")
            age_seconds = (datetime.utcnow() - block_time).total_seconds()
        except (ValueError, TypeError):
            age_seconds = 999

        return {
            "synced": age_seconds < 30,
            "head_block": head_block,
            "lib": lib,
            "block_age_seconds": age_seconds,
            "head_time": head_time,
            "latency_ms": latency * 1000
        }

    def check_api_endpoints(self):
        """Test various API endpoints for availability."""
        endpoints = [
            ("condenser_api.get_dynamic_global_properties", {}),
            ("database_api.get_dynamic_global_properties", {}),
            ("block_api.get_block", {"block_num": 1}),
            ("rc_api.find_rc_accounts", {"accounts": ["hiveio"]}),
            ("condenser_api.get_accounts", [["hiveio"]]),
        ]

        results = {}
        for method, params in endpoints:
            result, latency, error = self.rpc_call(method, params, timeout=5)
            api_name = method.split(".")[0]
            results[method] = {
                "available": error is None and result is not None,
                "latency_ms": round(latency * 1000, 1),
                "error": error
            }

        return results

    def full_health_check(self):
        """Run a complete health check."""
        print(f"\n=== Health Check: {self.name} ===")
        print(f"URL: {self.url}")
        print(f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")

        # Sync status
        sync = self.check_sync_status()
        sync_icon = "SYNCED" if sync.get("synced") else "OUT OF SYNC"
        print(f"Sync: {sync_icon}")
        print(f"  Head block: {sync.get('head_block', 'N/A')}")
        print(f"  LIB:        {sync.get('lib', 'N/A')}")
        print(f"  Block age:  {sync.get('block_age_seconds', 'N/A'):.0f}s")
        print(f"  Latency:    {sync.get('latency_ms', 0):.0f}ms")

        # API endpoints
        apis = self.check_api_endpoints()
        print(f"\nAPI Endpoints:")
        for method, status in apis.items():
            available = "UP" if status["available"] else "DOWN"
            print(f"  {method:50s} {available:5s} "
                  f"({status['latency_ms']:6.1f}ms)")

        # Compute overall health score
        api_count = len(apis)
        healthy_apis = sum(1 for s in apis.values() if s["available"])
        avg_latency = (sum(s["latency_ms"] for s in apis.values()) /
                       api_count if api_count else 999)

        score = 0
        if sync.get("synced"):
            score += 50
        score += (healthy_apis / api_count * 30) if api_count else 0
        if avg_latency < 500:
            score += 20
        elif avg_latency < 1000:
            score += 10

        print(f"\nHealth Score: {score:.0f}/100")
        print(f"APIs: {healthy_apis}/{api_count}")
        print(f"Avg latency: {avg_latency:.0f}ms")

        return {
            "sync": sync,
            "apis": apis,
            "score": score,
            "timestamp": datetime.utcnow().isoformat()
        }

# Monitor multiple nodes
def monitor_all_nodes(node_urls, interval=60):
    monitors = [HiveNodeMonitor(url) for url in node_urls]

    while True:
        for monitor in monitors:
            try:
                monitor.full_health_check()
            except Exception as e:
                print(f"Monitor error for {monitor.url}: {e}")
        print(f"\nNext check in {interval}s...")
        time.sleep(interval)

# Usage
monitor = HiveNodeMonitor("https://api.hive.blog", "Hive Blog API")
monitor.full_health_check()

# Monitor multiple nodes
# monitor_all_nodes([
#     "https://api.hive.blog",
#     "https://api.deathwing.me",
#     "https://api.openhive.network"
# ], interval=300)
```

For production monitoring, integrate with Prometheus/Grafana by exposing these metrics as Prometheus endpoints, or send them to a time-series database for historical analysis and alerting.
'''
    ),
    (
        "hive/node-replay-sync",
        r'''How do I replay the Hive blockchain from scratch or from a snapshot? What are the performance considerations?''',
        r'''Replaying the Hive blockchain involves processing all historical blocks to rebuild the chain state. This can be done from scratch (slow) or from a snapshot (fast). Here are both approaches:

```bash
#!/bin/bash
# Full replay from genesis (can take days)

# Method 1: Full replay from block_log
# Download block_log from a trusted source first
HIVE_DATA="/data/hive"
mkdir -p $HIVE_DATA

# Download block_log (200+ GB)
wget -O $HIVE_DATA/blockchain/block_log \
    "https://gtg.openhive.network/get/blockchain/block_log"

# Start replay
docker run -d --name hive-replay \
    -v $HIVE_DATA:/hive/data \
    -v /dev/shm:/dev/shm \
    hiveio/hive:latest \
    --data-dir=/hive/data \
    --shared-file-dir=/dev/shm \
    --replay-blockchain \
    --stop-replay-at-block=0

# Monitor progress
docker logs -f hive-replay 2>&1 | grep -E "block_num|replay"


# Method 2: Snapshot restore (much faster)
# Download a recent MIRA/RocksDB snapshot
wget -O $HIVE_DATA/snapshot.tar.zst \
    "https://gtg.openhive.network/get/snapshot/latest"

# Extract snapshot
cd $HIVE_DATA
zstd -d snapshot.tar.zst | tar xf -

# Start from snapshot (no full replay needed)
docker run -d --name hive-node \
    -v $HIVE_DATA:/hive/data \
    -v /dev/shm:/dev/shm \
    -p 2001:2001 -p 8090:8090 -p 8091:8091 \
    hiveio/hive:latest \
    --data-dir=/hive/data \
    --shared-file-dir=/dev/shm
```

Performance monitoring during replay:

```python
import subprocess
import time
import json
import requests
from datetime import datetime

def monitor_replay(node_url="http://localhost:8091", interval=30):
    """Monitor replay progress."""
    last_block = 0
    start_time = time.time()

    while True:
        try:
            resp = requests.post(node_url, json={
                "jsonrpc": "2.0",
                "method": "condenser_api.get_dynamic_global_properties",
                "params": [],
                "id": 1
            }, timeout=5)
            data = resp.json().get("result", {})
            current_block = data.get("head_block_number", 0)
            head_time = data.get("time", "")

            blocks_per_sec = (current_block - last_block) / interval
            elapsed = time.time() - start_time
            elapsed_hours = elapsed / 3600

            # Estimate total blocks (approximate current head)
            est_total = 85000000  # Update this periodically
            pct = (current_block / est_total * 100) if est_total else 0
            remaining_blocks = est_total - current_block
            eta_hours = (remaining_blocks / blocks_per_sec / 3600
                        if blocks_per_sec > 0 else 0)

            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"Block {current_block:,} ({pct:.1f}%) "
                  f"Speed: {blocks_per_sec:.0f} blocks/s "
                  f"ETA: {eta_hours:.1f}h "
                  f"Chain time: {head_time}")

            last_block = current_block

        except requests.ConnectionError:
            print("Node not yet accepting connections...")
        except Exception as e:
            print(f"Monitor error: {e}")

        time.sleep(interval)

# Replay optimization tips as config
REPLAY_CONFIG = """
# Optimized config.ini for fast replay

# Use all CPU cores for replay
# (hived uses multi-threaded validation where possible)

# Shared memory in tmpfs for maximum speed
shared-file-dir = /dev/shm
shared-file-size = 32G

# Disable unnecessary plugins during replay
# Only enable what you need post-replay
plugin = chain
plugin = p2p
plugin = webserver
plugin = condenser_api
plugin = database_api
plugin = block_api

# Account history can slow replay significantly
# Enable only if needed:
# plugin = account_history_api
# plugin = account_history_rocksdb
# account-history-rocksdb-path = /data/hive/ah-rocksdb

# Flush less frequently during replay
flush-state-interval = 10000

# Block log compression (saves disk space)
block-log-split = -1
"""

print(REPLAY_CONFIG)
# monitor_replay()
```

Replay performance tips:
- Use tmpfs/ramdisk for shared memory (shared-file-dir = /dev/shm)
- Disable account_history_api during initial replay if not needed
- Use NVMe SSD for block_log storage
- Snapshot restore is 10-100x faster than full replay
- A full replay from genesis takes 2-5 days on modern hardware
- Snapshot restore takes 1-4 hours depending on storage speed
'''
    ),
]
