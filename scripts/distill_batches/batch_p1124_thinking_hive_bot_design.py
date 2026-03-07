"""
Hive blockchain thinking pairs - bot architecture reasoning
"""

pairs = [
    {
        "instruction": r'''I want to build a curation bot that upvotes quality posts on Hive. What are the main design tradeoffs I should consider?''',
        "output": r'''<think>
Curation bot design -- there are several major tradeoffs to think about. Let me work through them systematically.

First, vote timing. On Hive, curation rewards are maximized when you vote early on posts that later get more votes. If you vote at exactly 0 minutes, you lose some curation rewards to a penalty (I think the penalty was removed in HF25 actually... wait, let me think. HF25 changed curation to be linear and removed the reverse auction. So timing is less critical than it used to be, but voting early on posts that will do well is still advantageous because your vote captures more of the reward curve before larger votes come in.

Hmm, but voting too early means you have not had time to evaluate quality. Automated quality detection is hard. Options: keyword matching (crude), author reputation/history (better), NLP content analysis (complex), manual curation trail following (easiest).

I initially thought following a curation trail would be simplest, but that introduces dependency on the trail leader. If the trail leader makes bad votes, your bot follows. And you are always voting AFTER the leader, so your curation position is worse.

Second tradeoff: vote weight distribution. A 100% vote on one post vs 10% votes on 10 posts. With linear rewards, spreading votes is mathematically equivalent in terms of your curation return. But practically, voting on more posts with smaller weight diversifies your curation risk.

Third: RC and voting power management. Each vote consumes voting power (VP). At 100% VP, a full vote uses 2% VP. VP regenerates at about 20% per day. So you can do roughly 10 full votes per day. If the bot votes too aggressively, VP drops and individual votes become worth less.

The tradeoff summary: vote early (better curation position) vs vote late (better quality assessment). Vote concentrated (higher individual impact) vs vote distributed (lower risk). Follow trails (simple) vs independent evaluation (harder but more valuable).
</think>

Here is a curation bot framework that balances the key tradeoffs with configurable strategies:

```python
from beem import Hive
from beem.account import Account
from beem.comment import Comment
from beem.blockchain import Blockchain
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Vote
import time
import json
from datetime import datetime, timedelta
from collections import defaultdict

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)


class CurationBot:
    """Configurable curation bot with quality filtering."""

    def __init__(self, account, blockchain_instance=None):
        self.account = account
        self.hive = blockchain_instance or hive
        self.acc = Account(self.account, blockchain_instance=self.hive)

        # === Tunable Parameters ===
        self.min_vote_power = 80.0    # stop voting below this VP %
        self.default_weight = 5000    # 50% vote weight
        self.max_daily_votes = 15
        self.min_post_age_minutes = 5    # wait for initial assessment
        self.max_post_age_minutes = 120  # do not vote on old posts
        self.min_author_rep = 25.0
        self.min_word_count = 200
        self.blacklisted_authors = set()
        self.whitelisted_authors = set()

        # Tracking
        self.votes_today = 0
        self.day_start = datetime.utcnow().date()
        self.voted_posts = set()

    def get_voting_power(self):
        """Get current voting power percentage."""
        self.acc.refresh()
        vp = self.acc.get_voting_power()
        return vp

    def should_vote(self, post):
        """Evaluate whether a post deserves a vote."""
        author = post["author"]
        permlink = post["permlink"]
        post_key = f"{author}/{permlink}"

        # Already voted
        if post_key in self.voted_posts:
            return False, "already_voted"

        # Daily limit
        today = datetime.utcnow().date()
        if today != self.day_start:
            self.votes_today = 0
            self.day_start = today
        if self.votes_today >= self.max_daily_votes:
            return False, "daily_limit"

        # Voting power check
        vp = self.get_voting_power()
        if vp < self.min_vote_power:
            return False, f"low_vp_{vp:.1f}"

        # Blacklist / whitelist
        if author in self.blacklisted_authors:
            return False, "blacklisted"

        # Author reputation
        try:
            author_acc = Account(author, blockchain_instance=self.hive)
            rep = author_acc.get_reputation()
            if rep < self.min_author_rep:
                return False, f"low_rep_{rep:.1f}"
        except Exception:
            return False, "author_lookup_failed"

        # Content quality checks
        body = post.get("body", "")
        word_count = len(body.split())
        if word_count < self.min_word_count:
            return False, f"short_{word_count}_words"

        # Post age check
        created = post.get("created", "")
        if isinstance(created, str) and created:
            try:
                created_dt = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S")
                age_minutes = (datetime.utcnow() - created_dt).seconds / 60
                if age_minutes < self.min_post_age_minutes:
                    return False, "too_new"
                if age_minutes > self.max_post_age_minutes:
                    return False, "too_old"
            except ValueError:
                pass

        # Whitelist gets higher weight
        if author in self.whitelisted_authors:
            return True, "whitelisted"

        return True, "passed_filters"

    def calculate_weight(self, post, reason):
        """Determine vote weight based on post quality signals."""
        if reason == "whitelisted":
            return min(self.default_weight * 2, 10000)

        # Scale weight by content length (rough quality proxy)
        body = post.get("body", "")
        words = len(body.split())
        if words > 1000:
            return self.default_weight
        elif words > 500:
            return int(self.default_weight * 0.8)
        else:
            return int(self.default_weight * 0.5)

    def vote(self, author, permlink, weight):
        """Cast a vote."""
        tx = TransactionBuilder(blockchain_instance=self.hive)
        tx.appendOps(Vote(**{
            "voter": self.account,
            "author": author,
            "permlink": permlink,
            "weight": weight
        }))
        tx.appendSigner(self.account, "posting")
        tx.sign()
        result = tx.broadcast()

        self.voted_posts.add(f"{author}/{permlink}")
        self.votes_today += 1
        return result

    def run(self, tags=None):
        """Main loop: stream new posts and evaluate them."""
        chain = Blockchain(blockchain_instance=self.hive)
        print(f"Curation bot started for @{self.account}")
        print(f"VP: {self.get_voting_power():.1f}% | "
              f"Min VP: {self.min_vote_power}%")

        for op in chain.stream(opNames=["comment"]):
            # Only root posts (not replies)
            if op.get("parent_author", "") != "":
                continue

            # Tag filter
            if tags:
                try:
                    meta = json.loads(op.get("json_metadata", "{}"))
                    post_tags = meta.get("tags", [])
                    if not any(t in tags for t in post_tags):
                        continue
                except json.JSONDecodeError:
                    continue

            should, reason = self.should_vote(op)
            if should:
                weight = self.calculate_weight(op, reason)
                try:
                    result = self.vote(
                        op["author"], op["permlink"], weight
                    )
                    print(f"Voted {weight/100:.0f}% on "
                          f"@{op['author']}/{op['permlink']} "
                          f"({reason})")
                except Exception as e:
                    print(f"Vote failed: {e}")

                # Rate limiting
                time.sleep(3)


# Usage
bot = CurationBot("mycurationbot", blockchain_instance=hive)
bot.whitelisted_authors = {"trustedauthor1", "trustedauthor2"}
bot.blacklisted_authors = {"spammer1"}
bot.run(tags=["python", "programming", "hive-dev"])
```

Key design decisions: minimum VP threshold prevents vote value from degrading. Post age window (5-120 min) balances early voting against quality assessment time. Word count filter catches low-effort posts. Weight scaling rewards longer content. Daily vote cap preserves VP for the next day.'''
    },
    {
        "instruction": r'''My curation bot sometimes votes right before the post author deletes the post, or the post turns out to be plagiarism found later. Is there a way to handle this?''',
        "output": r'''<think>
Hmm, this is about vote recovery after bad votes. Let me think about what happens on Hive when you vote on a post that later turns out to be bad.

On Hive, you CAN change your vote within a certain window. You can set your vote weight to 0 (effectively unvoting) or change the weight. But there is a catch -- changing your vote still uses voting power. Actually, wait, I need to think about this more carefully.

When you unvote (set weight to 0), you get your curation reward allocation back BUT you still spent the voting power. So unvoting is not free. And there is a time limit -- I believe you can change your vote within... hmm, actually I do not think there is a strict time limit on changing votes. You can change your vote at any time before the post pays out (7 days).

But here is the thing -- if you unvote after other voters have voted based on your vote (trail followers), the damage to your curation position is already done. And the voting power spent on the original vote plus the unvote is wasted.

I initially thought about just monitoring for plagiarism reports and auto-unvoting, but that is reactive. A better approach is to have a confirmation delay -- vote after some time has passed, giving plagiarism checkers like @hivewatcher time to flag content.

The tradeoff is: vote immediately (best curation position, risk of voting on bad content) vs wait for verification (worse curation position, less risk). Could also implement a two-phase approach: downvote (flag) if plagiarism is detected later, but that uses even more VP.

For deleted posts, once a post is deleted, the vote stays but the post has no rewards to distribute. The VP is spent with no return. Not much you can do about that after the fact.
</think>

You can unvote or change your vote before payout, and you should implement post-vote monitoring. Here is a defensive curation system:

```python
from beem import Hive
from beem.comment import Comment
from beem.account import Account
from beem.blockchain import Blockchain
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Vote
import time
import json
from threading import Thread
from datetime import datetime, timedelta

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)

BOT_ACCOUNT = "mycurationbot"


class DefensiveCurationBot:
    """Curation bot with post-vote monitoring and unvote capability."""

    def __init__(self, account, blockchain_instance):
        self.account = account
        self.hive = blockchain_instance
        self.active_votes = {}  # permlink -> vote_info
        self.plagiarism_reporters = {
            "hivewatchers", "hivewatcher", "spaminator"
        }

    def vote(self, author, permlink, weight):
        """Cast a vote and register it for monitoring."""
        tx = TransactionBuilder(blockchain_instance=self.hive)
        tx.appendOps(Vote(**{
            "voter": self.account,
            "author": author,
            "permlink": permlink,
            "weight": weight
        }))
        tx.appendSigner(self.account, "posting")
        tx.sign()
        result = tx.broadcast()

        # Track for monitoring
        self.active_votes[f"{author}/{permlink}"] = {
            "author": author,
            "permlink": permlink,
            "weight": weight,
            "voted_at": datetime.utcnow(),
            "tx_id": result["id"]
        }
        return result

    def unvote(self, author, permlink):
        """Remove a vote by setting weight to 0.

        Note: this still costs voting power (the original VP
        plus the unvote VP). Use sparingly.
        """
        tx = TransactionBuilder(blockchain_instance=self.hive)
        tx.appendOps(Vote(**{
            "voter": self.account,
            "author": author,
            "permlink": permlink,
            "weight": 0  # 0 = remove vote
        }))
        tx.appendSigner(self.account, "posting")
        tx.sign()
        result = tx.broadcast()

        key = f"{author}/{permlink}"
        if key in self.active_votes:
            del self.active_votes[key]
        print(f"Unvoted @{author}/{permlink}")
        return result

    def check_post_health(self, author, permlink):
        """Check if a voted post is still healthy."""
        issues = []

        try:
            post = Comment(f"@{author}/{permlink}",
                          blockchain_instance=self.hive)
            post.refresh()
        except Exception:
            issues.append("post_deleted_or_not_found")
            return issues

        # Check if post body was emptied (soft delete)
        body = post.get("body", "")
        if len(body.strip()) < 50:
            issues.append("post_body_removed")

        # Check for downvotes from anti-abuse accounts
        active_votes = post.get("active_votes", [])
        for vote in active_votes:
            voter = vote.get("voter", "")
            weight = vote.get("percent", vote.get("weight", 0))
            if voter in self.plagiarism_reporters and weight < 0:
                issues.append(f"flagged_by_{voter}")

        # Check if the post has been heavily downvoted overall
        net_votes = post.get("net_votes", 0)
        if net_votes < -3:
            issues.append("heavily_downvoted")

        return issues

    def monitor_voted_posts(self):
        """Periodically check all voted posts for problems."""
        while True:
            posts_to_check = list(self.active_votes.values())

            for vote_info in posts_to_check:
                author = vote_info["author"]
                permlink = vote_info["permlink"]
                age = datetime.utcnow() - vote_info["voted_at"]

                # Only monitor posts less than 7 days old (before payout)
                if age > timedelta(days=7):
                    key = f"{author}/{permlink}"
                    self.active_votes.pop(key, None)
                    continue

                issues = self.check_post_health(author, permlink)

                if issues:
                    print(f"Issues with @{author}/{permlink}: {issues}")
                    # Auto-unvote for serious issues
                    serious = {"post_deleted_or_not_found",
                               "post_body_removed",
                               "flagged_by_hivewatchers",
                               "flagged_by_hivewatcher"}
                    if serious.intersection(issues):
                        try:
                            self.unvote(author, permlink)
                            print(f"Auto-unvoted due to: {issues}")
                        except Exception as e:
                            print(f"Unvote failed: {e}")

            # Check every 30 minutes
            time.sleep(1800)

    def start_monitoring(self):
        """Start the monitoring thread."""
        monitor = Thread(target=self.monitor_voted_posts, daemon=True)
        monitor.start()
        print("Post health monitoring started")


# === Stream-Based Plagiarism Detection ===

def watch_for_flags(bot, blockchain_instance):
    """Watch the blockchain for downvotes on our voted posts."""
    chain = Blockchain(blockchain_instance=blockchain_instance)

    for op in chain.stream(opNames=["vote"]):
        voter = op.get("voter", "")
        weight = op.get("weight", 0)

        # Only care about downvotes from anti-abuse accounts
        if voter not in bot.plagiarism_reporters:
            continue
        if weight >= 0:
            continue

        author = op.get("author", "")
        permlink = op.get("permlink", "")
        key = f"{author}/{permlink}"

        if key in bot.active_votes:
            print(f"ALERT: {voter} flagged @{key} (weight: {weight})")
            try:
                bot.unvote(author, permlink)
            except Exception as e:
                print(f"Auto-unvote failed: {e}")


# Usage
bot = DefensiveCurationBot(BOT_ACCOUNT, hive)
bot.start_monitoring()
```

The monitoring catches three scenarios: deleted posts (body check), plagiarism flags (anti-abuse downvotes), and community rejection (heavy downvoting). Auto-unvoting wastes some VP but prevents your account from being associated with abusive content and recovers the curation reward allocation.'''
    },
    {
        "instruction": r'''How should I handle chain forks and missed blocks in my Hive bot that processes every block sequentially?''',
        "output": r'''<think>
Chain forks on Hive -- this is important for any bot that relies on block data being final. Let me think about how forks work on Hive.

Hive uses DPoS with 21 witnesses producing blocks in rounds. A block becomes irreversible after 2/3+1 of witnesses (15 out of 21) have built on top of it. The last irreversible block (LIB) is usually about 45 seconds (15 blocks) behind the head block.

So between the head block and LIB, blocks can be reversed if a minority fork occurs. This is rare but possible -- for example, if a witness misses their slot and produces a block late, creating a temporary fork.

For a bot processing blocks sequentially, the question is: should I process blocks as they appear (head) or wait for irreversibility (LIB)?

If I process at head, I get faster reaction times but risk processing a block that gets orphaned. Then I need to "undo" whatever I did based on that block.

If I wait for LIB, I am always 15 blocks (~45 seconds) behind but I never need to handle reverts.

Hmm, the tradeoff depends on the use case. A curation bot voting based on new posts can afford to wait 45 seconds. A trading bot that needs to react to transfers immediately cannot wait.

I initially thought most bots should just use LIB, but wait -- there is a middle ground. Process at head for time-sensitive operations but maintain a "pending" state that only becomes final after the block reaches LIB. This is how exchanges handle deposits.

For missed blocks, the issue is different. If witness X misses their slot, there is simply no block for that number. The next witness produces the next block. Block numbers can have gaps in the block stream. Beem handles this transparently in most cases, but if you are fetching blocks by number, you need to handle None responses.

Actually, I do not think Hive skips block numbers. Missed slots mean the block is produced late or by a backup witness, but the block number sequence is continuous. Let me reconsider... no, on Hive, if a witness misses their slot, the block number is still assigned but the block might be empty or produced by the next witness. The block number sequence is always continuous.

Wait, actually I think missed blocks can result in the block existing but being empty (no transactions). So the bot just sees an empty block and moves on. The fork scenario is the real concern.
</think>

Handle forks by tracking irreversibility and maintaining a revertible state buffer. Here is a fork-safe block processor:

```python
from beem import Hive
from beem.blockchain import Blockchain
import time
import json
from collections import OrderedDict
from threading import Lock

hive = Hive(node=[
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://api.openhive.network"
])


class ForkSafeBlockProcessor:
    """Process blocks with fork detection and revert capability."""

    def __init__(self, blockchain_instance, start_block=None):
        self.hive = blockchain_instance
        self.chain = Blockchain(blockchain_instance=self.hive)

        # Track processed blocks for fork detection
        self.processed_blocks = OrderedDict()  # block_num -> block_id
        self.max_tracked = 100  # keep last 100 blocks

        # Pending state: operations processed but not yet irreversible
        self.pending_ops = OrderedDict()  # block_num -> [operations]

        self.start_block = start_block
        self.last_lib = 0
        self.lock = Lock()

    def get_lib(self):
        """Get the Last Irreversible Block number."""
        props = self.hive.rpc.get_dynamic_global_properties()
        return props["last_irreversible_block_num"]

    def get_head_block(self):
        props = self.hive.rpc.get_dynamic_global_properties()
        return props["head_block_number"]

    def detect_fork(self, block_num, block_id):
        """Check if we are on a different fork than expected."""
        if block_num in self.processed_blocks:
            expected_id = self.processed_blocks[block_num]
            if expected_id != block_id:
                return True  # Fork detected
        return False

    def handle_fork(self, fork_block_num):
        """Revert operations from the forked blocks."""
        print(f"FORK DETECTED at block {fork_block_num}!")

        # Collect all blocks after the fork point
        blocks_to_revert = []
        with self.lock:
            for bnum in sorted(self.pending_ops.keys(), reverse=True):
                if bnum >= fork_block_num:
                    blocks_to_revert.append(bnum)

        # Revert in reverse order
        for bnum in blocks_to_revert:
            ops = self.pending_ops.pop(bnum, [])
            for op in reversed(ops):
                self._revert_operation(op)
            self.processed_blocks.pop(bnum, None)
            print(f"  Reverted block {bnum} ({len(ops)} ops)")

        return fork_block_num  # resume from fork point

    def _revert_operation(self, op):
        """Revert a single operation. Override for your app logic.

        Example: if you indexed a vote, remove it from your index.
        """
        op_type = op.get("type", "")
        print(f"  Reverting {op_type}: {op.get('summary', '')}")
        # App-specific revert logic goes here
        # e.g., DELETE FROM votes WHERE block_num = ? AND voter = ?

    def finalize_blocks(self):
        """Move blocks that reached LIB from pending to finalized."""
        current_lib = self.get_lib()
        if current_lib <= self.last_lib:
            return

        finalized = []
        with self.lock:
            for bnum in list(self.pending_ops.keys()):
                if bnum <= current_lib:
                    ops = self.pending_ops.pop(bnum)
                    finalized.append((bnum, ops))

        for bnum, ops in finalized:
            for op in ops:
                self._finalize_operation(op)

        if finalized:
            self.last_lib = current_lib

    def _finalize_operation(self, op):
        """Mark an operation as irreversible. Override for your app.

        Example: UPDATE votes SET is_final = TRUE WHERE ...
        """
        pass  # App-specific finalization

    def process_block(self, block_num):
        """Fetch and process a single block."""
        block = self.hive.rpc.get_block(block_num)
        if block is None:
            return False  # Block not yet produced

        block_id = block.get("block_id", "")

        # Fork detection
        if self.detect_fork(block_num, block_id):
            resume_from = self.handle_fork(block_num)
            return resume_from

        # Process transactions
        block_ops = []
        for tx_idx, tx in enumerate(block.get("transactions", [])):
            for op_idx, op in enumerate(tx.get("operations", [])):
                op_type = op[0] if isinstance(op, list) else op.get("type")
                op_data = op[1] if isinstance(op, list) else op.get("value")

                processed = self._process_operation(
                    block_num, op_type, op_data
                )
                if processed:
                    block_ops.append(processed)

        # Track block
        with self.lock:
            self.processed_blocks[block_num] = block_id
            if block_ops:
                self.pending_ops[block_num] = block_ops

            # Trim tracked blocks
            while len(self.processed_blocks) > self.max_tracked:
                self.processed_blocks.popitem(last=False)

        return True

    def _process_operation(self, block_num, op_type, op_data):
        """Process a single operation. Override for your app."""
        # Example: index custom_json operations
        if op_type == "custom_json" and op_data.get("id") == "myapp":
            return {
                "type": op_type,
                "block_num": block_num,
                "data": op_data,
                "summary": f"custom_json from {op_data.get('required_posting_auths', ['?'])[0]}"
            }
        return None

    def run(self):
        """Main processing loop with fork handling."""
        current = self.start_block or self.get_head_block()
        print(f"Starting from block {current}")
        finalize_counter = 0

        while True:
            result = self.process_block(current)

            if result is False:
                # At head, wait for next block
                time.sleep(1)
                continue
            elif isinstance(result, int):
                # Fork detected, resume from fork point
                current = result
                continue

            current += 1
            finalize_counter += 1

            # Finalize irreversible blocks periodically
            if finalize_counter >= 10:
                self.finalize_blocks()
                finalize_counter = 0


# Usage
processor = ForkSafeBlockProcessor(hive)
processor.run()
```

Key design points: blocks between head and LIB (~15 blocks) are tentative. Fork detection compares block IDs. Operations are held in pending state until irreversible. Revert logic undoes tentative operations if a fork is detected. For most bots (curation, indexing), waiting for LIB is simpler and sufficient -- fork handling is only needed if you must react to head blocks immediately.'''
    },
    {
        "instruction": r'''I want my bot to vote at the optimal time after a post is created to maximize curation rewards. What is the current optimal timing strategy on Hive?''',
        "output": r'''<think>
Vote timing for curation rewards on Hive -- let me think about how curation rewards work after the various hard forks.

Before HF25, there was a "reverse auction" penalty where votes in the first 5 minutes would forfeit a portion of curation rewards back to the author. This incentivized voting at exactly 5 minutes.

After HF25 (which went live in June 2021), the reverse auction was removed. Curation rewards are now linear -- your curation reward is proportional to your vote's rshares relative to the total rshares on the post, regardless of when you vote.

Wait, but does timing still matter? Let me think... Even without the reverse auction, there is a strategic element. Your curation reward is based on your share of the total curation. If you vote early when the post has few votes, your rshares make up a larger share of the total. But if the post later gets big votes, your share dilutes.

Hmm, but actually the formula is that curation rewards are distributed proportionally to rshares. So if I vote 1000 rshares and the total is 10000 rshares, I get 10% of curation. It does not matter WHEN I voted relative to others -- just my proportion of total rshares.

Wait, I am confusing myself. Let me reconsider. The curation reward formula on Hive after HF25 is: each voter gets curation rewards proportional to their sqrt(rshares) at the time of their vote, relative to the total sqrt(rshares) accumulated. Actually no, I think it is simpler than that now. Let me think again...

I initially thought timing was irrelevant post-HF25, but actually there is still one factor: the way curation rewards are calculated, early voters benefit because their vote's contribution to the total reward pool is measured from their vote time forward. Each subsequent vote adds to the pool, and the existing voters benefit from the post's total payout increasing.

Actually, I think I am overcomplicating this. Post-HF25, curation is 50% of post rewards, distributed to voters proportionally by rshares. Timing does not affect the formula directly. The optimal strategy is simply: vote on posts that will have high final payouts, regardless of when you vote.

The real optimization is post selection, not vote timing. Vote on posts that will earn high rewards. That said, voting earlier gives you more time for your VP to regenerate for the next vote.
</think>

Since HF25 removed the reverse auction, vote timing is much less critical than post selection. Here is the current optimal strategy:

```python
from beem import Hive
from beem.account import Account
from beem.comment import Comment
from beem.blockchain import Blockchain
import time
from datetime import datetime, timedelta

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)


class OptimalCurationStrategy:
    """Post-HF25 curation strategy focused on post selection."""

    def __init__(self, account):
        self.account = account
        self.acc = Account(account, blockchain_instance=hive)

    # === Understanding Current Curation Math ===
    #
    # Post-HF25 (current Hive):
    # - No reverse auction penalty (vote anytime)
    # - Curation = 50% of post rewards
    # - Distributed proportionally by voter rshares
    # - YOUR curation = (your_rshares / total_rshares) * curation_pool
    #
    # This means:
    # - Vote timing does NOT matter for the formula
    # - What matters is: vote on posts with HIGH final payout
    # - Your rshares (vote value) matters -- higher HP = more rshares

    def estimate_vote_value(self):
        """Estimate the current value of a 100% vote."""
        self.acc.refresh()
        vp = self.acc.get_voting_power()
        vote_value = self.acc.get_vote_value(voting_power=vp)
        return vote_value, vp

    def evaluate_post_potential(self, author, permlink):
        """Score a post's potential for high final payout."""
        post = Comment(f"@{author}/{permlink}", blockchain_instance=hive)
        post.refresh()

        author_acc = Account(author, blockchain_instance=hive)
        signals = {}

        # Signal 1: Author's historical performance
        author_rep = author_acc.get_reputation()
        author_hp = author_acc.get_hive_power()
        signals["author_rep"] = author_rep
        signals["author_hp"] = author_hp

        # Signal 2: Early vote momentum
        active_votes = post.get("active_votes", [])
        total_rshares = sum(
            abs(int(v.get("rshares", 0))) for v in active_votes
        )
        signals["vote_count"] = len(active_votes)
        signals["total_rshares"] = total_rshares

        # Signal 3: Post age vs payout velocity
        created = post.get("created", "")
        if isinstance(created, str) and created:
            try:
                created_dt = datetime.strptime(
                    created, "%Y-%m-%dT%H:%M:%S"
                )
                age_hours = (
                    datetime.utcnow() - created_dt
                ).total_seconds() / 3600
                if age_hours > 0:
                    velocity = len(active_votes) / age_hours
                    signals["vote_velocity"] = velocity
            except ValueError:
                age_hours = 0

        # Scoring heuristic
        score = 0
        if author_rep > 60:
            score += 20
        if author_rep > 70:
            score += 10
        if author_hp > 5000:
            score += 15
        if signals.get("vote_velocity", 0) > 5:
            score += 25
        if len(active_votes) > 3 and total_rshares > 0:
            score += 20

        signals["score"] = score
        return signals

    def optimal_vote_schedule(self, max_votes_per_day=10):
        """Calculate optimal voting schedule for VP management.

        With 10 full votes per day, VP stays near 100%.
        Voting more frequently reduces individual vote value.
        """
        # VP regenerates at 20% per day (100% / 5 days)
        # Each 100% vote uses 2% VP
        # Equilibrium: 10 full votes/day uses 20% = regeneration rate

        regen_per_hour = 20.0 / 24.0  # ~0.833% per hour
        cost_per_vote = 2.0  # 2% VP per 100% vote

        interval_hours = 24.0 / max_votes_per_day
        vp_cost_per_day = max_votes_per_day * cost_per_vote

        print(f"=== Optimal Vote Schedule ===")
        print(f"Max votes/day: {max_votes_per_day}")
        print(f"Vote interval: every {interval_hours:.1f} hours")
        print(f"VP cost/day: {vp_cost_per_day:.0f}%")
        print(f"VP regen/day: 20%")
        print(f"Net VP change: {20 - vp_cost_per_day:+.0f}%/day")

        if vp_cost_per_day > 20:
            print("WARNING: Voting faster than regeneration!")
            sustainable = int(20 / cost_per_vote)
            print(f"Sustainable rate: {sustainable} full votes/day")

        return {
            "interval_hours": interval_hours,
            "sustainable": vp_cost_per_day <= 20,
            "votes_per_day": max_votes_per_day
        }


# === Practical Strategy ===

def curate_strategically(bot_account, target_tags):
    """The real optimal strategy: good post selection, not timing."""
    strategy = OptimalCurationStrategy(bot_account)

    vote_value, vp = strategy.estimate_vote_value()
    print(f"Current VP: {vp:.1f}% | Vote value: ${vote_value:.3f}")

    schedule = strategy.optimal_vote_schedule(max_votes_per_day=10)

    chain = Blockchain(blockchain_instance=hive)
    last_vote_time = 0

    for op in chain.stream(opNames=["comment"]):
        if op.get("parent_author", "") != "":
            continue

        # Enforce vote interval
        if time.time() - last_vote_time < schedule["interval_hours"] * 3600:
            continue

        # Evaluate post potential
        signals = strategy.evaluate_post_potential(
            op["author"], op["permlink"]
        )

        if signals["score"] >= 50:
            print(f"High potential: @{op['author']}/{op['permlink']} "
                  f"(score: {signals['score']})")
            # Vote logic here
            last_vote_time = time.time()


curate_strategically("mybotaccount", ["hive-dev"])
```

Post-HF25 summary: the reverse auction is gone, so vote at any time. The optimization is entirely in POST SELECTION -- vote on posts that will reach high final payouts. Maintain VP near 100% by limiting to ~10 full votes per day. Use author reputation, early vote momentum, and historical performance as selection signals.'''
    },
    {
        "instruction": r'''My Hive bot crashes occasionally and I lose track of which block it was processing. How should I implement checkpoint/resume so it does not reprocess or skip blocks?''',
        "output": r'''<think>
Checkpoint/resume for a block processor -- this is essential for production bots. Let me think about the requirements.

The bot needs to persist its current position (last processed block number) so that on restart, it picks up where it left off. Simple enough in concept, but there are edge cases.

Edge case 1: The bot processes block N, then crashes BEFORE writing the checkpoint. On restart, it reprocesses block N. This means operations must be idempotent -- processing the same block twice should produce the same result.

Edge case 2: The bot writes the checkpoint for block N, then crashes BEFORE processing block N+1. This is the normal case -- it resumes from N+1.

Edge case 3: The bot processes block N and writes the checkpoint atomically in the same database transaction. This is the gold standard -- either both happen or neither does.

Hmm, what about file-based checkpoints vs database checkpoints? File-based is simpler but not atomic with the processing. Database-based can be in the same transaction as the data writes.

I initially thought a simple JSON file would be fine, but there is a subtle issue. If the bot writes the checkpoint file and then the OS crashes before the file is flushed to disk, the file could be corrupted or contain partial data. Using fsync or atomic file writes (write to temp, then rename) prevents this.

The tradeoff is: file-based (simple, no DB dependency, slight corruption risk) vs database-based (atomic with processing, requires DB, more robust). For most bots, atomic file writes are good enough. For critical financial bots, database checkpoints are worth the complexity.

Actually, there is another approach: store the checkpoint in a custom_json on the blockchain itself. Then it is durable and accessible from anywhere. But that costs RC for every checkpoint write. Probably too expensive for per-block checkpointing.
</think>

Use atomic file-based checkpoints for simplicity, or database checkpoints for robustness. Here is both approaches with idempotent processing:

```python
import os
import json
import time
import tempfile
from beem import Hive
from beem.blockchain import Blockchain
from contextlib import contextmanager

hive = Hive(node=[
    "https://api.hive.blog",
    "https://api.deathwing.me"
])


# === Approach 1: Atomic File Checkpoint ===

class FileCheckpoint:
    """Atomic file-based checkpoint that survives crashes."""

    def __init__(self, filepath):
        self.filepath = filepath

    def load(self, default_block=None):
        """Load the last checkpoint, or return default."""
        try:
            with open(self.filepath, "r") as f:
                data = json.load(f)
                return data.get("last_block", default_block)
        except (FileNotFoundError, json.JSONDecodeError):
            return default_block

    def save(self, block_num):
        """Atomically save checkpoint using write-then-rename.

        This prevents corruption if the process crashes mid-write.
        """
        data = {
            "last_block": block_num,
            "timestamp": time.time(),
            "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

        # Write to temp file in same directory (same filesystem)
        dir_path = os.path.dirname(os.path.abspath(self.filepath))
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
                f.flush()
                os.fsync(f.fileno())  # force to disk
            # Atomic rename (on same filesystem)
            os.replace(tmp_path, self.filepath)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


# === Approach 2: Database Checkpoint (atomic with processing) ===

class DBCheckpoint:
    """Database checkpoint that commits atomically with data writes."""

    def __init__(self, db_connection, app_name="hive_bot"):
        self.db = db_connection
        self.app_name = app_name
        self._ensure_table()

    def _ensure_table(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS bot_checkpoints (
                app_name TEXT PRIMARY KEY,
                last_block INTEGER NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.commit()

    def load(self, default_block=None):
        row = self.db.execute(
            "SELECT last_block FROM bot_checkpoints WHERE app_name = ?",
            (self.app_name,)
        ).fetchone()
        return row[0] if row else default_block

    def save_in_transaction(self, block_num):
        """Save checkpoint -- caller must commit the transaction."""
        self.db.execute("""
            INSERT INTO bot_checkpoints (app_name, last_block, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(app_name) DO UPDATE SET
                last_block = EXCLUDED.last_block,
                updated_at = CURRENT_TIMESTAMP
        """, (self.app_name, block_num))
        # NOTE: do NOT commit here -- let the caller commit
        # so checkpoint is atomic with data processing


# === Resilient Block Processor ===

class ResilientBlockProcessor:
    """Block processor with checkpoint/resume and idempotent ops."""

    CHECKPOINT_INTERVAL = 10  # save checkpoint every N blocks

    def __init__(self, checkpoint, blockchain_instance):
        self.checkpoint = checkpoint
        self.hive = blockchain_instance
        self.chain = Blockchain(blockchain_instance=self.hive)
        self.blocks_since_checkpoint = 0

    def _process_block(self, block_num):
        """Process a single block. Must be idempotent."""
        block = self.hive.rpc.get_block(block_num)
        if block is None:
            return False

        for tx in block.get("transactions", []):
            for op in tx.get("operations", []):
                op_type = op[0] if isinstance(op, list) else op.get("type")
                op_data = op[1] if isinstance(op, list) else op.get("value")
                self._handle_operation(block_num, op_type, op_data)

        return True

    def _handle_operation(self, block_num, op_type, op_data):
        """Handle a single operation idempotently.

        Idempotent means: processing the same operation twice
        produces the same result as processing it once.
        Use INSERT ... ON CONFLICT DO NOTHING, or check-then-act.
        """
        if op_type == "custom_json" and op_data.get("id") == "myapp":
            # Example: upsert instead of insert to be idempotent
            print(f"Block {block_num}: custom_json from "
                  f"{op_data.get('required_posting_auths', ['?'])}")

    def run(self, default_start=None):
        """Main loop with checkpoint/resume."""
        if default_start is None:
            default_start = self.chain.get_current_block_num()

        current = self.checkpoint.load(default_block=default_start)
        # Resume from the NEXT block after the checkpoint
        current += 1
        print(f"Resuming from block {current}")

        while True:
            try:
                success = self._process_block(current)
                if not success:
                    time.sleep(1)
                    continue

                self.blocks_since_checkpoint += 1

                # Periodic checkpoint
                if self.blocks_since_checkpoint >= self.CHECKPOINT_INTERVAL:
                    self.checkpoint.save(current)
                    self.blocks_since_checkpoint = 0

                current += 1

            except KeyboardInterrupt:
                print(f"Shutting down. Saving checkpoint at block {current}")
                self.checkpoint.save(current)
                break
            except Exception as e:
                print(f"Error at block {current}: {e}")
                # Save checkpoint at last successful block
                self.checkpoint.save(current - 1)
                time.sleep(5)
                # Retry same block


# === Usage ===

checkpoint = FileCheckpoint("bot_checkpoint.json")
processor = ResilientBlockProcessor(checkpoint, hive)
processor.run(default_start=80000000)
```

Critical invariants: (1) the checkpoint records the last SUCCESSFULLY processed block, so on resume you start at checkpoint+1. (2) Processing must be idempotent to handle the case where you crash after processing but before checkpointing. (3) Atomic file writes (write-to-temp then rename) prevent checkpoint corruption. (4) Checkpoint every N blocks, not every block, to reduce IO overhead.'''
    },
]
