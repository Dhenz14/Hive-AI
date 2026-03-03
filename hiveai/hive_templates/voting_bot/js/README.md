# Hive Voting Bot (JavaScript / dhive)

An automated curation bot that monitors the Hive blockchain in real time and votes on posts matching configurable rules. Built with [@hiveio/dhive](https://github.com/openhive-network/dhive).

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
- **Graceful shutdown** (Ctrl+C) with pending timer cleanup

## Prerequisites

- Node.js >= 18.0.0
- A Hive account with the **posting private key**

## Quick Start

```bash
# 1. Install dependencies
npm install

# 2. Create your credentials file
cp .env.example .env
# Edit .env -- set HIVE_USERNAME and HIVE_POSTING_KEY

# 3. Create your rules configuration
cp config.example.json config.json
# Edit config.json -- customise voting rules, thresholds, trail accounts

# 4. Run the bot
node bot.js

# Or with auto-restart on file changes (Node 18+):
npm run dev
```

## Configuration

Configuration is split across two files:

### `.env` -- Credentials (NEVER commit this file)

| Variable | Default | Description |
|---|---|---|
| `HIVE_NODE` | `https://api.hive.blog` | Primary API node |
| `HIVE_USERNAME` | (required) | Your Hive account name |
| `HIVE_POSTING_KEY` | (required) | Posting private key (starts with `5...`) |
| `VOTE_WEIGHT` | `5000` | Default vote weight override (10000=100%) |
| `MIN_REPUTATION` | `25` | Minimum author reputation override |
| `VOTE_DELAY_MINUTES` | `5` | Vote delay override |
| `MAX_DAILY_VOTES` | `20` | Daily limit override |
| `MIN_RC_PERCENT` | `20` | RC threshold override |

### `config.json` -- Rules and thresholds (safe to version-control)

```jsonc
{
  "rules": [
    // Vote by tag (any post tagged "hive" gets a 50% vote)
    { "type": "tag", "value": "hive", "vote_weight": 50 },

    // Vote by author (always 100% for this author)
    { "type": "author", "value": "buildteam", "vote_weight": 100 },

    // Vote by reputation (authors with rep >= 50 get a 25% vote)
    { "type": "min_reputation", "value": 50, "vote_weight": 25 },

    // Vote by content length (posts with 300+ words get a 30% vote)
    { "type": "min_words", "value": 300, "vote_weight": 30 }
  ],

  "default_vote_weight": 50,     // Used when a rule doesn't specify weight
  "min_reputation": 25,          // Global floor (skip posts below this)
  "min_word_count": 0,           // Global min word count (0 = disabled)

  "min_rc_percent": 10,          // Pause voting when RC drops below this
  "min_vp_percent": 80,          // Pause voting when VP drops below this
  "max_daily_votes": 20,         // Max votes in a 24-hour rolling window
  "vote_delay_minutes": 5,       // Wait after post creation before voting

  "trail_accounts": [],          // Accounts to mirror votes from
  "trail_vote_weight": 50,       // Weight when trail voting (%)

  "blacklist": [],               // Never vote on these authors
  "whitelist": [],               // If set, ONLY vote on these authors

  "vote_log_path": "vote_log.json"
}
```

Rules are evaluated in order. The **first matching rule** determines the vote weight. Blacklist overrides everything. If a whitelist is configured, only whitelisted authors are considered.

## Hive Curation Economics

Understanding these concepts is key to effective curation on Hive.

### How Curation Rewards Work

When a post pays out after 7 days, the total pending rewards are split:
- **50%** goes to the post **author**
- **50%** goes to the **curators** (voters) proportionally

Your share of the curator pool depends on:
1. **Vote value**: Your Hive Power x voting mana percentage x vote weight
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
- Votes cost very little RC; you'll rarely hit RC limits unless your HP is very low

### The 5-Minute Curation Window

The HF25 hard fork (June 2021) removed the "reverse auction" penalty, so you get full curation rewards instantly. However, waiting ~5 minutes is still strategic:
- Verify the post isn't spam or plagiarism
- Let others see your vote and pile on (boosting total rewards)
- Avoid wasting mana on posts that will be downvoted

### Vote Timing Strategy

| Timing | Advantage | Risk |
|---|---|---|
| 0-5 min | Maximum early-voter share | Post might be spam |
| 5-30 min | Good balance of safety and reward | Moderate curation share |
| 30+ min | Very safe (post is validated) | Small curation share |

## Trail Voting

Trail voting automatically mirrors another account's votes. This is useful for:
- Following a trusted curator passively
- Community curation accounts
- Coordinating voting power across multiple accounts

Configure trail accounts in `config.json`:

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
{"timestamp":"2026-02-26T12:00:00.000Z","voter":"you","author":"alice","permlink":"my-post","weight_percent":50,"dhive_weight":5000,"voting_power":92.5,"resource_credits":98.2,"reason":"tag:hive","block_num":12345678,"tx_id":"abc123..."}
```

This file grows append-only. Use it for debugging, analytics, or compliance auditing.

## Testing

```bash
node test.js
```

Tests cover:
- Reputation score conversion
- Tag extraction from json_metadata
- Word counting with Markdown/HTML stripping
- Rule engine matching logic
- Daily vote limiter
- Edge cases

## Security

- **Only use your POSTING key** -- it can only vote and comment, never transfer funds
- **Never commit `.env`** -- it contains your private key
- Keys never leave your machine; transactions are signed locally by dhive
- The `.gitignore` should include `.env`, `config.json`, and `vote_log.json`

## Architecture

```
.env ---------> Credentials (username, posting key)
config.json --> Rules, thresholds, trail accounts, blacklist
                    |
                    v
bot.js -------> dhive Client (5 failover nodes)
                    |
                    +-> Blockchain Stream (getOperationsStream, mode=latest)
                    |   |
                    |   +-> "comment" ops --> Rule Engine --> Schedule Vote
                    |   |                                       |
                    |   +-> "vote" ops ----> Trail Engine ------+
                    |                                           |
                    |                                           v
                    |                      Pre-vote checks (RC, VP, daily limit)
                    |                                           |
                    |                                           v
                    |                      Broadcast vote (signed with posting key)
                    |                                           |
                    |                                           v
                    |                      Append to vote_log.json
                    |
                    +-> Graceful shutdown (SIGINT/SIGTERM)
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| "FATAL: HIVE_USERNAME is not set" | Missing `.env` | Copy `.env.example` to `.env` |
| "Resource Credits too low" | Low HP account | Delegate HP or reduce `max_daily_votes` |
| "Voting power too low" | Voting too aggressively | Increase `min_vp_percent` or reduce daily votes |
| "Daily vote limit reached" | Hit `max_daily_votes` | Wait 24h or increase the limit |
| Stream keeps reconnecting | Node issues | Bot auto-retries; check your internet |
| "already voted" errors | Duplicate detection | Normal -- the bot skips and moves on |

## License

MIT
