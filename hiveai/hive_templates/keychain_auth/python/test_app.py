"""
Tests for the Hive Keychain Authentication Flask Server
========================================================

These tests verify the server-side logic WITHOUT requiring:
  - A running Hive blockchain node
  - The Hive Keychain browser extension
  - The beem library (for unit tests)

The tests mock blockchain interactions and signature verification
to test the Flask routes, session management, and error handling.

Run with:
    cd python/
    python -m pytest test_app.py -v

Or directly:
    python test_app.py
"""

import json
import time
import unittest
from unittest.mock import MagicMock, patch

# Import the Flask app and its internals
from app import (
    app,
    pending_challenges,
    CHALLENGE_TTL,
)


class TestHiveKeychainAuth(unittest.TestCase):
    """Test suite for the Hive Keychain authentication server."""

    def setUp(self):
        """
        Set up the Flask test client before each test.

        Flask's test_client() creates a client that can make requests
        to the app without starting a real server. This is standard
        Flask testing practice.
        """
        app.config["TESTING"] = True
        # Use a fixed secret key for reproducible session cookies in tests
        app.config["SECRET_KEY"] = "test-secret-key-for-testing-only"
        self.client = app.test_client()
        # Clear pending challenges between tests
        pending_challenges.clear()

    def tearDown(self):
        """Clean up after each test."""
        pending_challenges.clear()

    # -----------------------------------------------------------------------
    # Test: Frontend serving
    # -----------------------------------------------------------------------

    def test_index_page_serves_html(self):
        """GET / should return the login page HTML."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        # The template should contain the Keychain-related elements
        html = response.data.decode("utf-8")
        self.assertIn("Hive Keychain Login", html)
        self.assertIn("keychain-warning", html)
        self.assertIn("login-btn", html)

    # -----------------------------------------------------------------------
    # Test: Challenge generation
    # -----------------------------------------------------------------------

    @patch("app.get_hive_account")
    def test_challenge_success(self, mock_get_account):
        """POST /api/auth/challenge should return a challenge for a valid account."""
        # Mock the blockchain lookup to return a valid account
        mock_get_account.return_value = {
            "name": "alice",
            "posting": {"key_auths": [["STM7abc...", 1]]},
        }

        response = self.client.post(
            "/api/auth/challenge",
            data=json.dumps({"username": "alice"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        # Response should contain a challenge string and expiry
        self.assertIn("challenge", data)
        self.assertIn("expires_in", data)
        self.assertEqual(data["expires_in"], CHALLENGE_TTL)

        # Challenge format: "hive-auth:<username>:<random_hex>:<timestamp>"
        challenge = data["challenge"]
        self.assertTrue(challenge.startswith("hive-auth:alice:"))
        parts = challenge.split(":")
        self.assertEqual(len(parts), 4)
        self.assertEqual(parts[0], "hive-auth")
        self.assertEqual(parts[1], "alice")
        # parts[2] is 64 hex chars (32 random bytes)
        self.assertEqual(len(parts[2]), 64)

        # Challenge should be stored in pending_challenges
        self.assertIn("alice", pending_challenges)
        self.assertEqual(pending_challenges["alice"]["challenge"], challenge)

    def test_challenge_missing_username(self):
        """POST /api/auth/challenge with no username should return 400."""
        response = self.client.post(
            "/api/auth/challenge",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("error", data)

    @patch("app.get_hive_account")
    def test_challenge_account_not_found(self, mock_get_account):
        """POST /api/auth/challenge for non-existent account should return 404."""
        mock_get_account.return_value = None

        response = self.client.post(
            "/api/auth/challenge",
            data=json.dumps({"username": "nonexistent"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        self.assertIn("not found", data["error"].lower())

    @patch("app.get_hive_account")
    def test_challenge_normalizes_username(self, mock_get_account):
        """Username should be lowercased and trimmed."""
        mock_get_account.return_value = {"name": "alice", "posting": {"key_auths": []}}

        response = self.client.post(
            "/api/auth/challenge",
            data=json.dumps({"username": "  Alice  "}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        # The stored challenge should use the normalized username
        self.assertIn("alice", pending_challenges)

    # -----------------------------------------------------------------------
    # Test: Signature verification
    # -----------------------------------------------------------------------

    @patch("app.verify_hive_signature")
    @patch("app.get_hive_account")
    def test_verify_success(self, mock_get_account, mock_verify):
        """
        POST /api/auth/verify with valid signature should authenticate
        and create a Flask session.
        """
        # Set up a pending challenge
        challenge = "hive-auth:alice:abc123:1709000000"
        pending_challenges["alice"] = {
            "challenge": challenge,
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + CHALLENGE_TTL,
        }

        # Mock blockchain lookup
        mock_get_account.return_value = {
            "name": "alice",
            "posting": {"key_auths": [["STM7testkey123", 1]]},
        }

        # Mock signature verification to return True
        mock_verify.return_value = True

        response = self.client.post(
            "/api/auth/verify",
            data=json.dumps({
                "username": "alice",
                "challenge": challenge,
                "signature": "20" + "ab" * 32,  # Fake 65-byte hex signature
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["username"], "alice")

        # The challenge should be consumed (deleted from pending)
        self.assertNotIn("alice", pending_challenges)

        # Verify the Flask session was created by checking auth status
        status_response = self.client.get("/api/auth/status")
        status_data = status_response.get_json()
        self.assertTrue(status_data["authenticated"])
        self.assertEqual(status_data["username"], "alice")

    def test_verify_missing_fields(self):
        """POST /api/auth/verify with missing fields should return 400."""
        response = self.client.post(
            "/api/auth/verify",
            data=json.dumps({"username": "alice"}),  # Missing challenge and signature
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_verify_no_pending_challenge(self):
        """POST /api/auth/verify with no pending challenge should return 401."""
        response = self.client.post(
            "/api/auth/verify",
            data=json.dumps({
                "username": "alice",
                "challenge": "hive-auth:alice:fake:123",
                "signature": "20" + "ab" * 32,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_verify_challenge_mismatch(self):
        """POST /api/auth/verify with wrong challenge should return 401."""
        pending_challenges["alice"] = {
            "challenge": "hive-auth:alice:real:123",
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + CHALLENGE_TTL,
        }

        response = self.client.post(
            "/api/auth/verify",
            data=json.dumps({
                "username": "alice",
                "challenge": "hive-auth:alice:wrong:456",
                "signature": "20" + "ab" * 32,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("mismatch", data["error"].lower())

    def test_verify_challenge_expired(self):
        """POST /api/auth/verify with expired challenge should return 401."""
        challenge = "hive-auth:alice:expired:123"
        pending_challenges["alice"] = {
            "challenge": challenge,
            "created_at": int(time.time()) - 600,  # 10 minutes ago
            "expires_at": int(time.time()) - 300,   # Expired 5 minutes ago
        }

        response = self.client.post(
            "/api/auth/verify",
            data=json.dumps({
                "username": "alice",
                "challenge": challenge,
                "signature": "20" + "ab" * 32,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("expired", data["error"].lower())

        # Expired challenge should be cleaned up
        self.assertNotIn("alice", pending_challenges)

    @patch("app.verify_hive_signature")
    @patch("app.get_hive_account")
    def test_verify_invalid_signature(self, mock_get_account, mock_verify):
        """POST /api/auth/verify with invalid signature should return 401."""
        challenge = "hive-auth:alice:valid:123"
        pending_challenges["alice"] = {
            "challenge": challenge,
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + CHALLENGE_TTL,
        }

        mock_get_account.return_value = {
            "name": "alice",
            "posting": {"key_auths": [["STM7testkey123", 1]]},
        }

        # Mock signature verification to return False (invalid sig)
        mock_verify.return_value = False

        response = self.client.post(
            "/api/auth/verify",
            data=json.dumps({
                "username": "alice",
                "challenge": challenge,
                "signature": "20" + "ff" * 32,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("invalid", data["error"].lower())

    @patch("app.get_hive_account")
    def test_verify_no_posting_keys(self, mock_get_account):
        """Account with no posting keys should return 400."""
        challenge = "hive-auth:alice:nokeys:123"
        pending_challenges["alice"] = {
            "challenge": challenge,
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + CHALLENGE_TTL,
        }

        mock_get_account.return_value = {
            "name": "alice",
            "posting": {"key_auths": []},  # No posting keys!
        }

        response = self.client.post(
            "/api/auth/verify",
            data=json.dumps({
                "username": "alice",
                "challenge": challenge,
                "signature": "20" + "ab" * 32,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    # -----------------------------------------------------------------------
    # Test: Protected routes
    # -----------------------------------------------------------------------

    def test_profile_unauthenticated(self):
        """GET /api/profile without auth should return 401."""
        response = self.client.get("/api/profile")
        self.assertEqual(response.status_code, 401)

    @patch("app.get_hive_account")
    def test_profile_authenticated(self, mock_get_account):
        """GET /api/profile with valid session should return profile data."""
        # Simulate an authenticated session
        with self.client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["username"] = "alice"
            sess["auth_method"] = "hive_keychain"
            sess["auth_time"] = int(time.time())

        mock_get_account.return_value = {
            "name": "alice",
            "posting_json_metadata": json.dumps({
                "profile": {
                    "name": "Alice",
                    "about": "Test user",
                    "location": "Decentralized",
                    "website": "https://alice.dev",
                    "profile_image": "https://example.com/alice.jpg",
                    "cover_image": "",
                }
            }),
            "reputation": 7500000000000,
            "post_count": 42,
            "created": "2020-01-15T00:00:00",
            "balance": "100.000 HIVE",
            "hbd_balance": "50.000 HBD",
            "vesting_shares": "500000.000000 VESTS",
        }

        response = self.client.get("/api/profile")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        self.assertEqual(data["username"], "alice")
        self.assertEqual(data["profile"]["name"], "Alice")
        self.assertEqual(data["profile"]["about"], "Test user")
        self.assertEqual(data["post_count"], 42)
        self.assertIn("HIVE", data["balance"])

    # -----------------------------------------------------------------------
    # Test: Auth status
    # -----------------------------------------------------------------------

    def test_auth_status_unauthenticated(self):
        """GET /api/auth/status without session should return not authenticated."""
        response = self.client.get("/api/auth/status")
        data = response.get_json()
        self.assertFalse(data["authenticated"])

    def test_auth_status_authenticated(self):
        """GET /api/auth/status with valid session should return authenticated."""
        with self.client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["username"] = "alice"

        response = self.client.get("/api/auth/status")
        data = response.get_json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["username"], "alice")

    # -----------------------------------------------------------------------
    # Test: Logout
    # -----------------------------------------------------------------------

    def test_logout_clears_session(self):
        """POST /api/auth/logout should clear the session."""
        # Set up an authenticated session
        with self.client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["username"] = "alice"

        # Verify we are authenticated
        status = self.client.get("/api/auth/status").get_json()
        self.assertTrue(status["authenticated"])

        # Logout
        response = self.client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 200)

        # Verify the session is cleared
        status = self.client.get("/api/auth/status").get_json()
        self.assertFalse(status["authenticated"])

    # -----------------------------------------------------------------------
    # Test: Challenge cleanup
    # -----------------------------------------------------------------------

    @patch("app.get_hive_account")
    def test_expired_challenges_cleaned_up(self, mock_get_account):
        """Generating a new challenge should clean up expired ones."""
        # Add an expired challenge for a different user
        pending_challenges["old_user"] = {
            "challenge": "hive-auth:old_user:expired:1",
            "created_at": int(time.time()) - 600,
            "expires_at": int(time.time()) - 300,
        }

        mock_get_account.return_value = {
            "name": "alice",
            "posting": {"key_auths": [["STM7...", 1]]},
        }

        # Generate a challenge for a new user
        self.client.post(
            "/api/auth/challenge",
            data=json.dumps({"username": "alice"}),
            content_type="application/json",
        )

        # The expired challenge should have been cleaned up
        self.assertNotIn("old_user", pending_challenges)
        # The new challenge should exist
        self.assertIn("alice", pending_challenges)

    # -----------------------------------------------------------------------
    # Test: Challenge is single-use
    # -----------------------------------------------------------------------

    @patch("app.verify_hive_signature")
    @patch("app.get_hive_account")
    def test_challenge_consumed_after_verification(self, mock_get_account, mock_verify):
        """A challenge should be deleted after successful verification (single-use)."""
        challenge = "hive-auth:alice:singleuse:123"
        pending_challenges["alice"] = {
            "challenge": challenge,
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + CHALLENGE_TTL,
        }

        mock_get_account.return_value = {
            "name": "alice",
            "posting": {"key_auths": [["STM7test", 1]]},
        }
        mock_verify.return_value = True

        # First verification should succeed
        resp1 = self.client.post(
            "/api/auth/verify",
            data=json.dumps({
                "username": "alice",
                "challenge": challenge,
                "signature": "20" + "ab" * 32,
            }),
            content_type="application/json",
        )
        self.assertEqual(resp1.status_code, 200)

        # Second attempt with the same challenge should fail (replay protection)
        resp2 = self.client.post(
            "/api/auth/verify",
            data=json.dumps({
                "username": "alice",
                "challenge": challenge,
                "signature": "20" + "ab" * 32,
            }),
            content_type="application/json",
        )
        self.assertEqual(resp2.status_code, 401)

    # -----------------------------------------------------------------------
    # Test: Multi-key support
    # -----------------------------------------------------------------------

    @patch("app.verify_hive_signature")
    @patch("app.get_hive_account")
    def test_verify_multi_key_account(self, mock_get_account, mock_verify):
        """
        Verification should succeed if the signature matches ANY posting key.
        (Multi-sig accounts may have multiple posting keys.)
        """
        challenge = "hive-auth:alice:multikey:123"
        pending_challenges["alice"] = {
            "challenge": challenge,
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + CHALLENGE_TTL,
        }

        # Account has two posting keys
        mock_get_account.return_value = {
            "name": "alice",
            "posting": {"key_auths": [
                ["STM7key_one", 1],
                ["STM7key_two", 1],
            ]},
        }

        # First key fails, second key succeeds
        mock_verify.side_effect = [False, True]

        response = self.client.post(
            "/api/auth/verify",
            data=json.dumps({
                "username": "alice",
                "challenge": challenge,
                "signature": "20" + "ab" * 32,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        # verify_hive_signature should have been called twice
        self.assertEqual(mock_verify.call_count, 2)


if __name__ == "__main__":
    unittest.main()
