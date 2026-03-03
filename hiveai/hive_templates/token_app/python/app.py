"""
=============================================================================
Hive Engine Token Operations API (Python / Flask)
=============================================================================

ARCHITECTURE OVERVIEW — How Hive Engine Works:

Hive Engine is a Layer 2 (L2) sidechain built on top of Hive (Layer 1 / L1).
It enables custom token creation, transfers, staking, and a decentralized
exchange (DEX) — features not natively available on Hive's base layer.

THE LAYER 1 / LAYER 2 BRIDGE:

  1. A user wants to transfer 10 BEE tokens to another account.
  2. This app constructs a JSON payload describing the operation.
  3. The payload is wrapped in a "custom_json" operation and broadcast to
     the Hive LAYER 1 blockchain (using beem and the user's active key).
  4. Hive Engine sidechain nodes watch the L1 blockchain for custom_json ops
     with id="ssc-mainnet-hive".
  5. When they see one, they parse the JSON payload, validate it, and execute
     the token operation on their sidechain database.
  6. The sidechain maintains its own state: token balances, market orders,
     staking records, etc.

So: Layer 1 is the TRANSPORT (immutable, trustless), and Layer 2 is the
EXECUTION ENGINE (fast, feature-rich, indexed by sidechain nodes).

TWO APIs IN PLAY:
  - Hive RPC (api.hive.blog): For broadcasting custom_json ops to Layer 1
  - Hive Engine RPC (api.hive-engine.com): For reading sidechain state

KEY CONCEPTS:
  - HIVE/HBD: Native Layer 1 tokens, handled by hived consensus
  - BEE, DEC, SPS, etc.: Layer 2 tokens, handled by Hive Engine sidechain
  - custom_json: The Hive L1 operation type used as the bridge
  - "ssc-mainnet-hive": The custom_json ID that Hive Engine nodes watch for
  - Active key: Required because token ops are financial (not social/posting)

=============================================================================
"""

import json
import os
import re
from typing import Optional

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

# beem is the comprehensive Python library for the Hive blockchain.
# It handles key management, transaction building, signing, and broadcasting
# to Hive Layer 1 nodes. It's the Python equivalent of @hiveio/dhive.
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json

# Load environment variables from .env file (must be done before accessing os.environ)
load_dotenv()

# =============================================================================
# Configuration
# =============================================================================

# Your Hive blockchain account name (the @username without the @)
HIVE_ACCOUNT = os.environ.get("HIVE_ACCOUNT", "")

# Your Hive ACTIVE private key (starts with 5...)
# WHY ACTIVE KEY: Hive has a key hierarchy:
#   - Owner key: account recovery only (never use in apps)
#   - Active key: financial operations (transfers, staking, market orders)
#   - Posting key: social operations (posts, votes, comments)
# Token operations are FINANCIAL, so they require the active key.
HIVE_ACTIVE_KEY = os.environ.get("HIVE_ACTIVE_KEY", "")

# Hive Layer 1 RPC node — broadcasts custom_json transactions to the blockchain.
# These nodes run hived (the Hive daemon) and serve the main blockchain API.
HIVE_NODE = os.environ.get("HIVE_NODE", "https://api.hive.blog")

# Hive Engine Layer 2 API — queries sidechain state (balances, tokens, markets).
# This is NOT a blockchain node. It's the Hive Engine sidechain API that indexes
# custom_json operations from Layer 1 and maintains token/market state.
HIVE_ENGINE_API = os.environ.get("HIVE_ENGINE_API", "https://api.hive-engine.com/rpc")

# Flask server port
PORT = int(os.environ.get("PORT", 3002))

# =============================================================================
# Initialize Hive Blockchain Connection
# =============================================================================

# Initialize beem's Hive instance with the active key and node list.
# beem connects to Hive Layer 1 nodes for broadcasting transactions.
# Multiple nodes are specified for automatic failover if one goes down.
#
# The keys parameter accepts private keys for signing transactions.
# Only the active key is needed for Hive Engine operations (financial ops).
# NEVER pass your owner key to an application.
hive_instance = None
if HIVE_ACTIVE_KEY:
    hive_instance = Hive(
        node=[
            HIVE_NODE,
            "https://api.deathwing.me",      # Backup node for reliability
            "https://api.openhive.network",   # Another backup node
        ],
        keys=[HIVE_ACTIVE_KEY],  # Active key for signing financial operations
    )

app = Flask(__name__)

# =============================================================================
# Helper: Query Hive Engine Sidechain via JSON-RPC
# =============================================================================


def query_hive_engine(
    contract: str,
    table: str,
    query: dict = None,
    limit: int = 1000,
    offset: int = 0,
    indexes: list = None,
) -> list:
    """
    Sends a JSON-RPC request to the Hive Engine sidechain API.

    The Hive Engine API uses a JSON-RPC interface where you specify:
      - contract: Which smart contract to query (tokens, market, etc.)
      - table: Which data table within that contract
      - query: MongoDB-style query filter

    Hive Engine uses a smart contract system. Key contracts:
      - "tokens": Token definitions, balances, staking
      - "market": DEX order book, trade history
      - "mining": Token mining pools
      - "nft": Non-fungible tokens

    Args:
        contract: The smart contract name (e.g., "tokens", "market")
        table: The table to query within the contract
        query: MongoDB-style filter object (default: {} for all records)
        limit: Maximum number of results to return
        offset: Number of results to skip (for pagination)
        indexes: Optional sort indexes list

    Returns:
        List of matching records from the sidechain
    """
    if query is None:
        query = {}
    if indexes is None:
        indexes = []

    # The Hive Engine API endpoint for reading contract state.
    # "find" retrieves multiple records matching the query.
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "find",  # "find" returns multiple matching records
        "params": {
            "contract": contract,  # Which smart contract (tokens, market, etc.)
            "table": table,        # Which table in that contract
            "query": query,        # MongoDB-style filter (e.g., {"symbol": "BEE"})
            "limit": limit,        # Max results per page
            "offset": offset,      # Skip this many results (pagination)
            "indexes": indexes,    # Sort order
        },
    }

    # Send the JSON-RPC request to the Hive Engine sidechain API.
    # This reads from the SIDECHAIN state, not from Layer 1.
    response = requests.post(HIVE_ENGINE_API, json=payload, timeout=30)
    response.raise_for_status()

    # The sidechain returns results in the standard JSON-RPC "result" field
    data = response.json()
    return data.get("result", [])


def query_hive_engine_one(contract: str, table: str, query: dict = None) -> Optional[dict]:
    """
    Query a single record from Hive Engine sidechain.
    Uses "findOne" instead of "find" to return exactly one result or None.

    Args:
        contract: The smart contract name
        table: The table to query
        query: MongoDB-style filter

    Returns:
        Single matching record dict, or None if not found
    """
    if query is None:
        query = {}

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "findOne",  # Returns single record instead of array
        "params": {
            "contract": contract,
            "table": table,
            "query": query,
        },
    }

    response = requests.post(HIVE_ENGINE_API, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("result")


# =============================================================================
# Helper: Broadcast Custom JSON to Hive Layer 1
# =============================================================================


def broadcast_hive_engine_op(
    contract_name: str,
    contract_action: str,
    contract_payload: dict,
    account: str,
) -> dict:
    """
    Broadcasts a Hive Engine operation to the Hive Layer 1 blockchain.

    THIS IS THE CORE BRIDGE BETWEEN LAYER 1 AND LAYER 2:

    Every Hive Engine operation (transfer, stake, buy, sell, etc.) is encoded as
    a JSON payload and broadcast as a "custom_json" operation on Hive Layer 1.

    The custom_json operation structure:
      - id: "ssc-mainnet-hive" — tells Hive Engine nodes to process it
      - required_auths: [account] — requires the account's ACTIVE key signature
      - required_posting_auths: [] — posting key is NOT sufficient for financial ops
      - json: stringified JSON containing the contract call details

    The JSON payload structure:
      {
        "contractName": "tokens",        // Which sidechain contract to call
        "contractAction": "transfer",    // Which function on that contract
        "contractPayload": { ... }       // Arguments to the function
      }

    After broadcast, Hive Engine sidechain nodes:
      1. See the custom_json in a new Hive block (3 second block time)
      2. Verify the JSON payload is valid
      3. Execute the contract action on their local sidechain database
      4. The sidechain state update is deterministic — all nodes reach consensus

    WHY ACTIVE KEY (not posting key):
      Hive's key hierarchy separates concerns:
      - Posting key: social actions (posts, votes) — low risk if compromised
      - Active key: financial actions (transfers, market orders) — high value
      - Owner key: account recovery — highest security
      Token operations move value, so they require "required_auths" (active key).

    Args:
        contract_name: Sidechain contract (e.g., "tokens", "market")
        contract_action: Action to perform (e.g., "transfer", "stake")
        contract_payload: Arguments for the action
        account: Hive account broadcasting the operation

    Returns:
        Transaction result dict with transaction_id and block_num

    Raises:
        RuntimeError: If hive_instance is not configured with keys
        Exception: If broadcast fails
    """
    if hive_instance is None:
        raise RuntimeError(
            "Hive instance not configured. Set HIVE_ACTIVE_KEY in .env file."
        )

    # Construct the Hive Engine JSON payload.
    # This follows the Hive Engine smart contract calling convention.
    json_data = json.dumps({
        "contractName": contract_name,      # e.g., "tokens" — the smart contract
        "contractAction": contract_action,  # e.g., "transfer" — the function to call
        "contractPayload": contract_payload # e.g., {symbol, to, quantity, memo}
    })

    # Build a Hive Layer 1 transaction containing the custom_json operation.
    # TransactionBuilder lets us construct the exact operation we need.
    tx = TransactionBuilder(blockchain_instance=hive_instance)

    # Create the custom_json operation.
    # This is the Layer 1 operation that bridges to Layer 2:
    #
    #   {
    #     "type": "custom_json",
    #     "required_auths": ["youraccount"],      # Active key authorization
    #     "required_posting_auths": [],            # Empty — not a social op
    #     "id": "ssc-mainnet-hive",                # Hive Engine's listener ID
    #     "json": "{\"contractName\":...}"         # The operation payload
    #   }
    #
    # When this gets included in a Hive block (~3 seconds), Hive Engine
    # sidechain nodes will parse it and execute the contract action.
    tx.appendOps(
        Custom_json(
            **{
                "required_auths": [account],       # Active key auth — required for financial ops
                "required_posting_auths": [],      # Empty — we're using active, not posting
                "id": "ssc-mainnet-hive",          # THE critical identifier — HE watches for this
                "json": json_data,                 # Stringified contract call payload
            }
        )
    )

    # Sign the transaction with the active key and broadcast to Hive Layer 1.
    # beem automatically picks the correct key from the keys we provided at init.
    tx.appendSigner(account, "active")  # Use the active key for signing
    tx.sign()                           # Cryptographically sign the transaction

    # Broadcast to Hive Layer 1 nodes. The transaction gets included in the
    # next block (every 3 seconds). Hive Engine will process it shortly after.
    result = tx.broadcast()

    return result


# =============================================================================
# Input Validation Helpers
# =============================================================================


def validate_account(account: str) -> Optional[str]:
    """
    Validates a Hive account name.

    Hive account names follow strict rules:
      - 3 to 16 characters long
      - Lowercase letters, digits, hyphens, and dots only
      - Must start with a letter
      - Cannot have consecutive dots or hyphens

    Args:
        account: Account name to validate

    Returns:
        Error message string if invalid, None if valid
    """
    if not account or not isinstance(account, str):
        return "Account name is required"
    # Hive account names: 3-16 chars, lowercase alphanumeric + hyphens/dots
    if not re.match(r"^[a-z][a-z0-9\-.]{2,15}$", account):
        return "Invalid Hive account name. Must be 3-16 lowercase characters, starting with a letter."
    return None


def validate_symbol(symbol: str) -> Optional[str]:
    """
    Validates a Hive Engine token symbol.

    Token symbols on Hive Engine:
      - 1 to 10 characters
      - Uppercase letters, digits, and dots
      - Must start with a letter
      - Examples: BEE, DEC, SPS, SWAP.HIVE, LEO

    Note: Dots are used in wrapped tokens (e.g., SWAP.HIVE = wrapped HIVE on L2).

    Args:
        symbol: Token symbol to validate

    Returns:
        Error message string if invalid, None if valid
    """
    if not symbol or not isinstance(symbol, str):
        return "Token symbol is required"
    # Hive Engine symbols: uppercase letters, digits, and dots (for wrapped tokens)
    if not re.match(r"^[A-Z][A-Z0-9.]{0,9}$", symbol):
        return "Invalid token symbol. Must be 1-10 uppercase characters (letters, digits, dots)."
    return None


def validate_quantity(quantity: str) -> Optional[str]:
    """
    Validates a token quantity string.

    Hive Engine quantities are strings (not floats) to avoid floating-point
    precision issues. The blockchain requires exact string representation.

    Args:
        quantity: Quantity string like "10.000" or "0.5"

    Returns:
        Error message string if invalid, None if valid
    """
    if not quantity or not isinstance(quantity, str):
        return 'Quantity is required and must be a string (e.g., "10.000")'
    # Must be a positive decimal number
    if not re.match(r"^\d+(\.\d+)?$", quantity) or float(quantity) <= 0:
        return 'Quantity must be a positive number string (e.g., "10.000")'
    return None


def validate_price(price: str) -> Optional[str]:
    """
    Validates a price string for market orders.

    Prices on the Hive Engine DEX are denominated in SWAP.HIVE (the wrapped
    version of HIVE on Layer 2). All prices are strings to maintain precision.

    Args:
        price: Price string like "0.001" or "1.50"

    Returns:
        Error message string if invalid, None if valid
    """
    if not price or not isinstance(price, str):
        return 'Price is required and must be a string (e.g., "0.001")'
    if not re.match(r"^\d+(\.\d+)?$", price) or float(price) <= 0:
        return 'Price must be a positive number string (e.g., "0.001")'
    return None


# =============================================================================
# Route: GET /api/tokens — List All Hive Engine Tokens
# =============================================================================


@app.route("/api/tokens", methods=["GET"])
def list_tokens():
    """
    Lists all tokens registered on the Hive Engine sidechain.

    This queries the "tokens" contract's "tokens" table on Hive Engine.
    Each token record includes:
      - symbol: The ticker (e.g., "BEE", "DEC", "SPS")
      - name: Human-readable name
      - issuer: The Hive account that created the token
      - supply: Current circulating supply
      - maxSupply: Maximum possible supply (set at creation, immutable)
      - precision: Decimal places (0-8)
      - stakingEnabled: Whether tokens can be staked for governance/rewards
      - delegationEnabled: Whether staked tokens can be delegated

    There are thousands of tokens on Hive Engine, so we paginate.

    Query params:
      ?limit=100    Number of tokens per page (default 100, max 1000)
      ?offset=0     Skip this many tokens (for pagination)
    """
    try:
        limit = min(int(request.args.get("limit", 100)), 1000)
        offset = int(request.args.get("offset", 0))

        # Query the "tokens" contract, "tokens" table on the Hive Engine sidechain.
        # Empty query {} returns all tokens. Results are paginated.
        tokens = query_hive_engine(
            contract="tokens",  # Contract: the token management smart contract
            table="tokens",     # Table: the registry of all token definitions
            query={},           # Query: empty = all tokens
            limit=limit,        # Pagination: max results
            offset=offset,      # Pagination: skip count
            indexes=[{"index": "symbol", "descending": False}],  # Sort alphabetically
        )

        return jsonify({
            "success": True,
            "count": len(tokens),
            "offset": offset,
            "limit": limit,
            "data": tokens,
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Failed to fetch tokens from Hive Engine sidechain: {str(e)}",
        }), 500


# =============================================================================
# Route: GET /api/token/<symbol> — Get Single Token Details
# =============================================================================


@app.route("/api/token/<symbol>", methods=["GET"])
def get_token(symbol: str):
    """
    Retrieves detailed information about a specific Hive Engine token.

    Returns the full token record including supply, precision, staking config,
    and the unstaking cooldown period.

    STAKING MECHANICS:
      When you stake tokens, they become "locked" in exchange for governance power
      or reward eligibility. Staked tokens cannot be transferred or sold.
      To get them back, you must "unstake", which triggers a cooldown period
      (set by the token creator, often 7-28 days) before they become liquid again.
      This prevents dump-and-run attacks on token governance.
    """
    try:
        symbol = symbol.upper()
        symbol_error = validate_symbol(symbol)
        if symbol_error:
            return jsonify({"success": False, "error": symbol_error}), 400

        # Query for a specific token by its symbol.
        # findOne returns None if the token doesn't exist.
        token = query_hive_engine_one(
            contract="tokens",  # Contract: token management
            table="tokens",     # Table: token definitions
            query={"symbol": symbol},  # Query: exact match on symbol
        )

        if not token:
            return jsonify({
                "success": False,
                "error": f"Token {symbol} not found on Hive Engine",
            }), 404

        return jsonify({"success": True, "data": token})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to fetch token details: {str(e)}"}), 500


# =============================================================================
# Route: GET /api/balance/<account> — Get All Token Balances
# =============================================================================


@app.route("/api/balance/<account>", methods=["GET"])
def get_balances(account: str):
    """
    Retrieves all Hive Engine token balances for a given account.

    IMPORTANT DISTINCTION:
      - This returns Layer 2 (Hive Engine) token balances only.
      - Layer 1 balances (HIVE, HBD, VESTS) are NOT included here.
      - To get L1 balances, use beem's Account class directly.

    Each balance record includes:
      - account: The Hive account name
      - symbol: Token symbol (e.g., "BEE")
      - balance: Liquid (transferable) balance as a string
      - stake: Amount of this token currently staked (locked for governance/rewards)
      - pendingUnstake: Amount currently in the unstaking cooldown period
      - delegationsIn: Stake delegated TO this account by others
      - delegationsOut: Stake this account has delegated to others

    A user's "effective stake" = stake + delegationsIn - delegationsOut
    """
    try:
        account = account.lower()
        account_error = validate_account(account)
        if account_error:
            return jsonify({"success": False, "error": account_error}), 400

        # Query the "tokens" contract's "balances" table for all tokens held by this account.
        # Each row represents one token the account has interacted with.
        balances = query_hive_engine(
            contract="tokens",   # Contract: token management
            table="balances",    # Table: per-account, per-token balance records
            query={"account": account},  # Query: all tokens for this specific account
            limit=1000,          # Most accounts hold fewer than 1000 different tokens
            offset=0,
        )

        return jsonify({
            "success": True,
            "account": account,
            "count": len(balances),
            "data": balances,
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Failed to fetch token balances: {str(e)}",
        }), 500


# =============================================================================
# Route: GET /api/balance/<account>/<symbol> — Get Specific Token Balance
# =============================================================================


@app.route("/api/balance/<account>/<symbol>", methods=["GET"])
def get_balance(account: str, symbol: str):
    """
    Retrieves the balance of a specific token for a given account.
    More efficient than fetching all balances when you only need one token.
    Returns zero fields if the account has never held this token.
    """
    try:
        account = account.lower()
        symbol = symbol.upper()

        account_error = validate_account(account)
        if account_error:
            return jsonify({"success": False, "error": account_error}), 400
        symbol_error = validate_symbol(symbol)
        if symbol_error:
            return jsonify({"success": False, "error": symbol_error}), 400

        # Query for the specific account + symbol combination.
        # Returns None if this account has never held this token.
        balance = query_hive_engine_one(
            contract="tokens",                     # Contract: token management
            table="balances",                      # Table: balance records
            query={"account": account, "symbol": symbol},  # Exact match on both
        )

        if not balance:
            # Account has no record for this token — return zero balances
            return jsonify({
                "success": True,
                "data": {
                    "account": account,
                    "symbol": symbol,
                    "balance": "0",
                    "stake": "0",
                    "pendingUnstake": "0",
                    "delegationsIn": "0",
                    "delegationsOut": "0",
                },
            })

        return jsonify({"success": True, "data": balance})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to fetch token balance: {str(e)}"}), 500


# =============================================================================
# Route: POST /api/transfer — Transfer Tokens
# =============================================================================


@app.route("/api/transfer", methods=["POST"])
def transfer_tokens():
    """
    Transfers Hive Engine tokens from the configured account to another.

    HOW THIS WORKS (THE L1/L2 BRIDGE IN ACTION):

      1. Client sends: { symbol: "BEE", to: "alice", quantity: "10.000", memo: "hi" }
      2. We construct a Hive Engine JSON payload:
         {
           contractName: "tokens",
           contractAction: "transfer",
           contractPayload: { symbol: "BEE", to: "alice", quantity: "10.000", memo: "hi" }
         }
      3. This payload is stringified and broadcast as a custom_json operation
         on Hive Layer 1, signed with the sender's active key.
      4. Hive Engine sidechain nodes see the custom_json in the next L1 block.
      5. They validate: Does the sender have enough BEE? Is the quantity valid?
      6. If valid, they debit sender and credit receiver on the sidechain.
      7. The transfer is now complete — queryable via the balances API.

    Expected JSON body:
      {
        "symbol": "BEE",
        "to": "recipient_account",
        "quantity": "10.000",
        "memo": "optional message"
      }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "JSON body required"}), 400

        symbol = data.get("symbol", "")
        to = data.get("to", "")
        quantity = data.get("quantity", "")
        memo = data.get("memo", "")

        # Validate all required fields
        symbol_error = validate_symbol(symbol.upper() if symbol else symbol)
        if symbol_error:
            return jsonify({"success": False, "error": symbol_error}), 400

        to_error = validate_account(to.lower() if to else to)
        if to_error:
            return jsonify({"success": False, "error": f"Invalid recipient: {to_error}"}), 400

        qty_error = validate_quantity(quantity)
        if qty_error:
            return jsonify({"success": False, "error": qty_error}), 400

        # Ensure environment is configured with keys
        if not HIVE_ACCOUNT or not HIVE_ACTIVE_KEY:
            return jsonify({
                "success": False,
                "error": "Server not configured: HIVE_ACCOUNT and HIVE_ACTIVE_KEY required in .env",
            }), 500

        # Broadcast the transfer as a custom_json operation to Hive Layer 1.
        # The "tokens" contract's "transfer" action moves tokens between accounts.
        result = broadcast_hive_engine_op(
            contract_name="tokens",       # contractName: the token management contract
            contract_action="transfer",   # contractAction: the transfer function
            contract_payload={
                "symbol": symbol.upper(),
                "to": to.lower(),
                "quantity": quantity,      # Must be a string matching the token's precision
                "memo": memo or "",       # Memo is optional but always included
            },
            account=HIVE_ACCOUNT,
        )

        # The result contains the Layer 1 transaction info.
        # Note: This confirms the custom_json was included in a Hive block,
        # but the sidechain execution is asynchronous (usually within seconds).
        return jsonify({
            "success": True,
            "message": f"Transfer of {quantity} {symbol.upper()} to {to} broadcast to Hive Layer 1",
            "transaction": result,
            "note": "Transaction broadcast to Layer 1. Sidechain will process within ~3-6 seconds.",
        })
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Transfer failed: {str(e)}"}), 500


# =============================================================================
# Route: POST /api/stake — Stake Tokens
# =============================================================================


@app.route("/api/stake", methods=["POST"])
def stake_tokens():
    """
    Stakes Hive Engine tokens for governance power and/or reward eligibility.

    STAKING MECHANICS:
      - Staking locks your tokens, removing them from your liquid balance.
      - Staked tokens cannot be transferred, sold, or traded.
      - In return, you get governance power (voting weight) and/or reward eligibility.
      - Many Hive Engine communities use staking to determine reward distribution.

      Example: Staking LEO tokens in the LeoFinance community gives you:
        1. Curation rewards (earn LEO by upvoting content)
        2. Governance votes (influence community decisions)
        3. Higher visibility in the community

    You can stake to your own account or to another account.
    Staking is instant. Unstaking requires a cooldown period.

    Expected JSON body:
      {
        "symbol": "BEE",
        "to": "target_account",     (optional, defaults to self)
        "quantity": "100.000"
      }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "JSON body required"}), 400

        symbol = data.get("symbol", "")
        to = data.get("to", HIVE_ACCOUNT)  # Default: stake to self
        quantity = data.get("quantity", "")

        symbol_error = validate_symbol(symbol.upper() if symbol else symbol)
        if symbol_error:
            return jsonify({"success": False, "error": symbol_error}), 400

        stake_target = to.lower() if to else HIVE_ACCOUNT
        to_error = validate_account(stake_target)
        if to_error:
            return jsonify({"success": False, "error": f"Invalid target: {to_error}"}), 400

        qty_error = validate_quantity(quantity)
        if qty_error:
            return jsonify({"success": False, "error": qty_error}), 400

        if not HIVE_ACCOUNT or not HIVE_ACTIVE_KEY:
            return jsonify({
                "success": False,
                "error": "Server not configured: HIVE_ACCOUNT and HIVE_ACTIVE_KEY required",
            }), 500

        # Broadcast the stake operation to Hive Layer 1.
        # The "tokens" contract's "stake" action locks tokens and updates the stake balance.
        result = broadcast_hive_engine_op(
            contract_name="tokens",    # contractName: token management contract
            contract_action="stake",   # contractAction: stake function — locks tokens
            contract_payload={
                "to": stake_target,    # Account receiving the staked tokens (usually self)
                "symbol": symbol.upper(),
                "quantity": quantity,   # Amount to move from liquid to staked balance
            },
            account=HIVE_ACCOUNT,
        )

        return jsonify({
            "success": True,
            "message": f"Staked {quantity} {symbol.upper()} to {stake_target}",
            "transaction": result,
            "note": "Staking is instant. Tokens moved from liquid to staked balance.",
        })
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Stake failed: {str(e)}"}), 500


# =============================================================================
# Route: POST /api/unstake — Begin Unstaking (Cooldown Period)
# =============================================================================


@app.route("/api/unstake", methods=["POST"])
def unstake_tokens():
    """
    Begins the unstaking process for Hive Engine tokens.

    UNSTAKING COOLDOWN:
      Unlike staking (which is instant), unstaking has a COOLDOWN period.
      This is a security/governance feature that prevents "vote-and-dump" attacks:

      1. You call unstake for X tokens.
      2. The tokens enter "pendingUnstake" status — they are still locked.
      3. After the cooldown period (set by the token creator, e.g., 7 days),
         the tokens automatically move back to your liquid balance.
      4. During cooldown, the tokens do NOT earn rewards or provide governance power.

      The cooldown period varies by token:
        - BEE: 3 days (short, since it's the platform utility token)
        - LEO: 28 days (long, to encourage commitment)
        - Each token's unstakingCooldown is set at creation time.

    Expected JSON body:
      {
        "symbol": "BEE",
        "quantity": "50.000"
      }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "JSON body required"}), 400

        symbol = data.get("symbol", "")
        quantity = data.get("quantity", "")

        symbol_error = validate_symbol(symbol.upper() if symbol else symbol)
        if symbol_error:
            return jsonify({"success": False, "error": symbol_error}), 400

        qty_error = validate_quantity(quantity)
        if qty_error:
            return jsonify({"success": False, "error": qty_error}), 400

        if not HIVE_ACCOUNT or not HIVE_ACTIVE_KEY:
            return jsonify({
                "success": False,
                "error": "Server not configured: HIVE_ACCOUNT and HIVE_ACTIVE_KEY required",
            }), 500

        # Broadcast the unstake operation to Hive Layer 1.
        # The "tokens" contract's "unstake" action initiates the cooldown period.
        # Tokens move from "stake" to "pendingUnstake" immediately.
        # After the cooldown, they automatically become liquid again.
        result = broadcast_hive_engine_op(
            contract_name="tokens",      # contractName: token management contract
            contract_action="unstake",   # contractAction: begin unstaking cooldown
            contract_payload={
                "symbol": symbol.upper(),
                "quantity": quantity,     # Amount to begin unstaking
            },
            account=HIVE_ACCOUNT,
        )

        return jsonify({
            "success": True,
            "message": f"Unstaking {quantity} {symbol.upper()} — cooldown period has begun",
            "transaction": result,
            "note": "Tokens are now in pendingUnstake. They will become liquid after the cooldown period.",
        })
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Unstake failed: {str(e)}"}), 500


# =============================================================================
# Route: GET /api/market/<symbol> — Get Order Book
# =============================================================================


@app.route("/api/market/<symbol>", methods=["GET"])
def get_market(symbol: str):
    """
    Retrieves the DEX order book for a Hive Engine token.

    HIVE ENGINE DEX (Decentralized Exchange):
      Hive Engine has a built-in order-book DEX where tokens trade against SWAP.HIVE.

      SWAP.HIVE is the wrapped version of HIVE on Layer 2:
        - You deposit HIVE (Layer 1) into the @honey-swap gateway account.
        - You receive SWAP.HIVE (Layer 2) at a 1:1 ratio.
        - SWAP.HIVE is the base trading pair for ALL tokens on the DEX.

      Order Book:
        - Buy orders (bids): People willing to buy the token with SWAP.HIVE
        - Sell orders (asks): People willing to sell the token for SWAP.HIVE
        - Orders are sorted by price (best prices first)
        - When a buy price meets a sell price, the trade executes automatically

      This is a LIMIT ORDER book (not AMM). You specify exact price and quantity.

    Query params:
      ?limit=50    Number of orders per side (default 50)
    """
    try:
        symbol = symbol.upper()
        symbol_error = validate_symbol(symbol)
        if symbol_error:
            return jsonify({"success": False, "error": symbol_error}), 400

        limit = min(int(request.args.get("limit", 50)), 500)

        # Fetch buy orders (bids) from the "market" contract's "buyBook" table.
        # Buy orders are sorted by price descending (highest bid first).
        buy_orders = query_hive_engine(
            contract="market",   # Contract: the DEX smart contract
            table="buyBook",     # Table: open buy orders
            query={"symbol": symbol},  # Orders for this specific token
            limit=limit,
            offset=0,
            indexes=[{"index": "priceDec", "descending": True}],  # Highest price first
        )

        # Fetch sell orders (asks) from the "market" contract's "sellBook" table.
        # Sell orders are sorted by price ascending (lowest ask first).
        sell_orders = query_hive_engine(
            contract="market",   # Contract: the DEX smart contract
            table="sellBook",    # Table: open sell orders
            query={"symbol": symbol},  # Orders for this specific token
            limit=limit,
            offset=0,
            indexes=[{"index": "priceDec", "descending": False}],  # Lowest price first
        )

        # Calculate spread: gap between highest bid and lowest ask.
        # Tight spread = liquid market; wide spread = thin liquidity.
        highest_bid = float(buy_orders[0]["price"]) if buy_orders else 0
        lowest_ask = float(sell_orders[0]["price"]) if sell_orders else 0
        spread = (lowest_ask - highest_bid) if (lowest_ask > 0 and highest_bid > 0) else None

        return jsonify({
            "success": True,
            "symbol": symbol,
            "market_pair": f"{symbol}/SWAP.HIVE",      # All tokens trade against SWAP.HIVE
            "highest_bid": highest_bid or None,          # Best buy price
            "lowest_ask": lowest_ask or None,            # Best sell price
            "spread": f"{spread:.8f}" if spread is not None else None,
            "buy_orders": buy_orders,
            "sell_orders": sell_orders,
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to fetch market data: {str(e)}"}), 500


# =============================================================================
# Route: POST /api/market/buy — Place Buy Order on DEX
# =============================================================================


@app.route("/api/market/buy", methods=["POST"])
def market_buy():
    """
    Places a LIMIT BUY order on the Hive Engine DEX.

    HOW DEX ORDERS WORK:
      1. You specify: I want to buy X tokens at Y price (SWAP.HIVE per token).
      2. The total cost is X * Y in SWAP.HIVE, deducted from your SWAP.HIVE balance.
      3. If there are sell orders at or below your price, they match instantly (fill).
      4. Any unfilled portion sits in the buy order book until filled or cancelled.
      5. There is NO expiration — orders remain until filled or manually cancelled.

      Example: Buy 100 BEE at 0.01 SWAP.HIVE each = costs 1.0 SWAP.HIVE total

    IMPORTANT: You need SWAP.HIVE balance (not regular HIVE) to place buy orders.
      To get SWAP.HIVE: deposit HIVE via https://tribaldex.com/wallet/

    Expected JSON body:
      {
        "symbol": "BEE",
        "quantity": "100.000",
        "price": "0.01000000"
      }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "JSON body required"}), 400

        symbol = data.get("symbol", "")
        quantity = data.get("quantity", "")
        price = data.get("price", "")

        symbol_error = validate_symbol(symbol.upper() if symbol else symbol)
        if symbol_error:
            return jsonify({"success": False, "error": symbol_error}), 400

        qty_error = validate_quantity(quantity)
        if qty_error:
            return jsonify({"success": False, "error": qty_error}), 400

        price_error = validate_price(price)
        if price_error:
            return jsonify({"success": False, "error": price_error}), 400

        if not HIVE_ACCOUNT or not HIVE_ACTIVE_KEY:
            return jsonify({
                "success": False,
                "error": "Server not configured: HIVE_ACCOUNT and HIVE_ACTIVE_KEY required",
            }), 500

        # Broadcast the buy order to Hive Layer 1.
        # The "market" contract's "buy" action places a limit buy order on the DEX.
        # If matching sell orders exist at or below this price, they fill immediately.
        result = broadcast_hive_engine_op(
            contract_name="market",    # contractName: the DEX smart contract
            contract_action="buy",     # contractAction: place a buy order
            contract_payload={
                "symbol": symbol.upper(),
                "quantity": quantity,   # Number of tokens to buy
                "price": price,        # Price per token in SWAP.HIVE
            },
            account=HIVE_ACCOUNT,
        )

        total_cost = f"{float(quantity) * float(price):.8f}"

        return jsonify({
            "success": True,
            "message": f"Buy order placed: {quantity} {symbol.upper()} at {price} SWAP.HIVE each",
            "total_cost": f"{total_cost} SWAP.HIVE",
            "transaction": result,
            "note": "Order may fill immediately if matching sell orders exist at this price or lower.",
        })
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Buy order failed: {str(e)}"}), 500


# =============================================================================
# Route: POST /api/market/sell — Place Sell Order on DEX
# =============================================================================


@app.route("/api/market/sell", methods=["POST"])
def market_sell():
    """
    Places a LIMIT SELL order on the Hive Engine DEX.

    HOW SELL ORDERS WORK:
      1. You specify: I want to sell X tokens at Y price (SWAP.HIVE per token).
      2. X tokens are deducted from your liquid balance and held in escrow.
      3. If there are buy orders at or above your price, they match instantly (fill).
      4. Any unfilled portion sits in the sell order book until filled or cancelled.
      5. When filled, you receive SWAP.HIVE at the order price.

      Example: Sell 100 BEE at 0.012 SWAP.HIVE each = receive 1.2 SWAP.HIVE total

    IMPORTANT: You need liquid (unstaked) tokens to sell. Staked tokens cannot be sold.

    Expected JSON body:
      {
        "symbol": "BEE",
        "quantity": "100.000",
        "price": "0.01200000"
      }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "JSON body required"}), 400

        symbol = data.get("symbol", "")
        quantity = data.get("quantity", "")
        price = data.get("price", "")

        symbol_error = validate_symbol(symbol.upper() if symbol else symbol)
        if symbol_error:
            return jsonify({"success": False, "error": symbol_error}), 400

        qty_error = validate_quantity(quantity)
        if qty_error:
            return jsonify({"success": False, "error": qty_error}), 400

        price_error = validate_price(price)
        if price_error:
            return jsonify({"success": False, "error": price_error}), 400

        if not HIVE_ACCOUNT or not HIVE_ACTIVE_KEY:
            return jsonify({
                "success": False,
                "error": "Server not configured: HIVE_ACCOUNT and HIVE_ACTIVE_KEY required",
            }), 500

        # Broadcast the sell order to Hive Layer 1.
        # The "market" contract's "sell" action places a limit sell order on the DEX.
        # If matching buy orders exist at or above this price, they fill immediately.
        result = broadcast_hive_engine_op(
            contract_name="market",    # contractName: the DEX smart contract
            contract_action="sell",    # contractAction: place a sell order
            contract_payload={
                "symbol": symbol.upper(),
                "quantity": quantity,   # Number of tokens to sell
                "price": price,        # Price per token in SWAP.HIVE
            },
            account=HIVE_ACCOUNT,
        )

        total_proceeds = f"{float(quantity) * float(price):.8f}"

        return jsonify({
            "success": True,
            "message": f"Sell order placed: {quantity} {symbol.upper()} at {price} SWAP.HIVE each",
            "total_proceeds": f"{total_proceeds} SWAP.HIVE (if fully filled)",
            "transaction": result,
            "note": "Order may fill immediately if matching buy orders exist at this price or higher.",
        })
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Sell order failed: {str(e)}"}), 500


# =============================================================================
# Route: GET /api/history/<account>/<symbol> — Transaction History
# =============================================================================


@app.route("/api/history/<account>/<symbol>", methods=["GET"])
def get_history(account: str, symbol: str):
    """
    Retrieves transaction history for a specific account and token on Hive Engine.

    HOW HISTORY WORKS ON HIVE ENGINE:
      The Hive Engine sidechain maintains a transaction history table that records
      every operation affecting token balances: transfers, stakes, unstakes, market
      fills, rewards, etc.

      Note: This history is maintained by the SIDECHAIN, not Layer 1.
      The Layer 1 blockchain has the raw custom_json operations, but the sidechain
      provides a more structured, indexed history that's easier to query.

    Query params:
      ?limit=50    Number of transactions (default 50, max 500)
      ?offset=0    Pagination offset
    """
    try:
        account = account.lower()
        symbol = symbol.upper()

        account_error = validate_account(account)
        if account_error:
            return jsonify({"success": False, "error": account_error}), 400
        symbol_error = validate_symbol(symbol)
        if symbol_error:
            return jsonify({"success": False, "error": symbol_error}), 400

        limit = min(int(request.args.get("limit", 50)), 500)
        offset = int(request.args.get("offset", 0))

        # Try the accountHistory endpoint first (available on some HE API nodes).
        # This provides a unified view of all operations for an account+token.
        try:
            base_url = HIVE_ENGINE_API.replace("/rpc", "")
            response = requests.get(
                f"{base_url}/accountHistory",
                params={
                    "account": account,
                    "symbol": symbol,
                    "limit": limit,
                    "offset": offset,
                },
                timeout=30,
            )
            response.raise_for_status()
            history = response.json() or []

            return jsonify({
                "success": True,
                "account": account,
                "symbol": symbol,
                "count": len(history),
                "offset": offset,
                "limit": limit,
                "data": history,
            })
        except Exception:
            # Fallback: Query the sidechain's transferHistory table directly.
            # Some Hive Engine API nodes may not support the accountHistory endpoint.
            pass

        # Fallback: Query sent and received transactions separately and merge them.
        sent = query_hive_engine(
            contract="tokens",
            table="transferHistory",
            query={"from": account, "symbol": symbol},
            limit=limit,
            offset=offset,
        )

        received = query_hive_engine(
            contract="tokens",
            table="transferHistory",
            query={"to": account, "symbol": symbol},
            limit=limit,
            offset=offset,
        )

        # Merge, deduplicate, and sort by timestamp descending (newest first)
        merged = sent + received
        seen = set()
        unique = []
        for tx in merged:
            key = tx.get("_id", json.dumps(tx, sort_keys=True))
            if key not in seen:
                seen.add(key)
                unique.append(tx)
        unique.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

        return jsonify({
            "success": True,
            "account": account,
            "symbol": symbol,
            "count": len(unique[:limit]),
            "data": unique[:limit],
            "note": "Fallback to transferHistory query. May not include staking/market transactions.",
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Failed to fetch transaction history: {str(e)}",
        }), 500


# =============================================================================
# Route: GET / — API Info (Root)
# =============================================================================


@app.route("/", methods=["GET"])
def api_info():
    """Returns API documentation at the root endpoint."""
    return jsonify({
        "name": "Hive Engine Token Operations API (Python)",
        "version": "1.0.0",
        "description": "REST API for Hive Engine Layer 2 token operations",
        "architecture": {
            "layer1": "Hive blockchain — immutable ledger, transaction transport via custom_json",
            "layer2": "Hive Engine sidechain — token state, DEX, staking, smart contracts",
            "bridge": 'custom_json operations with id="ssc-mainnet-hive" on Layer 1',
        },
        "endpoints": {
            "GET /api/tokens": "List all Hive Engine tokens (paginated)",
            "GET /api/token/<symbol>": "Get details for a specific token",
            "GET /api/balance/<account>": "Get all token balances for an account",
            "GET /api/balance/<account>/<symbol>": "Get specific token balance",
            "POST /api/transfer": "Transfer tokens (requires active key)",
            "POST /api/stake": "Stake tokens for governance/rewards",
            "POST /api/unstake": "Begin unstaking (cooldown period)",
            "GET /api/market/<symbol>": "Get DEX order book for a token",
            "POST /api/market/buy": "Place limit buy order on DEX",
            "POST /api/market/sell": "Place limit sell order on DEX",
            "GET /api/history/<account>/<symbol>": "Transaction history",
        },
    })


# =============================================================================
# Start Server
# =============================================================================

if __name__ == "__main__":
    print(f"\n=== Hive Engine Token Operations API (Python) ===")
    print(f"Server running on http://localhost:{PORT}")
    print(f"\nConfigured account: {HIVE_ACCOUNT or '(not set — read-only mode)'}")
    print(f"Hive L1 node: {HIVE_NODE}")
    print(f"Hive Engine L2 API: {HIVE_ENGINE_API}")
    print(f"\nEndpoints:")
    print(f"  GET  /api/tokens              — List all tokens")
    print(f"  GET  /api/token/<symbol>       — Token details")
    print(f"  GET  /api/balance/<account>     — All token balances")
    print(f"  GET  /api/balance/<acct>/<sym>  — Specific balance")
    print(f"  POST /api/transfer              — Transfer tokens")
    print(f"  POST /api/stake                 — Stake tokens")
    print(f"  POST /api/unstake               — Unstake tokens")
    print(f"  GET  /api/market/<symbol>       — Order book")
    print(f"  POST /api/market/buy            — Buy order")
    print(f"  POST /api/market/sell           — Sell order")
    print(f"  GET  /api/history/<acct>/<sym>  — Tx history")
    print(f"\n=================================================\n")

    # Run Flask in debug mode for development. In production, use gunicorn:
    #   gunicorn -w 4 -b 0.0.0.0:3002 app:app
    app.run(host="0.0.0.0", port=PORT, debug=True)
