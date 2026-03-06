"""beem Python Library — streaming, vote bots, account analysis, witness ops, scheduled posting.

Covers the beem library (v0.24+) for Hive blockchain interaction from Python.
"""

PAIRS = [
    (
        "hive/development",
        r'''How do I stream real-time blockchain operations from Hive using the beem Python library? I need to monitor specific operations like transfers, votes, and custom_json in real time.''',
        r'''## Streaming Hive Blockchain Operations with beem

The beem library provides a powerful streaming interface that connects to a Hive API node and processes operations block by block in real time. This is the foundation for building bots, analytics pipelines, and reactive applications.

### Core Concepts

- **Blockchain.stream()** yields operations as they appear in new blocks (every 3 seconds on Hive)
- You can filter by operation type to reduce processing overhead
- Streaming is sequential — each block is processed in order for consistency
- Node failover is handled by beem's built-in node rotation

### Basic Stream — Watch All Transfers

```python
from beem import Hive
from beem.blockchain import Blockchain
from datetime import datetime

# Connect to Hive (no keys needed for read-only streaming)
hive = Hive(node=[
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://anyx.io",
])

blockchain = Blockchain(blockchain_instance=hive)

def stream_transfers():
    """Stream all HIVE/HBD transfers in real time."""
    print(f"Starting transfer stream at block {blockchain.get_current_block_num()}")

    # stream() yields individual operations from each block
    for op in blockchain.stream(opNames=["transfer"]):
        amount = op.get("amount", "")
        sender = op["from"]
        receiver = op["to"]
        memo = op.get("memo", "")
        block = op.get("block_num", "?")

        # Truncate memo for display (memos starting with # are encrypted)
        display_memo = memo[:50] + "..." if len(memo) > 50 else memo
        if memo.startswith("#"):
            display_memo = "[encrypted]"

        print(f"[Block {block}] @{sender} -> @{receiver}: {amount}")
        if display_memo:
            print(f"  Memo: {display_memo}")

stream_transfers()
```

### Production Multi-Operation Stream with Error Recovery

```python
from beem import Hive
from beem.blockchain import Blockchain
from beem.exceptions import NodeException, NumRetriesReached
import json
import time
import logging
import signal
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("hive_stream")


class HiveOperationStream:
    """Production-grade Hive blockchain operation streamer with error recovery."""

    def __init__(self, nodes=None, state_file="stream_state.json"):
        self.nodes = nodes or [
            "https://api.hive.blog",
            "https://api.deathwing.me",
            "https://anyx.io",
            "https://hive-api.arcange.eu",
        ]
        self.state_file = state_file
        self.running = True
        self.handlers = {}
        self.stats = {"blocks_processed": 0, "ops_processed": 0, "errors": 0}

        # Graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        logger.info("Shutdown signal received, finishing current block...")
        self.running = False

    def on(self, op_type, handler):
        """Register a handler for a specific operation type."""
        if op_type not in self.handlers:
            self.handlers[op_type] = []
        self.handlers[op_type].append(handler)
        return self  # Allow chaining

    def _load_last_block(self):
        """Resume from last processed block."""
        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
                return state.get("last_block", None)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _save_last_block(self, block_num):
        """Persist progress for crash recovery."""
        with open(self.state_file, "w") as f:
            json.dump({"last_block": block_num, "updated": time.time()}, f)

    def run(self, start_block=None):
        """Main streaming loop with automatic reconnection."""
        # Determine start block
        if start_block is None:
            start_block = self._load_last_block()

        op_names = list(self.handlers.keys()) if self.handlers else None
        retry_delay = 1

        while self.running:
            try:
                hive = Hive(node=self.nodes)
                blockchain = Blockchain(blockchain_instance=hive)

                if start_block:
                    logger.info(f"Resuming from block {start_block}")
                else:
                    start_block = blockchain.get_current_block_num()
                    logger.info(f"Starting from current block {start_block}")

                for op in blockchain.stream(
                    opNames=op_names,
                    start=start_block,
                    max_batch_size=50,
                    threading=False,
                    raw_ops=False,
                ):
                    if not self.running:
                        break

                    op_type = op.get("type", "")
                    block_num = op.get("block_num", 0)

                    # Dispatch to registered handlers
                    for handler in self.handlers.get(op_type, []):
                        try:
                            handler(op)
                        except Exception as e:
                            logger.error(f"Handler error for {op_type}: {e}")
                            self.stats["errors"] += 1

                    self.stats["ops_processed"] += 1

                    # Save checkpoint every 100 blocks
                    if block_num > start_block and block_num % 100 == 0:
                        self._save_last_block(block_num)
                        start_block = block_num
                        self.stats["blocks_processed"] = block_num
                        logger.info(
                            f"Checkpoint: block {block_num}, "
                            f"ops: {self.stats['ops_processed']}, "
                            f"errors: {self.stats['errors']}"
                        )

                retry_delay = 1  # Reset on success

            except (NodeException, NumRetriesReached) as e:
                logger.warning(f"Node error: {e}. Reconnecting in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)  # Exponential backoff

            except Exception as e:
                logger.error(f"Unexpected error: {e}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

        # Final checkpoint
        if start_block:
            self._save_last_block(start_block)
        logger.info(f"Stream stopped. Stats: {self.stats}")


# ---- Usage: Multi-purpose stream ----

def handle_transfer(op):
    amount = op.get("amount", {})
    if isinstance(amount, dict):
        value = f"{amount['amount']} {amount['nai']}"
    else:
        value = str(amount)
    logger.info(f"Transfer: @{op['from']} -> @{op['to']}: {value}")

def handle_vote(op):
    weight = op.get("weight", 0) / 100  # Convert to percentage
    logger.info(f"Vote: @{op['voter']} -> @{op['author']}/{op['permlink']} ({weight}%)")

def handle_custom_json(op):
    json_id = op.get("id", "")
    if json_id == "ssc-mainnet-hive":
        try:
            payload = json.loads(op["json"])
            action = payload.get("contractAction", "unknown")
            logger.info(f"Hive Engine: {action} by @{op.get('required_auths', ['?'])[0]}")
        except json.JSONDecodeError:
            pass

def handle_comment(op):
    if op.get("parent_author", "") == "":
        # Top-level post
        logger.info(f"New post: @{op['author']}/{op['permlink']}: {op.get('title', '')[:60]}")


stream = HiveOperationStream()
stream.on("transfer", handle_transfer)
stream.on("vote", handle_vote)
stream.on("custom_json", handle_custom_json)
stream.on("comment", handle_comment)

stream.run()
```

### Key Notes

1. **Block time**: Hive produces blocks every 3 seconds, so expect ~20 operations/second on average but spikes up to hundreds during high activity.
2. **Node selection**: Use multiple nodes for failover. Nodes like `api.deathwing.me` tend to be fast; `api.hive.blog` is the official node.
3. **start parameter**: When resuming, always persist and restore the last processed block number. Without this, you either miss operations or reprocess them.
4. **Memory**: Streaming indefinitely is fine — beem processes one operation at a time and does not accumulate memory.
5. **raw_ops=False**: Gives you parsed, human-readable operation dicts. Set `True` for raw protocol format if you need maximum performance.
'''
    ),
    (
        "hive/development",
        r'''How do I build a curation vote bot using beem that votes on posts within optimal curation windows, manages voting power, and follows author whitelists?''',
        r'''## Building a Curation Vote Bot with beem

A curation bot monitors new posts and votes on content from selected authors at optimal timing, while managing voting power to stay sustainable. Since HF25, the curation reward curve is linear — there is no early-voter penalty, but strategic voting still matters for maximizing returns.

### Key Concepts

- **Voting mana**: Regenerates 20% per day. Full vote costs 2% of max mana. At 50% vote weight, costs 1%.
- **Curation rewards**: 50% of post rewards go to curators, distributed by rshares proportion.
- **Vote timing**: No penalty for early votes (post-HF25), but voting before whale votes means your rshares proportion is higher.
- **Dust threshold**: Very small votes may be below dust and earn zero curation.

### Production Curation Bot

```python
from beem import Hive
from beem.blockchain import Blockchain
from beem.account import Account
from beem.comment import Comment
from beem.exceptions import ContentDoesNotExistsException
import json
import time
import threading
import logging
from datetime import datetime, timedelta
from collections import deque

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("curation_bot")


class CurationBot:
    """Automated curation bot with voting power management and author whitelist."""

    def __init__(self, config):
        self.hive = Hive(
            node=config.get("nodes", [
                "https://api.hive.blog",
                "https://api.deathwing.me",
            ]),
            keys=[config["posting_key"]],
        )
        self.account_name = config["account"]
        self.whitelist = set(config.get("whitelist", []))
        self.tag_whitelist = set(config.get("tag_whitelist", []))

        # Voting parameters
        self.default_weight = config.get("default_vote_weight", 100)  # percent
        self.min_voting_power = config.get("min_voting_power", 80)    # percent
        self.vote_delay_minutes = config.get("vote_delay_minutes", 0) # minutes after post
        self.max_votes_per_day = config.get("max_votes_per_day", 20)
        self.author_weights = config.get("author_weights", {})  # per-author weights

        # Rate limiting
        self.vote_cooldown = 3.5  # seconds between votes
        self.last_vote_time = 0
        self.votes_today = deque()  # timestamps of votes in last 24h
        self.pending_votes = []     # (vote_time, author, permlink, weight)

        self.running = True

    def get_voting_power(self):
        """Calculate current voting mana percentage."""
        acc = Account(self.account_name, blockchain_instance=self.hive)
        vp = acc.get_voting_power()
        return round(vp, 2)

    def get_effective_vote_value(self, weight_percent=100):
        """Estimate the dollar value of a vote at given weight."""
        acc = Account(self.account_name, blockchain_instance=self.hive)
        vp = acc.get_voting_power()
        vote_value = acc.get_vote_value(weight=weight_percent)
        return round(vote_value, 4)

    def should_vote(self, author, tags):
        """Determine if this post should receive a vote."""
        # Check author whitelist
        if self.whitelist and author not in self.whitelist:
            return False, "author not in whitelist"

        # Check tag whitelist (if configured)
        if self.tag_whitelist:
            if not self.tag_whitelist.intersection(set(tags)):
                return False, "no matching tags"

        # Check daily vote budget
        now = time.time()
        # Clean old entries
        while self.votes_today and self.votes_today[0] < now - 86400:
            self.votes_today.popleft()
        if len(self.votes_today) >= self.max_votes_per_day:
            return False, f"daily limit reached ({self.max_votes_per_day})"

        # Check voting power
        vp = self.get_voting_power()
        if vp < self.min_voting_power:
            regen_hours = (self.min_voting_power - vp) / 20 * 24
            return False, f"VP too low ({vp}%), regen in {regen_hours:.1f}h"

        return True, "ok"

    def get_vote_weight(self, author):
        """Get vote weight for a specific author."""
        return self.author_weights.get(author, self.default_weight)

    def schedule_vote(self, author, permlink, weight):
        """Schedule a vote with the configured delay."""
        vote_time = time.time() + (self.vote_delay_minutes * 60)
        self.pending_votes.append((vote_time, author, permlink, weight))
        delay_str = f"{self.vote_delay_minutes}min" if self.vote_delay_minutes > 0 else "now"
        logger.info(f"Scheduled vote: @{author}/{permlink[:30]}... ({weight}%) in {delay_str}")

    def execute_vote(self, author, permlink, weight):
        """Execute a single vote with error handling."""
        # Enforce cooldown
        elapsed = time.time() - self.last_vote_time
        if elapsed < self.vote_cooldown:
            time.sleep(self.vote_cooldown - elapsed)

        try:
            comment = Comment(f"@{author}/{permlink}", blockchain_instance=self.hive)

            # Verify post is still within payout window
            if comment.is_pending():
                comment.upvote(weight=weight, voter=self.account_name)
                self.last_vote_time = time.time()
                self.votes_today.append(time.time())

                vp_after = self.get_voting_power()
                logger.info(
                    f"VOTED {weight}% on @{author}/{permlink[:30]}... | VP: {vp_after}%"
                )
                return True
            else:
                logger.warning(f"Post @{author}/{permlink} past payout window, skipping")
                return False

        except ContentDoesNotExistsException:
            logger.warning(f"Post @{author}/{permlink} not found (deleted?)")
            return False
        except Exception as e:
            msg = str(e)
            if "rc_plugin_exception" in msg:
                logger.error("Insufficient RC — pausing for 1 hour")
                time.sleep(3600)
            elif "already voted" in msg.lower():
                logger.warning(f"Already voted on @{author}/{permlink}")
            elif "HIVE_MIN_VOTE_INTERVAL" in msg:
                logger.warning("Vote interval too short, retrying in 5s")
                time.sleep(5)
                return self.execute_vote(author, permlink, weight)
            else:
                logger.error(f"Vote failed: {e}")
            return False

    def process_pending_votes(self):
        """Process scheduled votes that are due."""
        now = time.time()
        due = [v for v in self.pending_votes if v[0] <= now]
        remaining = [v for v in self.pending_votes if v[0] > now]
        self.pending_votes = remaining

        for vote_time, author, permlink, weight in due:
            if self.running:
                self.execute_vote(author, permlink, weight)

    def run(self):
        """Main bot loop — stream new posts and vote on matching content."""
        blockchain = Blockchain(blockchain_instance=self.hive)
        logger.info(f"Curation bot started for @{self.account_name}")
        logger.info(f"Whitelist: {self.whitelist or 'ALL AUTHORS'}")
        logger.info(f"VP threshold: {self.min_voting_power}%")

        # Background thread for pending votes
        def vote_processor():
            while self.running:
                self.process_pending_votes()
                time.sleep(1)

        processor = threading.Thread(target=vote_processor, daemon=True)
        processor.start()

        try:
            for op in blockchain.stream(opNames=["comment"]):
                if not self.running:
                    break

                # Only top-level posts (not replies)
                if op.get("parent_author", "") != "":
                    continue

                author = op["author"]
                permlink = op["permlink"]

                # Parse tags from metadata
                try:
                    metadata = json.loads(op.get("json_metadata", "{}"))
                    tags = metadata.get("tags", [])
                except (json.JSONDecodeError, TypeError):
                    tags = []

                should, reason = self.should_vote(author, tags)
                if should:
                    weight = self.get_vote_weight(author)
                    self.schedule_vote(author, permlink, weight)
                else:
                    logger.debug(f"Skip @{author}/{permlink[:20]}: {reason}")

        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        finally:
            self.running = False


# ---- Configuration and launch ----

config = {
    "account": "mycurator",
    "posting_key": "5Kexample_YOUR_POSTING_KEY_HERE",
    "nodes": ["https://api.hive.blog", "https://api.deathwing.me"],

    "whitelist": ["author1", "author2", "author3"],
    "tag_whitelist": ["hive-dev", "programming", "python"],

    "default_vote_weight": 50,    # 50% default
    "min_voting_power": 85,       # Don't vote below 85% VP
    "vote_delay_minutes": 0,      # Vote immediately (no curation window needed post-HF25)
    "max_votes_per_day": 15,

    "author_weights": {
        "author1": 100,  # Full vote for top author
        "author2": 75,
        "author3": 50,
    },
}

bot = CurationBot(config)
bot.run()
```

### Key Notes

1. **HF25 curation**: There is no 5-minute curation penalty anymore. Voting immediately is fine. The only consideration is whether you want to read the content first.
2. **Vote value**: A 100% vote from an account with 1000 HP is worth approximately $0.01-0.05 depending on HIVE price and reward pool state.
3. **Sustainability**: At 15 votes/day with 50% weight, you consume about 15% VP daily — sustainable with 20% daily regen.
4. **RC cost**: Votes are very cheap in RC. Even low-HP accounts can vote frequently.
5. **Legal note**: Automated voting is common and accepted on Hive, but vote-selling schemes or coordinated abuse can lead to community downvotes.
'''
    ),
    (
        "hive/development",
        r'''How do I analyze Hive account history using beem? I need to build reports on an account's posting frequency, earnings, voting patterns, and delegation history.''',
        r'''## Hive Account History Analysis with beem

Account history on Hive contains every operation that affected an account — posts, votes, transfers, delegations, and more. Using beem, you can iterate through this history to build comprehensive analytics reports.

### Core Concepts

- **Account history** is an append-only log of every operation involving the account
- Operations are indexed sequentially — newest have the highest index
- History can be very large for active accounts (millions of operations)
- Each entry contains the operation type, data, timestamp, block number, and transaction ID

### Basic Account History Scan

```python
from beem import Hive
from beem.account import Account
from datetime import datetime, timedelta
from collections import defaultdict

hive = Hive(node=[
    "https://api.hive.blog",
    "https://api.deathwing.me",
])

def get_recent_history(account_name, days=30):
    """Get account operations from the last N days."""
    account = Account(account_name, blockchain_instance=hive)
    cutoff = datetime.utcnow() - timedelta(days=days)

    ops_by_type = defaultdict(list)

    for op in account.history_reverse(only_ops=[
        "comment", "vote", "transfer", "curation_reward",
        "author_reward", "delegate_vesting_shares",
    ]):
        timestamp = datetime.strptime(op["timestamp"], "%Y-%m-%dT%H:%M:%S")
        if timestamp < cutoff:
            break

        op["_parsed_time"] = timestamp
        ops_by_type[op["type"]].append(op)

    return ops_by_type


# Quick summary
history = get_recent_history("blocktrades", days=7)
for op_type, ops in history.items():
    print(f"{op_type}: {len(ops)} operations")
```

### Production Account Analytics Report Generator

```python
from beem import Hive
from beem.account import Account
from beem.amount import Amount
from datetime import datetime, timedelta
from collections import defaultdict
import json

hive = Hive(node=[
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://anyx.io",
])


class HiveAccountAnalyzer:
    """Comprehensive account history analysis and reporting."""

    def __init__(self, account_name, days=30):
        self.account = Account(account_name, blockchain_instance=hive)
        self.account_name = account_name
        self.days = days
        self.cutoff = datetime.utcnow() - timedelta(days=days)
        self._history = None

    def _load_history(self):
        """Load and cache all relevant history."""
        if self._history is not None:
            return self._history

        history = defaultdict(list)
        count = 0

        for op in self.account.history_reverse():
            timestamp = datetime.strptime(op["timestamp"], "%Y-%m-%dT%H:%M:%S")
            if timestamp < self.cutoff:
                break

            op["_time"] = timestamp
            history[op["type"]].append(op)
            count += 1

            if count % 5000 == 0:
                print(f"  Loaded {count} operations...")

        print(f"  Total: {count} operations in {self.days} days")
        self._history = history
        return history

    def posting_report(self):
        """Analyze posting frequency and engagement."""
        history = self._load_history()
        comments = history.get("comment", [])

        posts = [c for c in comments if c.get("parent_author", "") == ""]
        replies = [c for c in comments if c.get("parent_author", "") != ""]

        # Posting frequency by day of week
        day_counts = defaultdict(int)
        hour_counts = defaultdict(int)
        for post in posts:
            day_counts[post["_time"].strftime("%A")] += 1
            hour_counts[post["_time"].hour] += 1

        # Tag analysis
        tag_counts = defaultdict(int)
        for post in posts:
            try:
                meta = json.loads(post.get("json_metadata", "{}"))
                for tag in meta.get("tags", []):
                    tag_counts[tag] += 1
            except (json.JSONDecodeError, TypeError):
                pass

        top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:10]

        return {
            "total_posts": len(posts),
            "total_replies": len(replies),
            "posts_per_day": round(len(posts) / max(self.days, 1), 2),
            "replies_per_day": round(len(replies) / max(self.days, 1), 2),
            "posts_by_day_of_week": dict(day_counts),
            "posts_by_hour_utc": dict(hour_counts),
            "top_tags": top_tags,
        }

    def earnings_report(self):
        """Analyze author and curation rewards."""
        history = self._load_history()

        author_rewards = history.get("author_reward", [])
        curation_rewards = history.get("curation_reward", [])

        # Author rewards
        total_hbd = 0.0
        total_hive = 0.0
        total_vests = 0.0

        for reward in author_rewards:
            total_hbd += float(Amount(reward.get("hbd_payout", "0.000 HBD")))
            total_hive += float(Amount(reward.get("hive_payout", "0.000 HIVE")))
            total_vests += float(Amount(reward.get("vesting_payout", "0.000000 VESTS")))

        # Curation rewards (paid in VESTS)
        total_curation_vests = 0.0
        curation_by_author = defaultdict(float)
        for reward in curation_rewards:
            vests = float(Amount(reward.get("reward", "0.000000 VESTS")))
            total_curation_vests += vests
            author = reward.get("comment_author", "unknown")
            curation_by_author[author] += vests

        top_curation_authors = sorted(
            curation_by_author.items(), key=lambda x: -x[1]
        )[:10]

        return {
            "author_rewards": {
                "hbd_earned": round(total_hbd, 3),
                "hive_earned": round(total_hive, 3),
                "vests_earned": round(total_vests, 6),
                "total_payouts": len(author_rewards),
            },
            "curation_rewards": {
                "total_vests": round(total_curation_vests, 6),
                "total_curation_events": len(curation_rewards),
                "top_curated_authors": [
                    {"author": a, "vests": round(v, 6)} for a, v in top_curation_authors
                ],
            },
        }

    def voting_report(self):
        """Analyze voting patterns."""
        history = self._load_history()
        votes = history.get("vote", [])

        votes_cast = [v for v in votes if v.get("voter") == self.account_name]
        votes_received = [v for v in votes if v.get("author") == self.account_name]

        # Vote weight distribution
        weight_buckets = defaultdict(int)
        voted_authors = defaultdict(int)
        for vote in votes_cast:
            weight = vote.get("weight", 0) / 100  # Convert to percentage
            bucket = f"{int(weight // 10) * 10}-{int(weight // 10) * 10 + 10}%"
            weight_buckets[bucket] += 1
            voted_authors[vote.get("author", "unknown")] += 1

        top_voted = sorted(voted_authors.items(), key=lambda x: -x[1])[:15]

        return {
            "votes_cast": len(votes_cast),
            "votes_received": len(votes_received),
            "votes_per_day": round(len(votes_cast) / max(self.days, 1), 2),
            "weight_distribution": dict(weight_buckets),
            "most_voted_authors": [
                {"author": a, "votes": c} for a, c in top_voted
            ],
        }

    def delegation_report(self):
        """Analyze HP delegation changes."""
        history = self._load_history()
        delegations = history.get("delegate_vesting_shares", [])

        outgoing = [d for d in delegations if d.get("delegator") == self.account_name]
        incoming = [d for d in delegations if d.get("delegatee") == self.account_name]

        return {
            "outgoing_delegation_changes": len(outgoing),
            "incoming_delegation_changes": len(incoming),
            "recent_outgoing": [
                {
                    "to": d.get("delegatee"),
                    "vests": str(d.get("vesting_shares", "")),
                    "date": d["_time"].isoformat(),
                }
                for d in outgoing[:10]
            ],
            "recent_incoming": [
                {
                    "from": d.get("delegator"),
                    "vests": str(d.get("vesting_shares", "")),
                    "date": d["_time"].isoformat(),
                }
                for d in incoming[:10]
            ],
        }

    def transfer_report(self):
        """Analyze token transfers."""
        history = self._load_history()
        transfers = history.get("transfer", [])

        sent = [t for t in transfers if t.get("from") == self.account_name]
        received = [t for t in transfers if t.get("to") == self.account_name]

        sent_totals = defaultdict(float)
        received_totals = defaultdict(float)

        for t in sent:
            amt = Amount(t["amount"])
            sent_totals[amt.symbol] += float(amt)

        for t in received:
            amt = Amount(t["amount"])
            received_totals[amt.symbol] += float(amt)

        return {
            "transfers_sent": len(sent),
            "transfers_received": len(received),
            "total_sent": {k: round(v, 3) for k, v in sent_totals.items()},
            "total_received": {k: round(v, 3) for k, v in received_totals.items()},
        }

    def full_report(self):
        """Generate comprehensive account report."""
        print(f"Generating report for @{self.account_name} ({self.days} days)...")
        report = {
            "account": self.account_name,
            "period_days": self.days,
            "generated_at": datetime.utcnow().isoformat(),
            "posting": self.posting_report(),
            "earnings": self.earnings_report(),
            "voting": self.voting_report(),
            "delegations": self.delegation_report(),
            "transfers": self.transfer_report(),
        }
        return report


# ---- Usage ----

analyzer = HiveAccountAnalyzer("blocktrades", days=30)
report = analyzer.full_report()

# Pretty print
print(json.dumps(report, indent=2, default=str))

# Save to file
with open("account_report.json", "w") as f:
    json.dump(report, f, indent=2, default=str)
```

### Key Notes

1. **history_reverse()**: Iterates from newest to oldest. Much more efficient when you only need recent data — you can break early once past your cutoff date.
2. **Rate limiting**: Large accounts may have millions of operations. Always set a time cutoff. The API returns batches of 1000 operations per request.
3. **VESTS vs HP**: Rewards are often in VESTS. Convert using: `HP = VESTS * total_vesting_fund_hive / total_vesting_shares` (from dynamic global properties).
4. **Amount parsing**: beem's `Amount` class handles the Hive asset format (`"1.000 HIVE"`) correctly. Always use it instead of manual parsing.
5. **Caching**: For repeated analysis, cache the raw history to avoid hitting API nodes repeatedly. The history is immutable once written.
'''
    ),
    (
        "hive/development",
        r'''How do I publish a witness price feed on Hive using beem? I need to understand witness operations including feed publishing, witness updates, and monitoring.''',
        r'''## Witness Operations and Price Feed Publishing with beem

Hive witnesses are the block producers of the network. One of their critical duties is publishing a price feed that determines the HIVE/HBD conversion rate. This guide covers feed publishing, witness configuration, and monitoring using beem.

### Core Concepts

- **Price feed**: Witnesses publish the HIVE/USD price, used to calculate HBD conversions and reward payouts
- **Feed must be updated regularly** — stale feeds (>24h) are penalized and can cause the witness to be disabled
- **Witness update**: Sets signing key, URL, account creation fee, maximum block size, and HBD interest rate
- **Signing key**: The key your witness node uses to sign blocks — distinct from owner/active/posting keys

### Basic Price Feed Publisher

```python
from beem import Hive
from beem.witness import Witness
from beem.amount import Amount
import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("witness_feed")

# Active key is required for witness operations
hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5Kexample_YOUR_ACTIVE_KEY_HERE"],
)


def get_hive_price():
    """Fetch current HIVE/USD price from CoinGecko."""
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "hive", "vs_currencies": "usd"},
            timeout=10,
        )
        resp.raise_for_status()
        price = resp.json()["hive"]["usd"]
        return round(price, 3)
    except Exception as e:
        logger.error(f"CoinGecko fetch failed: {e}")
        return None


def publish_feed(witness_account, price_usd):
    """Publish a price feed to the Hive blockchain."""
    # The feed format is: base/quote where base is HBD and quote is HIVE
    # If HIVE = $0.30, then 1 HBD = 1/0.30 = 3.333 HIVE
    # Feed: base="0.300 HBD", quote="1.000 HIVE" (meaning 1 HIVE = 0.300 USD)
    base = Amount(f"{price_usd:.3f} HBD")
    quote = Amount("1.000 HIVE")

    witness = Witness(witness_account, blockchain_instance=hive)

    try:
        witness.feed_publish(base, quote=quote)
        logger.info(f"Published feed: 1 HIVE = ${price_usd:.3f} USD")
        return True
    except Exception as e:
        logger.error(f"Feed publish failed: {e}")
        return False


# Publish once
price = get_hive_price()
if price:
    publish_feed("mywitness", price)
```

### Production Witness Feed Publisher with Multi-Source Pricing

```python
from beem import Hive
from beem.witness import Witness
from beem.amount import Amount
from beem.blockchain import Blockchain
import requests
import time
import statistics
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("witness")


class WitnessFeedPublisher:
    """Production witness price feed publisher with multi-source pricing and safety checks."""

    def __init__(self, config):
        self.hive = Hive(
            node=config.get("nodes", ["https://api.hive.blog"]),
            keys=[config["active_key"]],
        )
        self.witness_account = config["witness_account"]
        self.publish_interval = config.get("publish_interval_minutes", 60)
        self.max_price_change = config.get("max_price_change_pct", 15)  # Safety limit
        self.price_history = []
        self.last_published_price = None
        self.running = True

    def fetch_coingecko(self):
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "hive", "vs_currencies": "usd"},
                timeout=10,
            )
            return r.json()["hive"]["usd"]
        except Exception as e:
            logger.warning(f"CoinGecko error: {e}")
            return None

    def fetch_binance(self):
        try:
            r = requests.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": "HIVEUSDT"},
                timeout=10,
            )
            return float(r.json()["price"])
        except Exception as e:
            logger.warning(f"Binance error: {e}")
            return None

    def fetch_upbit(self):
        try:
            # Upbit provides KRW pair — convert via USDT/KRW
            r = requests.get(
                "https://api.upbit.com/v1/ticker",
                params={"markets": "KRW-HIVE"},
                timeout=10,
            )
            krw_price = r.json()[0]["trade_price"]
            # Get KRW/USD rate
            r2 = requests.get(
                "https://api.exchangerate-api.com/v4/latest/USD",
                timeout=10,
            )
            krw_rate = r2.json()["rates"]["KRW"]
            return round(krw_price / krw_rate, 4)
        except Exception as e:
            logger.warning(f"Upbit error: {e}")
            return None

    def get_median_price(self):
        """Get median price from multiple sources for reliability."""
        sources = {
            "coingecko": self.fetch_coingecko,
            "binance": self.fetch_binance,
        }

        prices = {}
        for name, fetcher in sources.items():
            price = fetcher()
            if price and price > 0:
                prices[name] = price
                logger.info(f"  {name}: ${price:.4f}")

        if len(prices) < 1:
            logger.error("No valid price sources available")
            return None

        # Use median to filter outliers
        price_values = list(prices.values())
        median = statistics.median(price_values)

        # Check for outlier sources (>10% from median)
        filtered = [p for p in price_values if abs(p - median) / median < 0.10]
        if not filtered:
            filtered = price_values

        final_price = round(statistics.median(filtered), 3)
        logger.info(f"  Final price: ${final_price:.3f} (from {len(filtered)} sources)")
        return final_price

    def safety_check(self, new_price):
        """Prevent publishing wildly wrong prices due to API errors."""
        if self.last_published_price is None:
            return True

        change_pct = abs(new_price - self.last_published_price) / self.last_published_price * 100
        if change_pct > self.max_price_change:
            logger.warning(
                f"Price change too large: {change_pct:.1f}% "
                f"(${self.last_published_price:.3f} -> ${new_price:.3f}). "
                f"Max allowed: {self.max_price_change}%. Skipping."
            )
            return False
        return True

    def publish_feed(self, price_usd):
        """Publish the price feed to the blockchain."""
        if not self.safety_check(price_usd):
            return False

        try:
            witness = Witness(self.witness_account, blockchain_instance=self.hive)
            base = Amount(f"{price_usd:.3f} HBD")
            quote = Amount("1.000 HIVE")

            witness.feed_publish(base, quote=quote)

            self.last_published_price = price_usd
            self.price_history.append({
                "price": price_usd,
                "time": datetime.utcnow().isoformat(),
            })

            # Keep only 24h of history
            self.price_history = self.price_history[-1440:]

            logger.info(f"Published feed: 1 HIVE = ${price_usd:.3f}")
            return True

        except Exception as e:
            msg = str(e)
            if "missing required active authority" in msg:
                logger.error("Wrong key — active key is required for feed publishing")
            elif "rc_plugin_exception" in msg:
                logger.error("Insufficient RC for feed publish")
            else:
                logger.error(f"Feed publish failed: {e}")
            return False

    def check_witness_status(self):
        """Monitor witness status — block production, version, feed age."""
        try:
            witness = Witness(self.witness_account, blockchain_instance=self.hive)
            w = witness.json()

            last_block = w.get("last_confirmed_block_num", 0)
            total_missed = w.get("total_missed", 0)
            running_version = w.get("running_version", "unknown")
            signing_key = w.get("signing_key", "")

            # Check if witness is disabled (signing key is all zeros)
            is_disabled = signing_key.startswith("STM1111111")

            # Feed age
            feed_time = datetime.strptime(
                w.get("last_hbd_exchange_update", "1970-01-01T00:00:00"),
                "%Y-%m-%dT%H:%M:%S",
            )
            feed_age = datetime.utcnow() - feed_time
            feed_stale = feed_age > timedelta(hours=24)

            status = {
                "account": self.witness_account,
                "enabled": not is_disabled,
                "last_block": last_block,
                "total_missed": total_missed,
                "version": running_version,
                "feed_age_hours": round(feed_age.total_seconds() / 3600, 1),
                "feed_stale": feed_stale,
            }

            if feed_stale:
                logger.warning(f"Feed is stale! Age: {status['feed_age_hours']}h")
            if is_disabled:
                logger.warning("Witness is DISABLED — signing key is null")

            return status

        except Exception as e:
            logger.error(f"Status check failed: {e}")
            return None

    def update_witness_properties(self, props):
        """Update witness parameters (account creation fee, block size, HBD interest)."""
        witness = Witness(self.witness_account, blockchain_instance=self.hive)

        try:
            witness.update(
                signing_key=props.get("signing_key"),
                url=props.get("url", ""),
                props={
                    "account_creation_fee": Amount(
                        props.get("account_creation_fee", "3.000 HIVE")
                    ),
                    "maximum_block_size": props.get("maximum_block_size", 65536),
                    "hbd_interest_rate": props.get("hbd_interest_rate", 1500),  # 15.00%
                },
            )
            logger.info("Witness properties updated")
        except Exception as e:
            logger.error(f"Witness update failed: {e}")

    def run(self):
        """Main loop — publish feed at configured intervals."""
        logger.info(f"Witness feed publisher started for @{self.witness_account}")
        logger.info(f"Publish interval: {self.publish_interval} minutes")

        while self.running:
            # Check witness status
            status = self.check_witness_status()
            if status:
                logger.info(
                    f"Witness status: enabled={status['enabled']}, "
                    f"missed={status['total_missed']}, "
                    f"feed_age={status['feed_age_hours']}h"
                )

            # Fetch and publish price
            price = self.get_median_price()
            if price:
                self.publish_feed(price)
            else:
                logger.warning("Could not determine price — skipping this round")

            # Sleep until next publish
            logger.info(f"Next publish in {self.publish_interval} minutes")
            for _ in range(self.publish_interval * 60):
                if not self.running:
                    break
                time.sleep(1)


# ---- Launch ----

config = {
    "witness_account": "mywitness",
    "active_key": "5Kexample_YOUR_ACTIVE_KEY_HERE",
    "nodes": ["https://api.hive.blog", "https://api.deathwing.me"],
    "publish_interval_minutes": 60,
    "max_price_change_pct": 15,
}

publisher = WitnessFeedPublisher(config)
publisher.run()
```

### Key Notes

1. **Feed format**: The feed is expressed as `base/quote` where base is HBD and quote is HIVE. Publishing `"0.300 HBD" / "1.000 HIVE"` means 1 HIVE = $0.30.
2. **Publish frequency**: Most witnesses publish every 1-3 hours. More frequent is fine but wastes RC. Less frequent risks the feed becoming stale.
3. **Safety checks**: Always validate prices against the last published value. A bad API response could cause you to publish a wildly wrong price, harming the network.
4. **HBD interest rate**: Set via `hbd_interest_rate` in witness properties. The value is in basis points: 1500 = 15.00% APR. The median of all top-20 witness rates is used.
5. **Active key**: All witness operations require the active key. Never put the owner key in a feed publisher script.
'''
    ),
    (
        "hive/development",
        r'''How do I build an automated content posting system for Hive using beem with scheduling, template support, and retry logic?''',
        r'''## Automated Content Posting System for Hive with beem

Building a scheduled posting system requires handling Hive's rate limits (5-minute interval between posts), managing posting keys securely, supporting content templates, and implementing retry logic for network failures.

### Core Concepts

- **5-minute cooldown**: Hive enforces a minimum 5-minute interval between top-level posts from the same account
- **3-second cooldown**: Replies (comments) have a 3-second minimum interval
- **Permlink uniqueness**: Reusing a permlink edits the existing post instead of creating a new one
- **json_metadata**: Frontends parse this for tags, images, app attribution, and content format

### Basic Scheduled Post

```python
from beem import Hive
from beem.comment import Comment
from beem.exceptions import ContentDoesNotExistsException
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("poster")

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5Kexample_YOUR_POSTING_KEY_HERE"],
)


def create_post(author, title, body, tags, community=None):
    """Create a single post on Hive."""
    import json as json_mod
    from beem.transactionbuilder import TransactionBuilder
    from beembase.operations import Comment as CommentOp, Comment_options

    # Generate unique permlink
    slug = title.lower()
    for ch in "?!@#$%^&*()+=[]{}|;:'\",.<>/":
        slug = slug.replace(ch, "")
    slug = "-".join(slug.split())[:200]
    timestamp = hex(int(time.time()))[2:]
    permlink = f"{slug}-{timestamp}"

    parent_permlink = community if community else (tags[0] if tags else "general")

    metadata = json_mod.dumps({
        "tags": tags,
        "app": "hive-autoposter/1.0",
        "format": "markdown",
    })

    try:
        hive.post(
            title=title,
            body=body,
            author=author,
            permlink=permlink,
            tags=tags,
            community=community,
            json_metadata=metadata,
        )
        logger.info(f"Posted: @{author}/{permlink}")
        return permlink
    except Exception as e:
        logger.error(f"Post failed: {e}")
        raise


# Simple usage
create_post(
    author="myaccount",
    title="Daily Market Update",
    body="# Market Summary\n\nHIVE is looking strong today...",
    tags=["hive", "market", "crypto"],
)
```

### Production Automated Posting System

```python
from beem import Hive
from beem.exceptions import ContentDoesNotExistsException
import json
import time
import os
import logging
import schedule
from datetime import datetime, timedelta
from string import Template
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("autoposter.log"),
    ],
)
logger = logging.getLogger("autoposter")


class PostTemplate:
    """Markdown post template with variable substitution."""

    def __init__(self, template_str, defaults=None):
        self.template = Template(template_str)
        self.defaults = defaults or {}

    @classmethod
    def from_file(cls, filepath, defaults=None):
        content = Path(filepath).read_text(encoding="utf-8")
        return cls(content, defaults)

    def render(self, **kwargs):
        merged = {**self.defaults, **kwargs}
        merged.setdefault("date", datetime.utcnow().strftime("%Y-%m-%d"))
        merged.setdefault("datetime", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
        return self.template.safe_substitute(merged)


class ScheduledPost:
    """Represents a post scheduled for future publication."""

    def __init__(self, title, body, tags, community=None, beneficiaries=None,
                 max_accepted_payout="1000000.000 HBD", percent_hbd=10000):
        self.title = title
        self.body = body
        self.tags = tags
        self.community = community
        self.beneficiaries = beneficiaries or []
        self.max_accepted_payout = max_accepted_payout
        self.percent_hbd = percent_hbd
        self.attempts = 0
        self.max_attempts = 3
        self.created_permlink = None


class HiveAutoPoster:
    """Production automated posting system with scheduling, templates, and retries."""

    def __init__(self, config):
        self.hive = Hive(
            node=config.get("nodes", ["https://api.hive.blog", "https://api.deathwing.me"]),
            keys=[config["posting_key"]],
        )
        self.author = config["author"]
        self.active_key = config.get("active_key")  # Needed for beneficiaries
        self.post_queue = []
        self.published = []
        self.last_post_time = 0
        self.min_post_interval = 310  # 5 min + 10s safety margin
        self.state_file = config.get("state_file", "poster_state.json")
        self.running = True

    def _generate_permlink(self, title):
        slug = title.lower()
        for ch in "?!@#$%^&*()+=[]{}|;:'\",.<>/":
            slug = slug.replace(ch, "")
        slug = "-".join(slug.split())[:180]
        timestamp = hex(int(time.time()))[2:]
        return f"{slug}-{timestamp}"

    def _wait_for_cooldown(self):
        """Wait for the 5-minute post interval if needed."""
        elapsed = time.time() - self.last_post_time
        if elapsed < self.min_post_interval:
            wait = self.min_post_interval - elapsed
            logger.info(f"Waiting {wait:.0f}s for post cooldown...")
            time.sleep(wait)

    def publish_post(self, scheduled_post):
        """Publish a single post with retry logic."""
        post = scheduled_post
        post.attempts += 1

        self._wait_for_cooldown()

        permlink = self._generate_permlink(post.title)
        parent_permlink = post.community or (post.tags[0] if post.tags else "general")

        metadata = json.dumps({
            "tags": post.tags,
            "app": "hive-autoposter/1.0",
            "format": "markdown",
            "image": self._extract_images(post.body),
        })

        try:
            self.hive.post(
                title=post.title,
                body=post.body,
                author=self.author,
                permlink=permlink,
                tags=post.tags,
                community=post.community,
                json_metadata=metadata,
                beneficiaries=post.beneficiaries if post.beneficiaries else None,
                self_vote=False,
            )

            self.last_post_time = time.time()
            post.created_permlink = permlink
            self.published.append({
                "title": post.title,
                "permlink": permlink,
                "time": datetime.utcnow().isoformat(),
            })
            self._save_state()

            logger.info(f"Published: '{post.title}' -> @{self.author}/{permlink}")
            logger.info(f"  Tags: {post.tags}, Community: {post.community or 'none'}")
            return permlink

        except Exception as e:
            msg = str(e)
            if "HIVE_MIN_ROOT_COMMENT_INTERVAL" in msg:
                logger.warning("Post interval not met, retrying after wait...")
                time.sleep(60)
                if post.attempts < post.max_attempts:
                    return self.publish_post(post)

            elif "rc_plugin_exception" in msg:
                logger.error("Insufficient RC. Waiting 30 minutes...")
                time.sleep(1800)
                if post.attempts < post.max_attempts:
                    return self.publish_post(post)

            elif "missing required posting authority" in msg:
                logger.error("Posting key is invalid or does not match the account")
                return None

            else:
                logger.error(f"Post failed (attempt {post.attempts}): {msg}")
                if post.attempts < post.max_attempts:
                    wait = 30 * post.attempts
                    logger.info(f"Retrying in {wait}s...")
                    time.sleep(wait)
                    return self.publish_post(post)

            logger.error(f"Post failed after {post.attempts} attempts: {post.title}")
            return None

    def queue_post(self, title, body, tags, **kwargs):
        """Add a post to the queue."""
        post = ScheduledPost(title, body, tags, **kwargs)
        self.post_queue.append(post)
        logger.info(f"Queued: '{title}' ({len(self.post_queue)} in queue)")
        return post

    def queue_from_template(self, template, title, tags, context=None, **kwargs):
        """Create a post from a template and queue it."""
        body = template.render(**(context or {}))
        return self.queue_post(title, body, tags, **kwargs)

    def process_queue(self):
        """Process all queued posts sequentially."""
        logger.info(f"Processing {len(self.post_queue)} queued posts...")
        results = []
        while self.post_queue and self.running:
            post = self.post_queue.pop(0)
            permlink = self.publish_post(post)
            results.append({"title": post.title, "permlink": permlink, "success": bool(permlink)})
        return results

    def _extract_images(self, markdown):
        import re
        return re.findall(r'!\[.*?\]\((https?://[^\s)]+)\)', markdown)

    def _save_state(self):
        with open(self.state_file, "w") as f:
            json.dump({
                "published": self.published[-100:],
                "last_post_time": self.last_post_time,
            }, f, indent=2)

    def _load_state(self):
        try:
            with open(self.state_file) as f:
                state = json.load(f)
                self.published = state.get("published", [])
                self.last_post_time = state.get("last_post_time", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            pass


# ---- Usage: Daily automated posting ----

poster = HiveAutoPoster({
    "author": "myaccount",
    "posting_key": "5Kexample_YOUR_POSTING_KEY_HERE",
    "nodes": ["https://api.hive.blog", "https://api.deathwing.me"],
})

# Define templates
daily_template = PostTemplate(r"""# Daily Update - $date

## Summary
$summary

## Statistics
- Posts today: $post_count
- Active users: $active_users
- HIVE price: $$hive_price

---
*Posted automatically by [MyApp](https://myapp.com)*
""")

# Queue templated posts
poster.queue_from_template(
    template=daily_template,
    title=f"Daily Update - {datetime.utcnow().strftime('%Y-%m-%d')}",
    tags=["hive", "daily", "update"],
    community="hive-174301",
    context={
        "summary": "Another great day on Hive!",
        "post_count": "142",
        "active_users": "5,231",
        "hive_price": "0.32",
    },
    beneficiaries=[
        {"account": "myapp", "weight": 300},  # 3% app fee
    ],
)

# Process the queue
results = poster.process_queue()
for r in results:
    status = "OK" if r["success"] else "FAILED"
    print(f"[{status}] {r['title']} -> {r['permlink']}")
```

### Key Notes

1. **5-minute rule**: The blockchain enforces `HIVE_MIN_ROOT_COMMENT_INTERVAL` (5 minutes) between top-level posts. Plan your scheduling accordingly. Replies have a 3-second interval.
2. **Permlink as edit**: If you accidentally reuse a permlink, you will overwrite (edit) the existing post. Always include a timestamp or random component.
3. **Beneficiaries with beem**: beem's `post()` method accepts a `beneficiaries` parameter directly. They must be sorted alphabetically by account name.
4. **Content size**: Hive posts can be up to ~64KB. For larger content, split into a series or host media externally (IPFS, Imgur).
5. **Scheduling libraries**: Use `schedule`, `APScheduler`, or system cron to trigger posts. The bot should persist state so it can resume after restarts without duplicate posting.
'''
    ),
]
