/**
 * HAF Indexer — Database Schema Setup
 * ====================================
 *
 * HAF Architecture Tutorial:
 * ==========================
 * HAF (Hive Application Framework) is the OFFICIAL way to build Hive blockchain
 * indexers. It is a PostgreSQL-based framework with these key components:
 *
 * 1. hived (the Hive node daemon) writes ALL blockchain data directly into
 *    PostgreSQL tables via the sql_serializer plugin. Every block, transaction,
 *    and operation is stored in normalized SQL tables.
 *
 * 2. Your application registers as a "HAF application" in the database by
 *    creating an "application context". This context is a named cursor that
 *    tracks which block your app has processed up to.
 *
 * 3. HAF tracks processing progress per-context, so multiple independent
 *    indexers can run against the same database at different speeds.
 *
 * 4. Your app reads operations from HAF's built-in tables (hive.operations,
 *    hive.blocks, etc.) and builds its OWN application-specific state tables.
 *
 * 5. This is MUCH more efficient than streaming from API nodes because:
 *    - No network overhead (direct PostgreSQL queries)
 *    - Batch processing of thousands of blocks at once
 *    - SQL-native filtering and joins
 *    - Automatic blockchain reorganization (fork) handling
 *
 * Key HAF tables (provided by the framework — DO NOT create these):
 * -----------------------------------------------------------------
 * - hive.blocks:          Block metadata (num, hash, timestamp, witness, etc.)
 * - hive.transactions:    Transaction data (hash, block_num, trx_in_block)
 * - hive.operations:      ALL blockchain operations, indexed by block/trx/op
 *                          The `body` column contains the operation as JSON.
 * - hive.accounts:        Account registry (id, name)
 * - hive.operation_types: Lookup table mapping op_type_id to operation names
 *                          (e.g., 2 = 'transfer_operation')
 *
 * Your app creates its OWN tables in its OWN schema for the specific data
 * it cares about. This script creates those tables.
 *
 * Run this once before starting the indexer:
 *   node setup.js
 */

const { Pool } = require('pg');
require('dotenv').config();

// ---------------------------------------------------------------------------
// Configuration — loaded from .env file
// ---------------------------------------------------------------------------
const APP_NAME = process.env.APP_NAME || 'my_haf_indexer';

const pool = new Pool({
  host: process.env.HAF_DB_HOST || 'localhost',
  port: parseInt(process.env.HAF_DB_PORT || '5432', 10),
  database: process.env.HAF_DB_NAME || 'haf_block_log',
  user: process.env.HAF_DB_USER || 'haf_app',
  password: process.env.HAF_DB_PASSWORD || '',
});

// ---------------------------------------------------------------------------
// Schema Setup
// ---------------------------------------------------------------------------
async function setup() {
  const client = await pool.connect();

  try {
    console.log(`[setup] Setting up HAF application: ${APP_NAME}`);
    console.log(`[setup] Database: ${process.env.HAF_DB_NAME || 'haf_block_log'}`);

    // -----------------------------------------------------------------------
    // Step 1: Create the application schema
    // -----------------------------------------------------------------------
    // HAF best practice: each application creates its own PostgreSQL schema
    // to namespace its tables. This avoids collisions with other HAF apps
    // sharing the same database.
    console.log('[setup] Step 1: Creating application schema...');
    await client.query(`CREATE SCHEMA IF NOT EXISTS ${APP_NAME};`);

    // -----------------------------------------------------------------------
    // Step 2: Register the HAF application context
    // -----------------------------------------------------------------------
    // hive.app_create_context(context_name TEXT) registers your application
    // with HAF. This creates an entry in hive.contexts that tracks:
    //   - Which block your app has processed up to
    //   - Whether your app is in a valid state
    //   - Fork handling metadata
    //
    // The context name MUST be unique across all HAF apps on this node.
    // If the context already exists, this call is idempotent (no error).
    //
    // IMPORTANT: The context is what enables HAF's killer feature —
    // automatic fork handling. When the blockchain reorganizes (forks),
    // HAF automatically rolls back your context to the fork point.
    // Your app just needs to re-process blocks from that point.
    console.log('[setup] Step 2: Registering HAF application context...');
    await client.query(`
      DO $$
      BEGIN
        -- Check if context already exists to make this idempotent
        IF NOT EXISTS (
          SELECT 1 FROM hive.contexts WHERE name = '${APP_NAME}'
        ) THEN
          -- Register this application with HAF
          -- This is the fundamental step that connects your app to the framework
          PERFORM hive.app_create_context('${APP_NAME}');
          RAISE NOTICE 'Created HAF context: ${APP_NAME}';
        ELSE
          RAISE NOTICE 'HAF context already exists: ${APP_NAME}';
        END IF;
      END
      $$;
    `);

    // -----------------------------------------------------------------------
    // Step 3: Create application-specific tables
    // -----------------------------------------------------------------------
    // These are YOUR tables — HAF doesn't dictate their structure.
    // Design them based on what your application needs to query.
    //
    // For this transfer indexer, we create:
    //   1. transfers: Every transfer operation on the blockchain
    //   2. account_stats: Aggregated transfer statistics per account
    //   3. indexer_state: Tracks our processing progress
    console.log('[setup] Step 3: Creating application tables...');

    // --- transfers table ---
    // Stores every transfer operation extracted from hive.operations.
    // Each row represents one transfer_operation from the blockchain.
    await client.query(`
      CREATE TABLE IF NOT EXISTS ${APP_NAME}.transfers (
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
    `);

    // --- account_stats table ---
    // Pre-computed aggregate statistics per account. Updated incrementally
    // as new transfers are processed. This avoids expensive full-table scans
    // when querying account summaries.
    await client.query(`
      CREATE TABLE IF NOT EXISTS ${APP_NAME}.account_stats (
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
    `);

    // --- indexer_state table ---
    // Tracks the indexer's own state: last processed block, start time, etc.
    // This supplements the HAF context (which also tracks block progress)
    // with application-specific metadata.
    await client.query(`
      CREATE TABLE IF NOT EXISTS ${APP_NAME}.indexer_state (
        key               TEXT PRIMARY KEY,
        value             TEXT NOT NULL,
        updated_at        TIMESTAMP DEFAULT NOW()
      );
    `);

    // Initialize indexer state with defaults
    await client.query(`
      INSERT INTO ${APP_NAME}.indexer_state (key, value)
      VALUES
        ('last_processed_block', '0'),
        ('start_block', '${process.env.START_BLOCK || 1}'),
        ('total_transfers_indexed', '0'),
        ('indexer_version', '1.0.0')
      ON CONFLICT (key) DO NOTHING;
    `);

    // -----------------------------------------------------------------------
    // Step 4: Create indexes for fast querying
    // -----------------------------------------------------------------------
    // Proper indexing is CRITICAL for HAF apps. Without indexes, queries on
    // millions of transfers would be unacceptably slow.
    //
    // Index design principles for HAF apps:
    // 1. Index columns you filter on (WHERE clause)
    // 2. Index columns you sort on (ORDER BY)
    // 3. Use composite indexes for common query patterns
    // 4. Consider partial indexes for hot data
    console.log('[setup] Step 4: Creating indexes...');

    // Index on sender — for "show all transfers FROM this account" queries
    await client.query(`
      CREATE INDEX IF NOT EXISTS idx_transfers_sender
      ON ${APP_NAME}.transfers (sender);
    `);

    // Index on receiver — for "show all transfers TO this account" queries
    await client.query(`
      CREATE INDEX IF NOT EXISTS idx_transfers_receiver
      ON ${APP_NAME}.transfers (receiver);
    `);

    // Index on block_num — for "show all transfers in block X" queries
    // Also used by the indexer to efficiently find where it left off
    await client.query(`
      CREATE INDEX IF NOT EXISTS idx_transfers_block_num
      ON ${APP_NAME}.transfers (block_num);
    `);

    // Index on timestamp — for time-range queries ("last 24 hours", etc.)
    await client.query(`
      CREATE INDEX IF NOT EXISTS idx_transfers_timestamp
      ON ${APP_NAME}.transfers (timestamp DESC);
    `);

    // Composite index — for the common "all transfers involving account X" query
    // This covers both sender and receiver lookups efficiently
    await client.query(`
      CREATE INDEX IF NOT EXISTS idx_transfers_sender_receiver
      ON ${APP_NAME}.transfers (sender, receiver);
    `);

    // -----------------------------------------------------------------------
    // Step 5: Create helper functions
    // -----------------------------------------------------------------------
    // SQL functions for common operations, called by the indexer.
    console.log('[setup] Step 5: Creating helper functions...');

    // Function to upsert account statistics after processing a transfer.
    // Uses INSERT ... ON CONFLICT for atomic upsert.
    await client.query(`
      CREATE OR REPLACE FUNCTION ${APP_NAME}.upsert_account_stats(
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
        INSERT INTO ${APP_NAME}.account_stats (
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
          total_sent = ${APP_NAME}.account_stats.total_sent + p_sent,
          total_received = ${APP_NAME}.account_stats.total_received + p_received,
          hbd_sent = ${APP_NAME}.account_stats.hbd_sent + p_hbd_sent,
          hbd_received = ${APP_NAME}.account_stats.hbd_received + p_hbd_received,
          transfer_count = ${APP_NAME}.account_stats.transfer_count + p_transfer_count,
          last_transfer_at = GREATEST(${APP_NAME}.account_stats.last_transfer_at, p_timestamp),
          last_updated_block = GREATEST(${APP_NAME}.account_stats.last_updated_block, p_block_num);
      END;
      $$ LANGUAGE plpgsql;
    `);

    // -----------------------------------------------------------------------
    // Step 6: Verify the setup
    // -----------------------------------------------------------------------
    console.log('[setup] Step 6: Verifying setup...');

    // Verify the HAF context was created
    const contextCheck = await client.query(
      `SELECT name, current_block_num FROM hive.contexts WHERE name = $1`,
      [APP_NAME]
    );
    if (contextCheck.rows.length > 0) {
      console.log(`[setup] HAF context '${APP_NAME}' registered at block: ${contextCheck.rows[0].current_block_num}`);
    } else {
      throw new Error(`HAF context '${APP_NAME}' not found after creation!`);
    }

    // List all tables we created
    const tables = await client.query(
      `SELECT table_name FROM information_schema.tables WHERE table_schema = $1 ORDER BY table_name`,
      [APP_NAME]
    );
    console.log(`[setup] Tables created in schema '${APP_NAME}':`);
    tables.rows.forEach(row => console.log(`  - ${APP_NAME}.${row.table_name}`));

    console.log('[setup] Setup complete! You can now run the indexer: npm run index');
  } catch (error) {
    console.error('[setup] ERROR:', error.message);

    // Provide helpful diagnostics for common HAF setup issues
    if (error.message.includes('hive.app_create_context')) {
      console.error('\n[setup] HINT: The hive.app_create_context function was not found.');
      console.error('  This means the HAF extension is not installed in this database.');
      console.error('  Make sure you are connecting to a PostgreSQL instance that has:');
      console.error('  1. The HAF extension installed (CREATE EXTENSION hive_fork_manager)');
      console.error('  2. hived running with sql_serializer plugin writing to this database');
    }
    if (error.message.includes('hive.contexts')) {
      console.error('\n[setup] HINT: The hive.contexts table was not found.');
      console.error('  The HAF schema does not exist in this database.');
      console.error('  Ensure hived with HAF is properly installed and running.');
    }
    if (error.message.includes('password authentication')) {
      console.error('\n[setup] HINT: Authentication failed. Check your .env credentials.');
    }
    if (error.message.includes('ECONNREFUSED')) {
      console.error('\n[setup] HINT: Cannot connect to PostgreSQL.');
      console.error('  Verify HAF_DB_HOST and HAF_DB_PORT in your .env file.');
    }

    process.exit(1);
  } finally {
    client.release();
    await pool.end();
  }
}

// ---------------------------------------------------------------------------
// Run setup
// ---------------------------------------------------------------------------
setup().catch(err => {
  console.error('[setup] Unhandled error:', err);
  process.exit(1);
});
