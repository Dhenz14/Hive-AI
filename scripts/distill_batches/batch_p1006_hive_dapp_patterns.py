"""Hive blockchain training pairs: dApp development patterns."""

PAIRS = [
    (
        "hive/hive-keychain-integration",
        r'''How do I integrate Hive Keychain into a web dApp for secure transaction signing?''',
        r'''Hive Keychain is a browser extension that manages keys securely. Users never expose their private keys to your dApp. Here is how to integrate it:

```html
<!DOCTYPE html>
<html>
<head><title>Hive dApp with Keychain</title></head>
<body>
<button onclick="login()">Login with Keychain</button>
<button onclick="vote()">Upvote</button>
<button onclick="transfer()">Transfer</button>
<button onclick="customJson()">Custom JSON</button>
<div id="status"></div>

<script>
// Check if Hive Keychain is installed
function isKeychainInstalled() {
    return window.hive_keychain !== undefined;
}

// Login: verify account ownership
function login() {
    if (!isKeychainInstalled()) {
        document.getElementById("status").innerText =
            "Please install Hive Keychain extension";
        return;
    }

    const username = prompt("Enter your Hive username:");
    if (!username) return;

    // Request a signature to prove ownership
    const message = "Login to MyApp: " + Date.now();

    window.hive_keychain.requestSignBuffer(
        username,
        message,
        "Posting",
        function(response) {
            if (response.success) {
                document.getElementById("status").innerText =
                    "Logged in as @" + username;
                // Verify signature server-side for production
                sessionStorage.setItem("hiveUser", username);
            } else {
                document.getElementById("status").innerText =
                    "Login failed: " + response.message;
            }
        }
    );
}

// Vote on a post
function vote() {
    const username = sessionStorage.getItem("hiveUser");
    if (!username) { alert("Please login first"); return; }

    window.hive_keychain.requestVote(
        username,
        "author",        // Post author
        "post-permlink", // Post permlink
        10000,           // Weight: 10000 = 100%
        function(response) {
            if (response.success) {
                document.getElementById("status").innerText =
                    "Vote successful! TX: " + response.result.id;
            } else {
                document.getElementById("status").innerText =
                    "Vote failed: " + response.message;
            }
        }
    );
}

// Transfer HIVE/HBD
function transfer() {
    const username = sessionStorage.getItem("hiveUser");
    if (!username) { alert("Please login first"); return; }

    window.hive_keychain.requestTransfer(
        username,
        "recipient",    // To account
        "1.000",        // Amount
        "Payment memo", // Memo
        "HIVE",         // Currency: HIVE or HBD
        function(response) {
            if (response.success) {
                document.getElementById("status").innerText =
                    "Transfer successful!";
            } else {
                document.getElementById("status").innerText =
                    "Transfer failed: " + response.message;
            }
        },
        false  // enforce=false allows user to modify amount
    );
}

// Broadcast custom_json
function customJson() {
    const username = sessionStorage.getItem("hiveUser");
    if (!username) { alert("Please login first"); return; }

    const payload = JSON.stringify({
        app: "myapp/1.0",
        action: "register",
        data: {preference: "dark_mode"}
    });

    window.hive_keychain.requestCustomJson(
        username,
        "myapp",         // custom_json id
        "Posting",       // Key type: Posting or Active
        payload,         // JSON string
        "Register User", // Display title for user
        function(response) {
            if (response.success) {
                document.getElementById("status").innerText =
                    "Custom JSON broadcast!";
            } else {
                document.getElementById("status").innerText =
                    "Failed: " + response.message;
            }
        }
    );
}
</script>
</body>
</html>
```

Hive Keychain API methods:
- requestSignBuffer: Sign arbitrary data (login verification)
- requestVote: Vote on posts/comments
- requestTransfer: Transfer HIVE/HBD
- requestCustomJson: Broadcast custom_json operations
- requestPost: Create/edit posts
- requestDelegation: Delegate HP
- requestWitnessVote: Vote for witnesses
- requestProxy: Set voting proxy

All methods are async with callback. The user sees a popup to approve each operation. Keys never leave the extension.
'''
    ),
    (
        "hive/hiveauth-flow",
        r'''How do I implement HiveAuth authentication in my dApp for mobile and desktop users who do not have Keychain?''',
        r'''HiveAuth provides QR-code-based authentication for Hive dApps, working with mobile wallets like Hive Keychain Mobile. Here is the implementation:

```javascript
// HiveAuth integration for web dApps
// Install: npm install hiveauth-wrapper

const HiveAuth = require("hiveauth-wrapper");

class HiveAuthClient {
    constructor(appName, appDescription) {
        this.appName = appName;
        this.appDescription = appDescription;
        this.authKey = null;
        this.username = null;
    }

    async authenticate(username) {
        /**
         * HiveAuth flow:
         * 1. App creates an auth request
         * 2. User scans QR code with Hive Keychain Mobile
         * 3. User approves on their phone
         * 4. App receives confirmation via websocket
         */
        return new Promise((resolve, reject) => {
            const auth = {
                username: username,
                expire: Math.floor(Date.now() / 1000) + 600, // 10 min
                key: HiveAuth.generateKey()
            };

            this.authKey = auth.key;
            this.username = username;

            HiveAuth.authenticate(
                auth,
                this.appName,
                (evt) => {
                    // Callback for auth events
                    if (evt.type === "qr") {
                        // Display this QR code to the user
                        console.log("Scan this QR code:", evt.data);
                        // In a web app, use a QR library to render:
                        // displayQRCode(evt.data);
                    } else if (evt.type === "success") {
                        console.log("Authenticated as @" + username);
                        resolve({
                            username: username,
                            token: evt.data.token,
                            expire: evt.data.expire
                        });
                    } else if (evt.type === "error") {
                        reject(new Error("Auth failed: " + evt.data));
                    }
                }
            );
        });
    }

    async broadcastOperation(op) {
        /**
         * Broadcast a signed operation via HiveAuth.
         * The user approves on their mobile device.
         */
        return new Promise((resolve, reject) => {
            HiveAuth.broadcast(
                this.username,
                [op],
                this.authKey,
                (evt) => {
                    if (evt.type === "qr") {
                        console.log("Approve on your device:", evt.data);
                    } else if (evt.type === "success") {
                        resolve(evt.data);
                    } else if (evt.type === "error") {
                        reject(new Error("Broadcast failed: " + evt.data));
                    }
                }
            );
        });
    }

    async vote(author, permlink, weight) {
        const op = [
            "vote",
            {
                voter: this.username,
                author: author,
                permlink: permlink,
                weight: weight
            }
        ];
        return await this.broadcastOperation(op);
    }

    async customJson(id, payload, keyType) {
        const auths = keyType === "active"
            ? {required_auths: [this.username], required_posting_auths: []}
            : {required_auths: [], required_posting_auths: [this.username]};

        const op = [
            "custom_json",
            {
                ...auths,
                id: id,
                json: JSON.stringify(payload)
            }
        ];
        return await this.broadcastOperation(op);
    }
}

// Server-side: Verify HiveAuth login
async function verifyHiveAuthLogin(username, token) {
    // Verify the token matches what was issued
    // In production, validate against your session store
    return {verified: true, username: username};
}

// Usage in a web app
async function main() {
    const client = new HiveAuthClient("MyApp", "A cool Hive dApp");

    try {
        const session = await client.authenticate("someuser");
        console.log("Session:", session);

        // Now broadcast operations
        const result = await client.vote("author", "post-permlink", 10000);
        console.log("Vote result:", result);
    } catch (err) {
        console.error("Error:", err.message);
    }
}

// main();
```

HiveAuth is ideal for:
- Mobile users without the browser extension
- Desktop users who prefer phone-based signing
- Cross-platform dApps that need a universal auth method
- Situations where Hive Keychain is not available

The flow is similar to WalletConnect in Ethereum -- the user scans a QR code and approves transactions on their trusted device.
'''
    ),
    (
        "hive/posting-authority-dapps",
        r'''How do I build a dApp that uses posting authority to perform actions on behalf of users?''',
        r'''When a user grants posting authority to your dApp account, your dApp can sign posting-level operations using your own key. This enables seamless background operations. Here is the pattern:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Vote, Comment, Custom_json
import json

class PostingAuthorityDApp:
    """A dApp that operates with delegated posting authority."""

    def __init__(self, dapp_account, dapp_posting_key, nodes=None):
        self.account = dapp_account
        self.hive = Hive(
            node=nodes or ["https://api.hive.blog"],
            keys=[dapp_posting_key]
        )

    def check_authority(self, user_account):
        """Check if user has granted us posting authority."""
        acct = Account(user_account, hive_instance=self.hive)
        posting = acct["posting"]
        authorized = [a[0] for a in posting.get("account_auths", [])]
        has_auth = self.account in authorized
        print(f"@{user_account} posting auth to @{self.account}: {has_auth}")
        return has_auth

    def vote_for_user(self, user_account, author, permlink, weight=10000):
        """Vote on behalf of a user (requires their posting authority)."""
        if not self.check_authority(user_account):
            raise PermissionError(
                f"@{user_account} has not granted posting authority "
                f"to @{self.account}"
            )

        op = Vote(**{
            "voter": user_account,  # The USER is the voter
            "author": author,
            "permlink": permlink,
            "weight": weight
        })

        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        # Sign with OUR posting key, but the operation is for the USER
        tx.appendSigner(self.account, "posting")
        tx.sign()
        result = tx.broadcast()
        print(f"Voted as @{user_account} on @{author}/{permlink}")
        return result

    def post_for_user(self, user_account, title, body, tags,
                       permlink=None):
        """Create a post on behalf of a user."""
        if not self.check_authority(user_account):
            raise PermissionError("No posting authority")

        if not permlink:
            import time
            permlink = f"{title.lower().replace(' ', '-')[:80]}-{int(time.time())}"
            permlink = "".join(c for c in permlink if c.isalnum() or c == "-")

        op = Comment(**{
            "parent_author": "",
            "parent_permlink": tags[0] if tags else "hive",
            "author": user_account,
            "permlink": permlink,
            "title": title,
            "body": body,
            "json_metadata": json.dumps({
                "tags": tags,
                "app": f"{self.account}/1.0",
                "format": "markdown"
            })
        })

        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "posting")
        tx.sign()
        result = tx.broadcast()
        print(f"Posted as @{user_account}: {title}")
        return result, permlink

    def custom_json_for_user(self, user_account, dapp_id, payload):
        """Broadcast custom_json on behalf of a user."""
        if not self.check_authority(user_account):
            raise PermissionError("No posting authority")

        op = Custom_json(**{
            "required_auths": [],
            "required_posting_auths": [user_account],
            "id": dapp_id,
            "json": json.dumps(payload)
        })

        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "posting")
        tx.sign()
        return tx.broadcast()

    def batch_operations(self, operations):
        """Execute multiple operations in a single transaction."""
        tx = TransactionBuilder(hive_instance=self.hive)
        for op in operations:
            tx.appendOps(op)
        tx.appendSigner(self.account, "posting")
        tx.sign()
        return tx.broadcast()

# Usage
dapp = PostingAuthorityDApp("myapp", "5MyAppPostingKey")

# Check if user authorized us
if dapp.check_authority("someuser"):
    # Vote on their behalf
    dapp.vote_for_user("someuser", "goodauthor", "good-post", 5000)

    # Post on their behalf
    dapp.post_for_user("someuser", "Automated Post",
                        "This was posted by MyApp on my behalf.",
                        ["myapp", "automated"])
```

This pattern is used by all major Hive dApps (PeakD, Ecency, Splinterlands). The dApp signs operations with its own posting key, but the operations specify the user as the actor. The blockchain validates that the signing account has posting authority over the user's account. This only works for posting-level operations -- active-level operations (transfers, etc.) cannot be delegated this way.
'''
    ),
    (
        "hive/reward-splitting",
        r'''How do I implement reward splitting in a Hive dApp using beneficiaries and automatic transfers?''',
        r'''Reward splitting on Hive can be implemented through beneficiaries (set at post creation) or through automatic post-payout transfers. Here are both approaches:

```python
from beem import Hive
from beem.account import Account
from beem.blockchain import Blockchain
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Comment, Comment_options, Transfer
import json
import time

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5PostingKey", "5ActiveKey"]
)

# Approach 1: Beneficiaries (set at post creation)
def post_with_revenue_share(author, title, body, tags, shares):
    """Create a post with revenue sharing via beneficiaries.

    Args:
        shares: dict of {account: percentage} e.g., {"dev": 5, "dao": 3}
    """
    permlink = f"{title.lower().replace(' ', '-')[:80]}-{int(time.time())}"
    permlink = "".join(c for c in permlink if c.isalnum() or c == "-")

    # Convert percentages to basis points and sort alphabetically
    beneficiaries = sorted(
        [{"account": acct, "weight": int(pct * 100)}
         for acct, pct in shares.items()],
        key=lambda x: x["account"]
    )

    total_weight = sum(b["weight"] for b in beneficiaries)
    if total_weight > 10000:
        raise ValueError("Total share exceeds 100%")

    comment_op = Comment(**{
        "parent_author": "",
        "parent_permlink": tags[0],
        "author": author,
        "permlink": permlink,
        "title": title,
        "body": body,
        "json_metadata": json.dumps({"tags": tags, "app": "myapp/1.0"})
    })

    options_op = Comment_options(**{
        "author": author,
        "permlink": permlink,
        "max_accepted_payout": "1000000.000 HBD",
        "percent_hbd": 10000,
        "allow_votes": True,
        "allow_curation_rewards": True,
        "extensions": [[0, {"beneficiaries": beneficiaries}]]
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(comment_op)
    tx.appendOps(options_op)
    tx.appendSigner(author, "posting")
    tx.sign()
    result = tx.broadcast()

    print(f"Post with revenue share created:")
    print(f"  Author keeps: {100 - total_weight/100}%")
    for b in beneficiaries:
        print(f"  @{b['account']}: {b['weight']/100}%")
    return result

# Approach 2: Monitor payouts and distribute manually
class PayoutDistributor:
    """Watch for post payouts and distribute rewards."""

    def __init__(self, hive_instance, dapp_account, active_key):
        self.hive = hive_instance
        self.account = dapp_account
        self.splits = {}  # {author: {recipient: percentage}}

    def register_split(self, author, recipient, percentage):
        """Register a split for an author's future payouts."""
        self.splits.setdefault(author, {})[recipient] = percentage

    def process_payout(self, author_reward_op):
        """Process an author_reward operation and distribute."""
        author = author_reward_op.get("author", "")
        if author not in self.splits:
            return

        hbd_payout = author_reward_op.get("hbd_payout", "0.000 HBD")
        hive_payout = author_reward_op.get("hive_payout", "0.000 HIVE")

        hbd_amount = float(str(hbd_payout).split()[0])
        hive_amount = float(str(hive_payout).split()[0])

        for recipient, pct in self.splits[author].items():
            hbd_share = hbd_amount * pct / 100
            hive_share = hive_amount * pct / 100

            if hbd_share >= 0.001:
                self._transfer(author, recipient,
                               f"{hbd_share:.3f} HBD",
                               f"Revenue share: {pct}%")
            if hive_share >= 0.001:
                self._transfer(author, recipient,
                               f"{hive_share:.3f} HIVE",
                               f"Revenue share: {pct}%")

    def _transfer(self, from_acct, to_acct, amount, memo):
        """Execute a transfer (requires active key of from_acct)."""
        op = Transfer(**{
            "from": from_acct,
            "to": to_acct,
            "amount": amount,
            "memo": memo
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(from_acct, "active")
        tx.sign()
        return tx.broadcast()

    def monitor_payouts(self):
        """Stream author_reward operations."""
        blockchain = Blockchain(hive_instance=self.hive)
        stream = blockchain.stream(
            opNames=["author_reward"],
            raw_ops=False,
            threading=False
        )
        for op in stream:
            self.process_payout(op)

# Usage
# Beneficiary approach (recommended - trustless, on-chain)
post_with_revenue_share(
    "author1", "My Post", "Content here", ["hive-dev"],
    shares={"myapp": 5, "charity": 2}
)
```

Beneficiaries are the preferred approach because they are trustless -- the blockchain enforces the split at the consensus level. Manual distribution requires trust in the distributor. Most dApps use beneficiaries with a small percentage (3-10%) as their revenue model.
'''
    ),
    (
        "hive/login-verification",
        r'''How do I verify a Hive account login server-side? Show the cryptographic verification process.''',
        r'''Server-side login verification on Hive uses cryptographic signature verification. The user signs a challenge message with their posting key, and you verify the signature matches their on-chain public key:

```python
from beem import Hive
from beem.account import Account
from beemgraphenebase.ecdsasig import verify_message
from beemgraphenebase.account import PublicKey
import hashlib
import time
import json
import secrets

hive = Hive(node=["https://api.hive.blog"])

class HiveLoginVerifier:
    """Server-side Hive account login verification."""

    def __init__(self, app_name, hive_instance=None):
        self.app_name = app_name
        self.hive = hive_instance or hive
        self.challenges = {}  # Store pending challenges

    def create_challenge(self, username):
        """Create a login challenge for the user to sign."""
        nonce = secrets.token_hex(16)
        timestamp = int(time.time())
        challenge = f"{self.app_name}:{username}:{timestamp}:{nonce}"

        # Store with expiration
        self.challenges[username] = {
            "challenge": challenge,
            "expires": timestamp + 300,  # 5 minute expiry
            "nonce": nonce
        }

        return challenge

    def verify_login(self, username, signature, challenge=None):
        """Verify a signed login challenge.

        Args:
            username: Hive account name
            signature: Hex-encoded signature from the user
            challenge: The challenge string that was signed

        Returns:
            dict with verified=True/False and details
        """
        # Check challenge validity
        stored = self.challenges.get(username)
        if not stored:
            return {"verified": False, "error": "No pending challenge"}

        if challenge != stored["challenge"]:
            return {"verified": False, "error": "Challenge mismatch"}

        if time.time() > stored["expires"]:
            del self.challenges[username]
            return {"verified": False, "error": "Challenge expired"}

        # Get the account's posting public keys
        try:
            acct = Account(username, hive_instance=self.hive)
        except Exception:
            return {"verified": False, "error": "Account not found"}

        posting_keys = acct["posting"]["key_auths"]
        posting_public_keys = [k[0] for k in posting_keys]

        # Also check account_auths (dApps with posting authority)
        # In most cases, we want direct key verification
        try:
            # Verify the signature against each posting key
            message_hash = hashlib.sha256(challenge.encode("utf-8")).digest()

            for pub_key_str in posting_public_keys:
                try:
                    # Use beem's signature verification
                    pub_key = PublicKey(pub_key_str)
                    is_valid = verify_message(
                        message_hash,
                        bytes.fromhex(signature),
                        pub_key
                    )
                    if is_valid:
                        del self.challenges[username]
                        return {
                            "verified": True,
                            "username": username,
                            "key_type": "posting",
                            "timestamp": int(time.time())
                        }
                except Exception:
                    continue

            return {"verified": False, "error": "Invalid signature"}

        except Exception as e:
            return {"verified": False, "error": str(e)}

# Express.js equivalent for Node.js server
NODE_SERVER_CODE = """
// Node.js server-side verification with dhive
const dhive = require("@hiveio/dhive");
const crypto = require("crypto");
const express = require("express");

const app = express();
const client = new dhive.Client(["https://api.hive.blog"]);
const challenges = new Map();

app.use(express.json());

// Step 1: Generate challenge
app.post("/auth/challenge", (req, res) => {
    const {username} = req.body;
    const nonce = crypto.randomBytes(16).toString("hex");
    const challenge = `MyApp:${username}:${Date.now()}:${nonce}`;

    challenges.set(username, {
        challenge,
        expires: Date.now() + 300000
    });

    res.json({challenge});
});

// Step 2: Verify signed challenge
app.post("/auth/verify", async (req, res) => {
    const {username, signature} = req.body;
    const stored = challenges.get(username);

    if (!stored || Date.now() > stored.expires) {
        return res.status(401).json({error: "Invalid or expired challenge"});
    }

    try {
        const accounts = await client.database.getAccounts([username]);
        if (accounts.length === 0) {
            return res.status(404).json({error: "Account not found"});
        }

        const postingKeys = accounts[0].posting.key_auths.map(k => k[0]);

        // Recover public key from signature
        const signatureObj = dhive.Signature.fromString(signature);
        const messageHash = dhive.cryptoUtils.sha256(stored.challenge);
        const recoveredKey = signatureObj.recover(messageHash).toString();

        if (postingKeys.includes(recoveredKey)) {
            challenges.delete(username);
            // Create session/JWT here
            res.json({verified: true, username});
        } else {
            res.status(401).json({error: "Invalid signature"});
        }
    } catch (err) {
        res.status(500).json({error: err.message});
    }
});

app.listen(3000);
"""

# Usage
verifier = HiveLoginVerifier("MyApp")
challenge = verifier.create_challenge("testuser")
print(f"Challenge: {challenge}")
# User signs this challenge with their posting key
# result = verifier.verify_login("testuser", user_signature, challenge)
```

This challenge-response pattern is the standard way to authenticate Hive users. The user never sends their private key -- they only send a signature that proves they control the key. Always use HTTPS in production and set short challenge expiration times to prevent replay attacks.
'''
    ),
]
