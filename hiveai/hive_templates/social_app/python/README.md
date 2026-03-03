# Hive Social App (Python / Flask + beem)

A complete, production-ready REST API for Hive blockchain social features. Every line of Hive-specific code includes tutorial comments so you can learn blockchain social mechanics as you build.

This is a **reference implementation** that ships with HiveAI. Use it to scaffold real Hive applications immediately.

## What This App Does

This Flask server exposes a REST API that interacts with the Hive blockchain to:

- **Read** trending/new posts by tag, fetch individual posts with comments, look up accounts, and retrieve notifications
- **Write** new blog posts, vote on content, leave comments, follow/unfollow users, and reblog posts

All write operations are signed locally with your posting key (your key never leaves the server) and broadcast to the Hive network. Transactions confirm in approximately 3 seconds.

## Prerequisites

- **Python** 3.9+ (3.11+ recommended)
- **A Hive account** (create one at [signup.hive.io](https://signup.hive.io/) or [ecency.com/signup](https://ecency.com/signup))
- **Your posting private key** (find it in [Hive Keychain](https://hive-keychain.com/) or [wallet.hive.blog](https://wallet.hive.blog/) under Permissions)

## Setup

```bash
# 1. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your environment
cp .env.example .env
# Edit .env with your Hive username and posting key

# 4. Start the server
python app.py
```

The server starts on `http://localhost:3000` (configurable via `PORT` in `.env`).

## API Documentation

### Read Endpoints (no key required)

These work even without a posting key configured, connecting to public Hive API nodes.

---

#### `GET /` -- Server status and API index

```bash
curl http://localhost:3000/
```

Returns app version, configured account, and a list of all endpoints.

---

#### `GET /api/health` -- Blockchain connection check

```bash
curl http://localhost:3000/api/health
```

Returns the current head block, witness, and time from the Hive blockchain. Useful for verifying your node connection is live and synced.

---

#### `GET /api/feed/<tag>` -- Get posts by tag

Fetches posts filtered by a tag, sorted by trending, new, or hot.

```bash
# Trending posts tagged "hive" (default sort)
curl http://localhost:3000/api/feed/hive

# Newest posts tagged "technology", limit 5
curl "http://localhost:3000/api/feed/technology?sort=created&limit=5"

# Hot posts tagged "photography"
curl "http://localhost:3000/api/feed/photography?sort=hot&limit=10"
```

Query parameters:

- `sort` (default: `trending`) -- Sort order: `trending`, `created`, `hot`
- `limit` (default: `10`) -- Number of posts (1-100)

---

#### `GET /api/post/<author>/<permlink>` -- Get a single post with comments

Returns the full post content, all votes, and the complete comment tree.

```bash
curl http://localhost:3000/api/post/hiveio/hive-hard-fork-26
```

---

#### `GET /api/account/<username>` -- Get account info

Returns reputation, Hive Power, balances, follower counts, Resource Credits, and profile metadata.

```bash
curl http://localhost:3000/api/account/blocktrades
```

---

#### `GET /api/notifications/<username>` -- Get notifications

Returns recent account activity: votes, replies, mentions, follows, reblogs, and transfers.

```bash
# All notifications (default limit 20)
curl http://localhost:3000/api/notifications/blocktrades

# Only vote notifications, limit 50
curl "http://localhost:3000/api/notifications/blocktrades?type=vote&limit=50"
```

Query parameters:

- `limit` (default: `20`) -- Number of notifications (1-100)
- `type` (optional) -- Filter: `vote`, `reply`, `mention`, `follow`, `reblog`, `transfer`, `unvote`

---

### Write Endpoints (posting key required)

These require `HIVE_USERNAME` and `HIVE_POSTING_KEY` in your `.env` file.

---

#### `POST /api/post` -- Create a new blog post

```bash
curl -X POST http://localhost:3000/api/post \
  -H "Content-Type: application/json" \
  -d '{
    "title": "My First Hive Post",
    "body": "Hello Hive! This is my first post.\n\n## Subtitle\n\nMarkdown is fully supported.",
    "tags": ["introduceyourself", "hive", "blog"]
  }'
```

Body parameters:

- `title` (required) -- Post title
- `body` (required) -- Post content in Markdown
- `tags` (required) -- Array of tags (first tag = category). Lowercase, letters/numbers/hyphens only.
- `beneficiaries` (optional) -- Array of `{account, weight}` to share rewards. Weight in basis points: 500 = 5%.
- `max_accepted_payout` (optional) -- String like `"100.000 HBD"`. Set `"0.000 HBD"` to decline rewards.
- `percent_hbd` (optional) -- 10000 = 50/50 HBD+HP (default), 0 = 100% HP

---

#### `POST /api/vote` -- Vote on a post or comment

```bash
# 100% upvote
curl -X POST http://localhost:3000/api/vote \
  -H "Content-Type: application/json" \
  -d '{"author": "hiveio", "permlink": "hive-hard-fork-26", "weight": 10000}'

# 50% upvote
curl -X POST http://localhost:3000/api/vote \
  -H "Content-Type: application/json" \
  -d '{"author": "hiveio", "permlink": "hive-hard-fork-26", "weight": 5000}'

# Remove vote
curl -X POST http://localhost:3000/api/vote \
  -H "Content-Type: application/json" \
  -d '{"author": "hiveio", "permlink": "hive-hard-fork-26", "weight": 0}'
```

Body parameters:

- `author` (required) -- Post/comment author
- `permlink` (required) -- Post/comment permlink
- `weight` (required) -- Vote weight: `-10000` (100% downvote) to `10000` (100% upvote). `0` = unvote.

---

#### `POST /api/comment` -- Comment on a post

```bash
curl -X POST http://localhost:3000/api/comment \
  -H "Content-Type: application/json" \
  -d '{
    "parent_author": "hiveio",
    "parent_permlink": "hive-hard-fork-26",
    "body": "Great update! Looking forward to the new features."
  }'
```

Body parameters:

- `parent_author` (required) -- Author of the post/comment being replied to
- `parent_permlink` (required) -- Permlink of the post/comment being replied to
- `body` (required) -- Comment content in Markdown

---

#### `POST /api/follow` -- Follow, unfollow, or mute a user

```bash
# Follow
curl -X POST http://localhost:3000/api/follow \
  -H "Content-Type: application/json" \
  -d '{"following": "blocktrades", "action": "follow"}'

# Unfollow
curl -X POST http://localhost:3000/api/follow \
  -H "Content-Type: application/json" \
  -d '{"following": "blocktrades", "action": "unfollow"}'

# Mute (hide their content from your view)
curl -X POST http://localhost:3000/api/follow \
  -H "Content-Type: application/json" \
  -d '{"following": "spammer", "action": "mute"}'
```

Body parameters:

- `following` (required) -- Username to follow/unfollow/mute
- `action` (required) -- One of: `follow`, `unfollow`, `mute`

---

#### `POST /api/reblog` -- Reblog (resteem) a post

```bash
curl -X POST http://localhost:3000/api/reblog \
  -H "Content-Type: application/json" \
  -d '{"author": "hiveio", "permlink": "hive-hard-fork-26"}'
```

Body parameters:

- `author` (required) -- Original post author
- `permlink` (required) -- Original post permlink

**Warning:** Reblogs cannot be undone on-chain.

---

## How Hive Social Features Work

### Posts Are On-Chain and (Eventually) Immutable

Every post and comment is a blockchain transaction. Once confirmed (in ~3 seconds), it exists permanently on Hive. Posts can be edited within 7 days, but after that, they become fully immutable. Even "deleted" posts just have their body replaced with empty text -- the original content is still visible in block explorers.

### The Reward System

When you upvote a post, you are allocating a portion of Hive's daily inflation pool to that post's author. The reward comes from the blockchain's monetary policy, NOT from the voter's wallet. After 7 days, rewards are distributed:

- **50%** to the author (as HIVE + HBD or 100% Hive Power, author's choice)
- **50%** to curators (voters), proportional to their vote weight and HP

### Key Hierarchy

Hive uses four key types, each with different permissions:

- **Posting** -- Social actions: post, comment, vote, follow, reblog. This is all this app needs.
- **Active** -- Financial: transfer tokens, power up/down, witness voting. NOT used here.
- **Owner** -- Account recovery, change all other keys. NEVER use in apps.
- **Memo** -- Encrypt/decrypt transfer memos. NOT needed here.

**Security rule:** Only use the minimum key level needed. This app only requires the posting key.

### Resource Credits (RC)

Hive has no gas fees. Instead, each account has a "Resource Credits" budget proportional to their staked HIVE (Hive Power). RC regenerates 20% per day (full in 5 days). If you run out, wait for regeneration or stake more HIVE.

Approximate RC costs per operation:

- Vote: ~1-2% of daily budget
- Comment/Post: ~5-10% of daily budget
- Follow/Reblog: ~1-2% of daily budget

## Differences from the JavaScript Version

| Feature | JavaScript (dhive) | Python (beem) |
|---------|-------------------|---------------|
| Client setup | `new dhive.Client(nodes)` | `Hive(node=nodes, keys=keys)` |
| Account lookup | `client.database.getAccounts([name])` | `Account(name)` |
| Feed queries | `client.call("bridge", ...)` | `Discussions_by_trending(query)` |
| Transaction building | `client.broadcast.sendOperations(ops, key)` | `TransactionBuilder` + `appendOps` + `sign` + `broadcast` |
| HP from VESTS | Manual calculation | `account.get_token_power()` |
| RC lookup | `client.call("rc_api", ...)` | `hive.rpc.find_rc_accounts(...)` |

beem provides more high-level abstractions (like `Account.get_token_power()`), while dhive is closer to the raw API. Both produce identical blockchain transactions.

## Common Pitfalls and Troubleshooting

### "Missing required posting authority"

Your `HIVE_POSTING_KEY` does not match `HIVE_USERNAME`. Double-check both values in `.env`. The posting key starts with `5` and is ~51 characters.

### "Not enough resource credits"

Your account ran out of free transactions. Wait a few hours for RC to regenerate (20% per day), or power up more HIVE to increase capacity.

### "HIVE_MIN_ROOT_COMMENT_INTERVAL" / rate limit errors

Hive enforces a 5-minute cooldown between top-level posts and a 3-second cooldown between comments. Wait and retry.

### Node connection timeouts

Public Hive nodes occasionally go down. The app is configured with failover nodes, but you can also change `HIVE_NODE` in `.env` to a different node from [beacon.peakd.com](https://beacon.peakd.com/).

### "Duplicate transaction"

You broadcast the exact same operation twice within the same block (~3 seconds). This is a safety feature preventing accidental double-posts.

### Posts not appearing on PeakD/Ecency immediately

After broadcasting, it takes 1-3 seconds for the transaction to be included in a block, then another 1-2 seconds for front-end indexers to process it. Wait 5-10 seconds before checking.

## Hive Concepts Covered in Source Code

Reading `app.py` will teach you about:

- Key hierarchy and permission system
- VESTS, Hive Power, and the staking model
- Resource Credits and transaction costs
- Post/comment operations and permlinks
- json_metadata conventions
- Voting mechanics, mana, and curation rewards
- Reputation calculation
- Beneficiary rewards
- custom_json for social operations (follow/mute/reblog)
- Node failover and API architecture
- 7-day payout windows and cashout mechanics
- Power down (13-week unstaking)
- TransactionBuilder for atomic multi-operation transactions
- Witness governance (DPoS block production)
- HBD stablecoin mechanics

## Testing

```bash
# Install test dependencies
pip install pytest

# Run the test suite
pytest test_app.py -v
```

Tests validate helper functions (permlink generation, reputation parsing) and Flask route logic without requiring a live Hive connection.

## Hive Testnet

For testing with real blockchain operations without risking your mainnet account, Hive has a testnet:

- Testnet node: `https://testnet.openhive.network`
- Testnet block explorer: `https://testnet.hiveblocks.com`
- Create testnet accounts at the testnet faucet

Set `HIVE_NODE=https://testnet.openhive.network` in your `.env` to use the testnet.

## License

MIT
