/**
 * HAF Indexer — REST API Server
 * ==============================
 *
 * Provides HTTP endpoints to query data built by the HAF indexer.
 * This is the "read side" of the application — the indexer writes data,
 * and this server reads it.
 *
 * In production HAF deployments, the indexer and API server typically run
 * as separate processes. The indexer writes to PostgreSQL, and one or more
 * API servers read from it. This separation allows:
 *   - Scaling API servers independently of the indexer
 *   - Restarting the API without interrupting indexing
 *   - Load balancing across multiple API replicas
 *
 * Endpoints:
 *   GET /api/transfers/:account   — All transfers for an account
 *   GET /api/stats/:account       — Account transfer statistics
 *   GET /api/top-senders          — Leaderboard of top senders
 *   GET /api/block/:num           — Transfers in a specific block
 *   GET /api/status               — Indexer status and health check
 *
 * Run:
 *   node server.js
 *   # or: npm run serve
 */

const express = require('express');
const { Pool } = require('pg');
require('dotenv').config();

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const APP_NAME = process.env.APP_NAME || 'my_haf_indexer';
const PORT = parseInt(process.env.PORT || '3003', 10);

// PostgreSQL connection pool for the API server.
// HAF apps read from the same database that hived writes to.
// Use a larger pool for the API server than the indexer, since
// multiple API requests may be served concurrently.
const pool = new Pool({
  host: process.env.HAF_DB_HOST || 'localhost',
  port: parseInt(process.env.HAF_DB_PORT || '5432', 10),
  database: process.env.HAF_DB_NAME || 'haf_block_log',
  user: process.env.HAF_DB_USER || 'haf_app',
  password: process.env.HAF_DB_PASSWORD || '',
  max: 10,  // Up to 10 concurrent connections for API serving
});

const app = express();

// ---------------------------------------------------------------------------
// Middleware
// ---------------------------------------------------------------------------
// Parse JSON request bodies (for any future POST endpoints)
app.use(express.json());

// CORS headers — allow browser-based frontends to call this API
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept');
  next();
});

// Request logging
app.use((req, res, next) => {
  const start = Date.now();
  res.on('finish', () => {
    const duration = Date.now() - start;
    console.log(`[api] ${req.method} ${req.url} — ${res.statusCode} (${duration}ms)`);
  });
  next();
});

// ---------------------------------------------------------------------------
// API Endpoints
// ---------------------------------------------------------------------------

/**
 * GET /api/transfers/:account
 *
 * Returns all transfers involving the specified Hive account (as sender OR receiver).
 *
 * Query parameters:
 *   ?limit=50     — Maximum number of results (default 50, max 1000)
 *   ?offset=0     — Pagination offset (default 0)
 *   ?asset=HIVE   — Filter by asset type: HIVE, HBD (optional)
 *   ?direction=sent|received|all — Filter by direction (default: all)
 *
 * Example:
 *   GET /api/transfers/blocktrades?limit=10&asset=HIVE&direction=sent
 *
 * The transfers are read from our application-specific transfers table,
 * NOT directly from hive.operations. This is the whole point of HAF —
 * we pre-process the raw blockchain data into queryable application state.
 */
app.get('/api/transfers/:account', async (req, res) => {
  try {
    const { account } = req.params;
    const limit = Math.min(parseInt(req.query.limit || '50', 10), 1000);
    const offset = parseInt(req.query.offset || '0', 10);
    const asset = req.query.asset;              // Optional: 'HIVE' or 'HBD'
    const direction = req.query.direction || 'all'; // 'sent', 'received', or 'all'

    // Build the WHERE clause dynamically based on query parameters
    let whereClause;
    const params = [];
    let paramIdx = 1;

    // Direction filter: sender, receiver, or both
    if (direction === 'sent') {
      whereClause = `sender = $${paramIdx++}`;
      params.push(account);
    } else if (direction === 'received') {
      whereClause = `receiver = $${paramIdx++}`;
      params.push(account);
    } else {
      // "all" — transfers where account is either sender or receiver
      whereClause = `(sender = $${paramIdx} OR receiver = $${paramIdx})`;
      params.push(account);
      paramIdx++;
    }

    // Optional asset filter
    if (asset) {
      whereClause += ` AND asset = $${paramIdx++}`;
      params.push(asset.toUpperCase());
    }

    // Query our application's transfers table (built by the indexer)
    const result = await pool.query(`
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
      FROM ${APP_NAME}.transfers
      WHERE ${whereClause}
      ORDER BY block_num DESC, trx_in_block DESC
      LIMIT $${paramIdx++} OFFSET $${paramIdx++}
    `, [...params, limit, offset]);

    // Get total count for pagination metadata
    const countResult = await pool.query(`
      SELECT COUNT(*) as total
      FROM ${APP_NAME}.transfers
      WHERE ${whereClause}
    `, params);

    res.json({
      account,
      transfers: result.rows,
      pagination: {
        total: parseInt(countResult.rows[0].total, 10),
        limit,
        offset,
        has_more: offset + limit < parseInt(countResult.rows[0].total, 10),
      },
    });
  } catch (error) {
    console.error('[api] Error in /api/transfers/:account:', error.message);
    res.status(500).json({ error: 'Internal server error', details: error.message });
  }
});

/**
 * GET /api/stats/:account
 *
 * Returns aggregated transfer statistics for a Hive account.
 * This data comes from our pre-computed account_stats table, which the
 * indexer updates incrementally as it processes new blocks.
 *
 * Response includes: total sent/received (HIVE and HBD), transfer count,
 * unique counterparties, first/last transfer timestamps.
 *
 * Example:
 *   GET /api/stats/blocktrades
 */
app.get('/api/stats/:account', async (req, res) => {
  try {
    const { account } = req.params;

    // Query the pre-computed statistics table
    // This is O(1) — just a primary key lookup, no matter how many
    // transfers the account has made. That's the power of pre-aggregation.
    const result = await pool.query(`
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
      FROM ${APP_NAME}.account_stats
      WHERE account = $1
    `, [account]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        error: 'Account not found',
        message: `No transfer data found for account '${account}'. ` +
                 'The account may not have made any transfers, or the indexer ' +
                 'may not have processed their blocks yet.',
      });
    }

    const stats = result.rows[0];

    // Calculate net balance from transfers (this is NOT the account's total
    // balance — just what was moved via transfer operations)
    res.json({
      account: stats.account,
      hive: {
        total_sent: parseFloat(stats.total_sent),
        total_received: parseFloat(stats.total_received),
        net: parseFloat(stats.total_received) - parseFloat(stats.total_sent),
      },
      hbd: {
        total_sent: parseFloat(stats.hbd_sent),
        total_received: parseFloat(stats.hbd_received),
        net: parseFloat(stats.hbd_received) - parseFloat(stats.hbd_sent),
      },
      transfer_count: stats.transfer_count,
      unique_partners: stats.unique_partners,
      first_transfer_at: stats.first_transfer_at,
      last_transfer_at: stats.last_transfer_at,
      last_updated_block: stats.last_updated_block,
    });
  } catch (error) {
    console.error('[api] Error in /api/stats/:account:', error.message);
    res.status(500).json({ error: 'Internal server error', details: error.message });
  }
});

/**
 * GET /api/top-senders
 *
 * Returns a leaderboard of accounts ranked by total HIVE sent.
 *
 * Query parameters:
 *   ?limit=25    — Number of results (default 25, max 100)
 *   ?asset=HIVE  — Rank by HIVE or HBD (default: HIVE)
 *
 * Example:
 *   GET /api/top-senders?limit=10&asset=HBD
 */
app.get('/api/top-senders', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit || '25', 10), 100);
    const asset = (req.query.asset || 'HIVE').toUpperCase();

    // Choose the column to rank by based on the asset parameter
    const sentColumn = asset === 'HBD' ? 'hbd_sent' : 'total_sent';
    const receivedColumn = asset === 'HBD' ? 'hbd_received' : 'total_received';

    // Query the pre-computed account_stats table, ordered by amount sent
    const result = await pool.query(`
      SELECT
        account,
        ${sentColumn} as total_sent,
        ${receivedColumn} as total_received,
        transfer_count,
        last_transfer_at
      FROM ${APP_NAME}.account_stats
      WHERE ${sentColumn} > 0
      ORDER BY ${sentColumn} DESC
      LIMIT $1
    `, [limit]);

    res.json({
      asset,
      leaderboard: result.rows.map((row, index) => ({
        rank: index + 1,
        account: row.account,
        total_sent: parseFloat(row.total_sent),
        total_received: parseFloat(row.total_received),
        transfer_count: row.transfer_count,
        last_transfer_at: row.last_transfer_at,
      })),
    });
  } catch (error) {
    console.error('[api] Error in /api/top-senders:', error.message);
    res.status(500).json({ error: 'Internal server error', details: error.message });
  }
});

/**
 * GET /api/block/:num
 *
 * Returns all transfers that occurred in a specific block.
 *
 * This is useful for:
 *   - Debugging: "What transfers happened in block 80000000?"
 *   - Block explorers: Showing all activity in a block
 *   - Verification: Comparing our indexed data with the raw blockchain
 *
 * Example:
 *   GET /api/block/80000000
 */
app.get('/api/block/:num', async (req, res) => {
  try {
    const blockNum = parseInt(req.params.num, 10);

    if (isNaN(blockNum) || blockNum < 1) {
      return res.status(400).json({
        error: 'Invalid block number',
        message: 'Block number must be a positive integer.',
      });
    }

    // Query transfers in this specific block from our indexed data
    const result = await pool.query(`
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
      FROM ${APP_NAME}.transfers
      WHERE block_num = $1
      ORDER BY trx_in_block, op_pos
    `, [blockNum]);

    // Also get block metadata directly from HAF's hive.blocks table
    // This shows how your app can still query HAF's built-in tables
    // alongside your own application tables.
    const blockInfo = await pool.query(`
      SELECT
        num,
        hash,
        created_at as timestamp,
        producer as witness
      FROM hive.blocks
      WHERE num = $1
    `, [blockNum]);

    res.json({
      block_num: blockNum,
      block_info: blockInfo.rows.length > 0 ? {
        hash: blockInfo.rows[0].hash,
        timestamp: blockInfo.rows[0].timestamp,
        witness: blockInfo.rows[0].witness,
      } : null,
      transfer_count: result.rows.length,
      transfers: result.rows,
    });
  } catch (error) {
    console.error('[api] Error in /api/block/:num:', error.message);
    res.status(500).json({ error: 'Internal server error', details: error.message });
  }
});

/**
 * GET /api/status
 *
 * Returns the current status of the HAF indexer.
 * Useful for monitoring and health checks.
 *
 * Response includes:
 *   - Last processed block number
 *   - Total transfers indexed
 *   - HAF context status
 *   - How far behind the blockchain head we are
 *   - Database connection health
 *
 * Example:
 *   GET /api/status
 */
app.get('/api/status', async (req, res) => {
  try {
    // Get our application's internal state
    const stateResult = await pool.query(`
      SELECT key, value, updated_at
      FROM ${APP_NAME}.indexer_state
    `);
    const state = {};
    stateResult.rows.forEach(row => {
      state[row.key] = { value: row.value, updated_at: row.updated_at };
    });

    // Get the HAF context status — this tells us where HAF thinks we are
    // hive.contexts tracks each registered application's progress
    const contextResult = await pool.query(`
      SELECT
        name,
        current_block_num,
        is_attached,
        events_id
      FROM hive.contexts
      WHERE name = $1
    `, [APP_NAME]);

    // Get the current blockchain head block from HAF
    // hive.blocks contains all blocks that hived has synced
    const headResult = await pool.query(`
      SELECT MAX(num) as head_block
      FROM hive.blocks
    `);

    const lastProcessed = parseInt(state.last_processed_block?.value || '0', 10);
    const headBlock = parseInt(headResult.rows[0]?.head_block || '0', 10);
    const blocksBehinds = headBlock - lastProcessed;

    // Calculate sync percentage
    const syncPct = headBlock > 0 ? ((lastProcessed / headBlock) * 100).toFixed(2) : '0.00';

    res.json({
      app_name: APP_NAME,
      status: blocksBehinds < 100 ? 'synced' : 'syncing',
      last_processed_block: lastProcessed,
      head_block: headBlock,
      blocks_behind: blocksBehinds,
      sync_percentage: `${syncPct}%`,
      total_transfers_indexed: parseInt(state.total_transfers_indexed?.value || '0', 10),
      indexer_version: state.indexer_version?.value || 'unknown',
      haf_context: contextResult.rows.length > 0 ? {
        current_block_num: contextResult.rows[0].current_block_num,
        is_attached: contextResult.rows[0].is_attached,
      } : null,
      database: {
        host: process.env.HAF_DB_HOST || 'localhost',
        database: process.env.HAF_DB_NAME || 'haf_block_log',
        connected: true,
      },
    });
  } catch (error) {
    console.error('[api] Error in /api/status:', error.message);
    res.status(500).json({
      error: 'Internal server error',
      details: error.message,
      database: { connected: false },
    });
  }
});

/**
 * GET / — Root endpoint
 * Simple welcome/discovery page.
 */
app.get('/', (req, res) => {
  res.json({
    name: 'HAF Transfer Indexer API',
    version: '1.0.0',
    description: 'REST API for querying Hive blockchain transfer data indexed via HAF',
    endpoints: {
      'GET /api/transfers/:account': 'All transfers for an account (?limit, ?offset, ?asset, ?direction)',
      'GET /api/stats/:account': 'Aggregated transfer statistics for an account',
      'GET /api/top-senders': 'Leaderboard of top senders (?limit, ?asset)',
      'GET /api/block/:num': 'All transfers in a specific block',
      'GET /api/status': 'Indexer status and sync progress',
    },
    links: {
      haf_docs: 'https://gitlab.syncad.com/hive/haf',
      hive_docs: 'https://developers.hive.io',
    },
  });
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------
// 404 handler for unknown routes
app.use((req, res) => {
  res.status(404).json({
    error: 'Not found',
    message: `No endpoint matches ${req.method} ${req.url}`,
    hint: 'Visit GET / for a list of available endpoints.',
  });
});

// Global error handler
app.use((err, req, res, next) => {
  console.error('[api] Unhandled error:', err);
  res.status(500).json({
    error: 'Internal server error',
    message: err.message,
  });
});

// ---------------------------------------------------------------------------
// Start the server
// ---------------------------------------------------------------------------
app.listen(PORT, () => {
  console.log('='.repeat(70));
  console.log(`HAF Transfer Indexer API — listening on http://localhost:${PORT}`);
  console.log('='.repeat(70));
  console.log(`Database: ${process.env.HAF_DB_NAME || 'haf_block_log'}`);
  console.log(`App context: ${APP_NAME}`);
  console.log('');
  console.log('Available endpoints:');
  console.log(`  GET http://localhost:${PORT}/api/transfers/:account`);
  console.log(`  GET http://localhost:${PORT}/api/stats/:account`);
  console.log(`  GET http://localhost:${PORT}/api/top-senders`);
  console.log(`  GET http://localhost:${PORT}/api/block/:num`);
  console.log(`  GET http://localhost:${PORT}/api/status`);
  console.log('');
  console.log('Press Ctrl+C to stop.');
});

// Graceful shutdown
process.on('SIGINT', async () => {
  console.log('\n[api] Shutting down...');
  await pool.end();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  console.log('\n[api] Shutting down...');
  await pool.end();
  process.exit(0);
});
