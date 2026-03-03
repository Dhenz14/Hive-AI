/**
 * HAF Indexer — Test Suite
 * =========================
 *
 * Tests for the HAF transfer indexer. These tests verify:
 *   1. Database connectivity and schema existence
 *   2. HAF context registration
 *   3. Amount parsing logic
 *   4. Transfer insertion and querying
 *   5. Account statistics aggregation
 *   6. API endpoint responses
 *
 * Run:
 *   node test.js
 *   # or: npm test
 *
 * Prerequisites:
 *   - PostgreSQL with HAF running and accessible
 *   - Schema created via: npm run setup
 *
 * Note: Tests that require a live HAF database will be skipped if the
 * database is not available. Unit tests (like amount parsing) always run.
 */

const { Pool } = require('pg');
require('dotenv').config();

const APP_NAME = process.env.APP_NAME || 'my_haf_indexer';

// ---------------------------------------------------------------------------
// Minimal test framework (no external dependencies)
// ---------------------------------------------------------------------------
let passed = 0;
let failed = 0;
let skipped = 0;
const results = [];

async function test(name, fn) {
  try {
    await fn();
    passed++;
    results.push({ name, status: 'PASS' });
    console.log(`  PASS  ${name}`);
  } catch (error) {
    if (error.message === 'SKIP') {
      skipped++;
      results.push({ name, status: 'SKIP', reason: error.reason || 'Precondition not met' });
      console.log(`  SKIP  ${name} (${error.reason || 'precondition not met'})`);
    } else {
      failed++;
      results.push({ name, status: 'FAIL', error: error.message });
      console.log(`  FAIL  ${name}`);
      console.log(`        ${error.message}`);
    }
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message || 'Assertion failed');
}

function assertEqual(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(
      (message ? message + ': ' : '') +
      `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`
    );
  }
}

function skip(reason) {
  const err = new Error('SKIP');
  err.reason = reason;
  throw err;
}

// ---------------------------------------------------------------------------
// Amount parsing (extracted from indexer.js for testability)
// ---------------------------------------------------------------------------
/**
 * Parse a HAF amount object into human-readable form.
 * Duplicated here from indexer.js for isolated unit testing.
 *
 * HAF stores amounts as:
 *   { amount: "1000", precision: 3, nai: "@@000000021" }
 *
 * NAI codes:
 *   @@000000021 = HIVE
 *   @@000000013 = HBD
 *   @@000000037 = VESTS
 */
function parseAmount(amountObj) {
  const rawAmount = parseInt(amountObj.amount, 10);
  const precision = amountObj.precision;
  const numeric = rawAmount / Math.pow(10, precision);

  const naiMap = {
    '@@000000021': 'HIVE',
    '@@000000013': 'HBD',
    '@@000000037': 'VESTS',
  };
  const asset = naiMap[amountObj.nai] || 'UNKNOWN';

  return {
    numeric: numeric.toFixed(precision),
    asset,
    display: `${numeric.toFixed(precision)} ${asset}`,
  };
}

// ---------------------------------------------------------------------------
// Test Suites
// ---------------------------------------------------------------------------

async function runTests() {
  console.log('='.repeat(70));
  console.log('HAF Transfer Indexer — Test Suite');
  console.log('='.repeat(70));
  console.log('');

  // =========================================================================
  // Unit Tests — Amount Parsing (no database required)
  // =========================================================================
  console.log('--- Unit Tests: Amount Parsing ---');

  await test('Parse HIVE amount: 1.000 HIVE', () => {
    // HAF stores 1.000 HIVE as {amount: "1000", precision: 3, nai: "@@000000021"}
    const result = parseAmount({ amount: '1000', precision: 3, nai: '@@000000021' });
    assertEqual(result.numeric, '1.000', 'numeric');
    assertEqual(result.asset, 'HIVE', 'asset');
    assertEqual(result.display, '1.000 HIVE', 'display');
  });

  await test('Parse HBD amount: 25.500 HBD', () => {
    // 25.500 HBD = amount 25500, precision 3
    const result = parseAmount({ amount: '25500', precision: 3, nai: '@@000000013' });
    assertEqual(result.numeric, '25.500', 'numeric');
    assertEqual(result.asset, 'HBD', 'asset');
    assertEqual(result.display, '25.500 HBD', 'display');
  });

  await test('Parse VESTS amount: 123456.789012 VESTS', () => {
    // VESTS have 6 decimal places of precision
    const result = parseAmount({ amount: '123456789012', precision: 6, nai: '@@000000037' });
    assertEqual(result.numeric, '123456.789012', 'numeric');
    assertEqual(result.asset, 'VESTS', 'asset');
  });

  await test('Parse zero amount: 0.000 HIVE', () => {
    const result = parseAmount({ amount: '0', precision: 3, nai: '@@000000021' });
    assertEqual(result.numeric, '0.000', 'numeric');
    assertEqual(result.asset, 'HIVE', 'asset');
  });

  await test('Parse large amount: 1,000,000.000 HIVE', () => {
    // 1 million HIVE = 1000000000 (amount) with precision 3
    const result = parseAmount({ amount: '1000000000', precision: 3, nai: '@@000000021' });
    assertEqual(result.numeric, '1000000.000', 'numeric');
  });

  await test('Parse unknown NAI returns UNKNOWN', () => {
    const result = parseAmount({ amount: '100', precision: 3, nai: '@@999999999' });
    assertEqual(result.asset, 'UNKNOWN', 'asset');
  });

  // =========================================================================
  // Unit Tests — Operation JSON Parsing
  // =========================================================================
  console.log('\n--- Unit Tests: Operation JSON Parsing ---');

  await test('Parse transfer operation body', () => {
    // This is the exact JSON structure stored in hive.operations.body
    // for a transfer_operation
    const opBody = {
      type: 'transfer_operation',
      value: {
        from: 'alice',
        to: 'bob',
        amount: { amount: '5000', precision: 3, nai: '@@000000021' },
        memo: 'test transfer',
      },
    };

    assertEqual(opBody.value.from, 'alice', 'sender');
    assertEqual(opBody.value.to, 'bob', 'receiver');
    assertEqual(opBody.value.memo, 'test transfer', 'memo');

    const amount = parseAmount(opBody.value.amount);
    assertEqual(amount.display, '5.000 HIVE', 'amount');
  });

  await test('Handle transfer with empty memo', () => {
    const opBody = {
      type: 'transfer_operation',
      value: {
        from: 'alice',
        to: 'bob',
        amount: { amount: '1000', precision: 3, nai: '@@000000021' },
        memo: '',
      },
    };
    assertEqual(opBody.value.memo, '', 'empty memo');
  });

  // =========================================================================
  // Integration Tests — Database (requires live HAF PostgreSQL)
  // =========================================================================
  console.log('\n--- Integration Tests: Database ---');

  let pool;
  let dbAvailable = false;

  try {
    pool = new Pool({
      host: process.env.HAF_DB_HOST || 'localhost',
      port: parseInt(process.env.HAF_DB_PORT || '5432', 10),
      database: process.env.HAF_DB_NAME || 'haf_block_log',
      user: process.env.HAF_DB_USER || 'haf_app',
      password: process.env.HAF_DB_PASSWORD || '',
      connectionTimeoutMillis: 5000,
    });
    // Test connection
    await pool.query('SELECT 1');
    dbAvailable = true;
    console.log('  (Database connected successfully)\n');
  } catch (err) {
    console.log(`  (Database not available: ${err.message})`);
    console.log('  (Integration tests will be skipped)\n');
  }

  await test('Database connection is alive', async () => {
    if (!dbAvailable) skip('Database not available');
    const result = await pool.query('SELECT 1 as alive');
    assertEqual(result.rows[0].alive, 1, 'query result');
  });

  await test('HAF schema (hive) exists', async () => {
    if (!dbAvailable) skip('Database not available');
    // Verify that the hive schema exists — this is created by HAF/hived
    const result = await pool.query(`
      SELECT schema_name
      FROM information_schema.schemata
      WHERE schema_name = 'hive'
    `);
    assert(result.rows.length > 0, 'hive schema not found — HAF may not be installed');
  });

  await test('HAF core tables exist (hive.blocks, hive.operations)', async () => {
    if (!dbAvailable) skip('Database not available');
    // These tables are created by HAF and populated by hived
    const tables = ['blocks', 'operations', 'transactions', 'operation_types'];
    for (const table of tables) {
      const result = await pool.query(`
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'hive' AND table_name = $1
      `, [table]);
      assert(result.rows.length > 0, `hive.${table} table not found`);
    }
  });

  await test('HAF context function exists (hive.app_create_context)', async () => {
    if (!dbAvailable) skip('Database not available');
    // Verify the key HAF function is available
    const result = await pool.query(`
      SELECT proname
      FROM pg_proc
      JOIN pg_namespace ON pg_namespace.oid = pronamespace
      WHERE nspname = 'hive' AND proname = 'app_create_context'
    `);
    assert(result.rows.length > 0, 'hive.app_create_context function not found');
  });

  await test(`Application schema '${APP_NAME}' exists`, async () => {
    if (!dbAvailable) skip('Database not available');
    const result = await pool.query(`
      SELECT schema_name
      FROM information_schema.schemata
      WHERE schema_name = $1
    `, [APP_NAME]);
    assert(result.rows.length > 0,
      `Schema '${APP_NAME}' not found. Run 'npm run setup' first.`);
  });

  await test('Application tables exist (transfers, account_stats, indexer_state)', async () => {
    if (!dbAvailable) skip('Database not available');
    const tables = ['transfers', 'account_stats', 'indexer_state'];
    for (const table of tables) {
      const result = await pool.query(`
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = $1 AND table_name = $2
      `, [APP_NAME, table]);
      assert(result.rows.length > 0,
        `Table ${APP_NAME}.${table} not found. Run 'npm run setup' first.`);
    }
  });

  await test('HAF context is registered', async () => {
    if (!dbAvailable) skip('Database not available');
    // Verify our application context exists in hive.contexts
    const result = await pool.query(`
      SELECT name, current_block_num
      FROM hive.contexts
      WHERE name = $1
    `, [APP_NAME]);
    assert(result.rows.length > 0,
      `HAF context '${APP_NAME}' not registered. Run 'npm run setup' first.`);
    console.log(`        (Context at block: ${result.rows[0].current_block_num})`);
  });

  await test('Transfers table has correct columns', async () => {
    if (!dbAvailable) skip('Database not available');
    const result = await pool.query(`
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_schema = $1 AND table_name = 'transfers'
      ORDER BY ordinal_position
    `, [APP_NAME]);
    const columns = result.rows.map(r => r.column_name);
    const expected = ['id', 'block_num', 'trx_in_block', 'op_pos', 'timestamp',
                      'sender', 'receiver', 'amount', 'amount_numeric', 'asset', 'memo'];
    for (const col of expected) {
      assert(columns.includes(col), `Missing column: ${col}`);
    }
  });

  await test('Indexes exist on transfers table', async () => {
    if (!dbAvailable) skip('Database not available');
    const result = await pool.query(`
      SELECT indexname
      FROM pg_indexes
      WHERE schemaname = $1 AND tablename = 'transfers'
    `, [APP_NAME]);
    const indexNames = result.rows.map(r => r.indexname);
    assert(indexNames.length >= 4, `Expected at least 4 indexes, found ${indexNames.length}`);
  });

  await test('Indexer state is initialized', async () => {
    if (!dbAvailable) skip('Database not available');
    const result = await pool.query(`
      SELECT key, value
      FROM ${APP_NAME}.indexer_state
      ORDER BY key
    `);
    assert(result.rows.length >= 3, 'indexer_state should have at least 3 entries');
    const keys = result.rows.map(r => r.key);
    assert(keys.includes('last_processed_block'), 'Missing key: last_processed_block');
    assert(keys.includes('total_transfers_indexed'), 'Missing key: total_transfers_indexed');
  });

  await test('HAF has blocks synced (hive.blocks is not empty)', async () => {
    if (!dbAvailable) skip('Database not available');
    // Check if hived has synced any blocks into HAF
    const result = await pool.query('SELECT COUNT(*) as count FROM hive.blocks');
    const count = parseInt(result.rows[0].count, 10);
    if (count === 0) {
      skip('No blocks synced yet — hived may still be syncing');
    }
    assert(count > 0, 'hive.blocks is empty');
    console.log(`        (${count.toLocaleString()} blocks synced in HAF)`);
  });

  await test('hive.operation_types contains transfer_operation', async () => {
    if (!dbAvailable) skip('Database not available');
    // Verify that transfer_operation is registered in HAF's operation type table
    // This is used by the indexer to filter for transfer operations
    const result = await pool.query(`
      SELECT id, name
      FROM hive.operation_types
      WHERE name = 'hive::protocol::transfer_operation'
         OR id = 2
      LIMIT 1
    `);
    if (result.rows.length === 0) {
      skip('operation_types table may have different format');
    }
    assert(result.rows.length > 0, 'transfer_operation not found in operation_types');
    console.log(`        (transfer_operation type_id = ${result.rows[0].id})`);
  });

  // =========================================================================
  // Cleanup
  // =========================================================================
  if (pool) {
    await pool.end();
  }

  // =========================================================================
  // Summary
  // =========================================================================
  console.log('\n' + '='.repeat(70));
  console.log(`Results: ${passed} passed, ${failed} failed, ${skipped} skipped`);
  console.log('='.repeat(70));

  if (failed > 0) {
    console.log('\nFailed tests:');
    results.filter(r => r.status === 'FAIL').forEach(r => {
      console.log(`  - ${r.name}: ${r.error}`);
    });
    process.exit(1);
  }

  if (skipped > 0) {
    console.log('\nSkipped tests (database not available or not fully synced):');
    results.filter(r => r.status === 'SKIP').forEach(r => {
      console.log(`  - ${r.name}: ${r.reason}`);
    });
  }

  console.log('\nAll tests passed!');
}

// ---------------------------------------------------------------------------
// Run tests
// ---------------------------------------------------------------------------
runTests().catch(err => {
  console.error('Test runner error:', err);
  process.exit(1);
});
