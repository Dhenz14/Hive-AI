# Hive SDK Development (beem + dhive)

## Python — beem

### Initialization
```python
from beem import Hive
from beem.account import Account
from beem.comment import Comment
from beem.blockchain import Blockchain

# Read-only (no keys needed)
h = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

# With keys (posting key for social ops, active key for financial ops)
h = Hive(keys=["5K..posting_wif", "5K..active_wif"],
         node=["https://api.hive.blog"])
```

### Common Operations
```python
# Post content
h.post("Title", "Body in **markdown**", author="username",
       tags=["hive", "dev"], self_vote=False)

# Vote (weight: -10000 to 10000, i.e., -100% to 100%)
h.vote(100.0, "@author/permlink", account="voter")  # 100% upvote

# Transfer
from beem.transactionbuilder import TransactionBuilder
h.transfer("recipient", 1.0, "HIVE", memo="payment", account="sender")
h.transfer("recipient", 1.0, "HBD", memo="payment", account="sender")

# Custom JSON (posting auth)
h.custom_json("app_id", json_data={"action": "do_thing"},
              required_posting_auths=["username"])

# Custom JSON (active auth — for financial operations)
h.custom_json("app_id", json_data={"action": "transfer_token"},
              required_auths=["username"])

# Account data
acc = Account("username", blockchain_instance=h)
acc.get_balances()        # HIVE, HBD, VESTS
acc.get_rc_manabar()      # Resource Credits
acc.get_voting_power()    # Current VP (decays on votes, recharges ~20%/day)
acc.history_reverse(limit=100)  # Recent operations

# Stream blocks
bc = Blockchain(blockchain_instance=h)
for op in bc.stream(opNames=["vote", "comment", "transfer"]):
    print(op)
```

### Key Gotchas
- **VESTS not HP**: On-chain uses VESTS. Convert: `h.vests_to_hp(vests_amount)`
- **Permlink format**: Lowercase, hyphens, max 256 chars, must be unique per author
- **3-second blocks**: Hive produces a block every 3 seconds
- **Memo encryption**: Prefix memo with `#` for encrypted memo (uses memo keys)
- **Account creation fee**: ~3 HIVE or use `claim_account` (free with enough RC)

## JavaScript — @hiveio/dhive

### Initialization
```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");
const client = new Client(["https://api.hive.blog", "https://api.deathwing.me"]);
```

### Common Operations
```javascript
// Post
const key = PrivateKey.fromString("5K..posting_wif");
await client.broadcast.comment({
  parent_author: "",        // "" for root post
  parent_permlink: "hive",  // category/community
  author: "username",
  permlink: "my-post-slug",
  title: "My Post",
  body: "Content in **markdown**",
  json_metadata: JSON.stringify({ tags: ["hive", "dev"], app: "myapp/1.0" })
}, key);

// Vote
await client.broadcast.vote({
  voter: "username", author: "author", permlink: "post-slug", weight: 10000
}, key);

// Transfer
const activeKey = PrivateKey.fromString("5K..active_wif");
await client.broadcast.transfer({
  from: "sender", to: "recipient", amount: "1.000 HIVE", memo: "payment"
}, activeKey);

// Custom JSON
await client.broadcast.json({
  id: "app_id",
  required_posting_auths: ["username"],
  required_auths: [],
  json: JSON.stringify({ action: "do_thing" })
}, key);

// Read account
const [acc] = await client.database.getAccounts(["username"]);

// Stream blocks
for await (const block of client.blockchain.getBlocks()) {
  for (const tx of block.transactions) {
    for (const op of tx.operations) {
      console.log(op[0], op[1]);  // [op_type, op_data]
    }
  }
}
```

### Amount Formatting
- Always 3 decimal places: `"1.000 HIVE"`, `"0.500 HBD"` — wrong format = rejected
- VESTS use 6 decimals: `"1000.000000 VESTS"`

### Node Selection
| Node | Notes |
|------|-------|
| api.hive.blog | Official, rate-limited |
| api.deathwing.me | Reliable, generous limits |
| api.openhive.network | Community-run |
| rpc.ecency.com | Ecency's node |

Always use 2+ nodes for failover. Check health: `GET /` returns server time.
