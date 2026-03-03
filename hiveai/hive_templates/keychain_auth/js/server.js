/**
 * Hive Keychain Authentication Server
 * ====================================
 *
 * WHY HIVE KEYCHAIN EXISTS
 * -------------------------
 * Hive accounts are controlled by cryptographic key pairs (posting, active, owner, memo).
 * Users should NEVER paste private keys into a website. Hive Keychain is a browser extension
 * (like MetaMask for Ethereum) that stores keys locally and signs transactions on behalf of
 * the user. The dapp never sees the private key — it only receives the resulting signature.
 *
 * THE CHALLENGE-RESPONSE AUTH FLOW
 * ---------------------------------
 * 1. User clicks "Login" and provides their Hive username.
 * 2. Server generates a unique, random challenge string (a nonce).
 * 3. Frontend asks Hive Keychain to sign that challenge with the user's posting key.
 * 4. Keychain prompts the user to approve the signature (user sees what they are signing).
 * 5. Frontend sends (username, challenge, signature) back to the server.
 * 6. Server fetches the user's public posting key from the Hive blockchain.
 * 7. Server verifies the signature was produced by the corresponding private key.
 * 8. If valid, server issues a JWT for session management.
 *
 * This is the standard authentication pattern for Hive dapps. No passwords, no OAuth —
 * just cryptographic proof that the user controls the account.
 *
 * SIGNATURE VERIFICATION
 * -----------------------
 * Hive uses the Graphene signature scheme (shared with BitShares, Steem, etc.):
 *   - Keys are secp256k1 elliptic curve key pairs.
 *   - A signature is 65 bytes: 1 byte recovery id + 32 bytes r + 32 bytes s.
 *   - To verify: recover the public key from (message_hash, signature), then compare
 *     it to the on-chain public key. If they match, the signature is valid.
 *
 * Hive Keychain's requestSignBuffer() signs the raw buffer (the challenge string).
 * The message is SHA-256 hashed before signing. We replicate this on the server side.
 */

require("dotenv").config();
const express = require("express");
const cors = require("cors");
const crypto = require("crypto");
const jwt = require("jsonwebtoken");
const path = require("path");

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const PORT = process.env.PORT || 3000;
const JWT_SECRET = process.env.JWT_SECRET || "change_this_to_a_random_secret";
const HIVE_NODE = process.env.HIVE_NODE || "https://api.hive.blog";

// In-memory store for pending challenges.
// In production, use Redis or a database with TTL expiration.
const pendingChallenges = new Map();

// Challenge expiry time: 5 minutes
const CHALLENGE_TTL_MS = 5 * 60 * 1000;

// ---------------------------------------------------------------------------
// Helpers: Hive blockchain RPC
// ---------------------------------------------------------------------------

/**
 * Call a Hive blockchain API method via JSON-RPC.
 *
 * Hive nodes expose a JSON-RPC 2.0 interface. The condenser_api is the most
 * commonly used API namespace and provides backwards-compatible methods.
 */
async function hiveRpc(method, params) {
  const response = await fetch(HIVE_NODE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      method: method,
      params: params,
      id: 1,
    }),
  });
  const data = await response.json();
  if (data.error) {
    throw new Error(`Hive RPC error: ${JSON.stringify(data.error)}`);
  }
  return data.result;
}

/**
 * Fetch a Hive account's data from the blockchain.
 *
 * Returns the full account object which includes:
 *   - posting.key_auths: array of [public_key, weight] pairs for posting authority
 *   - active.key_auths: same for active authority
 *   - owner.key_auths: same for owner authority
 *   - memo_key: the memo public key
 *   - plus balances, reputation, JSON metadata, etc.
 */
async function getHiveAccount(username) {
  const accounts = await hiveRpc("condenser_api.get_accounts", [[username]]);
  if (!accounts || accounts.length === 0) {
    return null;
  }
  return accounts[0];
}

// ---------------------------------------------------------------------------
// Helpers: Hive signature verification (pure Node.js, no native deps)
// ---------------------------------------------------------------------------

/**
 * HOW HIVE SIGNATURE VERIFICATION WORKS
 * =======================================
 *
 * Hive Keychain's requestSignBuffer() does the following internally:
 *   1. Takes the raw message string (our challenge).
 *   2. Computes SHA-256 hash of the message bytes.
 *   3. Signs the hash with the user's private posting key using secp256k1 ECDSA.
 *   4. Returns the signature as a hex string (65 bytes = 130 hex chars).
 *
 * To verify on the server:
 *   1. Compute the same SHA-256 hash of the challenge string.
 *   2. Recover the public key from the (hash, signature) pair.
 *   3. Encode the recovered public key in Hive's format (STM prefix + base58check).
 *   4. Compare against the user's on-chain posting public key(s).
 *
 * The recovery step is what makes this elegant: we do not need the public key
 * to verify — we DERIVE it from the signature and then check if it matches
 * what the blockchain says the user's key should be.
 *
 * IMPORTANT: Node.js's built-in crypto module supports secp256k1 ECDSA via
 * the 'ec' key type, but it does NOT support public key recovery from signatures.
 * For production use, you need either:
 *   (a) The 'secp256k1' npm package (C binding, fast), or
 *   (b) The 'elliptic' npm package (pure JS), or
 *   (c) The '@noble/secp256k1' package (modern, audited pure JS).
 *
 * Below we implement verification using Node.js crypto's ECDSA verify directly,
 * which requires us to have the public key already (fetched from chain).
 * This is the simpler approach and works perfectly for auth.
 */

// Base58 alphabet used by Bitcoin/Hive (no 0, O, I, l to avoid ambiguity)
const BASE58_ALPHABET =
  "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

/**
 * Decode a base58 string to a Buffer.
 */
function base58Decode(str) {
  let result = 0n;
  for (const char of str) {
    const index = BASE58_ALPHABET.indexOf(char);
    if (index === -1) throw new Error(`Invalid base58 character: ${char}`);
    result = result * 58n + BigInt(index);
  }
  // Convert bigint to byte array
  const hex = result.toString(16).padStart(2, "0");
  // Ensure even length
  const paddedHex = hex.length % 2 === 0 ? hex : "0" + hex;
  const bytes = Buffer.from(paddedHex, "hex");
  // Preserve leading zeros from base58
  let leadingZeros = 0;
  for (const char of str) {
    if (char === "1") leadingZeros++;
    else break;
  }
  return Buffer.concat([Buffer.alloc(leadingZeros), bytes]);
}

/**
 * Parse a Hive public key string (STM... format) into a raw 33-byte compressed
 * public key buffer.
 *
 * Hive public keys look like: STM7abc123...
 * Format: prefix + base58check(compressed_pubkey + checksum)
 * The checksum is RIPEMD160 of the compressed public key (first 4 bytes).
 */
function parseHivePublicKey(pubKeyStr) {
  // Strip the STM prefix (or TST for testnet)
  let keyStr;
  if (pubKeyStr.startsWith("STM")) {
    keyStr = pubKeyStr.slice(3);
  } else if (pubKeyStr.startsWith("TST")) {
    keyStr = pubKeyStr.slice(3);
  } else {
    throw new Error(`Unknown key prefix in: ${pubKeyStr}`);
  }

  const decoded = base58Decode(keyStr);
  // Last 4 bytes are the RIPEMD160 checksum
  const keyBytes = decoded.slice(0, decoded.length - 4);
  const checksum = decoded.slice(decoded.length - 4);

  // Verify checksum: RIPEMD160 of the key bytes, first 4 bytes
  const hash = crypto.createHash("ripemd160").update(keyBytes).digest();
  if (!hash.slice(0, 4).equals(checksum)) {
    throw new Error("Public key checksum mismatch");
  }

  return keyBytes; // 33-byte compressed secp256k1 public key
}

/**
 * Verify a Hive Keychain signature against a challenge message and public key.
 *
 * This uses Node.js built-in crypto ECDSA verification:
 *   1. Hash the challenge with SHA-256 (matching what Keychain does).
 *   2. Parse the 65-byte signature (recovery_id + r + s) into DER format.
 *   3. Use crypto.verify() with the on-chain public key.
 *
 * Returns true if the signature is valid for this public key and message.
 */
function verifyHiveSignature(challenge, signatureHex, hivePublicKey) {
  try {
    // Step 1: SHA-256 hash of the challenge (this is what Keychain signs)
    const messageHash = crypto
      .createHash("sha256")
      .update(challenge, "utf8")
      .digest();

    // Step 2: Parse the 65-byte Hive signature
    // Format: [recovery_id (1 byte)] [r (32 bytes)] [s (32 bytes)]
    const sigBuffer = Buffer.from(signatureHex, "hex");
    if (sigBuffer.length !== 65) {
      console.error(`Signature length ${sigBuffer.length}, expected 65`);
      return false;
    }

    // Skip byte 0 (recovery id, used for key recovery but not needed for verify)
    const r = sigBuffer.slice(1, 33);
    const s = sigBuffer.slice(33, 65);

    // Step 3: Convert r,s to DER encoding (what Node.js crypto expects)
    const derSignature = encodeDER(r, s);

    // Step 4: Parse the Hive public key into raw bytes
    const pubKeyBytes = parseHivePublicKey(hivePublicKey);

    // Step 5: Create a KeyObject from the raw compressed public key
    // Node.js needs the key in SubjectPublicKeyInfo (SPKI) DER format
    const spkiDer = wrapCompressedKeyInSPKI(pubKeyBytes);
    const publicKey = crypto.createPublicKey({
      key: spkiDer,
      format: "der",
      type: "spki",
    });

    // Step 6: Verify the ECDSA signature
    return crypto.verify(null, messageHash, publicKey, derSignature);
  } catch (err) {
    console.error("Signature verification error:", err.message);
    return false;
  }
}

/**
 * Encode r and s values into DER format for ECDSA signature.
 *
 * DER structure:
 *   SEQUENCE {
 *     INTEGER r
 *     INTEGER s
 *   }
 *
 * Integers in DER are signed, so if the high bit is set we must prepend 0x00.
 */
function encodeDER(r, s) {
  // Strip leading zeros but ensure the integer is positive (high bit = 0)
  function derInteger(buf) {
    let i = 0;
    while (i < buf.length - 1 && buf[i] === 0) i++;
    buf = buf.slice(i);
    if (buf[0] & 0x80) {
      buf = Buffer.concat([Buffer.from([0x00]), buf]);
    }
    return Buffer.concat([Buffer.from([0x02, buf.length]), buf]);
  }

  const rDer = derInteger(r);
  const sDer = derInteger(s);
  const body = Buffer.concat([rDer, sDer]);
  return Buffer.concat([Buffer.from([0x30, body.length]), body]);
}

/**
 * Wrap a 33-byte compressed secp256k1 public key in SPKI DER format.
 *
 * SPKI structure:
 *   SEQUENCE {
 *     SEQUENCE {
 *       OID 1.2.840.10045.2.1   (ecPublicKey)
 *       OID 1.3.132.0.10        (secp256k1)
 *     }
 *     BIT STRING <compressed public key>
 *   }
 */
function wrapCompressedKeyInSPKI(compressedKey) {
  // Pre-built header for secp256k1 compressed public key SPKI
  const header = Buffer.from(
    "3036301006072a8648ce3d020106052b8104000a032200",
    "hex"
  );
  return Buffer.concat([header, compressedKey]);
}

// ---------------------------------------------------------------------------
// Routes
// ---------------------------------------------------------------------------

/**
 * GET /
 * Serve the login page.
 */
app.get("/", (req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

/**
 * POST /api/auth/challenge
 *
 * Generate a random challenge for the user to sign with Hive Keychain.
 *
 * The challenge is a unique, random string that:
 *   - Prevents replay attacks (each login attempt gets a fresh challenge)
 *   - Expires after 5 minutes (prevents stale challenge reuse)
 *   - Is tied to the username (prevents challenge reuse across accounts)
 *
 * Request body: { "username": "alice" }
 * Response: { "challenge": "hive-auth:alice:abc123...", "expires_in": 300 }
 */
app.post("/api/auth/challenge", async (req, res) => {
  try {
    const { username } = req.body;
    if (!username || typeof username !== "string") {
      return res.status(400).json({ error: "Username is required" });
    }

    const cleanUsername = username.toLowerCase().trim();

    // Verify the account actually exists on the Hive blockchain
    const account = await getHiveAccount(cleanUsername);
    if (!account) {
      return res.status(404).json({ error: "Hive account not found" });
    }

    // Generate a random challenge string
    // Format: "hive-auth:<username>:<random_hex>:<timestamp>"
    // The prefix makes it clear to the user what they are signing.
    const randomBytes = crypto.randomBytes(32).toString("hex");
    const timestamp = Date.now();
    const challenge = `hive-auth:${cleanUsername}:${randomBytes}:${timestamp}`;

    // Store the challenge with expiry
    pendingChallenges.set(cleanUsername, {
      challenge,
      createdAt: timestamp,
      expiresAt: timestamp + CHALLENGE_TTL_MS,
    });

    // Clean up expired challenges periodically
    for (const [key, value] of pendingChallenges) {
      if (Date.now() > value.expiresAt) {
        pendingChallenges.delete(key);
      }
    }

    res.json({
      challenge,
      expires_in: CHALLENGE_TTL_MS / 1000,
    });
  } catch (err) {
    console.error("Challenge generation error:", err);
    res.status(500).json({ error: "Failed to generate challenge" });
  }
});

/**
 * POST /api/auth/verify
 *
 * Verify the Hive Keychain signature and issue a JWT.
 *
 * This is the core of the auth flow:
 *   1. Look up the pending challenge for this username.
 *   2. Check it has not expired.
 *   3. Fetch the user's posting public key(s) from the Hive blockchain.
 *   4. Verify the signature against each posting key (accounts can have multiple).
 *   5. If valid, delete the challenge (one-time use) and issue a JWT.
 *
 * Request body: { "username": "alice", "challenge": "hive-auth:...", "signature": "20abc..." }
 * Response: { "token": "eyJ...", "username": "alice", "expires_in": 86400 }
 */
app.post("/api/auth/verify", async (req, res) => {
  try {
    const { username, challenge, signature } = req.body;

    if (!username || !challenge || !signature) {
      return res
        .status(400)
        .json({ error: "username, challenge, and signature are required" });
    }

    const cleanUsername = username.toLowerCase().trim();

    // Step 1: Look up the pending challenge
    const pending = pendingChallenges.get(cleanUsername);
    if (!pending) {
      return res
        .status(401)
        .json({ error: "No pending challenge for this user" });
    }

    // Step 2: Verify the challenge matches and has not expired
    if (pending.challenge !== challenge) {
      return res.status(401).json({ error: "Challenge mismatch" });
    }

    if (Date.now() > pending.expiresAt) {
      pendingChallenges.delete(cleanUsername);
      return res
        .status(401)
        .json({ error: "Challenge expired — please request a new one" });
    }

    // Step 3: Fetch the user's public keys from the blockchain
    //
    // A Hive account has multiple authority levels:
    //   - owner: highest authority, can change all other keys
    //   - active: for financial operations (transfers, power ups)
    //   - posting: for social operations (posts, votes, follows)
    //   - memo: for encrypting/decrypting private messages
    //
    // For login/auth, we use the POSTING key because:
    //   - It is the lowest-privilege key (principle of least privilege)
    //   - Users are comfortable approving posting-key signatures
    //   - It proves account ownership without risking funds
    //
    // Each authority level can have multiple keys (multi-sig), so we check all.
    const account = await getHiveAccount(cleanUsername);
    if (!account) {
      return res.status(404).json({ error: "Hive account not found" });
    }

    const postingKeys = account.posting.key_auths.map(([key]) => key);

    if (postingKeys.length === 0) {
      return res
        .status(400)
        .json({ error: "Account has no posting keys configured" });
    }

    // Step 4: Verify the signature against each posting key
    //
    // We try each key because:
    //   - An account might have multiple posting keys (multi-sig setup)
    //   - We need the signature to match at least ONE of them
    let verified = false;
    for (const pubKey of postingKeys) {
      if (verifyHiveSignature(challenge, signature, pubKey)) {
        verified = true;
        break;
      }
    }

    if (!verified) {
      return res.status(401).json({ error: "Invalid signature" });
    }

    // Step 5: Authentication successful! Delete the challenge (one-time use)
    pendingChallenges.delete(cleanUsername);

    // Step 6: Issue a JWT for session management
    //
    // After verifying the Hive signature, we switch to standard JWT-based
    // sessions. The JWT contains the username and is signed with our server
    // secret. Subsequent API calls send this JWT in the Authorization header
    // instead of re-signing with Keychain each time.
    const tokenPayload = {
      username: cleanUsername,
      auth_method: "hive_keychain",
      iat: Math.floor(Date.now() / 1000),
    };

    const token = jwt.sign(tokenPayload, JWT_SECRET, { expiresIn: "24h" });

    res.json({
      token,
      username: cleanUsername,
      expires_in: 86400, // 24 hours in seconds
    });
  } catch (err) {
    console.error("Verification error:", err);
    res.status(500).json({ error: "Verification failed" });
  }
});

// ---------------------------------------------------------------------------
// JWT middleware
// ---------------------------------------------------------------------------

/**
 * Middleware to verify JWT tokens on protected routes.
 *
 * Expects the token in the Authorization header:
 *   Authorization: Bearer eyJhbGciOi...
 *
 * If valid, req.user is set to the decoded JWT payload.
 */
function requireAuth(req, res, next) {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    return res.status(401).json({ error: "Authorization header required" });
  }

  const token = authHeader.split(" ")[1];

  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    req.user = decoded;
    next();
  } catch (err) {
    return res.status(401).json({ error: "Invalid or expired token" });
  }
}

/**
 * GET /api/profile
 *
 * Protected route — requires a valid JWT.
 * Returns the authenticated user's Hive account data.
 *
 * This demonstrates how to use the JWT after Keychain authentication.
 * Any subsequent API calls that need auth should use this pattern.
 */
app.get("/api/profile", requireAuth, async (req, res) => {
  try {
    const account = await getHiveAccount(req.user.username);
    if (!account) {
      return res.status(404).json({ error: "Account not found" });
    }

    // Parse the JSON metadata (profile info, etc.)
    let profile = {};
    try {
      const meta = JSON.parse(account.posting_json_metadata || "{}");
      profile = meta.profile || {};
    } catch {
      // Metadata might not be valid JSON
    }

    res.json({
      username: account.name,
      profile: {
        name: profile.name || account.name,
        about: profile.about || "",
        location: profile.location || "",
        website: profile.website || "",
        profile_image: profile.profile_image || "",
        cover_image: profile.cover_image || "",
      },
      reputation: account.reputation,
      post_count: account.post_count,
      created: account.created,
      balance: account.balance,
      hbd_balance: account.hbd_balance,
      vesting_shares: account.vesting_shares,
    });
  } catch (err) {
    console.error("Profile fetch error:", err);
    res.status(500).json({ error: "Failed to fetch profile" });
  }
});

// ---------------------------------------------------------------------------
// Start server
// ---------------------------------------------------------------------------
app.listen(PORT, () => {
  console.log(`Hive Keychain Auth server running on http://localhost:${PORT}`);
  console.log(`Using Hive node: ${HIVE_NODE}`);
});
