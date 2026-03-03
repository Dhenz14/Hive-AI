"""
HAF Indexer — Database Schema Setup (Python)
=============================================

HAF Architecture Tutorial:
==========================
HAF (Hive Application Framework) is the OFFICIAL way to build Hive blockchain
indexers. It is a PostgreSQL-based framework with these key components:

1. hived (the Hive node daemon) writes ALL blockchain data directly into
   PostgreSQL tables via the sql_serializer plugin. Every block, transaction,
   and operation is stored in normalized SQL tables.

2. Your application registers as a "HAF application" in the database by
   creating an "application context". This context is a named cursor that
   tracks which block your app has processed up to.

3. HAF tracks processing progress per-context, so multiple independent
   indexers can run against the same database at different speeds.

4. Your app reads operations from HAF's built-in tables (hive.operations,
   hive.blocks, etc.) and builds its OWN application-specific state tables.

5. This is MUCH more efficient than streaming from API nodes because:
   - No network overhead (direct PostgreSQL queries)
   - Batch processing of thousands of blocks at once
   - SQL-native filtering and joins
   - Automatic blockchain reorganization (fork) handling

Key HAF tables (provided by the framework — DO NOT create these):
-----------------------------------------------------------------
- hive.blocks:          Block metadata (num, hash, timestamp, witness, etc.)
- hive.transactions:    Transaction data (hash, block_num, trx_in_block)
- hive.operations:      ALL blockchain operations, indexed by block/trx/op
                         The 'body' column contains the operation as JSON.
- hive.accounts:        Account registry (id, name)
- hive.operation_types: Lookup table mapping op_type_id to operation names
                         (e.g., 2 = 'transfer_operation')

Your app creates its OWN tables in its OWN schema for the specific data
it cares about. This script creates those tables.

Run this once before starting the indexer:
    python setup.py
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# Configuration — loaded from .env file
# ---------------------------------------------------------------------------
APP_NAME = os.getenv("APP_NAME", "my_haf_indexer")
START_BLOCK = os.getenv("START_BLOCK", "1")

DB_CONFIG = {
    "host": os.getenv("HAF_DB_HOST", "localhost"),
    "port": int(os.getenv("HAF_DB_PORT", "5432")),
    "dbname": os.getenv("HAF_DB_NAME", "haf_block_log"),
    "user": os.getenv("HAF_DB_USER", "haf_app"),
    "password": os.getenv("HAF_DB_PASSWORD", ""),
}


def setup():
    """Create the HAF application schema, tables, indexes, and register the context."""

    # Connect to the HAF PostgreSQL database
    # This is the same database that hived writes blockchain data into
    conn = psycopg2.connect(**DB_CONFIG)

    # autocommit=True so each DDL statement takes effect immediately
    # (PostgreSQL DDL is transactional, but for setup we want immediate effect)
    conn.autocommit = True
    cur = conn.cursor()

    try:
        print(f"[setup] Setting up HAF application: {APP_NAME}")
        print(f"[setup] Database: {DB_CONFIG['dbname']}")

        # -------------------------------------------------------------------
        # Step 1: Create the application schema
        # -------------------------------------------------------------------
        # HAF best practice: each application creates its own PostgreSQL schema
        # to namespace its tables. This avoids collisions with other HAF apps
        # sharing the same database.
        print("[setup] Step 1: Creating application schema...")
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {APP_NAME};")

        # -------------------------------------------------------------------
        # Step 2: Register the HAF application context
        # -------------------------------------------------------------------
        # hive.app_create_context(context_name) registers your application
        # with HAF. This creates an entry in hive.contexts that tracks:
        #   - Which block your app has processed up to
        #   - Whether your app is in a valid state
        #   - Fork handling metadata
        #
        # The context name MUST be unique across all HAF apps on this node.
        # If the context already exists, we skip creation (idempotent).
        #
        # IMPORTANT: The context is what enables HAF's killer feature —
        # automatic fork handling. When the blockchain reorganizes (forks),
        # HAF automatically rolls back your context to the fork point.
        # Your app just needs to re-process blocks from that point.
        print("[setup] Step 2: Registering HAF application context...")
        cur.execute(f"""
            DO $$
            BEGIN
                -- Check if context already exists to make this idempotent
                IF NOT EXISTS (
                    SELECT 1 FROM hive.contexts WHERE name = '{APP_NAME}'
                ) THEN
                    -- Register this application with HAF
                    -- This is the fundamental step that connects your app to the framework
                    PERFORM hive.app_create_context('{APP_NAME}');
                    RAISE NOTICE 'Created HAF context: {APP_NAME}';
                ELSE
                    RAISE NOTICE 'HAF context already exists: {APP_NAME}';
                END IF;
            END
            $$;
        """)

        # -------------------------------------------------------------------
        # Step 3: Create application-specific tables
        # -------------------------------------------------------------------
        # These are YOUR tables — HAF doesn't dictate their structure.
        # Design them based on what your application needs to query.
        #
        # For this transfer indexer, we create:
        #   1. transfers: Every transfer operation on the blockchain
        #   2. account_stats: Aggregated transfer statistics per account
        #   3. indexer_state: Tracks our processing progress
        print("[setup] Step 3: Creating application tables...")

        # --- transfers table ---
        # Stores every transfer operation extracted from hive.operations.
        # Each row represents one transfer_operation from the blockchain.
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {APP_NAME}.transfers (
                id                BIGSERIAL PRIMARY KEY,

                -- Block and transaction context (from hive.operations)
                block_num         INTEGER NOT NULL,       -- Block number where this transfer occurred
                trx_in_block      SMALLINT NOT NULL,       -- Transaction index within the block
                op_pos            INTEGER NOT NULL,        -- Operation position within the transaction
                timestamp         TIMESTAMP NOT NULL,      -- Block timestamp (from hive.blocks)

                -- Transfer-specific fields (parsed from operation JSON body)
                sender            TEXT NOT NULL,            -- Account sending the funds (from_account)
                receiver          TEXT NOT NULL,            -- Account receiving the funds (to_account)
                amount            TEXT NOT NULL,            -- Amount with asset symbol (e.g., "1.000 HIVE")
                amount_numeric    NUMERIC(20, 3),           -- Numeric amount for aggregation queries
                asset             TEXT NOT NULL,            -- Asset symbol: HIVE, HBD, VESTS
                memo              TEXT DEFAULT '',          -- Transfer memo (can be empty)

                -- Prevent duplicate inserts if we re-process a block range
                UNIQUE(block_num, trx_in_block, op_pos)
            );
        """)

        # --- account_stats table ---
        # Pre-computed aggregate statistics per account. Updated incrementally
        # as new transfers are processed. This avoids expensive full-table scans
        # when querying account summaries.
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {APP_NAME}.account_stats (
                account           TEXT PRIMARY KEY,         -- Hive account name
                total_sent        NUMERIC(20, 3) DEFAULT 0, -- Total HIVE sent
                total_received    NUMERIC(20, 3) DEFAULT 0, -- Total HIVE received
                hbd_sent          NUMERIC(20, 3) DEFAULT 0, -- Total HBD sent
                hbd_received      NUMERIC(20, 3) DEFAULT 0, -- Total HBD received
                transfer_count    INTEGER DEFAULT 0,        -- Total number of transfers (sent + received)
                unique_partners   INTEGER DEFAULT 0,        -- Number of unique counterparties
                first_transfer_at TIMESTAMP,                -- Timestamp of first transfer
                last_transfer_at  TIMESTAMP,                -- Timestamp of most recent transfer
                last_updated_block INTEGER DEFAULT 0        -- Block number of last update
            );
        """)

        # --- indexer_state table ---
        # Tracks the indexer's own state: last processed block, start time, etc.
        # This supplements the HAF context (which also tracks block progress)
        # with application-specific metadata.
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {APP_NAME}.indexer_state (
                key               TEXT PRIMARY KEY,
                value             TEXT NOT NULL,
                updated_at        TIMESTAMP DEFAULT NOW()
            );
        """)

        # Initialize indexer state with defaults
        cur.execute(f"""
            INSERT INTO {APP_NAME}.indexer_state (key, value)
            VALUES
                ('last_processed_block', '0'),
                ('start_block', '{START_BLOCK}'),
                ('total_transfers_indexed', '0'),
                ('indexer_version', '1.0.0')
            ON CONFLICT (key) DO NOTHING;
        """)

        # -------------------------------------------------------------------
        # Step 4: Create indexes for fast querying
        # -------------------------------------------------------------------
        # Proper indexing is CRITICAL for HAF apps. Without indexes, queries on
        # millions of transfers would be unacceptably slow.
        #
        # Index design principles for HAF apps:
        # 1. Index columns you filter on (WHERE clause)
        # 2. Index columns you sort on (ORDER BY)
        # 3. Use composite indexes for common query patterns
        # 4. Consider partial indexes for hot data
        print("[setup] Step 4: Creating indexes...")

        # Index on sender — for "show all transfers FROM this account" queries
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_transfers_sender
            ON {APP_NAME}.transfers (sender);
        """)

        # Index on receiver — for "show all transfers TO this account" queries
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_transfers_receiver
            ON {APP_NAME}.transfers (receiver);
        """)

        # Index on block_num — for "show all transfers in block X" queries
        # Also used by the indexer to efficiently find where it left off
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_transfers_block_num
            ON {APP_NAME}.transfers (block_num);
        """)

        # Index on timestamp — for time-range queries ("last 24 hours", etc.)
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_transfers_timestamp
            ON {APP_NAME}.transfers (timestamp DESC);
        """)

        # Composite index — for the common "all transfers involving account X" query
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_transfers_sender_receiver
            ON {APP_NAME}.transfers (sender, receiver);
        """)

        # -------------------------------------------------------------------
        # Step 5: Create helper functions
        # -------------------------------------------------------------------
        # SQL functions for common operations, called by the indexer.
        print("[setup] Step 5: Creating helper functions...")

        # Function to upsert account statistics after processing a transfer.
        # Uses INSERT ... ON CONFLICT for atomic upsert.
        cur.execute(f"""
            CREATE OR REPLACE FUNCTION {APP_NAME}.upsert_account_stats(
                p_account TEXT,
                p_sent NUMERIC,
                p_received NUMERIC,
                p_hbd_sent NUMERIC,
                p_hbd_received NUMERIC,
                p_transfer_count INTEGER,
                p_timestamp TIMESTAMP,
                p_block_num INTEGER
            ) RETURNS VOID AS $$
            BEGIN
                INSERT INTO {APP_NAME}.account_stats (
                    account, total_sent, total_received,
                    hbd_sent, hbd_received,
                    transfer_count, first_transfer_at, last_transfer_at,
                    last_updated_block
                ) VALUES (
                    p_account, p_sent, p_received,
                    p_hbd_sent, p_hbd_received,
                    p_transfer_count, p_timestamp, p_timestamp,
                    p_block_num
                )
                ON CONFLICT (account) DO UPDATE SET
                    total_sent = {APP_NAME}.account_stats.total_sent + p_sent,
                    total_received = {APP_NAME}.account_stats.total_received + p_received,
                    hbd_sent = {APP_NAME}.account_stats.hbd_sent + p_hbd_sent,
                    hbd_received = {APP_NAME}.account_stats.hbd_received + p_hbd_received,
                    transfer_count = {APP_NAME}.account_stats.transfer_count + p_transfer_count,
                    last_transfer_at = GREATEST({APP_NAME}.account_stats.last_transfer_at, p_timestamp),
                    last_updated_block = GREATEST({APP_NAME}.account_stats.last_updated_block, p_block_num);
            END;
            $$ LANGUAGE plpgsql;
        """)

        # -------------------------------------------------------------------
        # Step 6: Verify the setup
        # -------------------------------------------------------------------
        print("[setup] Step 6: Verifying setup...")

        # Verify the HAF context was created
        cur.execute(
            "SELECT name, current_block_num FROM hive.contexts WHERE name = %s",
            (APP_NAME,),
        )
        context_row = cur.fetchone()
        if context_row:
            print(f"[setup] HAF context '{APP_NAME}' registered at block: {context_row[1]}")
        else:
            raise RuntimeError(f"HAF context '{APP_NAME}' not found after creation!")

        # List all tables we created
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s ORDER BY table_name",
            (APP_NAME,),
        )
        tables = cur.fetchall()
        print(f"[setup] Tables created in schema '{APP_NAME}':")
        for (table_name,) in tables:
            print(f"  - {APP_NAME}.{table_name}")

        print("[setup] Setup complete! You can now run the indexer: python indexer.py")

    except Exception as error:
        print(f"[setup] ERROR: {error}", file=sys.stderr)

        # Provide helpful diagnostics for common HAF setup issues
        error_msg = str(error)
        if "hive.app_create_context" in error_msg:
            print(
                "\n[setup] HINT: The hive.app_create_context function was not found.\n"
                "  This means the HAF extension is not installed in this database.\n"
                "  Make sure you are connecting to a PostgreSQL instance that has:\n"
                "  1. The HAF extension installed (CREATE EXTENSION hive_fork_manager)\n"
                "  2. hived running with sql_serializer plugin writing to this database",
                file=sys.stderr,
            )
        if "hive.contexts" in error_msg:
            print(
                "\n[setup] HINT: The hive.contexts table was not found.\n"
                "  The HAF schema does not exist in this database.\n"
                "  Ensure hived with HAF is properly installed and running.",
                file=sys.stderr,
            )
        if "password authentication" in error_msg:
            print(
                "\n[setup] HINT: Authentication failed. Check your .env credentials.",
                file=sys.stderr,
            )
        if "Connection refused" in error_msg or "could not connect" in error_msg:
            print(
                "\n[setup] HINT: Cannot connect to PostgreSQL.\n"
                "  Verify HAF_DB_HOST and HAF_DB_PORT in your .env file.",
                file=sys.stderr,
            )

        sys.exit(1)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    setup()
