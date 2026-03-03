"""
Hive Keychain Authentication Server (Python / Flask + beem)
============================================================

WHY HIVE KEYCHAIN EXISTS
-------------------------
Hive accounts are controlled by cryptographic key pairs (posting, active, owner, memo).
Users should NEVER paste private keys into a website. Hive Keychain is a browser extension
(like MetaMask for Ethereum) that stores keys locally and signs transactions on behalf of
the user. The dapp never sees the private key -- it only receives the resulting signature.

THE CHALLENGE-RESPONSE AUTH FLOW
---------------------------------
1. User clicks "Login" and provides their Hive username.
2. Server generates a unique, random challenge string (a nonce).
3. Frontend asks Hive Keychain to sign that challenge with the user's posting key.
4. Keychain prompts the user to approve the signature (user sees what they are signing).
5. Frontend sends (username, challenge, signature) back to the server.
6. Server fetches the user's public posting key from the Hive blockchain.
7. Server verifies the signature was produced by the corresponding private key.
8. If valid, server creates an authenticated Flask session.

This is the standard authentication pattern for Hive dapps. No passwords, no OAuth --
just cryptographic proof that the user controls the account.

HIVE KEY HIERARCHY
-------------------
Every Hive account has four key pairs with different permission levels:

  1. OWNER KEY (highest privilege)
     - Can change ALL other keys, recover the account
     - Should be kept offline in cold storage
     - Hive Keychain shows a RED warning when this key is requested

  2. ACTIVE KEY (financial operations)
     - Required for: transfers, power-ups/power-downs, witness votes, market orders
     - This is the "wallet" key
     - Keychain shows an ORANGE warning for active key operations

  3. POSTING KEY (social operations) <-- Used for authentication
     - Required for: publishing posts, voting, reblogging, following, custom_json
     - SAFEST key for login: cannot move funds or change account settings
     - Worst case if compromised: someone posts/votes on your behalf
     - Keychain shows a GREEN indicator for posting operations

  4. MEMO KEY (message encryption)
     - Used to encrypt/decrypt private messages (transfer memos)
     - Not used for signing transactions

For authentication, we ALWAYS use the POSTING key (principle of least privilege).

SIGNATURE VERIFICATION WITH BEEM
----------------------------------
The beem library (https://github.com/holgern/beem) is the standard Python library
for Hive blockchain interaction. It provides:
  - Account lookups (fetching public keys from on-chain data)
  - Signature verification (secp256k1 ECDSA, Graphene scheme)
  - Transaction building and broadcasting
  - Blockchain state queries

Under the hood, Hive uses secp256k1 ECDSA (same curve as Bitcoin).
Signatures are 65 bytes: 1 byte recovery ID + 32 bytes r + 32 bytes s.
Verification recovers the public key from (message_hash, signature) and compares
it to the on-chain public key. If they match, the signature is valid.
"""

import hashlib
import json
import os
import secrets
import time
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
from flask_cors import CORS

# ---------------------------------------------------------------------------
# beem imports for Hive blockchain interaction
# ---------------------------------------------------------------------------
# beem is the standard Python library for the Hive blockchain.
# Install with: pip install beem>=0.24
#
# beem.account.Account -- Fetch account data (public keys, balances, profile)
#   from the Hive blockchain. Example:
#     account = Account("alice", blockchain_instance=hive)
#     posting_keys = [k for k, w in account["posting"]["key_auths"]]
#
# beem.hive.Hive -- Connection to a Hive API node for JSON-RPC calls.
#   Example: hive = Hive(node="https://api.hive.blog")
#
# beemgraphenebase.ecdsasig.verify_message -- Low-level ECDSA signature
#   verification. Recovers the public key from a (message_hash, signature)
#   pair using the secp256k1 curve. If the recovered key matches the
#   on-chain key, the signature is valid.
#
# beemgraphenebase.account.PublicKey -- Handles Hive's public key format:
#   "STM" prefix + base58check(33-byte compressed pubkey + 4-byte RIPEMD160 checksum)
try:
    from beem.account import Account
    from beem.hive import Hive
    from beemgraphenebase.ecdsasig import verify_message
    from beemgraphenebase.account import PublicKey

    BEEM_AVAILABLE = True
except ImportError:
    BEEM_AVAILABLE = False
    print(
        "WARNING: beem is not installed. Signature verification will be disabled.\n"
        "Install it with: pip install beem>=0.24\n"
    )

# Load environment variables from .env file (if present)
load_dotenv()

# ---------------------------------------------------------------------------
# Flask application setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

# SECRET_KEY is used by Flask to cryptographically sign session cookies.
# Flask sessions are tamper-proof (signed with HMAC) but NOT encrypted --
# do not store sensitive data directly in the session.
# In production, set this to a strong random value via environment variable.
app.secret_key = os.getenv(
    "FLASK_SECRET_KEY", "change-this-to-a-random-secret-in-production"
)

# Session configuration
# SESSION_COOKIE_HTTPONLY: prevent JavaScript from reading the session cookie (XSS defense)
# SESSION_COOKIE_SAMESITE: prevent CSRF by only sending the cookie on same-site requests
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# CORS configuration -- allows the frontend to make API calls to this backend.
# supports_credentials=True is needed for Flask session cookies to be sent
# cross-origin (if the frontend is on a different port during development).
# In production, restrict origins to your actual domain.
CORS(app, supports_credentials=True)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# The Hive API node to use for blockchain queries.
# api.hive.blog is the official API node. Alternatives include:
#   - api.deathwing.me  (community node, very reliable)
#   - api.openhive.network  (community node)
#   - anyx.io  (community node)
# beem supports passing a list of nodes for automatic failover.
HIVE_NODE = os.getenv("HIVE_NODE", "https://api.hive.blog")

# Port for the Flask development server
PORT = int(os.getenv("PORT", "5050"))

# Challenge expiry time in seconds.
# Challenges older than this are rejected to prevent replay attacks.
CHALLENGE_TTL = 300  # 5 minutes

# In-memory store for pending challenges.
# Key: username (str), Value: dict with challenge, created_at, expires_at
#
# PRODUCTION NOTE: Use Redis or a database with TTL expiration instead.
# The in-memory store is lost on server restart and does not scale
# across multiple workers/processes.
pending_challenges: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Initialize beem Hive connection
# ---------------------------------------------------------------------------
# The Hive instance is our connection to the blockchain.
# We use it to fetch account data (public keys, profile info, balances).
if BEEM_AVAILABLE:
    hive = Hive(node=HIVE_NODE)
else:
    hive = None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def get_hive_account(username: str) -> dict | None:
    """
    Fetch a Hive account's data from the blockchain using beem.

    beem's Account class calls condenser_api.get_accounts under the hood
    and returns a dict-like object with all on-chain account data:

      - account["posting"]["key_auths"]:  list of [public_key, weight] for posting authority
      - account["active"]["key_auths"]:   same for active authority
      - account["owner"]["key_auths"]:    same for owner authority
      - account["memo_key"]:              the memo public key
      - account["balance"]:               liquid HIVE balance (e.g., "100.000 HIVE")
      - account["hbd_balance"]:           HBD balance (e.g., "50.000 HBD")
      - account["vesting_shares"]:        Hive Power in VESTS
      - account["posting_json_metadata"]: JSON string with profile info
      - account["reputation"]:            raw reputation score
      - account["post_count"]:            number of root posts
      - account["created"]:               account creation timestamp

    Returns None if the account does not exist.
    """
    if not BEEM_AVAILABLE:
        return None
    try:
        account = Account(username, blockchain_instance=hive)
        # Convert to plain dict for easier serialization
        return dict(account)
    except Exception:
        return None


def verify_hive_signature(
    challenge: str, signature_hex: str, public_key_str: str
) -> bool:
    """
    Verify a Hive Keychain signature against a challenge and public key.

    HOW HIVE SIGNATURE VERIFICATION WORKS
    =======================================

    Hive Keychain's requestSignBuffer() does the following internally:
      1. Takes the raw message string (our challenge).
      2. Computes SHA-256 hash of the message bytes.
      3. Signs the hash with the user's private posting key using secp256k1 ECDSA.
      4. Returns the signature as a hex string (65 bytes = 130 hex chars).

    To verify on the server with beem:
      1. Compute the same SHA-256 hash of the challenge string.
      2. Convert the hex signature to bytes.
      3. Use verify_message() to RECOVER the public key from (hash, signature).
      4. Compare the recovered key to the on-chain public key.

    The recovery step is what makes this elegant: we do not need the private
    key to verify -- we DERIVE the public key from the signature and then
    check if it matches what the blockchain says the user's key should be.

    Parameters:
        challenge:       The original challenge string that was signed
        signature_hex:   65-byte hex-encoded signature from Keychain (130 hex chars)
        public_key_str:  On-chain public key in Hive format (e.g., "STM7abc...")

    Returns:
        True if the signature is valid for this public key and message.
    """
    if not BEEM_AVAILABLE:
        return False

    try:
        # Step 1: Hash the challenge with SHA-256.
        # This matches what Hive Keychain does internally when signing.
        # The raw challenge string is UTF-8 encoded, then SHA-256 hashed.
        message_hash = hashlib.sha256(challenge.encode("utf-8")).digest()

        # Step 2: Convert the hex signature to bytes.
        # The signature is exactly 65 bytes:
        #   [recovery_id (1 byte)] [r (32 bytes)] [s (32 bytes)]
        # The recovery_id encodes which of the two possible public keys
        # should be recovered (secp256k1 ECDSA has this ambiguity).
        signature_bytes = bytes.fromhex(signature_hex)
        if len(signature_bytes) != 65:
            print(f"Signature length {len(signature_bytes)}, expected 65")
            return False

        # Step 3: Recover the public key from the signature.
        #
        # verify_message() is from beemgraphenebase.ecdsasig.
        # It takes the raw message hash (32 bytes) and the full 65-byte signature.
        # Internally it:
        #   a. Extracts the recovery_id from the first byte
        #   b. Extracts r and s from the remaining 64 bytes
        #   c. Uses secp256k1 ECDSA public key recovery to compute the public key
        #   d. Returns a PublicKey object
        #
        # This is the Graphene-standard verification method used by Hive, Steem,
        # and BitShares. It's more common in these ecosystems than direct ECDSA verify.
        recovered_key = verify_message(message_hash, signature_bytes)

        # Step 4: Compare the recovered public key to the on-chain key.
        #
        # PublicKey() parses the Hive-format public key string:
        #   "STM" + base58check(33-byte compressed pubkey + 4-byte RIPEMD160 checksum)
        #
        # We compare the string representations. Both keys use the same format
        # so string comparison is sufficient and correct.
        on_chain_key = PublicKey(public_key_str, prefix="STM")

        return str(recovered_key) == str(on_chain_key)

    except Exception as e:
        print(f"Signature verification error: {e}")
        return False


def clean_expired_challenges():
    """
    Remove expired challenges from the in-memory store.

    Called periodically during challenge generation to prevent memory leaks.
    In production with Redis, use TTL keys instead.
    """
    now = time.time()
    expired = [
        username
        for username, data in pending_challenges.items()
        if now > data["expires_at"]
    ]
    for username in expired:
        del pending_challenges[username]


def require_auth(f):
    """
    Decorator to require authentication on a route.

    Checks the Flask session for a valid authenticated session.
    If not authenticated, returns 401 Unauthorized.

    Usage:
        @app.route("/api/protected")
        @require_auth
        def protected_route():
            username = session["username"]
            ...

    The Flask session cookie is:
      - Signed with HMAC (tamper-proof)
      - HttpOnly (not accessible to JavaScript -- XSS defense)
      - SameSite=Lax (not sent on cross-origin requests -- CSRF defense)
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Routes: Frontend
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """
    Serve the main login page.

    Renders the Jinja2 template (templates/index.html) which contains
    the login form, profile display, and Keychain operations panel.
    The template loads static/app.js for frontend Keychain interaction logic.
    """
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Routes: Authentication API
# ---------------------------------------------------------------------------


@app.route("/api/auth/challenge", methods=["POST"])
def generate_challenge():
    """
    Generate a random challenge for the user to sign with Hive Keychain.

    The challenge is a unique, random string that:
      - Prevents replay attacks (each login attempt gets a fresh challenge)
      - Expires after 5 minutes (prevents stale challenge reuse)
      - Is tied to the username (prevents challenge reuse across accounts)

    Request body (JSON):
        { "username": "alice" }

    Response (JSON):
        {
            "challenge": "hive-auth:alice:a7f3...d2e1:1709000000",
            "expires_in": 300
        }

    Errors:
        400 - Missing or invalid username
        404 - Hive account not found on the blockchain
        500 - Internal server error
    """
    try:
        data = request.get_json(silent=True) or {}
        username = data.get("username", "").lower().strip()

        if not username:
            return jsonify({"error": "Username is required"}), 400

        # Verify the account exists on the Hive blockchain before generating
        # a challenge. This prevents wasting resources on non-existent accounts
        # and gives the user immediate feedback if they mistyped their name.
        account = get_hive_account(username)
        if not account:
            return jsonify({"error": "Hive account not found"}), 404

        # Generate the challenge string.
        #
        # Format: "hive-auth:<username>:<random_hex>:<timestamp>"
        #
        # Why this format?
        #   - "hive-auth:" prefix makes it clear to the user what they are signing
        #     (they see this in the Keychain popup)
        #   - Username binds the challenge to one specific account
        #   - 32 random bytes (64 hex chars) make it cryptographically unpredictable
        #   - Timestamp enables server-side expiration checking
        random_hex = secrets.token_hex(32)
        timestamp = int(time.time())
        challenge = f"hive-auth:{username}:{random_hex}:{timestamp}"

        # Store the challenge with expiry metadata.
        # Only one active challenge per username (newest replaces oldest).
        # This prevents accumulation of unused challenges.
        pending_challenges[username] = {
            "challenge": challenge,
            "created_at": timestamp,
            "expires_at": timestamp + CHALLENGE_TTL,
        }

        # Periodically clean up expired challenges to prevent memory leaks
        clean_expired_challenges()

        return jsonify({
            "challenge": challenge,
            "expires_in": CHALLENGE_TTL,
        })

    except Exception as e:
        print(f"Challenge generation error: {e}")
        return jsonify({"error": "Failed to generate challenge"}), 500


@app.route("/api/auth/verify", methods=["POST"])
def verify_and_authenticate():
    """
    Verify a Hive Keychain signature and create an authenticated session.

    This is the core of the authentication flow:
      1. Look up the pending challenge for this username.
      2. Check it has not expired.
      3. Fetch the user's posting public key(s) from the Hive blockchain.
      4. Verify the signature against each posting key (accounts can have multiple).
      5. If valid, delete the challenge (one-time use) and create a Flask session.

    Request body (JSON):
        {
            "username": "alice",
            "challenge": "hive-auth:alice:a7f3...d2e1:1709000000",
            "signature": "20abcdef0123456789..."
        }

    Response (JSON):
        { "authenticated": true, "username": "alice" }

    Errors:
        400 - Missing required fields, no posting keys
        401 - No pending challenge, challenge mismatch, expired, invalid signature
        404 - Hive account not found
        500 - Internal server error
        503 - beem not installed (cannot verify signatures)
    """
    if not BEEM_AVAILABLE:
        return jsonify({
            "error": "beem library is not installed. "
                     "Install with: pip install beem>=0.24"
        }), 503

    try:
        data = request.get_json(silent=True) or {}
        username = data.get("username", "").lower().strip()
        challenge = data.get("challenge", "")
        signature = data.get("signature", "")

        if not username or not challenge or not signature:
            return jsonify({
                "error": "username, challenge, and signature are required"
            }), 400

        # Step 1: Look up the pending challenge for this username.
        # If there is no pending challenge, either:
        #   - The user never requested one (direct /verify call)
        #   - The challenge was already consumed (double-submit)
        #   - The server restarted (in-memory store was lost)
        pending = pending_challenges.get(username)
        if not pending:
            return jsonify({"error": "No pending challenge for this user"}), 401

        # Step 2: Verify the challenge matches what we issued.
        # The client must send back the EXACT same challenge string.
        if pending["challenge"] != challenge:
            return jsonify({"error": "Challenge mismatch"}), 401

        # Step 3: Check the challenge has not expired.
        # Challenges are valid for CHALLENGE_TTL seconds (default: 5 minutes).
        if time.time() > pending["expires_at"]:
            del pending_challenges[username]
            return jsonify({
                "error": "Challenge expired -- please request a new one"
            }), 401

        # Step 4: Fetch the user's posting public keys from the blockchain.
        #
        # A Hive account's "posting" authority contains one or more public keys.
        # Each key has a weight, and there is a threshold for multi-sig.
        # For most accounts, there is exactly one posting key with weight 1.
        #
        # We use the POSTING key for authentication because:
        #   - It is the lowest-privilege key (principle of least privilege)
        #   - It cannot transfer funds or change account settings
        #   - Users are comfortable approving posting-key signatures
        #   - It still cryptographically proves account ownership
        account = get_hive_account(username)
        if not account:
            return jsonify({"error": "Hive account not found"}), 404

        # account["posting"]["key_auths"] is a list of [public_key_string, weight]
        # Example: [["STM7abc...", 1], ["STM8def...", 1]]
        posting_keys = [key for key, weight in account["posting"]["key_auths"]]

        if not posting_keys:
            return jsonify({
                "error": "Account has no posting keys configured"
            }), 400

        # Step 5: Verify the signature against each posting key.
        #
        # We try every posting key because multi-sig accounts may have
        # multiple keys. The signature must match at least ONE of them.
        verified = False
        for pub_key in posting_keys:
            if verify_hive_signature(challenge, signature, pub_key):
                verified = True
                break

        if not verified:
            return jsonify({"error": "Invalid signature"}), 401

        # Step 6: Authentication successful!
        # Delete the challenge immediately (one-time use prevents replay attacks).
        del pending_challenges[username]

        # Step 7: Create a Flask session.
        #
        # Flask sessions use signed cookies (HMAC with app.secret_key).
        # The session data is serialized, signed, and stored in the cookie.
        # On each request, Flask verifies the signature to ensure the cookie
        # has not been tampered with.
        #
        # The session persists across requests until:
        #   - The user calls /api/auth/logout (session.clear())
        #   - The browser session ends (default: when browser closes)
        #   - The session cookie is deleted by the browser
        session["authenticated"] = True
        session["username"] = username
        session["auth_method"] = "hive_keychain"
        session["auth_time"] = int(time.time())

        return jsonify({
            "authenticated": True,
            "username": username,
        })

    except Exception as e:
        print(f"Verification error: {e}")
        return jsonify({"error": "Verification failed"}), 500


# ---------------------------------------------------------------------------
# Routes: Protected API
# ---------------------------------------------------------------------------


@app.route("/api/profile")
@require_auth
def get_profile():
    """
    Get the authenticated user's Hive profile data.

    This is a protected route -- requires a valid Flask session established
    by a successful Hive Keychain authentication.

    Demonstrates how to use the session after Keychain auth. The @require_auth
    decorator checks session["authenticated"] before allowing access.

    Response (JSON):
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
    """
    try:
        username = session["username"]
        account = get_hive_account(username)
        if not account:
            return jsonify({"error": "Account not found"}), 404

        # Parse the JSON metadata to extract profile information.
        #
        # Hive stores profile data (display name, bio, avatar URL, etc.)
        # in the posting_json_metadata field as a JSON string.
        # The standard structure is:
        #   { "profile": { "name": "...", "about": "...", "profile_image": "...", ... } }
        #
        # This metadata is set by Hive frontends (PeakD, Ecency, Hive.blog)
        # when the user updates their profile settings.
        profile = {}
        try:
            meta = json.loads(account.get("posting_json_metadata", "{}") or "{}")
            profile = meta.get("profile", {})
        except (json.JSONDecodeError, TypeError):
            # Metadata might not be valid JSON -- that is fine, just use defaults
            pass

        return jsonify({
            "username": account["name"],
            "profile": {
                "name": profile.get("name", account["name"]),
                "about": profile.get("about", ""),
                "location": profile.get("location", ""),
                "website": profile.get("website", ""),
                "profile_image": profile.get("profile_image", ""),
                "cover_image": profile.get("cover_image", ""),
            },
            "reputation": account.get("reputation", 0),
            "post_count": account.get("post_count", 0),
            "created": account.get("created", ""),
            "balance": str(account.get("balance", "0.000 HIVE")),
            "hbd_balance": str(account.get("hbd_balance", "0.000 HBD")),
            "vesting_shares": str(account.get("vesting_shares", "0.000000 VESTS")),
        })

    except Exception as e:
        print(f"Profile fetch error: {e}")
        return jsonify({"error": "Failed to fetch profile"}), 500


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    """
    Log out the current user by clearing the Flask session.

    This removes all session data. The signed session cookie becomes
    empty, effectively logging the user out. The user will need to
    re-authenticate with Keychain to access protected routes.
    """
    session.clear()
    return jsonify({"message": "Logged out successfully"})


@app.route("/api/auth/status")
def auth_status():
    """
    Check the current authentication status.

    Useful for the frontend to determine if the user is still logged in
    on page refresh or tab restore. No Keychain interaction is needed --
    this just checks the server-side session.

    Response (JSON):
        { "authenticated": true, "username": "alice" }
        or
        { "authenticated": false }
    """
    if session.get("authenticated"):
        return jsonify({
            "authenticated": True,
            "username": session["username"],
        })
    return jsonify({"authenticated": False})


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Hive Keychain Authentication Server (Python / Flask)")
    print("=" * 60)
    print(f"  Hive node:  {HIVE_NODE}")
    print(f"  Port:       {PORT}")
    print(f"  beem:       {'installed' if BEEM_AVAILABLE else 'NOT INSTALLED'}")
    if not BEEM_AVAILABLE:
        print("")
        print("  WARNING: Signature verification requires beem.")
        print("  Install it: pip install beem>=0.24")
    print("=" * 60)
    print(f"  Open http://localhost:{PORT} in your browser")
    print("  Make sure Hive Keychain extension is installed")
    print("=" * 60)

    # debug=True enables auto-reload on code changes and detailed error pages.
    # NEVER use debug=True in production -- it exposes a debugger that can
    # execute arbitrary Python code.
    app.run(host="0.0.0.0", port=PORT, debug=True)
