/**
 * =============================================================================
 * Hive Engine Token Operations Server
 * =============================================================================
 *
 * ARCHITECTURE OVERVIEW — How Hive Engine Works:
 *
 * Hive Engine is a Layer 2 (L2) sidechain built on top of Hive (Layer 1 / L1).
 * It enables custom token creation, transfers, staking, and a decentralized
 * exchange (DEX) — features not natively available on Hive's base layer.
 *
 * THE LAYER 1 / LAYER 2 BRIDGE:
 *
 *   1. A user wants to transfer 10 BEE tokens to another account.
 *   2. This app constructs a JSON payload describing the operation.
 *   3. The payload is wrapped in a "custom_json" operation and broadcast to
 *      the Hive LAYER 1 blockchain (using dhive and the user's active key).
 *   4. Hive Engine sidechain nodes watch the L1 blockchain for custom_json ops
 *      with id="ssc-mainnet-hive".
 *   5. When they see one, they parse the JSON payload, validate it, and execute
 *      the token operation on their sidechain database.
 *   6. The sidechain maintains its own state: token balances, market orders,
 *      staking records, etc.
 *
 * So: Layer 1 is the TRANSPORT (immutable, trustless), and Layer 2 is the
 * EXECUTION ENGINE (fast, feature-rich, indexed by sidechain nodes).
 *
 * KEY CONCEPTS:
 *   - HIVE/HBD: Native Layer 1 tokens, handled by hived consensus
 *   - BEE, DEC, SPS, etc.: Layer 2 tokens, handled by Hive Engine sidechain
 *   - custom_json: The Hive L1 operation type used as the bridge
 *   - "ssc-mainnet-hive": The custom_json ID that Hive Engine nodes watch for
 *   - Active key: Required because token ops are financial (not social/posting)
 *
 * TWO APIs IN PLAY:
 *   - Hive RPC (api.hive.blog): For broadcasting custom_json ops to Layer 1
 *   - Hive Engine RPC (api.hive-engine.com): For reading sidechain state
 *
 * =============================================================================
 */

// Load environment variables from .env file before anything else
require('dotenv').config();

const express = require('express');
const axios = require('axios');

// dhive is the official JavaScript library for interacting with the Hive blockchain.
// It handles key management, transaction signing, and broadcasting to Hive Layer 1 nodes.
const dhive = require('@hiveio/dhive');

// sscjs is a lightweight client for querying the Hive Engine sidechain API.
// It provides convenient methods for reading token data, balances, and market state
// from the Layer 2 sidechain — but NOT for writing (writes go through Layer 1).
const SSC = require('sscjs');

// =============================================================================
// Configuration
// =============================================================================

const HIVE_ACCOUNT = process.env.HIVE_ACCOUNT;
const HIVE_ACTIVE_KEY = process.env.HIVE_ACTIVE_KEY;
const HIVE_NODE = process.env.HIVE_NODE || 'https://api.hive.blog';
const HIVE_ENGINE_API = process.env.HIVE_ENGINE_API || 'https://api.hive-engine.com/rpc';
const PORT = process.env.PORT || 3002;

// Initialize the dhive client, connecting to a Hive Layer 1 RPC node.
// This client is used ONLY for broadcasting custom_json operations to the mainnet.
// Multiple nodes can be specified for failover.
const hiveClient = new dhive.Client([
  HIVE_NODE,
  'https://api.deathwing.me',        // Backup node for reliability
  'https://api.openhive.network'     // Another backup node
]);

// Initialize the Hive Engine sidechain client.
// This connects to the Hive Engine API for READING sidechain state:
// token info, balances, market orders, transaction history, etc.
// It does NOT broadcast transactions — that always goes through Layer 1.
const ssc = new SSC(HIVE_ENGINE_API);

const app = express();

// Parse JSON request bodies for POST endpoints
app.use(express.json());

// =============================================================================
// Helper: Query Hive Engine Sidechain via JSON-RPC
// =============================================================================

/**
 * Sends a JSON-RPC request to the Hive Engine sidechain API.
 *
 * The Hive Engine API uses a JSON-RPC interface where you specify:
 *   - contract: Which smart contract to query (tokens, market, etc.)
 *   - table: Which data table within that contract
 *   - query: MongoDB-style query filter
 *
 * Hive Engine uses a smart contract system. Key contracts:
 *   - "tokens": Token definitions, balances, staking
 *   - "market": DEX order book, trade history
 *   - "mining": Token mining pools
 *   - "nft": Non-fungible tokens
 *
 * @param {string} contract - The smart contract name (e.g., "tokens", "market")
 * @param {string} table - The table to query within the contract
 * @param {object} query - MongoDB-style filter object
 * @param {number} limit - Maximum number of results to return
 * @param {number} offset - Number of results to skip (for pagination)
 * @param {object[]} [indexes] - Optional sort indexes
 * @returns {Promise<object[]>} Array of matching records from the sidechain
 */
async function queryHiveEngine(contract, table, query = {}, limit = 1000, offset = 0, indexes = []) {
  // The Hive Engine API endpoint for reading contract state.
  // "contracts" is the method namespace, "find" retrieves multiple records.
  const response = await axios.post(HIVE_ENGINE_API, {
    jsonrpc: '2.0',
    id: 1,
    method: 'find',                    // "find" returns multiple matching records
    params: {
      contract,                        // Which smart contract (tokens, market, etc.)
      table,                           // Which table in that contract
      query,                           // MongoDB-style filter (e.g., {symbol: "BEE"})
      limit,                           // Max results per page
      offset,                          // Skip this many results (pagination)
      indexes                          // Sort order (e.g., [{index: "symbol", descending: false}])
    }
  });

  // The sidechain returns results in the standard JSON-RPC "result" field
  return response.data.result;
}

/**
 * Query a single record from Hive Engine sidechain.
 * Uses "findOne" instead of "find" to return exactly one result or null.
 *
 * @param {string} contract - The smart contract name
 * @param {string} table - The table to query
 * @param {object} query - MongoDB-style filter
 * @returns {Promise<object|null>} Single matching record or null
 */
async function queryHiveEngineOne(contract, table, query = {}) {
  const response = await axios.post(HIVE_ENGINE_API, {
    jsonrpc: '2.0',
    id: 1,
    method: 'findOne',                 // Returns single record instead of array
    params: {
      contract,
      table,
      query
    }
  });

  return response.data.result;
}

// =============================================================================
// Helper: Broadcast Custom JSON to Hive Layer 1
// =============================================================================

/**
 * Broadcasts a Hive Engine operation to the Hive Layer 1 blockchain.
 *
 * THIS IS THE CORE BRIDGE BETWEEN LAYER 1 AND LAYER 2:
 *
 * Every Hive Engine operation (transfer, stake, buy, sell, etc.) is encoded as
 * a JSON payload and broadcast as a "custom_json" operation on Hive Layer 1.
 *
 * The custom_json operation has these fields:
 *   - id: "ssc-mainnet-hive" — this tells Hive Engine nodes to process it
 *   - required_auths: [account] — requires the account's ACTIVE key signature
 *   - required_posting_auths: [] — posting key is NOT sufficient for financial ops
 *   - json: stringified JSON containing the contract call details
 *
 * The JSON payload structure:
 *   {
 *     "contractName": "tokens",        // Which sidechain contract to call
 *     "contractAction": "transfer",    // Which function on that contract
 *     "contractPayload": { ... }       // Arguments to the function
 *   }
 *
 * After broadcast, Hive Engine sidechain nodes:
 *   1. See the custom_json in a new Hive block (3 second block time)
 *   2. Verify the JSON payload is valid
 *   3. Execute the contract action on their local sidechain database
 *   4. The sidechain state update is deterministic — all nodes reach consensus
 *
 * WHY ACTIVE KEY (not posting key):
 *   Hive's key hierarchy separates concerns:
 *   - Posting key: social actions (posts, votes) — low risk if compromised
 *   - Active key: financial actions (transfers, market orders) — high value
 *   - Owner key: account recovery — highest security
 *   Token operations move value, so they require "required_auths" (active key).
 *
 * @param {string} contractName - Sidechain contract (e.g., "tokens", "market")
 * @param {string} contractAction - Action to perform (e.g., "transfer", "stake")
 * @param {object} contractPayload - Arguments for the action
 * @param {string} account - Hive account broadcasting the operation
 * @param {string} activeKey - The account's active private key for signing
 * @returns {Promise<object>} Transaction result from the Hive blockchain
 */
async function broadcastHiveEngineOp(contractName, contractAction, contractPayload, account, activeKey) {
  // Construct the Hive Engine JSON payload.
  // This follows the Hive Engine smart contract calling convention.
  const json = JSON.stringify({
    contractName,      // e.g., "tokens" — the smart contract on Hive Engine
    contractAction,    // e.g., "transfer" — the function to call
    contractPayload    // e.g., {symbol: "BEE", to: "alice", quantity: "10", memo: ""}
  });

  // Create a dhive PrivateKey object from the raw private key string.
  // dhive uses this for cryptographic signing of the transaction.
  const key = dhive.PrivateKey.fromString(activeKey);

  // Broadcast the custom_json operation to the Hive Layer 1 blockchain.
  // hiveClient.broadcast.json() constructs and signs a custom_json operation:
  //
  //   {
  //     "type": "custom_json",
  //     "required_auths": ["youraccount"],     // Active key authorization
  //     "required_posting_auths": [],           // Empty — not a social op
  //     "id": "ssc-mainnet-hive",               // Hive Engine's listener ID
  //     "json": "{\"contractName\":\"tokens\",...}"  // The operation payload
  //   }
  //
  // This gets included in the next Hive block (~3 seconds), and Hive Engine
  // sidechain nodes will process it within seconds after that.
  const result = await hiveClient.broadcast.json(
    {
      required_auths: [account],           // Active key auth — required for financial ops
      required_posting_auths: [],          // Empty — we're using active, not posting
      id: 'ssc-mainnet-hive',             // THE critical identifier — Hive Engine watches for this
      json                                 // Stringified contract call payload
    },
    key                                    // Sign with the active private key
  );

  return result;
}

// =============================================================================
// Input Validation Helpers
// =============================================================================

/**
 * Validates a Hive account name.
 *
 * Hive account names follow strict rules:
 *   - 3 to 16 characters long
 *   - Lowercase letters, digits, hyphens, and dots only
 *   - Must start with a letter
 *   - Cannot have consecutive dots or hyphens
 *
 * @param {string} account - Account name to validate
 * @returns {string|null} Error message if invalid, null if valid
 */
function validateAccount(account) {
  if (!account || typeof account !== 'string') {
    return 'Account name is required';
  }
  // Hive account names: 3-16 chars, lowercase alphanumeric + hyphens/dots
  if (!/^[a-z][a-z0-9\-.]{2,15}$/.test(account)) {
    return 'Invalid Hive account name. Must be 3-16 lowercase characters, starting with a letter.';
  }
  return null;
}

/**
 * Validates a Hive Engine token symbol.
 *
 * Token symbols on Hive Engine:
 *   - 1 to 10 characters
 *   - Uppercase letters and optionally digits
 *   - Examples: BEE, DEC, SPS, SWAP.HIVE, LEO
 *
 * Note: Some tokens use dots (e.g., SWAP.HIVE), which represents wrapped
 * versions of other assets bridged into Hive Engine.
 *
 * @param {string} symbol - Token symbol to validate
 * @returns {string|null} Error message if invalid, null if valid
 */
function validateSymbol(symbol) {
  if (!symbol || typeof symbol !== 'string') {
    return 'Token symbol is required';
  }
  // Hive Engine symbols: uppercase letters, digits, and dots (for wrapped tokens)
  if (!/^[A-Z][A-Z0-9.]{0,9}$/.test(symbol)) {
    return 'Invalid token symbol. Must be 1-10 uppercase characters (letters, digits, dots).';
  }
  return null;
}

/**
 * Validates a token quantity string.
 *
 * Hive Engine quantities are strings (not numbers) to avoid floating-point issues.
 * The blockchain requires exact string representation of amounts.
 *
 * @param {string} quantity - Quantity string like "10.000" or "0.5"
 * @returns {string|null} Error message if invalid, null if valid
 */
function validateQuantity(quantity) {
  if (!quantity || typeof quantity !== 'string') {
    return 'Quantity is required and must be a string (e.g., "10.000")';
  }
  // Must be a positive decimal number
  if (!/^\d+(\.\d+)?$/.test(quantity) || parseFloat(quantity) <= 0) {
    return 'Quantity must be a positive number string (e.g., "10.000")';
  }
  return null;
}

/**
 * Validates a price string for market orders.
 *
 * Prices on the Hive Engine DEX are denominated in SWAP.HIVE (the wrapped
 * version of HIVE on Layer 2). All prices are strings to maintain precision.
 *
 * @param {string} price - Price string like "0.001" or "1.50"
 * @returns {string|null} Error message if invalid, null if valid
 */
function validatePrice(price) {
  if (!price || typeof price !== 'string') {
    return 'Price is required and must be a string (e.g., "0.001")';
  }
  if (!/^\d+(\.\d+)?$/.test(price) || parseFloat(price) <= 0) {
    return 'Price must be a positive number string (e.g., "0.001")';
  }
  return null;
}

// =============================================================================
// Route: GET /api/tokens — List All Hive Engine Tokens
// =============================================================================

/**
 * Lists all tokens registered on the Hive Engine sidechain.
 *
 * This queries the "tokens" contract's "tokens" table on Hive Engine.
 * Each token record includes:
 *   - symbol: The ticker (e.g., "BEE", "DEC", "SPS")
 *   - name: Human-readable name
 *   - issuer: The Hive account that created the token
 *   - supply: Current circulating supply
 *   - maxSupply: Maximum possible supply (set at creation, immutable)
 *   - precision: Decimal places (e.g., 8 means 0.00000001 is the smallest unit)
 *   - stakingEnabled: Whether tokens can be staked for governance/rewards
 *   - delegationEnabled: Whether staked tokens can be delegated to others
 *
 * There are thousands of tokens on Hive Engine, so we paginate with limit/offset.
 *
 * Query params:
 *   ?limit=100    Number of tokens per page (default 100, max 1000)
 *   ?offset=0     Skip this many tokens (for pagination)
 */
app.get('/api/tokens', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 1000);
    const offset = parseInt(req.query.offset) || 0;

    // Query the "tokens" contract, "tokens" table on the Hive Engine sidechain.
    // Empty query {} returns all tokens. Results are paginated.
    const tokens = await queryHiveEngine(
      'tokens',       // Contract: the token management smart contract
      'tokens',       // Table: the registry of all token definitions
      {},             // Query: empty = all tokens
      limit,          // Pagination: max results
      offset,         // Pagination: skip count
      [{ index: 'symbol', descending: false }]  // Sort alphabetically by symbol
    );

    res.json({
      success: true,
      count: tokens.length,
      offset,
      limit,
      // Note: Hive Engine doesn't provide a total count in paginated queries,
      // so the client should keep requesting until count < limit.
      data: tokens
    });
  } catch (error) {
    console.error('Error fetching tokens:', error.message);
    res.status(500).json({ success: false, error: 'Failed to fetch tokens from Hive Engine sidechain' });
  }
});

// =============================================================================
// Route: GET /api/token/:symbol — Get Single Token Details
// =============================================================================

/**
 * Retrieves detailed information about a specific Hive Engine token.
 *
 * Returns the full token record including:
 *   - symbol, name, issuer, supply, maxSupply, precision
 *   - stakingEnabled: Can holders stake this token?
 *   - unstakingCooldown: Days before unstaked tokens become liquid (if staking enabled)
 *   - numberTransactions: Total number of transactions involving this token
 *   - totalStaked: Amount of this token currently staked across all accounts
 *   - delegationEnabled: Can staked tokens be delegated?
 *
 * STAKING MECHANICS:
 *   When you stake tokens, they become "locked" in exchange for governance power
 *   or reward eligibility. Staked tokens cannot be transferred or sold.
 *   To get them back, you must "unstake", which triggers a cooldown period
 *   (set by the token creator, often 7-28 days) before they become liquid again.
 *   This prevents dump-and-run attacks on token governance.
 */
app.get('/api/token/:symbol', async (req, res) => {
  try {
    const symbol = req.params.symbol.toUpperCase();
    const symbolError = validateSymbol(symbol);
    if (symbolError) return res.status(400).json({ success: false, error: symbolError });

    // Query for a specific token by its symbol.
    // findOne returns null if the token doesn't exist.
    const token = await queryHiveEngineOne(
      'tokens',       // Contract: token management
      'tokens',       // Table: token definitions
      { symbol }      // Query: exact match on symbol
    );

    if (!token) {
      return res.status(404).json({
        success: false,
        error: `Token ${symbol} not found on Hive Engine`
      });
    }

    res.json({ success: true, data: token });
  } catch (error) {
    console.error('Error fetching token:', error.message);
    res.status(500).json({ success: false, error: 'Failed to fetch token details' });
  }
});

// =============================================================================
// Route: GET /api/balance/:account — Get All Token Balances for an Account
// =============================================================================

/**
 * Retrieves all Hive Engine token balances for a given account.
 *
 * IMPORTANT DISTINCTION:
 *   - This returns Layer 2 (Hive Engine) token balances only.
 *   - Layer 1 balances (HIVE, HBD, VESTS) are NOT included here.
 *   - To get L1 balances, you'd query hiveClient.database.getAccounts().
 *
 * Each balance record includes:
 *   - account: The Hive account name
 *   - symbol: Token symbol (e.g., "BEE")
 *   - balance: Liquid (transferable) balance as a string
 *   - stake: Amount of this token currently staked (locked for governance/rewards)
 *   - pendingUnstake: Amount currently in the unstaking cooldown period
 *   - delegationsIn: Stake delegated TO this account by others
 *   - delegationsOut: Stake this account has delegated to others
 *   - pendingUndelegations: Delegations being withdrawn (also has a cooldown)
 *
 * A user's "effective stake" (for governance) = stake + delegationsIn - delegationsOut
 */
app.get('/api/balance/:account', async (req, res) => {
  try {
    const account = req.params.account.toLowerCase();
    const accountError = validateAccount(account);
    if (accountError) return res.status(400).json({ success: false, error: accountError });

    // Query the "tokens" contract's "balances" table for all tokens held by this account.
    // Each row represents one token the account has interacted with.
    const balances = await queryHiveEngine(
      'tokens',        // Contract: token management
      'balances',      // Table: per-account, per-token balance records
      { account },     // Query: all tokens for this specific account
      1000,            // Limit: most accounts hold fewer than 1000 different tokens
      0                // Offset: start from the beginning
    );

    res.json({
      success: true,
      account,
      count: balances.length,
      data: balances
    });
  } catch (error) {
    console.error('Error fetching balances:', error.message);
    res.status(500).json({ success: false, error: 'Failed to fetch token balances' });
  }
});

// =============================================================================
// Route: GET /api/balance/:account/:symbol — Get Specific Token Balance
// =============================================================================

/**
 * Retrieves the balance of a specific token for a given account.
 *
 * This is more efficient than fetching all balances when you only need one token.
 * Returns null fields if the account has never held this token.
 */
app.get('/api/balance/:account/:symbol', async (req, res) => {
  try {
    const account = req.params.account.toLowerCase();
    const symbol = req.params.symbol.toUpperCase();

    const accountError = validateAccount(account);
    if (accountError) return res.status(400).json({ success: false, error: accountError });
    const symbolError = validateSymbol(symbol);
    if (symbolError) return res.status(400).json({ success: false, error: symbolError });

    // Query for the specific account + symbol combination.
    // Returns null if this account has never held this token.
    const balance = await queryHiveEngineOne(
      'tokens',                // Contract: token management
      'balances',              // Table: balance records
      { account, symbol }      // Query: exact match on both fields
    );

    if (!balance) {
      // Account has no record for this token — return zero balances
      return res.json({
        success: true,
        data: {
          account,
          symbol,
          balance: '0',
          stake: '0',
          pendingUnstake: '0',
          delegationsIn: '0',
          delegationsOut: '0'
        }
      });
    }

    res.json({ success: true, data: balance });
  } catch (error) {
    console.error('Error fetching balance:', error.message);
    res.status(500).json({ success: false, error: 'Failed to fetch token balance' });
  }
});

// =============================================================================
// Route: POST /api/transfer — Transfer Tokens
// =============================================================================

/**
 * Transfers Hive Engine tokens from the configured account to another.
 *
 * HOW THIS WORKS (THE L1/L2 BRIDGE IN ACTION):
 *
 *   1. Client sends: { symbol: "BEE", to: "alice", quantity: "10.000", memo: "hi" }
 *   2. We construct a Hive Engine JSON payload:
 *      {
 *        contractName: "tokens",
 *        contractAction: "transfer",
 *        contractPayload: { symbol: "BEE", to: "alice", quantity: "10.000", memo: "hi" }
 *      }
 *   3. This payload is stringified and broadcast as a custom_json operation
 *      on Hive Layer 1, signed with the sender's active key.
 *   4. Hive Engine sidechain nodes see the custom_json in the next L1 block.
 *   5. They validate: Does the sender have enough BEE? Is the quantity valid?
 *   6. If valid, they debit sender and credit receiver on the sidechain.
 *   7. The transfer is now complete — queryable via the balances API.
 *
 * Expected request body:
 *   {
 *     "symbol": "BEE",              // Token to transfer
 *     "to": "recipient_account",     // Destination Hive account
 *     "quantity": "10.000",          // Amount as string (respects token precision)
 *     "memo": "optional message"     // Memo visible on-chain (optional)
 *   }
 */
app.post('/api/transfer', async (req, res) => {
  try {
    const { symbol, to, quantity, memo } = req.body;

    // Validate all required fields
    const symbolError = validateSymbol(symbol);
    if (symbolError) return res.status(400).json({ success: false, error: symbolError });

    const toError = validateAccount(to);
    if (toError) return res.status(400).json({ success: false, error: `Invalid recipient: ${toError}` });

    const qtyError = validateQuantity(quantity);
    if (qtyError) return res.status(400).json({ success: false, error: qtyError });

    // Ensure environment is configured with keys
    if (!HIVE_ACCOUNT || !HIVE_ACTIVE_KEY) {
      return res.status(500).json({
        success: false,
        error: 'Server not configured: HIVE_ACCOUNT and HIVE_ACTIVE_KEY required in .env'
      });
    }

    // Broadcast the transfer as a custom_json operation to Hive Layer 1.
    // The "tokens" contract's "transfer" action moves tokens between accounts.
    const result = await broadcastHiveEngineOp(
      'tokens',          // contractName: the token management contract
      'transfer',        // contractAction: the transfer function
      {
        symbol: symbol.toUpperCase(),
        to: to.toLowerCase(),
        quantity,          // Must be a string matching the token's precision
        memo: memo || ''   // Memo is optional but always included (empty string if not provided)
      },
      HIVE_ACCOUNT,
      HIVE_ACTIVE_KEY
    );

    // The result contains the Layer 1 transaction ID.
    // Note: This confirms the custom_json was included in a Hive block,
    // but the sidechain execution is asynchronous (usually within seconds).
    // To confirm the transfer succeeded on L2, you'd need to check balances
    // or query the sidechain transaction history after a few seconds.
    res.json({
      success: true,
      message: `Transfer of ${quantity} ${symbol} to ${to} broadcast to Hive Layer 1`,
      transaction_id: result.id,
      block_num: result.block_num,
      // Remind the caller that L2 execution is async
      note: 'Transaction broadcast to Layer 1. Sidechain will process within ~3-6 seconds.'
    });
  } catch (error) {
    console.error('Transfer error:', error.message);
    res.status(500).json({
      success: false,
      error: `Transfer failed: ${error.message}`
    });
  }
});

// =============================================================================
// Route: POST /api/stake — Stake Tokens
// =============================================================================

/**
 * Stakes Hive Engine tokens for governance power and/or reward eligibility.
 *
 * STAKING MECHANICS:
 *   - Staking locks your tokens, removing them from your liquid balance.
 *   - Staked tokens cannot be transferred, sold, or traded.
 *   - In return, you get governance power (voting weight) and/or reward eligibility.
 *   - Many Hive Engine communities use staking to determine reward distribution.
 *
 *   Example: Staking LEO tokens in the LeoFinance community gives you:
 *     1. Curation rewards (earn LEO by upvoting content)
 *     2. Governance votes (influence community decisions)
 *     3. Higher visibility in the community
 *
 * You can stake to your own account or to another account (as a gift/delegation).
 * Staking is instant. Unstaking requires a cooldown period.
 *
 * Expected request body:
 *   {
 *     "symbol": "BEE",              // Token to stake (must have staking enabled)
 *     "to": "target_account",        // Account to stake to (usually yourself)
 *     "quantity": "100.000"           // Amount to stake
 *   }
 */
app.post('/api/stake', async (req, res) => {
  try {
    const { symbol, to, quantity } = req.body;

    const symbolError = validateSymbol(symbol);
    if (symbolError) return res.status(400).json({ success: false, error: symbolError });

    // "to" defaults to the sender's own account if not specified
    const stakeTarget = to ? to.toLowerCase() : HIVE_ACCOUNT;
    const toError = validateAccount(stakeTarget);
    if (toError) return res.status(400).json({ success: false, error: `Invalid target: ${toError}` });

    const qtyError = validateQuantity(quantity);
    if (qtyError) return res.status(400).json({ success: false, error: qtyError });

    if (!HIVE_ACCOUNT || !HIVE_ACTIVE_KEY) {
      return res.status(500).json({
        success: false,
        error: 'Server not configured: HIVE_ACCOUNT and HIVE_ACTIVE_KEY required'
      });
    }

    // Broadcast the stake operation to Hive Layer 1.
    // The "tokens" contract's "stake" action locks tokens and updates the stake balance.
    const result = await broadcastHiveEngineOp(
      'tokens',          // contractName: token management contract
      'stake',           // contractAction: stake function — locks tokens
      {
        to: stakeTarget, // Account receiving the staked tokens (usually self)
        symbol: symbol.toUpperCase(),
        quantity           // Amount to move from liquid balance to staked balance
      },
      HIVE_ACCOUNT,
      HIVE_ACTIVE_KEY
    );

    res.json({
      success: true,
      message: `Staked ${quantity} ${symbol} to ${stakeTarget}`,
      transaction_id: result.id,
      block_num: result.block_num,
      note: 'Staking is instant. Tokens moved from liquid to staked balance.'
    });
  } catch (error) {
    console.error('Stake error:', error.message);
    res.status(500).json({
      success: false,
      error: `Stake failed: ${error.message}`
    });
  }
});

// =============================================================================
// Route: POST /api/unstake — Begin Unstaking (Cooldown Period)
// =============================================================================

/**
 * Begins the unstaking process for Hive Engine tokens.
 *
 * UNSTAKING COOLDOWN:
 *   Unlike staking (which is instant), unstaking has a COOLDOWN period.
 *   This is a security/governance feature that prevents "vote-and-dump" attacks:
 *
 *   1. You call unstake for X tokens.
 *   2. The tokens enter "pendingUnstake" status — they are still locked.
 *   3. After the cooldown period (set by the token creator, e.g., 7 days), the
 *      tokens automatically move back to your liquid balance.
 *   4. During cooldown, the tokens do NOT earn rewards or provide governance power.
 *
 *   The cooldown period varies by token:
 *     - BEE: 3 days (short, since it's the platform utility token)
 *     - LEO: 28 days (long, to encourage commitment)
 *     - Each token's unstakingCooldown is set at creation time.
 *
 * Expected request body:
 *   {
 *     "symbol": "BEE",              // Token to unstake
 *     "quantity": "50.000"           // Amount to begin unstaking
 *   }
 */
app.post('/api/unstake', async (req, res) => {
  try {
    const { symbol, quantity } = req.body;

    const symbolError = validateSymbol(symbol);
    if (symbolError) return res.status(400).json({ success: false, error: symbolError });

    const qtyError = validateQuantity(quantity);
    if (qtyError) return res.status(400).json({ success: false, error: qtyError });

    if (!HIVE_ACCOUNT || !HIVE_ACTIVE_KEY) {
      return res.status(500).json({
        success: false,
        error: 'Server not configured: HIVE_ACCOUNT and HIVE_ACTIVE_KEY required'
      });
    }

    // Broadcast the unstake operation to Hive Layer 1.
    // The "tokens" contract's "unstake" action initiates the cooldown period.
    // Tokens move from "stake" to "pendingUnstake" immediately.
    // After the cooldown, they automatically become liquid again.
    const result = await broadcastHiveEngineOp(
      'tokens',          // contractName: token management contract
      'unstake',         // contractAction: begin unstaking cooldown
      {
        symbol: symbol.toUpperCase(),
        quantity           // Amount to begin unstaking
      },
      HIVE_ACCOUNT,
      HIVE_ACTIVE_KEY
    );

    res.json({
      success: true,
      message: `Unstaking ${quantity} ${symbol} — cooldown period has begun`,
      transaction_id: result.id,
      block_num: result.block_num,
      note: 'Tokens are now in pendingUnstake. They will become liquid after the cooldown period.'
    });
  } catch (error) {
    console.error('Unstake error:', error.message);
    res.status(500).json({
      success: false,
      error: `Unstake failed: ${error.message}`
    });
  }
});

// =============================================================================
// Route: GET /api/market/:symbol — Get Order Book
// =============================================================================

/**
 * Retrieves the DEX order book for a Hive Engine token.
 *
 * HIVE ENGINE DEX (Decentralized Exchange):
 *   Hive Engine has a built-in order-book DEX where tokens trade against SWAP.HIVE.
 *
 *   SWAP.HIVE is the wrapped version of HIVE on Layer 2:
 *     - You deposit HIVE (Layer 1) into the @honey-swap gateway account.
 *     - You receive SWAP.HIVE (Layer 2) at a 1:1 ratio.
 *     - SWAP.HIVE is the base trading pair for ALL tokens on the DEX.
 *
 *   Order Book:
 *     - Buy orders (bids): People willing to buy the token with SWAP.HIVE
 *     - Sell orders (asks): People willing to sell the token for SWAP.HIVE
 *     - Orders are sorted by price (best prices first)
 *     - When a buy price meets a sell price, the trade executes automatically
 *
 *   This is a LIMIT ORDER book (not AMM). You specify the exact price and quantity.
 *
 * Query params:
 *   ?limit=50    Number of orders per side (default 50)
 */
app.get('/api/market/:symbol', async (req, res) => {
  try {
    const symbol = req.params.symbol.toUpperCase();
    const symbolError = validateSymbol(symbol);
    if (symbolError) return res.status(400).json({ success: false, error: symbolError });

    const limit = Math.min(parseInt(req.query.limit) || 50, 500);

    // Fetch buy orders (bids) from the "market" contract's "buyBook" table.
    // Buy orders are sorted by price descending (highest bid first).
    const buyOrders = await queryHiveEngine(
      'market',          // Contract: the DEX smart contract
      'buyBook',         // Table: open buy orders
      { symbol },        // Query: orders for this specific token
      limit,
      0,
      [{ index: 'priceDec', descending: true }]  // Sort: highest price first (best bids)
    );

    // Fetch sell orders (asks) from the "market" contract's "sellBook" table.
    // Sell orders are sorted by price ascending (lowest ask first).
    const sellOrders = await queryHiveEngine(
      'market',          // Contract: the DEX smart contract
      'sellBook',        // Table: open sell orders
      { symbol },        // Query: orders for this specific token
      limit,
      0,
      [{ index: 'priceDec', descending: false }]  // Sort: lowest price first (best asks)
    );

    // Calculate spread: the gap between the highest bid and lowest ask.
    // A tight spread indicates a liquid market; a wide spread indicates thin liquidity.
    const highestBid = buyOrders.length > 0 ? parseFloat(buyOrders[0].price) : 0;
    const lowestAsk = sellOrders.length > 0 ? parseFloat(sellOrders[0].price) : 0;
    const spread = lowestAsk > 0 && highestBid > 0 ? lowestAsk - highestBid : null;

    res.json({
      success: true,
      symbol,
      market_pair: `${symbol}/SWAP.HIVE`,         // All tokens trade against SWAP.HIVE
      highest_bid: highestBid || null,              // Best buy price
      lowest_ask: lowestAsk || null,                // Best sell price
      spread: spread !== null ? spread.toFixed(8) : null,  // Price gap
      buy_orders: buyOrders,                        // Full bid side of the order book
      sell_orders: sellOrders                       // Full ask side of the order book
    });
  } catch (error) {
    console.error('Market error:', error.message);
    res.status(500).json({ success: false, error: 'Failed to fetch market data' });
  }
});

// =============================================================================
// Route: POST /api/market/buy — Place Buy Order on DEX
// =============================================================================

/**
 * Places a LIMIT BUY order on the Hive Engine DEX.
 *
 * HOW DEX ORDERS WORK:
 *   1. You specify: I want to buy X tokens at Y price (SWAP.HIVE per token).
 *   2. The total cost is X * Y in SWAP.HIVE, deducted from your SWAP.HIVE balance.
 *   3. If there are sell orders at or below your price, they match instantly (fill).
 *   4. Any unfilled portion sits in the buy order book until filled or cancelled.
 *   5. There is NO expiration — orders remain until filled or manually cancelled.
 *
 *   Example: Buy 100 BEE at 0.01 SWAP.HIVE each = costs 1.0 SWAP.HIVE total
 *
 * IMPORTANT: You need SWAP.HIVE balance (not regular HIVE) to place buy orders.
 *   To get SWAP.HIVE: deposit HIVE via https://tribaldex.com/wallet/
 *
 * Expected request body:
 *   {
 *     "symbol": "BEE",              // Token to buy
 *     "quantity": "100.000",         // Number of tokens to buy
 *     "price": "0.01000000"          // Price per token in SWAP.HIVE (8 decimal places)
 *   }
 */
app.post('/api/market/buy', async (req, res) => {
  try {
    const { symbol, quantity, price } = req.body;

    const symbolError = validateSymbol(symbol);
    if (symbolError) return res.status(400).json({ success: false, error: symbolError });

    const qtyError = validateQuantity(quantity);
    if (qtyError) return res.status(400).json({ success: false, error: qtyError });

    const priceError = validatePrice(price);
    if (priceError) return res.status(400).json({ success: false, error: priceError });

    if (!HIVE_ACCOUNT || !HIVE_ACTIVE_KEY) {
      return res.status(500).json({
        success: false,
        error: 'Server not configured: HIVE_ACCOUNT and HIVE_ACTIVE_KEY required'
      });
    }

    // Broadcast the buy order to Hive Layer 1.
    // The "market" contract's "buy" action places a limit buy order on the DEX.
    // If matching sell orders exist at or below this price, they fill immediately.
    const result = await broadcastHiveEngineOp(
      'market',          // contractName: the DEX smart contract
      'buy',             // contractAction: place a buy order
      {
        symbol: symbol.toUpperCase(),
        quantity,          // Number of tokens to buy
        price              // Price per token in SWAP.HIVE
      },
      HIVE_ACCOUNT,
      HIVE_ACTIVE_KEY
    );

    // Calculate the total cost for the user's reference
    const totalCost = (parseFloat(quantity) * parseFloat(price)).toFixed(8);

    res.json({
      success: true,
      message: `Buy order placed: ${quantity} ${symbol} at ${price} SWAP.HIVE each`,
      total_cost: `${totalCost} SWAP.HIVE`,
      transaction_id: result.id,
      block_num: result.block_num,
      note: 'Order may fill immediately if matching sell orders exist at this price or lower.'
    });
  } catch (error) {
    console.error('Buy order error:', error.message);
    res.status(500).json({
      success: false,
      error: `Buy order failed: ${error.message}`
    });
  }
});

// =============================================================================
// Route: POST /api/market/sell — Place Sell Order on DEX
// =============================================================================

/**
 * Places a LIMIT SELL order on the Hive Engine DEX.
 *
 * HOW SELL ORDERS WORK:
 *   1. You specify: I want to sell X tokens at Y price (SWAP.HIVE per token).
 *   2. X tokens are deducted from your liquid balance and held in escrow.
 *   3. If there are buy orders at or above your price, they match instantly (fill).
 *   4. Any unfilled portion sits in the sell order book until filled or cancelled.
 *   5. When filled, you receive SWAP.HIVE at the order price.
 *
 *   Example: Sell 100 BEE at 0.012 SWAP.HIVE each = receive 1.2 SWAP.HIVE total
 *
 * IMPORTANT: You need liquid (unstaked) tokens to sell. Staked tokens cannot be sold.
 *
 * Expected request body:
 *   {
 *     "symbol": "BEE",              // Token to sell
 *     "quantity": "100.000",         // Number of tokens to sell
 *     "price": "0.01200000"          // Price per token in SWAP.HIVE
 *   }
 */
app.post('/api/market/sell', async (req, res) => {
  try {
    const { symbol, quantity, price } = req.body;

    const symbolError = validateSymbol(symbol);
    if (symbolError) return res.status(400).json({ success: false, error: symbolError });

    const qtyError = validateQuantity(quantity);
    if (qtyError) return res.status(400).json({ success: false, error: qtyError });

    const priceError = validatePrice(price);
    if (priceError) return res.status(400).json({ success: false, error: priceError });

    if (!HIVE_ACCOUNT || !HIVE_ACTIVE_KEY) {
      return res.status(500).json({
        success: false,
        error: 'Server not configured: HIVE_ACCOUNT and HIVE_ACTIVE_KEY required'
      });
    }

    // Broadcast the sell order to Hive Layer 1.
    // The "market" contract's "sell" action places a limit sell order on the DEX.
    // If matching buy orders exist at or above this price, they fill immediately.
    const result = await broadcastHiveEngineOp(
      'market',          // contractName: the DEX smart contract
      'sell',            // contractAction: place a sell order
      {
        symbol: symbol.toUpperCase(),
        quantity,          // Number of tokens to sell
        price              // Price per token in SWAP.HIVE
      },
      HIVE_ACCOUNT,
      HIVE_ACTIVE_KEY
    );

    // Calculate total proceeds for the user's reference
    const totalProceeds = (parseFloat(quantity) * parseFloat(price)).toFixed(8);

    res.json({
      success: true,
      message: `Sell order placed: ${quantity} ${symbol} at ${price} SWAP.HIVE each`,
      total_proceeds: `${totalProceeds} SWAP.HIVE (if fully filled)`,
      transaction_id: result.id,
      block_num: result.block_num,
      note: 'Order may fill immediately if matching buy orders exist at this price or higher.'
    });
  } catch (error) {
    console.error('Sell order error:', error.message);
    res.status(500).json({
      success: false,
      error: `Sell order failed: ${error.message}`
    });
  }
});

// =============================================================================
// Route: GET /api/history/:account/:symbol — Transaction History
// =============================================================================

/**
 * Retrieves transaction history for a specific account and token on Hive Engine.
 *
 * HOW HISTORY WORKS ON HIVE ENGINE:
 *   The Hive Engine sidechain maintains a transaction history table that records
 *   every operation affecting token balances: transfers, stakes, unstakes, market
 *   fills, rewards, etc. Each record has:
 *     - from / to: sender and receiver accounts
 *     - symbol: the token involved
 *     - quantity: the amount transferred
 *     - memo: optional message
 *     - timestamp: Unix timestamp of when the sidechain processed it
 *     - operation: the type of action (e.g., "tokens_transfer")
 *
 *   Note: This history is maintained by the SIDECHAIN, not Layer 1.
 *   The Layer 1 blockchain has the raw custom_json operations, but the sidechain
 *   provides a more structured, indexed history that's easier to query.
 *
 * Query params:
 *   ?limit=50    Number of transactions (default 50, max 500)
 *   ?offset=0    Pagination offset
 */
app.get('/api/history/:account/:symbol', async (req, res) => {
  try {
    const account = req.params.account.toLowerCase();
    const symbol = req.params.symbol.toUpperCase();

    const accountError = validateAccount(account);
    if (accountError) return res.status(400).json({ success: false, error: accountError });
    const symbolError = validateSymbol(symbol);
    if (symbolError) return res.status(400).json({ success: false, error: symbolError });

    const limit = Math.min(parseInt(req.query.limit) || 50, 500);
    const offset = parseInt(req.query.offset) || 0;

    // Hive Engine's account history endpoint uses a different API path.
    // We query it via the /accountHistory endpoint with specific parameters.
    const response = await axios.get(
      `${HIVE_ENGINE_API.replace('/rpc', '')}/accountHistory`,
      {
        params: {
          account,
          symbol,
          limit,
          offset
        }
      }
    );

    const history = response.data || [];

    res.json({
      success: true,
      account,
      symbol,
      count: history.length,
      offset,
      limit,
      data: history
    });
  } catch (error) {
    console.error('History error:', error.message);

    // Fallback: Query the sidechain's transferHistory table directly.
    // Some Hive Engine API nodes may not support the accountHistory endpoint,
    // so we try the JSON-RPC approach as a fallback.
    try {
      const limit = Math.min(parseInt(req.query.limit) || 50, 500);
      const offset = parseInt(req.query.offset) || 0;
      const account = req.params.account.toLowerCase();
      const symbol = req.params.symbol.toUpperCase();

      // Query transfers where this account is either the sender or receiver.
      // We query sent and received transactions separately and merge them.
      const [sent, received] = await Promise.all([
        queryHiveEngine(
          'tokens',               // Contract: token management
          'transferHistory',      // Table: record of all transfers
          { from: account, symbol },  // Transfers sent by this account
          limit,
          offset
        ),
        queryHiveEngine(
          'tokens',               // Contract: token management
          'transferHistory',      // Table: record of all transfers
          { to: account, symbol },    // Transfers received by this account
          limit,
          offset
        )
      ]);

      // Merge, deduplicate by _id, and sort by timestamp descending (newest first)
      const merged = [...sent, ...received];
      const seen = new Set();
      const unique = merged.filter(tx => {
        const key = tx._id || JSON.stringify(tx);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      unique.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));

      res.json({
        success: true,
        account,
        symbol,
        count: unique.length,
        data: unique.slice(0, limit),
        note: 'Fallback to transferHistory query. May not include staking/market transactions.'
      });
    } catch (fallbackError) {
      res.status(500).json({
        success: false,
        error: 'Failed to fetch transaction history from Hive Engine sidechain'
      });
    }
  }
});

// =============================================================================
// Route: GET / — API Info (Root)
// =============================================================================

/**
 * Returns API documentation at the root endpoint.
 */
app.get('/', (req, res) => {
  res.json({
    name: 'Hive Engine Token Operations API',
    version: '1.0.0',
    description: 'REST API for Hive Engine Layer 2 token operations',
    architecture: {
      layer1: 'Hive blockchain — immutable ledger, transaction transport via custom_json',
      layer2: 'Hive Engine sidechain — token state, DEX, staking, smart contracts',
      bridge: 'custom_json operations with id="ssc-mainnet-hive" on Layer 1'
    },
    endpoints: {
      'GET /api/tokens': 'List all Hive Engine tokens (paginated)',
      'GET /api/token/:symbol': 'Get details for a specific token',
      'GET /api/balance/:account': 'Get all token balances for an account',
      'GET /api/balance/:account/:symbol': 'Get specific token balance',
      'POST /api/transfer': 'Transfer tokens (requires active key)',
      'POST /api/stake': 'Stake tokens for governance/rewards',
      'POST /api/unstake': 'Begin unstaking (cooldown period)',
      'GET /api/market/:symbol': 'Get DEX order book for a token',
      'POST /api/market/buy': 'Place limit buy order on DEX',
      'POST /api/market/sell': 'Place limit sell order on DEX',
      'GET /api/history/:account/:symbol': 'Transaction history'
    }
  });
});

// =============================================================================
// Start Server
// =============================================================================

app.listen(PORT, () => {
  console.log(`\n=== Hive Engine Token Operations API ===`);
  console.log(`Server running on http://localhost:${PORT}`);
  console.log(`\nConfigured account: ${HIVE_ACCOUNT || '(not set — read-only mode)'}`);
  console.log(`Hive L1 node: ${HIVE_NODE}`);
  console.log(`Hive Engine L2 API: ${HIVE_ENGINE_API}`);
  console.log(`\nEndpoints:`);
  console.log(`  GET  /api/tokens              — List all tokens`);
  console.log(`  GET  /api/token/:symbol        — Token details`);
  console.log(`  GET  /api/balance/:account      — All token balances`);
  console.log(`  GET  /api/balance/:account/:sym — Specific balance`);
  console.log(`  POST /api/transfer              — Transfer tokens`);
  console.log(`  POST /api/stake                 — Stake tokens`);
  console.log(`  POST /api/unstake               — Unstake tokens`);
  console.log(`  GET  /api/market/:symbol        — Order book`);
  console.log(`  POST /api/market/buy            — Buy order`);
  console.log(`  POST /api/market/sell           — Sell order`);
  console.log(`  GET  /api/history/:acct/:sym    — Tx history`);
  console.log(`\n========================================\n`);
});

// Export for testing
module.exports = { app, validateAccount, validateSymbol, validateQuantity, validatePrice };
