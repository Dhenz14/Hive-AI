#!/usr/bin/env python3
"""
=============================================================================
Hive Automated Voting / Curation Bot (Python / beem)
=============================================================================

A production-ready curation bot that streams the Hive blockchain in real time,
filters posts by configurable rules (tags, authors, reputation, word count),
checks Resource Credits and voting power, implements vote scheduling and trail
voting, supports blacklist/whitelist, and logs every vote to a JSON file.

TUTORIAL STRUCTURE:
    Every Hive-specific section has a "HIVE CONCEPT" docstring or comment that
    explains the underlying blockchain mechanic so you learn while you build.

QUICK START:
    1. cp .env.example .env                 -- fill in your posting key
    2. cp config.example.json config.json   -- customise rules
    3. pip install -r requirements.txt
    4. python bot.py

DEPENDENCIES:
    beem          -- The official Python library for Hive blockchain interaction
    python-dotenv -- Load .env files into os.environ

=============================================================================
"""

import json
import math
import os
import re
import signal
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
except ImportError:
    print("[FATAL] python-dotenv not installed.  Run: pip install python-dotenv")
    sys.exit(1)

try:
    # beem is the official Python library for interacting with the Hive blockchain.
    # It provides high-level classes for accounts, posts, blockchain streaming,
    # and transaction broadcasting.
    from beem import Hive
    from beem.account import Account
    from beem.blockchain import Blockchain
    from beem.comment import Comment
    from beem.exceptions import (
        AccountDoesNotExistsException,
        MissingKeyError,
        UnhandledRPCError,
    )
except ImportError:
    print("[FATAL] beem not installed.  Run: pip install beem")
    sys.exit(1)


# Load .env from the same directory as this script BEFORE reading any env vars
load_dotenv(Path(__file__).parent / ".env")


# =============================================================================
# HIVE CONCEPT -- Nodes & Failover
# =============================================================================
# Hive is a decentralised network of API nodes run by independent operators.
# Any single node can go offline, lag behind the head block, or rate-limit
# your requests.  Production bots must rotate through several nodes so the
# blockchain stream never stalls.
#
# Popular public nodes (as of 2026):
#   - https://api.hive.blog        (Hive core team)
#   - https://api.deathwing.me     (deathwing)
#   - https://hive-api.arcange.eu  (arcange)
#   - https://api.openhive.network (community-run)
#   - https://rpc.mahdiyari.info   (mahdiyari)
#
# beem's Hive() class accepts a `node` parameter as a list of URLs.  It
# automatically fails over to the next node if the current one is unavailable
# or returns errors.
# =============================================================================

FAILOVER_NODES = [
    os.getenv("HIVE_NODE", "https://api.hive.blog"),
    "https://api.deathwing.me",
    "https://hive-api.arcange.eu",
    "https://api.openhive.network",
    "https://rpc.mahdiyari.info",
]


# =============================================================================
# Logging (defined early so load_config_file can use it)
# =============================================================================

def log(msg: str):
    """Print an info message with ISO-8601 UTC timestamp."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    print(f"[{ts}] {msg}", flush=True)


def warn(msg: str):
    """Print a warning message with ISO-8601 UTC timestamp."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    print(f"[{ts}] WARN: {msg}", file=sys.stderr, flush=True)


def error(msg: str):
    """Print an error message with ISO-8601 UTC timestamp."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    print(f"[{ts}] ERROR: {msg}", file=sys.stderr, flush=True)


# =============================================================================
# Configuration -- loaded from .env (credentials) + config.json (rules)
# =============================================================================
# We separate credentials from rules:
#   .env         -- secret posting key, username (NEVER commit this file)
#   config.json  -- voting rules, thresholds, lists (safe to version-control)
# =============================================================================

def load_config_file() -> dict:
    """Load config.json, falling back to config.example.json, then defaults."""
    script_dir = Path(__file__).parent
    for filename in ("config.json", "config.example.json"):
        filepath = script_dir / filename
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                log(f"Loaded configuration from {filename}")
                return data
            except (json.JSONDecodeError, OSError) as exc:
                warn(f"Failed to parse {filepath}: {exc}")
    warn("No config.json found -- using built-in defaults")
    return {}


def _parse_int(value, default: int) -> int:
    """Safely parse an env var or config value to int."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


_config_file = load_config_file()


class Config:
    """
    Configuration object combining .env credentials and config.json rules.

    Credentials ALWAYS come from .env (never from config.json).
    Everything else comes from config.json with optional .env overrides.
    """

    # --- Credentials (from .env) ---
    username: str = os.getenv("HIVE_USERNAME", "")
    posting_key: str = os.getenv("HIVE_POSTING_KEY", "")

    # --- Voting rules (from config.json) ---
    # Each rule: {"type": "tag"|"author"|"min_reputation"|"min_words",
    #             "value": ..., "vote_weight": 50}
    rules: list = _config_file.get("rules", [])

    # Default vote weight when a rule doesn't specify one (1-100%)
    # .env VOTE_WEIGHT is in beem percentage (e.g. 50.0 = 50%)
    default_vote_weight: float = (
        float(os.getenv("VOTE_WEIGHT", "0")) or
        _config_file.get("default_vote_weight", 50)
    )

    # Global minimum reputation floor
    min_reputation: int = (
        _parse_int(os.getenv("MIN_REPUTATION"), 0) or
        _config_file.get("min_reputation", 25)
    )

    # Minimum Resource Credits percentage before the bot pauses
    min_rc_percent: int = _config_file.get(
        "min_rc_percent",
        _parse_int(os.getenv("MIN_RC_PERCENT"), 10),
    )

    # Minimum voting power percentage before the bot pauses voting
    # HIVE CONCEPT: Keeping VP above 80% maximises curation reward efficiency.
    # Each full-power vote costs ~2% VP.  At 80% VP you get ~10 full votes/day.
    min_vp_percent: int = _config_file.get("min_vp_percent", 80)

    # Maximum votes in a rolling 24-hour window
    max_daily_votes: int = _config_file.get(
        "max_daily_votes",
        _parse_int(os.getenv("MAX_DAILY_VOTES"), 20),
    )

    # Minutes to wait after post creation before casting the vote
    vote_delay_minutes: int = _config_file.get(
        "vote_delay_minutes",
        _parse_int(os.getenv("VOTE_DELAY_MINUTES"), 5),
    )

    # Trail voting: mirror these accounts' votes in real time
    trail_accounts: list = [
        a.lower() for a in _config_file.get("trail_accounts", [])
    ]
    trail_vote_weight: float = _config_file.get("trail_vote_weight", 50)

    # Blacklist: never vote on these authors (overrides everything)
    blacklist: list = [a.lower() for a in _config_file.get("blacklist", [])]

    # Whitelist: if non-empty, ONLY vote on posts by these authors
    whitelist: list = [a.lower() for a in _config_file.get("whitelist", [])]

    # Minimum word count in post body (0 = disabled)
    min_word_count: int = _config_file.get("min_word_count", 0)

    # Path to the vote audit log (JSON-lines file)
    vote_log_path: str = _config_file.get(
        "vote_log_path",
        str(Path(__file__).parent / "vote_log.json"),
    )


CONFIG = Config()


# =============================================================================
# Validation -- fail fast if credentials are missing
# =============================================================================

def validate_config():
    """Check that essential configuration values are present."""
    if not CONFIG.username:
        print("[FATAL] HIVE_USERNAME is not set in .env", file=sys.stderr)
        sys.exit(1)
    if not CONFIG.posting_key:
        print("[FATAL] HIVE_POSTING_KEY is not set in .env", file=sys.stderr)
        sys.exit(1)
    has_rules = len(CONFIG.rules) > 0
    has_trail = len(CONFIG.trail_accounts) > 0
    if not has_rules and not has_trail:
        print(
            "[FATAL] No voting rules in config.json and no trail_accounts "
            "configured.  The bot has nothing to do.",
            file=sys.stderr,
        )
        sys.exit(1)


# =============================================================================
# beem Hive Instance
# =============================================================================
# beem.Hive wraps the Hive JSON-RPC API.  We pass:
#   - node: list of node URLs for automatic failover
#   - keys: list of WIF private keys (just the posting key for voting)
#
# HIVE CONCEPT -- Key Types:
#   Hive accounts have a hierarchy of keys:
#     Owner key   -- can change all keys, recover the account (NEVER use in bots)
#     Active key  -- can transfer funds, power up/down, change settings
#     Posting key -- can ONLY vote, comment, and follow (SAFEST for bots)
#     Memo key    -- encrypts/decrypts private memo messages
#
#   We ONLY ever use the posting key.  Even if the bot is compromised, the
#   attacker cannot steal funds -- they can only vote and comment.
#
# The private key is used to sign vote transactions locally.  Your key NEVER
# leaves your machine -- only the signed transaction is sent to the network.
#
# beem handles node switching transparently: if an RPC call fails, it retries
# with the next node in the list.
# =============================================================================

hive_instance: Hive | None = None


def init_hive() -> Hive:
    """Initialise the beem Hive instance with failover nodes and posting key."""
    global hive_instance
    hive_instance = Hive(
        node=FAILOVER_NODES,
        keys=[CONFIG.posting_key],
        num_retries=5,         # retry each node up to 5 times on failure
        num_retries_call=3,    # retry each RPC call up to 3 times
        timeout=30,            # seconds per RPC call before giving up
    )
    log(f"Hive instance initialised with {len(FAILOVER_NODES)} failover nodes")
    return hive_instance


# =============================================================================
# State Tracking
# =============================================================================

# Rolling list of vote timestamps (epoch floats) for the last 24h.
vote_timestamps: list[float] = []

# Set of "author/permlink" strings already voted on (prevents double-votes).
voted_posts: set[str] = set()

# Pending vote timers (threading.Timer objects) -- cancelled on shutdown.
pending_timers: list[threading.Timer] = []
timer_lock = threading.Lock()

# Graceful shutdown flag (threading.Event for interruptible sleep).
shutting_down = threading.Event()


# =============================================================================
# Vote Audit Log
# =============================================================================
# Every vote the bot casts is appended to a JSON-lines file (one JSON object
# per line).  This provides a permanent audit trail for:
#   - Debugging: see exactly what was voted on and why
#   - Compliance: prove your voting pattern to community reviewers
#   - Analytics: import into a spreadsheet or database for curation analysis
#
# Each entry records the author, permlink, weight, VP/RC at vote time,
# the rule that triggered the vote, and whether it was a trail vote.
# =============================================================================

def append_vote_log(entry: dict):
    """Append a vote record to the JSON-lines audit log."""
    try:
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), **entry}
        with open(CONFIG.vote_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as exc:
        warn(f"Failed to write vote log: {exc}")


# =============================================================================
# HIVE CONCEPT -- Reputation
# =============================================================================
# On-chain reputation is stored as a large raw integer (can be negative).
# The human-readable score (25-75+) is computed with a log10 formula:
#
#   score = (log10(abs(raw_reputation)) - 9) * 9 + 25
#
# New accounts start at 25.  Receiving upvotes on your posts increases it;
# receiving downvotes from accounts with HIGHER reputation decreases it.
# A reputation of ~50 means a reasonably established account.  Whales are 60-75+.
#
# Why filter by reputation?
#   Spam/bot accounts tend to stay below rep 25-30.  Filtering them out avoids
#   wasting your voting mana on content that will likely be downvoted.
#
# beem's Account.get_reputation() returns the human-readable score directly,
# but we also provide the raw formula for educational purposes.
# =============================================================================

def raw_rep_to_score(raw) -> float:
    """
    Convert a raw on-chain reputation integer to a human-readable score.

    Examples:
        0         -> 25.0  (brand new account)
        1e9       -> 25.0
        1e10      -> 34.0
        1e12      -> 52.0  (established)
        1e15      -> 79.0  (whale)
        negative  -> negative score (flagged accounts)
    """
    r = int(raw) if isinstance(raw, str) else raw
    if r == 0:
        return 25.0
    neg = r < 0
    abs_r = abs(r)
    score = max(math.log10(abs_r) - 9, 0) * 9 + 25
    return -score if neg else round(score, 2)


# =============================================================================
# HIVE CONCEPT -- Resource Credits (RC)
# =============================================================================
# Every Hive account has Resource Credits -- a regenerating "gas" budget that
# is consumed by every on-chain operation (vote, comment, transfer, etc.).
#
# Key facts about RC:
#   - RC regenerates linearly from 0% to 100% over 5 days (432,000 seconds)
#   - Your maximum RC is proportional to your effective Hive Power (HP)
#   - Different operations cost different RC amounts:
#       * A vote costs very little (~0.003% for a typical account)
#       * A comment costs more (~0.5%)
#       * claim_account costs the most by far
#   - If you run out, you cannot broadcast ANY transaction at all
#   - You can delegate HP to other accounts to give them more RC
#
# beem's Account.get_rc() returns a dict with:
#   - "rc_manabar": {"current_mana": int, "last_update_time": int}
#   - "max_rc": int (maximum mana when fully regenerated)
#
# Because mana regenerates continuously, we must time-adjust current_mana:
#   adjusted = current_mana + (max_rc * elapsed_seconds / 432000)
#   adjusted = min(adjusted, max_rc)
#
# We check RC before every vote and pause if it drops below our threshold.
# =============================================================================

def get_rc_percent(username: str) -> float:
    """
    Get the current Resource Credits percentage for an account.

    Returns a float 0.0-100.0.  Returns 100.0 on error (don't block voting
    on transient API failures).
    """
    try:
        account = Account(username, blockchain_instance=hive_instance)
        # get_rc() calls the rc_api.find_rc_accounts endpoint
        rc = account.get_rc()

        max_rc = int(rc.get("max_rc", 0))
        if max_rc == 0:
            return 0.0

        current_mana = int(rc["rc_manabar"]["current_mana"])
        last_update = rc["rc_manabar"]["last_update_time"]

        # Time-adjust: RC regenerates linearly over 432,000 seconds (5 days)
        if isinstance(last_update, str):
            last_update_dt = datetime.strptime(last_update, "%Y-%m-%dT%H:%M:%S")
            last_update_ts = int(
                last_update_dt.replace(tzinfo=timezone.utc).timestamp()
            )
        else:
            last_update_ts = int(last_update)

        now = int(time.time())
        elapsed = max(0, now - last_update_ts)
        regen_time = 432000  # 5 days in seconds

        # Formula: adjusted = current + (max * elapsed / regen_time), capped at max
        adjusted = current_mana + (max_rc * elapsed) // regen_time
        adjusted = min(adjusted, max_rc)

        return round((adjusted / max_rc) * 100, 2)

    except Exception as exc:
        warn(f"RC check failed for @{username}: {exc}")
        return 100.0


# =============================================================================
# HIVE CONCEPT -- Voting Power / Voting Mana
# =============================================================================
# Each Hive account has "voting mana" that determines the economic weight of
# each vote.
#
# How it works:
#   - Mana regenerates linearly from 0% to 100% over 5 days (432,000 seconds)
#   - That is 20% regeneration per day
#   - A 100%-weight vote at full mana costs exactly 2% of your mana
#   - A 50%-weight vote costs ~1%, a 25%-weight vote costs ~0.5%, etc.
#   - Formula: mana_cost = current_mana * vote_weight / 10000
#   - The less mana you have, the weaker (lower $-value) your votes become
#
# Optimal strategy:
#   Keep mana above 80%.  At 80% mana, each vote is worth 80% of its maximum
#   dollar value.  Casting 10 full-power votes per day = 20% spent, 20%
#   regenerated = steady 80% VP.  This is the "sweet spot".
#
# beem's Account.get_voting_power() returns a float 0-100 after applying the
# time-adjustment formula internally (reads voting_manabar from the account
# and adjusts for elapsed time since last_update_time).
# =============================================================================

def get_voting_power(username: str) -> float:
    """
    Get the current voting power (mana) percentage for an account.

    Returns a float 0.0-100.0.  Returns 100.0 on error.
    """
    try:
        account = Account(username, blockchain_instance=hive_instance)
        # get_voting_power() applies time-adjustment automatically
        vp = account.get_voting_power()
        return round(vp, 2)
    except Exception as exc:
        warn(f"Voting power check failed for @{username}: {exc}")
        return 100.0


# =============================================================================
# Reputation Lookup
# =============================================================================

def get_author_reputation(author: str) -> float:
    """
    Fetch an author's human-readable reputation score.

    beem's Account class provides the `reputation` property already converted
    from the raw integer to the human-readable log10 scale.

    Returns 25.0 on error (default for new accounts).
    """
    try:
        account = Account(author, blockchain_instance=hive_instance)
        # beem's .reputation property returns the human-readable score directly
        return round(account.reputation, 2)
    except AccountDoesNotExistsException:
        warn(f"Account @{author} does not exist")
        return 25.0
    except Exception as exc:
        warn(f"Reputation check failed for @{author}: {exc}")
        return 25.0


# =============================================================================
# Daily Vote Limiter
# =============================================================================
# We maintain a rolling window of vote timestamps.  Before each vote we prune
# entries older than 24 hours.  If the remaining count >= max_daily_votes,
# we skip the vote.
#
# Why limit daily votes?
#   - Each vote costs VP.  Unlimited voting = 0% VP = worthless votes.
#   - Hive community norms frown on "spray voting" (mass low-weight votes).
#   - Curation rewards are proportional to vote value, so fewer stronger
#     votes earn more than many weak ones.
# =============================================================================

def _prune_old_votes():
    """Remove vote timestamps older than 24 hours from the rolling window."""
    cutoff = time.time() - 24 * 3600
    while vote_timestamps and vote_timestamps[0] < cutoff:
        vote_timestamps.pop(0)


def can_vote_within_daily_limit() -> bool:
    """Check if we have remaining votes in the 24-hour rolling window."""
    _prune_old_votes()
    return len(vote_timestamps) < CONFIG.max_daily_votes


def votes_remaining_today() -> int:
    """Return how many votes remain in the current 24-hour window."""
    _prune_old_votes()
    return max(0, CONFIG.max_daily_votes - len(vote_timestamps))


def record_vote():
    """Record the current time as a vote in the rolling window."""
    vote_timestamps.append(time.time())


# =============================================================================
# Post Filtering -- Rule Engine
# =============================================================================
# The rule engine evaluates each incoming post against the rules in config.json.
# If ANY rule matches, the post is eligible for a vote.  Each rule can specify
# its own vote_weight override; otherwise the default weight is used.
#
# Supported rule types:
#   "tag"            -- match if the post has this tag
#   "author"         -- match if the post author matches the value
#   "min_reputation" -- match if the author's rep >= value
#   "min_words"      -- match if the post body has >= value words
#
# On top of rules, blacklist/whitelist act as global overrides:
#   blacklist -- if the author is on this list, NEVER vote (overrides everything)
#   whitelist -- if non-empty, ONLY consider authors on this list
# =============================================================================

def extract_tags(op: dict) -> list[str]:
    """
    Extract tags from a blockchain comment operation.

    HIVE CONCEPT -- json_metadata:
        Each post carries a JSON blob in the json_metadata field.  Frontends
        (PeakD, Ecency, Hive.blog) write structured data here, including:
          - "tags": an array of tag strings (most important for filtering)
          - "app": which frontend created the post (e.g. "peakd/2024.1.1")
          - "image": array of image URLs used in the post
          - "format": "markdown" or "html"

        The parent_permlink of a root post doubles as its primary (first) tag.
        Some posts only store the tag in parent_permlink, others also include
        it in json_metadata["tags"].  We check both and deduplicate.

    Args:
        op: Dict with "parent_permlink" and "json_metadata" keys.

    Returns:
        A deduplicated list of lowercase tag strings.
    """
    tags: list[str] = []

    # parent_permlink is the primary tag/community for root posts
    parent_permlink = op.get("parent_permlink", "")
    if parent_permlink:
        tags.append(parent_permlink.lower())

    # Parse json_metadata for the "tags" array
    json_metadata = op.get("json_metadata", "")
    if isinstance(json_metadata, str):
        try:
            meta = json.loads(json_metadata) if json_metadata else {}
        except json.JSONDecodeError:
            meta = {}  # malformed JSON is common on-chain -- just skip
    elif isinstance(json_metadata, dict):
        meta = json_metadata
    else:
        meta = {}

    if isinstance(meta.get("tags"), list):
        for t in meta["tags"]:
            if isinstance(t, str):
                tags.append(t.lower())

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def count_words(body: str) -> int:
    """
    Count words in a post body after stripping Markdown and HTML.

    HIVE CONCEPT -- Post body format:
        Post bodies are Markdown with some HTML allowed.  We strip formatting
        before counting to get a rough word count that helps filter low-effort
        posts (single images, one-liners, etc.).

    Args:
        body: The raw Markdown/HTML post body.

    Returns:
        Number of words.
    """
    # Strip Markdown images: ![alt](url)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", body)
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Strip Markdown links: [text](url) -> text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Strip Markdown formatting characters
    text = re.sub(r"[*_~#>`]", "", text)
    # Split on whitespace and filter empty strings
    words = [w for w in text.split() if w]
    return len(words)


def evaluate_rules(op: dict, author_rep: float) -> dict:
    """
    Evaluate voting rules against a post.

    Args:
        op: The comment operation dict from the blockchain stream.
            Keys include: author, permlink, parent_permlink, body, json_metadata.
        author_rep: The author's human-readable reputation score.

    Returns:
        A dict with:
          - "match" (bool): whether any rule matched
          - "weight" (float): vote weight percentage (1-100)
          - "rule" (str): description of the matching rule
    """
    author = op.get("author", "").lower()

    # --- Blacklist check (highest priority -- overrides everything) ---
    if author in CONFIG.blacklist:
        return {"match": False, "weight": 0, "rule": "blacklisted"}

    # --- Whitelist check (if configured, only whitelisted authors proceed) ---
    if CONFIG.whitelist and author not in CONFIG.whitelist:
        return {"match": False, "weight": 0, "rule": "not_whitelisted"}

    # --- Evaluate each rule ---
    tags = extract_tags(op)
    word_count = count_words(op.get("body", ""))

    for rule in CONFIG.rules:
        weight = rule.get("vote_weight", CONFIG.default_vote_weight)
        rule_type = rule.get("type", "")
        rule_value = rule.get("value", "")

        if rule_type == "tag":
            if str(rule_value).lower() in tags:
                return {"match": True, "weight": weight, "rule": f"tag:{rule_value}"}

        elif rule_type == "author":
            if author == str(rule_value).lower():
                return {"match": True, "weight": weight, "rule": f"author:{rule_value}"}

        elif rule_type == "min_reputation":
            if author_rep >= rule_value:
                return {
                    "match": True,
                    "weight": weight,
                    "rule": f"min_reputation:{rule_value}",
                }

        elif rule_type == "min_words":
            if word_count >= rule_value:
                return {
                    "match": True,
                    "weight": weight,
                    "rule": f"min_words:{rule_value}",
                }

        else:
            warn(f"Unknown rule type: {rule_type}")

    return {"match": False, "weight": 0, "rule": "no_match"}


# =============================================================================
# HIVE CONCEPT -- Casting a Vote
# =============================================================================
# The "vote" operation has these fields:
#   - voter:    your account name
#   - author:   the post author's account name
#   - permlink: the post's permlink (URL slug, e.g. "my-first-post")
#   - weight:   vote strength
#
# On-chain, weight ranges from -10000 to 10000 (basis points).
# beem's .upvote() method accepts a PERCENTAGE float (0.0 to 100.0) and
# converts it internally.
#
# HIVE CONCEPT -- Curation Rewards:
#   When a post pays out after 7 days, total rewards are split:
#     - 50% to the post AUTHOR
#     - 50% to the CURATORS (voters) proportionally
#
#   Your curation share depends on:
#     1. The HP-value of your vote (your HP * VP% * weight / 100)
#     2. When you voted relative to others (earlier = larger share)
#     3. The total votes the post received after yours
#
#   Early voters who discover good content are rewarded most.  If you vote
#   first on a post that later receives massive upvotes, you capture a huge
#   share of the curation pool.  This economic incentive is what makes
#   automated curation bots valuable on Hive.
#
#   The 5-minute "reverse auction" penalty was REMOVED in HF25 (June 2021),
#   so there is no penalty for voting immediately.  However, waiting ~5 min
#   lets you verify the post is not spam before committing your mana.
# =============================================================================

def cast_vote(author: str, permlink: str, weight_percent: float, reason: str) -> bool:
    """
    Cast a vote on a post after performing all pre-flight checks.

    Args:
        author: The post author's Hive username.
        permlink: The post's permlink (URL slug).
        weight_percent: Vote weight as a percentage (1.0-100.0).
        reason: Human-readable reason the vote was triggered.

    Returns:
        True if the vote was broadcast successfully, False otherwise.
    """
    post_key = f"{author}/{permlink}"

    # --- Prevent double-voting ---
    if post_key in voted_posts:
        log(f"Already voted on {post_key}, skipping")
        return False

    # --- Daily limit check ---
    if not can_vote_within_daily_limit():
        warn(
            f"Daily vote limit reached ({CONFIG.max_daily_votes}). "
            f"Skipping {post_key}. Will resume when oldest vote ages out."
        )
        return False

    # --- RC check ---
    rc = get_rc_percent(CONFIG.username)
    if rc < CONFIG.min_rc_percent:
        warn(
            f"Resource Credits too low: {rc}% < {CONFIG.min_rc_percent}%. "
            f"Skipping {post_key}. RC regenerates ~20%/day."
        )
        return False

    # --- Voting power check ---
    vp = get_voting_power(CONFIG.username)
    if vp < CONFIG.min_vp_percent:
        warn(
            f"Voting power too low: {vp}% < {CONFIG.min_vp_percent}%. "
            f"Pausing votes to let mana regenerate (~20%/day). Skipping {post_key}."
        )
        return False

    # Clamp weight to valid range
    weight_percent = max(1.0, min(100.0, float(weight_percent)))

    try:
        log(
            f"Casting vote: @{author}/{permlink} | weight: {weight_percent}% "
            f"| VP: {vp}% | RC: {rc}% | reason: {reason}"
        )

        # beem's Comment class represents a post or reply on the blockchain.
        # We construct it from "@author/permlink" and then call .upvote().
        #
        # Comment.upvote() parameters:
        #   weight -- float between 0.0 and 100.0 (percentage, NOT basis points)
        #   voter  -- the account name casting the vote
        #
        # Internally, beem converts the percentage to the on-chain -10000..10000
        # scale, constructs the vote operation, signs it with the posting key
        # we provided to Hive(), and broadcasts it to the connected node.
        post = Comment(
            f"@{author}/{permlink}",
            blockchain_instance=hive_instance,
        )
        post.upvote(weight=weight_percent, voter=CONFIG.username)

        log(
            f"Vote broadcast successfully for @{author}/{permlink} | "
            f"remaining today: {votes_remaining_today() - 1}"
        )

        voted_posts.add(post_key)
        record_vote()

        # Audit log entry
        append_vote_log({
            "voter": CONFIG.username,
            "author": author,
            "permlink": permlink,
            "weight_percent": weight_percent,
            "voting_power": vp,
            "resource_credits": rc,
            "reason": reason,
        })

        return True

    except UnhandledRPCError as exc:
        error(f"Vote RPC error for {post_key}: {exc}")
        # Common RPC errors:
        #   "You have already voted in a similar way" -- duplicate vote
        #   "Voting weight is too small"              -- rounds to zero
        #   "Account does not have enough RC"         -- resource credits depleted
        if "already voted" in str(exc).lower():
            voted_posts.add(post_key)

        append_vote_log({
            "voter": CONFIG.username, "author": author, "permlink": permlink,
            "weight_percent": weight_percent, "reason": reason,
            "error": str(exc),
        })
        return False

    except MissingKeyError:
        error(
            f"Missing posting key for @{CONFIG.username}. "
            f"Check HIVE_POSTING_KEY in .env"
        )
        return False

    except Exception as exc:
        error(f"Unexpected error voting on {post_key}: {exc}")
        append_vote_log({
            "voter": CONFIG.username, "author": author, "permlink": permlink,
            "weight_percent": weight_percent, "reason": reason,
            "error": str(exc),
        })
        return False


# =============================================================================
# HIVE CONCEPT -- Curation Window (Vote Delay)
# =============================================================================
# After HF25 (June 2021), the "reverse auction" penalty was removed.  You
# receive full curation rewards regardless of when you vote within the 7-day
# payout window.
#
# However, there are still strategic reasons to wait a few minutes:
#   1. VERIFICATION: Confirm the post isn't spam, plagiarism, or AI slop.
#   2. AMPLIFICATION: Others see your vote and pile on, boosting total payout
#      and therefore your curation reward share.
#   3. RISK MANAGEMENT: Avoid wasting mana on posts that get downvoted.
#   4. FRONT-RUNNING: Vote just before the "whale pile-on" at the 5-minute
#      mark to capture maximum early-voter share.
#
# The 7-day payout window is absolute.  After 7 days, voting on a post has
# zero effect (no rewards, no influence on payout).
# =============================================================================

def schedule_vote(
    author: str,
    permlink: str,
    post_created_str: str,
    weight_percent: float,
    reason: str,
):
    """
    Schedule a vote to be cast after the curation delay.

    If the post is already old enough (stream was lagging), vote immediately.
    Otherwise, set a threading.Timer that fires when the delay period expires.

    Args:
        author: Post author.
        permlink: Post permlink.
        post_created_str: ISO timestamp of when the post was created.
        weight_percent: Vote weight (1-100%).
        reason: Reason for the vote.
    """
    post_key = f"{author}/{permlink}"
    if post_key in voted_posts:
        return

    delay_seconds = CONFIG.vote_delay_minutes * 60

    # Parse the post creation timestamp
    try:
        ts_str = str(post_created_str)
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1]
        # Handle both "2026-02-26T12:00:00" and "2026-02-26 12:00:00" formats
        ts_str = ts_str.replace(" ", "T")
        post_created = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        post_created = datetime.now(timezone.utc)

    age_seconds = (datetime.now(timezone.utc) - post_created).total_seconds()
    remaining_delay = max(0, delay_seconds - age_seconds)

    if remaining_delay > 0:
        log(
            f"Scheduling vote for @{author}/{permlink} in "
            f"{int(remaining_delay)}s (curation delay) | "
            f"weight: {weight_percent}% | reason: {reason}"
        )
    else:
        log(
            f"Post @{author}/{permlink} is already {int(age_seconds)}s old "
            f"-- voting immediately | weight: {weight_percent}% | reason: {reason}"
        )

    def _delayed_vote():
        """Timer callback: cast the vote unless we're shutting down."""
        if shutting_down.is_set():
            return
        cast_vote(author, permlink, weight_percent, reason)

    timer = threading.Timer(remaining_delay, _delayed_vote)
    timer.daemon = True  # don't block process exit
    timer.start()

    with timer_lock:
        pending_timers.append(timer)


# =============================================================================
# HIVE CONCEPT -- Trail Voting
# =============================================================================
# Trail voting (also called "curation trails") means automatically copying
# another account's votes.  When a trailed account votes on a post, your bot
# immediately votes on the same post with your configured trail weight.
#
# Why trail vote?
#   - Passive curation: follow a trusted curator without manual effort
#   - Community support: trail your community's curation account
#   - Curation guilds: coordinate voting power across multiple accounts
#
# Popular trail services include hive.vote and leo.voter, but this bot
# implements trailing natively by watching for "vote" operations on-chain.
#
# When we see a vote operation where voter == a trailed account, we schedule
# a vote on the same author/permlink with our trail weight.  Blacklist and
# RC/VP checks still apply.  We NEVER trail downvotes (negative weight) to
# avoid accidental flagging.
# =============================================================================

def handle_trail_vote(op: dict):
    """
    Process a vote operation to check if we should trail it.

    Args:
        op: The vote operation dict with keys: voter, author, permlink, weight.
    """
    voter = op.get("voter", "").lower()

    # Only process votes from accounts we're trailing
    if voter not in CONFIG.trail_accounts:
        return

    # Skip downvotes and unvotes -- only trail upvotes
    weight = op.get("weight", 0)
    if weight <= 0:
        log(f"Trail: ignoring downvote/unvote by @{voter} (weight: {weight})")
        return

    author = op.get("author", "").lower()
    permlink = op.get("permlink", "")

    # Blacklist still applies to trail votes
    if author in CONFIG.blacklist:
        log(f"Trail: @{voter} voted on blacklisted @{author}, skipping")
        return

    post_key = f"{author}/{permlink}"
    if post_key in voted_posts:
        log(f"Trail: already voted on {post_key}, skipping")
        return

    log(
        f"Trail: @{voter} voted {weight / 100}% on @{author}/{permlink} "
        f"-- mirroring with {CONFIG.trail_vote_weight}%"
    )

    # Trail votes use a short 30-second delay rather than the full curation
    # delay, since the trailed account already evaluated the content.
    def _do_trail_vote():
        if shutting_down.is_set():
            return
        cast_vote(author, permlink, CONFIG.trail_vote_weight, f"trail:{voter}")

    timer = threading.Timer(30, _do_trail_vote)
    timer.daemon = True
    timer.start()

    with timer_lock:
        pending_timers.append(timer)


# =============================================================================
# HIVE CONCEPT -- Blockchain Streaming
# =============================================================================
# The Hive blockchain produces a new block every 3 seconds.  Each block
# contains zero or more transactions, each with one or more operations.
#
# beem's Blockchain class provides streaming via:
#
#   Blockchain.stream(opNames=["comment", "vote"])
#     A Python generator that yields individual operations filtered by type.
#     Each yielded dict contains the operation fields plus metadata:
#       - "type": the operation name ("comment", "vote", etc.)
#       - "block_num": which block this operation was in
#       - "timestamp": the block's timestamp
#       - "trx_id": the transaction hash
#
# Streaming modes (via `mode` parameter to Blockchain()):
#
#   "head":
#     Yields blocks as soon as the connected node receives them from the
#     producing witness.  Near real-time (~3s latency).  There's a tiny
#     chance of a micro-fork reverting the last 1-2 blocks, but for voting
#     this risk is negligible and the speed is essential.
#
#   "irreversible":
#     Only yields blocks confirmed by 2/3+ of witnesses (~21).  Adds ~45
#     seconds of latency but guarantees finality.  Use for financial apps.
#
# Common operation types:
#   "comment"     -- new post or reply (parent_author="" means root post)
#   "vote"        -- an upvote or downvote
#   "transfer"    -- HIVE/HBD token transfer
#   "custom_json" -- app-specific data (Splinterlands, Hive Engine, etc.)
#
# The stream automatically reconnects on node failures using beem's
# built-in failover.  We wrap it in a retry loop for extra resilience.
# =============================================================================

def start_stream():
    """
    Main streaming loop.  Watches for new posts and votes on the blockchain.

    Processes:
      - "comment" operations: evaluated against our rules for auto-voting
      - "vote" operations: checked for trail voting (if trail accounts configured)
    """
    log("Starting blockchain stream (mode: head)...")
    log(
        f"Rules: {len(CONFIG.rules)} configured | "
        f"Trail: [{', '.join(CONFIG.trail_accounts) or 'none'}] | "
        f"Blacklist: {len(CONFIG.blacklist)} accounts | "
        f"Whitelist: {len(CONFIG.whitelist) if CONFIG.whitelist else 'off'} | "
        f"Default weight: {CONFIG.default_vote_weight}% | "
        f"Delay: {CONFIG.vote_delay_minutes}m | "
        f"Max/day: {CONFIG.max_daily_votes} | "
        f"Min VP: {CONFIG.min_vp_percent}% | "
        f"Min RC: {CONFIG.min_rc_percent}%"
    )

    # Determine which operation types to stream
    op_types = ["comment"]
    if CONFIG.trail_accounts:
        op_types.append("vote")

    while not shutting_down.is_set():
        try:
            # Blockchain() creates a streaming interface connected to our Hive client
            blockchain = Blockchain(
                blockchain_instance=hive_instance,
                mode="head",  # "head" = latest block, "irreversible" = finalised
            )

            # stream() is a generator that yields operations indefinitely.
            # opNames filters to only the types we care about.
            # raw_ops=False means beem parses the operation into a dict for us.
            # threading=True uses background threads for faster block fetching.
            log(f"Streaming operations: {op_types}")
            for op in blockchain.stream(
                opNames=op_types,
                raw_ops=False,
                threading=True,
            ):
                if shutting_down.is_set():
                    break

                op_type = op.get("type", "")

                # --- Trail voting: watch for "vote" operations ---
                if op_type == "vote" and CONFIG.trail_accounts:
                    handle_trail_vote(op)
                    continue

                # --- Rule-based voting: watch for "comment" operations ---
                if op_type != "comment":
                    continue

                # HIVE CONCEPT: parent_author == "" means root post (not a reply).
                # Replies have parent_author set to the post they're replying to.
                if op.get("parent_author", "") != "":
                    continue

                author = op.get("author", "")

                # Fetch the author's reputation
                author_rep = get_author_reputation(author)

                # Global reputation floor check
                if author_rep < CONFIG.min_reputation:
                    continue

                # Evaluate rules
                result = evaluate_rules(op, author_rep)
                if not result["match"]:
                    continue

                # Global minimum word count check
                if CONFIG.min_word_count > 0:
                    wc = count_words(op.get("body", ""))
                    if wc < CONFIG.min_word_count:
                        log(
                            f"Skipping @{author}/{op.get('permlink', '')}: "
                            f"{wc} words < minimum {CONFIG.min_word_count}"
                        )
                        continue

                title = op.get("title", "(no title)")
                log(
                    f'Matched post: @{author}/{op.get("permlink", "")} '
                    f'-- "{title}" | rule: {result["rule"]} | rep: {author_rep}'
                )

                # Schedule the vote with curation delay
                timestamp = op.get(
                    "timestamp",
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                )
                if isinstance(timestamp, datetime):
                    timestamp = timestamp.strftime("%Y-%m-%dT%H:%M:%S")

                schedule_vote(
                    author,
                    op.get("permlink", ""),
                    str(timestamp),
                    result["weight"],
                    result["rule"],
                )

            # If stream ends without error (unlikely), restart
            if not shutting_down.is_set():
                log("Stream ended unexpectedly, reconnecting...")

        except KeyboardInterrupt:
            break

        except Exception as exc:
            if shutting_down.is_set():
                break
            error(f"Stream error: {exc}")
            log("Reconnecting in 10 seconds (beem will try next failover node)...")
            # Use the shutdown event as an interruptible sleep
            shutting_down.wait(timeout=10)

    log("Stream stopped.")


# =============================================================================
# Graceful Shutdown
# =============================================================================
# On SIGINT (Ctrl+C) or SIGTERM, we:
#   1. Set the shutting_down event to break the stream loop
#   2. Cancel all pending vote timers (so no votes fire after shutdown)
#   3. Log a session summary
#   4. Let the process exit cleanly
# =============================================================================

def shutdown_handler(signum, frame):
    """Handle SIGINT/SIGTERM for graceful shutdown."""
    if shutting_down.is_set():
        return  # prevent double-shutdown

    sig_name = (
        signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    )
    log(f"\nReceived {sig_name}. Shutting down gracefully...")

    shutting_down.set()

    # Cancel all pending vote timers
    with timer_lock:
        cancelled = len(pending_timers)
        for timer in pending_timers:
            timer.cancel()
        pending_timers.clear()

    log(f"Cancelled {cancelled} pending vote(s).")
    log(f"Total votes cast this session: {len(voted_posts)}")
    log(f"Vote log: {CONFIG.vote_log_path}")


def setup_shutdown_handlers():
    """Register signal handlers for graceful shutdown."""
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # On Windows, SIGTERM may not be available, but SIGINT (Ctrl+C) works.
    # SIGBREAK (Ctrl+Break) is Windows-specific.
    if sys.platform == "win32" and hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, shutdown_handler)


# =============================================================================
# Startup Banner
# =============================================================================

def print_startup_info():
    """Display account info and configuration at startup."""
    log("=" * 65)
    log("  Hive Voting Bot -- Automated Curation Engine (Python / beem)")
    log("=" * 65)
    log(f"Account:        @{CONFIG.username}")
    log(f"Nodes:          {len(FAILOVER_NODES)} configured (failover enabled)")
    log(f"Rules:          {len(CONFIG.rules)} voting rules loaded")
    log(f"Default weight: {CONFIG.default_vote_weight}%")
    log(f"Min reputation: {CONFIG.min_reputation}")
    log(f"Min word count: {CONFIG.min_word_count or 'off'}")
    log(f"Vote delay:     {CONFIG.vote_delay_minutes} minutes")
    log(f"Max daily:      {CONFIG.max_daily_votes}")
    log(f"Min VP:         {CONFIG.min_vp_percent}%")
    log(f"Min RC:         {CONFIG.min_rc_percent}%")
    log(f"Trail:          [{', '.join(CONFIG.trail_accounts) or 'none'}]")
    log(f"Blacklist:      {len(CONFIG.blacklist)} account(s)")
    wl = f"{len(CONFIG.whitelist)} account(s)" if CONFIG.whitelist else "off"
    log(f"Whitelist:      {wl}")
    log(f"Vote log:       {CONFIG.vote_log_path}")

    # Fetch live account info
    try:
        rep = get_author_reputation(CONFIG.username)
        vp = get_voting_power(CONFIG.username)
        rc = get_rc_percent(CONFIG.username)
        log("---")
        log(f"Reputation:      {rep}")
        log(f"Voting Power:    {vp}%")
        log(f"Resource Credits: {rc}%")
    except Exception as exc:
        warn(f"Could not fetch account info: {exc}")

    log("=" * 65)


# =============================================================================
# Main
# =============================================================================

def main():
    """Entry point: validate, initialise, and start streaming."""
    validate_config()
    init_hive()
    setup_shutdown_handlers()
    print_startup_info()
    start_stream()


if __name__ == "__main__":
    main()
