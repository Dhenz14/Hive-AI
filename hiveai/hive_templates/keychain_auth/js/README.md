# Hive Keychain Authentication Template (Node.js / Express)

A complete, production-ready authentication template for Hive blockchain dapps
using the Hive Keychain browser extension for challenge-response authentication.

## What Is Hive Keychain?

[Hive Keychain](https://hive-keychain.com) is a browser extension (available for
Chrome, Firefox, Brave, and Edge) that securely manages Hive blockchain private
keys. It works like MetaMask does for Ethereum:

- **Keys stay local.** Private keys are encrypted and stored in the browser
  extension. They are NEVER sent to any website or server.
- **User approves every action.** When a dapp requests a signature or transaction,
  Keychain shows a popup with the full details. The user must explicitly approve.
- **No passwords, no OAuth.** Authentication is purely cryptographic -- the user
  proves they control a Hive account by signing a challenge with their private key.

### Why This Matters

Traditional web authentication relies on passwords (which can be leaked, phished,
or brute-forced) or OAuth (which depends on a third-party provider). Hive Keychain
authentication has none of these weaknesses:

- No password database to breach
- No OAuth provider that could go offline
- No session tokens on the server (JWT is stateless)
- Cryptographic proof of identity tied to the blockchain

## Hive Key Hierarchy

Every Hive account has four key pairs, each with different permission levels.
Understanding this hierarchy is essential for building secure Hive dapps.

| Key | Privilege | Used For | Keychain Indicator |
|------|-----------|----------|-------------------|
| **Owner** | Highest | Change other keys, account recovery | Red warning |
| **Active** | High | Transfers, power-ups, market orders, delegation | Orange warning |
| **Posting** | Low | Posts, votes, follows, dapp custom_json | Green indicator |
| **Memo** | Special | Encrypt/decrypt private messages | -- |

**For authentication, always use the Posting key.** It is the lowest-privilege key
and cannot move funds or change account settings. If a posting key were somehow
compromised, the worst an attacker could do is post or vote on the user's behalf --
not steal their tokens.

## How Challenge-Response Authentication Works

```
  Browser                      Server                     Hive Blockchain
  -------                      ------                     ---------------
     |                            |                              |
     |  1. POST /api/auth/challenge                              |
     |     { username: "alice" }  |                              |
     |  =========================>|                              |
     |                            |  Verify account exists       |
     |                            |  ============================>
     |                            |  <============================
     |  2. { challenge: "hive-auth:alice:abc123:170900..." }     |
     |  <=========================|                              |
     |                            |                              |
     |  3. Keychain.requestSignBuffer("alice", challenge, "Posting")
     |     [User sees challenge, clicks Confirm]                 |
     |     -> signature = "20abcdef..."                          |
     |                            |                              |
     |  4. POST /api/auth/verify                                 |
     |     { username, challenge, signature }                    |
     |  =========================>|                              |
     |                            |  Fetch alice's public keys   |
     |                            |  ============================>
     |                            |  <============================
     |                            |  Verify sig matches pubkey   |
     |                            |                              |
     |  5. { token: "eyJ..." }    |                              |
     |  <=========================|                              |
     |                            |                              |
     |  6. GET /api/profile       |                              |
     |     Authorization: Bearer eyJ...                          |
     |  =========================>|                              |
```

### Step-by-step

1. **User enters username** and clicks "Sign in with Keychain."
2. **Frontend requests a challenge** from the server (`POST /api/auth/challenge`).
   The server generates a unique random string tied to the username with an expiry.
3. **Keychain signs the challenge.** The frontend calls
   `window.hive_keychain.requestSignBuffer(username, challenge, "Posting", callback)`.
   Keychain pops up showing the challenge text and asks the user to approve.
4. **Frontend sends the signature** to the server (`POST /api/auth/verify`).
5. **Server verifies the signature:**
   - Fetches the user's public posting key(s) from the Hive blockchain
   - Computes SHA-256 of the challenge (same hash Keychain used)
   - Verifies the ECDSA signature against the public key
   - If valid, the user has cryptographically proven they control this account
6. **Server issues a JWT** for subsequent authenticated API calls.

### Why Challenges Are Secure

- **Random:** Each challenge contains 32 random bytes -- impossible to predict.
- **Single-use:** Deleted from storage after verification -- cannot be replayed.
- **Time-limited:** Expires after 5 minutes -- no stale challenges.
- **Username-bound:** Contains the username -- cannot be reused across accounts.

## Project Structure

```
js/
  server.js          # Express backend: challenge generation, signature
                     # verification, JWT issuance, profile API
  package.json       # Dependencies: express, cors, jsonwebtoken, dotenv
  .env.example       # Configuration template
  README.md          # This file
  public/
    index.html       # Frontend UI: login form, profile display, operations panel
    app.js           # Frontend JS: Keychain interactions, auth flow, post-auth
                     # operations (post, transfer, vote, delegate, custom_json)
```

## Setup and Running

### Prerequisites

- [Node.js](https://nodejs.org/) 18+ installed
- [Hive Keychain](https://hive-keychain.com) browser extension installed
- A Hive account (create one at [signup.hive.io](https://signup.hive.io))

### Installation

```bash
# Clone or copy this template
cd js/

# Install dependencies
npm install

# Create your .env file from the template
cp .env.example .env

# (Optional) Edit .env to set a strong JWT_SECRET
# The default works for development but MUST be changed in production

# Start the server
npm start

# Or with auto-restart on file changes (development)
npm run dev
```

### Open in Browser

Navigate to `http://localhost:3000`. You should see the login form.

### Test the Authentication Flow

1. Enter a valid Hive username (e.g., your own account)
2. Click "Sign in with Keychain"
3. Approve the signature request in the Keychain popup
4. You should see your Hive profile data and the operations panel

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/`  | None | Serve the login page |
| `POST` | `/api/auth/challenge` | None | Generate a challenge for the given username |
| `POST` | `/api/auth/verify` | None | Verify a Keychain signature and get a JWT |
| `GET`  | `/api/profile` | JWT | Get the authenticated user's Hive profile |

### POST /api/auth/challenge

**Request:**
```json
{ "username": "alice" }
```

**Response:**
```json
{
  "challenge": "hive-auth:alice:a7f3b2c1d4e5f6...:1709000000000",
  "expires_in": 300
}
```

### POST /api/auth/verify

**Request:**
```json
{
  "username": "alice",
  "challenge": "hive-auth:alice:a7f3b2c1d4e5f6...:1709000000000",
  "signature": "20abcdef0123456789..."
}
```

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "username": "alice",
  "expires_in": 86400
}
```

### GET /api/profile

**Headers:** `Authorization: Bearer eyJhbGciOiJIUzI1NiIs...`

**Response:**
```json
{
  "username": "alice",
  "profile": {
    "name": "Alice",
    "about": "Hive developer",
    "location": "Decentralized",
    "website": "https://alice.dev",
    "profile_image": "https://...",
    "cover_image": "https://..."
  },
  "reputation": 7500000000000,
  "post_count": 42,
  "created": "2020-01-15T00:00:00",
  "balance": "100.000 HIVE",
  "hbd_balance": "50.000 HBD",
  "vesting_shares": "500000.000000 VESTS"
}
```

## Frontend Keychain API Methods

The `public/app.js` file demonstrates all major Keychain API methods with full
tutorial comments explaining each parameter and the user experience:

| Method | Key Type | Purpose |
|--------|----------|---------|
| `requestSignBuffer` | Posting | Sign arbitrary data (used for authentication) |
| `requestBroadcast` | Posting/Active | Broadcast any Hive transaction (post, vote, custom_json) |
| `requestTransfer` | Active | Send HIVE/HBD tokens (dedicated transfer UI) |
| `requestDelegation` | Active | Delegate Hive Power to another account |

### Operations Panel

After logging in, the frontend shows a tabbed operations panel with:

- **Post** -- Publish a blog post to the Hive blockchain
- **Transfer** -- Send HIVE or HBD tokens to another account
- **Vote** -- Upvote or downvote content (posts/comments)
- **Delegate** -- Delegate Hive Power to another account
- **Custom JSON** -- Broadcast arbitrary dapp data

Each operation prompts Keychain for user approval. The private key never
leaves the extension.

## Signature Verification Details

Hive uses the Graphene signature scheme (secp256k1 ECDSA, shared with
BitShares and Steem):

1. **Hashing:** The challenge string is SHA-256 hashed (matching what Keychain does internally).
2. **Signature format:** 65 bytes = 1 byte recovery ID + 32 bytes r + 32 bytes s (hex-encoded).
3. **Public key format:** `STM` prefix + base58check(33-byte compressed pubkey + 4-byte RIPEMD160 checksum).
4. **Verification:** Node.js native `crypto.verify()` with the on-chain public key in SPKI DER format.

This implementation uses only Node.js built-in `crypto` module -- no native
C dependencies or Hive-specific npm packages required.

## Security Considerations

### In Production

1. **Change JWT_SECRET** to a strong random value (32+ bytes):
   ```bash
   node -e "console.log(require('crypto').randomBytes(64).toString('hex'))"
   ```

2. **Use Redis for challenges** instead of the in-memory Map. The in-memory
   store is lost on server restart and does not scale across multiple instances.

3. **Rate-limit the challenge endpoint** to prevent abuse:
   - Max 5 challenges per username per minute
   - Max 20 challenges per IP per minute

4. **Use HTTPS** in production. Signatures transmitted over HTTP could be
   intercepted (though they are single-use, timing matters).

5. **Consider httpOnly cookies** instead of localStorage for JWT storage.
   localStorage is vulnerable to XSS attacks.

6. **Set CORS appropriately.** The template uses permissive CORS for
   development. In production, restrict to your domain.

### What Cannot Go Wrong

Even if your server is completely compromised:

- **Private keys are safe.** They never leave the Keychain extension.
- **Signatures are useless.** Each signature is bound to a specific challenge
  that is already consumed. A stolen signature cannot be replayed.
- **No password database.** There is nothing to breach.

The worst an attacker could do is issue fake JWTs, which only affect your
app -- not the user's Hive account or funds.

## Dependencies

| Package | Purpose |
|---------|---------|
| express | Web server framework |
| cors | Cross-Origin Resource Sharing middleware |
| jsonwebtoken | JWT creation and verification |
| dotenv | Load environment variables from .env file |

## License

MIT
