/**
 * HIVE KEYCHAIN FRONTEND APPLICATION (Flask / Session-based version)
 * ===================================================================
 *
 * This file handles all frontend interactions with the Hive Keychain browser
 * extension. It is a complete tutorial-style reference for building dapps
 * that authenticate users via Hive Keychain and perform on-chain operations.
 *
 * DIFFERENCE FROM THE NODE.JS VERSION:
 * This version uses Flask server-side sessions (signed cookies) instead of
 * JWTs stored in localStorage. Key differences:
 *
 *   - No JWT token is stored in localStorage (less XSS exposure)
 *   - The session cookie is HttpOnly (not accessible to JavaScript)
 *   - The session cookie is SameSite=Lax (CSRF protection)
 *   - All fetch() calls include credentials: "include" to send the cookie
 *   - Session validity is checked via GET /api/auth/status
 *   - Logout calls POST /api/auth/logout to clear the server-side session
 *
 * TABLE OF CONTENTS
 * ------------------
 * 1. Keychain Detection
 * 2. Challenge-Response Authentication (Login)
 * 3. Profile Management
 * 4. Post-Auth Operations:
 *    a. requestBroadcast -- Post content to the Hive blockchain
 *    b. requestTransfer  -- Send HIVE/HBD tokens
 *    c. requestVote      -- Upvote/downvote content
 *    d. requestDelegation -- Delegate Hive Power
 *    e. custom_json      -- Broadcast arbitrary dapp data
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

/** Base URL for the Flask backend API. Defaults to same-origin. */
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
    if (typeof window.hive_keychain === "undefined") {
        document.getElementById("keychain-warning").style.display = "block";
        return false;
    }
    document.getElementById("keychain-warning").style.display = "none";
    return true;
}

// =============================================================================
// 2. STATUS DISPLAY HELPERS
// =============================================================================

function showStatus(message, type) {
    const status = document.getElementById("status");
    status.textContent = message;
    status.className = "status " + type;
}

function clearStatus() {
    const status = document.getElementById("status");
    status.className = "status";
    status.textContent = "";
}

function showOpsStatus(message, type) {
    const status = document.getElementById("ops-status");
    if (!status) return;
    status.textContent = message;
    status.className = "status " + type;
}

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
 * FLASK SESSION VERSION:
 * Unlike the Node.js/JWT version, this flow uses Flask server-side sessions.
 * After successful signature verification, the Flask backend sets a signed
 * session cookie. All subsequent API calls send this cookie automatically
 * (via credentials: "include" in fetch options).
 *
 * THE CHALLENGE-RESPONSE PATTERN:
 *
 * Step 1: Frontend requests a CHALLENGE from the Flask backend.
 *         POST /api/auth/challenge { username: "alice" }
 *         Response: { challenge: "hive-auth:alice:random:timestamp" }
 *
 * Step 2: Frontend asks Hive Keychain to SIGN the challenge.
 *         Keychain.requestSignBuffer(username, challenge, "Posting", callback)
 *         Keychain pops up, user approves, returns 65-byte hex signature.
 *         The private key NEVER leaves Keychain.
 *
 * Step 3: Frontend sends (username, challenge, signature) to Flask.
 *         POST /api/auth/verify { username, challenge, signature }
 *
 * Step 4: Flask backend VERIFIES the signature using beem:
 *         - Hashes the challenge with SHA-256
 *         - Fetches the user's public posting key from the Hive blockchain
 *         - Uses beemgraphenebase.ecdsasig.verify_message() to recover the
 *           public key from the signature and compare it to the on-chain key
 *
 * Step 5: Flask creates a server-side session (signed cookie).
 *         Response: { authenticated: true, username: "alice" }
 *         Set-Cookie: session=<signed-data>; HttpOnly; SameSite=Lax
 */
async function login() {
    clearStatus();

    if (!checkKeychain()) {
        showStatus(
            "Hive Keychain extension is not installed. Please install it from hive-keychain.com",
            "error"
        );
        return;
    }

    const username = document.getElementById("username").value.trim().toLowerCase();
    if (!username) {
        showStatus("Please enter your Hive username.", "error");
        return;
    }

    // Hive username validation: 3-16 chars, starts with letter,
    // lowercase alphanumeric + dots + hyphens
    if (!/^[a-z][a-z0-9\-\.]{2,15}$/.test(username)) {
        showStatus(
            "Invalid Hive username format. Usernames are 3-16 characters: lowercase letters, numbers, dots, hyphens.",
            "error"
        );
        return;
    }

    const loginBtn = document.getElementById("login-btn");
    loginBtn.disabled = true;
    loginBtn.textContent = "Authenticating...";

    try {
        // =====================================================================
        // STEP 1: Request a challenge from the Flask server
        // =====================================================================
        showStatus("Requesting authentication challenge...", "info");

        const challengeRes = await fetch(`${API_BASE}/api/auth/challenge`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            // credentials: "include" sends the session cookie with the request.
            // This is needed for Flask sessions to work with CORS.
            credentials: "include",
            body: JSON.stringify({ username }),
        });

        const challengeData = await challengeRes.json();
        if (!challengeRes.ok) {
            throw new Error(challengeData.error || "Failed to get challenge");
        }

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
        //                          We use "Posting" -- the LEAST privileged key.
        //   callback  {function} - Called with the result object:
        //     Success: { success: true, result: "20abcdef...", publicKey: "STM..." }
        //     Failure: { success: false, error: "user_cancel" | "missing_key" | ... }
        showStatus("Waiting for Keychain approval...", "info");

        const signResult = await new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                reject(new Error("Keychain signing timed out after 2 minutes."));
            }, 120000);

            window.hive_keychain.requestSignBuffer(
                username,       // Hive account to sign with
                challenge,      // The challenge string to sign
                "Posting",      // Key type -- always Posting for authentication
                (response) => {
                    clearTimeout(timeout);
                    if (response.success) {
                        resolve(response);
                    } else {
                        let errorMsg = response.error || "Keychain signing failed";
                        if (response.error === "user_cancel" ||
                            response.message === "Request was canceled by the user.") {
                            errorMsg = "You cancelled the signing request.";
                        }
                        reject(new Error(errorMsg));
                    }
                }
            );
        });

        // =====================================================================
        // STEP 3: Send the signature to Flask for verification
        // =====================================================================
        showStatus("Verifying signature with the blockchain...", "info");

        const verifyRes = await fetch(`${API_BASE}/api/auth/verify`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            // credentials: "include" is CRITICAL here -- it tells the browser
            // to accept and store the Set-Cookie header from the Flask response.
            // Without this, the session cookie would be silently dropped.
            credentials: "include",
            body: JSON.stringify({
                username,
                challenge,
                signature: signResult.result,
            }),
        });

        const verifyData = await verifyRes.json();
        if (!verifyRes.ok) {
            throw new Error(verifyData.error || "Signature verification failed");
        }

        // =====================================================================
        // STEP 4: Session is now active -- load the authenticated UI
        // =====================================================================
        //
        // Unlike the JWT version, we do NOT store a token in localStorage.
        // The Flask session cookie is HttpOnly (JS cannot read it) and is
        // sent automatically with every request via credentials: "include".
        //
        // We store the username in localStorage purely for UI convenience
        // (showing "logged in as @alice" without an API call).
        localStorage.setItem("hive_username", verifyData.username);

        showStatus("Authentication successful!", "success");
        await fetchProfile();

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
 * Fetch the authenticated user's Hive profile from the protected API.
 *
 * FLASK SESSION NOTE:
 * The session cookie is sent automatically because we use credentials: "include".
 * The Flask @require_auth decorator checks session["authenticated"] on the server.
 * No explicit Authorization header is needed (unlike the JWT version).
 */
async function fetchProfile() {
    try {
        const res = await fetch(`${API_BASE}/api/profile`, {
            // credentials: "include" sends the Flask session cookie
            credentials: "include",
        });

        if (!res.ok) {
            if (res.status === 401) {
                localStorage.removeItem("hive_username");
                showLoginUI();
                return;
            }
            throw new Error("Failed to fetch profile");
        }

        const profile = await res.json();
        showAuthenticatedUI(profile);
    } catch (err) {
        console.error("Profile fetch error:", err);
        localStorage.removeItem("hive_username");
        showLoginUI();
    }
}

function showLoginUI() {
    document.getElementById("login-section").style.display = "block";
    document.getElementById("profile-section").style.display = "none";
    const opsSection = document.getElementById("operations-section");
    if (opsSection) opsSection.style.display = "none";
}

function showAuthenticatedUI(profile) {
    document.getElementById("login-section").style.display = "none";

    const profileSection = document.getElementById("profile-section");
    profileSection.style.display = "block";

    const img = document.getElementById("profile-image");
    if (profile.profile && profile.profile.profile_image) {
        img.src = profile.profile.profile_image;
        img.style.display = "block";
    } else {
        img.style.display = "none";
    }

    document.getElementById("profile-name").textContent =
        `@${profile.username}` +
        (profile.profile && profile.profile.name
            ? ` (${profile.profile.name})`
            : "");

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

    const opsSection = document.getElementById("operations-section");
    if (opsSection) opsSection.style.display = "block";
}

// =============================================================================
// 5. LOGOUT
// =============================================================================

/**
 * Log out: call the Flask backend to clear the server-side session,
 * then switch to the login view.
 *
 * FLASK SESSION NOTE:
 * Unlike the JWT version (which just deletes from localStorage), we must
 * call the server to invalidate the session. The POST /api/auth/logout
 * endpoint calls session.clear() which empties the signed cookie.
 */
async function logout() {
    try {
        await fetch(`${API_BASE}/api/auth/logout`, {
            method: "POST",
            credentials: "include",
        });
    } catch {
        // Even if the server call fails, clear local state
    }
    localStorage.removeItem("hive_username");
    showLoginUI();
    clearStatus();
    clearOpsStatus();
    document.getElementById("username").value = "";
}

// =============================================================================
// 6. POST-AUTH KEYCHAIN OPERATIONS
// =============================================================================
// These operations interact directly with Hive Keychain to broadcast
// transactions to the blockchain. They do NOT go through our Flask backend.
// Each operation prompts Keychain for user approval.

/**
 * PUBLISH A POST using requestBroadcast with the "comment" operation.
 *
 * On Hive, both posts and replies use the "comment" operation:
 *   - Top-level post: parent_author="" parent_permlink="category"
 *   - Reply: parent_author="original_author" parent_permlink="original_permlink"
 *
 * Uses POSTING key authority.
 */
async function publishPost() {
    if (!checkKeychain()) { showOpsStatus("Keychain not available.", "error"); return; }
    const username = localStorage.getItem("hive_username");
    if (!username) { showOpsStatus("You must be logged in.", "error"); return; }

    const title = (document.getElementById("post-title") || {}).value?.trim() || "";
    const body = (document.getElementById("post-body") || {}).value?.trim() || "";
    if (!title || !body) { showOpsStatus("Title and body are required.", "error"); return; }

    // Generate a URL-safe permlink from the title
    const permlink = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").substring(0, 200) + "-" + Date.now().toString(36);

    const operations = [["comment", {
        parent_author: "",              // Empty = top-level post
        parent_permlink: "hive-keychain", // Category/community
        author: username,
        permlink: permlink,
        title: title,
        body: body,
        json_metadata: JSON.stringify({
            tags: ["hive-keychain", "tutorial", "development"],
            app: "hive-keychain-auth-template/1.0.0",
            format: "markdown",
        }),
    }]];

    showOpsStatus("Waiting for Keychain to approve the post...", "info");
    try {
        const result = await new Promise((resolve, reject) => {
            window.hive_keychain.requestBroadcast(username, operations, "Posting", (response) => {
                response.success ? resolve(response) : reject(new Error(response.error || response.message || "Broadcast failed"));
            });
        });
        showOpsStatus(`Post published! TX: ${result.result?.id || "confirmed"}`, "success");
    } catch (err) { showOpsStatus(`Post failed: ${err.message}`, "error"); }
}

/**
 * SEND TOKENS using requestTransfer.
 *
 * requestTransfer(from, to, amount, memo, currency, callback)
 * - Amount MUST have exactly 3 decimal places (e.g., "1.000")
 * - Currency: "HIVE" or "HBD"
 * - Memo is public unless prefixed with # (then encrypted with memo keys)
 * - Uses ACTIVE key (financial operation)
 */
async function sendTransfer() {
    if (!checkKeychain()) { showOpsStatus("Keychain not available.", "error"); return; }
    const username = localStorage.getItem("hive_username");
    if (!username) { showOpsStatus("You must be logged in.", "error"); return; }

    const recipient = (document.getElementById("transfer-to") || {}).value?.trim().toLowerCase() || "";
    const amountRaw = (document.getElementById("transfer-amount") || {}).value?.trim() || "";
    const memo = (document.getElementById("transfer-memo") || {}).value?.trim() || "";
    const currency = (document.getElementById("transfer-currency") || {}).value || "HIVE";

    if (!recipient || !amountRaw) { showOpsStatus("Recipient and amount are required.", "error"); return; }
    const amount = parseFloat(amountRaw).toFixed(3);
    if (isNaN(parseFloat(amountRaw)) || parseFloat(amount) <= 0) { showOpsStatus("Enter a valid positive amount.", "error"); return; }

    showOpsStatus(`Requesting transfer of ${amount} ${currency} to @${recipient}...`, "info");
    try {
        await new Promise((resolve, reject) => {
            window.hive_keychain.requestTransfer(username, recipient, amount, memo, currency, (response) => {
                response.success ? resolve(response) : reject(new Error(response.error || response.message || "Transfer failed"));
            });
        });
        showOpsStatus(`Sent ${amount} ${currency} to @${recipient}!`, "success");
    } catch (err) { showOpsStatus(`Transfer failed: ${err.message}`, "error"); }
}

/**
 * VOTE ON CONTENT using requestBroadcast with the "vote" operation.
 *
 * Vote weight: 10000 = 100% upvote, -10000 = 100% downvote, 0 = unvote.
 * Uses POSTING key.
 */
async function voteOnContent() {
    if (!checkKeychain()) { showOpsStatus("Keychain not available.", "error"); return; }
    const username = localStorage.getItem("hive_username");
    if (!username) { showOpsStatus("You must be logged in.", "error"); return; }

    const author = (document.getElementById("vote-author") || {}).value?.trim().toLowerCase() || "";
    const permlink = (document.getElementById("vote-permlink") || {}).value?.trim() || "";
    const weightPercent = parseInt((document.getElementById("vote-weight") || {}).value, 10) || 100;

    if (!author || !permlink) { showOpsStatus("Author and permlink are required.", "error"); return; }
    const weight = Math.min(10000, Math.max(-10000, weightPercent * 100));

    const operations = [["vote", { voter: username, author, permlink, weight }]];
    showOpsStatus("Waiting for Keychain to approve the vote...", "info");
    try {
        await new Promise((resolve, reject) => {
            window.hive_keychain.requestBroadcast(username, operations, "Posting", (response) => {
                response.success ? resolve(response) : reject(new Error(response.error || response.message || "Vote failed"));
            });
        });
        showOpsStatus(`Vote of ${weightPercent}% on @${author}/${permlink} confirmed!`, "success");
    } catch (err) { showOpsStatus(`Vote failed: ${err.message}`, "error"); }
}

/**
 * DELEGATE HIVE POWER using requestDelegation.
 *
 * Delegation lends voting influence without transferring ownership.
 * Uses ACTIVE key. Set amount to 0 to undelegate (5-day cooldown).
 */
async function delegateHP() {
    if (!checkKeychain()) { showOpsStatus("Keychain not available.", "error"); return; }
    const username = localStorage.getItem("hive_username");
    if (!username) { showOpsStatus("You must be logged in.", "error"); return; }

    const delegatee = (document.getElementById("delegate-to") || {}).value?.trim().toLowerCase() || "";
    const amount = (document.getElementById("delegate-amount") || {}).value?.trim() || "";

    if (!delegatee || !amount) { showOpsStatus("Delegatee and amount are required.", "error"); return; }

    showOpsStatus(`Requesting delegation of ${amount} HP to @${delegatee}...`, "info");
    try {
        await new Promise((resolve, reject) => {
            window.hive_keychain.requestDelegation(username, delegatee, amount, "HP", (response) => {
                response.success ? resolve(response) : reject(new Error(response.error || response.message || "Delegation failed"));
            });
        });
        showOpsStatus(`Delegated ${amount} HP to @${delegatee}!`, "success");
    } catch (err) { showOpsStatus(`Delegation failed: ${err.message}`, "error"); }
}

/**
 * BROADCAST CUSTOM JSON -- the dapp swiss army knife.
 *
 * Used by: Splinterlands (game actions), dBuzz (short posts),
 * Hive-Engine (sidechain tokens), PeakD (user preferences).
 * Uses POSTING key (via required_posting_auths).
 */
async function broadcastCustomJson() {
    if (!checkKeychain()) { showOpsStatus("Keychain not available.", "error"); return; }
    const username = localStorage.getItem("hive_username");
    if (!username) { showOpsStatus("You must be logged in.", "error"); return; }

    const customId = (document.getElementById("custom-json-id") || {}).value?.trim() || "my-dapp";
    const customData = (document.getElementById("custom-json-data") || {}).value?.trim() || "{}";

    try { JSON.parse(customData); } catch { showOpsStatus("Invalid JSON data.", "error"); return; }

    const operations = [["custom_json", {
        required_auths: [],
        required_posting_auths: [username],
        id: customId,
        json: customData,
    }]];

    showOpsStatus("Waiting for Keychain to approve custom_json...", "info");
    try {
        await new Promise((resolve, reject) => {
            window.hive_keychain.requestBroadcast(username, operations, "Posting", (response) => {
                response.success ? resolve(response) : reject(new Error(response.error || response.message || "Broadcast failed"));
            });
        });
        showOpsStatus("Custom JSON broadcast confirmed!", "success");
    } catch (err) { showOpsStatus(`Custom JSON failed: ${err.message}`, "error"); }
}

// =============================================================================
// 7. INITIALIZATION
// =============================================================================

document.addEventListener("DOMContentLoaded", () => {
    checkKeychain();
    setTimeout(checkKeychain, KEYCHAIN_DETECT_DELAY_MS);

    // Check for an existing Flask session by calling /api/auth/status.
    // This is different from the JWT version which checks localStorage.
    // The Flask session cookie is HttpOnly (JS cannot read it directly),
    // so we must ask the server if the session is valid.
    fetch(`${API_BASE}/api/auth/status`, { credentials: "include" })
        .then((res) => res.json())
        .then((data) => {
            if (data.authenticated) {
                localStorage.setItem("hive_username", data.username);
                fetchProfile();
            }
        })
        .catch(() => {
            // Server not reachable or session expired -- stay on login page
        });

    // Enter key triggers login
    const usernameInput = document.getElementById("username");
    if (usernameInput) {
        usernameInput.addEventListener("keypress", (e) => {
            if (e.key === "Enter") login();
        });
    }

    // Tab switching for operations panel
    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
            document.querySelectorAll(".tab-panel").forEach((p) => (p.style.display = "none"));
            btn.classList.add("active");
            const panel = document.getElementById(btn.dataset.tab);
            if (panel) panel.style.display = "block";
            clearOpsStatus();
        });
    });
});
