# Hive Keychain Authentication Template (Python / Flask + beem)

A complete, production-ready authentication template for Hive blockchain dapps
using the Hive Keychain browser extension. This Python version uses Flask for
the backend and the `beem` library for blockchain interaction and signature
verification.

## What Is Hive Keychain?

[Hive Keychain](https://hive-keychain.com) is a browser extension (Chrome,
Firefox, Brave, Edge) that securely manages Hive blockchain private keys:

- **Keys stay local.** Private keys are encrypted and stored in the browser
  extension. They are NEVER sent to any website or server.
- **User approves every action.** When a dapp requests a signature or
  transaction, Keychain shows a popup with full details for user approval.
- **No passwords, no OAuth.** Authentication is purely cryptographic -- the
  user proves they control a Hive account by signing a challenge.

## Hive Key Hierarchy

Every Hive account has four key pairs with different permission levels:

| Key        | Privilege | Used For                                          |
|------------|-----------|---------------------------------------------------|
| **Owner**  | Highest   | Change other keys, account recovery               |
| **Active** | High      | Transfers, power-ups, market orders, delegation   |
| **Posting**| Low       | Posts, votes, follows, dapp custom_json            |
| **Memo**   | Special   | Encrypt/decrypt private messages                  |

**For authentication, always use the Posting key.** It is the lowest-privilege
key and cannot move funds or change account settings.

## How Challenge-Response Authentication Works

```
  Browser                      Flask Server               Hive Blockchain
  -------                      ------------               ---------------
     |                            |                              |
     |  1. POST /api/auth/challenge                              |
     |     { username: "alice" }  |                              |
     |  =========================>|                              |
     |                            |  beem.Account("alice")       |
     |                            |  ============================>
     |                            |  <============================
     |  2. { challenge: "hive-auth:alice:..." }                  |
     |  <=========================|                              |
     |                            |                              |
     |  3. Keychain.requestSignBuffer("alice", challenge, "Posting")
     |     [User approves in popup]                              |
     |     -> signature = "20abcdef..."                          |
     |                            |                              |
     |  4. POST /api/auth/verify                                 |
     |     { username, challenge, signature }                    |
     |  =========================>|                              |
     |                            |  beem: verify_message()      |
     |                            |  Recover pubkey from sig     |
     |                            |  Compare to on-chain key     |
     |                            |                              |
     |  5. Set-Cookie: session=<signed>; HttpOnly; SameSite=Lax  |
     |     { authenticated: true, username: "alice" }            |
     |  <=========================|                              |
```

### Step-by-step

1. **User enters username** and clicks "Sign in with Keychain."
2. **Flask generates a challenge** -- a random string tied to the username.
3. **Keychain signs the challenge** with the user's private posting key.
4. **Flask verifies the signature** using beem:
   - `verify_message()` recovers the public key from (SHA-256 hash, signature)
   - Compares the recovered key to the on-chain posting public key
5. **Flask creates a session** (signed HttpOnly cookie).

## Project Structure

```
python/
  app.py               Flask backend: challenge generation, beem signature
                       verification, Flask session management, profile API
  requirements.txt     Dependencies: flask, beem, python-dotenv, flask-cors
  .env.example         Configuration template
  test_app.py          Comprehensive test suite (mocked blockchain calls)
  README.md            This file
  templates/
    index.html         Jinja2 template: login form, profile, operations panel
  static/
    app.js             Frontend JS: Keychain interactions, auth flow, operations
                       (post, transfer, vote, delegate, custom_json)
```

## Setup and Running

### Prerequisites

- Python 3.10+
- [Hive Keychain](https://hive-keychain.com) browser extension installed
- A Hive account (create one at [signup.hive.io](https://signup.hive.io))

### Installation

```bash
# Navigate to the Python template directory
cd python/

# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate       # Linux/Mac
# venv\Scripts\activate        # Windows

# Install dependencies
pip install -r requirements.txt

# Create your .env file from the template
cp .env.example .env

# (Optional) Edit .env to set a strong FLASK_SECRET_KEY:
#   python -c "import secrets; print(secrets.token_hex(32))"

# Start the server
python app.py
```

### Open in Browser

Navigate to `http://localhost:5050`. You should see the login form.

### Run Tests

```bash
# With pytest (recommended)
python -m pytest test_app.py -v

# Or with unittest directly
python test_app.py
```

The test suite mocks all blockchain interactions, so it runs without a
network connection or beem installed (it mocks beem functions).

## API Endpoints

| Method | Path                  | Auth    | Description                           |
|--------|-----------------------|---------|---------------------------------------|
| GET    | `/`                   | None    | Serve the login page (Jinja2)         |
| POST   | `/api/auth/challenge` | None    | Generate a challenge for the username |
| POST   | `/api/auth/verify`    | None    | Verify Keychain signature, set session|
| GET    | `/api/profile`        | Session | Get authenticated user's Hive profile |
| POST   | `/api/auth/logout`    | Session | Clear the session (log out)           |
| GET    | `/api/auth/status`    | None    | Check if current session is valid     |

### POST /api/auth/challenge

**Request:**

```json
{ "username": "alice" }
```

**Response:**

```json
{
  "challenge": "hive-auth:alice:a7f3b2c1d4e5f6...:1709000000",
  "expires_in": 300
}
```

### POST /api/auth/verify

**Request:**

```json
{
  "username": "alice",
  "challenge": "hive-auth:alice:a7f3b2c1d4e5f6...:1709000000",
  "signature": "20abcdef0123456789..."
}
```

**Response:**

```json
{ "authenticated": true, "username": "alice" }
```

The response also sets a `Set-Cookie` header with the signed Flask session.

### GET /api/profile (requires session cookie)

**Response:**

```json
{
  "username": "alice",
  "profile": {
    "name": "Alice",
    "about": "Hive developer",
    "profile_image": "https://..."
  },
  "reputation": 7500000000000,
  "post_count": 42,
  "balance": "100.000 HIVE",
  "hbd_balance": "50.000 HBD"
}
```

## Signature Verification with beem

The Python version uses beem's `verify_message()` function for signature
verification. This implements the Graphene-standard public key recovery method:

1. **Hash:** SHA-256 of the challenge string (matching what Keychain does).
2. **Recover:** `beemgraphenebase.ecdsasig.verify_message(hash, sig_bytes)`
   recovers the secp256k1 public key from the 65-byte signature.
3. **Compare:** The recovered `PublicKey` is compared (as string) to the
   on-chain posting public key fetched via `beem.account.Account`.

This is the standard verification approach in the Hive/Graphene ecosystem --
"What public key produced this signature? Does it match the on-chain key?"

## Differences from the JavaScript Version

| Aspect              | JavaScript (Node.js)                | Python (Flask)                      |
|---------------------|-------------------------------------|-------------------------------------|
| Web framework       | Express                             | Flask                               |
| Session management  | JWT in localStorage                 | Flask signed session cookie         |
| Blockchain library  | Raw JSON-RPC + crypto module        | beem (full Hive SDK)                |
| Sig verification    | Direct ECDSA verify (crypto.verify) | Public key recovery (verify_message)|
| Session storage     | Client-side (localStorage)          | Client-side (signed cookie)         |
| XSS exposure        | JWT readable by JS (localStorage)   | Cookie is HttpOnly (JS cannot read) |
| Frontend JS file    | public/app.js                       | static/app.js (Flask static)        |
| Template engine     | Plain HTML                          | Jinja2 (url_for for static files)   |

Both approaches are correct and secure. The Python version has slightly
better XSS protection because the session cookie is HttpOnly.

## Frontend Keychain Operations

After login, the frontend provides a tabbed operations panel demonstrating
all major Keychain API methods:

| Method              | Key Type | Purpose                                     |
|---------------------|----------|---------------------------------------------|
| requestSignBuffer   | Posting  | Sign arbitrary data (used for authentication)|
| requestBroadcast    | Posting  | Post content, vote, custom_json             |
| requestTransfer     | Active   | Send HIVE/HBD tokens                        |
| requestDelegation   | Active   | Delegate Hive Power                         |

## Security Considerations

### In Production

1. **Set FLASK_SECRET_KEY** to a strong random value:

   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

2. **Use Redis for challenges** instead of the in-memory dict. The in-memory
   store is lost on server restart and does not work with multiple workers.

3. **Rate-limit /api/auth/challenge** to prevent abuse.

4. **Use HTTPS** in production. Session cookies should have `Secure` flag.

5. **Set SESSION_COOKIE_SECURE=True** in production (requires HTTPS).

6. **Deploy with gunicorn** (not the Flask dev server):

   ```bash
   gunicorn -w 4 -b 0.0.0.0:5050 app:app
   ```

### What Cannot Go Wrong

Even if your server is completely compromised:

- **Private keys are safe.** They never leave the Keychain extension.
- **Signatures cannot be replayed.** Each is bound to a single-use challenge.
- **No password database to breach.** Authentication is cryptographic.

## Dependencies

| Package      | Purpose                                            |
|--------------|----------------------------------------------------|
| flask        | Web framework                                      |
| beem         | Hive blockchain SDK (account lookup, sig verify)   |
| python-dotenv| Load environment variables from .env               |
| flask-cors   | Cross-Origin Resource Sharing middleware            |

## License

MIT
