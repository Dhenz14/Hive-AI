"""
HAF Indexer — Main Indexing Loop (Python)
==========================================

This is the core of a HAF application. It continuously reads new blocks
from HAF's PostgreSQL tables and extracts transfer operations into our
application-specific tables.

How HAF Indexing Works:
-----------------------
1. hived (Hive node) writes every block into PostgreSQL in real-time
2. Our indexer calls hive.app_next_block(context) to get the next block
   number that needs processing
3. We query hive.operations for that block's operations, filtering for
   the operation types we care about (transfer_operation in this case)
4. We parse the operation JSON and write results to our own tables
5. We call hive.app_context_detach(context) to commit our progress
6. If a blockchain fork/reorg occurs, HAF automatically rolls back our
   context to the fork point — we just re-process from there

Run:
    python indexer.py

Prerequisites:
    - Run setup.py first to create schema and register HAF context
    - PostgreSQL with HAF must be running and syncing blocks
"""

import json
import os
import signal
import sys
import time
from collections import defaultdict
from decimal import Decimal

import psycopg2
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
APP_NAME = os.getenv("APP_NAME", "my_haf_indexer")
START_BLOCK = int(os.getenv("START_BLOCK", "1"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1000"))

# HAF operation type IDs — these are defined by the Hive protocol and stored
# in the hive.operation_types table. You can query that table to find the
# op_type_id for any operation type.
#
# Common operation type IDs:
#   2  = transfer_operation          (HIVE/HBD transfers between accounts)
#   3  = transfer_to_vesting_operation (power up)
#   4  = withdraw_vesting_operation  (power down)
#   5  = limit_order_create_operation
#   6  = limit_order_cancel_operation
#   13 = account_create_operation
#   18 = custom_json_operation       (layer-2 apps like Splinterlands)
#   72 = vote_operation
#
# We index transfer_operation (type_id = 2) in this template.
TRANSFER_OP_TYPE_ID = 2

DB_CONFIG = {
    "host": os.getenv("HAF_DB_HOST", "localhost"),
    "port": int(os.getenv("HAF_DB_PORT", "5432")),
    "dbname": os.getenv("HAF_DB_NAME", "haf_block_log"),
    "user": os.getenv("HAF_DB_USER", "haf_app"),
    "password": os.getenv("HAF_DB_PASSWORD", ""),
}

# ---------------------------------------------------------------------------
# Graceful Shutdown
# ---------------------------------------------------------------------------
# HAF indexers should handle SIGINT/SIGTERM gracefully to avoid leaving the
# database in an inconsistent state. We set a flag and let the current batch
# finish before exiting.
shutdown_requested = False


def handle_shutdown(signum, frame):
    """Signal handler for graceful shutdown."""
    global shutdown_requested
    sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
    print(f"\n[indexer] {sig_name} received — finishing current batch and shutting down...")
    shutdown_requested = True


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


# ---------------------------------------------------------------------------
# Amount Parsing
# ---------------------------------------------------------------------------
# NAI (Numeric Asset Identifier) codes used by the Hive blockchain.
# These map the internal asset representation to human-readable names.
NAI_MAP = {
    "@@000000021": "HIVE",   # Native HIVE token (formerly STEEM)
    "@@000000013": "HBD",    # Hive Backed Dollars (formerly SBD)
    "@@000000037": "VESTS",  # Hive Power vesting shares
}


def parse_amount(amount_obj: dict) -> dict:
    """
    Parse a HAF amount object into human-readable form.

    In the HAF operations table, transfer amounts are stored as JSON objects
    with a "nai" (Numeric Asset Identifier) field. The body JSON looks like:

        {
            "type": "transfer_operation",
            "value": {
                "from": "alice",
                "to": "bob",
                "amount": {"amount": "1000", "precision": 3, "nai": "@@000000021"},
                "memo": "hello"
            }
        }

    Args:
        amount_obj: Dict with keys 'amount' (string integer), 'precision' (int),
                    and 'nai' (string NAI code).

    Returns:
        Dict with 'numeric' (Decimal), 'asset' (string), 'display' (string).

    NAI codes:
        @@000000021 = HIVE (formerly STEEM)
        @@000000013 = HBD  (Hive Backed Dollars, formerly SBD)
        @@000000037 = VESTS (Hive Power vesting shares)
    """
    # HAF stores amounts as {amount: "1000", precision: 3, nai: "@@000000021"}
    raw_amount = int(amount_obj["amount"])
    precision = int(amount_obj["precision"])

    # Convert integer amount to decimal using precision
    # e.g., amount=1000, precision=3 -> 1.000
    numeric = Decimal(raw_amount) / Decimal(10 ** precision)

    # Map NAI codes to human-readable asset names
    asset = NAI_MAP.get(amount_obj["nai"], "UNKNOWN")

    # Format with the correct number of decimal places
    format_str = f"{{:.{precision}f}}"
    display = f"{format_str.format(numeric)} {asset}"

    return {
        "numeric": numeric,
        "asset": asset,
        "display": display,
    }


# ---------------------------------------------------------------------------
# Block Processing
# ---------------------------------------------------------------------------
def process_block_batch(cur, start_block: int, end_block: int) -> dict:
    """
    Process a batch of blocks from HAF.

    HAF Batch Processing Strategy:
    ==============================
    Instead of processing one block at a time (slow!), we process blocks in
    batches within a single database transaction. This is dramatically faster:

        - Single block:  ~100 blocks/second
        - Batch of 1000: ~10,000 blocks/second (100x faster!)

    The batch approach:
    1. Start a transaction
    2. Query all operations in the block range [start_block, end_block]
    3. Insert all parsed transfers in bulk
    4. Update account stats
    5. Update HAF context progress
    6. Commit transaction

    If anything fails, the entire batch rolls back — no partial state.

    Args:
        cur: psycopg2 cursor within an active transaction.
        start_block: First block number in the range.
        end_block: Last block number in the range (inclusive).

    Returns:
        Dict with processing statistics.
    """

    # -----------------------------------------------------------------------
    # Query HAF's operations table for transfer operations in this block range
    # -----------------------------------------------------------------------
    # hive.operations is the master table that HAF populates from the blockchain.
    # Each row is one operation from one transaction in one block.
    #
    # Key columns:
    #   - block_num:     Which block this operation is in
    #   - trx_in_block:  Index of the transaction within the block
    #   - op_pos:        Position of this operation within the transaction
    #   - op_type_id:    Operation type (2 = transfer_operation)
    #   - body:          Full operation JSON (varies by op type)
    #
    # We JOIN with hive.blocks to get the block timestamp.
    #
    # IMPORTANT: We filter by op_type_id for performance. Without this filter,
    # we'd scan ALL operations (votes, comments, custom_json, etc.) and discard
    # 99%+ of them. The op_type_id column is indexed by HAF.
    cur.execute(
        """
        SELECT
            o.block_num,
            o.trx_in_block,
            o.op_pos,
            o.body::text as body,       -- Operation JSON as text (we parse in Python)
            b.created_at as timestamp   -- Block timestamp from hive.blocks
        FROM hive.operations o
        JOIN hive.blocks b ON b.num = o.block_num
        WHERE o.block_num >= %s
          AND o.block_num <= %s
          AND o.op_type_id = %s         -- Only transfer_operation (type 2)
        ORDER BY o.block_num, o.trx_in_block, o.op_pos
        """,
        (start_block, end_block, TRANSFER_OP_TYPE_ID),
    )

    rows = cur.fetchall()

    if not rows:
        return {"transfer_count": 0, "blocks_processed": end_block - start_block + 1}

    # -----------------------------------------------------------------------
    # Parse and insert each transfer operation
    # -----------------------------------------------------------------------
    transfer_count = 0
    # Accumulate stats updates per account (avoids per-transfer DB writes)
    account_updates = defaultdict(lambda: {
        "sent": Decimal("0"),
        "received": Decimal("0"),
        "hbd_sent": Decimal("0"),
        "hbd_received": Decimal("0"),
        "count": 0,
        "timestamp": None,
        "block_num": 0,
    })

    for row in rows:
        block_num, trx_in_block, op_pos, body_text, timestamp = row

        # Parse the operation JSON body
        # The body structure for transfer_operation:
        #   {
        #       "type": "transfer_operation",
        #       "value": {
        #           "from": "sender_account",
        #           "to": "receiver_account",
        #           "amount": {"amount": "1000", "precision": 3, "nai": "@@000000021"},
        #           "memo": "optional memo text"
        #       }
        #   }
        try:
            op_body = json.loads(body_text)
        except json.JSONDecodeError as e:
            print(f"[indexer] WARNING: Failed to parse operation JSON in block {block_num}: {e}")
            continue

        value = op_body.get("value", {})
        sender = value.get("from")
        receiver = value.get("to")
        amount_obj = value.get("amount")

        if not sender or not receiver or not amount_obj:
            print(f"[indexer] WARNING: Malformed transfer in block {block_num}")
            continue

        amount = parse_amount(amount_obj)
        memo = value.get("memo", "")

        # Insert the transfer into our application table
        # ON CONFLICT DO NOTHING handles the case where we re-process a block
        # (e.g., after a fork rollback)
        cur.execute(
            f"""
            INSERT INTO {APP_NAME}.transfers
                (block_num, trx_in_block, op_pos, timestamp, sender, receiver,
                 amount, amount_numeric, asset, memo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (block_num, trx_in_block, op_pos) DO NOTHING
            """,
            (
                block_num,
                trx_in_block,
                op_pos,
                timestamp,
                sender,
                receiver,
                amount["display"],      # e.g., "1.000 HIVE"
                float(amount["numeric"]),  # e.g., 1.000
                amount["asset"],         # e.g., "HIVE"
                memo,
            ),
        )

        transfer_count += 1

        # -------------------------------------------------------------------
        # Accumulate account statistics
        # -------------------------------------------------------------------
        # Instead of updating account_stats for every single transfer (slow),
        # we accumulate changes in memory and apply them in bulk at the end
        # of the batch.
        sender_stats = account_updates[sender]
        receiver_stats = account_updates[receiver]

        if amount["asset"] == "HIVE":
            sender_stats["sent"] += amount["numeric"]
            receiver_stats["received"] += amount["numeric"]
        elif amount["asset"] == "HBD":
            sender_stats["hbd_sent"] += amount["numeric"]
            receiver_stats["hbd_received"] += amount["numeric"]

        sender_stats["count"] += 1
        receiver_stats["count"] += 1
        sender_stats["timestamp"] = timestamp
        sender_stats["block_num"] = block_num
        receiver_stats["timestamp"] = timestamp
        receiver_stats["block_num"] = block_num

    # -----------------------------------------------------------------------
    # Bulk-update account statistics
    # -----------------------------------------------------------------------
    # Apply all accumulated account stat changes using our helper function.
    # This is much faster than updating after every single transfer.
    accounts_updated = 0
    for account, stats in account_updates.items():
        cur.execute(
            f"SELECT {APP_NAME}.upsert_account_stats(%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                account,
                float(stats["sent"]),
                float(stats["received"]),
                float(stats["hbd_sent"]),
                float(stats["hbd_received"]),
                stats["count"],
                stats["timestamp"],
                stats["block_num"],
            ),
        )
        accounts_updated += 1

    return {
        "transfer_count": transfer_count,
        "blocks_processed": end_block - start_block + 1,
        "accounts_updated": accounts_updated,
    }


# ---------------------------------------------------------------------------
# Main Indexer Loop
# ---------------------------------------------------------------------------
def run_indexer():
    """
    The main indexing loop. This runs continuously, processing new blocks as
    they become available in HAF.

    HAF Context Lifecycle:
    ======================

    1. ATTACH: hive.app_context_attach(context, start_block)
       Tells HAF "I want to start processing from this block."
       Only needed on first run — on subsequent runs, HAF remembers your position.

    2. NEXT BLOCK: hive.app_next_block(context)
       Returns the next block number to process, or NULL if caught up.
       This is the PRIMARY API for HAF indexers.
       - Returns a block number: process this block
       - Returns NULL: you're caught up, wait and retry
       - If a fork occurred, returns a LOWER block number than last time
         (HAF rolled back your context automatically!)

    3. DETACH: hive.app_context_detach(context)
       Saves your progress. Call this periodically (e.g., after each batch).
       After detaching, hive.app_next_block() will resume from where you left off.

    Fork Handling:
    ==============
    HAF's killer feature is automatic fork handling. Here's how it works:

    1. Your app processes blocks 1000-1050
    2. A blockchain reorganization occurs at block 1045
    3. HAF detects the fork and automatically rolls back your context to block 1044
    4. Next call to hive.app_next_block() returns 1045 (the new version)
    5. Your app re-processes blocks 1045-1050 with the correct data

    For this to work correctly, your app's INSERT statements should use
    ON CONFLICT to handle re-processing the same block numbers. Our transfers
    table has a UNIQUE constraint on (block_num, trx_in_block, op_pos) for this.
    """
    print("=" * 70)
    print(f"HAF Transfer Indexer — {APP_NAME}")
    print("=" * 70)
    print(f"Database: {DB_CONFIG['dbname']}")
    print(f"Batch size: {BATCH_SIZE} blocks")
    print(f"Start block: {START_BLOCK}")
    print()

    # Connect to HAF PostgreSQL
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False  # We manage transactions manually
    cur = conn.cursor()

    try:
        # -------------------------------------------------------------------
        # Step 1: Check if context exists and determine starting point
        # -------------------------------------------------------------------
        # Query the HAF context to see where we left off last time.
        # The current_block_num column tells us the last block we committed.
        cur.execute(
            "SELECT current_block_num, is_attached "
            "FROM hive.contexts WHERE name = %s",
            (APP_NAME,),
        )
        context_row = cur.fetchone()

        if context_row is None:
            print(f"[indexer] ERROR: HAF context '{APP_NAME}' not found!")
            print("  Run 'python setup.py' first to create the schema and context.")
            sys.exit(1)

        current_block, is_attached = context_row
        print(f"[indexer] HAF context '{APP_NAME}': last block = {current_block}")

        # -------------------------------------------------------------------
        # Step 2: Attach the context (if not already attached)
        # -------------------------------------------------------------------
        # hive.app_context_attach(context_name, start_block) tells HAF that we
        # are starting to process blocks. If we've processed blocks before, HAF
        # resumes from where we left off (ignoring start_block).
        #
        # If already attached (e.g., from a previous crashed run), we detach first
        # to reset the state cleanly.
        conn.autocommit = True  # HAF context management requires autocommit
        if is_attached:
            print("[indexer] Context is already attached (previous run may have crashed). Detaching first...")
            cur.execute(f"SELECT hive.app_context_detach('{APP_NAME}')")

        # Attach the context — HAF starts tracking our progress from this point
        print(f"[indexer] Attaching HAF context at start_block {START_BLOCK}...")
        cur.execute(f"SELECT hive.app_context_attach('{APP_NAME}', %s)", (START_BLOCK,))
        conn.autocommit = False

        # -------------------------------------------------------------------
        # Step 3: Main processing loop
        # -------------------------------------------------------------------
        print("[indexer] Starting block processing loop...")
        print("[indexer] Press Ctrl+C to stop gracefully.\n")

        total_transfers = 0
        total_blocks = 0
        last_log_time = time.time()
        last_block = 0

        while not shutdown_requested:
            # -----------------------------------------------------------------
            # Get the next block range to process from HAF
            # -----------------------------------------------------------------
            # hive.app_next_block(context_name) returns the next unprocessed block
            # number, or NULL if we're caught up to the head of the chain.
            #
            # This is the CORE of the HAF API — it handles:
            #   - Tracking which blocks you've already processed
            #   - Detecting blockchain forks and rolling back your position
            #   - Coordinating with hived's block production
            cur.execute(f"SELECT hive.app_next_block('{APP_NAME}') as next_block")
            next_block_row = cur.fetchone()
            next_block = next_block_row[0] if next_block_row else None

            # NULL means we've caught up to the blockchain head
            # Wait a bit and check again (hived produces blocks every 3 seconds)
            if next_block is None:
                now = time.time()
                if now - last_log_time > 10:
                    print(
                        f"[indexer] Caught up! Waiting for new blocks... "
                        f"({total_blocks} blocks, {total_transfers} transfers processed)"
                    )
                    last_log_time = now

                # Detach to save progress before sleeping
                conn.autocommit = True
                cur.execute(f"SELECT hive.app_context_detach('{APP_NAME}')")
                conn.autocommit = False

                # Wait 1 second, then re-attach and continue
                # Hive produces a block every 3 seconds, so 1s polling is fine
                time.sleep(1)

                # Re-attach to continue processing
                if not shutdown_requested:
                    conn.autocommit = True
                    cur.execute(f"SELECT hive.app_context_attach('{APP_NAME}', %s)", (START_BLOCK,))
                    conn.autocommit = False

                continue

            # Calculate end of this batch
            # We process up to BATCH_SIZE blocks at once for efficiency
            end_block = next_block + BATCH_SIZE - 1

            # -----------------------------------------------------------------
            # Process this batch of blocks
            # -----------------------------------------------------------------
            # The entire batch is wrapped in a transaction for atomicity.
            # If anything fails, the whole batch rolls back cleanly.
            try:
                result = process_block_batch(cur, next_block, end_block)

                # Update our internal state tracking
                cur.execute(
                    f"""
                    UPDATE {APP_NAME}.indexer_state
                    SET value = %s, updated_at = NOW()
                    WHERE key = 'last_processed_block'
                    """,
                    (str(end_block),),
                )

                cur.execute(
                    f"""
                    UPDATE {APP_NAME}.indexer_state
                    SET value = (CAST(value AS BIGINT) + %s)::text, updated_at = NOW()
                    WHERE key = 'total_transfers_indexed'
                    """,
                    (result["transfer_count"],),
                )

                # Commit the entire batch atomically
                conn.commit()

                total_transfers += result["transfer_count"]
                total_blocks += result["blocks_processed"]
                last_block = end_block

                # Log progress periodically
                now = time.time()
                if result["transfer_count"] > 0 or now - last_log_time > 5:
                    print(
                        f"[indexer] Block {next_block}-{end_block}: "
                        f"{result['transfer_count']} transfers, "
                        f"{result.get('accounts_updated', 0)} accounts updated "
                        f"(total: {total_blocks} blocks, {total_transfers} transfers)"
                    )
                    last_log_time = now

            except Exception as batch_error:
                # Roll back the failed batch — no partial state
                conn.rollback()
                print(f"[indexer] ERROR processing blocks {next_block}-{end_block}: {batch_error}")

                # Wait before retrying to avoid tight error loops
                time.sleep(5)

        # -------------------------------------------------------------------
        # Clean shutdown
        # -------------------------------------------------------------------
        # Detach the context to save our progress before exiting.
        # Next time we start, HAF will resume from this point.
        print("\n[indexer] Shutting down...")
        try:
            conn.autocommit = True
            cur.execute(f"SELECT hive.app_context_detach('{APP_NAME}')")
            print(f"[indexer] Context detached. Last processed block: {last_block}")
        except Exception as detach_err:
            # Context may already be detached
            print(f"[indexer] Warning: Could not detach context: {detach_err}")

        print(f"[indexer] Final stats: {total_blocks} blocks, {total_transfers} transfers")
        print("[indexer] Goodbye!")

    except Exception as error:
        print(f"[indexer] FATAL ERROR: {error}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        cur.close()
        conn.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_indexer()
