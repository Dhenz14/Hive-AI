/**
 * HAF Indexer — Main Indexing Loop
 * =================================
 *
 * This is the core of a HAF application. It continuously reads new blocks
 * from HAF's PostgreSQL tables and extracts transfer operations into our
 * application-specific tables.
 *
 * How HAF Indexing Works:
 * -----------------------
 * 1. hived (Hive node) writes every block into PostgreSQL in real-time
 * 2. Our indexer calls hive.app_next_block(context) to get the next block
 *    number that needs processing
 * 3. We query hive.operations for that block's operations, filtering for
 *    the operation types we care about (transfer_operation in this case)
 * 4. We parse the operation JSON and write results to our own tables
 * 5. We call hive.app_context_detach(context) to commit our progress
 * 6. If a blockchain fork/reorg occurs, HAF automatically rolls back our
 *    context to the fork point — we just re-process from there
 *
 * Run:
 *   node indexer.js
 *   # or: npm run index
 *
 * Prerequisites:
 *   - Run setup.js first to create schema and register HAF context
 *   - PostgreSQL with HAF must be running and syncing blocks
 */

const { Pool } = require('pg');
require('dotenv').config();

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const APP_NAME = process.env.APP_NAME || 'my_haf_indexer';
const START_BLOCK = parseInt(process.env.START_BLOCK || '1', 10);
const BATCH_SIZE = parseInt(process.env.BATCH_SIZE || '1000', 10);

// HAF operation type IDs — these are defined by the Hive protocol and stored
// in the hive.operation_types table. You can query that table to find the
// op_type_id for any operation type.
//
// Common operation type IDs:
//   2  = transfer_operation          (HIVE/HBD transfers between accounts)
//   3  = transfer_to_vesting_operation (power up)
//   4  = withdraw_vesting_operation  (power down)
//   5  = limit_order_create_operation
//   6  = limit_order_cancel_operation
//   13 = account_create_operation
//   18 = custom_json_operation       (layer-2 apps like Splinterlands)
//   72 = vote_operation
//
// We index transfer_operation (type_id = 2) in this template.
const TRANSFER_OP_TYPE_ID = 2;

const pool = new Pool({
  host: process.env.HAF_DB_HOST || 'localhost',
  port: parseInt(process.env.HAF_DB_PORT || '5432', 10),
  database: process.env.HAF_DB_NAME || 'haf_block_log',
  user: process.env.HAF_DB_USER || 'haf_app',
  password: process.env.HAF_DB_PASSWORD || '',
  // Use a small pool — the indexer mostly uses one connection at a time
  max: 3,
});

// ---------------------------------------------------------------------------
// Graceful Shutdown
// ---------------------------------------------------------------------------
// HAF indexers should handle SIGINT/SIGTERM gracefully to avoid leaving the
// database in an inconsistent state. We set a flag and let the current batch
// finish before exiting.
let shutdownRequested = false;

process.on('SIGINT', () => {
  console.log('\n[indexer] SIGINT received — finishing current batch and shutting down...');
  shutdownRequested = true;
});

process.on('SIGTERM', () => {
  console.log('\n[indexer] SIGTERM received — shutting down...');
  shutdownRequested = true;
});

// ---------------------------------------------------------------------------
// Amount Parsing
// ---------------------------------------------------------------------------
/**
 * Parse a Hive amount string like "1.000 HIVE" into { numeric, asset }.
 *
 * In the HAF operations table, transfer amounts are stored as JSON objects
 * with a "nai" (Numeric Asset Identifier) field. The body JSON looks like:
 *
 *   {
 *     "type": "transfer_operation",
 *     "value": {
 *       "from": "alice",
 *       "to": "bob",
 *       "amount": {"amount": "1000", "precision": 3, "nai": "@@000000021"},
 *       "memo": "hello"
 *     }
 *   }
 *
 * NAI codes:
 *   @@000000021 = HIVE (formerly STEEM)
 *   @@000000013 = HBD  (Hive Backed Dollars, formerly SBD)
 *   @@000000037 = VESTS (Hive Power vesting shares)
 */
function parseAmount(amountObj) {
  // HAF stores amounts as {amount: "1000", precision: 3, nai: "@@000000021"}
  const rawAmount = parseInt(amountObj.amount, 10);
  const precision = amountObj.precision;

  // Convert integer amount to decimal using precision
  // e.g., amount=1000, precision=3 → 1.000
  const numeric = rawAmount / Math.pow(10, precision);

  // Map NAI codes to human-readable asset names
  const naiMap = {
    '@@000000021': 'HIVE',
    '@@000000013': 'HBD',
    '@@000000037': 'VESTS',
  };
  const asset = naiMap[amountObj.nai] || 'UNKNOWN';

  return {
    numeric: numeric.toFixed(precision),   // e.g., "1.000"
    asset,                                  // e.g., "HIVE"
    display: `${numeric.toFixed(precision)} ${asset}`, // e.g., "1.000 HIVE"
  };
}

// ---------------------------------------------------------------------------
// Block Processing
// ---------------------------------------------------------------------------
/**
 * Process a batch of blocks from HAF.
 *
 * HAF Batch Processing Strategy:
 * ==============================
 * Instead of processing one block at a time (slow!), we process blocks in
 * batches within a single database transaction. This is dramatically faster:
 *
 *   - Single block:  ~100 blocks/second
 *   - Batch of 1000: ~10,000 blocks/second (100x faster!)
 *
 * The batch approach:
 * 1. Start a transaction
 * 2. Query all operations in the block range [startBlock, endBlock]
 * 3. Insert all parsed transfers in bulk
 * 4. Update account stats
 * 5. Update HAF context progress
 * 6. Commit transaction
 *
 * If anything fails, the entire batch rolls back — no partial state.
 */
async function processBlockBatch(client, startBlock, endBlock) {
  // -------------------------------------------------------------------------
  // Query HAF's operations table for transfer operations in this block range
  // -------------------------------------------------------------------------
  // hive.operations is the master table that HAF populates from the blockchain.
  // Each row is one operation from one transaction in one block.
  //
  // Key columns:
  //   - block_num:     Which block this operation is in
  //   - trx_in_block:  Index of the transaction within the block
  //   - op_pos:        Position of this operation within the transaction
  //   - op_type_id:    Operation type (2 = transfer_operation)
  //   - body:          Full operation JSON (varies by op type)
  //
  // We JOIN with hive.blocks to get the block timestamp.
  //
  // IMPORTANT: We filter by op_type_id for performance. Without this filter,
  // we'd scan ALL operations (votes, comments, custom_json, etc.) and discard
  // 99%+ of them. The op_type_id column is indexed by HAF.
  const opsResult = await client.query(`
    SELECT
      o.block_num,
      o.trx_in_block,
      o.op_pos,
      o.body::text as body,       -- Operation JSON as text (we parse in JS)
      b.created_at as timestamp   -- Block timestamp from hive.blocks
    FROM hive.operations o
    JOIN hive.blocks b ON b.num = o.block_num
    WHERE o.block_num >= $1
      AND o.block_num <= $2
      AND o.op_type_id = $3       -- Only transfer_operation (type 2)
    ORDER BY o.block_num, o.trx_in_block, o.op_pos
  `, [startBlock, endBlock, TRANSFER_OP_TYPE_ID]);

  if (opsResult.rows.length === 0) {
    return { transferCount: 0, blocksProcessed: endBlock - startBlock + 1 };
  }

  // -------------------------------------------------------------------------
  // Parse and insert each transfer operation
  // -------------------------------------------------------------------------
  let transferCount = 0;
  const accountUpdates = new Map(); // Accumulate stats updates per account

  for (const row of opsResult.rows) {
    // Parse the operation JSON body
    // The body structure for transfer_operation:
    //   {
    //     "type": "transfer_operation",
    //     "value": {
    //       "from": "sender_account",
    //       "to": "receiver_account",
    //       "amount": {"amount": "1000", "precision": 3, "nai": "@@000000021"},
    //       "memo": "optional memo text"
    //     }
    //   }
    let opBody;
    try {
      opBody = JSON.parse(row.body);
    } catch (parseErr) {
      console.warn(`[indexer] WARNING: Failed to parse operation JSON in block ${row.block_num}: ${parseErr.message}`);
      continue;
    }

    const value = opBody.value;
    if (!value || !value.from || !value.to || !value.amount) {
      console.warn(`[indexer] WARNING: Malformed transfer in block ${row.block_num}`);
      continue;
    }

    const amount = parseAmount(value.amount);
    const sender = value.from;
    const receiver = value.to;
    const memo = value.memo || '';

    // Insert the transfer into our application table
    // ON CONFLICT DO NOTHING handles the case where we re-process a block
    // (e.g., after a fork rollback)
    await client.query(`
      INSERT INTO ${APP_NAME}.transfers
        (block_num, trx_in_block, op_pos, timestamp, sender, receiver,
         amount, amount_numeric, asset, memo)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
      ON CONFLICT (block_num, trx_in_block, op_pos) DO NOTHING
    `, [
      row.block_num,
      row.trx_in_block,
      row.op_pos,
      row.timestamp,
      sender,
      receiver,
      amount.display,      // e.g., "1.000 HIVE"
      amount.numeric,      // e.g., 1.000
      amount.asset,        // e.g., "HIVE"
      memo,
    ]);

    transferCount++;

    // -----------------------------------------------------------------------
    // Accumulate account statistics
    // -----------------------------------------------------------------------
    // Instead of updating account_stats for every single transfer (slow),
    // we accumulate changes in memory and apply them in bulk at the end
    // of the batch.
    const senderStats = accountUpdates.get(sender) || {
      sent: 0, received: 0, hbd_sent: 0, hbd_received: 0, count: 0,
      timestamp: row.timestamp, block_num: row.block_num,
    };
    const receiverStats = accountUpdates.get(receiver) || {
      sent: 0, received: 0, hbd_sent: 0, hbd_received: 0, count: 0,
      timestamp: row.timestamp, block_num: row.block_num,
    };

    const numericAmount = parseFloat(amount.numeric);
    if (amount.asset === 'HIVE') {
      senderStats.sent += numericAmount;
      receiverStats.received += numericAmount;
    } else if (amount.asset === 'HBD') {
      senderStats.hbd_sent += numericAmount;
      receiverStats.hbd_received += numericAmount;
    }
    senderStats.count += 1;
    receiverStats.count += 1;
    senderStats.timestamp = row.timestamp;
    senderStats.block_num = row.block_num;
    receiverStats.timestamp = row.timestamp;
    receiverStats.block_num = row.block_num;

    accountUpdates.set(sender, senderStats);
    accountUpdates.set(receiver, receiverStats);
  }

  // -------------------------------------------------------------------------
  // Bulk-update account statistics
  // -------------------------------------------------------------------------
  // Apply all accumulated account stat changes using our helper function.
  // This is much faster than updating after every single transfer.
  for (const [account, stats] of accountUpdates) {
    await client.query(`
      SELECT ${APP_NAME}.upsert_account_stats($1, $2, $3, $4, $5, $6, $7, $8)
    `, [
      account,
      stats.sent,
      stats.received,
      stats.hbd_sent,
      stats.hbd_received,
      stats.count,
      stats.timestamp,
      stats.block_num,
    ]);
  }

  return {
    transferCount,
    blocksProcessed: endBlock - startBlock + 1,
    accountsUpdated: accountUpdates.size,
  };
}

// ---------------------------------------------------------------------------
// Main Indexer Loop
// ---------------------------------------------------------------------------
/**
 * The main indexing loop. This runs continuously, processing new blocks as
 * they become available in HAF.
 *
 * HAF Context Lifecycle:
 * ======================
 *
 * 1. ATTACH: hive.app_context_attach(context, start_block)
 *    Tells HAF "I want to start processing from this block."
 *    Only needed on first run — on subsequent runs, HAF remembers your position.
 *
 * 2. NEXT BLOCK: hive.app_next_block(context)
 *    Returns the next block number to process, or NULL if caught up.
 *    This is the PRIMARY API for HAF indexers.
 *    - Returns a block number: process this block
 *    - Returns NULL: you're caught up, wait and retry
 *    - If a fork occurred, returns a LOWER block number than last time
 *      (HAF rolled back your context automatically!)
 *
 * 3. DETACH: hive.app_context_detach(context)
 *    Saves your progress. Call this periodically (e.g., after each batch).
 *    After detaching, hive.app_next_block() will resume from where you left off.
 *
 * Fork Handling:
 * ==============
 * HAF's killer feature is automatic fork handling. Here's how it works:
 *
 * 1. Your app processes blocks 1000-1050
 * 2. A blockchain reorganization occurs at block 1045
 * 3. HAF detects the fork and automatically rolls back your context to block 1044
 * 4. Next call to hive.app_next_block() returns 1045 (the new version)
 * 5. Your app re-processes blocks 1045-1050 with the correct data
 *
 * For this to work correctly, your app's INSERT statements should use
 * ON CONFLICT to handle re-processing the same block numbers. Our transfers
 * table has a UNIQUE constraint on (block_num, trx_in_block, op_pos) for this.
 *
 * For applications that need to DELETE old data on fork, you can listen for
 * fork events and clean up accordingly. For most apps (like this one), the
 * ON CONFLICT approach is simpler and sufficient.
 */
async function runIndexer() {
  console.log('='.repeat(70));
  console.log(`HAF Transfer Indexer — ${APP_NAME}`);
  console.log('='.repeat(70));
  console.log(`Database: ${process.env.HAF_DB_NAME || 'haf_block_log'}`);
  console.log(`Batch size: ${BATCH_SIZE} blocks`);
  console.log(`Start block: ${START_BLOCK}`);
  console.log('');

  const client = await pool.connect();

  try {
    // -----------------------------------------------------------------------
    // Step 1: Check if context exists and determine starting point
    // -----------------------------------------------------------------------
    // Query the HAF context to see where we left off last time.
    // The current_block_num column tells us the last block we committed.
    const contextResult = await client.query(
      `SELECT current_block_num, is_attached
       FROM hive.contexts
       WHERE name = $1`,
      [APP_NAME]
    );

    if (contextResult.rows.length === 0) {
      console.error(`[indexer] ERROR: HAF context '${APP_NAME}' not found!`);
      console.error('  Run "npm run setup" first to create the schema and context.');
      process.exit(1);
    }

    const context = contextResult.rows[0];
    console.log(`[indexer] HAF context '${APP_NAME}': last block = ${context.current_block_num}`);

    // -----------------------------------------------------------------------
    // Step 2: Attach the context (if not already attached)
    // -----------------------------------------------------------------------
    // hive.app_context_attach(context_name, start_block) tells HAF that we
    // are starting to process blocks. If we've processed blocks before, HAF
    // resumes from where we left off (ignoring start_block).
    //
    // If already attached (e.g., from a previous crashed run), we detach first
    // to reset the state cleanly.
    if (context.is_attached) {
      console.log('[indexer] Context is already attached (previous run may have crashed). Detaching first...');
      await client.query(`SELECT hive.app_context_detach('${APP_NAME}')`);
    }

    // Attach the context — HAF starts tracking our progress from this point
    console.log(`[indexer] Attaching HAF context at start_block ${START_BLOCK}...`);
    await client.query(
      `SELECT hive.app_context_attach('${APP_NAME}', $1)`,
      [START_BLOCK]
    );

    // -----------------------------------------------------------------------
    // Step 3: Main processing loop
    // -----------------------------------------------------------------------
    console.log('[indexer] Starting block processing loop...');
    console.log('[indexer] Press Ctrl+C to stop gracefully.\n');

    let totalTransfers = 0;
    let totalBlocks = 0;
    let lastLogTime = Date.now();
    let lastBlock = 0;

    while (!shutdownRequested) {
      // ---------------------------------------------------------------------
      // Get the next block range to process from HAF
      // ---------------------------------------------------------------------
      // hive.app_next_block(context_name) returns the next unprocessed block
      // number, or NULL if we're caught up to the head of the chain.
      //
      // This is the CORE of the HAF API — it handles:
      //   - Tracking which blocks you've already processed
      //   - Detecting blockchain forks and rolling back your position
      //   - Coordinating with hived's block production
      const nextBlockResult = await client.query(
        `SELECT hive.app_next_block('${APP_NAME}') as next_block`
      );

      const nextBlock = nextBlockResult.rows[0].next_block;

      // NULL means we've caught up to the blockchain head
      // Wait a bit and check again (hived produces blocks every 3 seconds)
      if (nextBlock === null) {
        // Log status periodically while waiting
        if (Date.now() - lastLogTime > 10000) {
          console.log(`[indexer] Caught up! Waiting for new blocks... (${totalBlocks} blocks, ${totalTransfers} transfers processed)`);
          lastLogTime = Date.now();
        }

        // Detach to save progress before sleeping
        await client.query(`SELECT hive.app_context_detach('${APP_NAME}')`);

        // Wait 1 second, then re-attach and continue
        // Hive produces a block every 3 seconds, so 1s polling is fine
        await new Promise(resolve => setTimeout(resolve, 1000));

        // Re-attach to continue processing
        if (!shutdownRequested) {
          await client.query(
            `SELECT hive.app_context_attach('${APP_NAME}', $1)`,
            [START_BLOCK]
          );
        }
        continue;
      }

      // Calculate end of this batch
      // We process up to BATCH_SIZE blocks at once for efficiency
      const endBlock = nextBlock + BATCH_SIZE - 1;

      // ---------------------------------------------------------------------
      // Process this batch of blocks
      // ---------------------------------------------------------------------
      // Wrap the entire batch in a transaction for atomicity.
      // If anything fails, the whole batch rolls back cleanly.
      await client.query('BEGIN');

      try {
        const result = await processBlockBatch(client, nextBlock, endBlock);

        // Update our internal state tracking
        await client.query(`
          UPDATE ${APP_NAME}.indexer_state
          SET value = $1, updated_at = NOW()
          WHERE key = 'last_processed_block'
        `, [endBlock.toString()]);

        await client.query(`
          UPDATE ${APP_NAME}.indexer_state
          SET value = (CAST(value AS BIGINT) + $1)::text, updated_at = NOW()
          WHERE key = 'total_transfers_indexed'
        `, [result.transferCount]);

        await client.query('COMMIT');

        totalTransfers += result.transferCount;
        totalBlocks += result.blocksProcessed;
        lastBlock = endBlock;

        // Log progress periodically (every 5 seconds or every batch with transfers)
        const now = Date.now();
        if (result.transferCount > 0 || now - lastLogTime > 5000) {
          const rate = totalBlocks / ((now - lastLogTime) / 1000) || 0;
          console.log(
            `[indexer] Block ${nextBlock}-${endBlock}: ` +
            `${result.transferCount} transfers, ` +
            `${result.accountsUpdated || 0} accounts updated ` +
            `(total: ${totalBlocks} blocks, ${totalTransfers} transfers)`
          );
          lastLogTime = now;
        }
      } catch (batchError) {
        // Roll back the failed batch — no partial state
        await client.query('ROLLBACK');
        console.error(`[indexer] ERROR processing blocks ${nextBlock}-${endBlock}:`, batchError.message);

        // Wait before retrying to avoid tight error loops
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
    }

    // -----------------------------------------------------------------------
    // Clean shutdown
    // -----------------------------------------------------------------------
    // Detach the context to save our progress before exiting.
    // Next time we start, HAF will resume from this point.
    console.log('\n[indexer] Shutting down...');
    try {
      await client.query(`SELECT hive.app_context_detach('${APP_NAME}')`);
      console.log(`[indexer] Context detached. Last processed block: ${lastBlock}`);
    } catch (detachErr) {
      // Context may already be detached
      console.warn('[indexer] Warning: Could not detach context:', detachErr.message);
    }

    console.log(`[indexer] Final stats: ${totalBlocks} blocks, ${totalTransfers} transfers`);
    console.log('[indexer] Goodbye!');

  } catch (error) {
    console.error('[indexer] FATAL ERROR:', error.message);
    console.error(error.stack);
    process.exit(1);
  } finally {
    client.release();
    await pool.end();
  }
}

// ---------------------------------------------------------------------------
// Run the indexer
// ---------------------------------------------------------------------------
runIndexer().catch(err => {
  console.error('[indexer] Unhandled error:', err);
  process.exit(1);
});
