"""Deep Hive blockchain development training pairs: SDK, economics, security, layer2."""

PAIRS = [
    # ── hive_sdk (pairs 1-5) ──────────────────────────────────────────────
    (
        "hive_deep1_01",
        r'''How do I post an article to the Hive blockchain using beem in Python? I want to set tags, beneficiaries, and choose a 100% HP payout.''',
        r'''<think>
The user wants to create a root post on Hive using beem. I need to cover:
1. Initializing Hive with the posting key
2. Using h.post() with the right parameters
3. Setting beneficiaries (list of dicts with account + weight in basis points)
4. Setting percent_hbd=0 for 100% HP payout
5. Mentioning permlink rules, json_metadata, and key gotchas
</think>

Here is how to publish a post on Hive with beem, including beneficiaries and a 100% HP payout option.

```python
from beem import Hive
from beem.comment import Comment

# Initialize with your posting key (posting auth is sufficient for posts)
hive = Hive(
    keys=["5K...your_posting_wif"],
    node=["https://api.hive.blog", "https://api.deathwing.me"]
)

# Publish a post with full options
hive.post(
    title="Building on Hive with Python",
    body="""## Introduction\n\nThis is my post body in **markdown**.\n\n- Supports full markdown\n- Including code blocks, images, and tables""",
    author="yourusername",
    tags=["hive-dev", "python", "tutorial", "coding"],  # first tag = category
    self_vote=False,
    # 100% HP payout (percent_hbd=0 means no HBD, all HP)
    percent_hbd=0,
    # Route 5% of rewards to an app account, 3% to a curator
    beneficiaries=[
        {"account": "myapp", "weight": 500},    # 5.00%
        {"account": "curator1", "weight": 300},  # 3.00%
    ],
)

print("Post published successfully!")

# Verify it was created
post = Comment("@yourusername/building-on-hive-with-python",
               blockchain_instance=hive)
print(f"Title: {post['title']}")
print(f"Pending payout: {post['pending_payout_value']}")
```

**Key details:**

1. **Tags**: The first tag becomes the post's category (shown in the URL path). Maximum 8 tags, lowercase, no spaces — use hyphens.

2. **Beneficiaries**: Weights are in basis points (100 = 1%). They must be sorted alphabetically by account name. Beneficiaries are set at post time and cannot be changed afterward. Total beneficiary weight cannot exceed 10000 (100%).

3. **Payout options**: `percent_hbd=0` means 100% Hive Power. The default `percent_hbd=10000` means the standard 50/50 split (50% HBD + 50% HP). You can also set `max_accepted_payout="0.000 HBD"` to decline all rewards.

4. **Permlink**: Auto-generated from the title (lowercase, hyphens, max 256 chars). Must be unique per author — posting twice with the same permlink edits the original.

5. **Auth level**: Posting key is sufficient for creating posts. Never use your active or owner key for social operations.

6. **json_metadata**: beem auto-generates this from your tags, but you can pass `json_metadata` manually for custom app fields like `{"app": "myapp/1.0", "format": "markdown"}`.'''
    ),

    (
        "hive_deep1_02",
        r'''Show me how to stream live blockchain operations from Hive using dhive in JavaScript. I want to filter for transfers and votes only.''',
        r'''<think>
The user wants real-time streaming of Hive operations using @hiveio/dhive in JS. I need to show:
1. Client setup with multiple nodes for failover
2. Using client.blockchain.getOperationsStream() or iterating blocks
3. Filtering for specific operation types (transfer, vote)
4. Proper error handling and reconnection logic
The dhive library provides getBlockStream() and getOperationsStream() methods.
</think>

Here is how to stream live Hive operations filtered to transfers and votes using `@hiveio/dhive`:

```javascript
const { Client } = require("@hiveio/dhive");

// Use multiple nodes for failover
const client = new Client([
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://api.openhive.network"
]);

async function streamOperations() {
    console.log("Starting Hive operation stream...");

    // Stream from the latest irreversible block (safe from microforks)
    const stream = client.blockchain.getOperationsStream({
        blockchainMode: "irreversible"  // or "latest" for real-time
    });

    stream.on("data", (operation) => {
        const [opType, opData] = [operation.op[0], operation.op[1]];

        if (opType === "transfer") {
            console.log(
                `[Transfer] ${opData.from} -> ${opData.to}: ` +
                `${opData.amount} | memo: ${opData.memo}`
            );
        }

        if (opType === "vote") {
            const pct = (opData.weight / 100).toFixed(0);
            console.log(
                `[Vote] ${opData.voter} voted ${pct}% on ` +
                `@${opData.author}/${opData.permlink}`
            );
        }
    });

    stream.on("error", (err) => {
        console.error("Stream error:", err.message);
        // Reconnect after a delay
        setTimeout(streamOperations, 5000);
    });

    stream.on("end", () => {
        console.log("Stream ended, reconnecting...");
        setTimeout(streamOperations, 1000);
    });
}

streamOperations();
```

**Alternative: Block-by-block iteration** for more control:

```javascript
async function streamBlocks() {
    const stream = client.blockchain.getBlockStream({
        blockchainMode: "latest"
    });

    stream.on("data", (block) => {
        const blockNum = block.block_id
            ? parseInt(block.block_id.slice(0, 8), 16)
            : "?";

        for (const tx of block.transactions) {
            for (const [opType, opData] of tx.operations) {
                if (opType === "transfer" || opType === "vote") {
                    console.log(`Block ${blockNum}: ${opType}`, opData);
                }
            }
        }
    });
}
```

**Important considerations:**

1. **blockchainMode**: Use `"irreversible"` for financial processing (confirmed by 2/3 of witnesses, ~45 seconds behind). Use `"latest"` for real-time UIs but handle potential microfork reversals.

2. **Block timing**: Hive produces a block every 3 seconds, so expect a steady stream of data.

3. **Amount format**: Transfer amounts come as strings like `"1.000 HIVE"` or `"5.000 HBD"` — always 3 decimal places.

4. **Vote weight**: Ranges from -10000 (100% downvote) to 10000 (100% upvote). Divide by 100 for percentage.

5. **Reconnection**: Network issues will drop the stream. Always implement reconnection logic with exponential backoff in production.

6. **Memory**: Long-running streams accumulate event listeners if you restart without cleanup. Call `stream.destroy()` before reconnecting.'''
    ),

    (
        "hive_deep1_03",
        r'''How do I read account information and balances on Hive using beem? I need to get HP, liquid HIVE, HBD, resource credits, and voting power.''',
        r'''<think>
The user wants to read comprehensive account data using beem. Key things to cover:
1. Account initialization and basic properties
2. Balance retrieval (HIVE, HBD, VESTS -> HP conversion)
3. RC manabar reading
4. Voting power reading
5. The VESTS vs HP distinction is critical — on-chain everything is VESTS
</think>

Here is how to read all key account data using beem:

```python
from beem import Hive
from beem.account import Account

# Read-only access — no keys needed
hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

def get_account_info(username):
    """Fetch comprehensive account information from Hive."""
    acc = Account(username, blockchain_instance=hive)

    # === Balances ===
    balances = acc.get_balances()
    # Returns dict with 'available', 'savings', 'rewards', 'total'

    # Liquid balances
    liquid_hive = acc["balance"]               # e.g., Amount("12.345 HIVE")
    liquid_hbd = acc["hbd_balance"]            # e.g., Amount("5.678 HBD")

    # Hive Power (stored on-chain as VESTS, display as HP)
    vesting_shares = float(acc["vesting_shares"])    # raw VESTS
    hp = hive.vests_to_hp(vesting_shares)            # converted to HP

    # Include delegations
    received_vests = float(acc["received_vesting_shares"])
    delegated_vests = float(acc["delegated_vesting_shares"])
    effective_hp = hive.vests_to_hp(
        vesting_shares + received_vests - delegated_vests
    )

    # Savings (HBD savings earn 20% APR)
    savings_hive = acc["savings_balance"]
    savings_hbd = acc["savings_hbd_balance"]

    # === Resource Credits ===
    rc = acc.get_rc_manabar()
    rc_current = rc["current_mana"]
    rc_max = rc["max_mana"]
    rc_pct = rc["current_pct"]  # 0-100

    # === Voting Power ===
    vp = acc.get_voting_power()  # 0-100, regenerates 20%/day

    # === Print Summary ===
    print(f"=== Account: @{username} ===")
    print(f"Reputation: {acc.get_reputation():.0f}")
    print(f"\n-- Balances --")
    print(f"Liquid HIVE:   {liquid_hive}")
    print(f"Liquid HBD:    {liquid_hbd}")
    print(f"Hive Power:    {hp:,.3f} HP ({vesting_shares:,.6f} VESTS)")
    print(f"Effective HP:  {effective_hp:,.3f} HP (with delegations)")
    print(f"Savings HIVE:  {savings_hive}")
    print(f"Savings HBD:   {savings_hbd}")
    print(f"\n-- Resource Credits --")
    print(f"RC: {rc_current:,} / {rc_max:,} ({rc_pct:.1f}%)")
    print(f"\n-- Voting --")
    print(f"Voting Power:  {vp:.1f}%")

    return {
        "liquid_hive": float(liquid_hive),
        "liquid_hbd": float(liquid_hbd),
        "hp": hp,
        "effective_hp": effective_hp,
        "rc_pct": rc_pct,
        "voting_power": vp,
    }

info = get_account_info("blocktrades")
```

**Critical concepts:**

1. **VESTS vs HP**: The blockchain stores staked power as VESTS (6 decimal places). HP is a display unit. The conversion ratio changes over time as new HIVE is printed. Always use `hive.vests_to_hp()` — never hardcode a ratio.

2. **Effective HP**: Your actual influence = own HP + received delegations - outgoing delegations. This determines your vote value and RC capacity.

3. **RC regeneration**: Starts at 100% for a fully charged account. Each operation costs RC proportional to its size. Regenerates linearly at 20% per day (full recharge in 5 days).

4. **Voting power**: 100% means full strength. Each 100% vote costs 2% VP. Regenerates at 20% per day. Accounts with under 500 HP can only vote at 100% weight.

5. **Savings withdrawal**: HBD in savings earns 20% APR. Withdrawing requires a 3-day waiting period for security.'''
    ),

    (
        "hive_deep1_04",
        r'''How do I send a HIVE or HBD transfer with an encrypted memo using beem? Explain how memo encryption works on Hive.''',
        r'''<think>
The user wants to transfer HIVE/HBD with encrypted memos. Key concepts:
1. Encrypted memos use the memo key pair (both sender and recipient)
2. Prefix the memo with '#' to trigger encryption
3. beem handles the Diffie-Hellman shared secret derivation automatically
4. Need active key for transfers, memo key for encryption/decryption
5. Both sender and recipient can decrypt (shared secret from ECDH)
</think>

Here is how to send transfers with encrypted memos on Hive using beem:

```python
from beem import Hive
from beem.account import Account
from beem.memo import Memo

# You need BOTH active key (for transfer) and memo key (for encryption)
hive = Hive(
    keys=[
        "5K...your_active_wif",   # required for transfers
        "5K...your_memo_wif"      # required for memo encryption
    ],
    node=["https://api.hive.blog", "https://api.deathwing.me"]
)

# === Send transfer with encrypted memo ===
# Prefix the memo with '#' to encrypt it
hive.transfer(
    to="recipient",
    amount=1.0,
    asset="HIVE",
    memo="#This is a secret message only sender and recipient can read",
    account="sender"
)

# Works the same for HBD
hive.transfer(
    to="recipient",
    amount=5.0,
    asset="HBD",
    memo="#Payment for invoice #1234 — confidential",
    account="sender"
)
```

**Decrypting received memos:**

```python
# Initialize with your memo private key to decrypt
hive = Hive(
    keys=["5K...your_memo_wif"],
    node=["https://api.hive.blog"]
)

acc = Account("yourusername", blockchain_instance=hive)

# Iterate recent transfers and decrypt memos
for op in acc.history_reverse(limit=50):
    if op["type"] == "transfer" and op["memo"].startswith("#"):
        memo = Memo(blockchain_instance=hive)
        try:
            decrypted = memo.decrypt(op["memo"])
            print(f"From {op['from']}: {decrypted}")
        except Exception as e:
            # Can't decrypt if it wasn't addressed to you
            print(f"Cannot decrypt memo from {op['from']}: {e}")
```

**How memo encryption works under the hood:**

1. **Key derivation**: Hive uses Elliptic Curve Diffie-Hellman (ECDH). The sender combines their memo private key with the recipient's memo public key to derive a shared secret. The recipient does the reverse (their private + sender's public) and gets the same shared secret.

2. **Encryption**: The shared secret is used as an AES key to encrypt the memo content. A random nonce is generated for each memo.

3. **On-chain format**: The encrypted memo is stored as `#` followed by the base58-encoded ciphertext. It includes the sender's and recipient's memo public keys so either party can identify which key pair to use for decryption.

4. **Privacy**: Only the sender and recipient can decrypt. Witnesses, API nodes, and other users see only the encrypted blob. However, the transfer amount, sender, and recipient are always public.

**Important notes:**

- **Amount format**: Always 3 decimal places for HIVE and HBD (`"1.000 HIVE"`). beem handles this when you pass a float.
- **Active key required**: Transfers need active authority. The memo key is only for encryption/decryption, not for authorizing the transaction.
- **Unencrypted memos**: Without the `#` prefix, memos are stored in plaintext on-chain and visible to everyone forever.
- **Memo key compromise**: If someone gets your memo key, they can read your encrypted memos but cannot move your funds or post on your behalf. This is why Hive has separate key levels.
- **Public key lookup**: beem automatically fetches the recipient's memo public key from their account data on-chain.'''
    ),

    (
        "hive_deep1_05",
        r'''How do I build and broadcast a multi-operation transaction on Hive using beem's TransactionBuilder? I want to vote, comment, and transfer in a single atomic transaction.''',
        r'''<think>
The user wants to batch multiple operations into one transaction using beem's TransactionBuilder. Key points:
1. TransactionBuilder lets you compose multiple ops into one tx
2. Each op needs the correct auth level — if any op needs active key, the whole tx needs active signing
3. A transfer requires active key, vote and comment need posting key — so this tx needs both
4. The tx is atomic — all ops succeed or all fail
5. Show proper operation construction with beembase.operations
</think>

Here is how to build a multi-operation atomic transaction using beem's `TransactionBuilder`:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import (
    Vote, Comment, Transfer
)
import json

# Need both posting and active keys since we're mixing op types
hive = Hive(
    keys=[
        "5K...your_posting_wif",
        "5K...your_active_wif"
    ],
    node=["https://api.hive.blog", "https://api.deathwing.me"]
)

# Create a transaction builder
tx = TransactionBuilder(blockchain_instance=hive)

# Operation 1: Vote on a post (requires posting auth)
tx.appendOps(Vote(**{
    "voter": "yourusername",
    "author": "someauthor",
    "permlink": "great-post-about-hive",
    "weight": 10000  # 100% upvote (-10000 to 10000)
}))

# Operation 2: Leave a comment (requires posting auth)
tx.appendOps(Comment(**{
    "parent_author": "someauthor",          # reply to this author
    "parent_permlink": "great-post-about-hive",  # on this post
    "author": "yourusername",
    "permlink": "re-great-post-about-hive-reply1",  # unique permlink
    "title": "",  # empty for comments (only root posts have titles)
    "body": "Great article! Thanks for sharing this insight.",
    "json_metadata": json.dumps({
        "app": "myapp/1.0",
        "tags": ["hive"]
    })
}))

# Operation 3: Transfer HIVE (requires active auth)
tx.appendOps(Transfer(**{
    "from": "yourusername",
    "to": "someauthor",
    "amount": "1.000 HIVE",  # must be string with 3 decimals
    "memo": "Tip for your great post!"
}))

# Sign with all necessary keys and broadcast
tx.appendSigner("yourusername", "posting")  # for vote + comment
tx.appendSigner("yourusername", "active")   # for transfer
tx.sign()
result = tx.broadcast()

print(f"Transaction broadcast! Block: {result['block_num']}")
print(f"Transaction ID: {result['id']}")
```

**Why use TransactionBuilder?**

1. **Atomicity**: All operations in a single transaction either succeed or fail together. If the transfer fails (insufficient balance), the vote and comment are also rolled back.

2. **Efficiency**: One transaction = one signature verification, one block inclusion. Three separate calls would use 3x the RC and risk partial failures.

3. **Ordering**: Operations execute in the order you append them, within the same block.

**Important rules:**

- **Amount format**: Transfer amounts must be strings with exactly 3 decimal places: `"1.000 HIVE"`, `"0.500 HBD"`. Using a float or wrong decimals will fail.

- **Auth levels**: A transaction is signed with all required authority levels. If any operation requires active auth, you must provide the active key. Posting-only operations can be signed with just the posting key.

- **Transaction size limit**: Max 65,536 bytes per transaction. For large batches, split across multiple transactions.

- **Permlink uniqueness**: Comment permlinks must be unique per author. A common pattern is `re-{parent_permlink}-{timestamp}` to avoid collisions.

- **Expiration**: Transactions expire ~30 seconds after construction by default. TransactionBuilder handles this, but if you build a tx and wait too long before broadcasting, it will be rejected.

- **Error handling**: Wrap `broadcast()` in try/except. Common errors include insufficient RC, missing authority, duplicate permlink, or wrong amount format.

```python
try:
    result = tx.broadcast()
except Exception as e:
    if "missing required active authority" in str(e):
        print("Active key not provided or incorrect")
    elif "insufficient RC" in str(e).lower():
        print("Not enough Resource Credits — stake more HP")
    else:
        raise
```'''
    ),

    # ── hive_economics (pairs 6-10) ──────────────────────────────────────
    (
        "hive_deep1_06",
        r'''How do Resource Credits (RC) work on Hive? How do I check an account's RC, estimate if they can afford an operation, and delegate RC to a new user?''',
        r'''<think>
Resource Credits are Hive's feeless transaction system. I need to cover:
1. RC is derived from HP stake — more HP = more RC
2. RC regenerates at 20% per day (linear)
3. Different operations cost different amounts of RC
4. RC delegation (separate from HP delegation, available since HF26)
5. How to check RC with beem and dhive
6. Practical estimation of whether an account can afford an operation
</think>

Resource Credits (RC) are Hive's alternative to transaction fees. Instead of paying per transaction, you stake HP once and receive a regenerating bandwidth quota.

**How RC works:**

- Your max RC is proportional to your effective HP (own + received delegations - outgoing)
- RC regenerates linearly at 20% per day (full recharge from 0% takes 5 days)
- Each operation consumes RC based on its size and type
- Zero HP = zero RC = cannot transact

```python
from beem import Hive
from beem.account import Account
from beem.rc import RC

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

# === Check account RC ===
acc = Account("username", blockchain_instance=hive)
rc_manabar = acc.get_rc_manabar()

print(f"Current RC: {rc_manabar['current_mana']:,}")
print(f"Max RC:     {rc_manabar['max_mana']:,}")
print(f"Percentage: {rc_manabar['current_pct']:.2f}%")

# === Estimate RC costs for operations ===
rc = RC(blockchain_instance=hive)

# Cost of a comment/post (~1.2 billion RC)
comment_cost = rc.comment(tx_size=500)  # approximate tx size in bytes
print(f"Comment cost: {comment_cost:,} RC")

# Cost of a vote (~100 million RC)
vote_cost = rc.vote(tx_size=210)
print(f"Vote cost: {vote_cost:,} RC")

# Cost of a transfer (~400 million RC)
transfer_cost = rc.transfer(tx_size=250, market_op_count=1)
print(f"Transfer cost: {transfer_cost:,} RC")

# === Can this account afford the operation? ===
def can_afford(account_name, operation_cost):
    acc = Account(account_name, blockchain_instance=hive)
    rc_bar = acc.get_rc_manabar()
    current = rc_bar["current_mana"]
    if current >= operation_cost:
        ops_remaining = current // operation_cost
        print(f"Yes — can afford ~{ops_remaining} more of these operations")
        return True
    else:
        deficit = operation_cost - current
        # RC regenerates at max_mana * 0.2 per day
        regen_rate = rc_bar["max_mana"] * 0.2 / 86400  # per second
        if regen_rate > 0:
            wait_seconds = deficit / regen_rate
            print(f"No — need to wait ~{wait_seconds/60:.0f} minutes")
        else:
            print("No — account has zero HP, cannot regenerate RC")
        return False

can_afford("username", comment_cost)
```

**RC Delegation (since HF26):**

RC delegation lets you give bandwidth to new users without delegating your HP (and thus your voting influence):

```python
# Delegate RC to a new user (requires posting auth)
hive_with_keys = Hive(
    keys=["5K...your_posting_wif"],
    node=["https://api.hive.blog"]
)

# Delegate 5 billion RC (enough for ~4 posts per day)
hive_with_keys.custom_json(
    "rc",
    json_data={
        "action": "delegate_rc",
        "delegatees": ["newuser1", "newuser2"],
        "max_rc": 5000000000  # 5 billion RC each
    },
    required_posting_auths=["delegator"]
)

# Remove RC delegation
hive_with_keys.custom_json(
    "rc",
    json_data={
        "action": "delegate_rc",
        "delegatees": ["newuser1"],
        "max_rc": 0  # set to 0 to remove
    },
    required_posting_auths=["delegator"]
)
```

**Approximate RC costs by operation:**

| Operation | RC Cost | HP Needed for 10/day |
|-----------|---------|---------------------|
| Vote | ~100M | ~1 HP |
| Comment/Post | ~1.2B | ~6 HP |
| Transfer | ~400M | ~3 HP |
| Custom JSON | ~200M-1B | ~2-5 HP |
| Claim account | ~5T | ~5000+ HP |

**Key points:**
- RC delegation does not reduce the delegator's voting power — only HP delegation does that
- New accounts with 0 HP rely entirely on RC delegation to transact
- `claim_account` costs ~5 trillion RC, used to create free account tokens
- RC costs scale with transaction payload size — a 4KB custom_json costs more than a 200-byte vote'''
    ),

    (
        "hive_deep1_07",
        r'''Explain Hive's curation reward system. How are curation rewards calculated, and how should I time my votes to maximize them? Show how to check curation rewards with beem.''',
        r'''<think>
Curation rewards on Hive. Key points to cover:
1. 50/50 split between author and curators (since HF25)
2. Reverse auction was removed in HF25 — no penalty for early voting
3. Curation rewards proportional to rshares (your HP-weighted vote)
4. Earlier votes on posts that later become popular earn more
5. Dust threshold — votes worth < ~$0.02 are ignored
6. How to check curation rewards with beem
</think>

Hive splits post rewards 50/50 between the author and curators (voters). Understanding how curation works helps you maximize returns on your voting activity.

**How curation rewards are calculated:**

1. Each vote adds `rshares` (reward shares) to the post, proportional to the voter's effective HP and vote weight
2. At payout (7 days), the curator pool (50% of total rewards) is distributed to voters proportional to their rshares
3. Earlier voters on posts that accumulate more votes later earn a larger share — this incentivizes content discovery

```python
from beem import Hive
from beem.account import Account
from beem.comment import Comment
import datetime

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

# === Check pending curation on a specific post ===
post = Comment("@author/post-permlink", blockchain_instance=hive)
print(f"Total pending payout: {post['pending_payout_value']}")
print(f"Active votes: {len(post.get_votes())}")

# Examine individual vote details
for vote in post.get_votes():
    print(f"  {vote['voter']}: {vote['rshares']:,} rshares "
          f"({vote['percent']/100:.0f}%)")

# === Check your curation reward history ===
acc = Account("yourusername", blockchain_instance=hive)

total_curation = 0
curation_ops = []
for op in acc.history_reverse(limit=500):
    if op["type"] == "curation_reward":
        hp_reward = hive.vests_to_hp(
            float(op["reward"].split(" ")[0])  # "1.234567 VESTS"
        )
        total_curation += hp_reward
        curation_ops.append({
            "post": f"@{op['comment_author']}/{op['comment_permlink']}",
            "reward_hp": hp_reward,
            "timestamp": op["timestamp"]
        })

print(f"\nRecent curation rewards: {total_curation:.3f} HP")
for c in curation_ops[:10]:
    print(f"  {c['reward_hp']:.4f} HP from {c['post']}")

# === Estimate your vote value ===
acc = Account("yourusername", blockchain_instance=hive)
vp = acc.get_voting_power()
effective_vests = (
    float(acc["vesting_shares"]) +
    float(acc["received_vesting_shares"]) -
    float(acc["delegated_vesting_shares"])
)

# Get reward fund data for USD estimate
reward_fund = hive.get_reward_funds()
recent_claims = float(reward_fund["recent_claims"])
reward_balance = float(reward_fund["reward_balance"])

# Get price feed
price_feed = hive.get_current_median_history()
hive_price = float(price_feed["base"]) / float(price_feed["quote"])

# Simplified vote value estimate (100% vote)
rshares = effective_vests * 1e6 * (vp / 100) * 0.02
vote_value_hive = rshares * reward_balance / recent_claims
vote_value_usd = vote_value_hive * hive_price
print(f"\nYour 100% vote is worth ~${vote_value_usd:.4f}")
```

**Voting strategy tips:**

1. **No reverse auction penalty**: Since HF25, you earn full curation regardless of when you vote in the 7-day window. Vote whenever you find good content.

2. **Early voting advantage**: If you vote on a post before it gets other large votes, your share of the curation pool is larger. Voting after whales pile on means your relative share shrinks.

3. **Dust threshold**: If your vote's rshares value is below ~$0.02, it does not count toward rewards at all. Accounts with very low HP should vote at 100% weight to clear the dust threshold.

4. **Vote weight management**: Each 100% upvote costs 2% of your voting power. At 100% VP, you can cast about 10 full-strength votes per day while maintaining equilibrium. Voting at 50% weight costs 1% VP.

5. **Self-voting**: Technically allowed — you earn curation on your own posts. However, the community generally discourages excessive self-voting.

6. **Payout timing**: Rewards are calculated and paid exactly 7 days after the post is created. Late votes (near the 7-day mark) earn the same curation share as early votes with equal rshares, but early voters benefit from the "content discovery" premium.'''
    ),

    (
        "hive_deep1_08",
        r'''How do I power up HIVE, power down HP, and manage HP delegations programmatically with beem? Include the math on VESTS conversion.''',
        r'''<think>
This covers the staking/unstaking mechanics on Hive:
1. Power up: instant HIVE -> HP (VESTS)
2. Power down: 13 weekly installments HP -> HIVE
3. Delegation: lend HP to another account
4. VESTS <-> HP conversion math
5. Undelegation cooldown (5 days)
</think>

Here is how to manage Hive Power staking, unstaking, and delegations using beem:

```python
from beem import Hive
from beem.account import Account

hive = Hive(
    keys=["5K...your_active_wif"],  # active key needed for all power ops
    node=["https://api.hive.blog", "https://api.deathwing.me"]
)

# ═══ POWER UP (HIVE → HP) ═══
# Instant conversion. Minimum 0.001 HIVE.
hive.power_up(amount=100.0, account="yourusername")
print("Powered up 100 HIVE → HP")

# Power up to a DIFFERENT account (gift HP)
hive.power_up(amount=50.0, account="yourusername", to="friendaccount")
print("Powered up 50 HIVE to @friendaccount")

# ═══ POWER DOWN (HP → HIVE) ═══
# Converts HP back to liquid HIVE over 13 weekly installments.
# Each week, 1/13 of the total is deposited as liquid HIVE.
hive.power_down(amount=1300.0, account="yourusername")
print("Started power down: 1300 HP over 13 weeks (100 HP/week)")

# Cancel power down
hive.power_down(amount=0, account="yourusername")
print("Power down cancelled — remaining HP stays staked")

# Check power down status
acc = Account("yourusername", blockchain_instance=hive)
if float(acc["vesting_withdraw_rate"]) > 0:
    weekly_vests = float(acc["vesting_withdraw_rate"])
    weekly_hp = hive.vests_to_hp(weekly_vests)
    print(f"Active power down: {weekly_hp:.3f} HP per week")
    print(f"Next payout: {acc['next_vesting_withdrawal']}")
else:
    print("No active power down")

# ═══ DELEGATION ═══
# Delegate HP to another account (they get voting + RC power, you keep ownership)
# Must specify in VESTS on-chain, but beem can accept HP amount

# First, convert HP to VESTS for the operation
hp_to_delegate = 500.0
vests_to_delegate = hive.hp_to_vests(hp_to_delegate)
vests_str = f"{vests_to_delegate:.6f} VESTS"

hive.delegate_vesting_shares(
    to_account="delegatee",
    vesting_shares=vests_str,
    account="yourusername"
)
print(f"Delegated {hp_to_delegate:.3f} HP ({vests_str}) to @delegatee")

# Remove delegation (5-day cooldown before VESTS return)
hive.delegate_vesting_shares(
    to_account="delegatee",
    vesting_shares="0.000000 VESTS",
    account="yourusername"
)
print("Undelegated — HP returns after 5-day cooldown")

# ═══ CHECK DELEGATIONS ═══
acc = Account("yourusername", blockchain_instance=hive)

# Outgoing delegations
outgoing = acc.get_vesting_delegations()
print("\nOutgoing delegations:")
for d in outgoing:
    hp = hive.vests_to_hp(float(d["vesting_shares"]))
    print(f"  → @{d['delegatee']}: {hp:.3f} HP")

# Expiring delegations (returning after undelegation)
expiring = acc.get_expiring_vesting_delegations()
for d in expiring:
    hp = hive.vests_to_hp(float(d["vesting_shares"]))
    print(f"  Returning: {hp:.3f} HP on {d['expiration']}")
```

**VESTS ↔ HP conversion math:**

```python
# The conversion ratio comes from global chain properties
props = hive.get_dynamic_global_properties()
total_vesting_fund = float(props["total_vesting_fund_hive"])  # total HIVE staked
total_vesting_shares = float(props["total_vesting_shares"])   # total VESTS

# HP = VESTS × (total_vesting_fund / total_vesting_shares)
def vests_to_hp(vests):
    return vests * (total_vesting_fund / total_vesting_shares)

def hp_to_vests(hp):
    return hp * (total_vesting_shares / total_vesting_fund)

# Example: 1,000,000 VESTS ≈ ~530 HP (ratio changes as new HIVE is printed)
print(f"1M VESTS = {vests_to_hp(1_000_000):.3f} HP")
print(f"100 HP = {hp_to_vests(100):.6f} VESTS")
```

**Key rules:**

1. **Power up** is instant. There is no waiting period.
2. **Power down** takes 13 weeks. You receive 1/13 each week. Starting a new power down replaces the previous one.
3. **Delegation** takes effect immediately for the recipient. When you undelegate, there is a 5-day cooldown before the VESTS return to your account.
4. **VESTS format**: On-chain amounts use 6 decimal places (`"1000.000000 VESTS"`). Using wrong precision will cause the transaction to be rejected.
5. **Delegation does not transfer ownership**: You can undelegate at any time. The delegatee cannot power down or transfer your delegated HP.'''
    ),

    (
        "hive_deep1_09",
        r'''How do HBD savings work on Hive? Show me how to deposit, withdraw, and calculate the 20% APR interest using beem.''',
        r'''<think>
HBD savings is a key Hive economic feature:
1. HBD in savings earns 20% APR (set by witness consensus)
2. Deposit is instant, withdrawal has 3-day wait
3. Interest accrues continuously, paid out on any savings operation
4. Show beem code for deposit, withdraw, and interest calculation
</think>

HBD (Hive Backed Dollars) in savings earns 20% APR — one of the highest stable yields in crypto. Here is how to manage it programmatically:

```python
from beem import Hive
from beem.account import Account
from datetime import datetime, timedelta

hive = Hive(
    keys=["5K...your_active_wif"],  # active key for financial ops
    node=["https://api.hive.blog", "https://api.deathwing.me"]
)

# ═══ DEPOSIT HBD TO SAVINGS ═══
# Instant — starts earning interest immediately
hive.transfer_to_savings(
    account="yourusername",
    amount=100.0,
    asset="HBD",
    memo="Monthly savings deposit"
)
print("Deposited 100 HBD to savings")

# You can also save HIVE (but it earns 0% — only HBD earns interest)
hive.transfer_to_savings(
    account="yourusername",
    amount=50.0,
    asset="HIVE",
    memo="HIVE savings for security"
)

# ═══ WITHDRAW FROM SAVINGS ═══
# 3-day waiting period for security (prevents instant theft if key compromised)
hive.transfer_from_savings(
    account="yourusername",
    request_id=1,  # unique integer per pending withdrawal
    amount=50.0,
    asset="HBD",
    memo="Withdrawal for expenses"
)
print("Withdrawal initiated — arrives in 3 days")

# Cancel a pending withdrawal (before 3 days elapse)
hive.cancel_transfer_from_savings(
    account="yourusername",
    request_id=1
)

# ═══ CHECK SAVINGS BALANCE ═══
acc = Account("yourusername", blockchain_instance=hive)
savings_hbd = acc["savings_hbd_balance"]
savings_hive = acc["savings_balance"]
print(f"Savings: {savings_hbd} | {savings_hive}")

# Last interest payment timestamp
last_interest = acc["savings_hbd_last_interest_payment"]
print(f"Last interest payment: {last_interest}")

# ═══ ESTIMATE INTEREST EARNINGS ═══
def estimate_hbd_interest(hbd_amount, days, apr=0.20):
    """Calculate expected HBD savings interest.

    Interest accrues continuously but is paid out whenever
    a savings operation occurs (deposit, withdraw, or manual claim).
    """
    daily_rate = apr / 365
    interest = hbd_amount * daily_rate * days
    return round(interest, 3)

# Examples
balance = 1000.0  # 1000 HBD in savings
print(f"\n1000 HBD in savings at 20% APR:")
print(f"  30 days:  {estimate_hbd_interest(balance, 30):.3f} HBD")
print(f"  90 days:  {estimate_hbd_interest(balance, 90):.3f} HBD")
print(f"  365 days: {estimate_hbd_interest(balance, 365):.3f} HBD")

# ═══ CHECK PENDING WITHDRAWALS ═══
# Look for pending savings withdrawals in account history
for op in acc.history_reverse(limit=100):
    if op["type"] == "transfer_from_savings":
        print(f"Pending withdrawal: {op['amount']} "
              f"(request_id: {op['request_id']})")
    if op["type"] == "fill_transfer_from_savings":
        print(f"Completed withdrawal: {op['amount']} "
              f"at {op['timestamp']}")
```

**How HBD savings interest works:**

1. **APR is set by witnesses**: Currently 20%, voted on by the top 21 witnesses. It can change via witness consensus.

2. **Continuous accrual**: Interest accrues every second, but it is only credited to your balance when a savings operation triggers it (deposit, withdrawal, or any interaction with your savings).

3. **Compounding**: Interest is simple, not compound. To compound, periodically trigger a savings operation (even depositing 0.001 HBD recalculates and credits accrued interest).

4. **HBD peg**: HBD is designed to track $1 USD via the median price feed from witnesses. The 20% APR is on the dollar-pegged value.

5. **3-day withdrawal delay**: This is a security feature. If your active key is compromised, you have 3 days to notice and use your owner key to change your active key before the attacker can withdraw your savings.

6. **request_id**: Each pending withdrawal needs a unique integer ID. You can have multiple pending withdrawals simultaneously with different IDs.

7. **HIVE savings**: You can store HIVE in savings for the 3-day withdrawal security, but HIVE in savings earns 0% interest — only HBD earns the APR.'''
    ),

    (
        "hive_deep1_10",
        r'''How do I set up beneficiaries on a Hive post and calculate how rewards are split between the author, curators, and beneficiaries?''',
        r'''<think>
Beneficiaries and reward splitting on Hive:
1. Beneficiaries are set at post creation time, immutable after
2. Weights in basis points (100 = 1%), must be sorted alphabetically
3. Beneficiaries come out of the AUTHOR's share (not curator's)
4. Show the math: total reward -> 50% curator / 50% author -> author share minus beneficiaries
5. Code examples with beem
</think>

Beneficiaries let you automatically route a percentage of a post's author rewards to other accounts. Here is how they work and how to calculate the full reward split:

```python
from beem import Hive
from beem.comment import Comment

hive = Hive(
    keys=["5K...your_posting_wif"],
    node=["https://api.hive.blog", "https://api.deathwing.me"]
)

# ═══ POST WITH BENEFICIARIES ═══
hive.post(
    title="My App-Powered Post",
    body="Content goes here in **markdown**.",
    author="yourusername",
    tags=["hive", "development"],
    beneficiaries=[
        # MUST be sorted alphabetically by account name
        {"account": "app_revenue", "weight": 500},   # 5.00%
        {"account": "community_fund", "weight": 1000}, # 10.00%
        {"account": "referrer", "weight": 300},        # 3.00%
    ],
    # Optional: 50/50 (default) or 100% HP
    percent_hbd=10000  # 50/50 split (default)
)
```

**Reward calculation breakdown:**

```python
def calculate_reward_split(total_payout_usd, beneficiaries,
                            percent_hbd=10000):
    """Calculate how rewards are split on a Hive post.

    Args:
        total_payout_usd: Total post value at payout (e.g., $10.00)
        beneficiaries: List of {"account": str, "weight": int} dicts
                       (weight in basis points, 100 = 1%)
        percent_hbd: 10000 = 50/50 (default), 0 = 100% HP
    """
    # Step 1: Curator/Author split (always 50/50 since HF25)
    curator_pool = total_payout_usd * 0.50
    author_pool = total_payout_usd * 0.50

    # Step 2: Beneficiaries come from the AUTHOR's share
    beneficiary_payouts = {}
    total_beneficiary_weight = 0
    for b in beneficiaries:
        pct = b["weight"] / 10000  # convert basis points to fraction
        payout = author_pool * pct
        beneficiary_payouts[b["account"]] = payout
        total_beneficiary_weight += b["weight"]

    # Step 3: Author keeps remainder
    author_net = author_pool * (1 - total_beneficiary_weight / 10000)

    # Step 4: Author payout form depends on percent_hbd
    if percent_hbd == 10000:  # 50/50
        author_hp = author_net * 0.50
        author_hbd = author_net * 0.50
    elif percent_hbd == 0:  # 100% HP
        author_hp = author_net
        author_hbd = 0
    else:
        ratio = percent_hbd / 10000
        author_hbd = author_net * ratio * 0.50
        author_hp = author_net - author_hbd

    return {
        "total": total_payout_usd,
        "curators": curator_pool,
        "author_hp": author_hp,
        "author_hbd": author_hbd,
        "beneficiaries": beneficiary_payouts,
        "author_net": author_net,
    }

# Example: $10 post with 18% total beneficiaries
result = calculate_reward_split(
    total_payout_usd=10.00,
    beneficiaries=[
        {"account": "app_revenue", "weight": 500},
        {"account": "community_fund", "weight": 1000},
        {"account": "referrer", "weight": 300},
    ]
)

print(f"Total payout: ${result['total']:.2f}")
print(f"Curators:     ${result['curators']:.2f}")
print(f"Author (HP):  ${result['author_hp']:.2f}")
print(f"Author (HBD): ${result['author_hbd']:.2f}")
for name, amount in result['beneficiaries'].items():
    print(f"Beneficiary @{name}: ${amount:.2f}")
# Output:
# Total payout: $10.00
# Curators:     $5.00
# Author (HP):  $2.05
# Author (HBD): $2.05
# Beneficiary @app_revenue: $0.25
# Beneficiary @community_fund: $0.50
# Beneficiary @referrer: $0.15
```

**Checking beneficiaries on existing posts:**

```python
post = Comment("@author/permlink", blockchain_instance=hive)
beneficiaries = post["beneficiaries"]
for b in beneficiaries:
    print(f"@{b['account']}: {b['weight']/100:.2f}%")
```

**Rules and constraints:**

1. **Immutable**: Beneficiaries are set at post creation and cannot be changed afterward — even by the author.
2. **Sorted alphabetically**: The beneficiary list must be sorted by account name, or the transaction is rejected.
3. **Max total**: Combined beneficiary weight cannot exceed 10000 (100%).
4. **From author share only**: Beneficiaries reduce the author's portion. Curators always get their full 50%.
5. **Common use cases**: App fees (3-5%), community funds, referral programs, collaboration splits.
6. **Beneficiaries receive HP**: By default, beneficiary rewards are paid as HP (vesting shares), not liquid HIVE or HBD.'''
    ),
]
