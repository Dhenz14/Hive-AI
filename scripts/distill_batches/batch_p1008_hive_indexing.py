"""Hive blockchain training pairs: indexing and data processing."""

PAIRS = [
    (
        "hive/custom-indexer-python",
        r'''How do I build a custom blockchain indexer for Hive that stores operations in a SQL database?''',
        r'''<think>
A custom indexer needs to process Hive blocks sequentially and store relevant data. My first instinct is to just stream every block and insert each operation one at a time, but wait -- that would be extremely slow at scale because individual inserts have high overhead per round-trip. Batch inserts are the way to go here, since you can amortize the commit cost across hundreds of rows.

Now, should we process head blocks or only irreversible blocks? I considered tracking head blocks for lower latency, but actually that introduces a nasty complication: micro-forks. Hive can have short-lived forks where the last few blocks get replaced, meaning any data you indexed from those blocks becomes invalid. Therefore, for a first implementation, sticking to irreversible blocks is much safer -- you trade a few minutes of latency for guaranteed consistency.

Hmm, what about crash recovery? If the indexer dies mid-batch, we could end up with partial data. The solution is to checkpoint progress inside the same database transaction as the data writes. That way either both the data and the checkpoint commit, or neither does. I initially thought about using a separate state file on disk, but that would break atomicity -- you could update the checkpoint but crash before the data is flushed, or vice versa.

The architecture breaks down into: a block fetcher that reads from the chain, an operation filter that selects only the op types we care about (since indexing everything is wasteful for most use cases), a transformer to reshape ops into database rows, and a batch writer that groups inserts into transactions.
</think>

Here is a production-grade custom indexer for Hive that processes operations into a PostgreSQL database:

```python
import psycopg2
import psycopg2.extras
from beem import Hive
from beem.blockchain import Blockchain
import json
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("indexer")

class HiveIndexer:
    def __init__(self, db_dsn, nodes, op_types=None):
        self.db_dsn = db_dsn
        self.hive = Hive(node=nodes)
        self.blockchain = Blockchain(hive_instance=self.hive)
        self.op_types = set(op_types) if op_types else None
        self.batch_size = 100
        self._init_db()

    def _init_db(self):
        conn = psycopg2.connect(self.db_dsn)
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS indexer_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operations (
                    id BIGSERIAL PRIMARY KEY,
                    block_num BIGINT NOT NULL,
                    trx_id TEXT,
                    op_type TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    actor TEXT,
                    data JSONB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ops_block
                    ON operations(block_num);
                CREATE INDEX IF NOT EXISTS idx_ops_type
                    ON operations(op_type);
                CREATE INDEX IF NOT EXISTS idx_ops_actor
                    ON operations(actor);
                CREATE INDEX IF NOT EXISTS idx_ops_timestamp
                    ON operations(timestamp);
            """)
        conn.commit()
        conn.close()

    def get_last_block(self):
        conn = psycopg2.connect(self.db_dsn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT value FROM indexer_state WHERE key='last_block'"
            )
            row = cur.fetchone()
        conn.close()
        return int(row[0]) if row else None

    def save_last_block(self, conn, block_num):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO indexer_state (key, value)
                VALUES ('last_block', %s)
                ON CONFLICT (key) DO UPDATE SET value = %s
            """, (str(block_num), str(block_num)))

    def extract_actor(self, op_type, op_data):
        """Extract the primary actor from an operation."""
        actor_fields = [
            "author", "voter", "from", "account", "creator",
            "delegator", "witness", "owner"
        ]
        for field in actor_fields:
            if field in op_data:
                return op_data[field]
        # Check posting/active auths for custom_json
        if op_type == "custom_json":
            auths = (op_data.get("required_posting_auths", []) +
                     op_data.get("required_auths", []))
            return auths[0] if auths else None
        return None

    def process_block(self, block, block_num):
        """Extract operations from a block."""
        rows = []
        timestamp = block.get("timestamp", "")

        for tx in block.get("transactions", []):
            trx_id = tx.get("transaction_id", "")
            for op in tx.get("operations", []):
                if isinstance(op, list):
                    op_type, op_data = op[0], op[1]
                else:
                    op_type = op.get("type", "").replace("_operation", "")
                    op_data = op.get("value", op)

                if self.op_types and op_type not in self.op_types:
                    continue

                actor = self.extract_actor(op_type, op_data)
                rows.append((
                    block_num, trx_id, op_type, timestamp,
                    actor, json.dumps(op_data)
                ))
        return rows

    def run(self, use_irreversible=True):
        """Main indexing loop."""
        last_block = self.get_last_block()
        if last_block is None:
            props = self.hive.rpc.get_dynamic_global_properties()
            last_block = props["last_irreversible_block_num"] - 1000

        logger.info(f"Starting from block {last_block}")
        conn = psycopg2.connect(self.db_dsn)
        batch = []
        blocks_processed = 0

        while True:
            props = self.hive.rpc.get_dynamic_global_properties()
            target = (props["last_irreversible_block_num"]
                      if use_irreversible
                      else props["head_block_number"])

            while last_block < target:
                last_block += 1
                block = self.blockchain.get_block(last_block)
                if block:
                    rows = self.process_block(block, last_block)
                    batch.extend(rows)

                if len(batch) >= self.batch_size or last_block == target:
                    if batch:
                        with conn.cursor() as cur:
                            psycopg2.extras.execute_values(
                                cur,
                                """INSERT INTO operations
                                   (block_num, trx_id, op_type, timestamp,
                                    actor, data)
                                   VALUES %s""",
                                batch,
                                template="(%s, %s, %s, %s, %s, %s::jsonb)"
                            )
                        self.save_last_block(conn, last_block)
                        conn.commit()
                        blocks_processed += len(batch)
                        batch = []

                    if last_block % 1000 == 0:
                        logger.info(f"Block {last_block} ({blocks_processed} ops)")

            time.sleep(3)

# Usage
indexer = HiveIndexer(
    db_dsn="postgresql://user:pass@localhost/hive_index",
    nodes=["https://api.hive.blog", "https://api.deathwing.me"],
    op_types=["transfer", "vote", "comment", "custom_json"]
)
# indexer.run()
```

This indexer processes irreversible blocks, batch-inserts operations into PostgreSQL with JSONB for flexible querying, checkpoints progress, and indexes by block number, operation type, actor, and timestamp. For production scale, consider partitioning the operations table by block_num range.
'''
    ),
    (
        "hive/hivemind-architecture",
        r'''What is Hivemind's architecture and how does it provide the social layer for Hive?''',
        r'''Hivemind is the social consensus layer for Hive. It processes blockchain operations and builds a PostgreSQL database of social data (posts, follows, communities, notifications). Here is its architecture and how to work with it:

```python
# Hivemind Architecture Overview
# ==============================
# Hivemind sits between the blockchain and front-ends:
#
# [Hive Blockchain] -> [Hivemind Sync] -> [PostgreSQL] -> [Hivemind API]
#                                                              |
#                                                         [Front-ends]
#                                                    (PeakD, Ecency, etc.)

# Hivemind provides the "bridge" API namespace
# which powers all social features on Hive front-ends

import requests
import json

API_NODE = "https://api.hive.blog"

def bridge_call(method, params):
    payload = {
        "jsonrpc": "2.0",
        "method": f"bridge.{method}",
        "params": params,
        "id": 1
    }
    resp = requests.post(API_NODE, json=payload, timeout=15)
    return resp.json().get("result")

# Key Hivemind bridge API methods:

# 1. Post ranking (trending/hot/new algorithms)
def get_trending_posts(tag="", limit=20):
    """Get posts sorted by Hivemind's trending algorithm."""
    result = bridge_call("get_ranked_posts", {
        "sort": "trending",  # trending, hot, created, promoted, payout
        "tag": tag,          # empty for global, or community name
        "limit": limit,
        "observer": ""
    })
    for post in (result or []):
        print(f"  [{post.get('payout', 0):.2f}] @{post['author']}: "
              f"{post.get('title', '')[:50]}")
    return result

# 2. Account feed (posts from followed accounts)
def get_account_feed(account, limit=20):
    """Get personalized feed based on who the account follows."""
    return bridge_call("get_account_posts", {
        "account": account,
        "sort": "feed",
        "limit": limit,
        "observer": account
    })

# 3. Post details with social context
def get_post(author, permlink, observer=""):
    """Get a post with community info, reputation, etc."""
    result = bridge_call("get_post", {
        "author": author,
        "permlink": permlink,
        "observer": observer
    })
    if result:
        print(f"Title: {result.get('title')}")
        print(f"Community: {result.get('community_title', 'N/A')}")
        print(f"Reputation: {result.get('author_reputation', 0)}")
        print(f"Payout: ${result.get('payout', 0):.2f}")
        print(f"Votes: {result.get('stats', {}).get('total_votes', 0)}")
    return result

# 4. Follow/mute relationships
def get_following(account, what="blog", limit=100):
    """Get accounts that a user follows."""
    return bridge_call("get_relationship_between_accounts", [
        account, "some_other_account"
    ])

# 5. Notifications
def get_notifications(account, limit=50):
    """Get account notifications (votes, replies, mentions, etc.)."""
    result = bridge_call("account_notifications", {
        "account": account,
        "limit": limit
    })
    if result:
        for n in result[:10]:
            print(f"  [{n.get('date', '')}] {n.get('type', '')}: "
                  f"{n.get('msg', '')[:60]}")
    return result

# 6. Discussion threads
def get_discussion(author, permlink):
    """Get a full comment thread as a flat dictionary."""
    result = bridge_call("get_discussion", {
        "author": author,
        "permlink": permlink,
        "observer": ""
    })
    if result:
        print(f"Discussion has {len(result)} posts/comments")
    return result

# Hivemind's key database tables:
HIVEMIND_SCHEMA = """
Key PostgreSQL tables in Hivemind:

hive_posts:
  - Denormalized post data (title, body, metadata)
  - Payout calculations
  - Community assignments
  - Vote counts and values

hive_accounts:
  - Account metadata (reputation, post count)
  - Followers/following counts
  - Profile information

hive_follows:
  - Follow/mute relationships between accounts
  - Blog follows vs mutes

hive_communities:
  - Community properties and settings
  - Role assignments
  - Subscriber counts

hive_feed_cache:
  - Pre-computed feeds for accounts
  - Powers the "feed" sort order

hive_reblogs:
  - Reblog (reshare) tracking

hive_notifications:
  - Notification events per account
"""
print(HIVEMIND_SCHEMA)

# Usage
get_trending_posts(limit=5)
get_notifications("blocktrades", limit=5)
get_post("hiveio", "hive-hardfork-25")
```

Hivemind processes all blockchain operations that have social significance (comments, votes, follows, custom_json for communities) and maintains a structured PostgreSQL database. Front-ends query the bridge API instead of the raw blockchain API for social features, which is much faster and provides computed fields like reputation, trending scores, and notification feeds.
'''
    ),
    (
        "hive/sql-block-processing",
        r'''How do I process Hive blockchain data efficiently using SQL for analytics and reporting?''',
        r'''Once you have Hive data in a SQL database (via HAF, custom indexer, or Hivemind), you can run powerful analytics queries. Here are common patterns:

```sql
-- Assuming tables from a custom indexer or HAF setup

-- 1. Daily transfer volume
SELECT
    DATE(timestamp) as day,
    COUNT(*) as transfer_count,
    SUM((data->>'amount')::text::numeric) as total_volume,
    COUNT(DISTINCT data->>'from') as unique_senders,
    COUNT(DISTINCT data->>'to') as unique_receivers
FROM operations
WHERE op_type = 'transfer'
    AND timestamp >= NOW() - INTERVAL '30 days'
GROUP BY DATE(timestamp)
ORDER BY day DESC;

-- 2. Top custom_json dApp usage
SELECT
    data->>'id' as dapp_id,
    COUNT(*) as op_count,
    COUNT(DISTINCT actor) as unique_users,
    MIN(timestamp) as first_seen,
    MAX(timestamp) as last_seen
FROM operations
WHERE op_type = 'custom_json'
    AND timestamp >= NOW() - INTERVAL '7 days'
GROUP BY data->>'id'
ORDER BY op_count DESC
LIMIT 20;

-- 3. Account activity heatmap (hourly)
SELECT
    EXTRACT(HOUR FROM timestamp) as hour_utc,
    EXTRACT(DOW FROM timestamp) as day_of_week,
    COUNT(*) as op_count
FROM operations
WHERE actor = 'someaccount'
    AND timestamp >= NOW() - INTERVAL '90 days'
GROUP BY hour_utc, day_of_week
ORDER BY day_of_week, hour_utc;

-- 4. Delegation flow analysis
SELECT
    data->>'delegator' as delegator,
    data->>'delegatee' as delegatee,
    (data->>'vesting_shares')::text as vesting_shares,
    timestamp
FROM operations
WHERE op_type = 'delegate_vesting_shares'
    AND timestamp >= NOW() - INTERVAL '30 days'
ORDER BY timestamp DESC
LIMIT 100;

-- 5. Whale transfer alerts (>10000 HIVE)
SELECT
    block_num,
    timestamp,
    data->>'from' as sender,
    data->>'to' as receiver,
    data->>'amount' as amount,
    data->>'memo' as memo
FROM operations
WHERE op_type = 'transfer'
    AND (data->>'amount')::text LIKE '%HIVE%'
    AND SPLIT_PART(data->>'amount', ' ', 1)::numeric >= 10000
    AND timestamp >= NOW() - INTERVAL '24 hours'
ORDER BY SPLIT_PART(data->>'amount', ' ', 1)::numeric DESC;
```

Python wrapper for running analytics:

```python
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta

class HiveAnalytics:
    def __init__(self, db_dsn):
        self.dsn = db_dsn

    def query(self, sql, params=None):
        conn = psycopg2.connect(self.dsn)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            results = cur.fetchall()
        conn.close()
        return results

    def daily_active_users(self, days=30):
        """Count daily unique actors."""
        results = self.query("""
            SELECT DATE(timestamp) as day,
                   COUNT(DISTINCT actor) as dau
            FROM operations
            WHERE timestamp >= NOW() - INTERVAL '%s days'
            GROUP BY DATE(timestamp)
            ORDER BY day
        """, (days,))
        for r in results:
            print(f"  {r['day']}: {r['dau']:,} active users")
        return results

    def top_operations(self, days=7, limit=15):
        """Most common operation types."""
        results = self.query("""
            SELECT op_type, COUNT(*) as count,
                   COUNT(DISTINCT actor) as unique_actors
            FROM operations
            WHERE timestamp >= NOW() - INTERVAL '%s days'
            GROUP BY op_type
            ORDER BY count DESC
            LIMIT %s
        """, (days, limit))
        print(f"Top operations (last {days} days):")
        for r in results:
            print(f"  {r['op_type']:30s} {r['count']:>10,} "
                  f"({r['unique_actors']:,} actors)")
        return results

    def account_summary(self, account, days=30):
        """Summarize an account's activity."""
        results = self.query("""
            SELECT op_type, COUNT(*) as count
            FROM operations
            WHERE actor = %s
                AND timestamp >= NOW() - INTERVAL '%s days'
            GROUP BY op_type
            ORDER BY count DESC
        """, (account, days))
        print(f"Activity for @{account} (last {days} days):")
        for r in results:
            print(f"  {r['op_type']:30s}: {r['count']:,}")
        return results

# analytics = HiveAnalytics("postgresql://user:pass@localhost/hive_index")
# analytics.daily_active_users()
# analytics.top_operations()
# analytics.account_summary("blocktrades")
```

For best performance with large datasets, use table partitioning by timestamp or block_num, create appropriate indexes, and consider materialized views for frequently-accessed aggregations.
'''
    ),
    (
        "hive/operation-filtering-scale",
        r'''How do I efficiently filter and process specific operations from millions of Hive blocks at scale?''',
        r'''Processing Hive at scale requires careful optimization. Here are patterns for high-throughput operation filtering:

```python
from beem import Hive
from beem.blockchain import Blockchain
import json
import time
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import queue

class ScalableOperationFilter:
    """High-throughput operation filtering for Hive."""

    def __init__(self, nodes, op_types, batch_size=100):
        self.nodes = nodes
        self.op_types = set(op_types)
        self.batch_size = batch_size

    def fetch_block_batch(self, start_block, count, node_url):
        """Fetch a batch of blocks from a specific node."""
        from beem import Hive
        hive = Hive(node=[node_url])
        blocks = []
        for block_num in range(start_block, start_block + count):
            try:
                block = hive.rpc.get_block(
                    {"block_num": block_num}, api="block_api"
                )
                if block and "block" in block:
                    blocks.append((block_num, block["block"]))
            except Exception:
                pass
        return blocks

    def extract_operations(self, block_num, block_data):
        """Extract and filter operations from a block."""
        results = []
        timestamp = block_data.get("timestamp", "")

        for tx in block_data.get("transactions", []):
            for op in tx.get("operations", []):
                if isinstance(op, list):
                    op_type, op_data = op[0], op[1]
                elif isinstance(op, dict):
                    op_type = op.get("type", "").replace("_operation", "")
                    op_data = op.get("value", op)
                else:
                    continue

                if op_type in self.op_types:
                    results.append({
                        "block": block_num,
                        "timestamp": timestamp,
                        "type": op_type,
                        "data": op_data
                    })
        return results

    def process_range(self, start_block, end_block, callback):
        """Process a block range with parallel fetching."""
        total = end_block - start_block
        processed = 0
        current = start_block

        # Use multiple nodes for parallel fetching
        node_count = len(self.nodes)

        while current < end_block:
            batch_end = min(current + self.batch_size, end_block)
            blocks_needed = batch_end - current

            # Distribute blocks across nodes
            fetch_tasks = []
            blocks_per_node = max(1, blocks_needed // node_count)

            with ThreadPoolExecutor(max_workers=node_count) as pool:
                for i, node in enumerate(self.nodes):
                    task_start = current + i * blocks_per_node
                    task_count = min(blocks_per_node, batch_end - task_start)
                    if task_count > 0:
                        future = pool.submit(
                            self.fetch_block_batch,
                            task_start, task_count, node
                        )
                        fetch_tasks.append(future)

                # Collect results
                all_blocks = []
                for future in fetch_tasks:
                    all_blocks.extend(future.result())

            # Sort by block number
            all_blocks.sort(key=lambda x: x[0])

            # Extract operations
            for block_num, block_data in all_blocks:
                ops = self.extract_operations(block_num, block_data)
                for op in ops:
                    callback(op)

            processed += len(all_blocks)
            current = batch_end

            if processed % 1000 == 0:
                pct = processed / total * 100 if total > 0 else 0
                print(f"Progress: {processed:,}/{total:,} blocks "
                      f"({pct:.1f}%)")

    def stream_filtered(self, callback, start_block=None):
        """Stream filtered operations in real-time."""
        hive = Hive(node=self.nodes)
        blockchain = Blockchain(hive_instance=hive)

        stream = blockchain.stream(
            opNames=list(self.op_types),
            start=start_block,
            raw_ops=False,
            threading=False,
            max_batch_size=50
        )

        for op in stream:
            callback(op)

# Usage example: Index all transfers and votes for analysis
def handle_operation(op):
    op_type = op.get("type", op.get("op_type", ""))
    block = op.get("block", op.get("block_num", ""))
    if op_type == "transfer":
        data = op.get("data", op)
        print(f"[{block}] Transfer: {data.get('from')} -> "
              f"{data.get('to')}: {data.get('amount')}")

filter_engine = ScalableOperationFilter(
    nodes=[
        "https://api.hive.blog",
        "https://api.deathwing.me",
        "https://api.openhive.network"
    ],
    op_types=["transfer", "vote", "custom_json"],
    batch_size=50
)

# Historical processing
# filter_engine.process_range(80000000, 80010000, handle_operation)

# Real-time streaming
# filter_engine.stream_filtered(handle_operation)
```

Scale optimization strategies:
- Parallel block fetching across multiple API nodes
- Use opNames filter in beem to reduce data transfer
- Batch database writes (insert every N operations, not every one)
- For historical processing, use block_log directly instead of API calls
- Consider HAF for production-scale indexing (processes block_log natively)
- Use process pools for CPU-intensive operation parsing
'''
    ),
    (
        "hive/indexer-state-management",
        r'''How do I handle state management and crash recovery in a Hive blockchain indexer?''',
        r'''Reliable state management is critical for indexers. Here is a pattern that handles crash recovery, micro-forks, and checkpointing:

```python
import psycopg2
import json
import time
import logging
from contextlib import contextmanager
from beem import Hive
from beem.blockchain import Blockchain

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("indexer_state")

class IndexerStateManager:
    """Manages indexer state with crash recovery and fork handling."""

    def __init__(self, db_dsn, app_name):
        self.db_dsn = db_dsn
        self.app_name = app_name
        self._init_state_table()

    def _init_state_table(self):
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS indexer_state (
                        app_name TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT,
                        updated_at TIMESTAMP DEFAULT NOW(),
                        PRIMARY KEY (app_name, key)
                    );
                    CREATE TABLE IF NOT EXISTS indexer_block_hashes (
                        app_name TEXT NOT NULL,
                        block_num BIGINT NOT NULL,
                        block_id TEXT NOT NULL,
                        PRIMARY KEY (app_name, block_num)
                    );
                """)
            conn.commit()

    @contextmanager
    def _get_conn(self):
        conn = psycopg2.connect(self.db_dsn)
        try:
            yield conn
        finally:
            conn.close()

    def get_state(self, key, default=None):
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT value FROM indexer_state "
                    "WHERE app_name=%s AND key=%s",
                    (self.app_name, key)
                )
                row = cur.fetchone()
                return row[0] if row else default

    def set_state(self, conn, key, value):
        """Set state within an existing transaction."""
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO indexer_state (app_name, key, value, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (app_name, key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = NOW()
            """, (self.app_name, key, str(value)))

    def save_block_hash(self, conn, block_num, block_id):
        """Store block hash for fork detection."""
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO indexer_block_hashes (app_name, block_num, block_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (app_name, block_num) DO UPDATE
                SET block_id = EXCLUDED.block_id
            """, (self.app_name, block_num, block_id))

    def detect_fork(self, conn, block_num, block_id):
        """Check if a block has changed (fork detection)."""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT block_id FROM indexer_block_hashes "
                "WHERE app_name=%s AND block_num=%s",
                (self.app_name, block_num)
            )
            row = cur.fetchone()
            if row and row[0] != block_id:
                logger.warning(
                    f"Fork detected at block {block_num}! "
                    f"Old: {row[0][:16]}, New: {block_id[:16]}"
                )
                return True
        return False

    def handle_fork(self, conn, fork_block):
        """Roll back data from a forked block."""
        logger.info(f"Rolling back data from block {fork_block}")
        with conn.cursor() as cur:
            # Delete operations from forked blocks
            cur.execute(
                "DELETE FROM operations WHERE block_num >= %s",
                (fork_block,)
            )
            # Delete block hashes from forked blocks
            cur.execute(
                "DELETE FROM indexer_block_hashes "
                "WHERE app_name=%s AND block_num >= %s",
                (self.app_name, fork_block)
            )
            # Reset last processed block
            self.set_state(conn, "last_block", str(fork_block - 1))
        conn.commit()
        logger.info(f"Rollback complete. Resuming from block {fork_block}")

    def cleanup_old_hashes(self, conn, keep_blocks=1000):
        """Remove old block hashes to save space."""
        last_block = int(self.get_state("last_block", "0"))
        cutoff = last_block - keep_blocks
        if cutoff > 0:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM indexer_block_hashes "
                    "WHERE app_name=%s AND block_num < %s",
                    (self.app_name, cutoff)
                )

class ResilientIndexer:
    """Indexer with built-in crash recovery and fork handling."""

    def __init__(self, db_dsn, nodes, app_name="main_indexer"):
        self.state = IndexerStateManager(db_dsn, app_name)
        self.db_dsn = db_dsn
        self.hive = Hive(node=nodes)

    def run(self):
        last_block = int(self.state.get_state("last_block", "0"))
        if last_block == 0:
            props = self.hive.rpc.get_dynamic_global_properties()
            last_block = props["last_irreversible_block_num"]

        logger.info(f"Resuming from block {last_block}")
        blockchain = Blockchain(hive_instance=self.hive)

        while True:
            try:
                props = self.hive.rpc.get_dynamic_global_properties()
                lib = props["last_irreversible_block_num"]

                conn = psycopg2.connect(self.db_dsn)
                while last_block < lib:
                    last_block += 1
                    block = blockchain.get_block(last_block)
                    if not block:
                        continue

                    block_id = block.get("block_id", "")
                    if self.state.detect_fork(conn, last_block, block_id):
                        self.state.handle_fork(conn, last_block)
                        continue

                    self.state.save_block_hash(conn, last_block, block_id)
                    # Process operations here...
                    self.state.set_state(conn, "last_block", str(last_block))

                    if last_block % 100 == 0:
                        conn.commit()
                        self.state.cleanup_old_hashes(conn)

                conn.commit()
                conn.close()
                time.sleep(3)

            except Exception as e:
                logger.error(f"Error: {e}, retrying in 5s...")
                time.sleep(5)

# indexer = ResilientIndexer(
#     "postgresql://user:pass@localhost/hive",
#     ["https://api.hive.blog"],
# )
# indexer.run()
```

This state management pattern provides: crash recovery via checkpointed block numbers, fork detection via stored block hashes, automatic rollback on detected forks, and periodic cleanup of old state data. For production, add metrics (processed blocks/second, lag from head) and alerting.
'''
    ),
]
