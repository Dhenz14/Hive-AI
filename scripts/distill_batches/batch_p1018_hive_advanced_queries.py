"""
Hive blockchain advanced query training pairs: get_discussions_by, bridge.get_ranked_posts,
account_history filtering, following API, reputation calculation.
"""

PAIRS = [
    (
        "hive-advanced-ranked-posts",
        r'''How do I query ranked posts on Hive using the bridge API, including trending, hot, created, and community-specific feeds?''',
        r'''<think>
The bridge API (Hivemind) provides the primary way to query ranked content on Hive. The old condenser_api methods like get_discussions_by_trending are deprecated in favor of bridge.get_ranked_posts which is more flexible and performant. I need to show all the sort options, filtering, pagination, and community-scoped queries.
</think>

The **bridge API** (powered by Hivemind) is the recommended way to query ranked content on Hive. The old `condenser_api.get_discussions_by_*` methods are deprecated. Here is a comprehensive query library:

```python
import requests
import json
from datetime import datetime

HIVE_NODE = "https://api.hive.blog"

def bridge_call(method, params=None):
    """Call Hive bridge API method."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": f"bridge.{method}",
        "params": params or {}
    }
    resp = requests.post(HIVE_NODE, json=payload, timeout=15)
    result = resp.json()
    if "error" in result:
        raise Exception(f"API error: {result['error']}")
    return result["result"]

def get_ranked_posts(sort, tag=None, observer=None, limit=20, start_author=None, start_permlink=None):
    """
    Get ranked posts with flexible sorting.
    sort options: trending, hot, created, promoted, payout, payout_comments, muted
    tag: filter by tag or community (e.g., "hive-dev" or "python")
    observer: account name for personalized results (mute filtering)
    """
    params = {"sort": sort, "limit": limit}
    if tag:
        params["tag"] = tag
    if observer:
        params["observer"] = observer
    if start_author and start_permlink:
        params["start_author"] = start_author
        params["start_permlink"] = start_permlink
    posts = bridge_call("get_ranked_posts", params)
    return posts

def get_community_posts(community, sort="trending", limit=20):
    """
    Get posts from a specific Hive community.
    Communities are identified by their hive-XXXXXX name.
    """
    return get_ranked_posts(sort, tag=community, limit=limit)

def get_account_posts(account, sort="posts", limit=20, start_author=None, start_permlink=None):
    """
    Get posts by a specific account.
    sort options: posts, comments, replies, feed, payout
    - posts: top-level posts by the account
    - comments: comments/replies made by the account
    - replies: replies TO the account's posts
    - feed: posts from accounts the user follows
    - payout: posts with pending payout
    """
    params = {"account": account, "sort": sort, "limit": limit}
    if start_author and start_permlink:
        params["start_author"] = start_author
        params["start_permlink"] = start_permlink
    return bridge_call("get_account_posts", params)

def get_discussion(author, permlink):
    """Get a full discussion thread (post + all replies, nested)."""
    return bridge_call("get_discussion", {"author": author, "permlink": permlink})

def paginate_all_posts(account, sort="posts", max_posts=500):
    """Paginate through all posts from an account."""
    all_posts = []
    start_author = None
    start_permlink = None
    while len(all_posts) < max_posts:
        batch = get_account_posts(
            account, sort, limit=20,
            start_author=start_author, start_permlink=start_permlink
        )
        if not batch:
            break
        # Skip first item on continuation (it is the last item from prev page)
        if start_author and batch:
            batch = batch[1:]
        if not batch:
            break
        all_posts.extend(batch)
        last = batch[-1]
        start_author = last["author"]
        start_permlink = last["permlink"]
    return all_posts[:max_posts]

def search_by_multiple_tags(tags, sort="trending", limit=10):
    """
    Search for posts matching any of the given tags.
    Note: bridge API filters by one tag at a time,
    so we query each and merge results.
    """
    seen = set()
    merged = []
    for tag in tags:
        posts = get_ranked_posts(sort, tag=tag, limit=limit)
        for post in posts:
            key = f"{post['author']}/{post['permlink']}"
            if key not in seen:
                seen.add(key)
                post["matched_tag"] = tag
                merged.append(post)
    # Re-sort merged results
    if sort == "trending":
        merged.sort(key=lambda p: float(p.get("payout", 0)), reverse=True)
    elif sort == "created":
        merged.sort(key=lambda p: p.get("created", ""), reverse=True)
    return merged[:limit * 2]

def format_post_summary(post):
    """Format a post for display."""
    payout = post.get("payout", 0)
    votes = post.get("stats", {}).get("total_votes", 0)
    created = post.get("created", "")[:10]
    title = post.get("title", "(no title)")[:60]
    return (f"  @{post['author']}/{post['permlink'][:30]}\n"
            f"    {title}\n"
            f"    Payout: ${payout:.2f} | Votes: {votes} | Date: {created}")

# Usage examples
print("=== TRENDING POSTS ===")
trending = get_ranked_posts("trending", limit=5)
for post in trending:
    print(format_post_summary(post))

print("\n=== HOT IN PYTHON TAG ===")
hot_python = get_ranked_posts("hot", tag="python", limit=5)
for post in hot_python:
    print(format_post_summary(post))

print("\n=== COMMUNITY: hive-dev ===")
community = get_community_posts("hive-139531", sort="created", limit=5)
for post in community:
    print(format_post_summary(post))

print("\n=== ACCOUNT FEED ===")
feed = get_account_posts("myaccount", sort="feed", limit=5)
for post in feed:
    print(format_post_summary(post))

print("\n=== FULL DISCUSSION THREAD ===")
if trending:
    first = trending[0]
    discussion = get_discussion(first["author"], first["permlink"])
    print(f"Thread has {len(discussion)} posts/replies")
```

The bridge API is significantly more efficient than the old condenser_api discussion methods. Key differences: `get_ranked_posts` replaces all `get_discussions_by_*` methods with a single `sort` parameter. The `observer` parameter enables personalized feeds that respect mute lists. Community queries use the community name (e.g., "hive-139531") as the tag parameter. Pagination uses `start_author` and `start_permlink` from the last result. The `get_discussion` method returns the full comment tree for a post, making it easy to render threaded discussions.'''
    ),
    (
        "hive-advanced-account-history",
        r'''How do I efficiently query and filter account history on Hive to extract specific operation types like transfers, votes, or custom_json?''',
        r'''Account history on Hive stores every operation that affects an account. Efficient filtering requires understanding the pagination model (reverse chronological, batch fetching) and operation type filtering. Here is a production-quality history query library:

```python
import requests
import json
from datetime import datetime, timedelta
from collections import defaultdict

HIVE_NODE = "https://api.hive.blog"

def api_call(method, params):
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    resp = requests.post(HIVE_NODE, json=payload, timeout=30)
    return resp.json().get("result")

class AccountHistoryQuery:
    def __init__(self, account):
        self.account = account

    def get_history_batch(self, start=-1, limit=1000, operation_filter=None):
        """
        Fetch a batch of account history.
        start: -1 for most recent, or specific sequence number
        limit: max 1000 per call
        operation_filter: bitmask for filtering operation types (advanced)
        """
        params = [self.account, start, limit]
        result = api_call("condenser_api.get_account_history", params)
        return result or []

    def get_filtered_history(self, op_types=None, days_back=30, max_ops=5000):
        """
        Get filtered account history by operation type and time range.
        op_types: list of operation type strings, e.g. ["transfer", "vote"]
        """
        cutoff = datetime.utcnow() - timedelta(days=days_back)
        all_ops = []
        last_id = -1
        while len(all_ops) < max_ops:
            batch = self.get_history_batch(start=last_id, limit=1000)
            if not batch:
                break
            for item in batch:
                seq_id = item[0]
                op_data = item[1]
                timestamp = datetime.strptime(
                    op_data.get("timestamp", "2000-01-01T00:00:00"),
                    "%Y-%m-%dT%H:%M:%S"
                )
                if timestamp < cutoff:
                    return all_ops
                op_name = op_data.get("op", [None])[0]
                if op_types is None or op_name in op_types:
                    all_ops.append({
                        "seq": seq_id,
                        "timestamp": str(timestamp),
                        "type": op_name,
                        "data": op_data.get("op", [None, {}])[1],
                        "block": op_data.get("block"),
                        "trx_id": op_data.get("trx_id"),
                    })
            # Move to earlier history
            first_seq = batch[0][0]
            if first_seq <= 0:
                break
            last_id = first_seq - 1
        return all_ops

    def get_transfer_history(self, days_back=30, min_amount=0):
        """Get all transfers to/from this account."""
        ops = self.get_filtered_history(
            op_types=["transfer", "transfer_to_vesting",
                       "transfer_to_savings", "transfer_from_savings"],
            days_back=days_back
        )
        transfers = []
        for op in ops:
            data = op["data"]
            amount_str = data.get("amount", "0 HIVE")
            parts = amount_str.split()
            amount_val = float(parts[0])
            asset = parts[1] if len(parts) > 1 else "HIVE"
            if amount_val >= min_amount:
                transfers.append({
                    "timestamp": op["timestamp"],
                    "type": op["type"],
                    "from": data.get("from", ""),
                    "to": data.get("to", ""),
                    "amount": amount_val,
                    "asset": asset,
                    "memo": data.get("memo", ""),
                    "trx_id": op["trx_id"],
                })
        return transfers

    def get_vote_history(self, days_back=7):
        """Get all votes cast by this account."""
        ops = self.get_filtered_history(op_types=["vote"], days_back=days_back)
        votes = []
        for op in ops:
            data = op["data"]
            votes.append({
                "timestamp": op["timestamp"],
                "author": data.get("author", ""),
                "permlink": data.get("permlink", ""),
                "weight": data.get("weight", 0),  # -10000 to 10000
                "voter": data.get("voter", ""),
            })
        return votes

    def get_custom_json_history(self, json_id=None, days_back=30):
        """Get custom_json operations, optionally filtered by id."""
        ops = self.get_filtered_history(
            op_types=["custom_json"], days_back=days_back
        )
        results = []
        for op in ops:
            data = op["data"]
            op_id = data.get("id", "")
            if json_id and op_id != json_id:
                continue
            try:
                parsed_json = json.loads(data.get("json", "{}"))
            except json.JSONDecodeError:
                parsed_json = data.get("json", "")
            results.append({
                "timestamp": op["timestamp"],
                "id": op_id,
                "json": parsed_json,
                "required_auths": data.get("required_auths", []),
                "required_posting_auths": data.get("required_posting_auths", []),
            })
        return results

    def get_operation_summary(self, days_back=30):
        """Get a summary of all operation types and counts."""
        ops = self.get_filtered_history(days_back=days_back, max_ops=10000)
        counts = defaultdict(int)
        daily_counts = defaultdict(lambda: defaultdict(int))
        for op in ops:
            counts[op["type"]] += 1
            day = op["timestamp"][:10]
            daily_counts[day][op["type"]] += 1
        return {
            "total_operations": len(ops),
            "operation_counts": dict(sorted(counts.items(), key=lambda x: -x[1])),
            "daily_breakdown": {
                day: dict(ops_dict)
                for day, ops_dict in sorted(daily_counts.items())
            },
            "period_days": days_back,
        }

    def get_reward_history(self, days_back=30):
        """Get author and curation reward history."""
        ops = self.get_filtered_history(
            op_types=["author_reward", "curation_reward"],
            days_back=days_back
        )
        author_rewards = []
        curation_rewards = []
        for op in ops:
            if op["type"] == "author_reward":
                data = op["data"]
                author_rewards.append({
                    "timestamp": op["timestamp"],
                    "permlink": data.get("permlink", ""),
                    "hbd_payout": data.get("hbd_payout", "0 HBD"),
                    "hive_payout": data.get("hive_payout", "0 HIVE"),
                    "vesting_payout": data.get("vesting_payout", "0 VESTS"),
                })
            elif op["type"] == "curation_reward":
                data = op["data"]
                curation_rewards.append({
                    "timestamp": op["timestamp"],
                    "reward": data.get("reward", "0 VESTS"),
                    "author": data.get("comment_author", ""),
                    "permlink": data.get("comment_permlink", ""),
                })
        return {"author_rewards": author_rewards, "curation_rewards": curation_rewards}

# Usage
query = AccountHistoryQuery("blocktrades")

# Get recent large transfers
transfers = query.get_transfer_history(days_back=7, min_amount=100)
print(f"Large transfers (7 days): {len(transfers)}")
for t in transfers[:5]:
    print(f"  {t['timestamp'][:10]}: {t['from']} -> {t['to']}: "
          f"{t['amount']} {t['asset']}")

# Get vote history
votes = query.get_vote_history(days_back=1)
print(f"\nVotes cast (1 day): {len(votes)}")

# Get operation summary
summary = query.get_operation_summary(days_back=7)
print(f"\nOperation summary (7 days):")
print(f"  Total operations: {summary['total_operations']}")
for op_type, count in list(summary["operation_counts"].items())[:10]:
    print(f"  {op_type}: {count}")

# Get Hive Engine operations
engine_ops = query.get_custom_json_history(json_id="ssc-mainnet-hive", days_back=7)
print(f"\nHive Engine operations (7 days): {len(engine_ops)}")
```

Key optimization tips: (1) The `get_account_history` API returns operations in reverse chronological order, paginate using the sequence number from the first item in each batch. (2) For very active accounts, use the `operation_filter_low` and `operation_filter_high` bitmask parameters (database_api version) to filter at the node level. (3) Cache results since historical operations are immutable. (4) For real-time monitoring, combine history queries with blockchain streaming for completeness.'''
    ),
    (
        "hive-advanced-following-api",
        r'''How do I use the Hive following API to get followers, following lists, and build social graph features?''',
        r'''The Hive following API provides follower/following relationships, mute lists, and reblog tracking. These are managed through Hivemind (the social consensus layer). Here is a complete social graph toolkit:

```python
import requests
import json
from collections import defaultdict

HIVE_NODE = "https://api.hive.blog"

def api_call(method, params):
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    resp = requests.post(HIVE_NODE, json=payload, timeout=15)
    return resp.json().get("result")

def bridge_call(method, params):
    payload = {"jsonrpc": "2.0", "method": f"bridge.{method}", "params": params, "id": 1}
    resp = requests.post(HIVE_NODE, json=payload, timeout=15)
    return resp.json().get("result")

class HiveSocialGraph:
    def __init__(self, account):
        self.account = account

    def get_all_followers(self):
        """Get complete list of followers (paginates automatically)."""
        followers = []
        start = ""
        while True:
            batch = api_call("condenser_api.get_followers",
                           [self.account, start, "blog", 1000])
            if not batch:
                break
            if start and batch:
                batch = batch[1:]  # Skip duplicate from pagination
            if not batch:
                break
            followers.extend([f["follower"] for f in batch])
            start = batch[-1]["follower"]
        return followers

    def get_all_following(self):
        """Get complete list of accounts being followed."""
        following = []
        start = ""
        while True:
            batch = api_call("condenser_api.get_following",
                           [self.account, start, "blog", 1000])
            if not batch:
                break
            if start and batch:
                batch = batch[1:]
            if not batch:
                break
            following.extend([f["following"] for f in batch])
            start = batch[-1]["following"]
        return following

    def get_muted_accounts(self):
        """Get list of accounts muted by this user."""
        muted = []
        start = ""
        while True:
            # "ignore" type returns muted accounts
            batch = api_call("condenser_api.get_following",
                           [self.account, start, "ignore", 1000])
            if not batch:
                break
            if start and batch:
                batch = batch[1:]
            if not batch:
                break
            muted.extend([f["following"] for f in batch])
            start = batch[-1]["following"]
        return muted

    def get_follower_count(self):
        """Get follower and following counts."""
        result = api_call("condenser_api.get_follow_count", [self.account])
        return result

    def find_mutual_followers(self, other_account):
        """Find accounts that follow both self and other_account."""
        my_followers = set(self.get_all_followers())
        other = HiveSocialGraph(other_account)
        other_followers = set(other.get_all_followers())
        mutual = my_followers.intersection(other_followers)
        return {
            "mutual_followers": sorted(list(mutual)),
            "count": len(mutual),
            "only_follow_me": len(my_followers - other_followers),
            "only_follow_them": len(other_followers - my_followers),
        }

    def find_mutual_following(self, other_account):
        """Find accounts that both self and other_account follow."""
        my_following = set(self.get_all_following())
        other = HiveSocialGraph(other_account)
        other_following = set(other.get_all_following())
        mutual = my_following.intersection(other_following)
        return sorted(list(mutual))

    def get_follow_relationship(self, other_account):
        """Check the follow relationship between two accounts."""
        # Check if self follows other
        i_follow = api_call("condenser_api.get_following",
                           [self.account, other_account, "blog", 1])
        self_follows_other = (i_follow and len(i_follow) > 0 and
                              i_follow[0].get("following") == other_account)
        # Check if other follows self
        they_follow = api_call("condenser_api.get_followers",
                              [self.account, other_account, "blog", 1])
        other_follows_self = (they_follow and len(they_follow) > 0 and
                              they_follow[0].get("follower") == other_account)
        # Check mute status
        mute_check = api_call("condenser_api.get_following",
                             [self.account, other_account, "ignore", 1])
        is_muted = (mute_check and len(mute_check) > 0 and
                    mute_check[0].get("following") == other_account)
        return {
            "i_follow_them": self_follows_other,
            "they_follow_me": other_follows_self,
            "mutual": self_follows_other and other_follows_self,
            "i_muted_them": is_muted,
        }

    def get_account_notifications(self, limit=50):
        """Get recent notifications for the account via bridge API."""
        return bridge_call("account_notifications",
                          {"account": self.account, "limit": limit})

    def get_rebloggers(self, permlink):
        """Get list of accounts that reblogged a specific post."""
        result = api_call("condenser_api.get_reblogged_by",
                         [self.account, permlink])
        return result or []

    def build_influence_score(self):
        """
        Calculate a simple influence score based on social metrics.
        """
        counts = self.get_follower_count()
        followers = counts.get("follower_count", 0)
        following = counts.get("following_count", 0)
        # Follower-to-following ratio (higher = more influential)
        ratio = followers / max(following, 1)
        # Get profile for reputation
        profile = bridge_call("get_profile", {"account": self.account})
        reputation = profile.get("metadata", {}).get("profile", {})
        return {
            "account": self.account,
            "followers": followers,
            "following": following,
            "ratio": round(ratio, 2),
            "influence_tier": (
                "whale" if followers > 5000 else
                "orca" if followers > 1000 else
                "dolphin" if followers > 200 else
                "minnow" if followers > 50 else
                "plankton"
            ),
        }

# Usage
social = HiveSocialGraph("blocktrades")
counts = social.get_follower_count()
print(f"@{social.account}: {counts['follower_count']} followers, "
      f"{counts['following_count']} following")

# Check relationship
rel = social.get_follow_relationship("ausbitbank")
print(f"Relationship with @ausbitbank: {rel}")

# Influence score
score = social.build_influence_score()
print(f"Influence: {score['influence_tier']} (ratio: {score['ratio']})")

# Get notifications
notifs = social.get_account_notifications(limit=5)
if notifs:
    for n in notifs:
        print(f"  {n.get('type')}: {n.get('msg', '')[:60]}")
```

The following API uses three relationship types: "blog" (follow), "ignore" (mute), and "reblog" (used internally for reblogs). Pagination is alphabetical by account name using the `start` parameter. The bridge API's `account_notifications` method provides a unified notification feed including mentions, replies, follows, votes, and reblogs. For building recommendation engines, combine the mutual follower analysis with content tag overlap analysis to suggest accounts to follow.'''
    ),
    (
        "hive-advanced-reputation",
        r'''How is Hive reputation calculated, and how can I compute it programmatically from the raw reputation value?''',
        r'''Hive reputation is stored as a raw integer that needs logarithmic transformation to produce the human-readable score displayed on frontends. The raw value starts at 0 for new accounts and increases/decreases based on votes received from accounts with higher reputation. Here is the math and implementation:

```python
import math
import requests

HIVE_NODE = "https://api.hive.blog"

def api_call(method, params):
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    resp = requests.post(HIVE_NODE, json=payload, timeout=15)
    return resp.json().get("result")

def raw_to_reputation(raw_reputation):
    """
    Convert raw reputation integer to the display score (e.g., 25, 50, 72).

    The formula used by all Hive frontends:
    1. Take the log10 of the absolute value of raw reputation
    2. Subtract 9 (to normalize the starting point)
    3. Multiply by 9 (to spread the scale)
    4. Add 25 (base reputation for new accounts)
    5. Apply sign (negative reputation is possible but rare)

    Raw reputation of 0 maps to 25 (default for new accounts).
    The scale is logarithmic, so each point requires ~10x more
    vote value than the previous point.
    """
    if raw_reputation is None or raw_reputation == 0:
        return 25

    # Handle string input (API sometimes returns strings)
    raw = int(raw_reputation)

    # Determine sign
    is_negative = raw < 0
    raw = abs(raw)

    log_rep = math.log10(max(raw, 1))

    # The formula: (log10(raw) - 9) * 9 + 25
    # 9 is subtracted because new accounts start around 10^9
    reputation = (log_rep - 9) * 9 + 25

    if is_negative:
        reputation = -reputation

    return round(reputation, 2)

def reputation_to_raw_estimate(target_rep):
    """
    Estimate the raw reputation needed for a target display score.
    Useful for calculating how much vote value is needed to reach a target.
    """
    if target_rep <= 25:
        return 0
    # Reverse the formula: raw = 10^((rep - 25) / 9 + 9)
    exponent = (target_rep - 25) / 9 + 9
    return int(10 ** exponent)

def get_account_reputation(username):
    """Get reputation for a single account."""
    accounts = api_call("condenser_api.get_accounts", [[username]])
    if not accounts:
        return None
    raw = int(accounts[0].get("reputation", 0))
    display = raw_to_reputation(raw)
    return {
        "account": username,
        "raw_reputation": raw,
        "display_reputation": display,
    }

def get_reputation_batch(usernames):
    """Get reputation for multiple accounts efficiently."""
    accounts = api_call("condenser_api.get_accounts", [usernames])
    results = []
    for acct in accounts:
        raw = int(acct.get("reputation", 0))
        results.append({
            "account": acct["name"],
            "raw": raw,
            "display": raw_to_reputation(raw),
        })
    results.sort(key=lambda x: -x["raw"])
    return results

class ReputationAnalyzer:
    """Analyze reputation distribution and progression."""

    REPUTATION_TIERS = [
        (80, "Legendary"),
        (70, "Whale"),
        (65, "Orca"),
        (60, "Dolphin"),
        (50, "Minnow"),
        (40, "Red Fish"),
        (25, "Plankton"),
        (0, "Gray Listed"),
        (-1, "Black Listed"),
    ]

    @classmethod
    def get_tier(cls, display_rep):
        for threshold, name in cls.REPUTATION_TIERS:
            if display_rep >= threshold:
                return name
        return "Unknown"

    @classmethod
    def analyze_reputation(cls, username):
        """Full reputation analysis for an account."""
        rep_data = get_account_reputation(username)
        if not rep_data:
            return None
        display = rep_data["display_reputation"]
        raw = rep_data["raw_reputation"]
        tier = cls.get_tier(display)
        # Calculate progress to next tier
        current_tier_threshold = 25
        next_tier_threshold = 25
        for threshold, name in reversed(cls.REPUTATION_TIERS):
            if display >= threshold:
                current_tier_threshold = threshold
                break
        for threshold, name in cls.REPUTATION_TIERS:
            if threshold > display:
                next_tier_threshold = threshold
                break
        # Raw reputation needed for next tier
        raw_for_next = reputation_to_raw_estimate(next_tier_threshold)
        progress = 0
        if next_tier_threshold > current_tier_threshold:
            raw_for_current = reputation_to_raw_estimate(current_tier_threshold)
            if raw_for_next > raw_for_current:
                progress = (raw - raw_for_current) / (raw_for_next - raw_for_current) * 100
                progress = max(0, min(100, progress))
        return {
            "account": username,
            "raw_reputation": raw,
            "display_reputation": display,
            "tier": tier,
            "next_tier": next_tier_threshold,
            "progress_to_next": round(progress, 1),
            "raw_needed_for_next": raw_for_next,
            "raw_remaining": max(0, raw_for_next - raw),
        }

    @classmethod
    def compare_reputations(cls, usernames):
        """Compare reputation across multiple accounts."""
        reps = get_reputation_batch(usernames)
        print(f"{'Account':<20} {'Display':>8} {'Tier':<12} {'Raw':>20}")
        print("-" * 65)
        for r in reps:
            tier = cls.get_tier(r["display"])
            print(f"{r['account']:<20} {r['display']:>8.2f} {tier:<12} {r['raw']:>20}")
        return reps

    @classmethod
    def reputation_scale_reference(cls):
        """Print the full reputation scale for reference."""
        print("Hive Reputation Scale Reference")
        print("=" * 50)
        print(f"{'Display Rep':>12} {'Raw Rep Needed':>20} {'Tier':<15}")
        print("-" * 50)
        for rep in range(25, 81, 5):
            raw = reputation_to_raw_estimate(rep)
            tier = cls.get_tier(rep)
            print(f"{rep:>12} {raw:>20,} {tier:<15}")
        print()
        print("Key insight: Each +9 points requires ~10x more raw reputation.")
        print("Going from 25->34 is 10x easier than going from 34->43.")

# Usage
rep = get_account_reputation("blocktrades")
print(f"@blocktrades: {rep['display_reputation']} (raw: {rep['raw_reputation']})")

analysis = ReputationAnalyzer.analyze_reputation("blocktrades")
print(f"Tier: {analysis['tier']}, Progress to next: {analysis['progress_to_next']}%")

print("\nReputation comparison:")
ReputationAnalyzer.compare_reputations(["blocktrades", "ausbitbank", "acidyo"])

print()
ReputationAnalyzer.reputation_scale_reference()
```

Key facts about Hive reputation: (1) The scale is logarithmic -- each +9 display points requires roughly 10x more raw reputation. (2) Only votes from accounts with HIGHER reputation than yours can affect your score. (3) Downvotes from higher-rep accounts reduce reputation. (4) New accounts start at raw 0, which displays as 25. (5) Reputation below 0 (display below 25) causes content to be hidden on most frontends. (6) The maximum practical reputation is around 80 -- very few accounts exceed this. (7) Reputation cannot be transferred or purchased directly; it is earned through receiving upvotes on content from reputable accounts.'''
    ),
    (
        "hive-advanced-database-api",
        r'''How do I use the Hive database_api for structured queries with find and list methods, including proper parameter formatting?''',
        r'''The database_api provides structured access to chain state using `find_*` and `list_*` methods with JSON parameters. Unlike condenser_api which uses positional array parameters, database_api uses named parameters for clarity. Here is a comprehensive reference:

```python
import requests
import json
from datetime import datetime

HIVE_NODE = "https://api.hive.blog"

def database_api_call(method, params=None):
    """
    Call database_api methods.
    Unlike condenser_api, database_api uses named params in a dict.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": f"database_api.{method}",
        "params": params or {}
    }
    resp = requests.post(HIVE_NODE, json=payload, timeout=15)
    result = resp.json()
    if "error" in result:
        raise Exception(f"API error: {result['error']['message']}")
    return result["result"]

# === Account Queries ===

def find_accounts(names):
    """Find specific accounts by name."""
    result = database_api_call("find_accounts", {"accounts": names})
    accounts = result.get("accounts", [])
    for acct in accounts:
        print(f"@{acct['name']}: {acct['balance']} | "
              f"HP vests: {acct['vesting_shares']}")
    return accounts

def list_accounts(start="", limit=10, order="by_name"):
    """List accounts with pagination."""
    result = database_api_call("list_accounts", {
        "start": start, "limit": limit, "order": order
    })
    return result.get("accounts", [])

# === Witness Queries ===

def find_witnesses(owners):
    """Find witnesses by owner account name."""
    result = database_api_call("find_witnesses", {"owners": owners})
    witnesses = result.get("witnesses", [])
    for w in witnesses:
        print(f"Witness @{w['owner']}: votes={w['votes']}, "
              f"url={w.get('url', 'N/A')}")
    return witnesses

def list_witnesses(start="", limit=21, order="by_vote_name"):
    """
    List witnesses sorted by votes.
    order options: by_name, by_vote_name, by_schedule_time
    """
    result = database_api_call("list_witnesses", {
        "start": ["", start] if order == "by_vote_name" else start,
        "limit": limit,
        "order": order
    })
    return result.get("witnesses", [])

# === Proposal (DHF) Queries ===

def list_proposals(start=None, limit=50, order="by_total_votes",
                   order_direction="descending", status="all"):
    """
    List DHF proposals.
    order: by_creator, by_start_date, by_end_date, by_total_votes
    status: all, inactive, active, expired, votable
    """
    params = {
        "start": start or [""],
        "limit": limit,
        "order": order,
        "order_direction": order_direction,
        "status": status,
    }
    result = database_api_call("list_proposals", params)
    proposals = result.get("proposals", [])
    for p in proposals:
        print(f"#{p['id']}: {p['subject'][:50]} by @{p['creator']} "
              f"- {p['daily_pay']} daily")
    return proposals

def find_proposals(proposal_ids):
    """Find specific proposals by ID."""
    result = database_api_call("find_proposals", {"proposal_ids": proposal_ids})
    return result.get("proposals", [])

# === Vesting Delegation Queries ===

def find_vesting_delegations(account):
    """Find all outgoing vesting delegations from an account."""
    result = database_api_call("find_vesting_delegations", {"account": account})
    delegations = result.get("delegations", [])
    for d in delegations:
        print(f"@{d['delegator']} -> @{d['delegatee']}: "
              f"{d['vesting_shares']}")
    return delegations

# === Block and Transaction Queries ===

def get_block_range(starting_block, count=10):
    """Get a range of blocks using block_api."""
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "block_api.get_block_range",
        "params": {"starting_block_num": starting_block, "count": count}
    }
    resp = requests.post(HIVE_NODE, json=payload, timeout=15)
    return resp.json().get("result", {}).get("blocks", [])

# === Dynamic Global Properties ===

def get_dynamic_global_properties():
    """Get chain state using database_api format."""
    result = database_api_call("get_dynamic_global_properties")
    key_fields = [
        "head_block_number", "head_block_id", "time",
        "current_supply", "current_hbd_supply",
        "total_vesting_fund_hive", "total_vesting_shares",
        "hbd_interest_rate", "hbd_print_rate",
        "current_witness", "num_pow_witnesses",
    ]
    for field in key_fields:
        if field in result:
            val = result[field]
            if isinstance(val, dict) and "amount" in val:
                # database_api returns amounts as {amount, precision, nai}
                amount = int(val["amount"]) / (10 ** val["precision"])
                nai = val.get("nai", "")
                token_map = {"@@000000021": "HIVE", "@@000000013": "HBD",
                            "@@000000037": "VESTS"}
                symbol = token_map.get(nai, nai)
                print(f"  {field}: {amount:.3f} {symbol}")
            else:
                print(f"  {field}: {val}")
    return result

# === RC (Resource Credits) Queries ===

def find_rc_accounts(accounts):
    """Get RC status for accounts using rc_api."""
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "rc_api.find_rc_accounts",
        "params": {"accounts": accounts}
    }
    resp = requests.post(HIVE_NODE, json=payload, timeout=15)
    rc_accounts = resp.json().get("result", {}).get("rc_accounts", [])
    for rc in rc_accounts:
        max_rc = int(rc.get("max_rc", 0))
        # RC percentage requires calculating current RC from mana
        rc_mana = int(rc.get("rc_manabar", {}).get("current_mana", 0))
        pct = (rc_mana / max_rc * 100) if max_rc > 0 else 0
        print(f"@{rc['account']}: {pct:.1f}% RC ({rc_mana:,} / {max_rc:,})")
    return rc_accounts

# === Comprehensive Query Example ===

def chain_overview():
    """Print a comprehensive chain state overview."""
    print("=== HIVE CHAIN OVERVIEW ===")
    print()
    print("-- Global Properties --")
    props = get_dynamic_global_properties()
    print()
    print("-- Top Witnesses --")
    witnesses = list_witnesses(limit=5)
    for w in witnesses:
        print(f"  @{w['owner']}: {int(w['votes']) / 1e12:.0f}T votes")
    print()
    print("-- Active Proposals --")
    proposals = list_proposals(limit=5, status="active")
    print()
    print("-- RC Status --")
    find_rc_accounts(["blocktrades", "acidyo"])

chain_overview()
```

Key differences between database_api and condenser_api: (1) database_api uses named JSON parameters instead of positional arrays. (2) Amount values are returned as `{amount, precision, nai}` objects instead of strings like "1.000 HIVE". (3) The NAI (Numeric Asset Identifier) codes are @@000000021 for HIVE, @@000000013 for HBD, and @@000000037 for VESTS. (4) `list_*` methods support different sort orders via the `order` parameter. (5) `find_*` methods look up specific records by key. The database_api is preferred for applications that need structured data parsing since the response format is more consistent and machine-friendly.'''
    ),
]
