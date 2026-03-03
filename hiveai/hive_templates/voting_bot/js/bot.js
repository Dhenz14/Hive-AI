#!/usr/bin/env node
// =============================================================================
// Hive Automated Voting / Curation Bot (JavaScript / dhive)
// =============================================================================
//
// A production-ready curation bot that streams the Hive blockchain in real time,
// filters posts by configurable rules (tags, authors, reputation, word count),
// checks Resource Credits and voting power, implements vote scheduling and trail
// voting, supports blacklist/whitelist, and logs every vote to a JSON file.
//
// TUTORIAL STRUCTURE:
//   Every Hive-specific section has a "HIVE CONCEPT" comment block that explains
//   the underlying blockchain mechanic so you learn while you build.
//
// QUICK START:
//   1. cp .env.example .env          -- fill in your posting key
//   2. cp config.example.json config.json  -- customise rules
//   3. npm install
//   4. node bot.js
//
// =============================================================================

"use strict";

require("dotenv").config();
const dhive = require("@hiveio/dhive");
const fs = require("fs");
const path = require("path");

// =============================================================================
// HIVE CONCEPT -- Nodes & Failover
// =============================================================================
// Hive is a decentralized network of API nodes run by independent operators.
// Any single node can go offline, fall behind the head block, or rate-limit
// your requests.  Production bots must rotate through several nodes so the
// blockchain stream never stalls.
//
// Popular public nodes (as of 2026):
//   - https://api.hive.blog        (Hive core team)
//   - https://api.deathwing.me     (deathwing)
//   - https://hive-api.arcange.eu  (arcange)
//   - https://api.openhive.network (community-run)
//   - https://rpc.mahdiyari.info   (mahdiyari)
//
// dhive's Client constructor accepts an array of node URLs. When a request to
// the first node fails (timeout, 502, etc.), dhive automatically retries with
// the next node in the list.  We put the user's preferred node first but always
// include fallbacks so the bot stays online.
// =============================================================================

const FAILOVER_NODES = [
  process.env.HIVE_NODE || "https://api.hive.blog",
  "https://api.deathwing.me",
  "https://hive-api.arcange.eu",
  "https://api.openhive.network",
  "https://rpc.mahdiyari.info",
];

// =============================================================================
// Configuration -- loaded from .env (credentials) + config.json (rules)
// =============================================================================
// We separate credentials from rules:
//   .env         -- secret posting key, username (never commit this file)
//   config.json  -- voting rules, thresholds, lists (safe to version-control)
// =============================================================================

/** Load config.json, falling back to config.example.json, then to defaults. */
function loadConfigFile() {
  const candidates = [
    path.join(__dirname, "config.json"),
    path.join(__dirname, "config.example.json"),
  ];
  for (const filePath of candidates) {
    if (fs.existsSync(filePath)) {
      try {
        const raw = fs.readFileSync(filePath, "utf8");
        log(`Loaded configuration from ${path.basename(filePath)}`);
        return JSON.parse(raw);
      } catch (err) {
        warn(`Failed to parse ${filePath}: ${err.message}`);
      }
    }
  }
  warn("No config.json found -- using built-in defaults");
  return {};
}

const configFile = loadConfigFile();

const CONFIG = Object.freeze({
  // --- Credentials (from .env, NEVER from config.json) ---
  username: process.env.HIVE_USERNAME,
  postingKey: process.env.HIVE_POSTING_KEY,

  // --- Voting rules (from config.json, with .env overrides) ---
  // "rules" is an array of objects like:
  //   { "type": "tag",    "value": "hive",      "vote_weight": 50 }
  //   { "type": "author", "value": "buildteam",  "vote_weight": 100 }
  //   { "type": "min_reputation", "value": 50,   "vote_weight": 25 }
  //   { "type": "min_words",      "value": 300,  "vote_weight": 30 }
  // Each rule can override the default vote_weight (as a percentage 1-100).
  rules: configFile.rules || [],

  // Default vote weight used when a rule doesn't specify one (1-100%)
  defaultVoteWeight: parseInt(process.env.VOTE_WEIGHT, 10) / 100 ||
    configFile.default_vote_weight || 50,

  // Minimum reputation to vote (global floor, rules can raise it further)
  minReputation: parseInt(process.env.MIN_REPUTATION, 10) ||
    configFile.min_reputation || 25,

  // Minimum Resource Credits percentage before the bot pauses
  minRcPercent: configFile.min_rc_percent ??
    parseInt(process.env.MIN_RC_PERCENT, 10) || 10,

  // Minimum voting power percentage before the bot pauses voting
  // HIVE CONCEPT: Keeping VP above 80% maximises curation reward efficiency.
  // Each full-power vote costs ~2% VP. At 80% VP you have ~10 full votes/day.
  minVpPercent: configFile.min_vp_percent || 80,

  // Maximum votes in a rolling 24-hour window
  maxDailyVotes: configFile.max_daily_votes ||
    parseInt(process.env.MAX_DAILY_VOTES, 10) || 20,

  // Minutes to wait after a post is created before casting the vote
  // HIVE CONCEPT: See "Curation Window" section below for why this matters.
  voteDelayMinutes: configFile.vote_delay_minutes ??
    parseInt(process.env.VOTE_DELAY_MINUTES, 10) || 5,

  // Trail voting: follow another account's votes in real time
  // Array of usernames whose votes we mirror (we vote on whatever they vote on)
  trailAccounts: configFile.trail_accounts || [],

  // Vote weight when trail voting (percentage 1-100)
  trailVoteWeight: configFile.trail_vote_weight || 50,

  // Blacklist: never vote on posts by these authors (overrides everything)
  blacklist: (configFile.blacklist || []).map((a) => a.toLowerCase()),

  // Whitelist: if non-empty, ONLY vote on posts by these authors
  // (rules still apply on top of the whitelist)
  whitelist: (configFile.whitelist || []).map((a) => a.toLowerCase()),

  // Minimum word count in the post body (filters low-effort content)
  minWordCount: configFile.min_word_count || 0,

  // Path to the vote audit log (JSON lines file)
  voteLogPath: configFile.vote_log_path ||
    path.join(__dirname, "vote_log.json"),
});

// =============================================================================
// Validation -- fail fast if credentials are missing
// =============================================================================

function validateConfig() {
  if (!CONFIG.username) {
    console.error("[FATAL] HIVE_USERNAME is not set in .env");
    process.exit(1);
  }
  if (!CONFIG.postingKey) {
    console.error("[FATAL] HIVE_POSTING_KEY is not set in .env");
    process.exit(1);
  }
  const hasRules = CONFIG.rules.length > 0;
  const hasTrail = CONFIG.trailAccounts.length > 0;
  if (!hasRules && !hasTrail) {
    console.error(
      "[FATAL] No voting rules in config.json and no trail_accounts configured. " +
      "The bot has nothing to do."
    );
    process.exit(1);
  }
}

// =============================================================================
// dhive Client
// =============================================================================
// dhive.Client wraps the Hive JSON-RPC API.  We pass:
//   - An array of node URLs for automatic failover
//   - A PrivateKey object derived from the WIF posting key
//
// HIVE CONCEPT -- Key Types:
//   Hive accounts have a hierarchy of keys, each granting different permissions:
//     Owner key   -- can change all other keys, recover the account (NEVER use)
//     Active key  -- can transfer funds, power up/down, change settings
//     Posting key -- can ONLY vote, comment, and follow (SAFEST for bots)
//     Memo key    -- encrypts/decrypts private memo messages
//
//   We ONLY ever use the posting key. This means even if the bot is compromised,
//   the attacker cannot steal your funds -- they can only vote and comment.
//
// The PrivateKey is used to sign vote transactions locally before broadcasting.
// Your key NEVER leaves your machine -- only the signed transaction is sent.
// =============================================================================

let client;
let privateKey;

function initClient() {
  client = new dhive.Client(FAILOVER_NODES, {
    // timeout in milliseconds for each RPC call; if exceeded, try next node
    timeout: 15000,
    // how many consecutive failures before an error is thrown upstream
    failoverThreshold: 3,
    // log a message to console when failing over to the next node
    consoleOnFailover: true,
  });

  // dhive.PrivateKey.fromString() parses a WIF (Wallet Import Format) string
  // into a signing key object. WIF strings start with "5" and are base58-encoded.
  privateKey = dhive.PrivateKey.fromString(CONFIG.postingKey);
  log("Client initialised with " + FAILOVER_NODES.length + " failover nodes");
}

// =============================================================================
// State Tracking
// =============================================================================

/** Rolling window of timestamps for votes cast in the last 24h. */
const voteTimestamps = [];

/** Set of "author/permlink" strings already voted on (prevent double-votes). */
const votedPosts = new Set();

/** Pending vote timers (setTimeout handles) -- cancelled on shutdown. */
const pendingTimers = new Set();

/** Flag for graceful shutdown. */
let shuttingDown = false;

// =============================================================================
// Logging
// =============================================================================

function log(msg) {
  const ts = new Date().toISOString();
  console.log(`[${ts}] ${msg}`);
}

function warn(msg) {
  const ts = new Date().toISOString();
  console.warn(`[${ts}] WARN: ${msg}`);
}

function error(msg) {
  const ts = new Date().toISOString();
  console.error(`[${ts}] ERROR: ${msg}`);
}

// =============================================================================
// Vote Audit Log
// =============================================================================
// Every vote the bot casts is appended to a JSON-lines file (one JSON object
// per line).  This provides a permanent audit trail for:
//   - Debugging: see exactly what was voted on and why
//   - Compliance: prove your voting pattern to community reviewers
//   - Analytics: import into a spreadsheet or database for curation analysis
//
// Each entry records the author, permlink, weight, VP/RC at vote time,
// the rule that triggered the vote, and whether it was a trail vote.
// =============================================================================

function appendVoteLog(entry) {
  try {
    const line = JSON.stringify({
      timestamp: new Date().toISOString(),
      ...entry,
    }) + "\n";
    fs.appendFileSync(CONFIG.voteLogPath, line, "utf8");
  } catch (err) {
    warn(`Failed to write vote log: ${err.message}`);
  }
}

// =============================================================================
// HIVE CONCEPT -- Reputation
// =============================================================================
// On-chain reputation is stored as a large raw integer (can be negative).
// The human-readable score (25-75+) is computed with a log10 formula:
//
//   score = (log10(abs(raw_reputation)) - 9) * 9 + 25
//
// New accounts start at 25.  Receiving upvotes on your posts increases it;
// receiving downvotes from accounts with HIGHER reputation decreases it.
// A reputation of ~50 means a reasonably established account.  Most whales
// (large stakeholders) are in the 60-75+ range.
//
// Why filter by reputation?
//   Spam/bot accounts tend to stay below rep 25-30. Filtering them out avoids
//   wasting your voting mana on content that will likely be downvoted.
// =============================================================================

function rawRepToScore(raw) {
  // The API returns reputation as a string (large integer) or number
  const r = typeof raw === "string" ? parseInt(raw, 10) : raw;
  if (r === 0) return 25; // default for brand-new accounts
  const neg = r < 0;
  const absR = Math.abs(r);
  // The formula: (log10(absR) - 9) * 9 + 25, floored at 25
  const score = Math.max(Math.log10(absR) - 9, 0) * 9 + 25;
  return neg ? -score : Math.floor(score * 100) / 100;
}

// =============================================================================
// HIVE CONCEPT -- Resource Credits (RC)
// =============================================================================
// Every Hive account has Resource Credits -- a regenerating "gas" budget that
// is consumed by every on-chain operation (vote, comment, transfer, custom_json,
// claim_account, etc.).
//
// Key facts about RC:
//   - RC regenerates linearly from 0% to 100% over 5 days (432,000 seconds)
//   - Your maximum RC is proportional to your effective Hive Power (HP)
//   - Different operations cost different amounts of RC:
//       * A vote costs very little RC (~0.003% for a typical account)
//       * A comment costs more (~0.5%)
//       * A claim_account costs by far the most
//   - If you run out of RC, you cannot broadcast ANY transaction
//   - You can delegate HP to other accounts to give them more RC
//
// The rc_api returns:
//   - rc_manabar.current_mana   -- raw mana at last update time
//   - rc_manabar.last_update_time -- when current_mana was last written
//   - max_rc                    -- maximum mana when fully regenerated
//
// Because mana regenerates continuously, we must time-adjust current_mana:
//   adjusted = current_mana + (max_rc * elapsed_seconds / 432000)
//   adjusted = min(adjusted, max_rc)   -- cap at 100%
//
// We check RC before every vote and pause if it drops below our threshold.
// This prevents broadcast failures ("not enough RC" errors).
// =============================================================================

async function getRcPercent(username) {
  try {
    // rc_api.find_rc_accounts is a Hive-specific API call (not standard condenser)
    // It returns the raw RC manabar for one or more accounts.
    const rcResult = await client.call("rc_api", "find_rc_accounts", {
      accounts: [username],
    });

    if (!rcResult.rc_accounts || rcResult.rc_accounts.length === 0) {
      warn(`Could not fetch RC for @${username}`);
      return 100; // assume OK if API fails -- don't block voting
    }

    const rc = rcResult.rc_accounts[0];
    const maxRc = BigInt(rc.max_rc);
    if (maxRc === 0n) return 0;

    // Time-adjust the mana for regeneration since last_update_time
    const currentMana = BigInt(rc.rc_manabar.current_mana);
    const lastUpdateTime = rc.rc_manabar.last_update_time;
    const now = Math.floor(Date.now() / 1000);
    const elapsed = BigInt(now - lastUpdateTime);
    const REGEN_TIME = 432000n; // 5 days in seconds

    // Formula: adjusted = current + (max * elapsed / regen_time), capped at max
    let adjusted = currentMana + (maxRc * elapsed) / REGEN_TIME;
    if (adjusted > maxRc) adjusted = maxRc;

    // Convert to percentage with 2 decimal places
    const percent = Number((adjusted * 10000n) / maxRc) / 100;
    return Math.round(percent * 100) / 100;
  } catch (err) {
    warn(`RC check failed: ${err.message}`);
    return 100; // don't block on transient errors
  }
}

// =============================================================================
// HIVE CONCEPT -- Voting Power / Voting Mana
// =============================================================================
// Each Hive account has "voting mana" (historically called "voting power") that
// determines the economic weight (in HP terms) of each vote you cast.
//
// How it works:
//   - Mana regenerates linearly from 0% to 100% over exactly 5 days (432,000s)
//   - That works out to 20% regeneration per day
//   - A 100%-weight vote at full mana costs exactly 2% of your mana
//     (so 50 full-power votes drain you completely in ~2.5 days)
//   - A 50%-weight vote costs ~1%, a 25%-weight vote costs ~0.5%, etc.
//   - Formula: mana_cost = current_mana * vote_weight / 10000
//   - The less mana you have, the weaker (lower $-value) your votes become
//
// Optimal strategy:
//   Keep mana above 80%.  At 80% mana, each vote is worth 80% of its maximum
//   dollar value.  Below 80%, returns diminish because your votes earn less
//   curation reward relative to the mana you spend.
//
//   Casting 10 full-power votes per day = 20% mana spent, 20% regenerated = 80%
//   This is the "sweet spot" that most serious curators target.
//
// The API returns voting_manabar with:
//   - current_mana       -- raw mana value at last_update_time
//   - last_update_time   -- when current_mana was last written to chain
//
// Like RC, we must time-adjust for regeneration since the last update.
// =============================================================================

async function getVotingPower(username) {
  try {
    // database.getAccounts returns an array of account objects
    const [account] = await client.database.getAccounts([username]);
    if (!account) {
      warn(`Account @${username} not found`);
      return 100;
    }

    // Post-HF26, voting mana is in account.voting_manabar
    const manabar = account.voting_manabar;
    const currentMana = BigInt(manabar.current_mana);
    const lastUpdate = manabar.last_update_time;

    // Calculate max mana from effective vesting shares:
    //   effective_vests = vesting_shares + received_vesting_shares - delegated_vesting_shares
    // These are strings like "12345.678901 VESTS" -- we parse the numeric part.
    const vestingShares = parseFloat(String(account.vesting_shares));
    const receivedVests = parseFloat(String(account.received_vesting_shares));
    const delegatedVests = parseFloat(String(account.delegated_vesting_shares));
    const effectiveVests = vestingShares + receivedVests - delegatedVests;

    // Max mana = effective_vests * 1e6 (the manabar uses micro-VESTS)
    const maxMana = BigInt(Math.floor(effectiveVests * 1e6));
    if (maxMana === 0n) return 0;

    // Time-adjust for regeneration since last_update_time
    const now = Math.floor(Date.now() / 1000);
    const lastUpdateUnix =
      typeof lastUpdate === "number"
        ? lastUpdate
        : Math.floor(new Date(lastUpdate + "Z").getTime() / 1000);
    const elapsed = BigInt(Math.max(0, now - lastUpdateUnix));
    const REGEN_TIME = 432000n; // 5 days in seconds

    let adjusted = currentMana + (maxMana * elapsed) / REGEN_TIME;
    if (adjusted > maxMana) adjusted = maxMana;

    const percent = Number((adjusted * 10000n) / maxMana) / 100;
    return Math.round(percent * 100) / 100;
  } catch (err) {
    warn(`Voting power check failed: ${err.message}`);
    return 100;
  }
}

// =============================================================================
// Daily Vote Limiter
// =============================================================================
// We maintain a rolling window of vote timestamps.  Before each vote we prune
// entries older than 24 hours.  If the remaining count >= maxDailyVotes, we
// skip the vote.  This ensures we don't drain mana too fast and keeps the bot
// within the operator's desired voting budget.
//
// Why limit daily votes?
//   - Each vote costs VP (see above).  Unlimited voting = 0% VP = worthless votes.
//   - Hive community norms frown on "spray voting" (mass low-weight votes).
//   - Curation rewards are proportional to vote value, so fewer stronger votes
//     earn more than many weak ones.
// =============================================================================

function canVoteWithinDailyLimit() {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  // Prune old entries (mutating in-place for efficiency)
  while (voteTimestamps.length > 0 && voteTimestamps[0] < cutoff) {
    voteTimestamps.shift();
  }
  return voteTimestamps.length < CONFIG.maxDailyVotes;
}

function recordVote() {
  voteTimestamps.push(Date.now());
}

function votesRemainingToday() {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  while (voteTimestamps.length > 0 && voteTimestamps[0] < cutoff) {
    voteTimestamps.shift();
  }
  return Math.max(0, CONFIG.maxDailyVotes - voteTimestamps.length);
}

// =============================================================================
// Post Filtering -- Rule Engine
// =============================================================================
// The rule engine evaluates each incoming post against the rules in config.json.
// If ANY rule matches, the post is eligible for a vote.  Each rule can specify
// its own vote_weight override; otherwise the default weight is used.
//
// Supported rule types:
//   "tag"            -- match if the post has this tag
//   "author"         -- match if the post's author matches
//   "min_reputation" -- match if the author's rep >= value
//   "min_words"      -- match if the post body has >= value words
//
// On top of rules, blacklist/whitelist act as global overrides:
//   blacklist -- if the author is on this list, NEVER vote (overrides everything)
//   whitelist -- if non-empty, ONLY consider authors on this list
// =============================================================================

/**
 * Check if a post matches our voting criteria.
 *
 * @param {object} op - The "comment" operation body from the blockchain stream.
 *   Fields: author, permlink, parent_author, parent_permlink, title, body, json_metadata
 * @param {number} authorRep - The author's human-readable reputation score.
 * @returns {{ match: boolean, weight: number, rule: string }} - Result with the
 *   matching rule description and the vote weight to use (1-100%).
 *
 * HIVE CONCEPT -- comment vs. post:
 *   On Hive, BOTH posts and comments use the "comment" operation type.
 *   - If parent_author is "" (empty string), it's a root-level POST.
 *   - If parent_author is set, it's a REPLY (comment on someone's post).
 *   We only want root posts, so the caller checks parent_author before this.
 */
function evaluateRules(op, authorRep) {
  const author = op.author.toLowerCase();

  // --- Blacklist check (highest priority -- overrides everything) ---
  if (CONFIG.blacklist.includes(author)) {
    return { match: false, weight: 0, rule: "blacklisted" };
  }

  // --- Whitelist check (if configured, only whitelisted authors proceed) ---
  if (CONFIG.whitelist.length > 0 && !CONFIG.whitelist.includes(author)) {
    return { match: false, weight: 0, rule: "not_whitelisted" };
  }

  // --- Evaluate each rule ---
  const tags = extractTags(op);
  const wordCount = countWords(op.body || "");

  for (const rule of CONFIG.rules) {
    const weight = rule.vote_weight || CONFIG.defaultVoteWeight;

    switch (rule.type) {
      case "tag":
        // Match if any of the post's tags equals the rule's value
        if (tags.includes(rule.value.toLowerCase())) {
          return { match: true, weight, rule: `tag:${rule.value}` };
        }
        break;

      case "author":
        // Match if the post author matches
        if (author === rule.value.toLowerCase()) {
          return { match: true, weight, rule: `author:${rule.value}` };
        }
        break;

      case "min_reputation":
        // Match if the author's reputation meets the threshold
        if (authorRep >= rule.value) {
          return { match: true, weight, rule: `min_reputation:${rule.value}` };
        }
        break;

      case "min_words":
        // Match if the post body has enough words
        if (wordCount >= rule.value) {
          return { match: true, weight, rule: `min_words:${rule.value}` };
        }
        break;

      default:
        warn(`Unknown rule type: ${rule.type}`);
    }
  }

  return { match: false, weight: 0, rule: "no_match" };
}

/**
 * Extract tags from a post's json_metadata.
 *
 * HIVE CONCEPT -- json_metadata:
 *   Each post carries a JSON blob in the json_metadata field.  Frontends
 *   (PeakD, Ecency, Hive.blog) write structured data here, including:
 *     - "tags": an array of tag strings (most important for filtering)
 *     - "app": which frontend created the post (e.g. "peakd/2024.1.1")
 *     - "image": array of image URLs used in the post
 *     - "format": "markdown" or "html"
 *
 *   The parent_permlink of a root post is also its primary (first) tag.
 *   Some posts store tags in json_metadata, others only in parent_permlink.
 *   We check both and deduplicate.
 */
function extractTags(op) {
  const tags = [];
  // parent_permlink is the primary tag/community for root posts
  if (op.parent_permlink) {
    tags.push(op.parent_permlink.toLowerCase());
  }
  try {
    const meta =
      typeof op.json_metadata === "string"
        ? JSON.parse(op.json_metadata)
        : op.json_metadata;
    if (meta && Array.isArray(meta.tags)) {
      for (const t of meta.tags) {
        if (typeof t === "string") tags.push(t.toLowerCase());
      }
    }
  } catch {
    // json_metadata can be empty or malformed -- just use parent_permlink
  }
  return [...new Set(tags)]; // deduplicate
}

/**
 * Count words in a post body.
 *
 * HIVE CONCEPT -- Post body format:
 *   Post bodies are Markdown (with some HTML allowed).  We strip basic Markdown
 *   and HTML syntax before counting words.  This gives a rough word count that
 *   helps filter out low-effort posts (single image, one-liners, etc.).
 */
function countWords(body) {
  // Strip Markdown images: ![alt](url)
  let text = body.replace(/!\[.*?\]\(.*?\)/g, "");
  // Strip HTML tags
  text = text.replace(/<[^>]+>/g, " ");
  // Strip Markdown links: [text](url) -> text
  text = text.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1");
  // Strip Markdown formatting: **, __, ~~, #
  text = text.replace(/[*_~#>`]/g, "");
  // Split on whitespace and filter empty
  const words = text.split(/\s+/).filter((w) => w.length > 0);
  return words.length;
}

// =============================================================================
// Reputation Check
// =============================================================================

async function getAuthorReputation(author) {
  try {
    const [account] = await client.database.getAccounts([author]);
    if (!account) return 25;
    return rawRepToScore(account.reputation);
  } catch (err) {
    warn(`Reputation check failed for @${author}: ${err.message}`);
    return 25; // assume default on error
  }
}

// =============================================================================
// HIVE CONCEPT -- Casting a Vote
// =============================================================================
// The "vote" operation has these fields:
//   - voter:    your account name
//   - author:   the post author's account name
//   - permlink: the post's permlink (URL slug, e.g. "my-first-post")
//   - weight:   vote strength from -10000 to 10000
//                 10000 = 100% upvote
//                  5000 =  50% upvote
//                   100 =   1% upvote
//                     0 = unvote (removes your previous vote)
//                 -5000 =  50% downvote (flag)
//                -10000 = 100% downvote
//
// The vote is signed with your POSTING private key and broadcast to the network.
// Once included in a block (~3 seconds), it takes effect immediately.  You CAN
// change your vote by voting again with a different weight on the same permlink
// (within the 7-day payout window).
//
// HIVE CONCEPT -- Curation Rewards:
//   When a post pays out after 7 days, its total rewards are split:
//     - 50% goes to the post AUTHOR
//     - 50% goes to the CURATORS (voters) proportionally
//
//   Your share of the curation pool depends on:
//     1. The HP-value of your vote (your VP * your HP * weight / 10000)
//     2. When you voted relative to others (earlier = larger share)
//     3. The total votes the post received
//
//   Early voters who discover good content are rewarded most. If you vote first
//   on a post that later gets massive upvotes, you capture a huge curation share.
//   This incentive structure is what makes Hive curation economically interesting
//   and is the entire reason automated curation bots exist.
//
//   The 5-minute "reverse auction" penalty was REMOVED in HF25 (June 2021),
//   so there's no penalty for voting immediately. However, waiting ~5 minutes
//   lets you verify the post isn't spam before committing your mana.
// =============================================================================

async function castVote(author, permlink, weightPercent, reason) {
  const postKey = `${author}/${permlink}`;

  // Prevent double-voting on the same post
  if (votedPosts.has(postKey)) {
    log(`Already voted on ${postKey}, skipping`);
    return false;
  }

  // Daily limit check
  if (!canVoteWithinDailyLimit()) {
    warn(
      `Daily vote limit reached (${CONFIG.maxDailyVotes}). ` +
      `Skipping ${postKey}. Will resume when oldest vote ages out.`
    );
    return false;
  }

  // RC check -- ensure we have enough resource credits to broadcast
  const rc = await getRcPercent(CONFIG.username);
  if (rc < CONFIG.minRcPercent) {
    warn(
      `Resource Credits too low: ${rc}% < ${CONFIG.minRcPercent}%. ` +
      `Skipping ${postKey}. RC regenerates ~20%/day.`
    );
    return false;
  }

  // Voting power check -- block voting if VP too low
  const vp = await getVotingPower(CONFIG.username);
  if (vp < CONFIG.minVpPercent) {
    warn(
      `Voting power too low: ${vp}% < ${CONFIG.minVpPercent}%. ` +
      `Pausing votes to let mana regenerate (~20%/day). Skipping ${postKey}.`
    );
    return false;
  }

  // Convert percentage (1-100) to dhive weight (100-10000)
  // dhive expects weight in basis points: 100% = 10000, 50% = 5000, 1% = 100
  const dhiveWeight = Math.round(Math.max(1, Math.min(100, weightPercent)) * 100);

  // Broadcast the vote
  try {
    log(
      `Casting vote: @${author}/${permlink} | weight: ${weightPercent}% ` +
      `(${dhiveWeight}/10000) | VP: ${vp}% | RC: ${rc}% | reason: ${reason}`
    );

    // client.broadcast.vote() signs the transaction with our posting key
    // and broadcasts it to the connected node. The node validates the signature,
    // checks the account has sufficient RC, and includes it in the next block.
    const result = await client.broadcast.vote(
      {
        voter: CONFIG.username,     // who is voting
        author: author,              // post author
        permlink: permlink,          // post URL slug
        weight: dhiveWeight,         // vote strength in basis points
      },
      privateKey // posting key signs the transaction locally
    );

    // result contains: { id: "tx_hash...", block_num: 12345, ... }
    log(
      `Vote confirmed in block ${result.block_num} | tx: ${result.id} | ` +
      `remaining today: ${votesRemainingToday() - 1}`
    );

    votedPosts.add(postKey);
    recordVote();

    // Log to audit file
    appendVoteLog({
      voter: CONFIG.username,
      author,
      permlink,
      weight_percent: weightPercent,
      dhive_weight: dhiveWeight,
      voting_power: vp,
      resource_credits: rc,
      reason,
      block_num: result.block_num,
      tx_id: result.id,
    });

    return true;
  } catch (err) {
    error(`Vote broadcast failed for ${postKey}: ${err.message}`);
    // Common broadcast errors:
    //   "You have already voted in a similar way" -- duplicate vote
    //   "Voting weight is too small"              -- weight rounds to zero
    //   "Account does not have enough RC"         -- resource credits depleted
    //   "Cannot vote again on this comment"       -- already voted, can't re-vote same weight
    if (err.message && err.message.includes("already voted")) {
      votedPosts.add(postKey); // Mark to avoid retrying
    }

    appendVoteLog({
      voter: CONFIG.username,
      author,
      permlink,
      weight_percent: weightPercent,
      reason,
      error: err.message,
    });

    return false;
  }
}

// =============================================================================
// HIVE CONCEPT -- Curation Window (Vote Delay)
// =============================================================================
// After HF25 (June 2021), the "reverse auction" penalty was removed.  This
// means you receive full curation rewards regardless of when you vote within
// the 7-day payout window.
//
// However, there are still strategic reasons to wait a few minutes:
//
//   1. VERIFICATION: Waiting lets you (or the bot) confirm the post isn't spam,
//      plagiarism, or AI-generated slop that will get downvoted.
//
//   2. CURATION AMPLIFICATION: When others see your vote, they may pile on,
//      increasing the total payout and therefore your curation reward.
//
//   3. RISK MANAGEMENT: Voting too early on a post that gets downvoted by
//      anti-abuse accounts means wasted mana and potentially negative curation.
//
//   4. FRONT-RUNNING: Some large curators wait exactly 5 minutes. By voting
//      at ~4.5 minutes, you position yourself just before the "whale pile-on"
//      and capture maximum early-voter share.
//
// Our delay is configurable via vote_delay_minutes in config.json. The bot
// queues a timer after discovering a matching post, then votes when it fires.
//
// NOTE: The 7-day payout window is absolute. After 7 days, voting on a post
// has zero effect (no rewards, no influence on payout). The blockchain silently
// ignores votes on posts past their payout window.
// =============================================================================

function scheduleVote(author, permlink, postCreatedStr, weightPercent, reason) {
  const postKey = `${author}/${permlink}`;
  if (votedPosts.has(postKey)) return;

  const delayMs = CONFIG.voteDelayMinutes * 60 * 1000;

  // Calculate how old the post already is (the stream can lag behind HEAD)
  const postCreated = new Date(postCreatedStr + "Z").getTime();
  const age = Date.now() - postCreated;
  const remainingDelay = Math.max(0, delayMs - age);

  if (remainingDelay > 0) {
    log(
      `Scheduling vote for @${author}/${permlink} in ` +
      `${Math.round(remainingDelay / 1000)}s (curation delay) | ` +
      `weight: ${weightPercent}% | reason: ${reason}`
    );
  } else {
    log(
      `Post @${author}/${permlink} is already ${Math.round(age / 1000)}s old ` +
      `-- voting immediately | weight: ${weightPercent}% | reason: ${reason}`
    );
  }

  const timer = setTimeout(async () => {
    pendingTimers.delete(timer);
    if (shuttingDown) return;
    await castVote(author, permlink, weightPercent, reason);
  }, remainingDelay);

  pendingTimers.add(timer);
}

// =============================================================================
// HIVE CONCEPT -- Trail Voting
// =============================================================================
// Trail voting (also called "curation trails") means automatically copying
// another account's votes.  When a trailed account votes on a post, your bot
// immediately votes on the same post with your configured trail weight.
//
// Why trail vote?
//   - Passive curation: follow a trusted curator without manual effort
//   - Community support: trail your community's curation account
//   - Curation guilds: coordinate voting power across multiple accounts
//
// Popular curation trail services include hive.vote and leo.voter, but this
// bot implements trailing natively by watching for "vote" operations on-chain.
//
// When we see a vote operation where voter == a trailed account, we schedule
// a vote on the same author/permlink with our trail weight.  Blacklist and
// RC/VP checks still apply -- trailing doesn't bypass safety checks.
//
// We DON'T copy downvotes (negative weight) to avoid accidental flagging.
// =============================================================================

function handleTrailVote(op) {
  // op fields: { voter, author, permlink, weight }
  const voter = op.voter.toLowerCase();

  // Only process votes from accounts we're trailing
  if (!CONFIG.trailAccounts.includes(voter)) return;

  // Skip downvotes -- we only trail upvotes to avoid accidental flagging
  if (op.weight <= 0) {
    log(`Trail: ignoring downvote/unvote by @${voter} (weight: ${op.weight})`);
    return;
  }

  // Blacklist still applies to trail votes
  const author = op.author.toLowerCase();
  if (CONFIG.blacklist.includes(author)) {
    log(`Trail: @${voter} voted on blacklisted @${author}, skipping`);
    return;
  }

  const postKey = `${op.author}/${op.permlink}`;
  if (votedPosts.has(postKey)) {
    log(`Trail: already voted on ${postKey}, skipping`);
    return;
  }

  log(
    `Trail: @${voter} voted ${op.weight / 100}% on @${op.author}/${op.permlink} ` +
    `-- mirroring with ${CONFIG.trailVoteWeight}%`
  );

  // Trail votes use a short delay (30 seconds) rather than the full curation
  // delay, since the trailed account has already done the content evaluation.
  const timer = setTimeout(async () => {
    pendingTimers.delete(timer);
    if (shuttingDown) return;
    await castVote(
      op.author,
      op.permlink,
      CONFIG.trailVoteWeight,
      `trail:${voter}`
    );
  }, 30 * 1000); // 30-second delay for trail votes

  pendingTimers.add(timer);
}

// =============================================================================
// HIVE CONCEPT -- Blockchain Streaming
// =============================================================================
// The Hive blockchain produces a new block every 3 seconds. Each block contains
// zero or more transactions, each containing one or more operations.
//
// There are two streaming modes:
//
//   "irreversible" (BlockchainMode.Irreversible):
//     Only yields blocks confirmed by 2/3+ of witnesses (21 of ~20 active).
//     This adds ~45 seconds of latency but guarantees the block won't be
//     rolled back.  Use for financial operations where certainty matters.
//
//   "latest" (BlockchainMode.Latest):
//     Yields blocks as soon as the connected node receives them from the
//     producing witness.  Near real-time (~3s latency) but there's a tiny
//     chance of a micro-fork reverting the last 1-2 blocks.  For voting,
//     this risk is negligible and the speed advantage is essential for
//     curation window timing.
//
// dhive provides two streaming APIs:
//
//   client.blockchain.getBlockStream(mode):
//     Yields entire blocks (header + all transactions). Useful when you need
//     to process operations in strict block order.
//
//   client.blockchain.getOperationsStream(mode):
//     Yields individual operations one at a time. More convenient when you
//     only care about specific operation types. Each yielded item is:
//       { op: [operation_name, operation_body], timestamp, block_num, ... }
//
//     Common operation types:
//       "comment"     -- new post or reply (check parent_author to distinguish)
//       "vote"        -- an upvote or downvote
//       "transfer"    -- HIVE/HBD token transfer
//       "custom_json" -- app-specific data (Splinterlands, dApps, etc.)
//
// We use getOperationsStream("latest") and watch for:
//   1. "comment" operations (new posts) -- for rule-based voting
//   2. "vote" operations -- for trail voting
// =============================================================================

async function startStream() {
  log("Starting blockchain stream (mode: latest)...");
  log(
    `Rules: ${CONFIG.rules.length} configured | ` +
    `Trail: [${CONFIG.trailAccounts.join(", ") || "none"}] | ` +
    `Blacklist: ${CONFIG.blacklist.length} accounts | ` +
    `Whitelist: ${CONFIG.whitelist.length > 0 ? CONFIG.whitelist.length + " accounts" : "off"} | ` +
    `Weight: ${CONFIG.defaultVoteWeight}% default | ` +
    `Delay: ${CONFIG.voteDelayMinutes}m | ` +
    `Max/day: ${CONFIG.maxDailyVotes} | ` +
    `Min VP: ${CONFIG.minVpPercent}% | ` +
    `Min RC: ${CONFIG.minRcPercent}%`
  );

  while (!shuttingDown) {
    try {
      // getOperationsStream returns an AsyncIterable. We consume it with
      // for-await-of.  If the node connection drops, the loop throws and
      // we catch + reconnect below.
      const stream = client.blockchain.getOperationsStream({
        mode: dhive.BlockchainMode.Latest,
      });

      for await (const operation of stream) {
        if (shuttingDown) break;

        const [opType, opBody] = operation.op;

        // --- Trail voting: watch for "vote" operations ---
        if (opType === "vote" && CONFIG.trailAccounts.length > 0) {
          handleTrailVote(opBody);
          continue;
        }

        // --- Rule-based voting: watch for "comment" operations (new posts) ---
        if (opType !== "comment") continue;

        // HIVE CONCEPT: parent_author === "" means root post (not a reply)
        // Replies have parent_author set to the post they're replying to.
        if (opBody.parent_author !== "") continue;

        // Fetch the author's reputation for rule evaluation
        const authorRep = await getAuthorReputation(opBody.author);

        // Global reputation floor check
        if (authorRep < CONFIG.minReputation) {
          continue; // silently skip low-rep posts
        }

        // Evaluate rules
        const result = evaluateRules(opBody, authorRep);
        if (!result.match) continue;

        // Word count check (global minimum)
        if (CONFIG.minWordCount > 0) {
          const wc = countWords(opBody.body || "");
          if (wc < CONFIG.minWordCount) {
            log(
              `Skipping @${opBody.author}/${opBody.permlink}: ` +
              `${wc} words < minimum ${CONFIG.minWordCount}`
            );
            continue;
          }
        }

        log(
          `Matched post: @${opBody.author}/${opBody.permlink} ` +
          `-- "${opBody.title || "(no title)"}" | ` +
          `rule: ${result.rule} | rep: ${authorRep}`
        );

        // Schedule the vote with curation delay
        const timestamp =
          operation.timestamp || new Date().toISOString().replace("Z", "");
        scheduleVote(
          opBody.author,
          opBody.permlink,
          timestamp,
          result.weight,
          result.rule
        );
      }
    } catch (err) {
      if (shuttingDown) break;
      error(`Stream error: ${err.message}`);
      log("Reconnecting in 10 seconds (dhive will try the next failover node)...");
      await sleep(10000);
    }
  }

  log("Stream stopped.");
}

// =============================================================================
// Graceful Shutdown
// =============================================================================
// On SIGINT (Ctrl+C) or SIGTERM, we:
//   1. Set the shuttingDown flag to break the stream loop
//   2. Cancel all pending vote timers (so no votes fire after shutdown)
//   3. Log session summary
//   4. Let the process exit cleanly
//
// This prevents half-executed votes and orphaned timers.
// =============================================================================

function setupShutdownHandlers() {
  const shutdown = (signal) => {
    if (shuttingDown) return; // prevent double-shutdown from multiple signals
    shuttingDown = true;
    log(`\nReceived ${signal}. Shutting down gracefully...`);

    // Cancel all pending vote timers
    const timerCount = pendingTimers.size;
    for (const timer of pendingTimers) {
      clearTimeout(timer);
    }
    pendingTimers.clear();

    log(`Cancelled ${timerCount} pending vote(s).`);
    log(`Total votes cast this session: ${votedPosts.size}`);
    log(`Vote log: ${CONFIG.voteLogPath}`);

    // Give streams a moment to close, then exit
    setTimeout(() => process.exit(0), 1000);
  };

  // Standard Unix signals
  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));

  // On Windows, also handle the readline close event (Ctrl+C in CMD/PowerShell)
  if (process.platform === "win32") {
    const readline = require("readline");
    const rl = readline.createInterface({ input: process.stdin });
    rl.on("close", () => shutdown("STDIN_CLOSE"));
  }
}

// =============================================================================
// Startup Banner
// =============================================================================

async function printStartupInfo() {
  log("=".repeat(65));
  log("  Hive Voting Bot -- Automated Curation Engine");
  log("=".repeat(65));
  log(`Account:       @${CONFIG.username}`);
  log(`Nodes:         ${FAILOVER_NODES.length} configured (failover enabled)`);
  log(`Rules:         ${CONFIG.rules.length} voting rules loaded`);
  log(`Default weight: ${CONFIG.defaultVoteWeight}%`);
  log(`Min reputation: ${CONFIG.minReputation}`);
  log(`Min word count: ${CONFIG.minWordCount || "off"}`);
  log(`Vote delay:    ${CONFIG.voteDelayMinutes} minutes`);
  log(`Max daily:     ${CONFIG.maxDailyVotes}`);
  log(`Min VP:        ${CONFIG.minVpPercent}%`);
  log(`Min RC:        ${CONFIG.minRcPercent}%`);
  log(`Trail:         [${CONFIG.trailAccounts.join(", ") || "none"}]`);
  log(`Blacklist:     ${CONFIG.blacklist.length} account(s)`);
  log(`Whitelist:     ${CONFIG.whitelist.length > 0 ? CONFIG.whitelist.length + " account(s)" : "off"}`);
  log(`Vote log:      ${CONFIG.voteLogPath}`);

  // Fetch and display live account info
  try {
    const [account] = await client.database.getAccounts([CONFIG.username]);
    if (account) {
      const rep = rawRepToScore(account.reputation);
      const vp = await getVotingPower(CONFIG.username);
      const rc = await getRcPercent(CONFIG.username);
      log("---");
      log(`Reputation:     ${rep}`);
      log(`Voting Power:   ${vp}%`);
      log(`Resource Credits: ${rc}%`);
    } else {
      warn(`Account @${CONFIG.username} not found on chain!`);
    }
  } catch (err) {
    warn(`Could not fetch account info: ${err.message}`);
  }

  log("=".repeat(65));
}

// =============================================================================
// Utility
// =============================================================================

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// =============================================================================
// Exports (for testing)
// =============================================================================
// We export internal functions so the test suite can verify logic without
// needing to connect to the blockchain.

module.exports = {
  rawRepToScore,
  extractTags,
  countWords,
  evaluateRules,
  canVoteWithinDailyLimit,
  votesRemainingToday,
  // Expose internals for test manipulation
  _CONFIG: CONFIG,
  _voteTimestamps: voteTimestamps,
  _votedPosts: votedPosts,
};

// =============================================================================
// Main
// =============================================================================
// Only run the bot if this file is executed directly (not required as a module).
// This allows the test suite to require() and test individual functions.
// =============================================================================

if (require.main === module) {
  async function main() {
    validateConfig();
    initClient();
    setupShutdownHandlers();
    await printStartupInfo();
    await startStream();
  }

  main().catch((err) => {
    error(`Fatal error: ${err.message}`);
    console.error(err);
    process.exit(1);
  });
}
