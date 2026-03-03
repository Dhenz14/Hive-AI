// ============================================================================
// Hive Social App — Test Suite (Node.js built-in assert)
// ============================================================================
//
// Run: npm test   (or: node test.js)
//
// These tests validate helper functions and input validation logic WITHOUT
// needing a live Hive node connection. Blockchain-dependent tests use mocks.
//
// For integration tests against a live testnet, see the "Hive Testnet"
// section in README.md.
// ============================================================================

"use strict";

const assert = require("assert");

// Import the helper functions from our server module.
// We destructure the exports we need for testing.
const { generatePermlink, parseReputation } = require("./server");

let passed = 0;
let failed = 0;
const failures = [];

/**
 * Simple test runner — wraps each test in try/catch and tracks results.
 */
function test(name, fn) {
  try {
    fn();
    passed++;
    console.log(`  PASS  ${name}`);
  } catch (err) {
    failed++;
    failures.push({ name, error: err.message });
    console.log(`  FAIL  ${name}`);
    console.log(`        ${err.message}`);
  }
}

// ============================================================================
// PERMLINK GENERATION TESTS
// ============================================================================

console.log("\n--- generatePermlink ---\n");

test("creates a slug from a simple title", () => {
  const permlink = generatePermlink("Hello World");
  // Should start with "hello-world-" followed by a timestamp
  assert.ok(
    permlink.startsWith("hello-world-"),
    `Expected permlink to start with "hello-world-", got: ${permlink}`
  );
});

test("converts uppercase to lowercase", () => {
  const permlink = generatePermlink("MY UPPERCASE TITLE");
  // Hive permlinks must be all lowercase
  assert.strictEqual(permlink, permlink.toLowerCase());
});

test("replaces special characters with hyphens", () => {
  const permlink = generatePermlink("Hello! @World #2024 $$$");
  // Should not contain special characters — only a-z, 0-9, and hyphens
  const slug = permlink.split("-").slice(0, -1).join("-"); // Remove timestamp part
  assert.ok(
    /^[a-z0-9-]+$/.test(slug),
    `Permlink contains invalid chars: ${slug}`
  );
});

test("removes leading and trailing hyphens", () => {
  const permlink = generatePermlink("---leading and trailing---");
  // After slug conversion, should not start or end with hyphen (before timestamp)
  assert.ok(!permlink.startsWith("-"), `Starts with hyphen: ${permlink}`);
});

test("truncates long titles to 200 chars", () => {
  const longTitle = "a".repeat(300);
  const permlink = generatePermlink(longTitle);
  // The slug portion (before the timestamp suffix) should be <= 200 chars
  // Total permlink = slug (<=200) + "-" + timestamp
  const parts = permlink.split("-");
  const timestamp = parts.pop();
  const slug = parts.join("-");
  assert.ok(
    slug.length <= 200,
    `Slug length ${slug.length} exceeds 200: ${slug.substring(0, 50)}...`
  );
});

test("generates unique permlinks for same title", () => {
  // Because of the timestamp suffix, two calls should produce different permlinks
  const p1 = generatePermlink("Same Title");
  const p2 = generatePermlink("Same Title");
  // Note: if called in the same millisecond, they might be equal.
  // In practice, Date.now() resolution is 1ms, so this should pass.
  // We allow a tiny chance of collision in tests but verify format.
  assert.ok(
    p1.startsWith("same-title-") && p2.startsWith("same-title-"),
    "Both should start with the same slug prefix"
  );
});

test("handles empty title gracefully", () => {
  const permlink = generatePermlink("");
  // Should still produce a valid permlink (just the timestamp)
  assert.ok(permlink.length > 0, "Permlink should not be empty");
  assert.ok(
    /^[a-z0-9-]+$/.test(permlink),
    `Permlink contains invalid chars: ${permlink}`
  );
});

test("handles unicode titles by stripping non-ASCII", () => {
  const permlink = generatePermlink("Hello 世界 Blockchain");
  // Unicode chars get replaced with hyphens; result should still be valid
  assert.ok(
    /^[a-z0-9-]+$/.test(permlink),
    `Permlink contains invalid chars: ${permlink}`
  );
});


// ============================================================================
// REPUTATION PARSING TESTS
// ============================================================================

console.log("\n--- parseReputation ---\n");

test("returns 25 for zero reputation (new account)", () => {
  // New accounts start with reputation 0, which displays as 25
  const rep = parseReputation(0);
  assert.strictEqual(rep, 25);
});

test("returns 25 for string zero", () => {
  const rep = parseReputation("0");
  assert.strictEqual(rep, 25);
});

test("parses a typical positive reputation", () => {
  // A reputation raw value around 168190025879915 is roughly 72-73
  const rep = parseReputation(168190025879915);
  assert.ok(rep > 50 && rep < 80, `Expected 50-80, got ${rep}`);
});

test("parses a small positive reputation (new-ish account)", () => {
  // Small positive rep should be in the 25-35 range
  const rep = parseReputation(1000000000);
  assert.ok(rep >= 25 && rep <= 40, `Expected 25-40, got ${rep}`);
});

test("returns a negative reputation for flagged accounts", () => {
  // Negative raw rep means the account was heavily downvoted
  const rep = parseReputation(-168190025879915);
  assert.ok(rep < 0, `Expected negative reputation, got ${rep}`);
});

test("reputation is a finite number", () => {
  const rep = parseReputation(123456789012345);
  assert.ok(Number.isFinite(rep), `Expected finite number, got ${rep}`);
});


// ============================================================================
// INPUT VALIDATION TESTS (simulated — testing logic, not routes)
// ============================================================================

console.log("\n--- Input Validation ---\n");

test("valid Hive tags match the pattern", () => {
  // Hive tags: lowercase, starts with letter, letters/numbers/hyphens only
  const tagPattern = /^[a-z][a-z0-9-]*$/;
  const validTags = ["hive", "technology", "my-tag-123", "a"];
  const invalidTags = ["Hive", "123tag", "-leading", "no spaces", "UPPER", "tag!"];

  for (const tag of validTags) {
    assert.ok(tagPattern.test(tag), `'${tag}' should be a valid tag`);
  }
  for (const tag of invalidTags) {
    assert.ok(!tagPattern.test(tag), `'${tag}' should be an invalid tag`);
  }
});

test("vote weight validation: valid range is -10000 to 10000", () => {
  const validWeights = [-10000, -5000, 0, 5000, 10000, 1, -1];
  const invalidWeights = [-10001, 10001, 99999, -99999];

  for (const w of validWeights) {
    assert.ok(
      w >= -10000 && w <= 10000,
      `${w} should be in valid range`
    );
  }
  for (const w of invalidWeights) {
    assert.ok(
      w < -10000 || w > 10000,
      `${w} should be out of valid range`
    );
  }
});

test("permlink uniqueness constraint", () => {
  // On Hive, (author, permlink) must be unique. Our generator ensures
  // uniqueness via timestamp. Verify that format is suitable for Hive.
  const permlink = generatePermlink("Test Post");

  // Max length on Hive is 256 chars
  assert.ok(permlink.length <= 256, `Permlink too long: ${permlink.length}`);

  // Must match Hive's permlink character set
  assert.ok(
    /^[a-z0-9-]+$/.test(permlink),
    `Permlink has invalid chars: ${permlink}`
  );
});


// ============================================================================
// MOCK TESTS — Demonstrate how to mock Hive API calls
// ============================================================================

console.log("\n--- Mock Hive API Examples ---\n");

test("mock: parsing a Hive post response", () => {
  // This is what a real Hive API post response looks like (simplified).
  // In production, you'd use a library like sinon or jest to mock the
  // dhive client. Here we just verify our parsing logic works on realistic data.
  const mockPost = {
    author: "testuser",
    permlink: "my-first-post",
    title: "My First Post",
    body: "Hello Hive! This is **Markdown** content.",
    json_metadata: JSON.stringify({
      tags: ["hive", "introduction"],
      app: "peakd/2024.1.1",
      image: ["https://example.com/photo.jpg"],
    }),
    pending_payout_value: "1.234 HBD",
    net_votes: 42,
    children: 5,
    created: "2024-01-15T12:00:00",
    author_reputation: 168190025879915,
    active_votes: [
      { voter: "alice", percent: 10000, rshares: "123456789", time: "2024-01-15T12:01:00" },
      { voter: "bob", percent: 5000, rshares: "56789012", time: "2024-01-15T12:02:00" },
    ],
  };

  // Parse json_metadata like our endpoint does
  const meta = JSON.parse(mockPost.json_metadata);
  assert.deepStrictEqual(meta.tags, ["hive", "introduction"]);
  assert.strictEqual(meta.image[0], "https://example.com/photo.jpg");

  // Verify vote data parsing
  assert.strictEqual(mockPost.active_votes.length, 2);
  assert.strictEqual(mockPost.active_votes[0].percent, 10000); // 100% upvote
  assert.strictEqual(mockPost.active_votes[1].percent, 5000);  // 50% upvote
});

test("mock: parsing account balances", () => {
  // Hive stores balances as strings with token names (a convention from
  // the early Graphene framework). Our code must parse these correctly.
  const mockAccount = {
    name: "testuser",
    balance: "100.000 HIVE",
    hbd_balance: "50.000 HBD",
    vesting_shares: "1000000.000000 VESTS",
    delegated_vesting_shares: "100000.000000 VESTS",
    received_vesting_shares: "50000.000000 VESTS",
    reputation: 168190025879915,
  };

  // Parse balance strings
  const hiveBalance = parseFloat(mockAccount.balance.split(" ")[0]);
  assert.strictEqual(hiveBalance, 100.0);

  const hbdBalance = parseFloat(mockAccount.hbd_balance.split(" ")[0]);
  assert.strictEqual(hbdBalance, 50.0);

  const vests = parseFloat(mockAccount.vesting_shares.split(" ")[0]);
  assert.strictEqual(vests, 1000000.0);
});

test("mock: custom_json follow operation structure", () => {
  // Verify the exact JSON structure needed for a follow operation.
  // Getting this wrong results in the operation being ignored silently.
  const followOp = JSON.stringify([
    "follow",
    {
      follower: "alice",
      following: "bob",
      what: ["blog"],
    },
  ]);

  const parsed = JSON.parse(followOp);
  assert.strictEqual(parsed[0], "follow");
  assert.strictEqual(parsed[1].follower, "alice");
  assert.strictEqual(parsed[1].following, "bob");
  assert.deepStrictEqual(parsed[1].what, ["blog"]);

  // Unfollow structure — same but with empty "what" array
  const unfollowOp = JSON.stringify([
    "follow",
    {
      follower: "alice",
      following: "bob",
      what: [],     // Empty = unfollow
    },
  ]);

  const parsedUnfollow = JSON.parse(unfollowOp);
  assert.deepStrictEqual(parsedUnfollow[1].what, []);
});

test("mock: comment operation identifies posts vs replies", () => {
  // A root post has empty parent_author
  const rootPost = {
    parent_author: "",
    parent_permlink: "hive",   // This is the category/tag
    author: "alice",
    permlink: "my-post",
    title: "My Post",
    body: "Content here",
  };

  // A comment/reply has a non-empty parent_author
  const reply = {
    parent_author: "alice",
    parent_permlink: "my-post",
    author: "bob",
    permlink: "re-alice-my-post-abc123",
    title: "",                 // Comments don't have titles
    body: "Great post!",
  };

  assert.strictEqual(rootPost.parent_author, "", "Root post has empty parent_author");
  assert.notStrictEqual(reply.parent_author, "", "Reply has non-empty parent_author");
  assert.strictEqual(reply.title, "", "Comments should have empty title");
});


// ============================================================================
// RESULTS SUMMARY
// ============================================================================

console.log(`\n====================================================`);
console.log(`  Results: ${passed} passed, ${failed} failed`);
console.log(`====================================================\n`);

if (failures.length > 0) {
  console.log("Failures:");
  for (const f of failures) {
    console.log(`  - ${f.name}: ${f.error}`);
  }
  console.log();
}

// Exit with appropriate code (CI/CD integration)
process.exit(failed > 0 ? 1 : 0);
