#!/usr/bin/env python3
"""
=============================================================================
Hive Voting Bot -- Unit Tests (pytest)
=============================================================================
Run with:
    pytest test_bot.py -v

These tests verify the bot's filtering logic, VP calculations, reputation
conversion, word counting, and daily vote limits WITHOUT connecting to the
blockchain.  No network access is needed.
=============================================================================
"""

import json
import math
import os
import sys
import time

# Set dummy env vars BEFORE importing bot, because bot.py reads them at
# module load time.
os.environ["HIVE_USERNAME"] = "testuser"
os.environ["HIVE_POSTING_KEY"] = "5JtestKeyDoesNotMatter"
os.environ["VOTE_WEIGHT"] = "50.0"
os.environ["MIN_REPUTATION"] = "25"

# Now import the bot module.  Since we're importing (not running __main__),
# the bot won't start streaming -- we can test individual functions.
import bot


# =============================================================================
# Reputation Conversion
# =============================================================================

class TestRawRepToScore:
    """Test the raw reputation integer to human-readable score conversion."""

    def test_zero_rep_returns_25(self):
        """Brand-new accounts with 0 raw reputation should map to 25."""
        assert bot.raw_rep_to_score(0) == 25.0

    def test_one_billion_returns_25(self):
        """1e9 is the minimum positive rep; log10(1e9)=9, so (9-9)*9+25=25."""
        assert bot.raw_rep_to_score(int(1e9)) == 25.0

    def test_ten_billion_returns_approximately_34(self):
        """1e10: (log10(1e10)-9)*9+25 = 1*9+25 = 34."""
        score = bot.raw_rep_to_score(int(1e10))
        assert abs(score - 34.0) < 0.1

    def test_one_trillion_returns_approximately_52(self):
        """1e12: (log10(1e12)-9)*9+25 = 3*9+25 = 52. A well-established account."""
        score = bot.raw_rep_to_score(int(1e12))
        assert abs(score - 52.0) < 0.1

    def test_one_quadrillion_returns_approximately_79(self):
        """1e15: (log10(1e15)-9)*9+25 = 6*9+25 = 79. Whale territory."""
        score = bot.raw_rep_to_score(int(1e15))
        assert abs(score - 79.0) < 0.1

    def test_string_input(self):
        """The API often returns reputation as a string -- handle gracefully."""
        score = bot.raw_rep_to_score("1000000000000")
        assert abs(score - 52.0) < 0.1

    def test_negative_rep(self):
        """Negative raw reputation (flagged accounts) should return negative score."""
        score = bot.raw_rep_to_score(-int(1e12))
        assert score < 0

    def test_small_positive_rep(self):
        """Very small positive values (< 1e9) should still return 25."""
        assert bot.raw_rep_to_score(1000) == 25.0


# =============================================================================
# Tag Extraction
# =============================================================================

class TestExtractTags:
    """Test tag extraction from blockchain comment operations."""

    def test_normal_post_with_json_metadata(self):
        """Should extract tags from both parent_permlink and json_metadata."""
        op = {
            "parent_permlink": "hive",
            "json_metadata": json.dumps({"tags": ["hive", "development", "tutorial"]}),
        }
        tags = bot.extract_tags(op)
        assert "hive" in tags
        assert "development" in tags
        assert "tutorial" in tags

    def test_deduplication(self):
        """Tags appearing in both parent_permlink and json_metadata are deduplicated."""
        op = {
            "parent_permlink": "hive",
            "json_metadata": json.dumps({"tags": ["hive", "HIVE"]}),
        }
        tags = bot.extract_tags(op)
        # "hive" appears in parent_permlink and twice in tags (case-insensitive)
        assert tags.count("hive") == 1

    def test_malformed_json(self):
        """Malformed json_metadata should not crash -- just use parent_permlink."""
        op = {
            "parent_permlink": "test",
            "json_metadata": "not valid json {{{",
        }
        tags = bot.extract_tags(op)
        assert "test" in tags

    def test_empty_json_metadata(self):
        """Empty json_metadata string should return only parent_permlink tag."""
        op = {
            "parent_permlink": "crypto",
            "json_metadata": "",
        }
        tags = bot.extract_tags(op)
        assert tags == ["crypto"]

    def test_dict_json_metadata(self):
        """Some APIs return json_metadata as a pre-parsed dict, not a string."""
        op = {
            "parent_permlink": "test",
            "json_metadata": {"tags": ["alpha", "beta"]},
        }
        tags = bot.extract_tags(op)
        assert "alpha" in tags
        assert "beta" in tags
        assert "test" in tags

    def test_no_parent_permlink(self):
        """Handle missing parent_permlink gracefully."""
        op = {
            "json_metadata": json.dumps({"tags": ["hello"]}),
        }
        tags = bot.extract_tags(op)
        assert "hello" in tags

    def test_tags_are_lowercased(self):
        """All tags should be lowercased for consistent matching."""
        op = {
            "parent_permlink": "Hive",
            "json_metadata": json.dumps({"tags": ["DEVELOPMENT"]}),
        }
        tags = bot.extract_tags(op)
        assert "hive" in tags
        assert "development" in tags
        assert "DEVELOPMENT" not in tags


# =============================================================================
# Word Counting
# =============================================================================

class TestCountWords:
    """Test word counting with Markdown/HTML stripping."""

    def test_empty_string(self):
        assert bot.count_words("") == 0

    def test_simple_text(self):
        assert bot.count_words("hello world") == 2

    def test_strips_markdown_bold_italic(self):
        """Markdown formatting characters should be stripped before counting."""
        count = bot.count_words("This is **bold** and _italic_ text")
        assert count >= 5  # "This", "is", "bold", "and", "italic", "text"

    def test_strips_images(self):
        """Markdown images should be completely removed."""
        text = "Some text ![image](https://example.com/img.png) and more text here"
        count = bot.count_words(text)
        assert count >= 5

    def test_strips_html_tags(self):
        """HTML tags should be removed, leaving only their text content."""
        text = "<p>Hello <strong>world</strong></p> and <div>more</div> text"
        count = bot.count_words(text)
        assert count >= 3

    def test_strips_markdown_links(self):
        """Markdown links [text](url) should keep text, remove url."""
        text = "Click [this link](https://example.com) for info"
        count = bot.count_words(text)
        assert count >= 4  # "Click", "this", "link", "for", "info"

    def test_image_only_post(self):
        """A post with only images should have 0 words."""
        text = "![img1](http://a.com/1.png) ![img2](http://a.com/2.png)"
        assert bot.count_words(text) == 0

    def test_multiple_whitespace(self):
        """Multiple whitespace characters should not create phantom words."""
        assert bot.count_words("  hello   world  ") == 2


# =============================================================================
# Rule Engine
# =============================================================================

class TestEvaluateRules:
    """Test the rule engine that matches posts to voting rules."""

    def test_tag_rule_matches(self):
        """A post with a matching tag should trigger the tag rule."""
        op = {
            "author": "someuser",
            "parent_permlink": "hive",
            "json_metadata": json.dumps({"tags": ["hive", "coding"]}),
            "body": "This is a test post with enough words.",
        }
        result = bot.evaluate_rules(op, 50)
        assert result["match"] is True
        assert result["rule"].startswith("tag:")

    def test_author_rule_matches(self):
        """A post by a configured author should trigger the author rule."""
        op = {
            "author": "buildteam",
            "parent_permlink": "random",
            "json_metadata": "{}",
            "body": "Hello",
        }
        result = bot.evaluate_rules(op, 60)
        assert result["match"] is True
        assert result["rule"].startswith("author:")

    def test_min_reputation_rule_matches(self):
        """A post by an author with sufficient rep should match min_reputation."""
        op = {
            "author": "established_user",
            "parent_permlink": "random",
            "json_metadata": "{}",
            "body": "Hello",
        }
        result = bot.evaluate_rules(op, 55)
        assert result["match"] is True
        assert "min_reputation" in result["rule"]

    def test_low_rep_no_match(self):
        """A post that doesn't match any rule should return match=False."""
        op = {
            "author": "newaccount",
            "parent_permlink": "random_tag_no_match",
            "json_metadata": "{}",
            "body": "Hello",
        }
        # rep 30 < 50 (min_reputation rule), no tag/author match, body too short
        result = bot.evaluate_rules(op, 30)
        assert result["match"] is False

    def test_blacklist_blocks_vote(self):
        """A blacklisted author should never match, even if rules would allow it."""
        # Temporarily add to blacklist
        original_blacklist = bot.CONFIG.blacklist[:]
        bot.CONFIG.blacklist.append("spammer")
        try:
            op = {
                "author": "spammer",
                "parent_permlink": "hive",
                "json_metadata": json.dumps({"tags": ["hive"]}),
                "body": "This is spam",
            }
            result = bot.evaluate_rules(op, 60)
            assert result["match"] is False
            assert result["rule"] == "blacklisted"
        finally:
            bot.CONFIG.blacklist = original_blacklist

    def test_whitelist_filters(self):
        """If whitelist is set, only whitelisted authors should match."""
        original_whitelist = bot.CONFIG.whitelist[:]
        bot.CONFIG.whitelist = ["trusted_author"]
        try:
            # Non-whitelisted author
            op = {
                "author": "random_person",
                "parent_permlink": "hive",
                "json_metadata": json.dumps({"tags": ["hive"]}),
                "body": "Hello world",
            }
            result = bot.evaluate_rules(op, 60)
            assert result["match"] is False
            assert result["rule"] == "not_whitelisted"

            # Whitelisted author
            op["author"] = "trusted_author"
            result = bot.evaluate_rules(op, 60)
            assert result["match"] is True
        finally:
            bot.CONFIG.whitelist = original_whitelist

    def test_rule_weight_override(self):
        """Each rule can specify its own vote_weight that overrides the default."""
        op = {
            "author": "buildteam",
            "parent_permlink": "random",
            "json_metadata": "{}",
            "body": "Hello",
        }
        result = bot.evaluate_rules(op, 60)
        # The "author: buildteam" rule in config.example.json has vote_weight: 100
        assert result["match"] is True
        assert result["weight"] == 100

    def test_case_insensitive_author(self):
        """Author matching should be case-insensitive."""
        op = {
            "author": "BuildTeam",
            "parent_permlink": "random",
            "json_metadata": "{}",
            "body": "Hello",
        }
        result = bot.evaluate_rules(op, 60)
        assert result["match"] is True


# =============================================================================
# Daily Vote Limiter
# =============================================================================

class TestDailyVoteLimit:
    """Test the 24-hour rolling vote window."""

    def setup_method(self):
        """Clear vote timestamps before each test."""
        bot.vote_timestamps.clear()

    def test_can_vote_when_empty(self):
        """With no votes cast, voting should be allowed."""
        assert bot.can_vote_within_daily_limit() is True

    def test_blocks_at_limit(self):
        """After max_daily_votes, further voting should be blocked."""
        max_votes = bot.CONFIG.max_daily_votes
        for _ in range(max_votes):
            bot.vote_timestamps.append(time.time())

        assert bot.can_vote_within_daily_limit() is False

    def test_votes_remaining_zero_at_limit(self):
        """votes_remaining_today should return 0 when at limit."""
        max_votes = bot.CONFIG.max_daily_votes
        for _ in range(max_votes):
            bot.vote_timestamps.append(time.time())

        assert bot.votes_remaining_today() == 0

    def test_old_votes_expire(self):
        """Votes older than 24 hours should be pruned and no longer count."""
        max_votes = bot.CONFIG.max_daily_votes
        old_time = time.time() - 25 * 3600  # 25 hours ago
        for _ in range(max_votes):
            bot.vote_timestamps.append(old_time)

        assert bot.can_vote_within_daily_limit() is True

    def test_votes_remaining_accurate(self):
        """votes_remaining_today should correctly count remaining votes."""
        bot.vote_timestamps.append(time.time())
        bot.vote_timestamps.append(time.time())
        expected = bot.CONFIG.max_daily_votes - 2
        assert bot.votes_remaining_today() == expected

    def test_record_vote_increments(self):
        """record_vote should add a timestamp to the window."""
        before = len(bot.vote_timestamps)
        bot.record_vote()
        assert len(bot.vote_timestamps) == before + 1

    def teardown_method(self):
        """Clean up after each test."""
        bot.vote_timestamps.clear()


# =============================================================================
# Voted Posts Deduplication
# =============================================================================

class TestVotedPosts:
    """Test the voted posts tracking set."""

    def setup_method(self):
        bot.voted_posts.clear()

    def test_starts_empty(self):
        assert len(bot.voted_posts) == 0

    def test_tracks_voted_post(self):
        bot.voted_posts.add("alice/my-post")
        assert "alice/my-post" in bot.voted_posts

    def test_different_permlink_not_tracked(self):
        bot.voted_posts.add("alice/my-post")
        assert "alice/other-post" not in bot.voted_posts

    def test_different_author_same_permlink(self):
        bot.voted_posts.add("alice/my-post")
        assert "bob/my-post" not in bot.voted_posts

    def teardown_method(self):
        bot.voted_posts.clear()


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test various edge cases and boundary conditions."""

    def test_count_words_only_formatting(self):
        """A body with only Markdown formatting and no real words."""
        assert bot.count_words("**") == 0
        assert bot.count_words("# ") == 0

    def test_extract_tags_none_json_metadata(self):
        """Handle None json_metadata gracefully."""
        op = {"parent_permlink": "test", "json_metadata": None}
        tags = bot.extract_tags(op)
        assert "test" in tags

    def test_evaluate_rules_empty_author(self):
        """Handle empty author string."""
        op = {
            "author": "",
            "parent_permlink": "hive",
            "json_metadata": json.dumps({"tags": ["hive"]}),
            "body": "Test",
        }
        result = bot.evaluate_rules(op, 25)
        # Should still match the tag rule
        assert result["match"] is True

    def test_raw_rep_to_score_integer_type(self):
        """raw_rep_to_score should handle both int and str inputs."""
        int_result = bot.raw_rep_to_score(int(1e12))
        str_result = bot.raw_rep_to_score(str(int(1e12)))
        assert abs(int_result - str_result) < 0.01

    def test_count_words_mixed_content(self):
        """A realistic post body with mixed Markdown content."""
        body = """
# My Post Title

This is a paragraph with **bold** and *italic* text.

![banner](https://example.com/banner.png)

Here is [a link](https://hive.blog) to the main site.

<center>Some centered text</center>

> A blockquote with wisdom

1. First item
2. Second item
3. Third item
"""
        count = bot.count_words(body)
        assert count > 10  # should have at least 10 real words


# =============================================================================
# Config Validation
# =============================================================================

class TestConfig:
    """Test configuration loading and defaults."""

    def test_username_loaded(self):
        """Username should be loaded from env."""
        assert bot.CONFIG.username == "testuser"

    def test_default_vote_weight(self):
        """Default vote weight should be a reasonable value."""
        assert 1 <= bot.CONFIG.default_vote_weight <= 100

    def test_max_daily_votes_positive(self):
        """max_daily_votes should be a positive integer."""
        assert bot.CONFIG.max_daily_votes > 0

    def test_min_vp_percent_range(self):
        """min_vp_percent should be between 0 and 100."""
        assert 0 <= bot.CONFIG.min_vp_percent <= 100

    def test_min_rc_percent_range(self):
        """min_rc_percent should be between 0 and 100."""
        assert 0 <= bot.CONFIG.min_rc_percent <= 100

    def test_rules_is_list(self):
        """Rules should be a list."""
        assert isinstance(bot.CONFIG.rules, list)

    def test_blacklist_is_list(self):
        """Blacklist should be a list."""
        assert isinstance(bot.CONFIG.blacklist, list)

    def test_whitelist_is_list(self):
        """Whitelist should be a list."""
        assert isinstance(bot.CONFIG.whitelist, list)

    def test_trail_accounts_is_list(self):
        """Trail accounts should be a list."""
        assert isinstance(bot.CONFIG.trail_accounts, list)
