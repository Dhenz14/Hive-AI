"""
HAF Indexer — Flask REST API Server (Python)
=============================================

Provides HTTP endpoints to query data built by the HAF indexer.
This is the "read side" of the application — the indexer writes data,
and this server reads it.

In production HAF deployments, the indexer and API server typically run
as separate processes. The indexer writes to PostgreSQL, and one or more
API servers read from it. This separation allows:
    - Scaling API servers independently of the indexer
    - Restarting the API without interrupting indexing
    - Load balancing across multiple API replicas

Endpoints:
    GET /api/transfers/:account   — All transfers for an account
    GET /api/stats/:account       — Account transfer statistics
    GET /api/top-senders          — Leaderboard of top senders
    GET /api/block/:num           — Transfers in a specific block
    GET /api/status               — Indexer status and health check

Run:
    python server.py
    # or: flask --app server run --port 3003
"""

import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from flask import Flask, jsonify, request

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
APP_NAME = os.getenv("APP_NAME", "my_haf_indexer")
PORT = int(os.getenv("PORT", "3003"))

DB_CONFIG = {
    "host": os.getenv("HAF_DB_HOST", "localhost"),
    "port": int(os.getenv("HAF_DB_PORT", "5432")),
    "dbname": os.getenv("HAF_DB_NAME", "haf_block_log"),
    "user": os.getenv("HAF_DB_USER", "haf_app"),
    "password": os.getenv("HAF_DB_PASSWORD", ""),
}

# ---------------------------------------------------------------------------
# Flask Application
# ---------------------------------------------------------------------------
app = Flask(__name__)


def get_db_connection():
    """
    Get a PostgreSQL connection to the HAF database.

    HAF apps read from the same database that hived writes to.
    Each API request gets its own connection from the pool.
    For production, consider using a connection pool like pgbouncer
    or psycopg2's ThreadedConnectionPool.
    """
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True  # Read-only queries don't need transactions
    return conn


def query_db(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a SQL query and return results as a list of dicts."""
    conn = get_db_connection()
    try:
        # RealDictCursor returns rows as dictionaries instead of tuples
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        results = cur.fetchall()
        cur.close()
        return results
    finally:
        conn.close()


def query_one(sql: str, params: tuple = ()) -> dict | None:
    """Execute a SQL query and return the first row as a dict, or None."""
    results = query_db(sql, params)
    return results[0] if results else None


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """
    Root endpoint — returns API discovery information.
    Lists all available endpoints and links to documentation.
    """
    return jsonify({
        "name": "HAF Transfer Indexer API",
        "version": "1.0.0",
        "description": "REST API for querying Hive blockchain transfer data indexed via HAF",
        "endpoints": {
            "GET /api/transfers/<account>": "All transfers for an account (?limit, ?offset, ?asset, ?direction)",
            "GET /api/stats/<account>": "Aggregated transfer statistics for an account",
            "GET /api/top-senders": "Leaderboard of top senders (?limit, ?asset)",
            "GET /api/block/<num>": "All transfers in a specific block",
            "GET /api/status": "Indexer status and sync progress",
        },
        "links": {
            "haf_docs": "https://gitlab.syncad.com/hive/haf",
            "hive_docs": "https://developers.hive.io",
        },
    })


@app.route("/api/transfers/<account>")
def get_transfers(account: str):
    """
    GET /api/transfers/:account

    Returns all transfers involving the specified Hive account (as sender OR receiver).

    Query parameters:
        limit     — Maximum number of results (default 50, max 1000)
        offset    — Pagination offset (default 0)
        asset     — Filter by asset type: HIVE, HBD (optional)
        direction — Filter by direction: sent, received, all (default: all)

    Example:
        GET /api/transfers/blocktrades?limit=10&asset=HIVE&direction=sent

    The transfers are read from our application-specific transfers table,
    NOT directly from hive.operations. This is the whole point of HAF —
    we pre-process the raw blockchain data into queryable application state.
    """
    try:
        limit = min(int(request.args.get("limit", 50)), 1000)
        offset = int(request.args.get("offset", 0))
        asset = request.args.get("asset")
        direction = request.args.get("direction", "all")

        # Build the WHERE clause dynamically based on query parameters
        conditions = []
        params = []

        # Direction filter: sender, receiver, or both
        if direction == "sent":
            conditions.append("sender = %s")
            params.append(account)
        elif direction == "received":
            conditions.append("receiver = %s")
            params.append(account)
        else:
            # "all" — transfers where account is either sender or receiver
            conditions.append("(sender = %s OR receiver = %s)")
            params.extend([account, account])

        # Optional asset filter
        if asset:
            conditions.append("asset = %s")
            params.append(asset.upper())

        where_clause = " AND ".join(conditions)

        # Query our application's transfers table (built by the indexer)
        transfers = query_db(
            f"""
            SELECT
                block_num,
                trx_in_block,
                timestamp,
                sender,
                receiver,
                amount,
                amount_numeric,
                asset,
                memo
            FROM {APP_NAME}.transfers
            WHERE {where_clause}
            ORDER BY block_num DESC, trx_in_block DESC
            LIMIT %s OFFSET %s
            """,
            (*params, limit, offset),
        )

        # Get total count for pagination metadata
        count_row = query_one(
            f"SELECT COUNT(*) as total FROM {APP_NAME}.transfers WHERE {where_clause}",
            tuple(params),
        )
        total = int(count_row["total"]) if count_row else 0

        # Convert Decimal and datetime objects to JSON-serializable types
        for t in transfers:
            t["amount_numeric"] = float(t["amount_numeric"]) if t["amount_numeric"] else 0
            t["timestamp"] = t["timestamp"].isoformat() if t["timestamp"] else None

        return jsonify({
            "account": account,
            "transfers": transfers,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total,
            },
        })

    except Exception as error:
        print(f"[api] Error in /api/transfers/{account}: {error}")
        return jsonify({"error": "Internal server error", "details": str(error)}), 500


@app.route("/api/stats/<account>")
def get_stats(account: str):
    """
    GET /api/stats/:account

    Returns aggregated transfer statistics for a Hive account.
    This data comes from our pre-computed account_stats table, which the
    indexer updates incrementally as it processes new blocks.

    Response includes: total sent/received (HIVE and HBD), transfer count,
    unique counterparties, first/last transfer timestamps.

    Example:
        GET /api/stats/blocktrades
    """
    try:
        # Query the pre-computed statistics table
        # This is O(1) — just a primary key lookup, no matter how many
        # transfers the account has made. That's the power of pre-aggregation.
        stats = query_one(
            f"""
            SELECT
                account,
                total_sent,
                total_received,
                hbd_sent,
                hbd_received,
                transfer_count,
                unique_partners,
                first_transfer_at,
                last_transfer_at,
                last_updated_block
            FROM {APP_NAME}.account_stats
            WHERE account = %s
            """,
            (account,),
        )

        if stats is None:
            return jsonify({
                "error": "Account not found",
                "message": (
                    f"No transfer data found for account '{account}'. "
                    "The account may not have made any transfers, or the indexer "
                    "may not have processed their blocks yet."
                ),
            }), 404

        # Calculate net balance from transfers
        total_sent = float(stats["total_sent"])
        total_received = float(stats["total_received"])
        hbd_sent = float(stats["hbd_sent"])
        hbd_received = float(stats["hbd_received"])

        return jsonify({
            "account": stats["account"],
            "hive": {
                "total_sent": total_sent,
                "total_received": total_received,
                "net": total_received - total_sent,
            },
            "hbd": {
                "total_sent": hbd_sent,
                "total_received": hbd_received,
                "net": hbd_received - hbd_sent,
            },
            "transfer_count": stats["transfer_count"],
            "unique_partners": stats["unique_partners"],
            "first_transfer_at": stats["first_transfer_at"].isoformat() if stats["first_transfer_at"] else None,
            "last_transfer_at": stats["last_transfer_at"].isoformat() if stats["last_transfer_at"] else None,
            "last_updated_block": stats["last_updated_block"],
        })

    except Exception as error:
        print(f"[api] Error in /api/stats/{account}: {error}")
        return jsonify({"error": "Internal server error", "details": str(error)}), 500


@app.route("/api/top-senders")
def get_top_senders():
    """
    GET /api/top-senders

    Returns a leaderboard of accounts ranked by total HIVE sent.

    Query parameters:
        limit — Number of results (default 25, max 100)
        asset — Rank by HIVE or HBD (default: HIVE)

    Example:
        GET /api/top-senders?limit=10&asset=HBD
    """
    try:
        limit = min(int(request.args.get("limit", 25)), 100)
        asset = request.args.get("asset", "HIVE").upper()

        # Choose the column to rank by based on the asset parameter
        sent_column = "hbd_sent" if asset == "HBD" else "total_sent"
        received_column = "hbd_received" if asset == "HBD" else "total_received"

        # Query the pre-computed account_stats table, ordered by amount sent
        rows = query_db(
            f"""
            SELECT
                account,
                {sent_column} as total_sent,
                {received_column} as total_received,
                transfer_count,
                last_transfer_at
            FROM {APP_NAME}.account_stats
            WHERE {sent_column} > 0
            ORDER BY {sent_column} DESC
            LIMIT %s
            """,
            (limit,),
        )

        leaderboard = []
        for i, row in enumerate(rows):
            leaderboard.append({
                "rank": i + 1,
                "account": row["account"],
                "total_sent": float(row["total_sent"]),
                "total_received": float(row["total_received"]),
                "transfer_count": row["transfer_count"],
                "last_transfer_at": row["last_transfer_at"].isoformat() if row["last_transfer_at"] else None,
            })

        return jsonify({
            "asset": asset,
            "leaderboard": leaderboard,
        })

    except Exception as error:
        print(f"[api] Error in /api/top-senders: {error}")
        return jsonify({"error": "Internal server error", "details": str(error)}), 500


@app.route("/api/block/<int:num>")
def get_block_transfers(num: int):
    """
    GET /api/block/:num

    Returns all transfers that occurred in a specific block.

    This is useful for:
        - Debugging: "What transfers happened in block 80000000?"
        - Block explorers: Showing all activity in a block
        - Verification: Comparing our indexed data with the raw blockchain

    Example:
        GET /api/block/80000000
    """
    try:
        if num < 1:
            return jsonify({
                "error": "Invalid block number",
                "message": "Block number must be a positive integer.",
            }), 400

        # Query transfers in this specific block from our indexed data
        transfers = query_db(
            f"""
            SELECT
                block_num,
                trx_in_block,
                op_pos,
                timestamp,
                sender,
                receiver,
                amount,
                amount_numeric,
                asset,
                memo
            FROM {APP_NAME}.transfers
            WHERE block_num = %s
            ORDER BY trx_in_block, op_pos
            """,
            (num,),
        )

        # Also get block metadata directly from HAF's hive.blocks table
        # This shows how your app can still query HAF's built-in tables
        # alongside your own application tables.
        block_info = query_one(
            """
            SELECT
                num,
                hash,
                created_at as timestamp,
                producer as witness
            FROM hive.blocks
            WHERE num = %s
            """,
            (num,),
        )

        # Convert types for JSON serialization
        for t in transfers:
            t["amount_numeric"] = float(t["amount_numeric"]) if t["amount_numeric"] else 0
            t["timestamp"] = t["timestamp"].isoformat() if t["timestamp"] else None

        block_meta = None
        if block_info:
            block_meta = {
                "hash": block_info["hash"],
                "timestamp": block_info["timestamp"].isoformat() if block_info["timestamp"] else None,
                "witness": block_info["witness"],
            }

        return jsonify({
            "block_num": num,
            "block_info": block_meta,
            "transfer_count": len(transfers),
            "transfers": transfers,
        })

    except Exception as error:
        print(f"[api] Error in /api/block/{num}: {error}")
        return jsonify({"error": "Internal server error", "details": str(error)}), 500


@app.route("/api/status")
def get_status():
    """
    GET /api/status

    Returns the current status of the HAF indexer.
    Useful for monitoring and health checks.

    Response includes:
        - Last processed block number
        - Total transfers indexed
        - HAF context status
        - How far behind the blockchain head we are
        - Database connection health
    """
    try:
        # Get our application's internal state
        state_rows = query_db(
            f"SELECT key, value, updated_at FROM {APP_NAME}.indexer_state"
        )
        state = {}
        for row in state_rows:
            state[row["key"]] = {
                "value": row["value"],
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            }

        # Get the HAF context status — this tells us where HAF thinks we are
        # hive.contexts tracks each registered application's progress
        context_row = query_one(
            """
            SELECT
                name,
                current_block_num,
                is_attached,
                events_id
            FROM hive.contexts
            WHERE name = %s
            """,
            (APP_NAME,),
        )

        # Get the current blockchain head block from HAF
        # hive.blocks contains all blocks that hived has synced
        head_row = query_one("SELECT MAX(num) as head_block FROM hive.blocks")

        last_processed = int(state.get("last_processed_block", {}).get("value", "0"))
        head_block = int(head_row["head_block"]) if head_row and head_row["head_block"] else 0
        blocks_behind = head_block - last_processed

        # Calculate sync percentage
        sync_pct = f"{(last_processed / head_block * 100):.2f}" if head_block > 0 else "0.00"

        haf_context = None
        if context_row:
            haf_context = {
                "current_block_num": context_row["current_block_num"],
                "is_attached": context_row["is_attached"],
            }

        return jsonify({
            "app_name": APP_NAME,
            "status": "synced" if blocks_behind < 100 else "syncing",
            "last_processed_block": last_processed,
            "head_block": head_block,
            "blocks_behind": blocks_behind,
            "sync_percentage": f"{sync_pct}%",
            "total_transfers_indexed": int(
                state.get("total_transfers_indexed", {}).get("value", "0")
            ),
            "indexer_version": state.get("indexer_version", {}).get("value", "unknown"),
            "haf_context": haf_context,
            "database": {
                "host": DB_CONFIG["host"],
                "database": DB_CONFIG["dbname"],
                "connected": True,
            },
        })

    except Exception as error:
        print(f"[api] Error in /api/status: {error}")
        return jsonify({
            "error": "Internal server error",
            "details": str(error),
            "database": {"connected": False},
        }), 500


# ---------------------------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------------------------


@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors with a helpful JSON response."""
    return jsonify({
        "error": "Not found",
        "message": f"No endpoint matches {request.method} {request.url}",
        "hint": "Visit GET / for a list of available endpoints.",
    }), 404


@app.errorhandler(500)
def internal_error(e):
    """Handle 500 errors with a JSON response."""
    return jsonify({
        "error": "Internal server error",
        "message": str(e),
    }), 500


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 70)
    print(f"HAF Transfer Indexer API — listening on http://localhost:{PORT}")
    print("=" * 70)
    print(f"Database: {DB_CONFIG['dbname']}")
    print(f"App context: {APP_NAME}")
    print()
    print("Available endpoints:")
    print(f"  GET http://localhost:{PORT}/api/transfers/<account>")
    print(f"  GET http://localhost:{PORT}/api/stats/<account>")
    print(f"  GET http://localhost:{PORT}/api/top-senders")
    print(f"  GET http://localhost:{PORT}/api/block/<num>")
    print(f"  GET http://localhost:{PORT}/api/status")
    print()

    # Run the Flask development server
    # For production, use gunicorn or uWSGI instead:
    #   gunicorn -w 4 -b 0.0.0.0:3003 server:app
    app.run(host="0.0.0.0", port=PORT, debug=False)
