"""Hive API & Data — condenser vs bridge API, HiveSQL, RC calculation, reputation, global properties.

Covers the data layer of Hive: how to query the blockchain effectively,
understand reputation scores, monitor resource credits, and use analytics tools.
"""

PAIRS = [
    (
        "hive/development",
        r'''What are the differences between Hive's condenser_api and bridge API? When should I use each one, and what are the key endpoints?''',
        r'''## condenser_api vs bridge API on Hive

Hive exposes multiple API namespaces through its nodes. The two most important for dApp developers are `condenser_api` (the legacy Steem-compatible API) and `bridge` (the modern HAF-powered API). Understanding when to use each is critical for building efficient applications.

### condenser_api — The Legacy Workhorse

`condenser_api` is the original API from Steem, maintained for backward compatibility. It provides direct access to blockchain state and operations.

**Best for**: Raw blockchain data, broadcasting transactions, account lookups, block/transaction queries.

```javascript
const dhive = require('@hiveio/dhive');
const client = new dhive.Client(['https://api.hive.blog']);

// ---- Account Data ----
async function getAccount(username) {
  // condenser_api.get_accounts — returns full account objects
  const accounts = await client.database.call('get_accounts', [[username]]);
  if (accounts.length === 0) return null;

  const acc = accounts[0];
  return {
    name: acc.name,
    balance: acc.balance,                    // "123.456 HIVE"
    hbd_balance: acc.hbd_balance,            // "45.678 HBD"
    vesting_shares: acc.vesting_shares,      // "12345.678901 VESTS"
    voting_power: acc.voting_manabar,        // mana object
    reputation: acc.reputation,              // raw reputation number
    post_count: acc.post_count,
    created: acc.created,
    json_metadata: acc.json_metadata,        // profile data
    posting_json_metadata: acc.posting_json_metadata,
  };
}

// ---- Content by condenser_api ----
async function getPostCondenser(author, permlink) {
  // Returns raw content with vote data
  const content = await client.database.call('get_content', [author, permlink]);
  return {
    title: content.title,
    body: content.body,
    pending_payout_value: content.pending_payout_value,
    active_votes: content.active_votes,  // Full vote list with rshares
    created: content.created,
    json_metadata: content.json_metadata,
    net_rshares: content.net_rshares,
    children: content.children,  // reply count
  };
}

// ---- Blockchain State ----
async function getGlobalProps() {
  const props = await client.database.getDynamicGlobalProperties();
  return {
    head_block: props.head_block_number,
    current_supply: props.current_supply,           // Total HIVE
    current_hbd_supply: props.current_hbd_supply,   // Total HBD
    virtual_supply: props.virtual_supply,
    total_vesting_fund: props.total_vesting_fund_hive,
    total_vesting_shares: props.total_vesting_shares,
    hbd_interest_rate: props.hbd_interest_rate,      // basis points
    hbd_print_rate: props.hbd_print_rate,
    head_block_time: props.time,
  };
}

// ---- Block Data ----
async function getBlock(blockNum) {
  const block = await client.database.call('get_block', [blockNum]);
  return {
    witness: block.witness,
    timestamp: block.timestamp,
    transactions: block.transactions.length,
    transaction_ids: block.transaction_ids,
  };
}

// Key condenser_api endpoints:
// get_accounts, get_content, get_content_replies
// get_block, get_block_header, get_ops_in_block
// get_dynamic_global_properties, get_chain_properties
// get_discussions_by_trending, get_discussions_by_created, get_discussions_by_blog
// get_active_votes, get_account_history
// broadcast_transaction_synchronous
```

### bridge API — The Modern API

`bridge` is the newer API built on the Hive Application Framework (HAF). It provides pre-processed, frontend-friendly data with better filtering and pagination.

**Best for**: Content feeds, community data, notifications, profile rendering, any UI-facing queries.

```javascript
// bridge API calls use client.call('bridge', method, params)

// ---- Content Feeds ----
async function getTrendingPosts(tag = '', limit = 20) {
  // bridge.get_ranked_posts — returns enriched post objects
  const posts = await client.call('bridge', 'get_ranked_posts', {
    sort: 'trending',
    tag: tag,        // filter by tag or community
    limit: limit,    // max 100
    observer: '',    // account viewing (affects blacklists)
  });

  return posts.map(post => ({
    author: post.author,
    permlink: post.permlink,
    title: post.title,
    body: post.body.substring(0, 200),  // Full body included
    payout: post.payout,                // Pre-calculated total payout
    votes: post.stats.total_votes,      // Vote count
    author_reputation: post.author_reputation, // Pre-calculated reputation
    community: post.community,
    community_title: post.community_title,
    is_pinned: post.stats.is_pinned,
    created: post.created,
    // bridge includes processed images, profile pics, etc.
    author_profile: post.author_profile || {},
  }));
}

// Available sort options: trending, hot, created, promoted, payout, muted

// ---- Single Post with Replies ----
async function getPostWithReplies(author, permlink) {
  // bridge.get_discussion — returns post + all nested replies
  const discussion = await client.call('bridge', 'get_discussion', {
    author: author,
    permlink: permlink,
    observer: '',
  });

  // Returns a map of author/permlink -> post object
  // The root post key is `${author}/${permlink}`
  const rootKey = `${author}/${permlink}`;
  const root = discussion[rootKey];

  return {
    root: root,
    replies: Object.values(discussion).filter(p => p.author !== author || p.permlink !== permlink),
    total_replies: Object.keys(discussion).length - 1,
  };
}

// ---- Community Data ----
async function getCommunityInfo(communityName) {
  const community = await client.call('bridge', 'get_community', {
    name: communityName,  // e.g., 'hive-174301'
    observer: '',
  });

  return {
    name: community.name,
    title: community.title,
    about: community.about,
    subscribers: community.subscribers,
    num_pending: community.num_pending,
    num_authors: community.num_authors,
    team: community.team,  // mods, admins
    is_nsfw: community.is_nsfw,
  };
}

// ---- Account Posts (blog, feed, replies) ----
async function getAccountPosts(account, sort = 'posts', limit = 20) {
  const posts = await client.call('bridge', 'get_account_posts', {
    account: account,
    sort: sort,    // 'posts' | 'blog' | 'feed' | 'replies' | 'payout'
    limit: limit,
    observer: '',
  });
  return posts;
}

// ---- Notifications ----
async function getNotifications(account, limit = 50) {
  const notifications = await client.call('bridge', 'account_notifications', {
    account: account,
    limit: limit,
  });
  return notifications.map(n => ({
    type: n.type,   // 'vote', 'reply', 'mention', 'follow', 'reblog', 'transfer'
    msg: n.msg,
    date: n.date,
    url: n.url,
    score: n.score,
  }));
}
```

### When to Use Which

| Use Case | API | Reason |
|----------|-----|--------|
| Display trending feed | bridge | Pre-processed, includes reputation, profiles |
| Get account balance | condenser_api | Raw data, simple query |
| Build a block explorer | condenser_api | Need raw block/transaction data |
| Show post with comments | bridge.get_discussion | Returns full threaded tree |
| Community pages | bridge | Community-aware filtering |
| Broadcasting transactions | condenser_api | broadcast_transaction_synchronous |
| Account history | condenser_api | get_account_history with filters |
| Notifications | bridge | account_notifications |
| Vote details with rshares | condenser_api | get_active_votes returns full vote data |
| Content feeds for UI | bridge | Enriched data, pagination support |

### Important Notes

1. **Node compatibility**: Not all nodes support all APIs. `api.hive.blog` supports both. Some lightweight nodes only have condenser_api.
2. **bridge requires HAF**: The bridge API runs on HAF (Hive Application Framework) nodes. If a node returns errors for bridge calls, it may not have HAF enabled.
3. **Rate limits**: Public nodes may rate-limit heavy queries. For production apps, run your own node or use a paid API service.
4. **Pagination**: bridge uses `start_author`/`start_permlink` for cursor-based pagination. condenser_api uses `start_entry_id` for history pagination.
5. **observer parameter**: In bridge calls, setting `observer` to a username applies that user's mute list and shows personalized data.
'''
    ),
    (
        "hive/development",
        r'''How do I query HiveSQL for analytics? I need to understand the database schema, write useful queries for account analysis, content metrics, and token economics.''',
        r'''## HiveSQL Analytics — Schema, Queries, and Patterns

HiveSQL is a public Microsoft SQL Server database that mirrors the Hive blockchain state. It is maintained by @arcange and provides SQL access to all blockchain data — accounts, posts, votes, transactions, and more.

### Connecting to HiveSQL

- **Server**: `vip.hivesql.io`
- **Port**: 1433
- **Database**: `DBHive`
- **Authentication**: Requires a HiveSQL subscription (paid via @hivesql on Hive)

```python
import pyodbc
import pandas as pd

# Connection string for HiveSQL
conn_str = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=vip.hivesql.io;"
    "DATABASE=DBHive;"
    "UID=your_hivesql_username;"
    "PWD=your_hivesql_password;"
    "TrustServerCertificate=yes;"
)

conn = pyodbc.connect(conn_str)

def query(sql, params=None):
    """Execute a query and return a DataFrame."""
    return pd.read_sql(sql, conn, params=params)
```

### Key Tables and Schema

```
Accounts        — All Hive accounts (name, balance, vesting, reputation, etc.)
Comments        — All posts and replies (author, permlink, body, metadata, rewards)
Votes           — All votes (voter, author, permlink, weight, rshares, timestamp)
Transfers       — HIVE/HBD transfer history
VOHiveOperations — Virtual operations (rewards, fills, etc.)
DynamicGlobalProperties — Current chain state
Witnesses       — Witness data and feed prices
CommunitySubscribers — Community membership
Delegations     — Active HP delegations
```

### Account Analysis Queries

```sql
-- 1. Account overview with calculated HP
SELECT
    a.name,
    a.balance AS hive_balance,
    a.hbd_balance,
    a.vesting_shares,
    a.reputation,
    a.post_count,
    a.created,
    a.last_post,
    a.last_vote_time,
    -- Calculate HP from VESTS
    CAST(a.vesting_shares AS FLOAT) *
        (SELECT CAST(total_vesting_fund_hive AS FLOAT) / CAST(total_vesting_shares AS FLOAT)
         FROM DynamicGlobalProperties) AS hive_power_hp,
    -- Net HP (own - delegated + received)
    (CAST(a.vesting_shares AS FLOAT) - CAST(a.delegated_vesting_shares AS FLOAT)
     + CAST(a.received_vesting_shares AS FLOAT)) *
        (SELECT CAST(total_vesting_fund_hive AS FLOAT) / CAST(total_vesting_shares AS FLOAT)
         FROM DynamicGlobalProperties) AS effective_hp
FROM Accounts a
WHERE a.name = 'blocktrades';

-- 2. Top accounts by effective HP (whale list)
SELECT TOP 50
    name,
    CAST(vesting_shares AS FLOAT) *
        (SELECT CAST(total_vesting_fund_hive AS FLOAT) / CAST(total_vesting_shares AS FLOAT)
         FROM DynamicGlobalProperties) AS hp
FROM Accounts
WHERE vesting_shares > 0
ORDER BY CAST(vesting_shares AS FLOAT) DESC;

-- 3. New account creation trend (last 30 days)
SELECT
    CAST(created AS DATE) AS day,
    COUNT(*) AS new_accounts
FROM Accounts
WHERE created >= DATEADD(DAY, -30, GETUTCDATE())
GROUP BY CAST(created AS DATE)
ORDER BY day DESC;
```

### Content Analytics Queries

```sql
-- 4. Top earning posts this week
SELECT TOP 20
    author,
    permlink,
    title,
    pending_payout_value,
    total_payout_value,
    net_votes,
    children AS reply_count,
    created
FROM Comments
WHERE depth = 0  -- top-level posts only
  AND created >= DATEADD(DAY, -7, GETUTCDATE())
  AND pending_payout_value > 0
ORDER BY pending_payout_value DESC;

-- 5. Author posting frequency and average rewards (30 days)
SELECT
    author,
    COUNT(*) AS post_count,
    AVG(CAST(total_payout_value AS FLOAT) + CAST(curator_payout_value AS FLOAT)) AS avg_total_payout,
    SUM(CAST(total_payout_value AS FLOAT)) AS total_author_payout,
    AVG(net_votes) AS avg_votes,
    AVG(children) AS avg_comments
FROM Comments
WHERE depth = 0
  AND created >= DATEADD(DAY, -30, GETUTCDATE())
  AND author = 'theycallmedan'
GROUP BY author;

-- 6. Most active communities by post count
SELECT TOP 20
    category AS community,
    COUNT(*) AS posts,
    COUNT(DISTINCT author) AS unique_authors,
    AVG(net_votes) AS avg_votes,
    AVG(CAST(pending_payout_value AS FLOAT) + CAST(total_payout_value AS FLOAT)) AS avg_payout
FROM Comments
WHERE depth = 0
  AND created >= DATEADD(DAY, -7, GETUTCDATE())
  AND category LIKE 'hive-%'
GROUP BY category
ORDER BY posts DESC;

-- 7. Engagement ratio: votes and comments per post by tag
SELECT
    j.value AS tag,
    COUNT(DISTINCT c.ID) AS posts,
    AVG(c.net_votes) AS avg_votes,
    AVG(c.children) AS avg_replies,
    AVG(CAST(c.pending_payout_value AS FLOAT)) AS avg_pending_payout
FROM Comments c
CROSS APPLY OPENJSON(c.json_metadata, '$.tags') j
WHERE c.depth = 0
  AND c.created >= DATEADD(DAY, -7, GETUTCDATE())
GROUP BY j.value
HAVING COUNT(DISTINCT c.ID) >= 10
ORDER BY avg_votes DESC;
```

### Token Economics Queries

```sql
-- 8. Daily transfer volume (HIVE and HBD)
SELECT
    CAST(timestamp AS DATE) AS day,
    SUM(CASE WHEN amount LIKE '%HIVE' THEN CAST(REPLACE(amount, ' HIVE', '') AS FLOAT) ELSE 0 END) AS hive_volume,
    SUM(CASE WHEN amount LIKE '%HBD' THEN CAST(REPLACE(amount, ' HBD', '') AS FLOAT) ELSE 0 END) AS hbd_volume,
    COUNT(*) AS transfer_count
FROM Transfers
WHERE timestamp >= DATEADD(DAY, -30, GETUTCDATE())
  AND [type] = 'transfer'
GROUP BY CAST(timestamp AS DATE)
ORDER BY day DESC;

-- 9. Power-up vs power-down trend
SELECT
    CAST(timestamp AS DATE) AS day,
    SUM(CASE WHEN [type] = 'transfer_to_vesting' THEN CAST(REPLACE(amount, ' HIVE', '') AS FLOAT) ELSE 0 END) AS powered_up_hive,
    SUM(CASE WHEN [type] = 'fill_vesting_withdraw' THEN CAST(REPLACE(deposited, ' HIVE', '') AS FLOAT) ELSE 0 END) AS powered_down_hive
FROM VOHiveOperations
WHERE timestamp >= DATEADD(DAY, -30, GETUTCDATE())
  AND [type] IN ('transfer_to_vesting', 'fill_vesting_withdraw')
GROUP BY CAST(timestamp AS DATE)
ORDER BY day DESC;

-- 10. HBD savings interest accrual
SELECT
    CAST(timestamp AS DATE) AS day,
    COUNT(*) AS interest_payments,
    SUM(CAST(REPLACE(interest, ' HBD', '') AS FLOAT)) AS total_interest_hbd
FROM VOHiveOperations
WHERE [type] = 'interest'
  AND timestamp >= DATEADD(DAY, -30, GETUTCDATE())
GROUP BY CAST(timestamp AS DATE)
ORDER BY day DESC;
```

### Production Analytics Class

```python
class HiveSQLAnalytics:
    def __init__(self, connection_string):
        self.conn = pyodbc.connect(connection_string)

    def account_report(self, username):
        sql = """
        SELECT name, balance, hbd_balance, vesting_shares,
               delegated_vesting_shares, received_vesting_shares,
               reputation, post_count, created, last_post
        FROM Accounts WHERE name = ?
        """
        return query(sql, params=[username])

    def author_earnings(self, username, days=30):
        sql = """
        SELECT
            COUNT(*) as posts,
            SUM(CAST(total_payout_value AS FLOAT)) as total_author_hbd,
            SUM(CAST(curator_payout_value AS FLOAT)) as total_curator_hbd,
            AVG(net_votes) as avg_votes
        FROM Comments
        WHERE author = ? AND depth = 0
          AND created >= DATEADD(DAY, ?, GETUTCDATE())
        """
        return query(sql, params=[username, -days])

    def whale_votes_on(self, username, min_rshares=1000000000):
        sql = """
        SELECT TOP 50 v.voter, v.weight, v.rshares, v.timestamp,
               c.title, c.permlink
        FROM Votes v
        JOIN Comments c ON v.author = c.author AND v.permlink = c.permlink
        WHERE v.author = ? AND v.rshares >= ?
          AND v.timestamp >= DATEADD(DAY, -30, GETUTCDATE())
        ORDER BY v.rshares DESC
        """
        return query(sql, params=[username, min_rshares])

    def close(self):
        self.conn.close()


# Usage
analytics = HiveSQLAnalytics(conn_str)
print(analytics.account_report("blocktrades"))
print(analytics.author_earnings("theycallmedan", days=30))
analytics.close()
```

### Key Notes

1. **HiveSQL is read-only**: You cannot write to the blockchain through HiveSQL. Use dhive or beem for broadcasting.
2. **Subscription required**: HiveSQL is a paid service (~$2/month in HIVE). Subscribe by sending HIVE to @hivesql with your desired username as memo.
3. **VESTS to HP conversion**: Always use the ratio from `DynamicGlobalProperties`: `HP = VESTS * total_vesting_fund_hive / total_vesting_shares`.
4. **Performance**: Complex queries on Comments or Votes tables can be slow — these tables have billions of rows. Always filter by date range and use TOP/LIMIT.
5. **Alternative**: If you cannot use HiveSQL, the HAF (Hive Application Framework) lets you run your own PostgreSQL-backed analytics database synchronized with the blockchain.
'''
    ),
    (
        "hive/development",
        r'''How do Resource Credits (RC) work on Hive? How do I calculate RC costs, monitor an account's RC, and optimize RC usage for high-volume applications?''',
        r'''## Resource Credits (RC) on Hive — Calculation, Monitoring, and Optimization

Resource Credits are Hive's rate-limiting mechanism that replaced the old bandwidth system in HF20. Every blockchain operation costs RC, which regenerates over time proportional to your Hive Power (HP). Understanding RC is critical for building applications that serve many users.

### Core Concepts

- **RC is derived from HP**: More HP = more max RC. The relationship is approximately 1 HP = ~1B RC (varies with chain state).
- **RC regenerates linearly**: Full regeneration takes 5 days (432,000 seconds), same as voting mana.
- **Each operation type has a different RC cost**: Votes are cheap, posts are moderate, account creation is expensive.
- **RC delegation** (HF26+): You can delegate RC without delegating HP — perfect for onboarding.
- **RC cost = resource consumption * resource price**: Prices are dynamic and adjust based on network load.

### Monitoring RC with dhive.js

```javascript
const dhive = require('@hiveio/dhive');
const client = new dhive.Client(['https://api.hive.blog', 'https://api.deathwing.me']);

async function getAccountRC(username) {
  // rc_api.find_rc_accounts gives current RC state
  const result = await client.call('rc_api', 'find_rc_accounts', {
    accounts: [username],
  });

  if (!result.rc_accounts || result.rc_accounts.length === 0) {
    throw new Error(`Account ${username} not found`);
  }

  const rc = result.rc_accounts[0];
  const maxRC = Number(rc.max_rc);
  const currentMana = Number(rc.rc_manabar.current_mana);
  const lastUpdate = Number(rc.rc_manabar.last_update_time);

  // Calculate regenerated mana since last update
  const now = Math.floor(Date.now() / 1000);
  const elapsed = now - lastUpdate;
  const regenerated = Math.floor((elapsed * maxRC) / 432000); // 5 days = 432000s

  const effectiveMana = Math.min(currentMana + regenerated, maxRC);
  const rcPercent = maxRC > 0 ? (effectiveMana / maxRC) * 100 : 0;

  return {
    account: username,
    maxRC: maxRC,
    currentRC: effectiveMana,
    rcPercent: Math.round(rcPercent * 100) / 100,
    regenPerDay: Math.floor(maxRC * 0.2), // 20% per day
    regenPerHour: Math.floor(maxRC * 0.2 / 24),
  };
}

// Usage
const rc = await getAccountRC('blocktrades');
console.log(`@${rc.account}: ${rc.rcPercent}% RC (${rc.currentRC.toLocaleString()} / ${rc.maxRC.toLocaleString()})`);
console.log(`Regen: ${rc.regenPerHour.toLocaleString()} RC/hour`);
```

### Estimating RC Cost per Operation

```javascript
async function estimateRCCost(operationType, operationData) {
  // rc_api.get_resource_params gives the current resource prices
  const params = await client.call('rc_api', 'get_resource_params', {});
  const poolInfo = await client.call('rc_api', 'get_resource_pool', {});

  // For a simpler approach, use empirical estimates:
  const APPROX_RC_COSTS = {
    vote: 0.5e9,              // ~0.5 billion RC
    comment: 1.5e9,           // ~1.5 billion RC (post or reply)
    comment_long: 5e9,        // ~5 billion RC (long post with images)
    transfer: 0.5e9,          // ~0.5 billion RC
    custom_json: 0.5e9,       // ~0.5 billion RC
    claim_account: 6000e9,    // ~6 trillion RC (very expensive!)
    delegate_vesting: 0.5e9,  // ~0.5 billion RC
  };

  return APPROX_RC_COSTS[operationType] || 1e9;
}

async function canPerformOperation(username, operationType) {
  const rc = await getAccountRC(username);
  const cost = await estimateRCCost(operationType);

  const canDo = rc.currentRC >= cost;
  const howMany = Math.floor(rc.currentRC / cost);

  return {
    canPerform: canDo,
    currentRC: rc.currentRC,
    estimatedCost: cost,
    remainingAfter: canDo ? rc.currentRC - cost : 0,
    totalPossible: howMany,
    rcPercent: rc.rcPercent,
  };
}

// Example: Can this account vote?
const check = await canPerformOperation('newuser123', 'vote');
console.log(`Can vote: ${check.canPerform} (${check.totalPossible} votes possible)`);
```

### Production RC Manager for High-Volume Apps

```python
from beem import Hive
from beem.account import Account
from beem.rc import RC
import time
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("rc_manager")


class RCManager:
    """Monitor and manage Resource Credits for high-volume Hive applications."""

    def __init__(self, config):
        self.hive = Hive(
            node=config.get("nodes", ["https://api.hive.blog"]),
            keys=config.get("keys", []),
        )
        self.accounts = config.get("accounts", [])
        self.alert_threshold = config.get("alert_threshold_pct", 20)
        self.rc_cache = {}
        self.cache_ttl = 30  # seconds
        self.op_costs = defaultdict(list)  # Track actual costs

    def get_rc_status(self, account_name, force_refresh=False):
        """Get current RC status for an account."""
        cache_key = account_name
        now = time.time()

        if not force_refresh and cache_key in self.rc_cache:
            cached = self.rc_cache[cache_key]
            if now - cached["fetched_at"] < self.cache_ttl:
                return cached

        acc = Account(account_name, blockchain_instance=self.hive)
        rc_manabar = acc.get_rc_manabar()

        max_rc = int(rc_manabar["max_mana"])
        current_rc = int(rc_manabar["current_mana"])
        rc_pct = (current_rc / max_rc * 100) if max_rc > 0 else 0

        status = {
            "account": account_name,
            "current_rc": current_rc,
            "max_rc": max_rc,
            "rc_pct": round(rc_pct, 2),
            "regen_per_hour": max_rc * 0.2 / 24,
            "fetched_at": now,
        }

        self.rc_cache[cache_key] = status
        return status

    def estimate_operations_possible(self, account_name):
        """Estimate how many of each operation type the account can perform."""
        rc = self.get_rc_status(account_name)
        current = rc["current_rc"]

        # Empirical RC costs (approximate, varies with chain load)
        estimates = {
            "vote": int(0.5e9),
            "comment_short": int(1e9),
            "comment_long": int(5e9),
            "transfer": int(0.5e9),
            "custom_json": int(0.5e9),
            "claim_account": int(6000e9),
            "delegate_rc": int(0.5e9),
        }

        result = {}
        for op_type, cost in estimates.items():
            result[op_type] = {
                "cost_rc": cost,
                "possible": max(0, current // cost),
            }

        return result

    def check_all_accounts(self):
        """Check RC for all monitored accounts and return alerts."""
        alerts = []
        statuses = []

        for account in self.accounts:
            status = self.get_rc_status(account, force_refresh=True)
            statuses.append(status)

            if status["rc_pct"] < self.alert_threshold:
                alerts.append({
                    "account": account,
                    "rc_pct": status["rc_pct"],
                    "current_rc": status["current_rc"],
                    "severity": "critical" if status["rc_pct"] < 5 else "warning",
                    "hours_to_threshold": (
                        (self.alert_threshold - status["rc_pct"]) / 100
                        * status["max_rc"] / status["regen_per_hour"]
                    ),
                })

        return {"statuses": statuses, "alerts": alerts}

    def optimal_rc_delegation(self, target_account, ops_per_day):
        """Calculate optimal RC delegation for a given activity level."""
        # ops_per_day: dict like {"vote": 10, "comment_short": 2, "custom_json": 50}

        costs = {
            "vote": int(0.5e9),
            "comment_short": int(1e9),
            "comment_long": int(5e9),
            "transfer": int(0.5e9),
            "custom_json": int(0.5e9),
        }

        daily_rc_needed = sum(
            costs.get(op_type, 1e9) * count
            for op_type, count in ops_per_day.items()
        )

        # Account needs enough max_rc to regenerate daily_rc_needed per day
        # Regen is 20% of max per day, so max_rc = daily_need / 0.2
        required_max_rc = int(daily_rc_needed / 0.2)

        # Check what target already has
        target_status = self.get_rc_status(target_account)
        existing_max = target_status["max_rc"]
        needed_delegation = max(0, required_max_rc - existing_max)

        # Convert RC to approximate HP (rough: 1 HP ≈ 1e9 RC)
        approx_hp_needed = needed_delegation / 1e9

        return {
            "target_account": target_account,
            "daily_rc_needed": daily_rc_needed,
            "required_max_rc": required_max_rc,
            "existing_max_rc": existing_max,
            "rc_delegation_needed": needed_delegation,
            "approx_hp_equivalent": round(approx_hp_needed, 1),
            "ops_per_day": ops_per_day,
        }

    def monitor_loop(self, interval_seconds=300):
        """Continuous monitoring loop."""
        logger.info(f"RC Monitor started for {len(self.accounts)} accounts")
        while True:
            result = self.check_all_accounts()

            for status in result["statuses"]:
                ops = self.estimate_operations_possible(status["account"])
                votes_left = ops["vote"]["possible"]
                logger.info(
                    f"@{status['account']}: {status['rc_pct']:.1f}% RC "
                    f"({votes_left} votes possible)"
                )

            for alert in result["alerts"]:
                logger.warning(
                    f"LOW RC [{alert['severity'].upper()}]: @{alert['account']} "
                    f"at {alert['rc_pct']:.1f}% — "
                    f"will reach {self.alert_threshold}% in {alert['hours_to_threshold']:.1f}h"
                )

            time.sleep(interval_seconds)


# Usage
manager = RCManager({
    "nodes": ["https://api.hive.blog", "https://api.deathwing.me"],
    "accounts": ["myapp", "myapp-posting", "myapp-onboarding"],
    "alert_threshold_pct": 20,
})

# One-time check
result = manager.check_all_accounts()
for s in result["statuses"]:
    print(f"@{s['account']}: {s['rc_pct']}% RC")

# Calculate delegation needs for a game account
delegation = manager.optimal_rc_delegation("gamebot", {
    "custom_json": 1000,  # 1000 game actions/day
    "transfer": 50,       # 50 reward payouts/day
    "comment_short": 10,  # 10 automated posts/day
})
print(f"RC delegation needed: {delegation['rc_delegation_needed']:,.0f}")
print(f"Approximate HP needed: {delegation['approx_hp_equivalent']} HP")

# Continuous monitoring
# manager.monitor_loop(interval_seconds=300)
```

### Key Notes

1. **RC regeneration**: 20% of max RC per day (full recharge in 5 days). Plan your daily operations to stay within the regen budget.
2. **RC costs are dynamic**: The chain adjusts RC prices based on network congestion. During heavy usage, costs increase. The empirical estimates above are approximate.
3. **RC delegation (HF26)**: Use `custom_json` with id `"rc"` and action `"delegate_rc"`. This gives users transacting ability without giving them voting/staking power.
4. **Account creation tokens**: Claiming an account token is by far the most expensive RC operation (~6 trillion RC). Only large stakeholders can do this.
5. **Optimization strategies**: Batch multiple operations into single transactions, use shorter memos, minimize post body size, and schedule non-urgent operations during off-peak hours.
'''
    ),
    (
        "hive/development",
        r'''How is reputation calculated on Hive? How do I convert the raw reputation number to the displayed score, and what do different reputation levels mean?''',
        r'''## Hive Reputation System — Calculation, Conversion, and Meaning

Reputation on Hive is a logarithmic score derived from the net rshares (reward shares) an account has received from upvotes and downvotes. It is an anti-spam signal, not a direct measure of content quality.

### Core Concepts

- **Raw reputation**: A large integer stored on-chain (can be negative for heavily downvoted accounts). New accounts start at 0 raw, which displays as 25.
- **Display reputation**: The log-scaled number users see (typically 25-80). Calculated client-side from the raw value.
- **Only higher-rep accounts affect reputation**: A downvote from a lower-rep account does NOT reduce the target's reputation. This prevents sybil attacks.
- **Reputation only increases from upvotes with positive rshares**: Self-votes and dust votes may not meaningfully affect reputation.

### Reputation Conversion Formula

The formula to convert raw reputation to display reputation:

```
display_rep = MAX(log10(raw_rep) - 9, 0) * 9 + 25
```

For negative raw reputation:
```
display_rep = -1 * (MAX(log10(abs(raw_rep)) - 9, 0) * 9 + 25)
```

### JavaScript Implementation

```javascript
function rawToDisplayReputation(rawRep) {
  // Handle string input (API returns strings for large numbers)
  const rep = typeof rawRep === 'string' ? BigInt(rawRep) : BigInt(rawRep);

  // Handle zero and near-zero
  if (rep === 0n) return 25;

  const isNegative = rep < 0n;
  const absRep = isNegative ? -rep : rep;

  // Convert to log10
  // For BigInt, we use string length as approximation + parseFloat for precision
  const absRepStr = absRep.toString();
  const log10 = Math.log10(parseFloat(absRepStr));

  // Apply formula
  let score = Math.max(log10 - 9, 0) * 9 + 25;

  if (isNegative) {
    score = -score;
  }

  return Math.floor(score);
}

// Examples:
console.log(rawToDisplayReputation(0));                    // 25 (new account)
console.log(rawToDisplayReputation('1000000000'));          // 25 (min display)
console.log(rawToDisplayReputation('95832978796820'));      // 68
console.log(rawToDisplayReputation('533973817843259'));     // 73
console.log(rawToDisplayReputation('170451007610498373'));  // 80
console.log(rawToDisplayReputation('-1000000000000'));      // -34 (flagged account)


// Full utility class
class HiveReputation {
  static toDisplay(rawRep) {
    return rawToDisplayReputation(rawRep);
  }

  static getLevel(displayRep) {
    if (displayRep < 1) return { level: 'flagged', description: 'Account has been heavily downvoted' };
    if (displayRep < 25) return { level: 'negative', description: 'More downvotes than upvotes' };
    if (displayRep === 25) return { level: 'newbie', description: 'New or inactive account' };
    if (displayRep < 35) return { level: 'newcomer', description: 'Getting started on Hive' };
    if (displayRep < 45) return { level: 'regular', description: 'Somewhat active user' };
    if (displayRep < 55) return { level: 'established', description: 'Active community member' };
    if (displayRep < 65) return { level: 'veteran', description: 'Well-established account' };
    if (displayRep < 75) return { level: 'authority', description: 'Highly regarded account' };
    if (displayRep < 80) return { level: 'elite', description: 'Top-tier Hive account' };
    return { level: 'legendary', description: 'Among the highest reputation on Hive' };
  }

  static estimateVotesToNextRep(currentRaw, targetDisplay) {
    // Estimate how much rshares needed to reach target display rep
    // display = (log10(raw) - 9) * 9 + 25
    // raw = 10^((display - 25) / 9 + 9)
    const targetRaw = Math.pow(10, (targetDisplay - 25) / 9 + 9);
    const currentRawNum = parseFloat(currentRaw.toString());
    const rsharesNeeded = targetRaw - currentRawNum;
    return {
      targetDisplay,
      rsharesNeeded: Math.max(0, rsharesNeeded),
      // Very rough estimate: a $1 vote ≈ 1e12 rshares
      estimatedDollarVotes: Math.max(0, rsharesNeeded / 1e12),
    };
  }
}

// Usage
const raw = '95832978796820';
const display = HiveReputation.toDisplay(raw);
const level = HiveReputation.getLevel(display);
console.log(`Rep ${display} — ${level.level}: ${level.description}`);

const estimate = HiveReputation.estimateVotesToNextRep(raw, display + 1);
console.log(`Need ~$${estimate.estimatedDollarVotes.toFixed(0)} in votes to reach ${estimate.targetDisplay}`);
```

### Python Implementation with beem

```python
import math
from beem import Hive
from beem.account import Account


def raw_to_display_reputation(raw_rep):
    """Convert raw blockchain reputation to display score."""
    raw_rep = int(raw_rep)

    if raw_rep == 0:
        return 25

    is_negative = raw_rep < 0
    abs_rep = abs(raw_rep)

    log_rep = math.log10(abs_rep)
    score = max(log_rep - 9, 0) * 9 + 25

    if is_negative:
        score = -score

    return int(score)


def get_reputation_info(account_name):
    """Get comprehensive reputation data for an account."""
    hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])
    acc = Account(account_name, blockchain_instance=hive)

    raw_rep = int(acc["reputation"])
    display_rep = raw_to_display_reputation(raw_rep)

    # beem also provides this directly:
    beem_rep = acc.get_reputation()

    return {
        "account": account_name,
        "raw_reputation": raw_rep,
        "display_reputation": display_rep,
        "beem_reputation": round(beem_rep, 2),
        "created": acc["created"],
        "post_count": acc["post_count"],
    }


def reputation_leaderboard(limit=20):
    """Get top accounts by reputation."""
    hive = Hive(node=["https://api.hive.blog"])

    # Use condenser_api to get accounts sorted by reputation
    accounts = hive.rpc.get_accounts_by_reputation(
        lower_bound_name="",
        limit=limit,
    )

    leaderboard = []
    for acc in accounts:
        raw = int(acc["reputation"])
        display = raw_to_display_reputation(raw)
        leaderboard.append({
            "name": acc["name"],
            "reputation": display,
            "raw": raw,
        })

    return leaderboard


# Quick lookup
info = get_reputation_info("blocktrades")
print(f"@{info['account']}: Reputation {info['display_reputation']} (raw: {info['raw_reputation']})")

# Leaderboard
for entry in reputation_leaderboard(10):
    print(f"  @{entry['name']}: {entry['reputation']}")
```

### Understanding Reputation Levels

| Display Rep | Level | What It Means |
|-------------|-------|---------------|
| < 0 | Flagged | Heavily downvoted, likely spam/abuse |
| 0-24 | Negative | More downvotes than upvotes received |
| 25 | New | Default for all new accounts |
| 26-34 | Newcomer | Has received some upvotes |
| 35-44 | Regular | Moderately active user |
| 45-54 | Established | Well-known community member |
| 55-64 | Veteran | Long-time active participant |
| 65-74 | Authority | Major contributor, significant stake interactions |
| 75-79 | Elite | Among the top users on the platform |
| 80+ | Legendary | Extremely rare, years of high-value engagement |

### Key Notes

1. **Logarithmic scale**: Each reputation point is exponentially harder to earn than the last. Going from 60 to 61 requires roughly 10x more rshares than going from 50 to 51.
2. **One-way protection**: Higher-rep accounts can damage lower-rep accounts' reputation via downvotes, but lower-rep accounts cannot damage higher-rep ones. This creates an asymmetric defense against spam.
3. **Not a quality metric**: Reputation reflects cumulative upvote history, not content quality. A highly-reputed account can still post low-quality content, and a low-rep account might produce excellent work.
4. **Starting at 25**: All accounts begin at reputation 25 (raw = 0). The first meaningful upvote moves the raw value into positive territory.
5. **Reputation cannot be "reset"**: It is a permanent, on-chain metric. The only way to change it is through votes from accounts with sufficient reputation and stake.
6. **Frontend-dependent**: The blockchain stores only the raw number. The conversion to display format is done by frontends, which is why different UIs may show slightly different numbers (due to rounding).
'''
    ),
    (
        "hive/development",
        r'''How do I retrieve and use Hive's dynamic global properties and chain state? What key metrics are available and how do I calculate VESTS-to-HP conversion?''',
        r'''## Hive Dynamic Global Properties and Chain State

The Dynamic Global Properties (DGP) object is the single most important data source on Hive. It contains the current state of the blockchain including supply figures, block info, VESTS/HP conversion ratio, and reward pool data. Every Hive application needs to query this.

### What DGP Contains

The DGP is available via `condenser_api.get_dynamic_global_properties` and returns a snapshot of the chain's current state, updated every block (3 seconds).

### Fetching and Using DGP with dhive.js

```javascript
const dhive = require('@hiveio/dhive');
const client = new dhive.Client(['https://api.hive.blog', 'https://api.deathwing.me']);

async function getChainState() {
  const dgp = await client.database.getDynamicGlobalProperties();

  // Key fields explained:
  return {
    // ---- Block Info ----
    head_block_number: dgp.head_block_number,
    head_block_id: dgp.head_block_id,
    time: dgp.time,  // Current block timestamp (UTC)
    current_witness: dgp.current_witness,
    last_irreversible_block_num: dgp.last_irreversible_block_num,

    // ---- Supply ----
    current_supply: dgp.current_supply,          // Total HIVE in existence
    current_hbd_supply: dgp.current_hbd_supply,  // Total HBD in existence
    virtual_supply: dgp.virtual_supply,           // HIVE + HBD converted to HIVE equivalent

    // ---- Vesting (HP) ----
    total_vesting_fund_hive: dgp.total_vesting_fund_hive,  // Total HIVE backing all VESTS
    total_vesting_shares: dgp.total_vesting_shares,        // Total VESTS in existence

    // ---- Reward Pool ----
    pending_rewarded_vesting_shares: dgp.pending_rewarded_vesting_shares,
    pending_rewarded_vesting_hive: dgp.pending_rewarded_vesting_hive,
    reward_fund: null,  // Fetched separately via get_reward_fund

    // ---- HBD Settings ----
    hbd_interest_rate: dgp.hbd_interest_rate,    // Witness-set interest rate (basis points)
    hbd_print_rate: dgp.hbd_print_rate,          // 10000 = printing HBD normally
    hbd_stop_percent: dgp.hbd_stop_percent,      // HBD % of market cap trigger
    hbd_start_percent: dgp.hbd_start_percent,    // Resume printing threshold

    // ---- Chain Config ----
    maximum_block_size: dgp.maximum_block_size,
    required_actions_partition_percent: dgp.required_actions_partition_percent,
  };
}

// ---- VESTS to HP Conversion ----
function vestsToHP(vests, dgp) {
  const totalVestingFund = parseFloat(dgp.total_vesting_fund_hive);
  const totalVestingShares = parseFloat(dgp.total_vesting_shares);
  return (parseFloat(vests) * totalVestingFund) / totalVestingShares;
}

function hpToVests(hp, dgp) {
  const totalVestingFund = parseFloat(dgp.total_vesting_fund_hive);
  const totalVestingShares = parseFloat(dgp.total_vesting_shares);
  return (parseFloat(hp) * totalVestingShares) / totalVestingFund;
}

// Usage
async function showAccountHP(username) {
  const dgp = await client.database.getDynamicGlobalProperties();
  const [account] = await client.database.getAccounts([username]);

  const ownVests = parseFloat(account.vesting_shares);
  const delegatedOut = parseFloat(account.delegated_vesting_shares);
  const receivedIn = parseFloat(account.received_vesting_shares);

  const ownHP = vestsToHP(ownVests, dgp);
  const effectiveHP = vestsToHP(ownVests - delegatedOut + receivedIn, dgp);
  const delegatedOutHP = vestsToHP(delegatedOut, dgp);
  const receivedHP = vestsToHP(receivedIn, dgp);

  console.log(`@${username} Hive Power Breakdown:`);
  console.log(`  Own HP:          ${ownHP.toFixed(3)} HP`);
  console.log(`  Delegated Out:  -${delegatedOutHP.toFixed(3)} HP`);
  console.log(`  Received In:    +${receivedHP.toFixed(3)} HP`);
  console.log(`  Effective HP:    ${effectiveHP.toFixed(3)} HP`);

  return { ownHP, effectiveHP, delegatedOutHP, receivedHP };
}
```

### Production Chain State Monitor

```python
from beem import Hive
from beem.blockchain import Blockchain
from beem.account import Account
from beem.amount import Amount
import json
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("chain_state")


class HiveChainMonitor:
    """Monitor Hive chain state, supply metrics, and calculate conversions."""

    def __init__(self, nodes=None):
        self.hive = Hive(
            node=nodes or ["https://api.hive.blog", "https://api.deathwing.me"]
        )
        self._dgp_cache = None
        self._dgp_time = 0

    def get_dgp(self, max_age=3):
        """Get Dynamic Global Properties with caching."""
        now = time.time()
        if self._dgp_cache and (now - self._dgp_time) < max_age:
            return self._dgp_cache

        self._dgp_cache = self.hive.rpc.get_dynamic_global_properties()
        self._dgp_time = now
        return self._dgp_cache

    def vests_to_hp(self, vests):
        """Convert VESTS to Hive Power (HP)."""
        dgp = self.get_dgp()
        total_vesting_fund = float(Amount(dgp["total_vesting_fund_hive"]))
        total_vesting_shares = float(Amount(dgp["total_vesting_shares"]))
        return float(vests) * total_vesting_fund / total_vesting_shares

    def hp_to_vests(self, hp):
        """Convert HP to VESTS."""
        dgp = self.get_dgp()
        total_vesting_fund = float(Amount(dgp["total_vesting_fund_hive"]))
        total_vesting_shares = float(Amount(dgp["total_vesting_shares"]))
        return float(hp) * total_vesting_shares / total_vesting_fund

    def get_supply_metrics(self):
        """Get current supply and economic metrics."""
        dgp = self.get_dgp(max_age=30)

        current_supply = float(Amount(dgp["current_supply"]))
        hbd_supply = float(Amount(dgp["current_hbd_supply"]))
        virtual_supply = float(Amount(dgp["virtual_supply"]))
        vesting_fund = float(Amount(dgp["total_vesting_fund_hive"]))

        # HBD debt ratio (HBD value / virtual supply)
        # When this exceeds hbd_stop_percent, HBD printing stops
        hbd_debt_ratio = (hbd_supply / virtual_supply * 100) if virtual_supply > 0 else 0

        # Staking ratio (HIVE locked in HP / total supply)
        staking_ratio = (vesting_fund / current_supply * 100) if current_supply > 0 else 0

        return {
            "current_supply_hive": round(current_supply, 3),
            "current_supply_hbd": round(hbd_supply, 3),
            "virtual_supply": round(virtual_supply, 3),
            "total_vesting_fund_hive": round(vesting_fund, 3),
            "hbd_debt_ratio_pct": round(hbd_debt_ratio, 2),
            "staking_ratio_pct": round(staking_ratio, 2),
            "hbd_interest_rate_pct": dgp["hbd_interest_rate"] / 100,
            "hbd_print_rate": dgp["hbd_print_rate"],
            "vests_per_hp": round(self.hp_to_vests(1), 6),
            "hp_per_mvests": round(self.vests_to_hp(1e6), 3),
        }

    def get_reward_fund(self):
        """Get current reward fund data for vote value estimation."""
        fund = self.hive.rpc.get_reward_fund("post")
        return {
            "reward_balance": str(fund["reward_balance"]),
            "recent_claims": int(fund["recent_claims"]),
            "content_constant": int(fund.get("content_constant", 0)),
        }

    def estimate_vote_value(self, hp, weight_pct=100, voting_power_pct=100):
        """Estimate the dollar value of a vote given HP, weight, and voting power."""
        dgp = self.get_dgp()
        fund = self.get_reward_fund()

        # Get median price
        median = self.hive.rpc.get_current_median_history_price()
        base = float(Amount(median["base"]))
        quote = float(Amount(median["quote"]))
        hive_price = base / quote  # HBD per HIVE

        # Calculate rshares
        vests = self.hp_to_vests(hp) * 1e6  # Convert to raw vests
        used_power = int(voting_power_pct * 100 * weight_pct) // 10000
        rshares = int(vests * used_power / 10000)

        # Calculate vote value
        reward_balance = float(Amount(fund["reward_balance"]))
        recent_claims = fund["recent_claims"]

        vote_value_hive = (rshares / recent_claims) * reward_balance
        vote_value_hbd = vote_value_hive * hive_price

        return {
            "rshares": rshares,
            "vote_value_hive": round(vote_value_hive, 4),
            "vote_value_hbd": round(vote_value_hbd, 4),
            "hive_price_usd": round(hive_price, 3),
        }

    def get_block_info(self):
        """Get current block production info."""
        dgp = self.get_dgp()
        blockchain = Blockchain(blockchain_instance=self.hive)

        return {
            "head_block": dgp["head_block_number"],
            "last_irreversible": dgp["last_irreversible_block_num"],
            "confirmation_lag": dgp["head_block_number"] - dgp["last_irreversible_block_num"],
            "current_witness": dgp["current_witness"],
            "block_time": dgp["time"],
            "blocks_per_day": 28800,  # 3-second blocks
        }

    def full_dashboard(self):
        """Generate a complete chain state dashboard."""
        supply = self.get_supply_metrics()
        block = self.get_block_info()
        vote_1k = self.estimate_vote_value(hp=1000)

        dashboard = {
            "timestamp": datetime.utcnow().isoformat(),
            "supply": supply,
            "block": block,
            "economics": {
                "1k_hp_vote_value_hbd": vote_1k["vote_value_hbd"],
                "hive_price_median": vote_1k["hive_price_usd"],
                "hbd_interest_apy": supply["hbd_interest_rate_pct"],
                "hbd_debt_ratio": supply["hbd_debt_ratio_pct"],
                "staking_ratio": supply["staking_ratio_pct"],
            },
            "conversion": {
                "1_hp_in_vests": supply["vests_per_hp"],
                "1m_vests_in_hp": supply["hp_per_mvests"],
            },
        }

        return dashboard


# Usage
monitor = HiveChainMonitor()

# Supply metrics
supply = monitor.get_supply_metrics()
print(f"HIVE Supply: {supply['current_supply_hive']:,.0f}")
print(f"HBD Supply: {supply['current_supply_hbd']:,.0f}")
print(f"HBD Debt Ratio: {supply['hbd_debt_ratio_pct']}%")
print(f"Staking Ratio: {supply['staking_ratio_pct']}%")
print(f"HBD Interest: {supply['hbd_interest_rate_pct']}%")
print(f"1 HP = {supply['vests_per_hp']} VESTS")

# Vote value estimation
vote = monitor.estimate_vote_value(hp=5000, weight_pct=100, voting_power_pct=100)
print(f"\n5000 HP full vote value: ~${vote['vote_value_hbd']:.4f}")

# Full dashboard
dashboard = monitor.full_dashboard()
print(json.dumps(dashboard, indent=2))
```

### Key Fields Reference

| Field | Type | Description |
|-------|------|-------------|
| `head_block_number` | int | Latest block number |
| `last_irreversible_block_num` | int | Last confirmed block (finality) |
| `current_supply` | Asset | Total HIVE tokens |
| `current_hbd_supply` | Asset | Total HBD tokens |
| `virtual_supply` | Asset | HIVE + HBD-as-HIVE total |
| `total_vesting_fund_hive` | Asset | HIVE locked in HP |
| `total_vesting_shares` | Asset | Total VESTS (HP unit) |
| `hbd_interest_rate` | int | HBD savings APR in basis pts (1500 = 15%) |
| `hbd_print_rate` | int | 10000 = normal, lower = restricted |
| `hbd_stop_percent` | int | Debt ratio to stop HBD printing |

### Important Notes

1. **VESTS vs HP**: The blockchain works in VESTS internally. HP is a display concept. Always convert using DGP ratios: `HP = VESTS * total_vesting_fund_hive / total_vesting_shares`.
2. **Irreversibility**: Transactions are reversible until they reach the last irreversible block (~45 seconds / 15 blocks). For exchanges and high-value operations, wait for irreversibility.
3. **HBD peg maintenance**: When `hbd_debt_ratio` exceeds `hbd_stop_percent` (~10%), the chain stops printing HBD and pays authors in HIVE instead. This protects the HBD peg.
4. **Reward pool**: The reward fund (`get_reward_fund`) shows the available reward balance and recent claims. Vote values decrease when total voting activity is high.
5. **Caching**: DGP changes every 3 seconds. For display purposes, cache for 3-30 seconds. For transaction building, always fetch fresh.
'''
    ),
]
