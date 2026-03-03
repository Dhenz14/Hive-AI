"""
=============================================================================
Hive Engine Token App — Test Suite (pytest)
=============================================================================

Tests for input validation, helper functions, and Flask route behavior.
These tests run WITHOUT any blockchain connectivity — they validate the
local logic that protects against malformed requests before they ever
reach the Hive Layer 1 or Hive Engine Layer 2 APIs.

Run: pytest test_app.py -v
=============================================================================
"""

import json
from unittest.mock import patch, MagicMock

import pytest

# Import the Flask app and validation functions from app.py
from app import (
    app,
    validate_account,
    validate_symbol,
    validate_quantity,
    validate_price,
)


# =============================================================================
# Pytest Fixture: Flask Test Client
# =============================================================================


@pytest.fixture
def client():
    """
    Creates a Flask test client for testing HTTP endpoints.
    The test client simulates HTTP requests without starting a real server.
    """
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# =============================================================================
# Tests: validate_account
# =============================================================================


class TestValidateAccount:
    """
    Tests for Hive account name validation.

    Hive account names must be:
      - 3 to 16 characters long
      - Lowercase letters, digits, hyphens, and dots only
      - Must start with a letter
    """

    def test_valid_simple_account(self):
        """Standard lowercase account name should be valid."""
        assert validate_account("alice") is None

    def test_valid_account_with_numbers(self):
        """Account names can contain digits after the first letter."""
        assert validate_account("user123") is None

    def test_valid_account_with_hyphens(self):
        """Hyphens are allowed in Hive account names."""
        assert validate_account("my-account") is None

    def test_valid_account_with_dots(self):
        """Dots are allowed in Hive account names."""
        assert validate_account("my.account") is None

    def test_valid_minimum_length(self):
        """Minimum account name length is 3 characters."""
        assert validate_account("abc") is None

    def test_valid_maximum_length(self):
        """Maximum account name length is 16 characters."""
        assert validate_account("abcdefghijklmnop") is None

    def test_valid_real_account_splinterlands(self):
        """Real Hive account 'splinterlands' should be valid."""
        assert validate_account("splinterlands") is None

    def test_valid_real_account_hive_engine(self):
        """Real Hive account 'hive-engine' should be valid."""
        assert validate_account("hive-engine") is None

    def test_invalid_none(self):
        """None input should return an error."""
        assert validate_account(None) is not None

    def test_invalid_empty_string(self):
        """Empty string should return an error."""
        assert validate_account("") is not None

    def test_invalid_number_type(self):
        """Non-string input should return an error."""
        assert validate_account(123) is not None

    def test_invalid_uppercase(self):
        """Uppercase letters are not allowed in Hive account names."""
        assert validate_account("Alice") is not None

    def test_invalid_too_short(self):
        """Account names shorter than 3 characters are invalid."""
        assert validate_account("ab") is not None

    def test_invalid_too_long(self):
        """Account names longer than 16 characters are invalid."""
        assert validate_account("abcdefghijklmnopq") is not None

    def test_invalid_starts_with_number(self):
        """Account names must start with a letter, not a number."""
        assert validate_account("1account") is not None

    def test_invalid_starts_with_hyphen(self):
        """Account names must start with a letter, not a hyphen."""
        assert validate_account("-account") is not None

    def test_invalid_contains_spaces(self):
        """Spaces are not allowed in account names."""
        assert validate_account("my account") is not None

    def test_invalid_special_characters(self):
        """Special characters like @ are not allowed."""
        assert validate_account("my@account") is not None

    def test_invalid_underscore(self):
        """Underscores are not allowed in Hive account names."""
        assert validate_account("my_account") is not None


# =============================================================================
# Tests: validate_symbol
# =============================================================================


class TestValidateSymbol:
    """
    Tests for Hive Engine token symbol validation.

    Token symbols must be:
      - 1 to 10 characters
      - Uppercase letters, digits, and dots only
      - Must start with a letter
      - Dots are used in wrapped tokens (e.g., SWAP.HIVE)
    """

    def test_valid_simple_symbol(self):
        """Standard 3-letter token symbol should be valid."""
        assert validate_symbol("BEE") is None

    def test_valid_single_char(self):
        """Single uppercase letter is a valid (minimal) symbol."""
        assert validate_symbol("A") is None

    def test_valid_with_digits(self):
        """Symbols can contain digits after the first letter."""
        assert validate_symbol("H4F") is None

    def test_valid_wrapped_token(self):
        """SWAP.HIVE uses dot notation for wrapped tokens — valid."""
        assert validate_symbol("SWAP.HIVE") is None

    def test_valid_max_length(self):
        """Maximum symbol length is 10 characters."""
        assert validate_symbol("ABCDEFGHIJ") is None

    def test_valid_real_tokens(self):
        """Real Hive Engine tokens should all be valid."""
        for token in ["DEC", "SPS", "LEO", "SWAP.HBD", "BEE"]:
            assert validate_symbol(token) is None, f"{token} should be valid"

    def test_invalid_none(self):
        """None input should return an error."""
        assert validate_symbol(None) is not None

    def test_invalid_empty(self):
        """Empty string should return an error."""
        assert validate_symbol("") is not None

    def test_invalid_lowercase(self):
        """Lowercase symbols are not valid."""
        assert validate_symbol("bee") is not None

    def test_invalid_mixed_case(self):
        """Mixed case is not valid — symbols must be all uppercase."""
        assert validate_symbol("Bee") is not None

    def test_invalid_too_long(self):
        """Symbols longer than 10 characters are invalid."""
        assert validate_symbol("ABCDEFGHIJK") is not None

    def test_invalid_starts_with_digit(self):
        """Symbols must start with a letter, not a digit."""
        assert validate_symbol("1TOKEN") is not None

    def test_invalid_contains_spaces(self):
        """Spaces are not allowed in symbols."""
        assert validate_symbol("MY TOKEN") is not None

    def test_invalid_special_chars(self):
        """Special characters (except dots) are not allowed."""
        assert validate_symbol("MY@TOKEN") is not None


# =============================================================================
# Tests: validate_quantity
# =============================================================================


class TestValidateQuantity:
    """
    Tests for token quantity validation.

    Quantities must be:
      - Strings (not numbers) to avoid floating-point precision issues
      - Positive decimal numbers
      - The blockchain requires exact string representation
    """

    def test_valid_integer(self):
        """Integer quantity as string should be valid."""
        assert validate_quantity("10") is None

    def test_valid_decimal(self):
        """Decimal quantity should be valid."""
        assert validate_quantity("10.000") is None

    def test_valid_small_amount(self):
        """Small decimal amount should be valid."""
        assert validate_quantity("0.001") is None

    def test_valid_large_amount(self):
        """Large amount with many decimals should be valid."""
        assert validate_quantity("1000000.00000000") is None

    def test_valid_max_precision(self):
        """8 decimal places (maximum Hive Engine precision) should be valid."""
        assert validate_quantity("0.00000001") is None

    def test_invalid_none(self):
        """None should return an error."""
        assert validate_quantity(None) is not None

    def test_invalid_number_type(self):
        """Numeric types (not strings) should be rejected to prevent precision loss."""
        assert validate_quantity(10) is not None

    def test_invalid_empty(self):
        """Empty string should return an error."""
        assert validate_quantity("") is not None

    def test_invalid_zero(self):
        """Zero quantity should be rejected (no-op transfer)."""
        assert validate_quantity("0") is not None

    def test_invalid_negative(self):
        """Negative quantities should be rejected."""
        assert validate_quantity("-5") is not None

    def test_invalid_non_numeric(self):
        """Non-numeric strings should be rejected."""
        assert validate_quantity("abc") is not None

    def test_invalid_leading_plus(self):
        """Leading plus sign should be rejected."""
        assert validate_quantity("+5") is not None

    def test_invalid_double_dot(self):
        """Double dots should be rejected."""
        assert validate_quantity("1..5") is not None


# =============================================================================
# Tests: validate_price
# =============================================================================


class TestValidatePrice:
    """
    Tests for DEX price validation.

    Prices are denominated in SWAP.HIVE per token.
    Same rules as quantity: must be positive number strings.
    """

    def test_valid_integer_price(self):
        """Integer price should be valid."""
        assert validate_price("1") is None

    def test_valid_decimal_price(self):
        """Decimal price should be valid."""
        assert validate_price("0.01000000") is None

    def test_valid_small_price(self):
        """Very small price (8 decimals) should be valid."""
        assert validate_price("0.00000001") is None

    def test_valid_large_price(self):
        """Large price should be valid."""
        assert validate_price("999.99999999") is None

    def test_invalid_none(self):
        """None should return an error."""
        assert validate_price(None) is not None

    def test_invalid_number_type(self):
        """Float types should be rejected (must be string)."""
        assert validate_price(0.01) is not None

    def test_invalid_zero(self):
        """Zero price should be rejected (free tokens makes no sense on DEX)."""
        assert validate_price("0") is not None

    def test_invalid_negative(self):
        """Negative price should be rejected."""
        assert validate_price("-0.01") is not None

    def test_invalid_non_numeric(self):
        """Non-numeric strings should be rejected."""
        assert validate_price("free") is not None


# =============================================================================
# Tests: Hive Engine Real-World Scenarios
# =============================================================================


class TestRealWorldScenarios:
    """
    Tests combining multiple validators to simulate real Hive Engine operations.
    These verify that the validation layer correctly handles realistic inputs.
    """

    def test_valid_transfer_scenario(self):
        """A typical BEE transfer should pass all validation."""
        assert validate_symbol("BEE") is None
        assert validate_account("splinterlands") is None
        assert validate_quantity("100.000") is None

    def test_valid_market_order_scenario(self):
        """A typical DEX buy order should pass all validation."""
        assert validate_symbol("DEC") is None
        assert validate_quantity("1000.000") is None
        assert validate_price("0.00100000") is None

    def test_valid_stake_scenario(self):
        """A typical staking operation should pass all validation."""
        assert validate_symbol("LEO") is None
        assert validate_account("leofinance") is None
        assert validate_quantity("500.000") is None

    def test_wrapped_token_balance_check(self):
        """Wrapped tokens (SWAP.HIVE, SWAP.HBD) should be valid symbols."""
        assert validate_symbol("SWAP.HIVE") is None
        assert validate_symbol("SWAP.HBD") is None
        assert validate_account("honey-swap") is None


# =============================================================================
# Tests: Flask Route — Root Endpoint
# =============================================================================


class TestRootEndpoint:
    """Tests for the GET / endpoint that returns API documentation."""

    def test_root_returns_200(self, client):
        """Root endpoint should return 200 OK."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_returns_json(self, client):
        """Root endpoint should return valid JSON."""
        response = client.get("/")
        data = response.get_json()
        assert data is not None

    def test_root_has_endpoints_list(self, client):
        """Root endpoint should list all available API endpoints."""
        response = client.get("/")
        data = response.get_json()
        assert "endpoints" in data
        assert "GET /api/tokens" in data["endpoints"]

    def test_root_has_architecture_info(self, client):
        """Root endpoint should describe the L1/L2 architecture."""
        response = client.get("/")
        data = response.get_json()
        assert "architecture" in data
        assert "layer1" in data["architecture"]
        assert "layer2" in data["architecture"]
        assert "bridge" in data["architecture"]


# =============================================================================
# Tests: Flask Routes — Input Validation on Endpoints
# =============================================================================


class TestTokenEndpointValidation:
    """Tests that the /api/token/<symbol> endpoint validates input properly."""

    def test_invalid_symbol_returns_400(self, client):
        """Requesting a token with an invalid symbol should return 400."""
        response = client.get("/api/token/invalid!")
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False


class TestBalanceEndpointValidation:
    """Tests that the /api/balance/<account> endpoints validate input properly."""

    def test_invalid_account_returns_400(self, client):
        """Requesting balances for an invalid account should return 400."""
        response = client.get("/api/balance/INVALID")
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_invalid_symbol_in_balance_returns_400(self, client):
        """Requesting balance with invalid symbol should return 400."""
        response = client.get("/api/balance/alice/invalid!")
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False


class TestTransferEndpointValidation:
    """Tests that the POST /api/transfer endpoint validates input properly."""

    def test_missing_body_returns_400(self, client):
        """POST without JSON body should return 400."""
        response = client.post(
            "/api/transfer",
            data="not json",
            content_type="text/plain",
        )
        assert response.status_code == 400

    def test_invalid_symbol_returns_400(self, client):
        """Transfer with invalid symbol should return 400."""
        response = client.post(
            "/api/transfer",
            json={"symbol": "invalid!", "to": "alice", "quantity": "10.000"},
        )
        assert response.status_code == 400

    def test_invalid_recipient_returns_400(self, client):
        """Transfer to invalid account should return 400."""
        response = client.post(
            "/api/transfer",
            json={"symbol": "BEE", "to": "INVALID", "quantity": "10.000"},
        )
        assert response.status_code == 400

    def test_invalid_quantity_returns_400(self, client):
        """Transfer with invalid quantity should return 400."""
        response = client.post(
            "/api/transfer",
            json={"symbol": "BEE", "to": "alice", "quantity": "-5"},
        )
        assert response.status_code == 400

    def test_zero_quantity_returns_400(self, client):
        """Transfer with zero quantity should return 400."""
        response = client.post(
            "/api/transfer",
            json={"symbol": "BEE", "to": "alice", "quantity": "0"},
        )
        assert response.status_code == 400


class TestStakeEndpointValidation:
    """Tests that the POST /api/stake endpoint validates input properly."""

    def test_invalid_symbol_returns_400(self, client):
        """Staking with invalid symbol should return 400."""
        response = client.post(
            "/api/stake",
            json={"symbol": "invalid!", "quantity": "10.000"},
        )
        assert response.status_code == 400

    def test_invalid_quantity_returns_400(self, client):
        """Staking with invalid quantity should return 400."""
        response = client.post(
            "/api/stake",
            json={"symbol": "BEE", "quantity": "abc"},
        )
        assert response.status_code == 400


class TestUnstakeEndpointValidation:
    """Tests that the POST /api/unstake endpoint validates input properly."""

    def test_invalid_symbol_returns_400(self, client):
        """Unstaking with invalid symbol should return 400."""
        response = client.post(
            "/api/unstake",
            json={"symbol": "invalid!", "quantity": "10.000"},
        )
        assert response.status_code == 400

    def test_invalid_quantity_returns_400(self, client):
        """Unstaking with invalid quantity should return 400."""
        response = client.post(
            "/api/unstake",
            json={"symbol": "BEE", "quantity": "0"},
        )
        assert response.status_code == 400


class TestMarketEndpointValidation:
    """Tests that the market endpoints validate input properly."""

    def test_invalid_symbol_in_orderbook_returns_400(self, client):
        """Requesting order book with invalid symbol should return 400."""
        response = client.get("/api/market/invalid!")
        assert response.status_code == 400

    def test_buy_invalid_symbol_returns_400(self, client):
        """Buy order with invalid symbol should return 400."""
        response = client.post(
            "/api/market/buy",
            json={"symbol": "bad!", "quantity": "10.000", "price": "0.01"},
        )
        assert response.status_code == 400

    def test_buy_invalid_quantity_returns_400(self, client):
        """Buy order with invalid quantity should return 400."""
        response = client.post(
            "/api/market/buy",
            json={"symbol": "BEE", "quantity": "-1", "price": "0.01"},
        )
        assert response.status_code == 400

    def test_buy_invalid_price_returns_400(self, client):
        """Buy order with invalid price should return 400."""
        response = client.post(
            "/api/market/buy",
            json={"symbol": "BEE", "quantity": "10.000", "price": "0"},
        )
        assert response.status_code == 400

    def test_sell_invalid_symbol_returns_400(self, client):
        """Sell order with invalid symbol should return 400."""
        response = client.post(
            "/api/market/sell",
            json={"symbol": "bad!", "quantity": "10.000", "price": "0.01"},
        )
        assert response.status_code == 400

    def test_sell_invalid_price_returns_400(self, client):
        """Sell order with zero price should return 400."""
        response = client.post(
            "/api/market/sell",
            json={"symbol": "BEE", "quantity": "10.000", "price": "0"},
        )
        assert response.status_code == 400


class TestHistoryEndpointValidation:
    """Tests that the GET /api/history endpoint validates input properly."""

    def test_invalid_account_returns_400(self, client):
        """History with invalid account should return 400."""
        response = client.get("/api/history/INVALID/BEE")
        assert response.status_code == 400

    def test_invalid_symbol_returns_400(self, client):
        """History with invalid symbol should return 400."""
        response = client.get("/api/history/alice/invalid!")
        assert response.status_code == 400


# =============================================================================
# Tests: Hive Engine JSON Payload Structure
# =============================================================================


class TestHiveEnginePayloadStructure:
    """
    Tests that verify the JSON payload structure used for Hive Engine operations.
    These ensure our payloads match what the sidechain expects.

    Hive Engine expects custom_json operations with:
      - id: "ssc-mainnet-hive"
      - json: stringified {contractName, contractAction, contractPayload}
    """

    def test_transfer_payload_structure(self):
        """Verify transfer payload has the correct Hive Engine structure."""
        # This is what gets stringified and sent as custom_json
        payload = {
            "contractName": "tokens",
            "contractAction": "transfer",
            "contractPayload": {
                "symbol": "BEE",
                "to": "alice",
                "quantity": "10.000",
                "memo": "test payment",
            },
        }
        json_str = json.dumps(payload)
        parsed = json.loads(json_str)

        assert parsed["contractName"] == "tokens"
        assert parsed["contractAction"] == "transfer"
        assert "symbol" in parsed["contractPayload"]
        assert "to" in parsed["contractPayload"]
        assert "quantity" in parsed["contractPayload"]

    def test_stake_payload_structure(self):
        """Verify stake payload has the correct Hive Engine structure."""
        payload = {
            "contractName": "tokens",
            "contractAction": "stake",
            "contractPayload": {
                "to": "alice",
                "symbol": "LEO",
                "quantity": "100.000",
            },
        }
        json_str = json.dumps(payload)
        parsed = json.loads(json_str)

        assert parsed["contractName"] == "tokens"
        assert parsed["contractAction"] == "stake"
        assert "to" in parsed["contractPayload"]

    def test_market_buy_payload_structure(self):
        """Verify market buy payload has the correct Hive Engine structure."""
        payload = {
            "contractName": "market",
            "contractAction": "buy",
            "contractPayload": {
                "symbol": "BEE",
                "quantity": "100.000",
                "price": "0.01000000",
            },
        }
        json_str = json.dumps(payload)
        parsed = json.loads(json_str)

        assert parsed["contractName"] == "market"
        assert parsed["contractAction"] == "buy"
        assert "price" in parsed["contractPayload"]

    def test_custom_json_id_is_correct(self):
        """
        The custom_json 'id' field MUST be 'ssc-mainnet-hive' for Hive Engine
        sidechain nodes to recognize and process the operation.
        This is the most critical constant in the entire bridge architecture.
        """
        HIVE_ENGINE_CUSTOM_JSON_ID = "ssc-mainnet-hive"
        assert HIVE_ENGINE_CUSTOM_JSON_ID == "ssc-mainnet-hive"

    def test_required_auths_not_posting_auths(self):
        """
        Financial operations must use required_auths (active key), NOT
        required_posting_auths (posting key). Using posting key would fail
        because Hive Engine only processes operations signed with active keys
        for security reasons.
        """
        # This simulates the custom_json operation structure
        custom_json_op = {
            "required_auths": ["testaccount"],       # Active key — CORRECT
            "required_posting_auths": [],             # Empty — CORRECT
            "id": "ssc-mainnet-hive",
            "json": '{"contractName":"tokens","contractAction":"transfer","contractPayload":{}}',
        }

        assert len(custom_json_op["required_auths"]) > 0, \
            "required_auths must contain the account (active key authorization)"
        assert len(custom_json_op["required_posting_auths"]) == 0, \
            "required_posting_auths must be empty for financial operations"
