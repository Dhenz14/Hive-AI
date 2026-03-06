"""Hive blockchain training pairs: curation and voting strategies."""

PAIRS = [
    (
        "hive/curation-rewards-calculation",
        r'''How are curation rewards calculated on Hive? Explain the formula and factors that affect curation returns.''',
        r'''<think>
Curation rewards on Hive changed significantly with HF25:
- 50% of post rewards go to curators (50/50 split)
- Reverse auction window was removed (was 5 minutes)
- Curation rewards are proportional to vote weight and timing
- Earlier voters get a larger share if the post gets more votes later
- Vote weight decays with voting frequency (voting power)

The formula:
1. Total reward pool for a post is split 50% author / 50% curation
2. Curation share is distributed proportionally by rshares (weighted voting power)
3. The earlier you vote, the more of the curation pie you capture
4. But voting too early on bad content wastes your voting power

Since HF25, there is no penalty for voting at any time within the 7-day window.
</think>

Curation rewards on Hive follow a specific formula. Since HF25, the reverse auction window was removed, making the timing dynamics simpler but still strategic:

```python
from beem import Hive
from beem.account import Account
from beem.comment import Comment
from beem.amount import Amount
import math
from datetime import datetime

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

def calculate_vote_value(account_name, weight_pct=100):
    """Calculate the value of a vote at a given weight.

    Vote value depends on:
    - Account's Hive Power (including delegations)
    - Current voting power (mana)
    - Vote weight (1-100%)
    - Reward pool parameters
    """
    acct = Account(account_name, hive_instance=hive)
    props = hive.rpc.get_dynamic_global_properties()
    reward_fund = hive.rpc.get_reward_fund("post", api="condenser_api")

    # Get account vesting shares
    vesting = float(str(acct["vesting_shares"]).split()[0])
    received = float(str(acct["received_vesting_shares"]).split()[0])
    delegated = float(str(acct["delegated_vesting_shares"]).split()[0])
    effective_vests = vesting + received - delegated

    # Calculate voting power (0-10000, regenerates 20% per day)
    vp = acct.get("voting_power", 10000)

    # Calculate rshares (reward shares)
    used_power = int(vp * weight_pct * 100 / 10000)
    used_power = int((used_power + 49) / 50)  # Round up
    rshares = int(effective_vests * 1e6 * used_power / 10000)

    # Convert rshares to HBD value
    reward_balance = float(str(reward_fund["reward_balance"]).split()[0])
    recent_claims = int(reward_fund["recent_claims"])
    median_price = float(str(props.get("current_median_history", {}).get("base", "0.001 HBD")).split()[0])

    if recent_claims > 0:
        vote_value = (rshares * reward_balance / recent_claims) * median_price
    else:
        vote_value = 0

    print(f"@{account_name} vote at {weight_pct}% weight:")
    print(f"  Effective VESTS: {effective_vests:,.0f}")
    print(f"  Voting power:   {vp / 100:.2f}%")
    print(f"  rshares:        {rshares:,}")
    print(f"  Vote value:     ${vote_value:.4f}")
    print(f"  Curation (50%): ${vote_value / 2:.4f}")

    return vote_value

def estimate_curation_rewards(post_url, voter_account):
    """Estimate curation rewards for a voter on a specific post."""
    # Parse author/permlink from URL
    parts = post_url.rstrip("/").split("/")
    author = parts[-2].lstrip("@")
    permlink = parts[-1]

    post = Comment(f"@{author}/{permlink}", hive_instance=hive)
    active_votes = post.get("active_votes", [])

    # Calculate total rshares and our share
    total_rshares = sum(int(v.get("rshares", 0)) for v in active_votes)
    our_rshares = 0
    our_position = -1

    for i, v in enumerate(active_votes):
        if v["voter"] == voter_account:
            our_rshares = int(v.get("rshares", 0))
            our_position = i
            break

    if our_rshares <= 0:
        print(f"@{voter_account} has not voted on this post")
        return 0

    # Pending payout
    pending = float(str(post.get("pending_payout_value", "0 HBD")).split()[0])
    curation_pool = pending * 0.5  # 50% goes to curators

    # Our share of curation
    if total_rshares > 0:
        our_share = (our_rshares / total_rshares) * curation_pool
    else:
        our_share = 0

    print(f"Post: @{author}/{permlink}")
    print(f"  Pending payout:   ${pending:.3f}")
    print(f"  Curation pool:    ${curation_pool:.3f}")
    print(f"  Total voters:     {len(active_votes)}")
    print(f"  Your vote pos:    #{our_position + 1}")
    print(f"  Your rshares:     {our_rshares:,} / {total_rshares:,}")
    print(f"  Est. curation:    ${our_share:.4f}")

    return our_share

# Usage
calculate_vote_value("blocktrades", weight_pct=100)
```

Key curation facts since HF25:
- 50/50 split between author and curators
- No reverse auction penalty (vote anytime)
- Curation share is proportional to rshares contribution
- Voting power regenerates 20% per day (full recharge in 5 days)
- A 100% vote uses 2% of your voting power
- Voting when VP is depleted reduces your vote value significantly
'''
    ),
    (
        "hive/vote-weight-strategies",
        r'''How should I optimize vote weight on Hive to maximize curation rewards without depleting my voting power?''',
        r'''Optimizing vote weight is about balancing curation returns with voting power sustainability. Here is a strategic framework:

```python
from beem import Hive
from beem.account import Account
import math
import time

hive = Hive(node=["https://api.hive.blog"])

class VotingStrategy:
    """Manage vote weights to optimize curation efficiency."""

    def __init__(self, account_name, target_vp=80.0, daily_vote_budget=10):
        self.account_name = account_name
        self.target_vp = target_vp
        self.daily_budget = daily_vote_budget
        self.hive = hive

    def get_current_vp(self):
        """Get current voting power as percentage."""
        acct = Account(self.account_name, hive_instance=self.hive)
        vp = acct.get("voting_power", 10000)
        last_vote = acct.get("last_vote_time", "")

        # VP regenerates 20% per day (100% in 5 days)
        # That is 10000 mana per 5 days = 2000 per day
        if last_vote:
            try:
                last_dt = datetime.strptime(last_vote, "%Y-%m-%dT%H:%M:%S")
                elapsed_sec = (datetime.utcnow() - last_dt).total_seconds()
                regen = elapsed_sec * 10000 / (5 * 86400)
                vp = min(10000, vp + regen)
            except (ValueError, TypeError):
                pass

        return vp / 100  # Return as percentage

    def calculate_optimal_weight(self, post_quality_score):
        """Calculate optimal vote weight based on VP and quality.

        Args:
            post_quality_score: 1-10 rating of content quality

        The strategy:
        - Reserve 20% VP for unexpected great content
        - Distribute remaining VP across daily budget
        - Weight each vote by quality score
        """
        current_vp = self.get_current_vp()

        # Available VP to spend (above target threshold)
        available_vp = max(0, current_vp - self.target_vp)

        # Each 100% vote costs 2% VP
        # So available VP translates to votes:
        max_full_votes = available_vp / 2.0

        # Base weight from daily budget
        # 20% VP regen per day = 10 full votes per day
        base_weight_per_vote = min(100, 100 * 10 / self.daily_budget)

        # Adjust by quality (quadratic scaling rewards top content)
        quality_multiplier = (post_quality_score / 10) ** 1.5
        recommended_weight = base_weight_per_vote * quality_multiplier

        # Cap at 100% and ensure minimum 1%
        recommended_weight = max(1, min(100, recommended_weight))

        # If VP is low, reduce further
        if current_vp < self.target_vp:
            reduction = current_vp / self.target_vp
            recommended_weight *= reduction

        return round(recommended_weight)

    def daily_plan(self, posts_with_scores):
        """Plan votes for a set of posts with quality scores.

        Args:
            posts_with_scores: List of (post_id, quality_score) tuples
        """
        current_vp = self.get_current_vp()
        print(f"Current VP: {current_vp:.1f}%")
        print(f"Daily budget: {self.daily_budget} votes")
        print(f"Target VP: {self.target_vp}%\n")

        # Sort by quality (best first)
        sorted_posts = sorted(posts_with_scores, key=lambda x: -x[1])

        total_vp_cost = 0
        plan = []
        for post_id, score in sorted_posts[:self.daily_budget]:
            weight = self.calculate_optimal_weight(score)
            vp_cost = weight * 2 / 100  # Each 1% weight costs 0.02% VP
            total_vp_cost += vp_cost
            plan.append({
                "post": post_id,
                "quality": score,
                "weight": weight,
                "vp_cost": vp_cost
            })

        # Daily regen is 20%
        net_vp_change = 20 - total_vp_cost
        projected_vp = current_vp + net_vp_change

        print(f"{'Post':40s} {'Quality':>8} {'Weight':>8} {'VP Cost':>8}")
        print("-" * 66)
        for p in plan:
            print(f"{p['post']:40s} {p['quality']:>8.1f} "
                  f"{p['weight']:>7}% {p['vp_cost']:>7.2f}%")

        print(f"\nTotal VP cost:  {total_vp_cost:.2f}%")
        print(f"Daily regen:    20.00%")
        print(f"Net VP change:  {net_vp_change:+.2f}%")
        print(f"Projected VP:   {projected_vp:.1f}%")

        return plan

from datetime import datetime

# Usage
strategy = VotingStrategy("myaccount", target_vp=80.0, daily_vote_budget=10)
vp = strategy.get_current_vp()
print(f"Current VP: {vp:.1f}%")

# Plan daily votes
posts = [
    ("author1/great-post", 9.5),
    ("author2/good-post", 7.0),
    ("author3/decent-post", 5.0),
    ("author4/average-post", 4.0),
    ("author5/okay-post", 3.0),
]
strategy.daily_plan(posts)
```

Key principles:
- 10 full (100%) votes per day = sustainable at 20% daily regen
- VP below 80% means your votes are less valuable; let it recover
- Higher quality content deserves higher weight (non-linear scaling)
- Front-loading your best votes when VP is high maximizes returns
- Track your VP constantly; do not over-vote on a single day
'''
    ),
    (
        "hive/trail-voting",
        r'''How do I build a curation trail that automatically follows another account's votes on Hive?''',
        r'''A curation trail automatically mirrors another account's votes with configurable weight scaling. Here is a complete implementation:

```python
from beem import Hive
from beem.blockchain import Blockchain
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Vote
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("trail")

class CurationTrail:
    def __init__(self, follower_account, posting_key, nodes=None):
        self.account = follower_account
        self.hive = Hive(
            node=nodes or ["https://api.hive.blog", "https://api.deathwing.me"],
            keys=[posting_key]
        )
        self.leaders = {}
        self.voted_posts = set()
        self.min_vp = 75.0  # Minimum VP to trail

    def follow(self, leader_account, weight_scale=50, min_leader_weight=1000,
               delay_seconds=0, max_weight=10000):
        """Add a leader to follow.

        Args:
            leader_account: Account to follow
            weight_scale: Percentage of leader's weight to use (1-100)
            min_leader_weight: Minimum leader vote weight to trail (basis points)
            delay_seconds: Delay before trailing (for analysis)
            max_weight: Maximum weight for our vote (basis points)
        """
        self.leaders[leader_account] = {
            "scale": weight_scale,
            "min_weight": min_leader_weight,
            "delay": delay_seconds,
            "max_weight": max_weight
        }
        logger.info(f"Following @{leader_account} at {weight_scale}% scale")

    def unfollow(self, leader_account):
        """Stop following a leader."""
        if leader_account in self.leaders:
            del self.leaders[leader_account]
            logger.info(f"Unfollowed @{leader_account}")

    def _get_vp(self):
        """Get current voting power."""
        acct = Account(self.account, hive_instance=self.hive)
        return acct.get("voting_power", 0) / 100

    def _cast_vote(self, author, permlink, weight):
        """Cast a vote."""
        post_key = f"{author}/{permlink}"
        if post_key in self.voted_posts:
            return False

        op = Vote(**{
            "voter": self.account,
            "author": author,
            "permlink": permlink,
            "weight": weight
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "posting")
        tx.sign()
        result = tx.broadcast()

        self.voted_posts.add(post_key)
        logger.info(f"Voted @{author}/{permlink} at {weight/100:.0f}%")
        return True

    def _process_leader_vote(self, leader, vote_data):
        """Process a vote from a leader we follow."""
        config = self.leaders[leader]
        leader_weight = vote_data.get("weight", 0)

        # Check minimum weight
        if abs(leader_weight) < config["min_weight"]:
            return

        # Calculate our weight
        our_weight = int(leader_weight * config["scale"] / 100)
        our_weight = min(our_weight, config["max_weight"])
        our_weight = max(our_weight, -config["max_weight"])

        if our_weight == 0:
            return

        # Check VP
        vp = self._get_vp()
        if vp < self.min_vp:
            logger.warning(f"VP too low ({vp:.1f}%), skipping trail vote")
            return

        # Apply delay
        if config["delay"] > 0:
            logger.info(f"Delaying {config['delay']}s before trailing")
            time.sleep(config["delay"])

        author = vote_data["author"]
        permlink = vote_data["permlink"]
        self._cast_vote(author, permlink, our_weight)

    def run(self):
        """Main trail loop - stream votes and follow leaders."""
        blockchain = Blockchain(hive_instance=self.hive)
        leader_set = set(self.leaders.keys())

        logger.info(f"Trail started for @{self.account}")
        logger.info(f"Following: {', '.join(leader_set)}")

        stream = blockchain.stream(
            opNames=["vote"],
            raw_ops=False,
            threading=False
        )

        for op in stream:
            voter = op.get("voter", "")
            if voter in leader_set:
                try:
                    self._process_leader_vote(voter, op)
                except Exception as e:
                    logger.error(f"Trail vote error: {e}")

            # Refresh leader set periodically
            leader_set = set(self.leaders.keys())

# Usage
trail = CurationTrail("myaccount", "5MyPostingKey")
trail.follow("topauthor", weight_scale=50, delay_seconds=30)
trail.follow("trustedcurator", weight_scale=75, min_leader_weight=5000)
# trail.run()
```

The trail mirrors leader votes with configurable scaling, minimum weight thresholds, VP protection, and optional delay. The delay feature allows you to add manual review time before your vote is cast. Production trails should also implement deduplication persistence and blacklist support.
'''
    ),
    (
        "hive/auto-voting-system",
        r'''How do I build an auto-voting system that votes on posts from specific authors based on configurable rules?''',
        r'''Here is a rule-based auto-voting system that monitors the blockchain for posts from configured authors and votes based on customizable criteria:

```python
from beem import Hive
from beem.blockchain import Blockchain
from beem.account import Account
from beem.comment import Comment
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Vote
import json
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("autovote")

class AutoVoter:
    def __init__(self, voter_account, posting_key, nodes=None):
        self.account = voter_account
        self.hive = Hive(
            node=nodes or ["https://api.hive.blog"],
            keys=[posting_key]
        )
        self.rules = {}
        self.daily_votes = 0
        self.daily_limit = 20
        self.min_vp = 75.0
        self.last_reset = datetime.utcnow().date()

    def add_author_rule(self, author, weight_pct=100, delay_minutes=5,
                         tags_required=None, tags_excluded=None,
                         min_reputation=25, only_root_posts=True):
        """Configure auto-voting rules for an author."""
        self.rules[author] = {
            "weight": int(weight_pct * 100),  # Convert to basis points
            "delay": delay_minutes * 60,
            "tags_required": set(tags_required or []),
            "tags_excluded": set(tags_excluded or []),
            "min_reputation": min_reputation,
            "root_only": only_root_posts
        }

    def remove_author(self, author):
        if author in self.rules:
            del self.rules[author]

    def _check_daily_limit(self):
        today = datetime.utcnow().date()
        if today != self.last_reset:
            self.daily_votes = 0
            self.last_reset = today
        return self.daily_votes < self.daily_limit

    def _get_vp(self):
        acct = Account(self.account, hive_instance=self.hive)
        return acct.get("voting_power", 0) / 100

    def _check_post_rules(self, author, op_data):
        """Check if a post matches the author's rules."""
        rule = self.rules.get(author)
        if not rule:
            return False, 0

        # Check if it is a root post (not a comment)
        parent_author = op_data.get("parent_author", "")
        if rule["root_only"] and parent_author:
            return False, 0

        # Parse tags from json_metadata
        try:
            metadata = json.loads(op_data.get("json_metadata", "{}"))
            tags = set(metadata.get("tags", []))
        except (json.JSONDecodeError, TypeError):
            tags = set()

        # Check required tags
        if rule["tags_required"] and not rule["tags_required"] & tags:
            logger.debug(f"Post missing required tags: {rule['tags_required']}")
            return False, 0

        # Check excluded tags
        if rule["tags_excluded"] and rule["tags_excluded"] & tags:
            logger.debug(f"Post has excluded tag: {rule['tags_excluded'] & tags}")
            return False, 0

        return True, rule["weight"]

    def _cast_vote(self, author, permlink, weight):
        """Cast a vote on a post."""
        try:
            op = Vote(**{
                "voter": self.account,
                "author": author,
                "permlink": permlink,
                "weight": weight
            })
            tx = TransactionBuilder(hive_instance=self.hive)
            tx.appendOps(op)
            tx.appendSigner(self.account, "posting")
            tx.sign()
            result = tx.broadcast()
            self.daily_votes += 1
            logger.info(f"VOTED @{author}/{permlink} at {weight/100}% "
                        f"({self.daily_votes}/{self.daily_limit} today)")
            return True
        except Exception as e:
            logger.error(f"Vote failed: {e}")
            return False

    def run(self):
        """Main auto-voter loop."""
        blockchain = Blockchain(hive_instance=self.hive)
        author_set = set(self.rules.keys())

        logger.info(f"Auto-voter @{self.account} started")
        logger.info(f"Watching {len(author_set)} authors")

        stream = blockchain.stream(
            opNames=["comment"],
            raw_ops=False,
            threading=False
        )

        for op in stream:
            author = op.get("author", "")
            if author not in author_set:
                continue

            passes, weight = self._check_post_rules(author, op)
            if not passes:
                continue

            # Check limits
            if not self._check_daily_limit():
                logger.warning("Daily vote limit reached")
                continue

            vp = self._get_vp()
            if vp < self.min_vp:
                logger.warning(f"VP too low: {vp:.1f}%")
                continue

            # Apply delay
            delay = self.rules[author]["delay"]
            if delay > 0:
                logger.info(f"Waiting {delay}s before voting @{author}")
                time.sleep(delay)

            permlink = op.get("permlink", "")
            self._cast_vote(author, permlink, weight)

# Usage
voter = AutoVoter("myaccount", "5PostingKey")
voter.add_author_rule("favoriteauthor", weight_pct=100, delay_minutes=5)
voter.add_author_rule(
    "techwriter", weight_pct=50, delay_minutes=10,
    tags_required=["python", "hive-dev"],
    tags_excluded=["spam", "nsfw"]
)
voter.daily_limit = 15
voter.min_vp = 80.0
# voter.run()
```

This auto-voter supports per-author configuration with weight, delay, tag filtering, and daily limits. The delay feature is important for avoiding voting on posts that might get edited or deleted shortly after creation. Always respect community norms and avoid voting patterns that could be considered vote manipulation.
'''
    ),
    (
        "hive/curation-analytics",
        r'''How do I analyze my curation performance on Hive? Show me how to track curation rewards, APR, and efficiency.''',
        r'''Here is a comprehensive curation analytics tool that tracks your voting performance and curation returns:

```python
from beem import Hive
from beem.account import Account
from datetime import datetime, timedelta
import json

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

class CurationAnalytics:
    def __init__(self, account_name, hive_instance):
        self.account = account_name
        self.hive = hive_instance

    def _vests_to_hp(self, vests):
        props = self.hive.rpc.get_dynamic_global_properties()
        total_hive = float(str(props["total_vesting_fund_hive"]).split()[0])
        total_vests = float(str(props["total_vesting_shares"]).split()[0])
        return vests * total_hive / total_vests

    def get_curation_rewards(self, days=30, limit=1000):
        """Get curation reward history."""
        acct = Account(self.account, hive_instance=self.hive)
        history = acct.get_account_history(
            index=-1,
            limit=limit,
            only_ops=["curation_reward"]
        )

        cutoff = datetime.utcnow() - timedelta(days=days)
        rewards = []

        for entry in history:
            ts_str = entry.get("timestamp", "")
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
            except (ValueError, TypeError):
                continue

            if ts < cutoff:
                continue

            op = entry["op"]
            if isinstance(op, list):
                op_data = op[1]
            else:
                op_data = op

            reward_vests = float(str(op_data.get("reward", "0")).split()[0])
            reward_hp = self._vests_to_hp(reward_vests)

            rewards.append({
                "timestamp": ts_str,
                "author": op_data.get("comment_author", ""),
                "permlink": op_data.get("comment_permlink", ""),
                "reward_vests": reward_vests,
                "reward_hp": reward_hp
            })

        return rewards

    def calculate_curation_apr(self, days=30):
        """Calculate annualized curation APR."""
        acct = Account(self.account, hive_instance=self.hive)
        own_vests = float(str(acct["vesting_shares"]).split()[0])
        own_hp = self._vests_to_hp(own_vests)

        rewards = self.get_curation_rewards(days=days)
        total_hp_earned = sum(r["reward_hp"] for r in rewards)

        if own_hp > 0 and days > 0:
            daily_return = total_hp_earned / days
            annual_return = daily_return * 365
            apr = (annual_return / own_hp) * 100
        else:
            daily_return = 0
            annual_return = 0
            apr = 0

        print(f"=== Curation Performance for @{self.account} ===")
        print(f"Period: last {days} days")
        print(f"Own HP: {own_hp:,.3f}")
        print(f"Total curation rewards: {total_hp_earned:.3f} HP")
        print(f"Daily average: {daily_return:.4f} HP")
        print(f"Projected annual: {annual_return:.3f} HP")
        print(f"Curation APR: {apr:.2f}%")
        print(f"Rewards collected: {len(rewards)}")

        return {
            "total_hp": total_hp_earned,
            "daily_avg": daily_return,
            "annual_projected": annual_return,
            "apr": apr,
            "reward_count": len(rewards)
        }

    def top_curated_authors(self, days=30, limit=1000):
        """Find which authors earned you the most curation."""
        rewards = self.get_curation_rewards(days=days, limit=limit)

        author_totals = {}
        for r in rewards:
            author = r["author"]
            author_totals[author] = author_totals.get(author, 0) + r["reward_hp"]

        sorted_authors = sorted(
            author_totals.items(), key=lambda x: -x[1]
        )

        print(f"\nTop curated authors (last {days} days):")
        for author, hp in sorted_authors[:15]:
            print(f"  @{author:20s}: {hp:.4f} HP")

        return sorted_authors

    def daily_breakdown(self, days=14):
        """Show daily curation reward breakdown."""
        rewards = self.get_curation_rewards(days=days)

        daily = {}
        for r in rewards:
            date = r["timestamp"][:10]
            daily[date] = daily.get(date, 0) + r["reward_hp"]

        print(f"\nDaily curation rewards:")
        for date in sorted(daily.keys()):
            hp = daily[date]
            bar = "#" * int(hp * 100)
            print(f"  {date}: {hp:.4f} HP {bar}")

        return daily

# Usage
analytics = CurationAnalytics("blocktrades", hive)
analytics.calculate_curation_apr(days=30)
analytics.top_curated_authors(days=30)
analytics.daily_breakdown(days=14)
```

This analytics tool calculates your curation APR, identifies your most rewarding authors, and shows daily reward trends. The APR calculation considers your own HP (not delegated) as the principal. A typical well-optimized curation strategy yields 8-12% APR on Hive, though this varies with market conditions and the size of the reward pool.
'''
    ),
]
