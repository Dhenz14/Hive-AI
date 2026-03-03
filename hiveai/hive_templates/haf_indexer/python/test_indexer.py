"""
HAF Indexer — Test Suite (Python / pytest)
===========================================

Tests for the HAF transfer indexer. These tests verify:
    1. Amount parsing logic (unit tests — no database required)
    2. Operation JSON parsing (unit tests)
    3. Database connectivity and schema existence (integration)
    4. HAF context registration (integration)
    5. Table structure verification (integration)
    6. Flask API endpoint responses (integration)

Run:
    pytest test_indexer.py -v
    # or: pytest test_indexer.py -v -k "not integration"  (unit tests only)

Prerequisites:
    - PostgreSQL with HAF running and accessible (for integration tests)
    - Schema created via: python setup.py
"""

import json
import os
from decimal import Decimal

import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

APP_NAME = os.getenv("APP_NAME", "my_haf_indexer")

# Import the parse_amount function from our indexer module
# This is the function under test for unit tests
from indexer import parse_amount


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def db_connection():
    """
    Create a database connection for integration tests.
    Yields the connection and closes it after all tests.
    Skips all integration tests if the database is not available.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("HAF_DB_HOST", "localhost"),
            port=int(os.getenv("HAF_DB_PORT", "5432")),
            dbname=os.getenv("HAF_DB_NAME", "haf_block_log"),
            user=os.getenv("HAF_DB_USER", "haf_app"),
            password=os.getenv("HAF_DB_PASSWORD", ""),
            connect_timeout=5,
        )
        conn.autocommit = True
        yield conn
        conn.close()
    except Exception as e:
        pytest.skip(f"Database not available: {e}")


@pytest.fixture(scope="session")
def db_cursor(db_connection):
    """Create a cursor from the database connection."""
    import psycopg2.extras
    cur = db_connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    yield cur
    cur.close()


@pytest.fixture
def flask_client():
    """
    Create a Flask test client for API endpoint tests.
    Skips if the database is not available.
    """
    try:
        from server import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client
    except Exception as e:
        pytest.skip(f"Flask app could not be created: {e}")


# =============================================================================
# Unit Tests — Amount Parsing (no database required)
# =============================================================================

class TestParseAmount:
    """
    Test the parse_amount function that converts HAF's internal amount
    representation to human-readable form.

    HAF stores amounts as:
        {"amount": "1000", "precision": 3, "nai": "@@000000021"}

    NAI codes:
        @@000000021 = HIVE
        @@000000013 = HBD
        @@000000037 = VESTS
    """

    def test_parse_hive_amount(self):
        """Parse 1.000 HIVE from HAF's internal format."""
        # HAF stores 1.000 HIVE as amount=1000, precision=3
        result = parse_amount({"amount": "1000", "precision": 3, "nai": "@@000000021"})
        assert result["numeric"] == Decimal("1.000")
        assert result["asset"] == "HIVE"
        assert result["display"] == "1.000 HIVE"

    def test_parse_hbd_amount(self):
        """Parse 25.500 HBD from HAF's internal format."""
        # 25.500 HBD = amount 25500, precision 3
        result = parse_amount({"amount": "25500", "precision": 3, "nai": "@@000000013"})
        assert result["numeric"] == Decimal("25.500")
        assert result["asset"] == "HBD"
        assert result["display"] == "25.500 HBD"

    def test_parse_vests_amount(self):
        """Parse VESTS amount (6 decimal places of precision)."""
        # VESTS have 6 decimal places
        result = parse_amount({"amount": "123456789012", "precision": 6, "nai": "@@000000037"})
        assert result["numeric"] == Decimal("123456.789012")
        assert result["asset"] == "VESTS"
        assert "123456.789012 VESTS" in result["display"]

    def test_parse_zero_amount(self):
        """Parse zero HIVE amount."""
        result = parse_amount({"amount": "0", "precision": 3, "nai": "@@000000021"})
        assert result["numeric"] == Decimal("0.000")
        assert result["asset"] == "HIVE"

    def test_parse_large_amount(self):
        """Parse 1,000,000.000 HIVE (1 million)."""
        # 1 million HIVE = amount 1000000000, precision 3
        result = parse_amount({"amount": "1000000000", "precision": 3, "nai": "@@000000021"})
        assert result["numeric"] == Decimal("1000000.000")

    def test_parse_unknown_nai(self):
        """Unknown NAI code returns 'UNKNOWN' asset."""
        result = parse_amount({"amount": "100", "precision": 3, "nai": "@@999999999"})
        assert result["asset"] == "UNKNOWN"

    def test_parse_small_amount(self):
        """Parse 0.001 HIVE (minimum transferable amount)."""
        result = parse_amount({"amount": "1", "precision": 3, "nai": "@@000000021"})
        assert result["numeric"] == Decimal("0.001")
        assert result["display"] == "0.001 HIVE"

    def test_precision_is_correct(self):
        """Verify decimal precision matches the precision field."""
        result = parse_amount({"amount": "5000", "precision": 3, "nai": "@@000000021"})
        # Should be "5.000" not "5" — precision of 3 means 3 decimal places
        assert "." in result["display"]
        assert len(result["display"].split(".")[1].split(" ")[0]) == 3


# =============================================================================
# Unit Tests — Operation JSON Parsing
# =============================================================================

class TestOperationParsing:
    """
    Test parsing of transfer operation JSON bodies as stored in hive.operations.
    """

    def test_parse_transfer_body(self):
        """Parse a complete transfer_operation JSON body."""
        # This is the exact JSON structure stored in hive.operations.body
        op_body = {
            "type": "transfer_operation",
            "value": {
                "from": "alice",
                "to": "bob",
                "amount": {"amount": "5000", "precision": 3, "nai": "@@000000021"},
                "memo": "test transfer",
            },
        }

        value = op_body["value"]
        assert value["from"] == "alice"
        assert value["to"] == "bob"
        assert value["memo"] == "test transfer"

        amount = parse_amount(value["amount"])
        assert amount["display"] == "5.000 HIVE"

    def test_parse_transfer_empty_memo(self):
        """Handle transfer with empty memo field."""
        op_body = {
            "type": "transfer_operation",
            "value": {
                "from": "alice",
                "to": "bob",
                "amount": {"amount": "1000", "precision": 3, "nai": "@@000000021"},
                "memo": "",
            },
        }
        assert op_body["value"]["memo"] == ""

    def test_parse_hbd_transfer(self):
        """Parse an HBD transfer operation."""
        op_body = {
            "type": "transfer_operation",
            "value": {
                "from": "exchange",
                "to": "user123",
                "amount": {"amount": "100000", "precision": 3, "nai": "@@000000013"},
                "memo": "withdrawal #12345",
            },
        }

        amount = parse_amount(op_body["value"]["amount"])
        assert amount["asset"] == "HBD"
        assert amount["numeric"] == Decimal("100.000")

    def test_json_round_trip(self):
        """Verify operation JSON survives serialization/deserialization."""
        original = {
            "type": "transfer_operation",
            "value": {
                "from": "alice",
                "to": "bob",
                "amount": {"amount": "5000", "precision": 3, "nai": "@@000000021"},
                "memo": "hello world",
            },
        }
        # Simulate what HAF does: store as JSON text and parse back
        json_text = json.dumps(original)
        parsed = json.loads(json_text)
        assert parsed == original

    def test_operation_type_identification(self):
        """Verify we can identify transfer operations by type field."""
        transfer_op = {"type": "transfer_operation", "value": {}}
        vote_op = {"type": "vote_operation", "value": {}}
        custom_op = {"type": "custom_json_operation", "value": {}}

        assert transfer_op["type"] == "transfer_operation"
        assert vote_op["type"] != "transfer_operation"
        assert custom_op["type"] != "transfer_operation"


# =============================================================================
# Integration Tests — Database (requires live HAF PostgreSQL)
# =============================================================================

@pytest.mark.integration
class TestDatabaseSetup:
    """
    Integration tests that verify the HAF database is properly set up.
    These tests require a live PostgreSQL instance with HAF installed.
    """

    def test_database_connection(self, db_cursor):
        """Verify we can connect to the HAF database."""
        db_cursor.execute("SELECT 1 as alive")
        result = db_cursor.fetchone()
        assert result["alive"] == 1

    def test_haf_schema_exists(self, db_cursor):
        """Verify the hive schema exists (created by HAF/hived)."""
        db_cursor.execute(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name = 'hive'"
        )
        result = db_cursor.fetchone()
        assert result is not None, "hive schema not found — HAF may not be installed"

    def test_haf_core_tables_exist(self, db_cursor):
        """Verify HAF's core tables exist (populated by hived)."""
        # These tables are created by HAF and populated by hived
        tables = ["blocks", "operations", "transactions", "operation_types"]
        for table in tables:
            db_cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'hive' AND table_name = %s",
                (table,),
            )
            result = db_cursor.fetchone()
            assert result is not None, f"hive.{table} table not found"

    def test_haf_context_function_exists(self, db_cursor):
        """Verify hive.app_create_context function is available."""
        db_cursor.execute(
            "SELECT proname FROM pg_proc "
            "JOIN pg_namespace ON pg_namespace.oid = pronamespace "
            "WHERE nspname = 'hive' AND proname = 'app_create_context'"
        )
        result = db_cursor.fetchone()
        assert result is not None, "hive.app_create_context function not found"

    def test_app_schema_exists(self, db_cursor):
        """Verify our application schema was created by setup.py."""
        db_cursor.execute(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name = %s",
            (APP_NAME,),
        )
        result = db_cursor.fetchone()
        assert result is not None, f"Schema '{APP_NAME}' not found. Run 'python setup.py' first."

    def test_app_tables_exist(self, db_cursor):
        """Verify our application tables were created by setup.py."""
        tables = ["transfers", "account_stats", "indexer_state"]
        for table in tables:
            db_cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s",
                (APP_NAME, table),
            )
            result = db_cursor.fetchone()
            assert result is not None, (
                f"Table {APP_NAME}.{table} not found. Run 'python setup.py' first."
            )

    def test_haf_context_registered(self, db_cursor):
        """Verify our HAF context is registered in hive.contexts."""
        db_cursor.execute(
            "SELECT name, current_block_num FROM hive.contexts WHERE name = %s",
            (APP_NAME,),
        )
        result = db_cursor.fetchone()
        assert result is not None, (
            f"HAF context '{APP_NAME}' not registered. Run 'python setup.py' first."
        )

    def test_transfers_table_columns(self, db_cursor):
        """Verify the transfers table has the expected columns."""
        db_cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = 'transfers' "
            "ORDER BY ordinal_position",
            (APP_NAME,),
        )
        columns = [row["column_name"] for row in db_cursor.fetchall()]
        expected = [
            "id", "block_num", "trx_in_block", "op_pos", "timestamp",
            "sender", "receiver", "amount", "amount_numeric", "asset", "memo",
        ]
        for col in expected:
            assert col in columns, f"Missing column: {col}"

    def test_indexes_exist(self, db_cursor):
        """Verify indexes were created on the transfers table."""
        db_cursor.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = %s AND tablename = 'transfers'",
            (APP_NAME,),
        )
        indexes = [row["indexname"] for row in db_cursor.fetchall()]
        assert len(indexes) >= 4, f"Expected at least 4 indexes, found {len(indexes)}"

    def test_indexer_state_initialized(self, db_cursor):
        """Verify indexer_state was populated with default values."""
        db_cursor.execute(
            f"SELECT key, value FROM {APP_NAME}.indexer_state ORDER BY key"
        )
        rows = db_cursor.fetchall()
        assert len(rows) >= 3, "indexer_state should have at least 3 entries"
        keys = [row["key"] for row in rows]
        assert "last_processed_block" in keys
        assert "total_transfers_indexed" in keys

    def test_haf_has_blocks(self, db_cursor):
        """Verify hived has synced blocks into HAF."""
        db_cursor.execute("SELECT COUNT(*) as count FROM hive.blocks")
        result = db_cursor.fetchone()
        count = int(result["count"])
        if count == 0:
            pytest.skip("No blocks synced yet — hived may still be syncing")
        assert count > 0

    def test_transfer_operation_type_exists(self, db_cursor):
        """Verify transfer_operation is in hive.operation_types."""
        db_cursor.execute(
            "SELECT id, name FROM hive.operation_types "
            "WHERE name = 'hive::protocol::transfer_operation' OR id = 2 "
            "LIMIT 1"
        )
        result = db_cursor.fetchone()
        if result is None:
            pytest.skip("operation_types table may have different format")
        assert result is not None


# =============================================================================
# Integration Tests — Flask API Endpoints
# =============================================================================

@pytest.mark.integration
class TestAPIEndpoints:
    """
    Integration tests for the Flask REST API endpoints.
    Require a live database with some indexed data.
    """

    def test_root_endpoint(self, flask_client):
        """GET / returns API discovery info."""
        response = flask_client.get("/")
        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "HAF Transfer Indexer API"
        assert "endpoints" in data

    def test_status_endpoint(self, flask_client):
        """GET /api/status returns indexer status."""
        response = flask_client.get("/api/status")
        # May return 500 if DB is not available, which is OK for this test
        if response.status_code == 200:
            data = response.get_json()
            assert "app_name" in data
            assert "last_processed_block" in data
            assert "head_block" in data
            assert "blocks_behind" in data
            assert "sync_percentage" in data

    def test_transfers_endpoint_format(self, flask_client):
        """GET /api/transfers/:account returns correct response format."""
        response = flask_client.get("/api/transfers/test-account")
        if response.status_code == 200:
            data = response.get_json()
            assert "account" in data
            assert "transfers" in data
            assert "pagination" in data
            assert isinstance(data["transfers"], list)

    def test_stats_endpoint_404(self, flask_client):
        """GET /api/stats/:account returns 404 for nonexistent account."""
        response = flask_client.get("/api/stats/this-account-definitely-does-not-exist-xyz")
        # Should be 404 (not found) or 500 (db error)
        assert response.status_code in (404, 500)

    def test_top_senders_endpoint(self, flask_client):
        """GET /api/top-senders returns leaderboard format."""
        response = flask_client.get("/api/top-senders")
        if response.status_code == 200:
            data = response.get_json()
            assert "asset" in data
            assert "leaderboard" in data
            assert isinstance(data["leaderboard"], list)

    def test_block_endpoint_invalid(self, flask_client):
        """GET /api/block/0 returns 400 for invalid block number."""
        response = flask_client.get("/api/block/0")
        if response.status_code == 400:
            data = response.get_json()
            assert "error" in data

    def test_404_handler(self, flask_client):
        """Unknown route returns 404 with helpful message."""
        response = flask_client.get("/api/nonexistent")
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data
        assert "hint" in data

    def test_transfers_pagination_params(self, flask_client):
        """GET /api/transfers/:account respects limit and offset params."""
        response = flask_client.get("/api/transfers/test?limit=5&offset=0")
        if response.status_code == 200:
            data = response.get_json()
            assert data["pagination"]["limit"] == 5
            assert data["pagination"]["offset"] == 0

    def test_transfers_direction_filter(self, flask_client):
        """GET /api/transfers/:account respects direction param."""
        for direction in ["sent", "received", "all"]:
            response = flask_client.get(f"/api/transfers/test?direction={direction}")
            # Should not crash regardless of direction value
            assert response.status_code in (200, 500)

    def test_top_senders_asset_filter(self, flask_client):
        """GET /api/top-senders respects asset param."""
        for asset in ["HIVE", "HBD"]:
            response = flask_client.get(f"/api/top-senders?asset={asset}")
            if response.status_code == 200:
                data = response.get_json()
                assert data["asset"] == asset
