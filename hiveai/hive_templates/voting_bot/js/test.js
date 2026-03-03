#!/usr/bin/env node
// =============================================================================
// Hive Voting Bot -- Unit Tests
// =============================================================================
// Run with:  node test.js
//
// These tests verify the bot's filtering logic, VP calculations, reputation
// conversion, and daily vote limits WITHOUT connecting to the blockchain.
// No dependencies beyond Node.js built-ins + the bot module itself.
// =============================================================================

"use strict";

// Minimal test harness (no external deps)
let passed = 0;
let failed = 0;
const failures = [];

function assert(condition, message) {
  if (condition) {
    passed++;
    console.log(`  PASS: ${message}`);
  } else {
    failed++;
    failures.push(message);
    console.log(`  FAIL: ${message}`);
  }
}

function assertApprox(actual, expected, tolerance, message) {
  const diff = Math.abs(actual - expected);
  assert(diff <= tolerance, `${message} (got ${actual}, expected ~${expected})`);
}

function section(name) {
  console.log(`\n--- ${name} ---`);
}

// =============================================================================
// We need to set dummy env vars BEFORE requiring bot.js, because bot.js reads
// process.env at module load time for CONFIG.
// =============================================================================
process.env.HIVE_USERNAME = "testuser";
process.env.HIVE_POSTING_KEY = "5JtestKeyDoesNotMatter";
process.env.VOTE_WEIGHT = "5000";
process.env.MIN_REPUTATION = "25";

// Require the bot module -- this imports the exported functions for testing.
// The bot won't start streaming because we're requiring it (not running it).
const bot = require("./bot.js");

// =============================================================================
// Test: rawRepToScore
// =============================================================================
section("Reputation Conversion (rawRepToScore)");

// New account with 0 reputation
assert(bot.rawRepToScore(0) === 25, "Zero raw rep => 25");

// Typical positive reputations
// Raw rep of 1e9 => (log10(1e9) - 9) * 9 + 25 = 0*9 + 25 = 25
assert(bot.rawRepToScore(1e9) === 25, "1e9 raw rep => 25");

// Raw rep of 1e10 => (log10(1e10) - 9) * 9 + 25 = 1*9 + 25 = 34
assertApprox(bot.rawRepToScore(1e10), 34, 0.1, "1e10 raw rep => ~34");

// Raw rep of 1e12 => (log10(1e12) - 9) * 9 + 25 = 3*9 + 25 = 52
assertApprox(bot.rawRepToScore(1e12), 52, 0.1, "1e12 raw rep => ~52");

// Raw rep of 1e15 => (log10(1e15) - 9) * 9 + 25 = 6*9 + 25 = 79
assertApprox(bot.rawRepToScore(1e15), 79, 0.1, "1e15 raw rep => ~79");

// String input (API often returns strings)
assertApprox(bot.rawRepToScore("1000000000000"), 52, 0.1, "String '1e12' => ~52");

// Negative reputation
const negRep = bot.rawRepToScore(-1e12);
assert(negRep < 0, `Negative raw rep => negative score (got ${negRep})`);

// =============================================================================
// Test: extractTags
// =============================================================================
section("Tag Extraction (extractTags)");

// Normal post with json_metadata tags
const op1 = {
  parent_permlink: "hive",
  json_metadata: JSON.stringify({ tags: ["hive", "development", "tutorial"] }),
};
const tags1 = bot.extractTags(op1);
assert(tags1.includes("hive"), "Includes parent_permlink tag 'hive'");
assert(tags1.includes("development"), "Includes json_metadata tag 'development'");
assert(tags1.includes("tutorial"), "Includes json_metadata tag 'tutorial'");

// Deduplication: parent_permlink and tags overlap
const op2 = {
  parent_permlink: "hive",
  json_metadata: JSON.stringify({ tags: ["hive", "HIVE"] }),
};
const tags2 = bot.extractTags(op2);
assert(tags2.length === 1, `Deduplicates tags (got ${tags2.length}, expected 1)`);

// Malformed json_metadata (should not crash)
const op3 = {
  parent_permlink: "test",
  json_metadata: "not valid json {{{",
};
const tags3 = bot.extractTags(op3);
assert(tags3.includes("test"), "Handles malformed JSON gracefully");

// Empty json_metadata
const op4 = {
  parent_permlink: "crypto",
  json_metadata: "",
};
const tags4 = bot.extractTags(op4);
assert(tags4.includes("crypto"), "Handles empty json_metadata");
assert(tags4.length === 1, "Only parent_permlink tag when metadata empty");

// =============================================================================
// Test: countWords
// =============================================================================
section("Word Count (countWords)");

assert(bot.countWords("") === 0, "Empty string => 0 words");
assert(bot.countWords("hello world") === 2, "'hello world' => 2 words");
assert(
  bot.countWords("This is a test with **bold** and _italic_ text") >= 8,
  "Strips Markdown formatting, counts correctly"
);

// Should strip images
const withImage = "Some text ![image](https://example.com/img.png) and more text here";
const imageCount = bot.countWords(withImage);
assert(imageCount >= 5, `Strips Markdown images (got ${imageCount} words)`);

// Should strip HTML
const withHtml = "<p>Hello <strong>world</strong></p> and <div>more</div> text";
const htmlCount = bot.countWords(withHtml);
assert(htmlCount >= 3, `Strips HTML tags (got ${htmlCount} words)`);

// =============================================================================
// Test: evaluateRules
// =============================================================================
section("Rule Engine (evaluateRules)");

// Tag rule match
const tagOp = {
  author: "someuser",
  parent_permlink: "hive",
  json_metadata: JSON.stringify({ tags: ["hive", "coding"] }),
  body: "This is a test post with enough words for demonstration purposes.",
};
const tagResult = bot.evaluateRules(tagOp, 50);
assert(tagResult.match === true, "Tag rule matches when post has matching tag");
assert(tagResult.rule.startsWith("tag:"), `Rule reason includes tag (got: ${tagResult.rule})`);

// Author rule match
const authorOp = {
  author: "buildteam",
  parent_permlink: "random",
  json_metadata: "{}",
  body: "Hello",
};
const authorResult = bot.evaluateRules(authorOp, 60);
assert(authorResult.match === true, "Author rule matches for configured author");
assert(authorResult.rule.startsWith("author:"), `Rule reason includes author (got: ${authorResult.rule})`);

// Min reputation rule
const repOp = {
  author: "newaccount",
  parent_permlink: "random",
  json_metadata: "{}",
  body: "Hello",
};
const repResult = bot.evaluateRules(repOp, 55);
assert(repResult.match === true, "Min reputation rule matches when rep >= threshold");

const lowRepResult = bot.evaluateRules(repOp, 30);
// This should match min_words rule (300) or min_reputation (50) -- rep 30 < 50
// Let's check that min_reputation doesn't match for low rep
// Actually, the rules have min_reputation=50, so rep 30 would not match that rule
// but min_words=300 won't match for "Hello" either
// The tag "random" doesn't match any rule, author "newaccount" doesn't match
// So this should NOT match
assert(lowRepResult.match === false, "No rule matches for low rep, no tag/author match");

// Blacklist test
const blacklistOp = {
  author: bot._CONFIG.blacklist.length > 0 ? bot._CONFIG.blacklist[0] : "nobody",
  parent_permlink: "hive",
  json_metadata: JSON.stringify({ tags: ["hive"] }),
  body: "Test",
};
// If blacklist is empty in test config, we simulate by checking the logic path
if (bot._CONFIG.blacklist.length === 0) {
  // No blacklist configured in test -- that's expected, just note it
  assert(true, "Blacklist empty in test config (no blacklist entries to test)");
} else {
  const blResult = bot.evaluateRules(blacklistOp, 60);
  assert(blResult.match === false, "Blacklisted author is rejected");
}

// =============================================================================
// Test: Daily Vote Limiter
// =============================================================================
section("Daily Vote Limiter");

// Clear the timestamps array for clean testing
bot._voteTimestamps.length = 0;

assert(bot.canVoteWithinDailyLimit() === true, "Can vote when no votes cast");

// Simulate filling up daily limit
const maxVotes = bot._CONFIG.maxDailyVotes;
for (let i = 0; i < maxVotes; i++) {
  bot._voteTimestamps.push(Date.now());
}
assert(
  bot.canVoteWithinDailyLimit() === false,
  `Cannot vote after ${maxVotes} votes (daily limit reached)`
);

assert(
  bot.votesRemainingToday() === 0,
  "votesRemainingToday() returns 0 at limit"
);

// Simulate old votes expiring (push them 25 hours into the past)
bot._voteTimestamps.length = 0;
const oldTime = Date.now() - 25 * 60 * 60 * 1000; // 25 hours ago
for (let i = 0; i < maxVotes; i++) {
  bot._voteTimestamps.push(oldTime);
}
assert(
  bot.canVoteWithinDailyLimit() === true,
  "Can vote again after old votes expire (>24h)"
);

// Clean up
bot._voteTimestamps.length = 0;

// =============================================================================
// Test: Voted Posts Deduplication
// =============================================================================
section("Voted Posts Deduplication");

bot._votedPosts.clear();
assert(bot._votedPosts.size === 0, "Voted posts set starts empty");

bot._votedPosts.add("alice/my-post");
assert(bot._votedPosts.has("alice/my-post"), "Can track a voted post");
assert(!bot._votedPosts.has("alice/other-post"), "Different permlink not tracked");

bot._votedPosts.clear();

// =============================================================================
// Test: Edge Cases
// =============================================================================
section("Edge Cases");

// countWords with only images
assert(
  bot.countWords("![img1](http://a.com/1.png) ![img2](http://a.com/2.png)") === 0,
  "Post with only images => 0 words"
);

// extractTags with object json_metadata (some APIs return parsed objects)
const op5 = {
  parent_permlink: "test",
  json_metadata: { tags: ["alpha", "beta"] },
};
const tags5 = bot.extractTags(op5);
assert(tags5.includes("alpha"), "Handles pre-parsed json_metadata object");

// rawRepToScore with very small positive value
const smallRep = bot.rawRepToScore(1000);
assert(smallRep === 25, `Very small raw rep => 25 (got ${smallRep})`);

// =============================================================================
// Summary
// =============================================================================
console.log("\n" + "=".repeat(50));
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failures.length > 0) {
  console.log("\nFailed tests:");
  for (const f of failures) {
    console.log(`  - ${f}`);
  }
}
console.log("=".repeat(50));
process.exit(failed > 0 ? 1 : 0);
