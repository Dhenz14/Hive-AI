// ============================================================================
// Hive Social App — Express + dhive Reference Implementation
// ============================================================================
//
// This is a COMPLETE, RUNNABLE REST API for interacting with the Hive
// blockchain's social features. Every Hive-specific line is annotated with
// tutorial comments so you can learn blockchain social mechanics as you read.
//
// Hive Blockchain Primer:
// -----------------------
// Hive is a Delegated Proof-of-Stake (DPoS) blockchain purpose-built for
// social media. Unlike Ethereum where every transaction costs gas (ETH),
// Hive uses "Resource Credits" (RC) — a renewable, stake-based budget.
// The more Hive Power (HP) you have, the more free transactions you can do.
//
// Key concepts:
//   - Posts and comments live ON-CHAIN and are immutable after 7 days
//   - Authors earn HIVE/HBD rewards from upvotes during a 7-day window
//   - Every action (post, vote, comment, follow) is a blockchain transaction
//   - Transactions confirm in ~3 seconds (one block time)
//   - No gas fees — Resource Credits regenerate every 5 days
//
// Run:  npm install && cp .env.example .env && npm start
// Docs: See README.md for full API documentation and curl examples
// ============================================================================

"use strict";

const express = require("express");
const cors = require("cors");
const dhive = require("@hiveio/dhive");
require("dotenv").config();

const app = express();
app.use(cors());
app.use(express.json());

// ============================================================================
// HIVE CLIENT SETUP
// ============================================================================
//
// dhive is the official JavaScript library for the Hive blockchain.
// It communicates with Hive API nodes over HTTP/WebSocket using the
// JSON-RPC 2.0 protocol. The client handles serialization of operations,
// signing with private keys, and broadcasting to the network.
//
// We pass an array of node URLs for automatic failover. If the first node
// is unreachable, dhive tries the next one. This is important because
// public Hive nodes occasionally go down for maintenance.
//
// Common public nodes (pick 2-3 for redundancy):
//   https://api.hive.blog        — Official, run by Hive core devs
//   https://api.deathwing.me     — Fast EU node, reliable
//   https://anyx.io              — Long-running community node
//   https://rpc.ausbit.dev       — Asia-Pacific region
//   https://hive-api.arcange.eu  — EU backup

const HIVE_NODE = process.env.HIVE_NODE || "https://api.hive.blog";
const HIVE_USERNAME = process.env.HIVE_USERNAME || "";
const HIVE_POSTING_KEY = process.env.HIVE_POSTING_KEY || "";
const PORT = parseInt(process.env.PORT, 10) || 3000;

// Create the dhive client with failover nodes.
// The second argument is unused (legacy), the third sets options:
//   - timeout: ms before a request is considered failed (default 60000)
//   - failoverThreshold: how many failures before switching nodes
const client = new dhive.Client(
  [HIVE_NODE, "https://api.deathwing.me", "https://anyx.io"],
  {
    timeout: 15000,       // 15s timeout per request
    failoverThreshold: 3, // switch node after 3 consecutive failures
  }
);

// ============================================================================
// PRIVATE KEY HANDLING
// ============================================================================
//
// Hive uses a hierarchical key system (derived from a master password):
//
//   POSTING KEY  -> social actions: post, comment, vote, follow, reblog
//   ACTIVE KEY   -> financial actions: transfer, power up/down, witness vote
//   OWNER KEY    -> account recovery, change other keys (NEVER use in apps)
//   MEMO KEY     -> encrypt/decrypt private transfer memos
//
// For a social app, you ONLY need the POSTING key. We parse it once at
// startup. If invalid, the app starts in read-only mode (GET endpoints
// still work, but POST endpoints will return 403).

let postingKey = null;
try {
  if (HIVE_POSTING_KEY && HIVE_POSTING_KEY !== "your_posting_private_key_here") {
    // dhive.PrivateKey.fromString() validates the WIF format.
    // Hive private keys are base58check-encoded and start with "5".
    // If the key is malformed, this throws immediately.
    postingKey = dhive.PrivateKey.fromString(HIVE_POSTING_KEY);
    console.log(`[Hive] Posting key loaded for @${HIVE_USERNAME}`);
  } else {
    console.warn(
      "[Hive] No posting key configured — running in READ-ONLY mode.\n" +
      "       Set HIVE_POSTING_KEY in .env to enable write operations."
    );
  }
} catch (err) {
  console.error(
    `[Hive] Invalid posting key: ${err.message}\n` +
    "       Check your .env file. The key should start with '5' and be ~51 chars."
  );
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Middleware: require a valid posting key for write operations.
 * Returns 403 if no key is configured.
 */
function requireKey(req, res, next) {
  if (!postingKey || !HIVE_USERNAME) {
    return res.status(403).json({
      error: "No posting key configured",
      hint: "Set HIVE_USERNAME and HIVE_POSTING_KEY in your .env file",
    });
  }
  next();
}

/**
 * Generate a unique permlink (URL slug) for a new post or comment.
 *
 * HIVE CONCEPT: Every post/comment is identified by the tuple (author, permlink).
 * The permlink must be unique per author and can only contain lowercase letters,
 * numbers, and hyphens. It becomes the URL path on front-ends like PeakD:
 *   https://peakd.com/@author/permlink
 *
 * Once a post is published, the permlink is permanent. You cannot rename or
 * move posts — they live on-chain forever.
 */
function generatePermlink(title) {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-") // Replace non-alphanumeric chars with hyphens
    .replace(/^-|-$/g, "")       // Trim leading/trailing hyphens
    .substring(0, 200);          // Hive permlinks max out around 256 chars

  // Append timestamp to guarantee uniqueness even if the user posts the same
  // title twice (which happens more often than you'd think)
  return `${slug}-${Date.now().toString(36)}`;
}

/**
 * Parse Hive reputation score from raw blockchain value.
 *
 * HIVE CONCEPT: Reputation on Hive is stored as a large integer (e.g.,
 * 168190025879915). The human-readable score (e.g., 72) is calculated with
 * a logarithmic formula. New accounts start at 25. Scores above ~70 indicate
 * established users. Negative reputation (below 0) means the account was
 * heavily downvoted and their posts are hidden by default on most front-ends.
 *
 * The formula: score = max(log10(abs(rawReputation) - 9) * 9 + 25, 0)
 * If rawReputation is negative, the score is negated.
 */
function parseReputation(rawReputation) {
  const raw = parseInt(rawReputation, 10);
  if (raw === 0) return 25; // Default reputation for new accounts

  const isNegative = raw < 0;
  const absRep = Math.abs(raw);
  const log = Math.log10(absRep);

  // The "- 9" in the classic formula is approximate; this simplified version
  // produces the same results as PeakD and Hive.blog front-ends.
  let score = Math.max(Math.log10(absRep - 9) * 9 + 25, 0);
  if (isNegative) score = -score;

  return Math.floor(score * 100) / 100; // Two decimal places
}

/**
 * Convert VESTS to Hive Power (HP).
 *
 * HIVE CONCEPT: Internally, Hive tracks staked tokens as "VESTS" (Vesting
 * Shares). Users see "Hive Power" (HP) on front-ends. The conversion rate
 * changes slowly over time as new HIVE is printed. To convert, we need the
 * global dynamic properties which tell us the current total_vesting_fund
 * and total_vesting_shares.
 *
 * Formula: HP = VESTS * (total_vesting_fund_hive / total_vesting_shares)
 */
async function vestsToHP(vests) {
  const props = await client.database.getDynamicGlobalProperties();

  // Parse out the numeric values (they come as strings like "123.456 HIVE")
  const totalVestingFund = parseFloat(props.total_vesting_fund_hive.split(" ")[0]);
  const totalVestingShares = parseFloat(props.total_vesting_shares.split(" ")[0]);

  return (parseFloat(vests) * totalVestingFund) / totalVestingShares;
}

/**
 * Check if the account has enough Resource Credits for an operation.
 *
 * HIVE CONCEPT: Resource Credits (RC) are Hive's "gas" system, but free and
 * regenerative. Every account has an RC budget proportional to their Hive
 * Power. RC regenerates 20% per day (fully in 5 days). Common RC costs:
 *   - Vote: ~1-2% of a typical account's daily RC
 *   - Comment: ~5-10%
 *   - Post: ~5-10%
 *   - Custom JSON (follow, reblog): ~1-2%
 *   - Transfer: ~1%
 *
 * New accounts with minimal HP often run out of RC after a few operations.
 * This function checks if the current RC percentage is above a threshold.
 * When RC runs out, the user gets "not enough resource credits" errors and
 * must wait for regeneration or power up more HIVE.
 */
async function checkResourceCredits(username, minimumPercent = 5) {
  try {
    // rc_api is a separate API namespace dedicated to Resource Credit queries
    const rcAccount = await client.call("rc_api", "find_rc_accounts", {
      accounts: [username],
    });

    if (!rcAccount || !rcAccount.rc_accounts || rcAccount.rc_accounts.length === 0) {
      return { ok: true, percent: 100, warning: "Could not fetch RC — proceeding anyway" };
    }

    const rc = rcAccount.rc_accounts[0];
    const maxRC = parseFloat(rc.max_rc);
    const currentRC = parseFloat(rc.rc_manabar.current_mana);

    // RC regenerates continuously. The stored value is a snapshot at a specific
    // time. We calculate current mana by adding regeneration since last update.
    const now = Math.floor(Date.now() / 1000);
    const lastUpdate = rc.rc_manabar.last_update_time;
    const elapsed = now - lastUpdate;

    // Regeneration: full regeneration in 432000 seconds (5 days)
    const regenerated = (maxRC * elapsed) / 432000;
    const estimatedCurrent = Math.min(currentRC + regenerated, maxRC);
    const percent = maxRC > 0 ? (estimatedCurrent / maxRC) * 100 : 0;

    return {
      ok: percent >= minimumPercent,
      percent: Math.round(percent * 100) / 100,
      maxRC: maxRC,
      currentRC: Math.round(estimatedCurrent),
    };
  } catch (err) {
    // If RC check fails, don't block the operation — the blockchain will
    // reject it anyway if RC is insufficient, and we'll get a clear error.
    return { ok: true, percent: -1, warning: `RC check failed: ${err.message}` };
  }
}

/**
 * Standard error handler for Hive blockchain errors.
 *
 * HIVE CONCEPT: The blockchain returns specific error messages for common
 * failures. This function translates cryptic blockchain errors into
 * developer-friendly messages with actionable hints.
 */
function handleHiveError(res, err, operation) {
  const msg = err.message || String(err);

  // "Missing Posting Authority" — wrong key type or key doesn't match account
  if (msg.includes("missing required posting authority")) {
    return res.status(403).json({
      error: `Posting authority missing for ${operation}`,
      hint: "Your posting key does not match the account in HIVE_USERNAME. " +
            "Double-check both values in .env.",
      details: msg,
    });
  }

  // "Not enough Resource Credits" — account ran out of free transactions
  if (msg.includes("not enough rc") || msg.includes("rc_plugin")) {
    return res.status(429).json({
      error: "Not enough Resource Credits",
      hint: "Your account has used up its free transaction budget. " +
            "Wait a few hours for RC to regenerate, or power up more HIVE " +
            "to increase your RC capacity.",
      details: msg,
    });
  }

  // "Bandwidth limit exceeded" — older name for RC exhaustion
  if (msg.includes("bandwidth")) {
    return res.status(429).json({
      error: "Bandwidth limit exceeded (Resource Credits depleted)",
      hint: "Same as RC exhaustion. Wait for regeneration or increase HP.",
      details: msg,
    });
  }

  // "duplicate transaction" — exact same transaction broadcast twice
  if (msg.includes("duplicate")) {
    return res.status(409).json({
      error: "Duplicate transaction",
      hint: "This exact operation was already broadcast. Hive blocks " +
            "duplicate transactions within the same block.",
      details: msg,
    });
  }

  // "STEEM_MIN_REPLY_INTERVAL" or similar rate limits
  if (msg.includes("HIVE_MIN_REPLY_INTERVAL") || msg.includes("MIN_ROOT_COMMENT_INTERVAL")) {
    return res.status(429).json({
      error: "Rate limited by Hive consensus rules",
      hint: "Hive enforces a 3-second interval between comments and " +
            "a 5-minute interval between top-level posts from the same account.",
      details: msg,
    });
  }

  // Generic blockchain error
  return res.status(500).json({
    error: `Hive operation failed: ${operation}`,
    details: msg,
  });
}


// ============================================================================
// READ ENDPOINTS (no key required)
// ============================================================================

// --------------------------------------------------------------------------
// GET /api/feed/:tag — Get posts by tag (trending, created, hot)
// --------------------------------------------------------------------------
// curl http://localhost:3000/api/feed/hive?sort=trending&limit=5
//
// HIVE CONCEPT: Posts on Hive are tagged with categories. The first tag is
// the "category" (also called the parent_permlink) which determines which
// community the post belongs to. Additional tags are stored in json_metadata.
//
// Hive offers several built-in sort orders:
//   - "trending"  — sorted by pending payout (popular posts with high rewards)
//   - "created"   — newest first (chronological)
//   - "hot"       — recent posts gaining traction quickly
//   - "promoted"  — posts that burned HBD for promotion (rarely used)
//
// The API uses the "bridge" namespace, which is a higher-level API layer
// that returns enriched post objects with profile info and community data.

app.get("/api/feed/:tag", async (req, res) => {
  try {
    const { tag } = req.params;
    const sort = req.query.sort || "trending";
    const limit = Math.min(parseInt(req.query.limit, 10) || 10, 50);

    // Validate the sort order against Hive's supported types.
    // Using an invalid sort returns an unhelpful RPC error.
    const validSorts = ["trending", "created", "hot", "promoted", "payout", "muted"];
    if (!validSorts.includes(sort)) {
      return res.status(400).json({
        error: `Invalid sort order: ${sort}`,
        valid: validSorts,
      });
    }

    // bridge.get_ranked_posts is the modern API for fetching sorted posts.
    // It replaced the deprecated condenser_api.get_discussions_by_* methods.
    //
    // Parameters:
    //   sort   — ranking algorithm (trending, created, hot, etc.)
    //   tag    — filter by tag/category (empty string = all tags)
    //   limit  — number of posts (1-50 per page)
    //
    // The response includes computed fields like `payout` (pending rewards),
    // `active_votes` (list of all votes), and `author_reputation` (decoded).
    const posts = await client.call("bridge", "get_ranked_posts", {
      sort: sort,
      tag: tag,
      limit: limit,
      observer: "", // Observer account — affects mute lists; empty = no filtering
    });

    // Transform the raw blockchain response into a cleaner API shape.
    // Hive posts contain a LOT of fields; we cherry-pick the useful ones.
    const results = posts.map((post) => ({
      // Core identity — the (author, permlink) tuple is a post's unique ID
      author: post.author,
      permlink: post.permlink,

      // Human-readable URL on PeakD (the most popular Hive front-end)
      url: `https://peakd.com/@${post.author}/${post.permlink}`,

      title: post.title,

      // post.body contains the full Markdown content. For a feed, we send
      // just a preview (first 300 chars). Use GET /api/post/:author/:permlink
      // for the full body.
      preview: post.body.substring(0, 300),

      // json_metadata is a JSON string embedded in the post that front-ends
      // use for images, tags, app name, canonical URLs, etc.
      tags: (() => {
        try {
          const meta = typeof post.json_metadata === "string"
            ? JSON.parse(post.json_metadata)
            : post.json_metadata;
          return meta.tags || [];
        } catch {
          return [];
        }
      })(),

      // Payout info — Hive's reward system explained:
      //   - Posts earn rewards for 7 days after publishing
      //   - Rewards come from Hive's inflation pool (not from voters' wallets)
      //   - pending_payout_value = estimated rewards if payout happened now
      //   - After 7 days, payout splits: 50% to author, 50% to curators (voters)
      //   - Author can choose: 50/50 (half HIVE, half HBD) or 100% HP
      pending_payout: post.pending_payout_value || post.payout,

      // Vote data
      // net_votes = upvotes minus downvotes (can be negative!)
      // Hive downvotes reduce rewards and can push reputation negative.
      net_votes: post.net_votes || 0,
      children: post.children,          // Number of replies (comments)
      author_reputation: post.author_reputation,

      // Timestamps — Hive uses UTC, no timezone info
      created: post.created,
    }));

    res.json({
      tag,
      sort,
      count: results.length,
      posts: results,
    });
  } catch (err) {
    handleHiveError(res, err, "get_ranked_posts");
  }
});

// --------------------------------------------------------------------------
// GET /api/post/:author/:permlink — Get a single post with comments
// --------------------------------------------------------------------------
// curl http://localhost:3000/api/post/hiveio/hive-hard-fork-26
//
// HIVE CONCEPT: A post is uniquely identified by its author + permlink.
// Comments are also posts — they just have a parent_author and parent_permlink
// that point to the post they're replying to. This creates a tree structure
// where all comments live on-chain alongside the root post.

app.get("/api/post/:author/:permlink", async (req, res) => {
  try {
    const { author, permlink } = req.params;

    // bridge.get_discussion fetches a post AND all its replies in one call.
    // This is more efficient than fetching the post then fetching comments
    // separately. The response is a flat map keyed by "author/permlink".
    //
    // The first entry is the root post. All others are comments/replies.
    // Each entry has parent_author and parent_permlink to reconstruct the tree.
    const discussion = await client.call("bridge", "get_discussion", {
      author: author,
      permlink: permlink,
      observer: "",
    });

    if (!discussion || Object.keys(discussion).length === 0) {
      return res.status(404).json({
        error: "Post not found",
        hint: `No post exists at @${author}/${permlink}. Check the author ` +
              "name and permlink spelling.",
      });
    }

    // The root post key in the discussion map
    const rootKey = `${author}/${permlink}`;
    const rootPost = discussion[rootKey];

    if (!rootPost) {
      return res.status(404).json({ error: "Post not found in discussion tree" });
    }

    // Parse json_metadata for the root post
    let metadata = {};
    try {
      metadata = typeof rootPost.json_metadata === "string"
        ? JSON.parse(rootPost.json_metadata)
        : rootPost.json_metadata || {};
    } catch {
      metadata = {};
    }

    // Separate comments from the root post and build a flat list
    const comments = [];
    for (const [key, entry] of Object.entries(discussion)) {
      if (key === rootKey) continue; // Skip the root post itself

      comments.push({
        author: entry.author,
        permlink: entry.permlink,
        // parent_author tells you who this comment is replying to.
        // If parent_author equals the root post's author, it's a top-level reply.
        // Otherwise, it's a nested reply (reply to a reply).
        parent_author: entry.parent_author,
        parent_permlink: entry.parent_permlink,
        body: entry.body,
        created: entry.created,
        net_votes: entry.net_votes || 0,
        // depth=1 means direct reply, depth=2 means reply-to-reply, etc.
        depth: entry.depth,
        author_reputation: entry.author_reputation,
      });
    }

    // Sort comments chronologically (oldest first, like a conversation)
    comments.sort((a, b) => new Date(a.created) - new Date(b.created));

    // active_votes is the full list of every vote on this post.
    // Each vote has: voter, weight (in basis points), rshares (reward shares),
    // and time. We include a summary plus the top voters.
    const votes = (rootPost.active_votes || []).map((v) => ({
      voter: v.voter,
      // Weight is in basis points: 10000 = 100% upvote, -10000 = 100% downvote.
      // Partial votes are common: 5000 = 50% upvote, etc.
      weight: v.percent || v.weight,
      // rshares (reward shares) determine how much this vote is worth in $$.
      // Higher HP voters have more rshares per vote.
      rshares: v.rshares,
      time: v.time,
    }));

    res.json({
      author: rootPost.author,
      permlink: rootPost.permlink,
      title: rootPost.title,
      body: rootPost.body,            // Full Markdown content
      category: rootPost.category,     // Primary tag / community
      tags: metadata.tags || [],
      image: metadata.image ? metadata.image[0] : null,

      // Payout details
      pending_payout: rootPost.pending_payout_value,
      total_payout: rootPost.total_payout_value,     // Already paid out (after 7 days)
      curator_payout: rootPost.curator_payout_value, // Portion paid to voters

      // Vote stats
      net_votes: rootPost.net_votes || 0,
      vote_count: votes.length,
      votes: votes,

      // Timestamps
      created: rootPost.created,
      last_update: rootPost.last_update,
      // cashout_time is when the 7-day payout window ends.
      // After this time, the post's rewards are finalized and distributed.
      // A cashout_time far in the past (1969) means payout already happened.
      cashout_time: rootPost.cashout_time,

      // Comment tree
      comment_count: comments.length,
      comments: comments,

      // The app that created this post (e.g., "peakd/2024.1.1", "ecency/3.1")
      app: metadata.app || "unknown",
    });
  } catch (err) {
    handleHiveError(res, err, "get_discussion");
  }
});

// --------------------------------------------------------------------------
// GET /api/account/:username — Get account info
// --------------------------------------------------------------------------
// curl http://localhost:3000/api/account/blocktrades
//
// HIVE CONCEPT: Hive accounts are human-readable names (3-16 chars, lowercase).
// Each account stores balances, reputation, delegations, and authority keys.
// Account creation costs ~3 HIVE or requires an "account creation token" from
// an existing account. This prevents sybil attacks (mass fake accounts).

app.get("/api/account/:username", async (req, res) => {
  try {
    const { username } = req.params;

    // condenser_api.get_accounts returns an array (you can fetch multiple
    // accounts in one call). We fetch just one.
    const accounts = await client.database.getAccounts([username]);
    if (!accounts || accounts.length === 0) {
      return res.status(404).json({
        error: `Account @${username} not found`,
        hint: "Hive usernames are case-sensitive and 3-16 characters. " +
              "Check the spelling.",
      });
    }

    const account = accounts[0];

    // Calculate Hive Power from VESTS
    // Hive stores staked tokens as "vesting_shares" in VESTS units.
    // We convert to the user-facing "Hive Power" (HP) value.
    const ownHP = await vestsToHP(
      parseFloat(account.vesting_shares.split(" ")[0])
    );

    // Delegated HP — some users delegate HP to others (e.g., to help new
    // accounts have more RC, or for curation projects). Delegation does NOT
    // transfer ownership — the delegator can undelegate anytime (5-day cooldown).
    const delegatedHP = await vestsToHP(
      parseFloat(account.delegated_vesting_shares.split(" ")[0])
    );
    const receivedHP = await vestsToHP(
      parseFloat(account.received_vesting_shares.split(" ")[0])
    );

    // Effective HP = own + received - delegated out
    const effectiveHP = ownHP + receivedHP - delegatedHP;

    // Fetch follower/following counts using the bridge API
    // (condenser_api methods for this are deprecated)
    let followerCount = 0;
    let followingCount = 0;
    try {
      const profile = await client.call("bridge", "get_profile", {
        account: username,
      });
      if (profile) {
        followerCount = profile.stats ? profile.stats.followers : 0;
        followingCount = profile.stats ? profile.stats.following : 0;
      }
    } catch {
      // Non-critical — profile stats may be unavailable on some nodes
    }

    // Check Resource Credits
    const rc = await checkResourceCredits(username);

    res.json({
      name: account.name,
      reputation: parseReputation(account.reputation),

      // Profile metadata is stored as a JSON string in posting_json_metadata.
      // This contains the user's display name, bio, profile picture, location,
      // and website — set through front-ends like PeakD or Ecency.
      profile: (() => {
        try {
          const meta = JSON.parse(account.posting_json_metadata || "{}");
          return meta.profile || {};
        } catch {
          return {};
        }
      })(),

      // Balances — Hive has two main tokens:
      //   HIVE: the governance/utility token (can be traded, staked as HP)
      //   HBD:  Hive Backed Dollar, a stablecoin pegged to ~$1 USD
      //         HBD in savings earns 15% APR (set by witnesses)
      balance: {
        hive: account.balance,          // Liquid HIVE
        hbd: account.hbd_balance,       // Liquid HBD (Hive Backed Dollars)
        savings_hive: account.savings_balance,
        savings_hbd: account.savings_hbd_balance,
      },

      // Hive Power breakdown
      hive_power: {
        own: Math.round(ownHP * 1000) / 1000,
        delegated_out: Math.round(delegatedHP * 1000) / 1000,
        received: Math.round(receivedHP * 1000) / 1000,
        effective: Math.round(effectiveHP * 1000) / 1000,
      },

      // Resource Credits — your "free transaction" budget
      resource_credits: rc,

      // Social stats
      followers: followerCount,
      following: followingCount,
      post_count: account.post_count,

      // Account dates
      created: account.created,
      last_post: account.last_post,
      last_vote_time: account.last_vote_time,

      // Witness votes — Hive uses DPoS where stakeholders vote for "witnesses"
      // (block producers). Each account can vote for up to 30 witnesses.
      // Top 20 witnesses produce blocks in round-robin order.
      witness_votes: account.witness_votes,
    });
  } catch (err) {
    handleHiveError(res, err, "get_account");
  }
});

// --------------------------------------------------------------------------
// GET /api/notifications/:username — Get recent account history
// --------------------------------------------------------------------------
// curl http://localhost:3000/api/notifications/blocktrades?limit=20
//
// HIVE CONCEPT: Every blockchain operation involving an account is recorded
// in that account's "account_history". This includes incoming votes,
// mentions, replies, transfers, and more. It's the raw on-chain activity
// feed — like a blockchain-native notification system.

app.get("/api/notifications/:username", async (req, res) => {
  try {
    const { username } = req.params;
    const limit = Math.min(parseInt(req.query.limit, 10) || 20, 100);
    const typeFilter = req.query.type || null; // e.g., "vote", "comment", "transfer"

    // bridge.account_notifications is the modern notification API.
    // It returns decoded, human-readable notifications instead of raw
    // account_history operations.
    //
    // Each notification has:
    //   type: "vote", "reply", "mention", "follow", "reblog", "transfer", etc.
    //   msg:  human-readable description
    //   url:  link to the related content
    //   date: when it happened
    //   score: relevance score (higher = more important)
    const notifications = await client.call("bridge", "account_notifications", {
      account: username,
      limit: limit,
    });

    // Filter by type if requested
    let results = notifications;
    if (typeFilter) {
      results = notifications.filter((n) => n.type === typeFilter);
    }

    res.json({
      account: username,
      count: results.length,
      // Available notification types for filtering
      available_types: [
        "vote",      // Someone voted on your post/comment
        "reply",     // Someone replied to your post/comment
        "mention",   // Someone mentioned @username in their post
        "follow",    // Someone followed you
        "reblog",    // Someone reblogged your post
        "transfer",  // Someone sent you HIVE or HBD
        "unvote",    // Someone removed their vote
      ],
      notifications: results.map((n) => ({
        type: n.type,
        message: n.msg,
        url: n.url ? `https://peakd.com${n.url}` : null,
        date: n.date,
        score: n.score,
      })),
    });
  } catch (err) {
    handleHiveError(res, err, "account_notifications");
  }
});


// ============================================================================
// WRITE ENDPOINTS (posting key required)
// ============================================================================

// --------------------------------------------------------------------------
// POST /api/post — Create a new blog post
// --------------------------------------------------------------------------
// curl -X POST http://localhost:3000/api/post \
//   -H "Content-Type: application/json" \
//   -d '{"title":"My First Post","body":"Hello Hive!","tags":["introduceyourself"]}'
//
// HIVE CONCEPT: Creating a post is a "comment" operation on the blockchain
// where parent_author is empty and parent_permlink is the first tag (category).
// Yes, posts and comments are the same operation type — the distinction is
// just whether it has a parent or not.
//
// Important constraints:
//   - You can only post once every 5 minutes (HIVE_MIN_ROOT_COMMENT_INTERVAL)
//   - Posts cannot be deleted — only the body can be replaced with empty text
//   - After 7 days, posts become immutable (no edits possible)
//   - Posts are stored on-chain in Markdown format
//   - Max post size is ~64KB (encoded)

app.post("/api/post", requireKey, async (req, res) => {
  try {
    const { title, body, tags } = req.body;

    // Validate inputs
    if (!title || !title.trim()) {
      return res.status(400).json({ error: "Title is required" });
    }
    if (!body || !body.trim()) {
      return res.status(400).json({ error: "Body is required (Markdown supported)" });
    }
    if (!tags || !Array.isArray(tags) || tags.length === 0) {
      return res.status(400).json({
        error: "At least one tag is required",
        hint: "Tags categorize your post. Common first tags: 'hive', 'technology', " +
              "'photography', 'gaming'. The first tag becomes the post category.",
      });
    }

    // Validate tags — Hive tags have specific rules
    for (const tag of tags) {
      if (!/^[a-z][a-z0-9-]*$/.test(tag)) {
        return res.status(400).json({
          error: `Invalid tag: '${tag}'`,
          hint: "Tags must be lowercase, start with a letter, and contain only " +
                "letters, numbers, and hyphens.",
        });
      }
    }

    // Check Resource Credits before broadcasting
    const rc = await checkResourceCredits(HIVE_USERNAME, 10);
    if (!rc.ok) {
      return res.status(429).json({
        error: "Not enough Resource Credits to post",
        rc_percent: rc.percent,
        hint: "Posts cost more RC than votes or follows. Wait for RC to regenerate " +
              "or power up more HIVE.",
      });
    }

    const permlink = generatePermlink(title);

    // Build the json_metadata — this is an arbitrary JSON string stored with
    // the post. Front-ends use it for display (images, tags, formatting hints).
    // The "app" field tells other front-ends which application created this post.
    const jsonMetadata = JSON.stringify({
      tags: tags,
      app: "hive-social-app/1.0.0",
      format: "markdown",
      // image: ["https://..."] — you can include a canonical image URL here
      // canonical_url: "https://..." — for SEO/cross-posting
    });

    // The "comment" operation is the blockchain primitive for both posts and
    // comments. When parent_author is empty (""), it's a root post.
    // When parent_author is set, it's a reply to that author's post/comment.
    //
    // Fields:
    //   parent_author:   "" for root posts, or the author being replied to
    //   parent_permlink: first tag for root posts, or parent's permlink for replies
    //   author:          who is publishing this
    //   permlink:        unique URL slug for this content
    //   title:           post title (empty for comments)
    //   body:            Markdown content
    //   json_metadata:   JSON string with tags, images, app info, etc.
    const operation = [
      "comment",
      {
        parent_author: "",             // Empty = this is a root post, not a reply
        parent_permlink: tags[0],      // First tag = category (community)
        author: HIVE_USERNAME,
        permlink: permlink,
        title: title,
        body: body,
        json_metadata: jsonMetadata,
      },
    ];

    // We also set the "comment_options" to configure payout preferences.
    // This is a separate operation bundled in the same transaction.
    //
    // HIVE CONCEPT: Authors choose how to receive rewards:
    //   - max_accepted_payout_value: cap on rewards ("0.000 HBD" = decline all)
    //   - percent_hbd: what percentage of the author reward is paid in HBD.
    //       10000 = 50% HBD + 50% HP (default, shown as "50/50" on front-ends)
    //       0     = 100% HP (shown as "Power Up 100%")
    //   - allow_votes: whether the post can be voted on (almost always true)
    //   - allow_curation_rewards: whether voters earn curation rewards
    const commentOptions = [
      "comment_options",
      {
        author: HIVE_USERNAME,
        permlink: permlink,
        max_accepted_payout_value: "1000000.000 HBD", // Accept up to $1M (effectively no cap)
        percent_hbd: 10000,                            // 50/50 split (HBD + HP)
        allow_votes: true,
        allow_curation_rewards: true,
        extensions: [],                                // For beneficiary rewards — see below
        // To set beneficiaries (share rewards with other accounts):
        // extensions: [[0, {
        //   beneficiaries: [
        //     { account: "some-app", weight: 500 }  // 5% of author rewards
        //   ]
        // }]]
        // Beneficiary weight is in basis points: 500 = 5%, 1000 = 10%, etc.
      },
    ];

    // client.broadcast.sendOperations() signs the operations with the provided
    // key and broadcasts them to the Hive network. Multiple operations in a
    // single transaction are atomic — either all succeed or all fail.
    //
    // The transaction is signed locally (your private key never leaves this
    // server) and only the signature is sent to the blockchain.
    const result = await client.broadcast.sendOperations(
      [operation, commentOptions],
      postingKey
    );

    // The result contains the transaction ID and block number.
    // The transaction is typically included in the next block (~3 seconds).
    res.status(201).json({
      success: true,
      message: `Post published! Viewable in ~3 seconds (one block time).`,
      author: HIVE_USERNAME,
      permlink: permlink,
      transaction_id: result.id,
      block_num: result.block_num,
      // Direct link to view on PeakD
      url: `https://peakd.com/@${HIVE_USERNAME}/${permlink}`,
      // Note: the post may take 1-2 seconds to appear on front-ends as
      // they need to process the block containing this transaction.
    });
  } catch (err) {
    handleHiveError(res, err, "create_post");
  }
});

// --------------------------------------------------------------------------
// POST /api/vote — Vote on a post or comment
// --------------------------------------------------------------------------
// curl -X POST http://localhost:3000/api/vote \
//   -H "Content-Type: application/json" \
//   -d '{"author":"hiveio","permlink":"hive-hard-fork-26","weight":10000}'
//
// HIVE CONCEPT: Voting is the core mechanic of Hive's reward system.
//
// How voting works:
//   - Each vote has a "weight" from -10000 to 10000 (basis points)
//     - 10000 = 100% upvote (max positive vote)
//     - 5000  = 50% upvote
//     - 0     = remove existing vote (unvote)
//     - -5000 = 50% downvote (flags the content)
//     - -10000 = 100% downvote
//
//   - Vote VALUE depends on your Hive Power and current "voting mana":
//     - Higher HP = each vote is worth more $$
//     - Voting mana starts at 100%, each 100% vote uses ~2% mana
//     - Mana regenerates 20% per day (full in 5 days)
//     - At 50% mana, your votes are worth 50% of their max value
//     - Optimal strategy: keep mana above 80% for maximum efficiency
//
//   - You can change your vote within the 7-day payout window
//   - After payout, votes are finalized and cannot be changed
//
//   - Downvotes are free (separate "downvote mana pool" at 25% of vote mana)
//     They reduce post rewards and can impact author reputation
//
//   - CURATION REWARDS: Voters earn ~50% of the post's total rewards,
//     distributed proportionally by vote weight and timing. Earlier votes
//     on posts that become popular earn more.

app.post("/api/vote", requireKey, async (req, res) => {
  try {
    const { author, permlink, weight } = req.body;

    // Validate inputs
    if (!author || !permlink) {
      return res.status(400).json({
        error: "Both 'author' and 'permlink' are required",
        hint: "These identify which post/comment to vote on. " +
              "Get them from the feed or post endpoint.",
      });
    }

    // Validate weight range
    const voteWeight = parseInt(weight, 10);
    if (isNaN(voteWeight) || voteWeight < -10000 || voteWeight > 10000) {
      return res.status(400).json({
        error: "Weight must be between -10000 and 10000",
        hint: "10000 = 100% upvote, 5000 = 50% upvote, " +
              "-10000 = 100% downvote, 0 = remove vote",
      });
    }

    // Check RC — votes are cheap but still cost some RC
    const rc = await checkResourceCredits(HIVE_USERNAME, 2);
    if (!rc.ok) {
      return res.status(429).json({
        error: "Not enough Resource Credits to vote",
        rc_percent: rc.percent,
      });
    }

    // The "vote" operation is straightforward:
    //   voter:    your account
    //   author:   post/comment author
    //   permlink: post/comment permlink
    //   weight:   vote strength in basis points (-10000 to 10000)
    const result = await client.broadcast.vote(
      {
        voter: HIVE_USERNAME,
        author: author,
        permlink: permlink,
        weight: voteWeight,
      },
      postingKey
    );

    const voteType =
      voteWeight > 0 ? "upvote" : voteWeight < 0 ? "downvote" : "unvote";

    res.json({
      success: true,
      vote_type: voteType,
      weight: voteWeight,
      weight_percent: `${(voteWeight / 100).toFixed(1)}%`,
      voter: HIVE_USERNAME,
      author: author,
      permlink: permlink,
      transaction_id: result.id,
      block_num: result.block_num,
      tip: voteWeight > 0
        ? "Your vote contributes to the post's rewards. You'll earn curation " +
          "rewards when the post pays out after 7 days."
        : voteWeight < 0
        ? "Downvotes reduce the post's pending rewards. Use responsibly — " +
          "downvoting is for spam/plagiarism, not disagreement."
        : "Vote removed. Your previous vote no longer affects this post's rewards.",
    });
  } catch (err) {
    handleHiveError(res, err, "vote");
  }
});

// --------------------------------------------------------------------------
// POST /api/comment — Comment on a post or reply
// --------------------------------------------------------------------------
// curl -X POST http://localhost:3000/api/comment \
//   -H "Content-Type: application/json" \
//   -d '{"parent_author":"hiveio","parent_permlink":"hive-hard-fork-26","body":"Great post!"}'
//
// HIVE CONCEPT: Comments use the exact same "comment" operation as posts.
// The difference is that parent_author is NOT empty — it points to the
// post or comment being replied to.
//
// Comments can earn rewards too! Many Hive users earn significant income
// from thoughtful comments that get upvoted.
//
// Rate limit: you can comment once every 3 seconds (HIVE_MIN_REPLY_INTERVAL).
// This is a consensus-level rule — the blockchain itself rejects faster comments.

app.post("/api/comment", requireKey, async (req, res) => {
  try {
    const { parent_author, parent_permlink, body } = req.body;

    if (!parent_author || !parent_permlink) {
      return res.status(400).json({
        error: "parent_author and parent_permlink are required",
        hint: "These identify which post or comment you are replying to.",
      });
    }
    if (!body || !body.trim()) {
      return res.status(400).json({
        error: "Comment body is required",
        hint: "Markdown is supported. Include meaningful content — low-effort " +
              "comments like 'nice post' often get downvoted on Hive.",
      });
    }

    // Check RC — comments cost more RC than votes
    const rc = await checkResourceCredits(HIVE_USERNAME, 5);
    if (!rc.ok) {
      return res.status(429).json({
        error: "Not enough Resource Credits to comment",
        rc_percent: rc.percent,
      });
    }

    // Comment permlinks typically include the parent permlink for context.
    // The "re-" prefix is a convention (like email "Re:") indicating a reply.
    const permlink = `re-${parent_author}-${parent_permlink}-${Date.now().toString(36)}`;

    // This is the same "comment" operation used for posts, but with
    // parent_author set (making it a reply) and title left empty
    // (comments don't have titles on Hive).
    const result = await client.broadcast.comment(
      {
        parent_author: parent_author,      // The author of the post/comment being replied to
        parent_permlink: parent_permlink,  // The permlink of the post/comment being replied to
        author: HIVE_USERNAME,
        permlink: permlink,
        title: "",                         // Comments don't have titles
        body: body,
        json_metadata: JSON.stringify({
          app: "hive-social-app/1.0.0",
          format: "markdown",
        }),
      },
      postingKey
    );

    res.status(201).json({
      success: true,
      message: "Comment published!",
      author: HIVE_USERNAME,
      permlink: permlink,
      parent_author: parent_author,
      parent_permlink: parent_permlink,
      transaction_id: result.id,
      block_num: result.block_num,
      url: `https://peakd.com/@${HIVE_USERNAME}/${permlink}`,
    });
  } catch (err) {
    handleHiveError(res, err, "comment");
  }
});

// --------------------------------------------------------------------------
// POST /api/follow — Follow or unfollow a user
// --------------------------------------------------------------------------
// curl -X POST http://localhost:3000/api/follow \
//   -H "Content-Type: application/json" \
//   -d '{"target":"blocktrades","unfollow":false}'
//
// HIVE CONCEPT: Follow/unfollow is implemented as a "custom_json" operation.
// Custom JSON is Hive's extensibility mechanism — it lets apps store arbitrary
// JSON data on-chain. The "follow" protocol is standardized so all Hive
// front-ends show the same follower lists.
//
// Custom JSON operations are the cheapest operation type on Hive (lowest RC
// cost) because they don't affect consensus state like token balances.
//
// The "id" field ("follow") tells Hive nodes which protocol/plugin should
// process this operation. Other common custom_json IDs:
//   "follow"        — follow/unfollow/mute users
//   "reblog"        — resteem/reblog posts
//   "community"     — community subscriptions, moderation
//   "notify"        — push notification preferences
//   "splinterlands" — Splinterlands game actions (most-used dApp on Hive)
//   "podping"       — podcast update pings (Hive is the backbone of Podping)

app.post("/api/follow", requireKey, async (req, res) => {
  try {
    const { target, unfollow } = req.body;

    if (!target) {
      return res.status(400).json({ error: "Target username is required" });
    }
    if (target === HIVE_USERNAME) {
      return res.status(400).json({ error: "You cannot follow yourself" });
    }

    // Verify the target account exists
    const accounts = await client.database.getAccounts([target]);
    if (!accounts || accounts.length === 0) {
      return res.status(404).json({
        error: `Account @${target} not found`,
      });
    }

    // The follow operation is a custom_json with specific structure:
    // - "what": ["blog"] = follow (show their posts in your feed)
    // - "what": []       = unfollow (remove from feed)
    // - "what": ["ignore"] = mute (hide their content from your view)
    //
    // Note: "following" and "follower" are from the perspective of
    // the action. The "follower" is who is doing the action (you).
    const followData = JSON.stringify([
      "follow",
      {
        follower: HIVE_USERNAME,
        following: target,
        what: unfollow ? [] : ["blog"], // Empty array = unfollow
      },
    ]);

    // custom_json requires specifying which key authorities are needed.
    // "required_posting_auths" means a posting key can authorize this.
    // "required_auths" would require an active key (for financial custom_json).
    const result = await client.broadcast.sendOperations(
      [
        [
          "custom_json",
          {
            required_auths: [],               // No active key needed
            required_posting_auths: [HIVE_USERNAME], // Posting key authorizes this
            id: "follow",                     // Protocol identifier
            json: followData,                 // The actual follow/unfollow payload
          },
        ],
      ],
      postingKey
    );

    res.json({
      success: true,
      action: unfollow ? "unfollowed" : "followed",
      account: HIVE_USERNAME,
      target: target,
      transaction_id: result.id,
      block_num: result.block_num,
      tip: unfollow
        ? `You unfollowed @${target}. Their posts will no longer appear in your feed.`
        : `You are now following @${target}. Their new posts will appear in your ` +
          `personalized feed on Hive front-ends like PeakD and Ecency.`,
    });
  } catch (err) {
    handleHiveError(res, err, "follow");
  }
});

// --------------------------------------------------------------------------
// POST /api/reblog — Reblog (resteem) a post
// --------------------------------------------------------------------------
// curl -X POST http://localhost:3000/api/reblog \
//   -H "Content-Type: application/json" \
//   -d '{"author":"hiveio","permlink":"hive-hard-fork-26"}'
//
// HIVE CONCEPT: Reblogging (called "resteeming" in Steem, Hive's predecessor)
// shares someone else's post to your followers' feeds. It's like a "retweet"
// on Twitter. The reblog is stored on-chain as a custom_json operation.
//
// Important: Reblogs CANNOT be undone on-chain (there's no "un-reblog"
// operation in the protocol). Some front-ends implement client-side
// un-reblog by hiding it, but the blockchain record persists.
//
// Reblogs don't earn rewards for the reblogger, but they help the original
// author reach a wider audience, which can lead to more votes/rewards.

app.post("/api/reblog", requireKey, async (req, res) => {
  try {
    const { author, permlink } = req.body;

    if (!author || !permlink) {
      return res.status(400).json({
        error: "Both 'author' and 'permlink' are required",
      });
    }

    if (author === HIVE_USERNAME) {
      return res.status(400).json({
        error: "You cannot reblog your own post",
      });
    }

    // Verify the post exists before attempting the reblog
    const content = await client.call("bridge", "get_post", {
      author: author,
      permlink: permlink,
    });
    if (!content || !content.author) {
      return res.status(404).json({ error: "Post not found" });
    }

    // Reblog is a custom_json operation with id "reblog" (some nodes also
    // accept "follow" id with reblog action — we use the dedicated "reblog" id).
    const reblogData = JSON.stringify([
      "reblog",
      {
        account: HIVE_USERNAME,  // Who is reblogging
        author: author,          // Original post author
        permlink: permlink,      // Original post permlink
      },
    ]);

    const result = await client.broadcast.sendOperations(
      [
        [
          "custom_json",
          {
            required_auths: [],
            required_posting_auths: [HIVE_USERNAME],
            id: "reblog",     // Reblog protocol identifier
            json: reblogData,
          },
        ],
      ],
      postingKey
    );

    res.json({
      success: true,
      message: `Reblogged @${author}/${permlink} to your followers`,
      reblogger: HIVE_USERNAME,
      original_author: author,
      permlink: permlink,
      transaction_id: result.id,
      block_num: result.block_num,
      tip: "This post will now appear in your followers' feeds. " +
           "Note: reblogs cannot be undone on-chain.",
    });
  } catch (err) {
    handleHiveError(res, err, "reblog");
  }
});


// ============================================================================
// HEALTH / INFO ENDPOINTS
// ============================================================================

// GET / — API info and blockchain status
app.get("/", async (req, res) => {
  try {
    // getDynamicGlobalProperties returns real-time blockchain state:
    // current block number, time, witness schedule, supply, etc.
    // This is the single most useful diagnostic call for checking
    // if the node is synced and responsive.
    const props = await client.database.getDynamicGlobalProperties();

    res.json({
      app: "Hive Social App",
      version: "1.0.0",
      description: "REST API for Hive blockchain social features",
      docs: "See README.md for full documentation",

      // Read-only mode indicator
      read_only: !postingKey,
      configured_account: HIVE_USERNAME || "(not set)",

      // Blockchain status
      blockchain: {
        head_block: props.head_block_number,
        // Hive produces a new block every 3 seconds
        head_block_time: props.time,
        // Current witness is the block producer for this specific block.
        // Hive has 21 active witnesses who take turns producing blocks.
        current_witness: props.current_witness,
      },

      endpoints: {
        "GET  /api/feed/:tag": "Get posts by tag (query: sort, limit)",
        "GET  /api/post/:author/:permlink": "Get post with comments",
        "GET  /api/account/:username": "Get account info",
        "GET  /api/notifications/:username": "Get notifications",
        "POST /api/post": "Create a new post (body: title, body, tags)",
        "POST /api/vote": "Vote on a post (body: author, permlink, weight)",
        "POST /api/comment": "Comment on a post (body: parent_author, parent_permlink, body)",
        "POST /api/follow": "Follow/unfollow (body: target, unfollow)",
        "POST /api/reblog": "Reblog a post (body: author, permlink)",
      },
    });
  } catch (err) {
    res.status(500).json({
      error: "Failed to connect to Hive node",
      hint: `Check if ${HIVE_NODE} is accessible. Try another node from ` +
            "https://beacon.peakd.com/",
      details: err.message,
    });
  }
});

// ============================================================================
// START SERVER
// ============================================================================

app.listen(PORT, () => {
  console.log(`
====================================================
  Hive Social App running on http://localhost:${PORT}
====================================================

  Mode: ${postingKey ? "READ/WRITE" : "READ-ONLY (no posting key)"}
  Account: ${HIVE_USERNAME || "(not configured)"}
  Node: ${HIVE_NODE}

  Try these endpoints:
    GET  http://localhost:${PORT}/
    GET  http://localhost:${PORT}/api/feed/hive
    GET  http://localhost:${PORT}/api/account/blocktrades

  See README.md for full API documentation.
====================================================
  `);
});

// Export for testing
module.exports = { app, generatePermlink, parseReputation, checkResourceCredits };
