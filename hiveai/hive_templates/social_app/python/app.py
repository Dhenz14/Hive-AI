"""
============================================================================
 HIVE SOCIAL APP -- Python / Flask / beem
============================================================================

 A fully working Hive blockchain social application that doubles as a
 tutorial. Every Hive-specific line has a comment explaining the concept
 so you can learn the blockchain while building on it.

 Endpoints:
   GET  /api/feed/<tag>                 -- Fetch posts by tag (trending/created/hot)
   GET  /api/post/<author>/<permlink>  -- Get single post with comments
   GET  /api/account/<username>        -- Account info (HP, RC, balances, profile)
   GET  /api/notifications/<username>  -- Recent account history (votes, mentions)
   POST /api/post                      -- Publish a new blog post
   POST /api/vote                      -- Upvote or downvote a post
   POST /api/comment                   -- Reply to a post or comment
   POST /api/follow                    -- Follow or unfollow a user
   POST /api/reblog                    -- Reblog (resteem) a post

 Usage:
   cp .env.example .env          # fill in your keys
   pip install -r requirements.txt
   python app.py

 Requires Python 3.9+.
============================================================================
"""

import json
import math
import os
import re
import time
import traceback

from dotenv import load_dotenv
from flask import Flask, jsonify, request

# HIVE CONCEPT: beem is the most comprehensive Python library for the
# Hive blockchain. It handles account management, transaction signing,
# broadcasting operations, and querying blockchain data.
#
# Key beem classes:
#   Hive        -- blockchain connection (node selection, key management)
#   Account     -- query account data (balances, HP, RC, profile)
#   Comment     -- read/create posts and comments
#   Vote        -- cast votes
#   Discussions -- query posts by tag, trending, etc.
from beem import Hive
from beem.account import Account
from beem.comment import Comment
from beem.discussions import (
    Discussions_by_created,
    Discussions_by_hot,
    Discussions_by_trending,
)
from beem.exceptions import (
    AccountDoesNotExistsException,
    ContentDoesNotExistsException,
    MissingKeyError,
)
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import (
    Comment as CommentOperation,
    Comment_options,
    Custom_json,
    Vote,
)

# ---------------------------------------------------------------------------
#  1. CONFIGURATION
# ---------------------------------------------------------------------------

load_dotenv()

app = Flask(__name__)

# HIVE CONCEPT: Hive is a decentralized blockchain with many public API
# nodes run by independent operators. If one node is down or slow, beem
# can be configured to try the next one. This list is ordered by reliability.
# You can find live node status at https://beacon.peakd.com/
HIVE_NODES = [
    os.getenv("HIVE_NODE", "https://api.hive.blog"),
    "https://api.deathwing.me",
    "https://anyx.io",
    "https://rpc.ausbit.dev",
    "https://hive-api.arcange.eu",
]

USERNAME = os.getenv("HIVE_USERNAME", "")
POSTING_KEY = os.getenv("HIVE_POSTING_KEY", "")

# ---------------------------------------------------------------------------
#  2. HIVE CLIENT SETUP -- Node Failover
# ---------------------------------------------------------------------------

# HIVE CONCEPT: Hive has 4 key types with different permission levels:
#
#   POSTING KEY  -- social actions: post, vote, comment, reblog, follow.
#                   This is the ONLY key your social app should ever need.
#                   If compromised, the attacker can spam but NOT steal funds.
#
#   ACTIVE KEY   -- financial actions: transfer HIVE/HBD, power up/down,
#                   convert HBD, set witness proxy, update profile metadata.
#                   Treat this like a bank password.
#
#   OWNER KEY    -- account recovery, change all other keys.
#                   Should be stored offline in cold storage.
#                   NEVER use in any application.
#
#   MEMO KEY     -- encrypts/decrypts private memos attached to transfers.
#                   Low risk but unrelated to social features.
#
# Private keys on Hive are WIF-encoded (Wallet Import Format) strings
# that start with the number "5". They are 51 characters long.

# HIVE CONCEPT: beem's Hive() class manages the blockchain connection.
# Passing `keys=[posting_key]` makes the key available for signing
# transactions. The `node` parameter accepts a list for automatic failover.
# `num_retries` controls how many times to retry a failed request.
def create_hive_client():
    """Create a beem Hive client with proper configuration."""
    keys = [POSTING_KEY] if POSTING_KEY else []
    try:
        hive = Hive(
            node=HIVE_NODES,
            keys=keys,
            # HIVE CONCEPT: num_retries controls failover behavior.
            # beem will try each node in order, retrying failed requests.
            num_retries=3,
            # HIVE CONCEPT: timeout in seconds per node before failover
            timeout=15,
        )
        return hive
    except Exception as e:
        print(f"WARNING: Could not initialize Hive client: {e}")
        print("Read-only mode. Write endpoints will fail.")
        return Hive(node=HIVE_NODES, num_retries=3, timeout=15)


hive = create_hive_client()


# ---------------------------------------------------------------------------
#  3. HELPER FUNCTIONS
# ---------------------------------------------------------------------------


def generate_permlink(title: str) -> str:
    """
    Generate a URL-safe permlink from a title.

    HIVE CONCEPT: Every post and comment on Hive is identified by the
    combination of (author, permlink). The permlink is a URL-safe slug
    that must be unique per author. If you try to broadcast a post with
    a permlink that already exists for that author, the blockchain will
    reject it with a "duplicate permlink" error.

    Permlink rules:
      - Lowercase letters, numbers, and hyphens only
      - Max 256 characters
      - Must be unique per author (not globally unique)
      - Convention: include a timestamp to avoid collisions
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)  # replace non-alphanumeric with hyphens
    slug = slug.strip("-")                    # trim leading/trailing hyphens
    slug = slug[:200]                         # leave room for timestamp suffix

    # Append timestamp to guarantee uniqueness even if the same title is reused
    timestamp = hex(int(time.time() * 1000))[2:]  # compact hex timestamp
    return f"{slug}-{timestamp}"


def decode_reputation(raw_rep) -> float:
    """
    HIVE CONCEPT: Reputation on Hive is stored as a raw bigint value.
    The human-readable reputation (25-80 range typically) is calculated
    using a logarithmic formula. New accounts start at 25. Downvotes
    from higher-reputation accounts can decrease it.

      readable_rep = max(log10(abs(raw_rep)) - 9, 0) * 9 * sign(raw_rep) + 25

    Typical ranges:
      25     -- brand new account, no activity
      30-40  -- beginner, some posts and votes
      40-55  -- regular user
      55-65  -- active community member
      65-75  -- well-known, long-time user
      75+    -- top content creators (very hard to reach)
    """
    rep = int(raw_rep)
    if rep == 0:
        return 25.0

    negative = rep < 0
    abs_rep = abs(rep)
    decoded = math.log10(abs_rep) - 9
    if decoded < 0:
        decoded = 0
    decoded = decoded * (-9 if negative else 9) + 25
    return round(decoded, 2)


def require_auth():
    """Check that posting key and username are configured."""
    if not USERNAME or not POSTING_KEY:
        return {
            "error": "Authentication required",
            "detail": (
                "Set HIVE_USERNAME and HIVE_POSTING_KEY in your .env file. "
                "The posting key is a WIF string starting with '5'."
            ),
        }, 401
    return None


def handle_hive_error(err):
    """
    Classify and format Hive blockchain errors into user-friendly messages.

    HIVE CONCEPT: Common blockchain-level errors you will encounter
    are listed in the handling below.
    """
    msg = str(err)

    if "missing required posting authority" in msg:
        return jsonify({
            "error": "Wrong key type",
            "detail": (
                "The private key you provided does not match the posting "
                "authority for this account. Make sure you are using the "
                "POSTING key, not the active, owner, or memo key."
            ),
        }), 403

    if "Account does not have sufficient" in msg or "rc_plugin" in msg.lower():
        # HIVE CONCEPT: This means your Resource Credits are exhausted.
        # RCs regenerate over ~5 days. You can get more by powering up
        # HIVE to increase your HP, which directly increases max RCs.
        return jsonify({
            "error": "Insufficient Resource Credits",
            "detail": (
                "Your account has run out of Resource Credits (RCs). "
                "RCs regenerate over ~5 days. To get more immediately, "
                "power up more HIVE to increase your Hive Power."
            ),
        }), 429

    if "duplicate" in msg.lower() and "permlink" in msg.lower():
        return jsonify({
            "error": "Duplicate permlink",
            "detail": (
                "A post or comment with this permlink already exists for "
                "your account. Each (author, permlink) pair must be unique "
                "on the blockchain."
            ),
        }), 409

    if "HIVE_MIN_ROOT_COMMENT_INTERVAL" in msg:
        # HIVE CONCEPT: Hive enforces a 5-minute cooldown between root posts
        # (top-level posts, not comments). This prevents spam.
        return jsonify({
            "error": "Posting too fast",
            "detail": (
                "Hive enforces a 5-minute cooldown between top-level posts. "
                "Comments have a shorter 3-second cooldown."
            ),
        }), 429

    if "HIVE_MIN_REPLY_INTERVAL" in msg:
        return jsonify({
            "error": "Commenting too fast",
            "detail": "Hive enforces a 3-second cooldown between comments.",
        }), 429

    if any(x in msg for x in ["ECONNREFUSED", "ETIMEDOUT", "ENOTFOUND", "ConnectionError"]):
        return jsonify({
            "error": "Hive node unreachable",
            "detail": (
                "All configured Hive API nodes are down or unreachable. "
                "Check your internet connection or try different nodes."
            ),
        }), 503

    # Fallback
    return jsonify({
        "error": "Blockchain error",
        "detail": msg,
    }), 500


# ---------------------------------------------------------------------------
#  4. ENDPOINTS
# ---------------------------------------------------------------------------

# ===== GET /api/feed/<tag> -- Fetch posts by tag ============================


@app.route("/api/feed/<tag>", methods=["GET"])
def get_feed(tag):
    """
    HIVE CONCEPT: Posts on Hive are organized by tags (also called
    "communities" in the newer system). The first tag is the post's
    "category" and determines which community it appears in.

    Feed sorting options (passed as ?sort=...):
      trending  -- ranked by pending payout (rewards not yet claimed)
      created   -- newest first (chronological)
      hot       -- recent posts with rapid engagement

    The API uses a cursor-based pagination model with (author, permlink)
    as the cursor for fetching the next page.
    """
    try:
        sort = request.args.get("sort", "trending")
        limit = min(int(request.args.get("limit", 20)), 100)

        valid_sorts = ["trending", "created", "hot"]
        if sort not in valid_sorts:
            return jsonify({
                "error": f"Invalid sort. Use one of: {', '.join(valid_sorts)}",
            }), 400

        # HIVE CONCEPT: beem provides dedicated Discussion classes for each
        # sort type. Under the hood they call condenser_api.get_discussions_by_*
        # on the Hive node. The query dict specifies the tag filter and limit.
        query = {"tag": tag, "limit": limit}

        # Add optional pagination cursor
        start_author = request.args.get("start_author")
        start_permlink = request.args.get("start_permlink")
        if start_author and start_permlink:
            query["start_author"] = start_author
            query["start_permlink"] = start_permlink

        # Map sort name to beem Discussion class
        discussion_classes = {
            "trending": Discussions_by_trending,
            "created": Discussions_by_created,
            "hot": Discussions_by_hot,
        }

        discussions = discussion_classes[sort](query, blockchain_instance=hive)

        # HIVE CONCEPT: Each post object from beem is a Comment instance with
        # many fields. Here are the most important ones:
        #
        #   author          -- the Hive username who wrote the post
        #   permlink        -- URL-safe unique slug (unique per author)
        #   title           -- post title (empty for comments)
        #   body            -- post content in Markdown format
        #   category        -- the first tag (also the "community")
        #   created         -- datetime when post was broadcast
        #   json_metadata   -- dict with tags, app info, images, etc.
        #   pending_payout_value -- Asset: unclaimed rewards (before 7-day window)
        #   total_payout_value   -- Asset: rewards already paid out
        #   active_votes    -- list of all votes with voter, weight, rshares
        #   children        -- number of direct replies
        #   depth           -- 0 = root post, 1+ = comment/reply
        #   author_reputation -- reputation score (raw bigint, needs decoding)
        #
        # The URL for any post is: https://hive.blog/@{author}/{permlink}
        posts = []
        for post in discussions:
            # HIVE CONCEPT: json_metadata is stored on-chain and contains
            # arbitrary app-specific data. beem auto-parses it into a dict.
            # The standard fields are:
            #   tags   -- list of tags (first one = category)
            #   image  -- list of image URLs (first is used as thumbnail)
            #   app    -- identifying string for the app that created the post
            #   format -- content format: "markdown" or "html"
            metadata = post.json_metadata if isinstance(post.json_metadata, dict) else {}

            # HIVE CONCEPT: pending_payout_value is the estimated reward
            # a post will earn. Posts earn rewards for 7 days after creation.
            # After the 7-day window, pending goes to 0 and total_payout_value
            # reflects what was actually paid. Rewards are split between the
            # author (~50% HBD + ~50% HP) and curators (voters).
            posts.append({
                "author": post["author"],
                "permlink": post["permlink"],
                "title": post["title"],
                "body": post["body"][:500],  # preview only
                "category": post["category"],
                "tags": metadata.get("tags", [post["category"]]),
                "created": str(post["created"]),
                "image": (metadata.get("image") or [None])[0],
                "pending_payout": str(post["pending_payout_value"]),
                "total_payout": str(post["total_payout_value"]),
                "votes": len(post.get("active_votes", [])),
                "children": post["children"],
                "reputation": decode_reputation(post["author_reputation"]),
                "url": f"https://hive.blog/@{post['author']}/{post['permlink']}",
            })

        return jsonify({
            "tag": tag,
            "sort": sort,
            "count": len(posts),
            "posts": posts,
        })

    except Exception as err:
        return handle_hive_error(err)


# ===== GET /api/post/<author>/<permlink> -- Single post with comments ========
# curl http://localhost:3000/api/post/hiveio/hive-hard-fork-26
#
# HIVE CONCEPT: A post is uniquely identified by its author + permlink.
# Comments are also posts -- they just have a parent_author and parent_permlink
# that point to the post they're replying to. This creates a tree structure
# where all comments live on-chain alongside the root post.


@app.route("/api/post/<author>/<permlink>", methods=["GET"])
def get_post(author, permlink):
    """
    Get a single post with its full comment tree.

    curl http://localhost:3000/api/post/hiveio/hive-hard-fork-26
    """
    try:
        # beem's Comment class fetches a single post/comment by author+permlink.
        # The authorperm format "@author/permlink" is a beem convention.
        post = Comment(f"@{author}/{permlink}", blockchain_instance=hive)

        # Parse json_metadata for images, tags, app info.
        # HIVE CONCEPT: json_metadata is a JSON string embedded in posts that
        # front-ends use for images, tags, app identification, canonical URLs, etc.
        metadata = {}
        jm = post.get("json_metadata", "{}")
        if isinstance(jm, str):
            try:
                metadata = json.loads(jm)
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        elif isinstance(jm, dict):
            metadata = jm

        # Fetch the comment tree.
        # HIVE CONCEPT: get_all_replies() fetches the entire reply tree
        # recursively. Each reply is a Comment object with parent_author,
        # parent_permlink, depth (1=direct reply, 2=reply-to-reply), and body.
        comments = []
        try:
            replies = post.get_all_replies()
            for reply in replies:
                comments.append({
                    "author": reply["author"],
                    "permlink": reply["permlink"],
                    # parent_author tells you who this comment is replying to.
                    # If it equals the root post's author, it's a top-level reply.
                    "parent_author": reply["parent_author"],
                    "parent_permlink": reply["parent_permlink"],
                    "body": reply["body"],
                    "created": str(reply.get("created", "")),
                    "net_votes": reply.get("net_votes", 0),
                    "depth": reply.get("depth", 1),
                    "author_reputation": reply.get("author_reputation", 0),
                })
        except Exception:
            # If comment fetching fails, return the post without comments
            pass

        # active_votes is the full list of every vote on this post.
        # HIVE CONCEPT: Each vote has voter, weight (basis points: 10000 = 100%
        # upvote, -10000 = 100% downvote), rshares (reward shares that determine
        # the dollar value of the vote), and timestamp.
        votes = []
        for v in post.get("active_votes", []):
            votes.append({
                "voter": v.get("voter", ""),
                "weight": v.get("percent", v.get("weight", 0)),
                "rshares": v.get("rshares", "0"),
                "time": str(v.get("time", "")),
            })

        return jsonify({
            "author": post["author"],
            "permlink": post["permlink"],
            "title": post["title"],
            "body": post["body"],  # Full Markdown content
            "category": post.get("category", ""),  # Primary tag / community
            "tags": metadata.get("tags", []),
            "image": (metadata.get("image", [None]) or [None])[0],
            # Payout details
            # HIVE CONCEPT: Posts earn rewards for 7 days. pending_payout_value
            # is the estimated reward if payout happened now. After 7 days, the
            # payout is finalized: 50% to author, 50% to curators (voters).
            "pending_payout": str(post.get("pending_payout_value", "0.000 HBD")),
            "total_payout": str(post.get("total_payout_value", "0.000 HBD")),
            "curator_payout": str(post.get("curator_payout_value", "0.000 HBD")),
            # Vote stats
            "net_votes": post.get("net_votes", 0),
            "vote_count": len(votes),
            "votes": votes,
            # Timestamps
            "created": str(post.get("created", "")),
            "last_update": str(post.get("last_update", "")),
            # cashout_time is when the 7-day payout window ends.
            # After this, rewards are finalized and distributed.
            "cashout_time": str(post.get("cashout_time", "")),
            # Comment tree
            "comment_count": len(comments),
            "comments": comments,
            # The app that created this post (e.g., "peakd/2024.1.1")
            "app": metadata.get("app", "unknown"),
        })

    except ContentDoesNotExistsException:
        return jsonify({
            "error": "Post not found",
            "hint": f'No post exists at @{author}/{permlink}. Check the spelling.',
        }), 404
    except Exception as err:
        return handle_hive_error(err)


# ===== GET /api/account/<username> -- Account info ==========================


@app.route("/api/account/<username>", methods=["GET"])
def get_account(username):
    """
    HIVE CONCEPT: A Hive account contains many pieces of data:
      - Balances (HIVE, HBD, Hive Power/VESTS, Savings)
      - Posting/voting metadata
      - Resource Credits (RCs)
      - Profile info (stored in json_metadata or posting_json_metadata)
      - Authority structures (which keys can do what)
      - Delegation info (delegated HP in/out)

    HIVE CURRENCY TYPES:
      HIVE -- the native token, can be transferred or "powered up" to HP
      HBD  -- Hive Backed Dollars, a stablecoin pegged to ~$1 USD.
              Holding HBD in savings earns ~20% APR interest.
      HP   -- Hive Power (VESTS), staked HIVE that gives governance weight,
              curation rewards, and Resource Credits. Takes 13 weeks to
              "power down" (unstake) in 13 weekly installments.
    """
    try:
        account_name = username.lower().lstrip("@")

        # HIVE CONCEPT: beem's Account class wraps all account data.
        # It automatically fetches account data from the blockchain
        # when instantiated. If the account doesn't exist, it raises
        # AccountDoesNotExistsException.
        try:
            account = Account(account_name, blockchain_instance=hive)
        except AccountDoesNotExistsException:
            return jsonify({
                "error": "Account not found",
                "detail": (
                    f'No Hive account exists with username "{account_name}". '
                    "Hive usernames are 3-16 characters, lowercase, and may "
                    "contain letters, numbers, hyphens, and dots."
                ),
            }), 404

        # HIVE CONCEPT: On-chain, Hive Power is stored as VESTS (Vesting Shares).
        # beem provides helper methods to convert between VESTS and HP.
        #
        # The account has several VESTS-related fields:
        #   vesting_shares           -- HP you own
        #   delegated_vesting_shares -- HP you've lent to others
        #   received_vesting_shares  -- HP others have lent to you
        #   vesting_withdraw_rate    -- weekly HP being powered down
        #
        # VESTS → HP conversion:
        #   HP = VESTS * (total_vesting_fund_hive / total_vesting_shares)
        #
        # Why VESTS exist: They represent your exact share of the reward pool,
        # independent of inflation. 1 VEST always equals the same fraction
        # of the pool, even as new HIVE is printed.
        own_hp = float(account.get_hive_power())
        delegated_out = float(account.get_delegated_hive_power())
        delegated_in = float(account.get_received_hive_power())
        effective_hp = own_hp - delegated_out + delegated_in

        # HIVE CONCEPT: Resource Credits (RCs) are the "gas" of Hive.
        # Every transaction (post, vote, comment, transfer, custom_json)
        # consumes RCs. Unlike Ethereum gas, RCs are FREE -- they regenerate
        # over time (fully in ~5 days). The more Hive Power (HP) you have,
        # the more RCs you get.
        #
        # If your RCs hit 0%, you cannot transact until they regenerate.
        # New accounts start with delegated RCs from the creator.
        #
        # RC cost varies by operation:
        #   Vote:          ~0.5% of a new account's RCs
        #   Comment/Post:  ~2-5% depending on size
        #   Transfer:      ~0.5%
        #   Custom JSON:   ~0.5%
        try:
            rc = account.get_rc()
            rc_data = {
                "percentage": f"{rc.get('estimated_pct', 0):.2f}",
                "max_rc": str(rc.get("max_rc", 0)),
                "current_rc": str(rc.get("current_mana", 0)),
            }
        except Exception:
            rc_data = {"percentage": "N/A", "max_rc": "N/A", "current_rc": "N/A"}

        # HIVE CONCEPT: Profile info is stored in `posting_json_metadata`
        # (preferred) or `json_metadata`. The profile object typically has:
        #   { "profile": { "name", "about", "location", "website",
        #                   "profile_image", "cover_image" } }
        profile_data = {}
        try:
            raw_meta = account.get("posting_json_metadata", "") or account.get("json_metadata", "")
            if isinstance(raw_meta, str) and raw_meta:
                parsed = json.loads(raw_meta)
                profile_data = parsed.get("profile", {})
            elif isinstance(raw_meta, dict):
                profile_data = raw_meta.get("profile", {})
        except (json.JSONDecodeError, TypeError):
            profile_data = {}

        # HIVE CONCEPT: Voting power (also called "mana") represents how
        # much influence your next vote carries. It starts at 100% and
        # decreases by ~2% with each full-weight vote. It regenerates
        # linearly back to 100% over 5 days (same as RCs).
        #
        # Voting at lower weight (e.g., 50%) uses proportionally less mana.
        # Power users typically keep their voting mana above 80%.
        try:
            voting_power = account.get_voting_power()
        except Exception:
            voting_power = 0.0

        return jsonify({
            "name": account["name"],
            "profile": {
                "display_name": profile_data.get("name", account["name"]),
                "about": profile_data.get("about", ""),
                "location": profile_data.get("location", ""),
                "website": profile_data.get("website", ""),
                "profile_image": profile_data.get("profile_image", ""),
                "cover_image": profile_data.get("cover_image", ""),
            },
            "balances": {
                "hive": str(account["balance"]),
                "hbd": str(account["hbd_balance"]),
                "hive_savings": str(account["savings_balance"]),
                "hbd_savings": str(account["savings_hbd_balance"]),
            },
            "hive_power": {
                "own_hp": f"{own_hp:.3f} HP",
                "delegated_out": f"{delegated_out:.3f} HP",
                "delegated_in": f"{delegated_in:.3f} HP",
                "effective_hp": f"{effective_hp:.3f} HP",
                # HIVE CONCEPT: VESTS are shown for transparency. 1 VEST is
                # approximately 0.0005 HP currently, but the ratio changes
                # with inflation over time.
                "raw_vests": str(account["vesting_shares"]),
            },
            "resource_credits": rc_data,
            "voting": {
                "mana_percent": f"{voting_power:.2f}%",
                "last_vote": str(account.get("last_vote_time", "")),
            },
            "stats": {
                "post_count": account["post_count"],
                "reputation": decode_reputation(account["reputation"]),
                "created": str(account["created"]),
                "last_post": str(account.get("last_post", "")),
                # HIVE CONCEPT: Witness votes are how Hive governance works.
                # Each account can vote for up to 30 "witnesses" who run the
                # blockchain nodes and set economic parameters (like HBD interest
                # rate and account creation fee). Top 20 witnesses produce blocks.
                "witness_votes": account.get("witness_votes", []),
                "witnesses_voted_for": account.get("witnesses_voted_for", 0),
            },
            # HIVE CONCEPT: Power down (vesting withdrawal) converts HP back
            # to liquid HIVE over 13 weekly installments. This 13-week period
            # is a security feature -- if your keys are compromised, you have
            # time to recover your account before all HP is drained.
            "power_down": {
                "is_powering_down": str(account["vesting_withdraw_rate"]) != "0.000000 VESTS",
                "weekly_rate": str(account["vesting_withdraw_rate"]),
                "next_withdrawal": str(account.get("next_vesting_withdrawal", "")),
            },
        })

    except AccountDoesNotExistsException:
        return jsonify({
            "error": "Account not found",
            "detail": f'No Hive account exists with username "{username}".',
        }), 404
    except Exception as err:
        return handle_hive_error(err)


# ===== GET /api/notifications/<username> -- Recent account history ===========
# curl http://localhost:3000/api/notifications/blocktrades?limit=20
#
# HIVE CONCEPT: Every blockchain operation involving an account is recorded
# in that account's history. bridge.account_notifications returns decoded,
# human-readable notifications (votes, replies, mentions, follows, reblogs,
# transfers) instead of raw account_history operations.


@app.route("/api/notifications/<username>", methods=["GET"])
def get_notifications(username):
    """
    Get recent notifications for an account.

    curl http://localhost:3000/api/notifications/blocktrades?limit=20
    curl "http://localhost:3000/api/notifications/blocktrades?type=vote&limit=50"
    """
    try:
        limit = min(int(request.args.get("limit", 20)), 100)
        type_filter = request.args.get("type", None)

        # bridge.account_notifications is the modern notification API.
        # It returns decoded notifications with type, message, URL, date,
        # and a relevance score. The "bridge" API is a higher-level layer
        # over the raw condenser_api.
        notifications = hive.rpc.account_notifications(
            {"account": username, "limit": limit}, api="bridge"
        )

        if not notifications:
            notifications = []

        # Filter by type if requested (e.g., ?type=vote to see only votes)
        results = notifications
        if type_filter:
            results = [n for n in notifications if n.get("type") == type_filter]

        return jsonify({
            "account": username,
            "count": len(results),
            # Available notification types for filtering
            "available_types": [
                "vote",      # Someone voted on your post/comment
                "reply",     # Someone replied to your post/comment
                "mention",   # Someone @mentioned you in their post
                "follow",    # Someone followed you
                "reblog",    # Someone reblogged your post
                "transfer",  # Someone sent you HIVE or HBD
                "unvote",    # Someone removed their vote
            ],
            "notifications": [
                {
                    "type": n.get("type", ""),
                    "message": n.get("msg", ""),
                    "url": (
                        f"https://peakd.com{n['url']}" if n.get("url") else None
                    ),
                    "date": n.get("date", ""),
                    "score": n.get("score", 0),
                }
                for n in results
            ],
        })
    except Exception as err:
        return handle_hive_error(err)


# ===== POST /api/post -- Create a new blog post ============================


@app.route("/api/post", methods=["POST"])
def create_post():
    """
    HIVE CONCEPT: Creating a post on Hive is a blockchain transaction.
    The operation type is "comment" (posts and comments use the same
    operation -- a post is just a comment with no parent).

    A post transaction consists of:
      1. A "comment" operation -- the actual content
      2. Optionally, a "comment_options" operation -- reward settings,
         beneficiaries, max payout, etc.

    Both operations are bundled into a single transaction and broadcast
    atomically (both succeed or both fail).

    Request body:
      {
        "title": "My First Hive Post",
        "body": "Hello world! This is **markdown** content.",
        "tags": ["hive", "introduction", "coding"],
        "beneficiaries": [{"account": "friend", "weight": 1000}],  // optional
        "max_accepted_payout": "1000000.000 HBD",                  // optional
        "percent_hbd": 10000                                        // optional
      }
    """
    auth_error = require_auth()
    if auth_error:
        return jsonify(auth_error[0]), auth_error[1]

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        title = data.get("title", "")
        body = data.get("body", "")
        tags = data.get("tags", [])
        beneficiaries = data.get("beneficiaries", [])
        max_accepted_payout = data.get("max_accepted_payout", "1000000.000 HBD")
        percent_hbd = data.get("percent_hbd", 10000)

        # Validation
        if not title or not body:
            return jsonify({"error": "Missing required fields: title and body"}), 400

        if not tags or not isinstance(tags, list) or len(tags) == 0:
            return jsonify({
                "error": "At least one tag is required. The first tag becomes the post's category.",
            }), 400

        permlink = generate_permlink(title)

        # HIVE CONCEPT: json_metadata is an on-chain JSON blob that contains
        # app-specific data. The standard fields are:
        #   tags   -- list of tags (first one = category)
        #   app    -- identifying string for the app that created the post
        #   format -- content format: "markdown" or "html"
        #   image  -- list of image URLs (first is used as thumbnail)
        #
        # You can add ANY custom fields here. Many apps use this for:
        #   - video metadata (3speak)
        #   - poll data (dpoll)
        #   - NFT references (splinterlands)
        metadata = json.dumps({
            "tags": tags,
            "app": "hive-social-app/1.0",
            "format": "markdown",
        })

        # HIVE CONCEPT: We use beem's TransactionBuilder to bundle multiple
        # operations into a single atomic transaction. This lets us attach
        # comment_options (beneficiaries, payout settings) to the post.
        #
        # The "comment" operation is used for BOTH posts and comments.
        # The difference:
        #   Post (root):     parent_author = "" (empty), parent_permlink = category tag
        #   Comment (reply): parent_author = author being replied to,
        #                    parent_permlink = permlink being replied to
        tx = TransactionBuilder(blockchain_instance=hive)

        comment_op = CommentOperation(**{
            "parent_author": "",          # empty = this is a root post (not a reply)
            "parent_permlink": tags[0],   # first tag = category
            "author": USERNAME,           # your Hive account name
            "permlink": permlink,         # unique slug for this post
            "title": title,               # post title (empty for comments)
            "body": body,                 # markdown content
            "json_metadata": metadata,    # app data, tags, etc.
        })
        tx.appendOps(comment_op)

        # HIVE CONCEPT: comment_options lets you control reward parameters:
        #
        #   max_accepted_payout -- max HBD rewards (default "1000000.000 HBD").
        #     Set to "0.000 HBD" to decline all rewards (altruistic post).
        #
        #   percent_hbd -- what percent of author rewards to pay in HBD vs HP.
        #     10000 = 100% of the author-portion as HBD (default)
        #     5000  = 50% HBD, 50% extra HP
        #     0     = 100% HP (power up everything)
        #
        #   allow_votes -- whether the post can receive votes (default True)
        #   allow_curation_rewards -- whether curators earn rewards (default True)
        #
        #   beneficiaries -- share a percentage of rewards with other accounts.
        #     Weight is in basis points: 1000 = 10%, 500 = 5%, etc.
        #     MUST be sorted alphabetically by account name.
        #     Common use: apps take 5-15% as a beneficiary for hosting costs.
        #     Example: [{"account": "hive.fund", "weight": 1000}] = 10% to hive.fund
        extensions = []
        if beneficiaries:
            # IMPORTANT: Beneficiaries MUST be sorted alphabetically
            sorted_bens = sorted(beneficiaries, key=lambda b: b["account"])
            extensions = [[0, {"beneficiaries": sorted_bens}]]

        comment_options_op = Comment_options(**{
            "author": USERNAME,
            "permlink": permlink,
            "max_accepted_payout": max_accepted_payout,
            "percent_hbd": percent_hbd,
            "allow_votes": True,
            "allow_curation_rewards": True,
            "extensions": extensions,
        })
        tx.appendOps(comment_options_op)

        # HIVE CONCEPT: appendWif adds the signing key to the transaction.
        # sign() serializes the operations and signs them with the private key.
        # broadcast() sends the signed transaction to the network.
        # The transaction is included in the next block (~3 seconds).
        tx.appendWif(POSTING_KEY)
        tx.sign()
        result = tx.broadcast()

        return jsonify({
            "success": True,
            "author": USERNAME,
            "permlink": permlink,
            "url": f"https://hive.blog/@{USERNAME}/{permlink}",
            # HIVE CONCEPT: block_num tells you which block included your
            # transaction. Blocks are produced every 3 seconds by witnesses.
            # You can verify the transaction at:
            #   https://hiveblocks.com/b/{block_num}
            "block_num": result.get("block_num"),
            "transaction_id": result.get("id"),
        }), 201

    except MissingKeyError:
        return jsonify({
            "error": "Wrong key type",
            "detail": (
                "The posting key is required but not loaded. "
                "Check HIVE_POSTING_KEY in your .env file."
            ),
        }), 403
    except Exception as err:
        return handle_hive_error(err)


# ===== POST /api/vote -- Vote on a post ====================================


@app.route("/api/vote", methods=["POST"])
def cast_vote():
    """
    HIVE CONCEPT: Voting on Hive is the core curation mechanism.

    Key concepts:
      - Weight ranges from -10000 to 10000 (basis points)
        - 10000 = 100% upvote (full strength)
        - 5000  = 50% upvote
        - 0     = remove existing vote
        - -10000 = 100% downvote (flag)

      - Each vote consumes voting mana (~2% for a 100% vote)
      - Voting mana regenerates to 100% over 5 days

      - Upvotes add "rshares" (reward shares) to the post's pending payout
      - Downvotes remove rshares and can reduce payouts

      - Curation rewards: voters who upvote posts that later become popular
        earn curation rewards (paid in HP). Earlier votes earn more.

      - You can change your vote at any time within the 7-day window.
        Removing a vote (weight 0) returns the used rshares.

    Request body:
      {
        "author": "hiveuser",
        "permlink": "my-awesome-post",
        "weight": 10000
      }
    """
    auth_error = require_auth()
    if auth_error:
        return jsonify(auth_error[0]), auth_error[1]

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        author = data.get("author", "")
        permlink = data.get("permlink", "")
        weight = data.get("weight", 10000)

        if not author or not permlink:
            return jsonify({
                "error": "Missing required fields: author and permlink",
            }), 400

        vote_weight = int(weight)
        if vote_weight < -10000 or vote_weight > 10000:
            return jsonify({
                "error": (
                    "Weight must be between -10000 (100% downvote) and "
                    "10000 (100% upvote). Use 0 to remove an existing vote."
                ),
            }), 400

        # HIVE CONCEPT: The "vote" operation. Fields:
        #   voter    -- the account casting the vote (you)
        #   author   -- the account that wrote the post/comment
        #   permlink -- the specific post or comment being voted on
        #   weight   -- vote strength in basis points (-10000 to 10000)
        tx = TransactionBuilder(blockchain_instance=hive)
        vote_op = Vote(**{
            "voter": USERNAME,
            "author": author,
            "permlink": permlink,
            "weight": vote_weight,
        })
        tx.appendOps(vote_op)
        tx.appendWif(POSTING_KEY)
        tx.sign()
        result = tx.broadcast()

        # Describe the action for the response
        if vote_weight > 0:
            action = f"Upvoted at {vote_weight / 100}%"
        elif vote_weight < 0:
            action = f"Downvoted at {abs(vote_weight) / 100}%"
        else:
            action = "Vote removed"

        return jsonify({
            "success": True,
            "action": action,
            "voter": USERNAME,
            "author": author,
            "permlink": permlink,
            "weight": vote_weight,
            "block_num": result.get("block_num"),
            "transaction_id": result.get("id"),
        })

    except MissingKeyError:
        return jsonify({
            "error": "Posting key required for voting",
            "detail": "Check HIVE_POSTING_KEY in your .env file.",
        }), 403
    except Exception as err:
        return handle_hive_error(err)


# ===== POST /api/comment -- Comment on a post ==============================


@app.route("/api/comment", methods=["POST"])
def create_comment():
    """
    HIVE CONCEPT: Comments are the same "comment" operation as posts,
    but with a non-empty parent_author and parent_permlink. Comments
    can be nested -- you can reply to a reply to a reply (unlimited depth).

    Comments also earn rewards just like posts. The 7-day payout window
    and voting work identically for comments.

    Request body:
      {
        "parent_author": "hiveuser",
        "parent_permlink": "the-post-being-replied-to",
        "body": "Great post! I especially liked..."
      }
    """
    auth_error = require_auth()
    if auth_error:
        return jsonify(auth_error[0]), auth_error[1]

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        parent_author = data.get("parent_author", "")
        parent_permlink = data.get("parent_permlink", "")
        body = data.get("body", "")

        if not parent_author or not parent_permlink or not body:
            return jsonify({
                "error": "Missing required fields: parent_author, parent_permlink, and body",
            }), 400

        # HIVE CONCEPT: Comment permlinks are typically auto-generated.
        # The convention is "re-{parent_author}-{parent_permlink}-{timestamp}"
        # but any unique-per-author string works.
        comment_permlink = f"re-{parent_author}-{parent_permlink}-{hex(int(time.time() * 1000))[2:]}"

        metadata = json.dumps({
            "app": "hive-social-app/1.0",
            "format": "markdown",
        })

        # HIVE CONCEPT: When parent_author is non-empty, this becomes a comment
        # (reply) rather than a root post. The parent_permlink points to the
        # content being replied to -- either a root post or another comment.
        tx = TransactionBuilder(blockchain_instance=hive)
        comment_op = CommentOperation(**{
            "parent_author": parent_author,       # author of the post/comment being replied to
            "parent_permlink": parent_permlink,   # permlink of the post/comment being replied to
            "author": USERNAME,                   # your account
            "permlink": comment_permlink,         # unique permlink for this comment
            "title": "",                          # comments have empty titles
            "body": body,                         # comment content in markdown
            "json_metadata": metadata,
        })
        tx.appendOps(comment_op)
        tx.appendWif(POSTING_KEY)
        tx.sign()
        result = tx.broadcast()

        return jsonify({
            "success": True,
            "author": USERNAME,
            "permlink": comment_permlink,
            "parent_author": parent_author,
            "parent_permlink": parent_permlink,
            "url": (
                f"https://hive.blog/@{parent_author}/{parent_permlink}"
                f"#@{USERNAME}/{comment_permlink}"
            ),
            "block_num": result.get("block_num"),
            "transaction_id": result.get("id"),
        }), 201

    except MissingKeyError:
        return jsonify({
            "error": "Posting key required for commenting",
            "detail": "Check HIVE_POSTING_KEY in your .env file.",
        }), 403
    except Exception as err:
        return handle_hive_error(err)


# ===== POST /api/follow -- Follow or unfollow a user =======================


@app.route("/api/follow", methods=["POST"])
def follow_user():
    """
    HIVE CONCEPT: Following on Hive is implemented via the "custom_json"
    operation, NOT a dedicated "follow" operation. custom_json is a
    general-purpose operation for storing arbitrary JSON data on the
    blockchain without a specific protocol-level meaning.

    The follow protocol uses:
      id: "follow"
      json: ["follow", {"follower": "you", "following": "them", "what": ["blog"]}]

    The "what" array determines the action:
      ["blog"]   -- follow the user (see their posts in your feed)
      []         -- unfollow (empty array)
      ["ignore"] -- mute/block the user (hide their content)

    custom_json operations require POSTING authority for social actions
    (specified in required_posting_auths).

    Request body:
      {
        "following": "hiveuser",
        "action": "follow"    // "follow", "unfollow", or "mute"
      }
    """
    auth_error = require_auth()
    if auth_error:
        return jsonify(auth_error[0]), auth_error[1]

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        following = data.get("following", "")
        action = data.get("action", "follow")

        if not following:
            return jsonify({
                "error": "Missing required field: following (the username to follow)",
            }), 400

        valid_actions = ["follow", "unfollow", "mute"]
        if action not in valid_actions:
            return jsonify({
                "error": f"Invalid action. Use one of: {', '.join(valid_actions)}",
            }), 400

        # HIVE CONCEPT: The "what" array in the follow protocol:
        #   ["blog"]   = follow -- their posts appear in your feed
        #   []         = unfollow -- remove from feed, neutral state
        #   ["ignore"] = mute -- hide their content from your view
        what_map = {
            "follow": ["blog"],
            "unfollow": [],
            "mute": ["ignore"],
        }
        what = what_map[action]

        # HIVE CONCEPT: custom_json is the Swiss Army knife operation.
        # Many Hive features are built on custom_json:
        #   - follow/mute (id: "follow")
        #   - reblog/resteem (id: "follow" with "reblog" type)
        #   - community operations (id: "community")
        #   - Splinterlands game actions (id: "sm_...")
        #   - Hive Engine token operations (id: "ssc-mainnet-hive")
        #   - Podping podcast notifications (id: "podping")
        #
        # Two auth fields:
        #   required_posting_auths -- for social/non-financial ops (posting key)
        #   required_auths         -- for financial ops (requires active key)
        follow_json = json.dumps([
            "follow",
            {
                "follower": USERNAME,     # the account doing the following
                "following": following,   # the account being followed
                "what": what,             # action type
            },
        ])

        tx = TransactionBuilder(blockchain_instance=hive)
        custom_json_op = Custom_json(**{
            "required_auths": [],                   # empty = not a financial operation
            "required_posting_auths": [USERNAME],   # signed with posting key
            "id": "follow",                         # protocol identifier
            "json": follow_json,
        })
        tx.appendOps(custom_json_op)
        tx.appendWif(POSTING_KEY)
        tx.sign()
        result = tx.broadcast()

        return jsonify({
            "success": True,
            "action": action,
            "follower": USERNAME,
            "following": following,
            "block_num": result.get("block_num"),
            "transaction_id": result.get("id"),
        })

    except MissingKeyError:
        return jsonify({
            "error": "Posting key required for follow operations",
            "detail": "Check HIVE_POSTING_KEY in your .env file.",
        }), 403
    except Exception as err:
        return handle_hive_error(err)


# ===== POST /api/reblog -- Reblog (resteem) a post ==========================
# curl -X POST http://localhost:3000/api/reblog \
#   -H "Content-Type: application/json" \
#   -d '{"author":"hiveio","permlink":"hive-hard-fork-26"}'
#
# HIVE CONCEPT: Reblogging (called "resteeming" in Steem, Hive's predecessor)
# shares someone else's post to your followers' feeds. It's like a "retweet"
# on Twitter. The reblog is stored on-chain as a custom_json operation.
#
# Important: Reblogs CANNOT be undone on-chain. Some front-ends implement
# client-side un-reblog by hiding it, but the blockchain record persists.
# Reblogs don't earn rewards for the reblogger, but they help the original
# author reach a wider audience, which can lead to more votes/rewards.


@app.route("/api/reblog", methods=["POST"])
def reblog_post():
    """
    Reblog (resteem) a post to your followers' feeds.

    curl -X POST http://localhost:3000/api/reblog \\
      -H "Content-Type: application/json" \\
      -d '{"author":"hiveio","permlink":"hive-hard-fork-26"}'
    """
    # HIVE CONCEPT: Only the POSTING KEY is needed for reblogs because they're
    # social operations (custom_json with required_posting_auths). Financial
    # operations would need the ACTIVE KEY.
    if not POSTING_KEY or not USERNAME:
        return jsonify({
            "error": "No posting key configured",
            "hint": "Set HIVE_USERNAME and HIVE_POSTING_KEY in your .env file.",
        }), 403

    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        author = (data.get("author") or "").strip()
        permlink = (data.get("permlink") or "").strip()

        if not author or not permlink:
            return jsonify({
                "error": "Both 'author' and 'permlink' are required",
                "hint": "These identify which post to reblog.",
            }), 400

        if author == USERNAME:
            return jsonify({"error": "You cannot reblog your own post"}), 400

        # Verify the post exists before reblogging.
        # This prevents broadcasting a reblog for non-existent content,
        # which would waste RC without any useful result.
        try:
            Comment(f"@{author}/{permlink}", blockchain_instance=hive)
        except ContentDoesNotExistsException:
            return jsonify({"error": "Post not found"}), 404

        # HIVE CONCEPT: Reblog is a custom_json operation with id "reblog".
        # custom_json is Hive's extensibility mechanism — any app can define
        # its own custom_json IDs. The "reblog" ID is standardized so all
        # Hive front-ends display reblogs consistently.
        reblog_data = json.dumps([
            "reblog",
            {
                "account": USERNAME,   # Who is reblogging
                "author": author,      # Original post author
                "permlink": permlink,  # Original post permlink
            },
        ])

        # Build the transaction with a custom_json operation.
        # required_posting_auths = posting key is sufficient (social action).
        # required_auths would need an active key (financial action).
        tx = TransactionBuilder(blockchain_instance=hive)
        tx.appendOps(Custom_json(**{
            "required_auths": [],                   # No active key needed
            "required_posting_auths": [USERNAME],    # Posting key authorizes this
            "id": "reblog",                          # Protocol identifier
            "json": reblog_data,                     # Reblog payload
        }))
        tx.appendWif(POSTING_KEY)
        tx.sign()
        result = tx.broadcast()

        return jsonify({
            "success": True,
            "message": f"Reblogged @{author}/{permlink} to your followers",
            "reblogger": USERNAME,
            "original_author": author,
            "permlink": permlink,
            "transaction_id": result.get("id", result.get("trx_id", "")),
            "block_num": result.get("block_num", 0),
            "tip": (
                "This post will now appear in your followers' feeds. "
                "Note: reblogs cannot be undone on-chain."
            ),
        })

    except MissingKeyError:
        return jsonify({
            "error": "Posting key required for reblog",
            "detail": "Check HIVE_POSTING_KEY in your .env file.",
        }), 403
    except Exception as err:
        return handle_hive_error(err)


# ---------------------------------------------------------------------------
#  5. HEALTH CHECK & INFO
# ---------------------------------------------------------------------------


@app.route("/", methods=["GET"])
def index():
    """Root endpoint with API documentation."""
    return jsonify({
        "name": "Hive Social App",
        "description": "A working Hive blockchain social app and learning tool",
        "version": "1.0.0",
        "endpoints": {
            "GET  /api/feed/<tag>": (
                "Get posts by tag (?sort=trending|created|hot&limit=20)"
            ),
            "GET  /api/post/<author>/<permlink>": (
                "Get single post with full comment tree and votes"
            ),
            "GET  /api/account/<username>": (
                "Get account info (HP, RC, balances, profile)"
            ),
            "GET  /api/notifications/<username>": (
                "Get notifications (?type=vote|reply|mention&limit=20)"
            ),
            "POST /api/post": (
                "Create a post { title, body, tags[], beneficiaries?, "
                "max_accepted_payout?, percent_hbd? }"
            ),
            "POST /api/vote": "Vote on a post { author, permlink, weight }",
            "POST /api/comment": (
                "Comment on a post { parent_author, parent_permlink, body }"
            ),
            "POST /api/follow": (
                "Follow/unfollow { following, action: follow|unfollow|mute }"
            ),
            "POST /api/reblog": (
                "Reblog a post { author, permlink }"
            ),
        },
        "hive_node": HIVE_NODES[0],
        "authenticated": bool(POSTING_KEY),
        "username": USERNAME or "(not set)",
    })


@app.route("/api/health", methods=["GET"])
def health_check():
    """
    HIVE CONCEPT: You can verify your connection to the blockchain by
    fetching global properties. This returns current head block,
    witness schedule, and economic parameters like the current
    HIVE price feed, HBD interest rate, and vesting fund totals.
    """
    try:
        # HIVE CONCEPT: get_dynamic_global_properties() returns the
        # current state of the blockchain including head block number,
        # current witness, time, and various economic parameters.
        props = hive.get_dynamic_global_properties()
        return jsonify({
            "status": "ok",
            "blockchain": {
                "head_block": props.get("head_block_number"),
                "time": props.get("time"),
                # HIVE CONCEPT: current_witness is the witness who produced
                # the current head block. Witnesses take turns producing
                # blocks in a round-robin schedule (top 20 + 1 backup).
                "current_witness": props.get("current_witness"),
            },
            "node": HIVE_NODES[0],
        })
    except Exception as err:
        return jsonify({
            "status": "error",
            "error": str(err),
        }), 503


# ---------------------------------------------------------------------------
#  6. START SERVER
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))

    print(f"\n  Hive Social App running on http://localhost:{port}")
    print(f"  Connected to: {HIVE_NODES[0]}")
    print(f"  Account: {USERNAME or '(read-only mode -- set HIVE_USERNAME in .env)'}")
    print(f"  Auth: {'Posting key loaded' if POSTING_KEY else 'No key -- write endpoints disabled'}")
    print(f"\n  Try it:")
    print(f"    curl http://localhost:{port}/api/feed/hive")
    print(f"    curl http://localhost:{port}/api/account/blocktrades")
    print(f"    curl http://localhost:{port}/api/health\n")

    # HIVE CONCEPT: debug=True enables auto-reload and detailed error pages.
    # NEVER use debug=True in production — it exposes a debugger that could
    # leak your private keys from memory.
    app.run(host="0.0.0.0", port=port, debug=True)
