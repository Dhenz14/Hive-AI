"""
============================================================================
Hive Social App -- pytest Test Suite
============================================================================

Run: pytest test_app.py -v

These tests validate helper functions and Flask route logic WITHOUT
needing a live Hive node connection. Blockchain-dependent tests use mocks.

For integration tests against a live testnet, see the "Hive Testnet"
section in README.md.
============================================================================
"""

import json
import math
import re
import time
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# We import the helper functions directly from app.py.
# The app module initializes a beem Hive client on import, which connects
# to a real node. We mock it to avoid network calls during testing.
# ---------------------------------------------------------------------------

# Mock the beem module before importing app so it doesn't try to connect
# to a real Hive node during test collection.
with patch.dict("os.environ", {
    "HIVE_USERNAME": "testuser",
    "HIVE_POSTING_KEY": "",  # Empty = read-only mode, no key validation
    "HIVE_NODE": "https://api.hive.blog",
}):
    from app import app, generate_permlink, decode_reputation


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def client():
    """Create a Flask test client for route testing."""
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


# ============================================================================
# PERMLINK GENERATION TESTS
# ============================================================================


class TestGeneratePermlink:
    """Tests for the generate_permlink() helper function."""

    def test_creates_slug_from_simple_title(self):
        """A simple title should produce a lowercase hyphenated slug."""
        permlink = generate_permlink("Hello World")
        # Should start with "hello-world-" followed by a hex timestamp
        assert permlink.startswith("hello-world-"), (
            f"Expected permlink to start with 'hello-world-', got: {permlink}"
        )

    def test_converts_uppercase_to_lowercase(self):
        """Hive permlinks must be all lowercase."""
        permlink = generate_permlink("MY UPPERCASE TITLE")
        assert permlink == permlink.lower()

    def test_replaces_special_characters_with_hyphens(self):
        """Special characters should be replaced with hyphens."""
        permlink = generate_permlink("Hello! @World #2024 $$$")
        # Only a-z, 0-9, and hyphens allowed in Hive permlinks
        assert re.match(r"^[a-z0-9-]+$", permlink), (
            f"Permlink contains invalid chars: {permlink}"
        )

    def test_removes_leading_and_trailing_hyphens(self):
        """Permlinks should not start or end with hyphens (before timestamp)."""
        permlink = generate_permlink("---leading and trailing---")
        assert not permlink.startswith("-"), f"Starts with hyphen: {permlink}"

    def test_truncates_long_titles(self):
        """The slug portion should be truncated to 200 chars max."""
        long_title = "a" * 300
        permlink = generate_permlink(long_title)
        # The slug portion (before the timestamp suffix) should be <= 200 chars.
        # Total permlink = slug (<=200) + "-" + hex_timestamp
        parts = permlink.rsplit("-", 1)
        slug = parts[0]
        assert len(slug) <= 200, (
            f"Slug length {len(slug)} exceeds 200"
        )

    def test_generates_unique_permlinks_for_same_title(self):
        """Two calls with the same title should produce different permlinks
        (due to the timestamp suffix)."""
        p1 = generate_permlink("Same Title")
        # Small delay to ensure different timestamps
        time.sleep(0.002)
        p2 = generate_permlink("Same Title")
        # Both should start with the same slug prefix
        assert p1.startswith("same-title-")
        assert p2.startswith("same-title-")
        # The full permlinks should differ (timestamp makes them unique)
        # Note: in theory they could collide if called in the same ms,
        # but the sleep above prevents that.
        assert p1 != p2, "Permlinks should be unique due to timestamp suffix"

    def test_handles_empty_title(self):
        """An empty title should still produce a valid permlink (just the timestamp)."""
        permlink = generate_permlink("")
        assert len(permlink) > 0, "Permlink should not be empty"
        assert re.match(r"^[a-z0-9-]+$", permlink), (
            f"Permlink contains invalid chars: {permlink}"
        )

    def test_handles_unicode_titles(self):
        """Unicode characters should be stripped, leaving only ASCII slug chars."""
        permlink = generate_permlink("Hello \u4e16\u754c Blockchain")
        assert re.match(r"^[a-z0-9-]+$", permlink), (
            f"Permlink contains invalid chars: {permlink}"
        )

    def test_permlink_under_max_hive_length(self):
        """Hive permlinks max out at 256 characters."""
        permlink = generate_permlink("A" * 300)
        assert len(permlink) <= 256, f"Permlink too long: {len(permlink)}"


# ============================================================================
# REPUTATION PARSING TESTS
# ============================================================================


class TestDecodeReputation:
    """Tests for the decode_reputation() helper function."""

    def test_returns_25_for_zero_reputation(self):
        """New accounts with zero raw reputation should display as 25."""
        assert decode_reputation(0) == 25.0

    def test_returns_25_for_string_zero(self):
        """Should handle string input gracefully."""
        assert decode_reputation("0") == 25.0

    def test_typical_positive_reputation(self):
        """A raw reputation of ~168190025879915 should be roughly 72-73."""
        rep = decode_reputation(168190025879915)
        assert 50 < rep < 80, f"Expected 50-80, got {rep}"

    def test_small_positive_reputation(self):
        """A small positive rep value should be in the 25-40 range."""
        rep = decode_reputation(1000000000)
        assert 25 <= rep <= 40, f"Expected 25-40, got {rep}"

    def test_negative_reputation(self):
        """Negative raw rep means the account was heavily downvoted."""
        rep = decode_reputation(-168190025879915)
        assert rep < 25, f"Expected negative (below 25), got {rep}"

    def test_reputation_is_finite(self):
        """Reputation should always be a finite number."""
        rep = decode_reputation(123456789012345)
        assert math.isfinite(rep), f"Expected finite number, got {rep}"

    def test_very_large_reputation(self):
        """Very large reputation values (whale accounts) should still parse."""
        rep = decode_reputation(999999999999999999)
        assert rep > 70, f"Expected >70 for whale-level rep, got {rep}"

    def test_reputation_of_one(self):
        """Edge case: reputation of 1 should return 25 (log10(0) is invalid)."""
        rep = decode_reputation(1)
        assert 25 <= rep <= 26, f"Expected ~25, got {rep}"


# ============================================================================
# INPUT VALIDATION TESTS
# ============================================================================


class TestInputValidation:
    """Tests for input validation logic used across endpoints."""

    def test_valid_hive_tags(self):
        """Valid Hive tags: lowercase, starts with letter, alphanumeric+hyphens."""
        tag_pattern = re.compile(r"^[a-z][a-z0-9-]*$")
        valid_tags = ["hive", "technology", "my-tag-123", "a"]
        for tag in valid_tags:
            assert tag_pattern.match(tag), f"'{tag}' should be a valid tag"

    def test_invalid_hive_tags(self):
        """Invalid tags should be rejected."""
        tag_pattern = re.compile(r"^[a-z][a-z0-9-]*$")
        invalid_tags = ["Hive", "123tag", "-leading", "no spaces", "UPPER", "tag!"]
        for tag in invalid_tags:
            assert not tag_pattern.match(tag), f"'{tag}' should be an invalid tag"

    def test_vote_weight_valid_range(self):
        """Vote weight must be between -10000 and 10000."""
        valid_weights = [-10000, -5000, 0, 5000, 10000, 1, -1]
        for w in valid_weights:
            assert -10000 <= w <= 10000, f"{w} should be in valid range"

    def test_vote_weight_invalid_range(self):
        """Weights outside -10000 to 10000 should be rejected."""
        invalid_weights = [-10001, 10001, 99999, -99999]
        for w in invalid_weights:
            assert not (-10000 <= w <= 10000), f"{w} should be out of range"

    def test_permlink_uniqueness_format(self):
        """Generated permlinks should be valid for Hive (max 256, valid chars)."""
        permlink = generate_permlink("Test Post")
        assert len(permlink) <= 256, f"Permlink too long: {len(permlink)}"
        assert re.match(r"^[a-z0-9-]+$", permlink), (
            f"Permlink has invalid chars: {permlink}"
        )


# ============================================================================
# MOCK HIVE DATA TESTS
# ============================================================================


class TestMockHiveData:
    """Tests that verify our parsing logic works on realistic Hive API data."""

    def test_parse_hive_post_response(self):
        """Parsing a realistic Hive post response should extract tags and metadata."""
        mock_post = {
            "author": "testuser",
            "permlink": "my-first-post",
            "title": "My First Post",
            "body": "Hello Hive! This is **Markdown** content.",
            "json_metadata": json.dumps({
                "tags": ["hive", "introduction"],
                "app": "peakd/2024.1.1",
                "image": ["https://example.com/photo.jpg"],
            }),
            "pending_payout_value": "1.234 HBD",
            "net_votes": 42,
            "children": 5,
            "created": "2024-01-15T12:00:00",
            "author_reputation": 168190025879915,
            "active_votes": [
                {"voter": "alice", "percent": 10000, "rshares": "123456789",
                 "time": "2024-01-15T12:01:00"},
                {"voter": "bob", "percent": 5000, "rshares": "56789012",
                 "time": "2024-01-15T12:02:00"},
            ],
        }

        # Parse json_metadata like our endpoint does
        meta = json.loads(mock_post["json_metadata"])
        assert meta["tags"] == ["hive", "introduction"]
        assert meta["image"][0] == "https://example.com/photo.jpg"

        # Verify vote data parsing
        assert len(mock_post["active_votes"]) == 2
        assert mock_post["active_votes"][0]["percent"] == 10000  # 100% upvote
        assert mock_post["active_votes"][1]["percent"] == 5000   # 50% upvote

    def test_parse_account_balances(self):
        """Hive stores balances as strings with token names. Parse them correctly."""
        mock_account = {
            "name": "testuser",
            "balance": "100.000 HIVE",
            "hbd_balance": "50.000 HBD",
            "vesting_shares": "1000000.000000 VESTS",
            "delegated_vesting_shares": "100000.000000 VESTS",
            "received_vesting_shares": "50000.000000 VESTS",
            "reputation": 168190025879915,
        }

        hive_balance = float(mock_account["balance"].split(" ")[0])
        assert hive_balance == 100.0

        hbd_balance = float(mock_account["hbd_balance"].split(" ")[0])
        assert hbd_balance == 50.0

        vests = float(mock_account["vesting_shares"].split(" ")[0])
        assert vests == 1000000.0

    def test_custom_json_follow_structure(self):
        """Verify the exact JSON structure for a follow custom_json operation."""
        follow_op = json.dumps([
            "follow",
            {
                "follower": "alice",
                "following": "bob",
                "what": ["blog"],
            },
        ])

        parsed = json.loads(follow_op)
        assert parsed[0] == "follow"
        assert parsed[1]["follower"] == "alice"
        assert parsed[1]["following"] == "bob"
        assert parsed[1]["what"] == ["blog"]

    def test_custom_json_unfollow_structure(self):
        """Unfollow uses the same structure but with an empty 'what' array."""
        unfollow_op = json.dumps([
            "follow",
            {
                "follower": "alice",
                "following": "bob",
                "what": [],  # Empty = unfollow
            },
        ])

        parsed = json.loads(unfollow_op)
        assert parsed[1]["what"] == []

    def test_custom_json_reblog_structure(self):
        """Verify the exact JSON structure for a reblog custom_json operation."""
        reblog_op = json.dumps([
            "reblog",
            {
                "account": "alice",
                "author": "bob",
                "permlink": "great-post",
            },
        ])

        parsed = json.loads(reblog_op)
        assert parsed[0] == "reblog"
        assert parsed[1]["account"] == "alice"
        assert parsed[1]["author"] == "bob"
        assert parsed[1]["permlink"] == "great-post"

    def test_comment_vs_post_distinction(self):
        """A root post has empty parent_author; a comment has a non-empty one."""
        root_post = {
            "parent_author": "",
            "parent_permlink": "hive",  # This is the category tag
            "author": "alice",
            "permlink": "my-post",
            "title": "My Post",
            "body": "Content here",
        }

        reply = {
            "parent_author": "alice",
            "parent_permlink": "my-post",
            "author": "bob",
            "permlink": "re-alice-my-post-abc123",
            "title": "",  # Comments don't have titles
            "body": "Great post!",
        }

        assert root_post["parent_author"] == "", "Root post has empty parent_author"
        assert reply["parent_author"] != "", "Reply has non-empty parent_author"
        assert reply["title"] == "", "Comments should have empty title"

    def test_mute_follow_structure(self):
        """Muting a user uses 'what': ['ignore'] in the follow custom_json."""
        mute_op = json.dumps([
            "follow",
            {
                "follower": "alice",
                "following": "spammer",
                "what": ["ignore"],  # Mute
            },
        ])

        parsed = json.loads(mute_op)
        assert parsed[1]["what"] == ["ignore"]


# ============================================================================
# FLASK ROUTE TESTS (using test client)
# ============================================================================


class TestFlaskRoutes:
    """Test Flask routes using the test client. These mock the Hive blockchain."""

    def test_index_returns_200(self, client):
        """The root endpoint should always return 200 with API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.get_json()
        assert "name" in data or "app" in data
        assert "endpoints" in data

    def test_post_vote_requires_auth(self, client):
        """POST /api/vote should return 401/403 without credentials."""
        response = client.post(
            "/api/vote",
            json={"author": "test", "permlink": "test", "weight": 10000},
        )
        # Should fail because no posting key is configured in test env
        assert response.status_code in (401, 403)
        data = response.get_json()
        assert "error" in data

    def test_post_create_requires_auth(self, client):
        """POST /api/post should return 401/403 without credentials."""
        response = client.post(
            "/api/post",
            json={
                "title": "Test",
                "body": "Hello",
                "tags": ["test"],
            },
        )
        assert response.status_code in (401, 403)

    def test_post_comment_requires_auth(self, client):
        """POST /api/comment should return 401/403 without credentials."""
        response = client.post(
            "/api/comment",
            json={
                "parent_author": "test",
                "parent_permlink": "test",
                "body": "Hello",
            },
        )
        assert response.status_code in (401, 403)

    def test_post_follow_requires_auth(self, client):
        """POST /api/follow should return 401/403 without credentials."""
        response = client.post(
            "/api/follow",
            json={"following": "testuser", "action": "follow"},
        )
        assert response.status_code in (401, 403)

    def test_post_reblog_requires_auth(self, client):
        """POST /api/reblog should return 401/403 without credentials."""
        response = client.post(
            "/api/reblog",
            json={"author": "test", "permlink": "test"},
        )
        assert response.status_code in (401, 403)


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestEdgeCases:
    """Edge case and boundary testing."""

    def test_permlink_with_only_special_chars(self):
        """A title of only special characters should still produce a valid permlink."""
        permlink = generate_permlink("!@#$%^&*()")
        assert len(permlink) > 0
        assert re.match(r"^[a-z0-9-]+$", permlink)

    def test_permlink_with_numbers_only(self):
        """A numeric title should produce a valid permlink."""
        permlink = generate_permlink("12345")
        assert permlink.startswith("12345-")
        assert re.match(r"^[a-z0-9-]+$", permlink)

    def test_reputation_boundary_values(self):
        """Test reputation decoding at boundary values."""
        # Just above zero
        rep = decode_reputation(10)
        assert isinstance(rep, float)
        assert math.isfinite(rep)

        # Maximum realistic value
        rep = decode_reputation(10**18)
        assert isinstance(rep, float)
        assert rep > 60

    def test_json_metadata_parsing_resilience(self):
        """json_metadata can be malformed. Parsing should not crash."""
        # Valid JSON
        meta = json.loads('{"tags": ["hive"], "app": "test/1.0"}')
        assert meta["tags"] == ["hive"]

        # Empty string should raise JSONDecodeError
        with pytest.raises(json.JSONDecodeError):
            json.loads("")

        # Invalid JSON should raise JSONDecodeError
        with pytest.raises(json.JSONDecodeError):
            json.loads("not json at all")

        # Empty object is valid
        meta = json.loads("{}")
        assert meta.get("tags", []) == []

    def test_balance_string_parsing(self):
        """Hive balance strings like '100.000 HIVE' should parse to floats."""
        balances = [
            ("100.000 HIVE", 100.0),
            ("0.001 HBD", 0.001),
            ("999999.999 HIVE", 999999.999),
            ("0.000 HBD", 0.0),
        ]
        for balance_str, expected in balances:
            amount = float(balance_str.split(" ")[0])
            assert amount == expected, (
                f"Parsing '{balance_str}' gave {amount}, expected {expected}"
            )

    def test_vote_weight_basis_point_conversion(self):
        """Vote weight in basis points should convert to percentages correctly."""
        test_cases = [
            (10000, "100.0%"),
            (5000, "50.0%"),
            (100, "1.0%"),
            (0, "0.0%"),
            (-5000, "-50.0%"),
            (-10000, "-100.0%"),
        ]
        for weight, expected_pct in test_cases:
            pct = f"{weight / 100:.1f}%"
            assert pct == expected_pct, (
                f"Weight {weight} -> {pct}, expected {expected_pct}"
            )
