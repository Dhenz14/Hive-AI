# Hive SDK Skill File (beem for Python, dhive for JavaScript)

## beem (Python)

### Installation
```bash
pip install beem
```

### Core Classes & Initialization

```python
from beem import Hive
from beem.account import Account
from beem.comment import Comment
from beem.vote import Vote, ActiveVotes
from beem.transactionbuilder import TransactionBuilder
from beem.nodelist import NodeList
from beembase.operations import Custom_json, Comment as CommentOp, Vote as VoteOp, Transfer
from beem.rc import RC

# Basic initialization (read-only, no keys)
hive = Hive()

# With specific nodes
hive = Hive(node=["https://api.hive.blog", "https://api.openhive.network", "https://anyx.io"])

# With keys for broadcasting (posting key for social ops)
hive = Hive(keys=["5Jxxxxxxxxx_POSTING_WIF"])

# With keys for financial ops (active key)
hive = Hive(keys=["5Jxxxxxxxxx_ACTIVE_WIF"])

# Using NodeList to get updated nodes
nodelist = NodeList()
nodelist.update_nodes()
hive = Hive(node=nodelist.get_hive_nodes())

# All beem objects can accept blockchain_instance= to share one connection
acc = Account("username", blockchain_instance=hive)
```

### Account Operations

```python
from beem import Hive
from beem.account import Account

hive = Hive(keys=["5Jxxxxxxxxx_ACTIVE_WIF"])
acc = Account("myaccount", blockchain_instance=hive)

# Read account data
print(acc.get_balances())           # All balances
print(acc["balance"])               # HIVE balance
print(acc["hbd_balance"])           # HBD balance
print(acc["vesting_shares"])        # Vesting (HP)
print(acc.get_hive_power())         # HP as float
print(acc.get_voting_power())       # Current voting mana %
print(acc.reputation)               # Reputation score

# Transfer HIVE
acc.transfer("recipient", 1.0, "HIVE", memo="payment for services")

# Transfer HBD
acc.transfer("recipient", 5.0, "HBD", memo="invoice #123")

# Transfer to savings
acc.transfer_to_savings(1.0, "HBD", memo="savings deposit")

# Power up (HIVE -> HP)
acc.transfer_to_vesting(10.0)

# Delegate HP
acc.delegate_vesting_shares("recipient", "100.000000 VESTS")

# Account history iteration
for op in acc.history(only_ops=["transfer"]):
    print(op["from"], "->", op["to"], op["amount"])

for op in acc.history_reverse(only_ops=["vote"]):
    print(op["voter"], "voted on", op["author"] + "/" + op["permlink"])
```

### Posting & Commenting

```python
from beem import Hive
from beem.comment import Comment

hive = Hive(keys=["5Jxxxxxxxxx_POSTING_WIF"])

# Submit a new post (top-level comment)
hive.post(
    title="My Post Title",
    body="This is the body of my post in **markdown**.",
    author="myaccount",
    permlink="my-post-permlink",           # optional, auto-generated from title
    tags=["hive", "development", "python"],  # first tag = main community/category
    json_metadata={"app": "myapp/1.0"},
    self_vote=False
)

# Reply to a post
hive.post(
    title="",                               # replies have empty title
    body="Great post! Thanks for sharing.",
    author="myaccount",
    reply_identifier="@originalauthor/original-permlink",  # the post to reply to
    json_metadata={"app": "myapp/1.0"}
)

# Read a comment/post
c = Comment("@author/permlink", blockchain_instance=hive)
print(c["title"])
print(c["body"])
print(c["author"])
print(c["created"])
print(c["pending_payout_value"])
print(c.get_votes())
```

### Voting

```python
from beem import Hive
from beem.comment import Comment

hive = Hive(keys=["5Jxxxxxxxxx_POSTING_WIF"])

# Upvote at 100% weight
c = Comment("@author/permlink", blockchain_instance=hive)
c.upvote(weight=100, voter="myaccount")

# Upvote at 50% weight
c.upvote(weight=50, voter="myaccount")

# Downvote at 100%
c.downvote(weight=100, voter="myaccount")

# Alternative: using hive.vote()
hive.vote(100, "@author/permlink", account="myaccount")
```

### Custom JSON

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json

hive = Hive(keys=["5Jxxxxxxxxx_POSTING_WIF"])

# Method 1: Using hive.custom_json (simplest)
hive.custom_json(
    id="myapp",
    json_data={"action": "do_something", "value": 42},
    required_posting_auths=["myaccount"]
)

# Method 2: Using TransactionBuilder (more control)
tx = TransactionBuilder(blockchain_instance=hive)
op = Custom_json(
    **{
        "required_auths": [],
        "required_posting_auths": ["myaccount"],
        "id": "myapp",
        "json": json.dumps({"action": "do_something", "value": 42})
    }
)
tx.appendOps(op)
tx.appendWif("5Jxxxxxxxxx_POSTING_WIF")
tx.sign()
result = tx.broadcast()

# Active-key custom_json (for financial operations on L2)
hive_active = Hive(keys=["5Jxxxxxxxxx_ACTIVE_WIF"])
hive_active.custom_json(
    id="ssc-mainnet-hive",
    json_data={
        "contractName": "tokens",
        "contractAction": "transfer",
        "contractPayload": {
            "symbol": "BEE",
            "to": "recipient",
            "quantity": "10",
            "memo": "token transfer"
        }
    },
    required_auths=["myaccount"]
)
```

### Resource Credits Check

```python
from beem import Hive
from beem.account import Account
from beem.rc import RC

hive = Hive()
acc = Account("myaccount", blockchain_instance=hive)

# Get RC manabar
manabar = acc.get_rc_manabar()
print(f"Current RC mana: {manabar['current_mana']}")
print(f"Max RC mana: {manabar['max_mana']}")
print(f"RC %: {manabar['current_mana'] / manabar['max_mana'] * 100:.2f}%")

# Calculate operation costs
rc = RC(blockchain_instance=hive)
comment_cost = rc.comment()
vote_cost = rc.vote()
custom_json_cost = rc.custom_json()
transfer_cost = rc.transfer()

print(f"Cost of a comment: {comment_cost} RC")
print(f"Cost of a vote: {vote_cost} RC")
print(f"Cost of a custom_json: {custom_json_cost} RC")

# How many ops can I do?
possible_votes = int(manabar['current_mana'] / vote_cost)
print(f"Possible votes: {possible_votes}")
```

### Error Handling

```python
from beem import Hive
from beem.exceptions import (
    AccountDoesNotExistsException,
    ContentDoesNotExistsException,
    VotingInvalidOnArchivedPost,
    InsufficientAuthorityError,
    MissingKeyError,
    UnhandledRPCError
)

hive = Hive(keys=["5Jxxxxxxxxx_POSTING_WIF"])

try:
    acc = Account("nonexistent_account_xyz", blockchain_instance=hive)
except AccountDoesNotExistsException:
    print("Account not found")

try:
    hive.vote(100, "@author/permlink", account="myaccount")
except VotingInvalidOnArchivedPost:
    print("Post is older than 7 days, cannot vote")
except MissingKeyError:
    print("Required key not provided")
except InsufficientAuthorityError:
    print("Wrong key type for this operation")
except UnhandledRPCError as e:
    print(f"RPC error: {e}")

# Common pitfall: RPCError for insufficient RC
try:
    hive.post(title="Test", body="Test", author="lowrc_account", tags=["test"])
except Exception as e:
    if "rc" in str(e).lower() or "resource" in str(e).lower():
        print("Insufficient Resource Credits - need more HP or RC delegation")
```

### Key Usage Summary (beem)
| Operation | Key Required | beem Method |
|-----------|-------------|-------------|
| Post/Comment | Posting | `hive.post()` |
| Vote | Posting | `comment.upvote()`, `hive.vote()` |
| Custom JSON (social) | Posting | `hive.custom_json(required_posting_auths=)` |
| Transfer HIVE/HBD | Active | `account.transfer()` |
| Power Up | Active | `account.transfer_to_vesting()` |
| Delegate HP | Active | `account.delegate_vesting_shares()` |
| Custom JSON (financial) | Active | `hive.custom_json(required_auths=)` |
| Change Keys | Owner | `account.change_password()` |

---

## dhive (JavaScript/TypeScript)

### Installation
```bash
npm install @hiveio/dhive
```

### Core Classes & Initialization

```javascript
const { Client, PrivateKey, Asset } = require("@hiveio/dhive");

// Basic client (read-only)
const client = new Client([
    "https://api.hive.blog",
    "https://api.openhive.network",
    "https://anyx.io",
    "https://api.deathwing.me"
]);

// Create PrivateKey from WIF string
const postingKey = PrivateKey.fromString("5Jxxxxxxxxx_POSTING_WIF");
const activeKey = PrivateKey.fromString("5Jxxxxxxxxx_ACTIVE_WIF");

// Derive key from username + password
const derivedKey = PrivateKey.fromLogin("username", "password", "posting");
```

### Account Operations

```javascript
// Get account info
const [account] = await client.database.getAccounts(["username"]);
console.log(account.balance);         // "123.456 HIVE"
console.log(account.hbd_balance);     // "45.678 HBD"
console.log(account.vesting_shares);  // "12345.678901 VESTS"

// Transfer HIVE
await client.broadcast.transfer({
    from: "sender",
    to: "recipient",
    amount: "1.000 HIVE",
    memo: "payment"
}, activeKey);

// Transfer HBD
await client.broadcast.transfer({
    from: "sender",
    to: "recipient",
    amount: "5.000 HBD",
    memo: "invoice #123"
}, activeKey);

// Transfer to savings
await client.broadcast.transferToSavings({
    from: "myaccount",
    to: "myaccount",
    amount: "100.000 HBD",
    memo: "savings"
}, activeKey);
```

### Posting & Commenting

```javascript
// Submit a new post
await client.broadcast.comment({
    author: "myaccount",
    title: "My Post Title",
    body: "Post body in **markdown**.",
    parent_author: "",                  // empty for top-level post
    parent_permlink: "hive-development", // category/community
    permlink: "my-post-permlink",
    json_metadata: JSON.stringify({
        tags: ["hive", "development"],
        app: "myapp/1.0",
        format: "markdown"
    })
}, postingKey);

// Set post options (beneficiaries, payout type)
const commentOptions = {
    author: "myaccount",
    permlink: "my-post-permlink",
    max_accepted_payout: "1000000.000 HBD",
    percent_hbd: 10000,        // 100% HBD (10000 = 100%)
    allow_votes: true,
    allow_curation_rewards: true,
    extensions: [[0, {         // beneficiaries extension
        beneficiaries: [
            { account: "beneficiary1", weight: 1000 },  // 10%
            { account: "beneficiary2", weight: 500 }     // 5%
        ]
    }]]
};

// Reply to a post
await client.broadcast.comment({
    author: "myaccount",
    title: "",                                   // empty for replies
    body: "Great post!",
    parent_author: "originalauthor",             // author of parent
    parent_permlink: "original-post-permlink",   // permlink of parent
    permlink: "re-originalauthor-my-reply",
    json_metadata: JSON.stringify({ app: "myapp/1.0" })
}, postingKey);
```

### Voting

```javascript
// Upvote at 100% (weight: 10000 = 100%)
await client.broadcast.vote({
    voter: "myaccount",
    author: "postauthor",
    permlink: "post-permlink",
    weight: 10000              // -10000 to 10000 (negative = downvote)
}, postingKey);

// Upvote at 50%
await client.broadcast.vote({
    voter: "myaccount",
    author: "postauthor",
    permlink: "post-permlink",
    weight: 5000
}, postingKey);

// Downvote at 100%
await client.broadcast.vote({
    voter: "myaccount",
    author: "postauthor",
    permlink: "post-permlink",
    weight: -10000
}, postingKey);
```

### Custom JSON

```javascript
// Posting authority custom_json
await client.broadcast.json({
    required_auths: [],
    required_posting_auths: ["myaccount"],
    id: "myapp",
    json: JSON.stringify({ action: "do_something", value: 42 })
}, postingKey);

// Active authority custom_json (e.g., Hive-Engine token transfer)
await client.broadcast.json({
    required_auths: ["myaccount"],
    required_posting_auths: [],
    id: "ssc-mainnet-hive",
    json: JSON.stringify({
        contractName: "tokens",
        contractAction: "transfer",
        contractPayload: {
            symbol: "BEE",
            to: "recipient",
            quantity: "10",
            memo: "token transfer"
        }
    })
}, activeKey);
```

### Streaming Blocks

```javascript
// Stream new blocks as they are produced
for await (const block of client.blockchain.getBlocks()) {
    console.log(`Block ${block.block_id}: ${block.transactions.length} txs`);
    for (const tx of block.transactions) {
        for (const op of tx.operations) {
            if (op[0] === "custom_json") {
                console.log("custom_json:", op[1].id, op[1].json);
            }
        }
    }
}

// Stream only operations of a specific type
for await (const op of client.blockchain.getOperationsStream()) {
    // process each operation
}
```

### Reading Blockchain Data

```javascript
// Get dynamic global properties
const props = await client.database.getDynamicGlobalProperties();
console.log(props.head_block_number);
console.log(props.current_supply);
console.log(props.virtual_supply);

// Get a specific block
const block = await client.database.getBlock(12345678);

// Get content (post/comment)
const content = await client.database.call("get_content", ["author", "permlink"]);

// Get active votes on a post
const votes = await client.database.call("get_active_votes", ["author", "permlink"]);

// Get account history
const history = await client.database.call("get_account_history", ["username", -1, 100]);
```

### Error Handling (dhive)

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");
const client = new Client(["https://api.hive.blog"]);

try {
    await client.broadcast.vote({
        voter: "myaccount",
        author: "author",
        permlink: "permlink",
        weight: 10000
    }, postingKey);
} catch (error) {
    if (error.message.includes("missing required posting authority")) {
        console.error("Wrong key provided - need posting key");
    } else if (error.message.includes("already voted")) {
        console.error("Already voted on this content");
    } else if (error.message.includes("Voting weight is too small")) {
        console.error("Vote weight too low (mana too low)");
    } else if (error.message.includes("rc_plugin")) {
        console.error("Insufficient Resource Credits");
    } else {
        console.error("Broadcast failed:", error.message);
    }
}

// Retry with node failover
const client = new Client([
    "https://api.hive.blog",
    "https://api.openhive.network",
    "https://anyx.io"
], { timeout: 10000, failoverThreshold: 3 });
```

### Common Pitfalls

1. **Amount format**: Always use 3 decimal places for HIVE/HBD: `"1.000 HIVE"`, not `"1 HIVE"`
2. **VESTS format**: Always use 6 decimal places: `"100.000000 VESTS"`
3. **Vote weight**: Range is -10000 to 10000 (not -100 to 100)
4. **Permlink rules**: lowercase, alphanumeric + hyphens only, max 256 chars
5. **json_metadata**: Must be a JSON string, not an object (stringify it)
6. **Beneficiaries**: Must be sorted alphabetically by account name
7. **Post payout window**: 7 days - cannot vote or edit rewards after that
8. **Key types**: Never use active key where posting key suffices - limits exposure
9. **Node failover**: Always provide multiple nodes for redundancy
10. **WebSocket removal**: dhive >= 0.7.0 uses HTTP(2) only, swap `wss://` to `https://`
