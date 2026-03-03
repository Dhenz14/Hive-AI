# Hive Voting Bot (Python / beem)

An automated curation bot that monitors the Hive blockchain in real time and votes on posts matching configurable rules. Built with [beem](https://github.com/holgern/beem), the official Python library for Hive.

## Features

- **Real-time blockchain streaming** with automatic node failover (5 public nodes)
- **Rule-based filtering**: vote by tag, author, reputation, or word count
- **Trail voting**: follow another account's votes automatically
- **Blacklist/whitelist**: block or restrict which authors receive votes
- **Resource Credits (RC) checking** before every vote
- **Voting power (VP) monitoring** with configurable minimum threshold
- **Curation window** optimisation (configurable delay after post creation)
- **Daily vote limit** with 24-hour rolling window
- **Vote audit log** (JSON-lines file for every vote cast)
- **Duplicate vote prevention**
- **Graceful shutdown** (Ctrl+C / SIGTERM) with pending timer cleanup
- **Threaded block fetching** for performance

## Prerequisites

- Python >= 3.10
- A Hive account with the **posting private key**

## Quick Start

```bash
# 1. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate   # Linux/macOS
venv\Scripts\activate      # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create your credentials file
cp .env.example .env
# Edit .env -- set HIVE_USERNAME and HIVE_POSTING_KEY

# 4. Create your rules configuration
cp config.example.json config.json
# Edit config.json -- customise voting rules, thresholds, trail accounts

# 5. Run the bot
python bot.py
```

## Configuration

Configuration is split across two files:

### `.env` -- Credentials (NEVER commit this file)

| Variable             | Default                  | Description                               |
| -------------------- | ------------------------ | ----------------------------------------- |
| `HIVE_NODE`          | `https://api.hive.blog`  | Primary API node                          |
| `HIVE_USERNAME`      | (required)               | Your Hive account name                    |
| `HIVE_POSTING_KEY`   | (required)               | Posting private key (starts with `5...`)  |
| `VOTE_WEIGHT`        | `50.0`                   | Default vote weight override (percentage) |
| `MIN_REPUTATION`     | `25`                     | Minimum author reputation override        |
| `VOTE_DELAY_MINUTES` | `5`                      | Vote delay override                       |
| `MAX_DAILY_VOTES`    | `20`                     | Daily limit override                      |
| `MIN_RC_PERCENT`     | `10`                     | RC threshold override                     |

### `config.json` -- Rules and thresholds (safe to version-control)

```json
{
  "rules": [
    { "type": "tag", "value": "hive", "vote_weight": 50 },
    { "type": "author", "value": "buildteam", "vote_weight": 100 },
    { "type": "min_reputation", "value": 50, "vote_weight": 25 },
    { "type": "min_words", "value": 300, "vote_weight": 30 }
  ],

  "default_vote_weight": 50,
  "min_reputation": 25,
  "min_word_count": 0,

  "min_rc_percent": 10,
  "min_vp_percent": 80,
  "max_daily_votes": 20,
  "vote_delay_minutes": 5,

  "trail_accounts": [],
  "trail_vote_weight": 50,

  "blacklist": [],
  "whitelist": [],

  "vote_log_path": "vote_log.json"
}
```

Rules are evaluated in order. The **first matching rule** determines the vote weight. Blacklist overrides everything. If a whitelist is configured, only whitelisted authors are considered.

### Rule Types

| Type             | Value     | Description                                       |
| ---------------- | --------- | ------------------------------------------------- |
| `tag`            | string    | Match if the post has this tag                    |
| `author`         | string    | Match if the post author equals this value        |
| `min_reputation` | number    | Match if the author's reputation >= this value    |
| `min_words`      | number    | Match if the post body has >= this many words     |

## Hive Curation Economics

Understanding these concepts is key to effective curation on Hive.

### How Curation Rewards Work

When a post pays out after 7 days, the total pending rewards are split:

- **50%** goes to the post **author**
- **50%** goes to the **curators** (voters) proportionally

Your share of the curator pool depends on:

1. **Vote value**: Your Hive Power x voting mana% x vote weight%
2. **Timing**: Earlier voters get a larger share of curation rewards
3. **Total votes**: The more votes a post gets after yours, the more your early position is worth

This creates an incentive to discover and vote on quality content early.

### Voting Power (Mana)

- Regenerates linearly from 0% to 100% over **5 days** (20% per day)
- A full-strength (100%) vote costs **2%** of your mana
- A 50% vote costs ~1%, a 25% vote costs ~0.5%, etc.
- Sweet spot: keep VP above **80%** (~10 full-weight votes per day)
- Below 80% VP, each vote has diminished economic impact

### Resource Credits (RC)

- A separate "gas" budget consumed by every blockchain operation
- Also regenerates over 5 days (same rate as VP)
- Running out of RC blocks ALL transactions (votes, comments, transfers)
- Proportional to your Hive Power (more HP = more RC)
- Votes cost very little RC; you will rarely hit RC limits unless your HP is very low

### The 5-Minute Curation Window

The HF25 hard fork (June 2021) removed the "reverse auction" penalty, so you get full curation rewards instantly. However, waiting ~5 minutes is still strategic:

- Verify the post is not spam or plagiarism
- Let others see your vote and pile on (boosting total rewards)
- Avoid wasting mana on posts that will be downvoted

### Vote Timing Strategy

| Timing   | Advantage                            | Risk                  |
| -------- | ------------------------------------ | --------------------- |
| 0-5 min  | Maximum early-voter share            | Post might be spam    |
| 5-30 min | Good balance of safety and reward    | Moderate curation     |
| 30+ min  | Very safe (post is validated)        | Small curation share  |

## Trail Voting

Trail voting automatically mirrors another account's votes. Configure trail accounts in `config.json`:

```json
{
  "trail_accounts": ["curangel", "ocd"],
  "trail_vote_weight": 25
}
```

The bot watches for `vote` operations on-chain. When a trailed account upvotes a post, your bot votes on the same post after a 30-second delay. Blacklist and RC/VP checks still apply. Downvotes are never trailed.

## Vote Audit Log

Every vote is logged to `vote_log.json` (one JSON object per line):

```json
{"timestamp": "2026-02-26T12:00:00+00:00", "voter": "you", "author": "alice", "permlink": "my-post", "weight_percent": 50.0, "voting_power": 92.5, "resource_credits": 98.2, "reason": "tag:hive"}
```

This file grows append-only. Use it for debugging, analytics, or compliance auditing.

## Testing

```bash
# Install test dependencies (pytest is included in requirements.txt)
pip install -r requirements.txt

# Run all tests
pytest test_bot.py -v
```

Tests cover:

- Reputation score conversion (raw integer to human-readable)
- Tag extraction from json_metadata
- Word counting with Markdown/HTML stripping
- Rule engine matching logic (tags, authors, reputation, word count)
- Blacklist and whitelist behaviour
- Daily vote limiter
- Voted posts deduplication
- Configuration loading and defaults
- Edge cases

## beem vs. dhive

This bot uses **beem** (Python). The JavaScript version in `../js/` uses **dhive**.

| Feature           | beem (Python)                         | dhive (JavaScript)                        |
| ----------------- | ------------------------------------- | ----------------------------------------- |
| Streaming         | `Blockchain.stream()` generator       | `getOperationsStream()` async iterable    |
| Vote weight       | `0.0` to `100.0` (percentage)         | `-10000` to `10000` (basis points)        |
| Key handling      | `Hive(keys=[...])`                    | `PrivateKey.fromString(wif)`              |
| Node failover     | Built into `Hive(node=[...])`         | Built into `Client([...])`               |
| RC access         | `Account.get_rc()`                    | `rc_api.find_rc_accounts` RPC call        |
| Voting power      | `Account.get_voting_power()`          | Manual manabar calculation                |
| Vote casting      | `Comment.upvote(weight, voter)`       | `client.broadcast.vote({...}, key)`       |

## Security

- **Only use your POSTING key** -- it can only vote and comment, never transfer funds
- **Never commit `.env`** -- it contains your private key
- Keys never leave your machine; transactions are signed locally by beem
- The `.gitignore` should include `.env`, `config.json`, and `vote_log.json`

## Architecture

```text
.env ----------> Credentials (username, posting key)
config.json ---> Rules, thresholds, trail accounts, blacklist
                     |
                     v
bot.py --------> beem.Hive (5 failover nodes + posting key)
                     |
                     +-> Blockchain.stream(opNames=["comment", "vote"])
                     |   |
                     |   +-> "comment" ops --> Rule Engine --> Schedule Vote
                     |   |                                       |
                     |   +-> "vote" ops ----> Trail Engine ------+
                     |                                           |
                     |                                           v
                     |                      Pre-vote checks (RC, VP, daily limit)
                     |                                           |
                     |                                           v
                     |                      Comment.upvote() (signed with posting key)
                     |                                           |
                     |                                           v
                     |                      Append to vote_log.json
                     |
                     +-> Graceful shutdown (SIGINT/SIGTERM)
```

## Troubleshooting

| Symptom                              | Likely Cause             | Fix                                        |
| ------------------------------------ | ------------------------ | ------------------------------------------ |
| "FATAL: HIVE_USERNAME is not set"    | Missing `.env`           | Copy `.env.example` to `.env`              |
| "Missing posting key" error          | Wrong key type           | Use the WIF posting key (starts with `5`)  |
| "Resource Credits too low"           | Low HP account           | Delegate HP or reduce `max_daily_votes`    |
| "Voting power too low"               | Voting too aggressively  | Increase `min_vp_percent` or reduce votes  |
| "Daily vote limit reached"           | Hit `max_daily_votes`    | Wait 24h or increase the limit             |
| Stream keeps reconnecting            | Node issues              | Bot auto-retries; check your internet      |
| "already voted" errors               | Duplicate detection      | Normal -- the bot skips and moves on       |
| Import errors                        | Missing dependencies     | Run `pip install -r requirements.txt`      |

## License

MIT
