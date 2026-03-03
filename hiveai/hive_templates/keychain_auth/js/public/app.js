/**
 * HIVE KEYCHAIN FRONTEND APPLICATION
 * ====================================
 *
 * This file handles all frontend interactions with the Hive Keychain browser
 * extension. It is a complete tutorial-style reference for building dapps
 * that authenticate users via Hive Keychain and perform on-chain operations.
 *
 * TABLE OF CONTENTS
 * ------------------
 * 1. Keychain Detection
 * 2. Challenge-Response Authentication (Login)
 * 3. Profile Management
 * 4. Post-Auth Operations:
 *    a. requestBroadcast — Post content to the Hive blockchain
 *    b. requestTransfer  — Send HIVE/HBD tokens
 *    c. requestVote       — Upvote/downvote content
 *    d. requestDelegation — Delegate Hive Power
 *
 * HIVE KEY HIERARCHY (CRITICAL TO UNDERSTAND)
 * =============================================
 *
 * Every Hive account has FOUR key pairs, each with different permission levels:
 *
 *   1. OWNER KEY (highest privilege)
 *      - Can change ALL other keys
 *      - Can recover the account
 *      - Should be kept offline / in cold storage
 *      - Hive Keychain will show a RED warning when this key is requested
 *
 *   2. ACTIVE KEY (financial operations)
 *      - Required for: transfers, power-ups/power-downs, witness votes,
 *        market orders, account updates (non-owner)
 *      - This is the "wallet" key
 *      - Keychain shows an ORANGE warning for active key operations
 *
 *   3. POSTING KEY (social operations) <-- Used for authentication
 *      - Required for: publishing posts, voting, reblogging, following,
 *        custom_json for dapps (Splinterlands, dBuzz, etc.)
 *      - This is the SAFEST key to use for login because:
 *        * It cannot move funds
 *        * It cannot change account settings
 *        * Worst case if compromised: someone posts/votes on your behalf
 *      - Keychain shows a GREEN indicator for posting operations
 *
 *   4. MEMO KEY (message encryption)
 *      - Used to encrypt/decrypt private messages (transfer memos)
 *      - Not used for signing transactions
 *
 * WHY KEYCHAIN NEVER EXPOSES PRIVATE KEYS
 * ==========================================
 * The browser extension stores encrypted keys locally. When a dapp calls
 * requestSignBuffer() or requestBroadcast(), Keychain:
 *   1. Shows the user exactly what will be signed/broadcast
 *   2. Waits for user approval
 *   3. Signs the data internally using the private key
 *   4. Returns ONLY the signature (never the private key)
 *
 * The dapp never sees, touches, or has access to the private key.
 * This is fundamentally more secure than password-based auth.
 */

// =============================================================================
// CONFIGURATION
// =============================================================================

/** Base URL for our backend API. Defaults to same-origin. */
const API_BASE = window.location.origin;

/**
 * How long to wait for Keychain to inject window.hive_keychain (ms).
 * Extensions load asynchronously, so we need a grace period.
 */
const KEYCHAIN_DETECT_DELAY_MS = 1500;

// =============================================================================
// 1. KEYCHAIN DETECTION
// =============================================================================

/**
 * Check if Hive Keychain browser extension is installed and available.
 *
 * HOW IT WORKS:
 * Hive Keychain injects a global `window.hive_keychain` object into every
 * webpage when the extension is active. This object exposes all Keychain
 * API methods (requestSignBuffer, requestBroadcast, etc.).
 *
 * TIMING ISSUE:
 * Browser extensions inject their content scripts asynchronously. The
 * window.hive_keychain object might not exist when our script first runs
 * but will appear a few hundred milliseconds later. We handle this by:
 *   1. Checking immediately on DOMContentLoaded
 *   2. Checking again after a 1-1.5 second delay
 *   3. Allowing login attempts even if detection fails (user may install
 *      the extension while the page is open)
 *
 * @returns {boolean} true if Keychain is detected
 */
function checkKeychain() {
    // window.hive_keychain is injected by the Hive Keychain browser extension.
    // If it exists, the extension is installed and active.
    if (typeof window.hive_keychain === "undefined") {
        document.getElementById("keychain-warning").style.display = "block";
        document.getElementById("login-btn").title =
            "Hive Keychain not detected — please install the extension";
        return false;
    }
    document.getElementById("keychain-warning").style.display = "none";
    document.getElementById("login-btn").title = "";
    return true;
}

/**
 * Check if Keychain supports a specific method.
 * Useful for feature detection on older Keychain versions.
 *
 * @param {string} methodName - e.g. "requestSignBuffer", "requestBroadcast"
 * @returns {boolean}
 */
function keychainSupports(methodName) {
    return (
        typeof window.hive_keychain !== "undefined" &&
        typeof window.hive_keychain[methodName] === "function"
    );
}

// =============================================================================
// 2. STATUS DISPLAY HELPERS
// =============================================================================

/**
 * Show a status message to the user.
 * @param {string} message - Text to display
 * @param {string} type - "error", "success", or "info"
 */
function showStatus(message, type) {
    const status = document.getElementById("status");
    status.textContent = message;
    status.className = "status " + type;
}

/** Clear the status display */
function clearStatus() {
    const status = document.getElementById("status");
    status.className = "status";
    status.textContent = "";
}

/**
 * Show a status message in the operations panel (post-auth area).
 * @param {string} message - Text to display
 * @param {string} type - "error", "success", or "info"
 */
function showOpsStatus(message, type) {
    const status = document.getElementById("ops-status");
    if (!status) return;
    status.textContent = message;
    status.className = "status " + type;
}

/** Clear the operations status display */
function clearOpsStatus() {
    const status = document.getElementById("ops-status");
    if (!status) return;
    status.className = "status";
    status.textContent = "";
}

// =============================================================================
// 3. CHALLENGE-RESPONSE AUTHENTICATION (LOGIN)
// =============================================================================

/**
 * Perform the full Hive Keychain login flow.
 *
 * THE CHALLENGE-RESPONSE PATTERN:
 * ================================
 *
 * This is the standard authentication pattern for Hive dapps. It works like this:
 *
 * Step 1: Frontend requests a CHALLENGE from the backend.
 *         The challenge is a unique, random string that includes:
 *         - The username (ties it to one account)
 *         - Random bytes (prevents prediction/replay)
 *         - A timestamp (enables expiration)
 *         Example: "hive-auth:alice:a7f3b2c1d4e5....:1709000000000"
 *
 * Step 2: Frontend asks Hive Keychain to SIGN the challenge.
 *         Keychain.requestSignBuffer(username, challenge, "Posting", callback)
 *         - Keychain pops up showing the challenge text
 *         - User approves or denies
 *         - If approved, Keychain signs the challenge with the PRIVATE posting key
 *         - Returns a 65-byte hex signature (recovery_id + r + s)
 *         - The private key NEVER leaves Keychain
 *
 * Step 3: Frontend sends (username, challenge, signature) to the backend.
 *
 * Step 4: Backend VERIFIES the signature:
 *         - Hashes the challenge with SHA-256 (same as Keychain did)
 *         - Fetches the user's PUBLIC posting key from the Hive blockchain
 *         - Verifies the signature was produced by the corresponding private key
 *         - If valid, the user has proven they control this Hive account
 *
 * Step 5: Backend issues a JWT for session management.
 *         Subsequent API calls use this JWT instead of re-signing.
 *
 * WHY THIS IS SECURE:
 * - Challenge is random and single-use (prevents replay attacks)
 * - Challenge expires after 5 minutes (prevents stale reuse)
 * - Private key never leaves the extension (no key exposure)
 * - Verification uses on-chain public key (trustless, no password database)
 * - Posting key is lowest privilege (cannot move funds if compromised)
 */
async function login() {
    clearStatus();

    // Check Keychain availability before attempting login
    if (!checkKeychain()) {
        showStatus(
            "Hive Keychain extension is not installed. Please install it from hive-keychain.com",
            "error"
        );
        return;
    }

    // Get and sanitize the username
    const usernameInput = document.getElementById("username");
    const username = usernameInput.value.trim().toLowerCase();

    // Hive usernames: 3-16 chars, lowercase letters, numbers, dots, hyphens
    if (!username) {
        showStatus("Please enter your Hive username.", "error");
        return;
    }

    // Basic Hive username validation (3-16 chars, alphanumeric + dots/hyphens)
    if (!/^[a-z][a-z0-9\-\.]{2,15}$/.test(username)) {
        showStatus(
            "Invalid Hive username format. Usernames are 3-16 characters: lowercase letters, numbers, dots, hyphens.",
            "error"
        );
        return;
    }

    // Disable the button to prevent double-clicks
    const loginBtn = document.getElementById("login-btn");
    loginBtn.disabled = true;
    loginBtn.textContent = "Authenticating...";

    try {
        // =====================================================================
        // STEP 1: Request a challenge from the server
        // =====================================================================
        showStatus("Requesting authentication challenge...", "info");

        const challengeRes = await fetch(`${API_BASE}/api/auth/challenge`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username }),
        });

        const challengeData = await challengeRes.json();

        if (!challengeRes.ok) {
            throw new Error(challengeData.error || "Failed to get challenge");
        }

        // The challenge string looks like: "hive-auth:alice:a7f3b2c1d4e5...:1709000000000"
        const challenge = challengeData.challenge;

        // =====================================================================
        // STEP 2: Ask Hive Keychain to sign the challenge
        // =====================================================================
        //
        // window.hive_keychain.requestSignBuffer(account, message, key_type, callback)
        //
        // Parameters:
        //   account   {string}   - The Hive username whose key should sign
        //   message   {string}   - The raw string to sign (our challenge)
        //   key_type  {string}   - "Posting", "Active", or "Memo"
        //                          We use "Posting" — the LEAST privileged key.
        //                          Never request Active/Owner for mere authentication.
        //   callback  {function} - Called with the result object:
        //     On success: { success: true, result: "20abcdef...", publicKey: "STM..." }
        //       - result: 65-byte hex signature (1 byte recovery + 32 byte r + 32 byte s)
        //       - publicKey: the public key used (useful for multi-key accounts)
        //     On failure: { success: false, error: "user_cancel" | "missing_key" | ... }
        //       - "user_cancel": user clicked Cancel in the Keychain popup
        //       - "missing_key": account not in Keychain or wrong key type
        //
        // WHAT THE USER SEES:
        // Keychain pops up a dialog showing:
        //   "Sign this message with your Posting key?"
        //   Message: hive-auth:alice:a7f3b2c1d4e5...:1709000000000
        //   [Confirm] [Cancel]
        //
        // The user can read the challenge and verify it is benign before approving.
        showStatus("Waiting for Keychain approval...", "info");

        const signResult = await new Promise((resolve, reject) => {
            // Set a timeout in case Keychain hangs or user walks away
            const timeout = setTimeout(() => {
                reject(
                    new Error(
                        "Keychain signing timed out after 2 minutes. Please try again."
                    )
                );
            }, 120000);

            window.hive_keychain.requestSignBuffer(
                username, // Hive account to sign with
                challenge, // The challenge string to sign
                "Posting", // Key type — always use Posting for authentication
                (response) => {
                    clearTimeout(timeout);

                    if (response.success) {
                        // response.result contains the hex-encoded signature
                        resolve(response);
                    } else {
                        // Common errors:
                        //   "user_cancel" — user clicked Cancel
                        //   "missing_key" — this account's posting key isn't in Keychain
                        //   "no_account" — username not found in Keychain
                        let errorMsg = response.error || "Keychain signing failed";
                        if (
                            response.error === "user_cancel" ||
                            response.message === "Request was canceled by the user."
                        ) {
                            errorMsg = "You cancelled the signing request.";
                        }
                        reject(new Error(errorMsg));
                    }
                }
            );
        });

        // =====================================================================
        // STEP 3: Send the signature to the server for verification
        // =====================================================================
        showStatus("Verifying signature with the blockchain...", "info");

        const verifyRes = await fetch(`${API_BASE}/api/auth/verify`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username,
                challenge,
                // signResult.result is the 65-byte hex signature from Keychain
                signature: signResult.result,
            }),
        });

        const verifyData = await verifyRes.json();

        if (!verifyRes.ok) {
            throw new Error(verifyData.error || "Signature verification failed");
        }

        // =====================================================================
        // STEP 4: Store the JWT and load the authenticated UI
        // =====================================================================
        //
        // After successful verification, the server returns a JWT.
        // We store it in localStorage for subsequent API calls.
        //
        // SECURITY NOTE: localStorage is accessible to all JS on this origin.
        // For higher-security apps, consider:
        //   - httpOnly cookies (immune to XSS)
        //   - sessionStorage (cleared on tab close)
        //   - In-memory only (cleared on page refresh)
        localStorage.setItem("hive_jwt", verifyData.token);
        localStorage.setItem("hive_username", verifyData.username);

        showStatus("Authentication successful!", "success");

        // Load the user's profile from the protected API
        await fetchProfile(verifyData.token);
    } catch (err) {
        showStatus(err.message, "error");
    } finally {
        loginBtn.disabled = false;
        loginBtn.textContent = "Sign in with Keychain";
    }
}

// =============================================================================
// 4. PROFILE MANAGEMENT
// =============================================================================

/**
 * Fetch and display the authenticated user's Hive profile.
 *
 * This demonstrates using the JWT for authenticated API calls.
 * The token is sent in the Authorization header as a Bearer token:
 *   Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
 *
 * @param {string} token - The JWT issued after successful auth
 */
async function fetchProfile(token) {
    try {
        const res = await fetch(`${API_BASE}/api/profile`, {
            headers: {
                // Standard Bearer token authentication
                // The server's requireAuth middleware validates this JWT
                Authorization: `Bearer ${token}`,
            },
        });

        if (!res.ok) {
            if (res.status === 401) {
                // JWT expired or invalid — clear session and show login
                localStorage.removeItem("hive_jwt");
                localStorage.removeItem("hive_username");
                showLoginUI();
                return;
            }
            throw new Error("Failed to fetch profile");
        }

        const profile = await res.json();

        // Switch from login view to authenticated view
        showAuthenticatedUI(profile);
    } catch (err) {
        console.error("Profile fetch error:", err);
        localStorage.removeItem("hive_jwt");
        localStorage.removeItem("hive_username");
        showLoginUI();
    }
}

/**
 * Show the login UI and hide the authenticated sections.
 */
function showLoginUI() {
    document.getElementById("login-section").style.display = "block";
    document.getElementById("profile-section").style.display = "none";
    const opsSection = document.getElementById("operations-section");
    if (opsSection) opsSection.style.display = "none";
}

/**
 * Show the authenticated UI with profile data and operations panel.
 * @param {object} profile - User profile data from the API
 */
function showAuthenticatedUI(profile) {
    // Hide login section
    document.getElementById("login-section").style.display = "none";

    // Show profile card
    const profileSection = document.getElementById("profile-section");
    profileSection.style.display = "block";

    // Profile image (from Hive JSON metadata)
    const img = document.getElementById("profile-image");
    if (profile.profile && profile.profile.profile_image) {
        img.src = profile.profile.profile_image;
        img.style.display = "block";
    } else {
        img.style.display = "none";
    }

    // Display name: @username (Display Name)
    document.getElementById("profile-name").textContent =
        `@${profile.username}` +
        (profile.profile && profile.profile.name
            ? ` (${profile.profile.name})`
            : "");

    // Build profile details rows
    const details = document.getElementById("profile-details");
    const rows = [
        ["About", profile.profile ? profile.profile.about : ""],
        ["Location", profile.profile ? profile.profile.location : ""],
        ["Website", profile.profile ? profile.profile.website : ""],
        ["Posts", profile.post_count],
        ["HIVE Balance", profile.balance],
        ["HBD Balance", profile.hbd_balance],
        ["Account Created", profile.created ? new Date(profile.created).toLocaleDateString() : ""],
    ];

    details.innerHTML = rows
        .filter(([, value]) => value)
        .map(
            ([label, value]) => `
            <div class="profile-row">
                <span class="label">${label}</span>
                <span class="value">${value}</span>
            </div>
        `
        )
        .join("");

    // Show operations section (post-auth Keychain interactions)
    const opsSection = document.getElementById("operations-section");
    if (opsSection) opsSection.style.display = "block";
}

// =============================================================================
// 5. LOGOUT
// =============================================================================

/**
 * Log out: clear the JWT and switch back to the login view.
 *
 * NOTE: There is no server-side session to invalidate with JWT.
 * The token will remain valid until it expires (24h by default).
 * For stricter security, implement a server-side token blacklist.
 */
function logout() {
    localStorage.removeItem("hive_jwt");
    localStorage.removeItem("hive_username");
    showLoginUI();
    clearStatus();
    clearOpsStatus();
    document.getElementById("username").value = "";
}

// =============================================================================
// 6. POST-AUTH KEYCHAIN OPERATIONS
// =============================================================================

// These operations require the user to be logged in and will prompt
// Keychain for approval each time. The JWT authenticates with our server,
// but on-chain operations still need Keychain signatures.

/**
 * BROADCAST A HIVE POST USING KEYCHAIN
 * ======================================
 *
 * window.hive_keychain.requestBroadcast(account, operations, key_type, callback)
 *
 * This method broadcasts a transaction to the Hive blockchain. A transaction
 * contains one or more "operations" (the Hive equivalent of smart contract calls).
 *
 * Parameters:
 *   account    {string}   - The Hive username broadcasting the transaction
 *   operations {array}    - Array of [operation_name, operation_data] pairs
 *   key_type   {string}   - "Posting" or "Active" (depends on the operation)
 *   callback   {function} - Result handler
 *
 * COMMON OPERATIONS AND THEIR KEY REQUIREMENTS:
 *
 *   Posting Key:
 *     - "comment"         — Create a post or reply
 *     - "vote"            — Upvote or downvote
 *     - "custom_json"     — dapp-specific data (games, social actions)
 *     - "delete_comment"  — Delete a post/reply
 *
 *   Active Key:
 *     - "transfer"        — Send HIVE/HBD (use requestTransfer instead)
 *     - "delegate_vesting_shares" — Delegate HP
 *     - "transfer_to_vesting"     — Power up HIVE to HP
 *     - "withdraw_vesting"        — Power down HP to HIVE
 *
 * WHAT THE USER SEES:
 * Keychain shows the full transaction details before the user confirms.
 * For a post, they see: author, title, body, parent_author, parent_permlink.
 * This transparency is why Keychain is trusted by the community.
 */
async function publishPost() {
    if (!checkKeychain()) {
        showOpsStatus("Keychain not available.", "error");
        return;
    }

    const username = localStorage.getItem("hive_username");
    if (!username) {
        showOpsStatus("You must be logged in to post.", "error");
        return;
    }

    // Get post data from the form
    const title = document.getElementById("post-title")
        ? document.getElementById("post-title").value.trim()
        : "";
    const body = document.getElementById("post-body")
        ? document.getElementById("post-body").value.trim()
        : "";

    if (!title || !body) {
        showOpsStatus("Title and body are required.", "error");
        return;
    }

    // Generate a URL-safe permlink from the title
    // Hive permlinks are lowercase, alphanumeric + hyphens, max ~256 chars
    const permlink =
        title
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-|-$/g, "")
            .substring(0, 200) +
        "-" +
        Date.now().toString(36);

    // The "comment" operation is used for BOTH posts and replies on Hive.
    //
    // For a TOP-LEVEL POST:
    //   parent_author  = ""  (empty string means this is a root post)
    //   parent_permlink = the community/category (like a subreddit)
    //   author         = the poster's username
    //   permlink       = unique URL slug for this post
    //   title          = post title
    //   body           = post content (Markdown supported)
    //   json_metadata  = JSON string with tags, app name, format, etc.
    //
    // For a REPLY to another post:
    //   parent_author  = the original post's author
    //   parent_permlink = the original post's permlink
    //   title          = "" (replies have no title)
    //   body           = reply content
    const operations = [
        [
            "comment",
            {
                parent_author: "", // Empty = top-level post (not a reply)
                parent_permlink: "hive-keychain", // Category/community
                author: username,
                permlink: permlink,
                title: title,
                body: body,
                json_metadata: JSON.stringify({
                    // Tags help with content discovery on Hive frontends
                    tags: ["hive-keychain", "tutorial", "development"],
                    // The app field identifies which dapp created this post
                    app: "hive-keychain-auth-template/1.0.0",
                    // Format tells frontends how to render the body
                    format: "markdown",
                }),
            },
        ],
    ];

    showOpsStatus("Waiting for Keychain to approve the post...", "info");

    try {
        const result = await new Promise((resolve, reject) => {
            // requestBroadcast sends a full Hive transaction
            // "Posting" key is used because "comment" is a posting-level operation
            window.hive_keychain.requestBroadcast(
                username, // Account broadcasting the transaction
                operations, // Array of operations to include in the transaction
                "Posting", // Key type — "comment" needs Posting authority
                (response) => {
                    if (response.success) {
                        resolve(response);
                    } else {
                        reject(
                            new Error(response.error || response.message || "Broadcast failed")
                        );
                    }
                }
            );
        });

        // result.result contains the transaction details including block number
        showOpsStatus(
            `Post published successfully! Transaction: ${result.result.id || "confirmed"}`,
            "success"
        );
    } catch (err) {
        showOpsStatus(`Post failed: ${err.message}`, "error");
    }
}

/**
 * SEND HIVE/HBD TOKENS USING KEYCHAIN
 * ======================================
 *
 * window.hive_keychain.requestTransfer(from, to, amount, memo, currency, callback)
 *
 * This is a convenience method specifically for token transfers. Keychain shows
 * a clear, dedicated transfer confirmation dialog (not the generic broadcast UI).
 *
 * Parameters:
 *   from     {string}   - Sender's Hive username
 *   to       {string}   - Recipient's Hive username
 *   amount   {string}   - Amount to send (e.g., "1.000" — exactly 3 decimal places)
 *   memo     {string}   - Transfer memo (public unless encrypted with memo key)
 *   currency {string}   - "HIVE" or "HBD" (Hive Backed Dollars)
 *   callback {function} - Result handler
 *
 * IMPORTANT NOTES:
 *   - This uses the ACTIVE key (not Posting) because transfers are financial
 *   - Amount MUST have exactly 3 decimal places (e.g., "1.000" not "1")
 *   - Memo is PUBLIC on the blockchain unless prefixed with # (then it's
 *     encrypted with the recipient's memo key)
 *   - Minimum transfer is 0.001 HIVE/HBD
 *
 * WHAT THE USER SEES:
 * Keychain shows a transfer confirmation:
 *   "Send 1.000 HIVE to @bob?"
 *   Memo: "Thanks for the tutorial!"
 *   [Confirm] [Cancel]
 *
 * The user can clearly see where their tokens are going before approving.
 */
async function sendTransfer() {
    if (!checkKeychain()) {
        showOpsStatus("Keychain not available.", "error");
        return;
    }

    const username = localStorage.getItem("hive_username");
    if (!username) {
        showOpsStatus("You must be logged in to transfer.", "error");
        return;
    }

    // Get transfer details from the form
    const recipient = document.getElementById("transfer-to")
        ? document.getElementById("transfer-to").value.trim().toLowerCase()
        : "";
    const amountRaw = document.getElementById("transfer-amount")
        ? document.getElementById("transfer-amount").value.trim()
        : "";
    const memo = document.getElementById("transfer-memo")
        ? document.getElementById("transfer-memo").value.trim()
        : "";
    const currency = document.getElementById("transfer-currency")
        ? document.getElementById("transfer-currency").value
        : "HIVE";

    if (!recipient || !amountRaw) {
        showOpsStatus("Recipient and amount are required.", "error");
        return;
    }

    // Hive requires exactly 3 decimal places for token amounts
    const amount = parseFloat(amountRaw).toFixed(3);
    if (isNaN(parseFloat(amountRaw)) || parseFloat(amount) <= 0) {
        showOpsStatus("Please enter a valid positive amount.", "error");
        return;
    }

    showOpsStatus(
        `Requesting transfer of ${amount} ${currency} to @${recipient}...`,
        "info"
    );

    try {
        const result = await new Promise((resolve, reject) => {
            window.hive_keychain.requestTransfer(
                username, // From: sender's Hive username
                recipient, // To: recipient's Hive username
                amount, // Amount: must be string with 3 decimal places
                memo, // Memo: public text (prefix with # for encrypted)
                currency, // Currency: "HIVE" or "HBD"
                (response) => {
                    if (response.success) {
                        resolve(response);
                    } else {
                        reject(
                            new Error(
                                response.error || response.message || "Transfer failed"
                            )
                        );
                    }
                }
            );
        });

        showOpsStatus(
            `Sent ${amount} ${currency} to @${recipient} successfully!`,
            "success"
        );
    } catch (err) {
        showOpsStatus(`Transfer failed: ${err.message}`, "error");
    }
}

/**
 * VOTE ON CONTENT USING KEYCHAIN
 * ================================
 *
 * Voting on Hive is done via the "vote" operation in a requestBroadcast call.
 *
 * The vote operation fields:
 *   voter    {string} - The account casting the vote
 *   author   {string} - The author of the post/comment being voted on
 *   permlink {string} - The permlink of the post/comment
 *   weight   {number} - Vote weight from -10000 to 10000
 *                        10000 = 100% upvote
 *                        -10000 = 100% downvote
 *                        0 = remove vote
 *
 * WHAT IS VOTE WEIGHT?
 * Hive allows partial votes. A 50% upvote (weight=5000) uses half the
 * voting power compared to a 100% upvote. Voting power regenerates at
 * ~20% per day. Heavy voters need to manage their voting power carefully.
 *
 * Uses the POSTING key (voting is a social action, not financial).
 */
async function voteOnContent() {
    if (!checkKeychain()) {
        showOpsStatus("Keychain not available.", "error");
        return;
    }

    const username = localStorage.getItem("hive_username");
    if (!username) {
        showOpsStatus("You must be logged in to vote.", "error");
        return;
    }

    const author = document.getElementById("vote-author")
        ? document.getElementById("vote-author").value.trim().toLowerCase()
        : "";
    const permlink = document.getElementById("vote-permlink")
        ? document.getElementById("vote-permlink").value.trim()
        : "";
    const weightPercent = document.getElementById("vote-weight")
        ? parseInt(document.getElementById("vote-weight").value, 10)
        : 100;

    if (!author || !permlink) {
        showOpsStatus("Author and permlink are required.", "error");
        return;
    }

    // Convert percentage (1-100) to Hive weight (100-10000)
    const weight = Math.min(10000, Math.max(-10000, weightPercent * 100));

    const operations = [
        [
            "vote",
            {
                voter: username,
                author: author,
                permlink: permlink,
                weight: weight, // 10000 = 100% upvote, -10000 = 100% downvote
            },
        ],
    ];

    showOpsStatus("Waiting for Keychain to approve the vote...", "info");

    try {
        const result = await new Promise((resolve, reject) => {
            window.hive_keychain.requestBroadcast(
                username,
                operations,
                "Posting", // Voting requires Posting authority
                (response) => {
                    if (response.success) {
                        resolve(response);
                    } else {
                        reject(
                            new Error(response.error || response.message || "Vote failed")
                        );
                    }
                }
            );
        });

        showOpsStatus(
            `Vote of ${weightPercent}% on @${author}/${permlink} confirmed!`,
            "success"
        );
    } catch (err) {
        showOpsStatus(`Vote failed: ${err.message}`, "error");
    }
}

/**
 * DELEGATE HIVE POWER USING KEYCHAIN
 * ====================================
 *
 * window.hive_keychain.requestDelegation(username, delegatee, amount, unit, callback)
 *
 * Hive Power (HP) delegation lets you lend your voting influence to another
 * account without transferring ownership. The delegator can undelegate at
 * any time (with a 5-day cooldown).
 *
 * Parameters:
 *   username  {string} - The account delegating HP
 *   delegatee {string} - The account receiving the delegation
 *   amount    {string} - Amount to delegate
 *   unit      {string} - "HP" (Hive Power) or "VESTS" (raw vesting shares)
 *   callback  {function}
 *
 * Uses ACTIVE key (delegation is considered a financial operation).
 *
 * WHAT IS HIVE POWER?
 * HIVE can be "powered up" into Hive Power (HP), which gives:
 *   - Voting influence (your upvotes/downvotes affect post rewards)
 *   - Resource Credits (bandwidth to transact on the blockchain)
 *   - Governance power (witness votes)
 * HP powers down over 13 weeks if you want to convert back to liquid HIVE.
 */
async function delegateHP() {
    if (!checkKeychain()) {
        showOpsStatus("Keychain not available.", "error");
        return;
    }

    const username = localStorage.getItem("hive_username");
    if (!username) {
        showOpsStatus("You must be logged in to delegate.", "error");
        return;
    }

    const delegatee = document.getElementById("delegate-to")
        ? document.getElementById("delegate-to").value.trim().toLowerCase()
        : "";
    const amount = document.getElementById("delegate-amount")
        ? document.getElementById("delegate-amount").value.trim()
        : "";

    if (!delegatee || !amount) {
        showOpsStatus("Delegatee and amount are required.", "error");
        return;
    }

    showOpsStatus(
        `Requesting delegation of ${amount} HP to @${delegatee}...`,
        "info"
    );

    try {
        const result = await new Promise((resolve, reject) => {
            window.hive_keychain.requestDelegation(
                username, // From: delegator
                delegatee, // To: delegatee
                amount, // Amount of HP to delegate
                "HP", // Unit: "HP" or "VESTS"
                (response) => {
                    if (response.success) {
                        resolve(response);
                    } else {
                        reject(
                            new Error(
                                response.error ||
                                    response.message ||
                                    "Delegation failed"
                            )
                        );
                    }
                }
            );
        });

        showOpsStatus(
            `Delegated ${amount} HP to @${delegatee} successfully!`,
            "success"
        );
    } catch (err) {
        showOpsStatus(`Delegation failed: ${err.message}`, "error");
    }
}

/**
 * CUSTOM JSON — THE DAPP SWISS ARMY KNIFE
 * ==========================================
 *
 * custom_json is the most versatile operation on Hive. It lets dapps store
 * arbitrary JSON data on the blockchain. This is how:
 *   - Splinterlands processes game actions
 *   - dBuzz stores short-form posts
 *   - PeakD stores user preferences
 *   - Hive-Engine sidechain tokens are transferred
 *
 * The operation fields:
 *   required_auths         - accounts that must sign with Active key
 *   required_posting_auths - accounts that must sign with Posting key
 *   id                     - a string identifier for your dapp (e.g., "splinterlands")
 *   json                   - your custom JSON payload (stringified)
 *
 * By convention, use "required_posting_auths" for social/game actions
 * and "required_auths" for financial actions. Using posting auth means
 * users only need their posting key, which is safer.
 */
async function broadcastCustomJson() {
    if (!checkKeychain()) {
        showOpsStatus("Keychain not available.", "error");
        return;
    }

    const username = localStorage.getItem("hive_username");
    if (!username) {
        showOpsStatus("You must be logged in.", "error");
        return;
    }

    const customId = document.getElementById("custom-json-id")
        ? document.getElementById("custom-json-id").value.trim()
        : "my-dapp";
    const customData = document.getElementById("custom-json-data")
        ? document.getElementById("custom-json-data").value.trim()
        : "{}";

    // Validate JSON
    try {
        JSON.parse(customData);
    } catch {
        showOpsStatus("Invalid JSON data. Please check the format.", "error");
        return;
    }

    const operations = [
        [
            "custom_json",
            {
                required_auths: [], // Empty — we are NOT using Active key
                required_posting_auths: [username], // Using Posting key
                id: customId, // Your dapp's unique identifier string
                json: customData, // The JSON payload (must be a string)
            },
        ],
    ];

    showOpsStatus("Waiting for Keychain to approve custom_json...", "info");

    try {
        const result = await new Promise((resolve, reject) => {
            window.hive_keychain.requestBroadcast(
                username,
                operations,
                "Posting", // Posting key because we used required_posting_auths
                (response) => {
                    if (response.success) {
                        resolve(response);
                    } else {
                        reject(
                            new Error(
                                response.error ||
                                    response.message ||
                                    "Custom JSON broadcast failed"
                            )
                        );
                    }
                }
            );
        });

        showOpsStatus("Custom JSON broadcast confirmed!", "success");
    } catch (err) {
        showOpsStatus(`Custom JSON failed: ${err.message}`, "error");
    }
}

// =============================================================================
// 7. INITIALIZATION
// =============================================================================

/**
 * Initialize the app on page load.
 */
document.addEventListener("DOMContentLoaded", () => {
    // Check for Keychain immediately
    checkKeychain();

    // Check again after a delay (extension injection timing)
    setTimeout(checkKeychain, KEYCHAIN_DETECT_DELAY_MS);

    // Check for an existing session (JWT in localStorage)
    const token = localStorage.getItem("hive_jwt");
    if (token) {
        // Attempt to restore the session by fetching the profile
        fetchProfile(token);
    }

    // Allow Enter key to trigger login
    const usernameInput = document.getElementById("username");
    if (usernameInput) {
        usernameInput.addEventListener("keypress", (e) => {
            if (e.key === "Enter") login();
        });
    }

    // Set up tab switching for operations panel
    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            // Deactivate all tabs and panels
            document
                .querySelectorAll(".tab-btn")
                .forEach((b) => b.classList.remove("active"));
            document
                .querySelectorAll(".tab-panel")
                .forEach((p) => (p.style.display = "none"));

            // Activate the clicked tab and its panel
            btn.classList.add("active");
            const panel = document.getElementById(btn.dataset.tab);
            if (panel) panel.style.display = "block";

            clearOpsStatus();
        });
    });
});
