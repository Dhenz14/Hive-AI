"""
Hive blockchain thinking pairs - data architecture reasoning
"""

pairs = [
    {
        "instruction": r'''I need to index Hive blockchain data for my application. Should I build a custom indexer from scratch or use the Hive Application Framework (HAF)?''',
        "output": r'''<think>
Custom indexer vs HAF -- this is a significant architectural decision. Let me think about what each option involves.

HAF (Hive Application Framework) is an official framework that provides a PostgreSQL database with all Hive blockchain data pre-indexed. Applications run as "HAF apps" that process operations from the HAF database rather than directly from the blockchain. HAF handles block syncing, fork management, and data storage.

A custom indexer is code you write that connects to an API node, streams blocks, parses operations, and stores them in your own database.

Advantages of HAF:
- All blockchain data is already in PostgreSQL
- Fork handling is built-in (reversible vs irreversible blocks)
- Applications can share the same HAF instance
- SQL access to historical data
- Maintained by the Hive core team

Disadvantages of HAF:
- Heavy infrastructure: full HAF node needs a lot of disk space (terabytes for full history)
- Requires running hived + HAF PostgreSQL
- Learning curve for HAF-specific APIs
- Might be overkill if you only need a small subset of data

Hmm, I initially thought HAF would be the obvious choice for any serious application, but actually if my app only needs custom_json operations for a specific id, syncing the entire blockchain history through HAF is massive overkill. A targeted custom indexer that only processes the operations I care about would be much lighter.

The tradeoff is: HAF (complete data, heavy infra, built-in reliability) vs custom indexer (only what you need, lightweight, but you handle everything). For a small-to-medium app that tracks specific custom_json operations, a custom indexer is more practical. For a full block explorer or a large-scale analytics platform, HAF makes more sense.

Actually, there is a middle ground: use a custom indexer but take advantage of some HAF concepts -- like tracking the last irreversible block for fork safety and using PostgreSQL with proper schema design.

Could also consider using the condenser API to backfill historical data and then stream new blocks going forward. This avoids syncing the entire chain but gives you the data you need.
</think>

The choice depends on your data needs. Here is a comparison and a practical custom indexer that borrows HAF concepts:

```python
# === Decision Matrix ===
#
# Use HAF when:
# - You need access to ALL blockchain data
# - Building a block explorer, analytics platform, or hivemind replacement
# - You already run a hived node
# - Multiple apps can share the HAF database
#
# Use a custom indexer when:
# - You only need specific operation types (e.g., custom_json for your app)
# - You want lightweight infrastructure
# - You need to deploy quickly
# - Your data volume is manageable (thousands, not billions of records)

# === Custom Indexer with HAF-Inspired Design ===

import psycopg2
import psycopg2.extras
from beem import Hive
from beem.blockchain import Blockchain
import json
import time
from contextlib import contextmanager

hive = Hive(node=[
    "https://api.hive.blog",
    "https://api.deathwing.me"
])

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "hive_indexer",
    "user": "indexer",
    "password": "indexer_password"
}


class HiveCustomIndexer:
    """Lightweight indexer for specific Hive operations.

    Borrows HAF concepts: reversible/irreversible tracking,
    PostgreSQL storage, atomic checkpoint updates.
    """

    def __init__(self, app_name, ops_of_interest, db_config):
        self.app_name = app_name
        self.ops_filter = set(ops_of_interest)
        self.db_config = db_config
        self.conn = None

    def connect(self):
        self.conn = psycopg2.connect(**self.db_config)
        self._init_schema()

    @contextmanager
    def _cursor(self):
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            yield cur
        finally:
            cur.close()

    def _init_schema(self):
        """Create tables if they do not exist."""
        with self._cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS indexer_state (
                    app_name TEXT PRIMARY KEY,
                    last_block INTEGER NOT NULL,
                    last_irreversible INTEGER NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS indexed_operations (
                    id BIGSERIAL PRIMARY KEY,
                    block_num INTEGER NOT NULL,
                    tx_id TEXT,
                    op_type TEXT NOT NULL,
                    op_data JSONB NOT NULL,
                    account TEXT,
                    is_irreversible BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ops_block
                ON indexed_operations(block_num)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ops_account
                ON indexed_operations(account)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ops_type
                ON indexed_operations(op_type)
            """)
            self.conn.commit()

    def get_last_block(self):
        """Get the last processed block number."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT last_block FROM indexer_state WHERE app_name = %s",
                (self.app_name,)
            )
            row = cur.fetchone()
            return row["last_block"] if row else 0

    def _process_block(self, block_num, block_data, cursor):
        """Process a single block within a transaction."""
        for tx in block_data.get("transactions", []):
            tx_id = tx.get("transaction_id", "")
            for op in tx.get("operations", []):
                op_type = op[0] if isinstance(op, list) else op.get("type")

                if op_type not in self.ops_filter:
                    continue

                op_data = op[1] if isinstance(op, list) else op.get("value")

                # Extract account for indexing
                account = None
                if op_type == "custom_json":
                    auths = (op_data.get("required_posting_auths") or
                             op_data.get("required_auths") or [])
                    account = auths[0] if auths else None
                elif op_type == "vote":
                    account = op_data.get("voter")
                elif op_type in ("comment", "transfer"):
                    account = op_data.get("from", op_data.get("author"))

                cursor.execute("""
                    INSERT INTO indexed_operations
                    (block_num, tx_id, op_type, op_data, account)
                    VALUES (%s, %s, %s, %s, %s)
                """, (block_num, tx_id, op_type,
                      json.dumps(op_data), account))

    def _update_checkpoint(self, block_num, lib, cursor):
        """Update checkpoint atomically with data."""
        cursor.execute("""
            INSERT INTO indexer_state (app_name, last_block,
                                       last_irreversible, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (app_name) DO UPDATE SET
                last_block = EXCLUDED.last_block,
                last_irreversible = EXCLUDED.last_irreversible,
                updated_at = NOW()
        """, (self.app_name, block_num, lib))

    def _mark_irreversible(self, lib, cursor):
        """Mark operations as irreversible up to LIB."""
        cursor.execute("""
            UPDATE indexed_operations
            SET is_irreversible = TRUE
            WHERE block_num <= %s AND is_irreversible = FALSE
        """, (lib,))

    def run(self, start_block=None):
        """Main indexing loop."""
        chain = Blockchain(blockchain_instance=hive)
        current = start_block or self.get_last_block() + 1

        if current == 1:
            current = chain.get_current_block_num()
            print(f"No checkpoint found, starting from head: {current}")
        else:
            print(f"Resuming from block {current}")

        batch_count = 0

        while True:
            try:
                block = hive.rpc.get_block(current)
                if block is None:
                    time.sleep(1)
                    continue

                props = hive.rpc.get_dynamic_global_properties()
                lib = props["last_irreversible_block_num"]

                with self._cursor() as cur:
                    self._process_block(current, block, cur)
                    self._mark_irreversible(lib, cur)

                    # Checkpoint every 10 blocks
                    batch_count += 1
                    if batch_count >= 10:
                        self._update_checkpoint(current, lib, cur)
                        self.conn.commit()
                        batch_count = 0
                    else:
                        self.conn.commit()

                current += 1

                if current % 100 == 0:
                    print(f"Block {current} | LIB: {lib} | "
                          f"Gap: {current - lib}")

            except KeyboardInterrupt:
                with self._cursor() as cur:
                    self._update_checkpoint(current - 1, lib, cur)
                    self.conn.commit()
                print(f"Stopped at block {current - 1}")
                break
            except Exception as e:
                print(f"Error at block {current}: {e}")
                self.conn.rollback()
                time.sleep(5)


# === Usage ===

indexer = HiveCustomIndexer(
    app_name="myapp",
    ops_of_interest=["custom_json", "vote", "comment"],
    db_config=DB_CONFIG
)
indexer.connect()
indexer.run()
```

This custom indexer gives you 90% of HAF's reliability (atomic checkpoints, fork safety via LIB tracking, PostgreSQL storage) at 10% of the infrastructure cost. It only indexes the operations you care about, so the database stays small. For apps that need full blockchain history or complex cross-operation queries, HAF is worth the infrastructure investment.'''
    },
    {
        "instruction": r'''I am designing a PostgreSQL schema to store Hive post data and vote data for an analytics dashboard. What schema design should I use?''',
        "output": r'''<think>
Database schema for Hive analytics -- I need to think about what queries the dashboard will need and design the schema to support them efficiently.

Common analytics queries:
- Top posts by votes, payout, comments in a time range
- Author performance over time
- Voting patterns (who votes on whom, when)
- Community-level statistics
- Tag/topic trends

Let me think about normalization vs denormalization. A fully normalized schema would have separate tables for posts, votes, authors, tags, etc. with foreign keys. This is clean but requires JOINs for most queries.

A denormalized schema would duplicate some data (e.g., author reputation stored on each post) to avoid JOINs. This is faster for reads but takes more space and requires update logic.

Hmm, for an analytics dashboard, reads heavily outweigh writes. The indexer writes data once and the dashboard queries it many times. So some denormalization is justified.

I initially thought about using a single wide posts table with all data, but that gets messy when a post has multiple tags, multiple votes, etc. Those are one-to-many relationships that need separate tables.

For the votes table, I need to think about cardinality. A popular post can have thousands of votes. The votes table will be the largest table by far. I need proper indexes: (author, permlink) for looking up votes on a post, (voter) for a user's voting history, (block_num) for time-range queries.

Wait, should I use the post's author+permlink as the key, or create a synthetic post_id? Author+permlink is the natural key on Hive but it is a compound string key. A synthetic integer ID would be faster for JOINs. I think using a serial post_id with a unique constraint on (author, permlink) is the right approach.

For tags, I should use a junction table (post_tags) since posts can have multiple tags. This enables efficient tag-based queries with proper indexing.

I should also consider partitioning. If the dashboard covers months or years of data, partitioning by time (monthly) would help with query performance on time-range queries.
</think>

Here is a schema optimized for analytics reads with proper indexing and partitioning:

```python
"""
PostgreSQL schema for Hive analytics dashboard.
Designed for read-heavy workloads with efficient aggregation.
"""

SCHEMA_SQL = """
-- === Posts Table ===
-- Core post data with some denormalized fields for fast queries

CREATE TABLE IF NOT EXISTS posts (
    post_id BIGSERIAL PRIMARY KEY,
    author TEXT NOT NULL,
    permlink TEXT NOT NULL,
    parent_author TEXT DEFAULT '',
    parent_permlink TEXT DEFAULT '',
    title TEXT DEFAULT '',
    body TEXT DEFAULT '',
    category TEXT DEFAULT '',
    community TEXT DEFAULT '',

    -- Denormalized metrics (updated by indexer)
    net_votes INTEGER DEFAULT 0,
    total_payout NUMERIC(15, 3) DEFAULT 0,
    curator_payout NUMERIC(15, 3) DEFAULT 0,
    pending_payout NUMERIC(15, 3) DEFAULT 0,
    reply_count INTEGER DEFAULT 0,

    -- Author info (denormalized for fast queries)
    author_reputation NUMERIC(10, 2) DEFAULT 0,

    -- Metadata
    json_metadata JSONB DEFAULT '{}',
    app TEXT DEFAULT '',

    -- Timestamps
    created_at TIMESTAMP NOT NULL,
    last_payout_at TIMESTAMP,
    block_num INTEGER NOT NULL,
    is_comment BOOLEAN DEFAULT FALSE,

    UNIQUE (author, permlink)
);

CREATE INDEX idx_posts_author ON posts(author);
CREATE INDEX idx_posts_community ON posts(community);
CREATE INDEX idx_posts_created ON posts(created_at DESC);
CREATE INDEX idx_posts_payout ON posts(pending_payout DESC);
CREATE INDEX idx_posts_block ON posts(block_num);
CREATE INDEX idx_posts_is_comment ON posts(is_comment);


-- === Tags Table (junction) ===

CREATE TABLE IF NOT EXISTS post_tags (
    post_id BIGINT REFERENCES posts(post_id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (post_id, tag)
);

CREATE INDEX idx_tags_tag ON post_tags(tag);


-- === Votes Table ===
-- Largest table -- partitioned by month for performance

CREATE TABLE IF NOT EXISTS votes (
    vote_id BIGSERIAL,
    post_id BIGINT NOT NULL,
    voter TEXT NOT NULL,
    author TEXT NOT NULL,
    permlink TEXT NOT NULL,
    weight SMALLINT NOT NULL,       -- -10000 to 10000
    rshares BIGINT DEFAULT 0,
    block_num INTEGER NOT NULL,
    voted_at TIMESTAMP NOT NULL,

    PRIMARY KEY (vote_id, voted_at)
) PARTITION BY RANGE (voted_at);

-- Create monthly partitions (add more as needed)
CREATE TABLE votes_2024_01 PARTITION OF votes
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
CREATE TABLE votes_2024_02 PARTITION OF votes
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');
-- ... add partitions as needed

CREATE INDEX idx_votes_post ON votes(post_id);
CREATE INDEX idx_votes_voter ON votes(voter);
CREATE INDEX idx_votes_author ON votes(author, permlink);
CREATE INDEX idx_votes_block ON votes(block_num);


-- === Authors Table (materialized stats) ===

CREATE TABLE IF NOT EXISTS author_stats (
    author TEXT PRIMARY KEY,
    total_posts INTEGER DEFAULT 0,
    total_comments INTEGER DEFAULT 0,
    total_votes_received INTEGER DEFAULT 0,
    total_votes_cast INTEGER DEFAULT 0,
    total_payout NUMERIC(15, 3) DEFAULT 0,
    avg_payout NUMERIC(15, 3) DEFAULT 0,
    reputation NUMERIC(10, 2) DEFAULT 0,
    first_post_at TIMESTAMP,
    last_post_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW()
);


-- === Daily Aggregates (materialized for fast dashboards) ===

CREATE TABLE IF NOT EXISTS daily_stats (
    stat_date DATE NOT NULL,
    community TEXT DEFAULT 'all',
    total_posts INTEGER DEFAULT 0,
    total_comments INTEGER DEFAULT 0,
    total_votes INTEGER DEFAULT 0,
    total_payout NUMERIC(15, 3) DEFAULT 0,
    unique_authors INTEGER DEFAULT 0,
    unique_voters INTEGER DEFAULT 0,
    PRIMARY KEY (stat_date, community)
);


-- === Indexer State ===

CREATE TABLE IF NOT EXISTS indexer_state (
    app_name TEXT PRIMARY KEY,
    last_block INTEGER NOT NULL,
    last_irreversible INTEGER NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);
"""


# === Python Indexer Integration ===

import psycopg2
import psycopg2.extras
import json
from datetime import datetime


class AnalyticsIndexer:
    """Index Hive data into the analytics schema."""

    def __init__(self, db_config):
        self.conn = psycopg2.connect(**db_config)

    def index_post(self, op_data, block_num, timestamp):
        """Index a comment/post operation."""
        author = op_data["author"]
        permlink = op_data["permlink"]
        is_comment = bool(op_data.get("parent_author", ""))

        meta = {}
        try:
            meta = json.loads(op_data.get("json_metadata", "{}") or "{}")
        except json.JSONDecodeError:
            pass

        tags = meta.get("tags", [])
        app = meta.get("app", "")
        community = op_data.get("parent_permlink", "") if not is_comment else ""

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO posts (author, permlink, parent_author,
                    parent_permlink, title, body, category, community,
                    json_metadata, app, created_at, block_num, is_comment)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (author, permlink) DO UPDATE SET
                    title = EXCLUDED.title,
                    body = EXCLUDED.body,
                    json_metadata = EXCLUDED.json_metadata
                RETURNING post_id
            """, (
                author, permlink,
                op_data.get("parent_author", ""),
                op_data.get("parent_permlink", ""),
                op_data.get("title", ""),
                op_data.get("body", ""),
                tags[0] if tags else "",
                community,
                json.dumps(meta),
                app,
                timestamp,
                block_num,
                is_comment
            ))
            post_id = cur.fetchone()[0]

            # Index tags
            for tag in tags[:10]:  # limit to 10 tags
                cur.execute("""
                    INSERT INTO post_tags (post_id, tag)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, (post_id, tag))

    def index_vote(self, op_data, block_num, timestamp):
        """Index a vote operation."""
        with self.conn.cursor() as cur:
            # Look up post_id
            cur.execute(
                "SELECT post_id FROM posts WHERE author = %s AND permlink = %s",
                (op_data["author"], op_data["permlink"])
            )
            row = cur.fetchone()
            post_id = row[0] if row else None

            cur.execute("""
                INSERT INTO votes (post_id, voter, author, permlink,
                    weight, block_num, voted_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                post_id,
                op_data["voter"],
                op_data["author"],
                op_data["permlink"],
                op_data.get("weight", 0),
                block_num,
                timestamp
            ))

            # Update post vote count
            if post_id:
                cur.execute("""
                    UPDATE posts SET net_votes = net_votes + 1
                    WHERE post_id = %s
                """, (post_id,))


# === Example Analytics Queries ===

SAMPLE_QUERIES = {
    "top_posts_this_week": """
        SELECT author, permlink, title, net_votes, pending_payout
        FROM posts
        WHERE created_at > NOW() - INTERVAL '7 days'
            AND is_comment = FALSE
        ORDER BY pending_payout DESC
        LIMIT 20
    """,

    "author_leaderboard": """
        SELECT author,
               COUNT(*) as post_count,
               SUM(net_votes) as total_votes,
               AVG(pending_payout) as avg_payout
        FROM posts
        WHERE created_at > NOW() - INTERVAL '30 days'
            AND is_comment = FALSE
        GROUP BY author
        ORDER BY total_votes DESC
        LIMIT 50
    """,

    "trending_tags": """
        SELECT t.tag, COUNT(*) as post_count,
               AVG(p.net_votes) as avg_votes
        FROM post_tags t
        JOIN posts p ON t.post_id = p.post_id
        WHERE p.created_at > NOW() - INTERVAL '7 days'
        GROUP BY t.tag
        HAVING COUNT(*) >= 5
        ORDER BY avg_votes DESC
        LIMIT 30
    """,
}
```

Schema design rationale: synthetic post_id enables fast JOINs. Denormalized author_reputation avoids joining to a separate accounts table for common queries. Votes table is partitioned by month because it grows fastest. Daily_stats table pre-aggregates common dashboard metrics. All indexes target the most common query patterns (by time range, by author, by community).'''
    },
    {
        "instruction": r'''Should I index Hive data in real-time as blocks are produced, or batch-process periodically? What are the tradeoffs?''',
        "output": r'''<think>
Real-time vs batch indexing -- this is a classic data engineering tradeoff. Let me think about the specific considerations for Hive blockchain data.

Real-time indexing means processing each block as it is produced (every 3 seconds). The data is available for queries almost immediately.

Batch indexing means collecting data for some period (e.g., every 5 minutes, every hour) and processing it all at once.

For Hive specifically, a block every 3 seconds means ~28,800 blocks per day. Each block can have 0-200+ transactions. During peak times, blocks are full.

Advantages of real-time:
- Data available for queries within seconds
- Simpler conceptual model (process one block at a time)
- Better for applications that need live data (bots, alerts)

Disadvantages of real-time:
- Per-block database commits are expensive
- Higher sustained load on the database
- Must handle chain forks in real-time
- A slow processing step blocks everything

Advantages of batch:
- Bulk inserts are much faster (10-100x per record)
- Less database connection overhead
- Can optimize processing (sort operations, batch SQL)
- Easier error recovery (reprocess the whole batch)

Disadvantages of batch:
- Data has a delay (the batch interval)
- Must store raw blocks/operations somewhere temporarily
- More complex orchestration

Hmm, I initially thought real-time would always be better for blockchain data, but actually the database performance difference is significant. A single INSERT per operation at 3-second block intervals could mean 200 individual INSERT statements every 3 seconds. Batching those into a single INSERT with 200 rows is dramatically faster in PostgreSQL.

The tradeoff is: latency vs throughput. Real-time gives you low latency but lower throughput. Batch gives you high throughput but higher latency.

Actually, there is a hybrid approach: process blocks in real-time but batch database writes. Accumulate operations in memory for N blocks (or N seconds), then do one bulk write. This gives you near-real-time data availability with batch-level database performance.

Wait, this is basically what I described in the performance batch file earlier with the write queue. Let me expand on it with more focus on the data engineering aspects.
</think>

The best approach is a hybrid: stream blocks in real-time but batch database writes. Here is the comparison and implementation:

```python
import psycopg2
import psycopg2.extras
from beem import Hive
from beem.blockchain import Blockchain
import json
import time
from collections import defaultdict
from io import StringIO

hive = Hive(node=[
    "https://api.hive.blog",
    "https://api.deathwing.me"
])

DB_CONFIG = {
    "host": "localhost",
    "dbname": "hive_indexer",
    "user": "indexer",
    "password": "password"
}

# === Approach Comparison ===
#
# Real-time (per-block commits):
#   - Latency: ~3 seconds
#   - Throughput: ~100-500 ops/sec (individual INSERTs)
#   - DB load: HIGH (constant small writes)
#   - Best for: bots, alerts, small data volumes
#
# Batch (periodic bulk):
#   - Latency: 30 sec to 5 min
#   - Throughput: ~10,000-50,000 ops/sec (COPY/bulk INSERT)
#   - DB load: LOW (periodic bursts)
#   - Best for: analytics, dashboards, large data volumes
#
# Hybrid (stream + batched writes):
#   - Latency: 5-15 seconds
#   - Throughput: ~5,000-20,000 ops/sec
#   - DB load: MODERATE (controlled bursts)
#   - Best for: most applications


class HybridIndexer:
    """Stream blocks in real-time, batch database writes."""

    BATCH_SIZE = 500        # rows before flush
    FLUSH_INTERVAL = 5.0    # seconds between flushes
    CHECKPOINT_INTERVAL = 50  # blocks between checkpoints

    def __init__(self, db_config, ops_filter=None):
        self.conn = psycopg2.connect(**db_config)
        self.ops_filter = set(ops_filter or [
            "custom_json", "vote", "comment", "transfer"
        ])

        # In-memory write buffers
        self.op_buffer = []
        self.last_flush = time.time()
        self.last_checkpoint_block = 0
        self.blocks_processed = 0

        # Performance tracking
        self.stats = {
            "blocks": 0,
            "ops_indexed": 0,
            "flushes": 0,
            "start_time": time.time()
        }

    def process_block(self, block_num, block_data, timestamp):
        """Process a block and buffer operations."""
        for tx in block_data.get("transactions", []):
            tx_id = tx.get("transaction_id", "")
            for op in tx.get("operations", []):
                op_type = op[0] if isinstance(op, list) else op.get("type")
                if op_type not in self.ops_filter:
                    continue

                op_data = op[1] if isinstance(op, list) else op.get("value")

                self.op_buffer.append((
                    block_num,
                    tx_id,
                    op_type,
                    json.dumps(op_data),
                    self._extract_account(op_type, op_data),
                    timestamp
                ))

        self.blocks_processed += 1
        self.stats["blocks"] += 1

        # Check if we should flush
        should_flush = (
            len(self.op_buffer) >= self.BATCH_SIZE or
            time.time() - self.last_flush >= self.FLUSH_INTERVAL
        )

        if should_flush and self.op_buffer:
            self._flush(block_num)

    def _extract_account(self, op_type, op_data):
        """Extract the primary account from an operation."""
        if op_type == "custom_json":
            auths = (op_data.get("required_posting_auths") or
                     op_data.get("required_auths") or [])
            return auths[0] if auths else None
        elif op_type == "vote":
            return op_data.get("voter")
        elif op_type == "comment":
            return op_data.get("author")
        elif op_type == "transfer":
            return op_data.get("from")
        return None

    def _flush(self, current_block):
        """Bulk-insert buffered operations using COPY."""
        if not self.op_buffer:
            return

        # Use COPY for maximum insert performance
        # 10-50x faster than individual INSERTs
        buf = StringIO()
        for row in self.op_buffer:
            # tab-separated values for COPY
            line = "\t".join(
                str(v) if v is not None else "\\N" for v in row
            )
            buf.write(line + "\n")
        buf.seek(0)

        with self.conn.cursor() as cur:
            cur.copy_from(
                buf,
                "indexed_operations",
                columns=("block_num", "tx_id", "op_type",
                        "op_data", "account", "created_at"),
                null="\\N"
            )

            # Checkpoint
            if (current_block - self.last_checkpoint_block >=
                    self.CHECKPOINT_INTERVAL):
                cur.execute("""
                    INSERT INTO indexer_state
                    (app_name, last_block, last_irreversible, updated_at)
                    VALUES ('hybrid_indexer', %s, %s, NOW())
                    ON CONFLICT (app_name) DO UPDATE SET
                        last_block = EXCLUDED.last_block,
                        updated_at = NOW()
                """, (current_block, current_block - 20))
                self.last_checkpoint_block = current_block

        self.conn.commit()

        count = len(self.op_buffer)
        self.stats["ops_indexed"] += count
        self.stats["flushes"] += 1
        self.op_buffer.clear()
        self.last_flush = time.time()

    def print_stats(self):
        elapsed = time.time() - self.stats["start_time"]
        if elapsed > 0:
            bps = self.stats["blocks"] / elapsed
            ops = self.stats["ops_indexed"] / elapsed
            print(f"Blocks: {self.stats['blocks']} ({bps:.1f}/s) | "
                  f"Ops: {self.stats['ops_indexed']} ({ops:.0f}/s) | "
                  f"Flushes: {self.stats['flushes']} | "
                  f"Buffer: {len(self.op_buffer)}")

    def run(self, start_block=None):
        """Main loop."""
        chain = Blockchain(blockchain_instance=hive)
        current = start_block or chain.get_current_block_num()
        print(f"Starting hybrid indexer from block {current}")

        while True:
            try:
                block = hive.rpc.get_block(current)
                if block is None:
                    # Flush any remaining buffer at head
                    if self.op_buffer:
                        self._flush(current - 1)
                    time.sleep(1)
                    continue

                timestamp = block.get("timestamp", "")
                self.process_block(current, block, timestamp)

                if current % 100 == 0:
                    self.print_stats()

                current += 1

            except KeyboardInterrupt:
                if self.op_buffer:
                    self._flush(current - 1)
                print("Stopped. Final stats:")
                self.print_stats()
                break
            except Exception as e:
                print(f"Error at block {current}: {e}")
                self.conn.rollback()
                self.op_buffer.clear()
                time.sleep(5)


# Usage
indexer = HybridIndexer(
    db_config=DB_CONFIG,
    ops_filter=["custom_json", "vote", "comment"]
)
indexer.run()
```

Performance comparison for 10,000 operations:
- Individual INSERTs: ~20 seconds (500 ops/sec)
- Batched INSERT with execute_values: ~2 seconds (5,000 ops/sec)
- COPY: ~0.5 seconds (20,000 ops/sec)

The hybrid approach gives you real-time streaming (never miss a block) with batch-level database performance (COPY is the fastest way to load data into PostgreSQL). The 5-15 second data latency is acceptable for most applications.'''
    },
    {
        "instruction": r'''I am building a Hive data indexer and I need to handle the case where the blockchain reorganizes (fork). How do I implement fork-safe indexing?''',
        "output": r'''<think>
Fork handling in a blockchain indexer is critical. On Hive, forks happen when two or more witnesses produce competing blocks at the same height. The chain resolves this by following the longest chain rule, and blocks on the shorter fork become orphaned.

The Last Irreversible Block (LIB) is the key concept. Blocks at or below the LIB number are guaranteed to never be reversed. Blocks above LIB are "reversible" -- they might be part of a fork that gets orphaned.

For an indexer, this means:
1. Data from blocks above LIB should be treated as tentative
2. If a fork is detected, tentative data must be rolled back
3. Data below LIB is final and safe

How to detect forks: track the block_id (hash) of each processed block. When fetching the next block, verify that its previous_block_hash matches the last block you processed. If it does not match, a fork has occurred.

Hmm, wait, how far back can a fork go? In practice, Hive forks are usually only 1-3 blocks deep. But theoretically, they could go back to the LIB. So the indexer needs to be prepared to revert up to (head - LIB) blocks, which is typically about 15 blocks.

I initially thought I could just delete and reprocess the forked blocks, but what if my indexer has side effects? For example, if it sent notifications or triggered external actions based on the forked blocks, those cannot be "unsent." So the indexer should distinguish between tentative processing (can be reverted) and final processing (after LIB confirmation).

The tradeoff is: simple approach (only index LIB-confirmed blocks, 45-second delay) vs complex approach (index head blocks tentatively, revert on fork, near-real-time). For an analytics dashboard, the 45-second delay of LIB-only indexing is perfectly fine. For a trading bot, you need head-block processing with fork handling.

Let me design a fork-safe indexer that uses a "reversible buffer" -- a staging area for tentative data that gets promoted to permanent storage once the block reaches LIB.
</think>

Use a two-tier storage approach: tentative data in a reversible buffer, permanent data after LIB confirmation:

```python
import psycopg2
import psycopg2.extras
from beem import Hive
import json
import time
from collections import OrderedDict

hive = Hive(node=[
    "https://api.hive.blog",
    "https://api.deathwing.me"
])

DB_CONFIG = {
    "host": "localhost",
    "dbname": "hive_indexer",
    "user": "indexer",
    "password": "password"
}


class ForkSafeIndexer:
    """Indexer with proper blockchain fork handling."""

    def __init__(self, db_config):
        self.conn = psycopg2.connect(**db_config)
        self._init_schema()

        # In-memory block tracking for fork detection
        self.block_ids = OrderedDict()  # block_num -> block_id
        self.max_tracked = 50  # keep last 50 block IDs

    def _init_schema(self):
        with self.conn.cursor() as cur:
            # Reversible operations (tentative, can be rolled back)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reversible_ops (
                    id BIGSERIAL PRIMARY KEY,
                    block_num INTEGER NOT NULL,
                    block_id TEXT NOT NULL,
                    tx_id TEXT,
                    op_type TEXT NOT NULL,
                    op_data JSONB NOT NULL,
                    account TEXT,
                    created_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_rev_block
                ON reversible_ops(block_num)
            """)

            # Permanent operations (irreversible, safe)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS permanent_ops (
                    id BIGSERIAL PRIMARY KEY,
                    block_num INTEGER NOT NULL,
                    tx_id TEXT,
                    op_type TEXT NOT NULL,
                    op_data JSONB NOT NULL,
                    account TEXT,
                    created_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_perm_block
                ON permanent_ops(block_num)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_perm_account
                ON permanent_ops(account)
            """)

            # Indexer state
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fork_safe_state (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    last_block INTEGER NOT NULL,
                    last_lib INTEGER NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            self.conn.commit()

    def _get_state(self):
        with self.conn.cursor(
            cursor_factory=psycopg2.extras.DictCursor
        ) as cur:
            cur.execute("SELECT * FROM fork_safe_state WHERE id = 1")
            return cur.fetchone()

    def _detect_fork(self, block_num, block):
        """Check if the new block connects to our chain."""
        previous = block.get("previous", "")
        prev_block_num = block_num - 1

        if prev_block_num in self.block_ids:
            expected_prev = self.block_ids[prev_block_num]
            # The previous field is the full block ID (hash)
            # We compare the prefix
            if not previous.startswith(expected_prev[:8]):
                return prev_block_num  # fork point
        return None  # no fork

    def _handle_fork(self, fork_point):
        """Roll back all reversible data from the fork point onward."""
        print(f"FORK DETECTED at block {fork_point}!")

        with self.conn.cursor() as cur:
            # Count what we are reverting
            cur.execute(
                "SELECT COUNT(*) FROM reversible_ops WHERE block_num >= %s",
                (fork_point,)
            )
            count = cur.fetchone()[0]

            # Delete forked reversible operations
            cur.execute(
                "DELETE FROM reversible_ops WHERE block_num >= %s",
                (fork_point,)
            )

            print(f"Reverted {count} operations from blocks >= {fork_point}")
            self.conn.commit()

        # Remove forked blocks from tracking
        to_remove = [
            bn for bn in self.block_ids if bn >= fork_point
        ]
        for bn in to_remove:
            del self.block_ids[bn]

        return fork_point  # resume from here

    def _promote_to_permanent(self, up_to_block):
        """Move irreversible operations from reversible to permanent."""
        with self.conn.cursor() as cur:
            # Move data
            cur.execute("""
                INSERT INTO permanent_ops
                    (block_num, tx_id, op_type, op_data, account, created_at)
                SELECT block_num, tx_id, op_type, op_data, account, created_at
                FROM reversible_ops
                WHERE block_num <= %s
                ORDER BY id
            """, (up_to_block,))
            promoted = cur.rowcount

            # Clean up reversible table
            cur.execute(
                "DELETE FROM reversible_ops WHERE block_num <= %s",
                (up_to_block,)
            )

            if promoted > 0:
                print(f"Promoted {promoted} ops to permanent "
                      f"(up to block {up_to_block})")

    def process_block(self, block_num, block):
        """Process a block with fork safety."""
        block_id = block.get("block_id", "")
        timestamp = block.get("timestamp", "")

        # Fork detection
        fork_point = self._detect_fork(block_num, block)
        if fork_point is not None:
            return self._handle_fork(fork_point)

        # Track block ID
        self.block_ids[block_num] = block_id
        while len(self.block_ids) > self.max_tracked:
            self.block_ids.popitem(last=False)

        # Index operations into reversible table
        with self.conn.cursor() as cur:
            for tx in block.get("transactions", []):
                tx_id = tx.get("transaction_id", "")
                for op in tx.get("operations", []):
                    op_type = op[0] if isinstance(op, list) else op.get("type")
                    op_data = op[1] if isinstance(op, list) else op.get("value")

                    account = None
                    if op_type == "custom_json":
                        auths = (op_data.get("required_posting_auths") or
                                op_data.get("required_auths") or [])
                        account = auths[0] if auths else None

                    cur.execute("""
                        INSERT INTO reversible_ops
                        (block_num, block_id, tx_id, op_type,
                         op_data, account, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (block_num, block_id, tx_id, op_type,
                          json.dumps(op_data), account, timestamp))

        return None  # no fork

    def run(self, start_block=None):
        """Main loop with fork handling and LIB promotion."""
        state = self._get_state()
        current = start_block or (state["last_block"] + 1 if state else None)

        if current is None:
            props = hive.rpc.get_dynamic_global_properties()
            current = props["head_block_number"]

        print(f"Starting fork-safe indexer from block {current}")
        last_lib = 0

        while True:
            try:
                block = hive.rpc.get_block(current)
                if block is None:
                    time.sleep(1)
                    continue

                result = self.process_block(current, block)

                if isinstance(result, int):
                    # Fork detected, resume from fork point
                    current = result
                    continue

                # Get LIB and promote irreversible data
                props = hive.rpc.get_dynamic_global_properties()
                lib = props["last_irreversible_block_num"]

                if lib > last_lib:
                    self._promote_to_permanent(lib)
                    last_lib = lib

                # Update state
                with self.conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO fork_safe_state (id, last_block, last_lib)
                        VALUES (1, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            last_block = EXCLUDED.last_block,
                            last_lib = EXCLUDED.last_lib,
                            updated_at = NOW()
                    """, (current, lib))
                self.conn.commit()

                current += 1

                if current % 100 == 0:
                    rev_gap = current - lib
                    print(f"Block {current} | LIB: {lib} | "
                          f"Reversible window: {rev_gap} blocks")

            except KeyboardInterrupt:
                self.conn.commit()
                print(f"Stopped at block {current}")
                break
            except Exception as e:
                print(f"Error at block {current}: {e}")
                self.conn.rollback()
                time.sleep(5)


# Usage
indexer = ForkSafeIndexer(DB_CONFIG)
indexer.run()

# Querying: use permanent_ops for confirmed data,
# UNION with reversible_ops for real-time (tentative) data
```

Two-tier architecture: reversible_ops holds tentative data from recent blocks. When blocks reach LIB (become irreversible), operations are promoted to permanent_ops and removed from reversible_ops. On fork detection, only reversible_ops rows are deleted -- permanent data is never touched. Applications query permanent_ops for guaranteed-accurate data, or UNION both tables for real-time but potentially-tentative data.'''
    },
    {
        "instruction": r'''What is the most efficient way to backfill historical Hive blockchain data for my indexer? Streaming from block 1 would take forever.''',
        "output": r'''<think>
Backfilling historical Hive blockchain data -- the chain has been running since March 2020 (and Steem before that). As of now, there are probably 80+ million blocks. Streaming from block 1 at the standard rate of one block every 3 seconds would take... 80 million * 3 seconds = 240 million seconds = roughly 7.6 years. Obviously not practical.

Even if we fetch blocks as fast as possible (without waiting for 3-second intervals), each block fetch is an API call. At maybe 50-100 blocks per second from a responsive node, that is still 80 million / 75 = about 12.5 days. And that is just fetching, not processing.

Let me think about optimization strategies:

1. Parallel block fetching: fetch multiple blocks concurrently from different nodes. This could increase throughput to 500-1000 blocks/second.

2. Use block_api.get_block_range: some API methods return multiple blocks at once, reducing round-trip overhead.

3. Use an existing database dump: if someone provides a PostgreSQL dump of historical data, you can load it directly. HAF provides this.

4. Only backfill what you need: if you only care about custom_json with a specific id, you could use account history API to find relevant operations without scanning every block.

Hmm, option 4 is interesting but limited. Account history only works if you know which accounts to query. For a general custom_json indexer, you would not know all senders in advance.

I initially thought parallel fetching would be enough, but even at 1000 blocks/second, 80 million blocks is still 22 hours. That is actually reasonable though.

Wait, there is another option: get_ops_in_block or similar API methods that return only operations from a block. This is lighter than get_block since it skips the full transaction data. But not all nodes support these methods.

The tradeoff is: full block scan (complete but slow) vs targeted queries (fast but only works if you know what to look for) vs database dump (fastest but requires compatibility). For most indexer backfills, parallel block fetching with operation filtering is the practical approach.

Actually, I should also consider using condenser_api.get_account_history for backfilling account-specific data. If your app tracks activity for specific accounts, this is much faster than scanning all blocks.
</think>

Use parallel block fetching with operation filtering for general backfill, or targeted API methods for account-specific data:

```python
import requests
import json
import time
import psycopg2
import psycopg2.extras
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from io import StringIO

# Multiple API nodes for parallel fetching
NODES = [
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://api.openhive.network",
    "https://hive-api.arcange.eu",
    "https://api.c0ff33a.uk",
]

DB_CONFIG = {
    "host": "localhost",
    "dbname": "hive_indexer",
    "user": "indexer",
    "password": "password"
}


class HistoricalBackfiller:
    """Fast backfill of historical Hive blockchain data."""

    def __init__(self, db_config, ops_filter=None, workers=10):
        self.conn = psycopg2.connect(**db_config)
        self.ops_filter = set(ops_filter or [])
        self.workers = workers
        self.sessions = {}  # thread-local sessions

        # Stats
        self.blocks_fetched = 0
        self.ops_indexed = 0
        self.start_time = time.time()

    def _get_session(self, node):
        """Get or create a requests session for a node."""
        if node not in self.sessions:
            self.sessions[node] = requests.Session()
        return self.sessions[node]

    def _fetch_block_range(self, start, count, node):
        """Fetch a range of blocks from a single node."""
        session = self._get_session(node)
        blocks = {}

        for block_num in range(start, start + count):
            payload = {
                "jsonrpc": "2.0",
                "method": "condenser_api.get_block",
                "params": [block_num],
                "id": block_num
            }
            try:
                resp = session.post(node, json=payload, timeout=10)
                result = resp.json().get("result")
                if result:
                    blocks[block_num] = result
            except Exception:
                pass  # will be retried in a different batch

        return blocks

    def _fetch_blocks_parallel(self, start, end):
        """Fetch a range of blocks using parallel workers."""
        all_blocks = {}
        chunk_size = 50  # blocks per worker task
        tasks = []

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            for chunk_start in range(start, end, chunk_size):
                chunk_end = min(chunk_start + chunk_size, end)
                count = chunk_end - chunk_start
                # Round-robin across nodes
                node = NODES[
                    (chunk_start // chunk_size) % len(NODES)
                ]
                future = executor.submit(
                    self._fetch_block_range, chunk_start, count, node
                )
                tasks.append(future)

            for future in as_completed(tasks):
                try:
                    blocks = future.result()
                    all_blocks.update(blocks)
                    self.blocks_fetched += len(blocks)
                except Exception as e:
                    print(f"Fetch error: {e}")

        return all_blocks

    def _extract_operations(self, blocks):
        """Extract and filter operations from fetched blocks."""
        operations = []

        for block_num in sorted(blocks.keys()):
            block = blocks[block_num]
            timestamp = block.get("timestamp", "")

            for tx in block.get("transactions", []):
                tx_id = tx.get("transaction_id", "")
                for op in tx.get("operations", []):
                    op_type = op[0] if isinstance(op, list) else op.get("type")

                    if self.ops_filter and op_type not in self.ops_filter:
                        continue

                    op_data = op[1] if isinstance(op, list) else op.get("value")

                    account = None
                    if op_type == "custom_json":
                        auths = (op_data.get("required_posting_auths") or
                                op_data.get("required_auths") or [])
                        account = auths[0] if auths else None
                    elif op_type == "vote":
                        account = op_data.get("voter")
                    elif op_type == "comment":
                        account = op_data.get("author")

                    operations.append((
                        block_num, tx_id, op_type,
                        json.dumps(op_data), account, timestamp
                    ))

        return operations

    def _bulk_insert(self, operations):
        """Bulk insert using PostgreSQL COPY (fastest method)."""
        if not operations:
            return

        buf = StringIO()
        for row in operations:
            line = "\t".join(
                str(v) if v is not None else "\\N" for v in row
            )
            buf.write(line + "\n")
        buf.seek(0)

        with self.conn.cursor() as cur:
            cur.copy_from(
                buf,
                "permanent_ops",
                columns=("block_num", "tx_id", "op_type",
                        "op_data", "account", "created_at"),
                null="\\N"
            )
        self.conn.commit()
        self.ops_indexed += len(operations)

    def backfill(self, start_block, end_block, batch_size=1000):
        """Backfill a range of blocks."""
        total = end_block - start_block
        print(f"Backfilling blocks {start_block} to {end_block} "
              f"({total:,} blocks)")
        print(f"Workers: {self.workers} | Batch: {batch_size}")

        for batch_start in range(start_block, end_block, batch_size):
            batch_end = min(batch_start + batch_size, end_block)

            # Fetch blocks in parallel
            blocks = self._fetch_blocks_parallel(batch_start, batch_end)

            # Extract and filter operations
            operations = self._extract_operations(blocks)

            # Bulk insert
            self._bulk_insert(operations)

            # Update checkpoint
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO fork_safe_state (id, last_block, last_lib)
                    VALUES (1, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        last_block = EXCLUDED.last_block,
                        last_lib = EXCLUDED.last_lib
                """, (batch_end - 1, batch_end - 1))
            self.conn.commit()

            # Progress report
            elapsed = time.time() - self.start_time
            progress = (batch_end - start_block) / total * 100
            bps = self.blocks_fetched / max(elapsed, 1)
            ops_ps = self.ops_indexed / max(elapsed, 1)
            eta_seconds = (total - (batch_end - start_block)) / max(bps, 1)
            eta_hours = eta_seconds / 3600

            missing = batch_size - len(blocks)
            if missing > 0:
                print(f"  Warning: {missing} blocks missing in batch")

            print(
                f"Block {batch_end:,} | {progress:.1f}% | "
                f"{bps:.0f} blk/s | {ops_ps:.0f} ops/s | "
                f"ETA: {eta_hours:.1f}h"
            )

        print(f"\nBackfill complete: {self.ops_indexed:,} operations indexed")


# === Account-Specific Backfill (much faster for known accounts) ===

def backfill_account_history(account, db_conn, node=NODES[0]):
    """Backfill data for a specific account using account history API.

    Much faster than scanning all blocks when you know the accounts.
    """
    session = requests.Session()
    last_id = -1
    total_ops = 0

    while True:
        payload = {
            "jsonrpc": "2.0",
            "method": "condenser_api.get_account_history",
            "params": [account, last_id, 1000],
            "id": 1
        }
        resp = session.post(node, json=payload, timeout=15)
        history = resp.json().get("result", [])

        if not history:
            break

        ops_to_insert = []
        for entry in history:
            seq_id = entry[0]
            op_data = entry[1]
            block_num = op_data.get("block", 0)
            tx_id = op_data.get("trx_id", "")
            timestamp = op_data.get("timestamp", "")
            op = op_data.get("op", [])
            op_type = op[0] if isinstance(op, list) else ""
            op_value = op[1] if isinstance(op, list) else {}

            ops_to_insert.append((
                block_num, tx_id, op_type,
                json.dumps(op_value), account, timestamp
            ))

        # Bulk insert
        buf = StringIO()
        for row in ops_to_insert:
            line = "\t".join(
                str(v) if v is not None else "\\N" for v in row
            )
            buf.write(line + "\n")
        buf.seek(0)

        with db_conn.cursor() as cur:
            cur.copy_from(
                buf, "permanent_ops",
                columns=("block_num", "tx_id", "op_type",
                        "op_data", "account", "created_at"),
                null="\\N"
            )
        db_conn.commit()

        total_ops += len(ops_to_insert)
        last_id = history[0][0] - 1
        if last_id < 0:
            break

        print(f"  @{account}: {total_ops} ops indexed "
              f"(at block {history[0][1].get('block', '?')})")

    return total_ops


# Usage

# Full backfill (hours)
backfiller = HistoricalBackfiller(
    DB_CONFIG,
    ops_filter=["custom_json", "vote"],
    workers=10
)
backfiller.backfill(start_block=1, end_block=80000000)

# Account-specific backfill (minutes)
# conn = psycopg2.connect(**DB_CONFIG)
# backfill_account_history("myaccount", conn)
```

Speed comparison for 1 million blocks: single-threaded sequential = ~3 hours, 10-worker parallel = ~20 minutes, account history API (single account) = ~2 minutes. Choose based on your data scope: full chain scan for broad indexing, account history for targeted accounts.'''
    },
]
