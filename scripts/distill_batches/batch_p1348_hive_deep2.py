"""Deep Hive blockchain training pairs batch 2: custom_json, layer2, security, architecture."""

PAIRS = [
    # ── hive_custom_json (pairs 11-15) ───────────────────────────────────────
    ("hive_deep1_11", r'''How do I design a custom_json protocol for my Hive dApp? I want to build a tipping system where users can send tokens to content creators.''', r'''<think>
The user wants to build a custom_json protocol for tipping on Hive. This is a Layer 2 pattern — custom_json is Hive's extensibility mechanism.

Key design decisions:
1. Protocol ID — short, unique identifier (max 32 chars)
2. Authority level — tipping involves value transfer, so active key
3. Payload schema — needs versioning for future-proofing
4. Deterministic processing — all nodes must reach same state
5. Validation — check balances, verify signer, handle edge cases

I should show both the broadcasting side (beem) and the processing side (streaming + validation). The common mistake is using posting auth for financial operations.
</think>

## Designing a Custom JSON Protocol on Hive

Custom JSON is Hive's extensibility layer — it lets you broadcast structured data on-chain without a hard fork. Here's how to build a tipping protocol:

### 1. Define Your Protocol Schema

```python
# Protocol constants
PROTOCOL_ID = "mytips"  # max 32 chars, unique to your app

# Schema with versioning for future compatibility
TIP_PAYLOAD = {
    "v": 1,                    # schema version
    "action": "tip",           # action type
    "data": {
        "to": "author_name",   # tip recipient
        "amount": "1.000",     # amount (string for precision)
        "symbol": "HIVE",      # HIVE or HBD
        "permlink": "post-id", # optional: link to specific content
        "memo": "Great post!"  # optional: tip message
    }
}
```

### 2. Broadcasting Tips

```python
from beem import Hive

h = Hive(keys=["5K...active_wif"])

def send_tip(sender, to, amount, symbol="HIVE", permlink=None, memo=""):
    """Broadcast a tip via custom_json."""
    payload = {
        "v": 1,
        "action": "tip",
        "data": {
            "to": to,
            "amount": f"{float(amount):.3f}",
            "symbol": symbol,
            "permlink": permlink or "",
            "memo": memo
        }
    }

    # Financial operation → requires active key (required_auths)
    h.custom_json(
        PROTOCOL_ID,
        json_data=payload,
        required_auths=[sender]  # NOT required_posting_auths
    )

send_tip("alice", "bob", "5.000", permlink="my-first-post", memo="Thanks!")
```

### 3. Processing Tips (Server Side)

```python
import json
from beem.blockchain import Blockchain

def process_tips():
    """Stream and process tip operations deterministically."""
    blockchain = Blockchain()

    for op in blockchain.stream(opNames=["custom_json"]):
        if op["id"] != PROTOCOL_ID:
            continue

        try:
            data = json.loads(op["json"])
        except json.JSONDecodeError:
            continue  # Malformed payload — skip

        # Validation checklist
        if data.get("v") != 1:
            continue  # Unknown version
        if data.get("action") != "tip":
            continue

        tip = data.get("data", {})
        sender = op["required_auths"][0] if op["required_auths"] else None

        if not sender:
            continue  # Signed with posting key — reject financial op

        if not all(k in tip for k in ("to", "amount", "symbol")):
            continue  # Missing required fields

        if tip["symbol"] not in ("HIVE", "HBD"):
            continue  # Invalid symbol

        # Process the tip deterministically
        # NO external API calls, NO datetime.now(), NO randomness
        print(f"Block {op['block_num']}: {sender} tipped {tip['amount']} "
              f"{tip['symbol']} to {tip['to']}")
```

### Key Design Rules

1. **Authority matters**: Use `required_auths` (active key) for anything involving value. Using `required_posting_auths` for financial ops is a security hole — your L2 processor should reject it.
2. **Version your schema**: The `"v": 1` field lets you evolve the protocol without breaking existing processors.
3. **Deterministic processing**: Never use timestamps, external APIs, or randomness in your processor. All nodes must reach the same state from the same blockchain data.
4. **Payload limit**: 8,192 bytes max for the JSON field. Keep payloads lean.
5. **Idempotent processing**: Handle blockchain microforks — the same operation might be replayed. Use `block_num + tx_index` as a unique key.'''),

    ("hive_deep1_12", r'''How do I implement a follow/unfollow system using Hive custom_json? Show me the standard Hive follow protocol.''', r'''<think>
The follow/unfollow system is one of Hive's built-in custom_json protocols. The protocol ID is "follow" and it uses posting authority since it's a social operation.

Key points:
- Protocol ID: "follow"
- Auth: required_posting_auths (social operation)
- Actions: follow, unfollow, mute (ignore), and reblog
- The JSON structure is a list containing a list: [["follow", {...}]]
- This is processed by Hivemind, not a custom L2

I should show both beem's high-level API and the raw custom_json format so the user understands what's happening under the hood.
</think>

## Hive Follow/Unfollow Protocol

The follow system is a built-in custom_json protocol processed by Hivemind. Protocol ID: `"follow"`.

### Using beem's High-Level API

```python
from beem import Hive
from beem.account import Account

h = Hive(keys=["5K...posting_wif"])

# Follow a user
h.follow("target_user", what=["blog"], account="my_account")

# Unfollow
h.unfollow("target_user", account="my_account")

# Mute (ignore) a user
h.follow("spammer", what=["ignore"], account="my_account")

# Unmute
h.unfollow("spammer", account="my_account")
```

### Raw Custom JSON Format

Under the hood, beem broadcasts this custom_json:

```python
import json

# Follow operation
h.custom_json(
    "follow",
    json_data=["follow", {
        "follower": "my_account",
        "following": "target_user",
        "what": ["blog"]  # ["blog"] = follow, [] = unfollow, ["ignore"] = mute
    }],
    required_posting_auths=["my_account"]
)

# Reblog (resteem) a post
h.custom_json(
    "follow",
    json_data=["reblog", {
        "account": "my_account",
        "author": "post_author",
        "permlink": "post-permlink"
    }],
    required_posting_auths=["my_account"]
)
```

### Reading Follow Data

```python
from beem.account import Account

acc = Account("username")

# Get followers
followers = acc.get_followers()
print(f"Follower count: {acc.get_follow_count()['follower_count']}")

# Get following
following = acc.get_following()
print(f"Following count: {acc.get_follow_count()['following_count']}")

# Check if user A follows user B
def is_following(follower, following):
    acc = Account(follower)
    return following in [f["following"] for f in acc.get_following()]
```

### Important Details

- **Posting key only**: Follow/unfollow/mute are social operations — they use `required_posting_auths`
- **`what` field meanings**: `["blog"]` = follow, `[]` = unfollow, `["ignore"]` = mute
- **Processed by Hivemind**: The follow state lives in Hivemind's PostgreSQL database, not in hived's chain state
- **Reblogs are one-way**: You can reblog but there's no "un-reblog" operation
- **No notification built-in**: Follow events don't trigger on-chain notifications — apps handle that separately'''),

    ("hive_deep1_13", r'''How do I validate and process custom_json operations safely on the server side? What are the security considerations?''', r'''<think>
This is about building a secure custom_json processor — a critical piece for any Hive Layer 2 application. The user needs to understand:

1. Authority validation — checking that the right key level signed the operation
2. Payload validation — parsing and sanitizing the JSON
3. Deterministic processing — no external state dependencies
4. Replay protection — handling microforks and reorgs
5. Rate limiting — preventing spam

The biggest security mistake people make is not checking authority levels — a posting-key-signed financial operation should be rejected.
</think>

## Secure Custom JSON Processing

Building a safe custom_json processor is critical for any Hive L2 application. Here's a production-grade approach:

### 1. Authority Validation

```python
def validate_authority(op, required_level="active"):
    """Ensure the operation is signed with the correct authority level."""

    if required_level == "active":
        if not op.get("required_auths"):
            raise SecurityError(
                "Financial operation requires active key, "
                "got posting key — rejecting"
            )
        return op["required_auths"][0]  # signer account

    elif required_level == "posting":
        # Accept either posting or active (active implies posting)
        if op.get("required_posting_auths"):
            return op["required_posting_auths"][0]
        elif op.get("required_auths"):
            return op["required_auths"][0]
        raise SecurityError("No valid authority found")
```

### 2. Payload Validation

```python
import json
from typing import Any

def safe_parse(op) -> dict | None:
    """Parse and validate custom_json payload."""
    try:
        data = json.loads(op["json"])
    except (json.JSONDecodeError, KeyError):
        return None  # Malformed — skip silently

    # Type check
    if not isinstance(data, dict):
        return None

    # Version check
    if data.get("v") not in (1, 2):  # supported versions
        return None

    # Size guard (defense in depth — chain enforces 8KB)
    if len(op["json"]) > 8192:
        return None

    return data


def validate_tip_payload(data: dict) -> dict:
    """Validate a specific action's payload fields."""
    tip = data.get("data", {})

    required = {"to", "amount", "symbol"}
    if not required.issubset(tip.keys()):
        raise ValueError(f"Missing fields: {required - tip.keys()}")

    # Amount must be valid decimal
    try:
        amount = float(tip["amount"])
        if amount <= 0 or amount > 1_000_000:
            raise ValueError(f"Invalid amount: {amount}")
    except (ValueError, TypeError) as e:
        raise ValueError(f"Bad amount: {e}")

    # Symbol whitelist
    if tip["symbol"] not in ("HIVE", "HBD"):
        raise ValueError(f"Unknown symbol: {tip['symbol']}")

    # Account name format (3-16 chars, lowercase, dots/hyphens)
    import re
    if not re.match(r'^[a-z][a-z0-9\-\.]{2,15}$', tip["to"]):
        raise ValueError(f"Invalid account name: {tip['to']}")

    return tip
```

### 3. Deterministic Processing Loop

```python
from beem.blockchain import Blockchain

class CustomJsonProcessor:
    def __init__(self, protocol_id, start_block=None):
        self.protocol_id = protocol_id
        self.processed_txs = set()  # For idempotency

    def run(self, start_block=None):
        blockchain = Blockchain()
        stream = blockchain.stream(
            opNames=["custom_json"],
            start=start_block,
            threading=False  # Deterministic = single-threaded
        )

        for op in stream:
            if op["id"] != self.protocol_id:
                continue

            # Idempotency: skip already-processed transactions
            tx_key = f"{op['block_num']}:{op['trx_id']}"
            if tx_key in self.processed_txs:
                continue

            self.process_op(op)
            self.processed_txs.add(tx_key)

    def process_op(self, op):
        """Process a single operation. MUST be deterministic."""
        # Rule 1: NO external API calls
        # Rule 2: NO datetime.now() — use op['timestamp']
        # Rule 3: NO randomness
        # Rule 4: NO floating-point math — use Decimal
        # Rule 5: Same input = same output, always

        data = safe_parse(op)
        if not data:
            return

        action = data.get("action")
        if action == "tip":
            signer = validate_authority(op, "active")
            tip = validate_tip_payload(data)
            self._apply_tip(signer, tip, op["block_num"])
```

### Security Checklist

1. **Always validate authority level** — the most common L2 security bug is accepting posting-key-signed financial operations
2. **Parse JSON defensively** — malformed payloads must not crash your processor
3. **Whitelist actions** — reject unknown action types instead of ignoring them
4. **Validate all field types and ranges** — never trust user input
5. **Handle reorgs** — on microforks, blocks replay. Make processing idempotent with `block_num + trx_id` dedup
6. **Never use floating-point for amounts** — use `Decimal` or integer math to avoid rounding errors'''),

    ("hive_deep1_14", r'''How do Splinterlands and other games use custom_json on Hive? Show me the pattern for a game action protocol.''', r'''<think>
Splinterlands is the most successful Hive dApp and uses custom_json extensively. Their pattern is a great reference for anyone building games on Hive.

Key patterns from Splinterlands:
- Multiple protocol IDs for different action types (sm_find_match, sm_submit_team, sm_market_sale)
- Posting auth for gameplay, active auth for marketplace/financial
- JSON payloads vary per action type
- Client-side actions are broadcast and server processes deterministically

I should show the actual Splinterlands patterns, then generalize into a template for building any game.
</think>

## Game Action Protocols on Hive (Splinterlands Pattern)

Splinterlands is Hive's most successful dApp, processing thousands of custom_json operations per day. Here's how their protocol works and how to build your own.

### Splinterlands Protocol IDs

```python
# Splinterlands uses separate IDs per action category
SPLINTERLANDS_OPS = {
    # Gameplay (posting key)
    "sm_find_match":    "posting",  # Queue for a ranked battle
    "sm_submit_team":   "posting",  # Submit team for battle
    "sm_team_reveal":   "posting",  # Reveal team after opponent submits

    # Marketplace (active key — involves value)
    "sm_market_sale":   "active",   # List card for sale
    "sm_market_purchase": "active", # Buy a card listing
    "sm_cancel_sell":   "active",   # Cancel a listing

    # Asset transfers (active key)
    "sm_token_transfer": "active",  # Transfer in-game tokens
    "sm_gift_cards":     "active",  # Gift cards to another player
}
```

### Example: Battle Matchmaking Flow

```python
from beem import Hive
import json

h = Hive(keys=["5K...posting_wif"])

# Step 1: Queue for a match
h.custom_json("sm_find_match", json_data={
    "match_type": "Ranked",
    "mana_cap": 30,
    "ruleset": "Standard",
    "opponent": None  # null = random matchmaking
}, required_posting_auths=["player1"])

# Step 2: Submit team (after match is found)
h.custom_json("sm_submit_team", json_data={
    "trx_id": "abc123...",      # Reference to the match transaction
    "team_hash": "sha256...",   # Hash of team (commit phase)
    "summoner": "C1-001-ABC",   # Card IDs
    "monsters": ["C2-010-DEF", "C3-020-GHI", "C4-030-JKL"]
}, required_posting_auths=["player1"])

# Step 3: Reveal team (after both players submit hashes)
h.custom_json("sm_team_reveal", json_data={
    "trx_id": "abc123...",
    "summoner": "C1-001-ABC",
    "monsters": ["C2-010-DEF", "C3-020-GHI", "C4-030-JKL"],
    "secret": "random_nonce_used_in_hash"  # Proves hash matches team
}, required_posting_auths=["player1"])
```

### Building Your Own Game Protocol

```python
# Template for a card game / RPG on Hive
GAME_ID = "mygame"

class GameAction:
    """Base class for game actions broadcast via custom_json."""

    # Action registry — maps action names to auth levels
    ACTIONS = {
        "play_card":    "posting",   # Gameplay
        "join_lobby":   "posting",
        "trade_item":   "active",    # Value transfer
        "buy_pack":     "active",
        "open_pack":    "posting",   # No value transfer
    }

    @staticmethod
    def broadcast(h, player, action, data):
        auth_level = GameAction.ACTIONS.get(action)
        if not auth_level:
            raise ValueError(f"Unknown action: {action}")

        payload = {
            "v": 1,
            "action": action,
            "player": player,
            "data": data,
            "ts": None  # Server uses block timestamp, not client time
        }

        if auth_level == "active":
            h.custom_json(GAME_ID, json_data=payload,
                         required_auths=[player])
        else:
            h.custom_json(GAME_ID, json_data=payload,
                         required_posting_auths=[player])

# Usage
GameAction.broadcast(h, "player1", "play_card", {
    "card_id": "warrior_01",
    "target": "enemy_slot_3",
    "position": 2
})
```

### Why This Pattern Works

1. **Commit-reveal for fairness**: Players submit a hash first, then reveal. This prevents the second player from seeing the first player's team.
2. **Posting vs active split**: Gameplay actions use posting key (low risk), marketplace uses active key (financial).
3. **Deterministic battle resolution**: The server processes both revealed teams through a deterministic simulator — same inputs always produce the same winner.
4. **On-chain audit trail**: Every action is recorded on the blockchain, making cheating detectable and disputes resolvable.'''),

    ("hive_deep1_15", r'''How do I batch multiple custom_json operations into a single Hive transaction? When is this useful?''', r'''<think>
Batching multiple operations into a single transaction is a common optimization on Hive. Key benefits:
- Atomic execution — all ops succeed or all fail
- Lower RC cost — one transaction overhead instead of multiple
- Faster processing — one block inclusion instead of waiting for multiple

I should show beem's TransactionBuilder for multi-op transactions, and explain when batching makes sense vs when to keep operations separate.
</think>

## Batching Custom JSON Operations

Hive supports multiple operations in a single transaction. This is useful for atomicity, efficiency, and reducing RC costs.

### Using TransactionBuilder

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json

h = Hive(keys=["5K...active_wif", "5K...posting_wif"])

# Build a transaction with multiple custom_json ops
tx = TransactionBuilder(blockchain_instance=h)

# Op 1: Transfer a token (active key)
tx.appendOps(Custom_json(**{
    "id": "ssc-mainnet-hive",
    "required_auths": ["myaccount"],
    "required_posting_auths": [],
    "json": json.dumps({
        "contractName": "tokens",
        "contractAction": "transfer",
        "contractPayload": {
            "symbol": "BEE",
            "to": "recipient1",
            "quantity": "10.000",
            "memo": "batch payment 1"
        }
    })
}))

# Op 2: Another transfer in the same transaction
tx.appendOps(Custom_json(**{
    "id": "ssc-mainnet-hive",
    "required_auths": ["myaccount"],
    "required_posting_auths": [],
    "json": json.dumps({
        "contractName": "tokens",
        "contractAction": "transfer",
        "contractPayload": {
            "symbol": "BEE",
            "to": "recipient2",
            "quantity": "5.000",
            "memo": "batch payment 2"
        }
    })
}))

# Op 3: A social action (posting key)
tx.appendOps(Custom_json(**{
    "id": "follow",
    "required_auths": [],
    "required_posting_auths": ["myaccount"],
    "json": json.dumps(["follow", {
        "follower": "myaccount",
        "following": "recipient1",
        "what": ["blog"]
    }])
}))

# Sign and broadcast atomically
tx.appendSigner("myaccount", "active")
tx.appendSigner("myaccount", "posting")
tx.sign()
result = tx.broadcast()
print(f"Transaction ID: {result['id']}")
```

### When to Batch

| Scenario | Batch? | Reason |
|----------|--------|--------|
| Paying multiple users at once | **Yes** | Atomic: all payments succeed or none do |
| Game turn + follow action | **No** | Unrelated ops — failure of one shouldn't block the other |
| Multi-step protocol action | **Yes** | Ensures all steps are recorded in the same block |
| Airdrop to 100 users | **Yes** (in groups) | RC efficiency — but stay under 65KB tx limit |
| Social follow + vote | **Maybe** | Low stakes — batching saves RC but failure blocks both |

### Limits and Gotchas

1. **Max transaction size**: 65,536 bytes total. For airdrops, batch in groups of ~20-30 operations.
2. **Mixed authorities**: You can mix active and posting operations in one transaction — just provide both keys.
3. **Atomicity**: If any operation fails validation, the entire transaction is rejected. This is a feature for financial batches but a risk for mixed operations.
4. **RC cost**: One transaction costs less RC than multiple separate transactions because you pay the base transaction overhead only once.
5. **Block inclusion**: All operations in a batched transaction land in the same block, giving you a consistent `block_num` for processing.'''),

    # ── hive_layer2 (pairs 16-20) ────────────────────────────────────────────
    ("hive_deep1_16", r'''How do I create a new token on Hive-Engine? Walk me through the full process including token configuration.''', r'''<think>
Creating a token on Hive-Engine involves broadcasting a custom_json operation with the ssc-mainnet-hive protocol ID. Key details:
- Costs 100 BEE to create a token
- Must specify precision (immutable after creation)
- Can configure staking, delegation, and max supply
- Must be signed with active key and include isSignedWithActiveKey: true

I should walk through the full flow: checking BEE balance, creating the token, enabling staking, and verifying creation.
</think>

## Creating a Token on Hive-Engine

Hive-Engine lets you create custom tokens that trade against SWAP.HIVE. Here's the complete process:

### Prerequisites

```python
import requests
import json
from beem import Hive

h = Hive(keys=["5K...active_wif"])

# Check you have enough BEE (costs 100 BEE to create a token)
resp = requests.post("https://api.hive-engine.com/rpc/contracts", json={
    "jsonrpc": "2.0", "id": 1, "method": "find",
    "params": {
        "contract": "tokens",
        "table": "balances",
        "query": {"account": "myaccount", "symbol": "BEE"},
        "limit": 1
    }
})
balance = resp.json()["result"]
if balance:
    print(f"BEE balance: {balance[0]['balance']}")
else:
    print("No BEE balance — need 100 BEE to create a token")
```

### Step 1: Create the Token

```python
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "tokens",
    "contractAction": "create",
    "contractPayload": {
        "symbol": "MYTOKEN",           # 3-10 uppercase letters
        "name": "My Awesome Token",    # Display name
        "precision": 3,                # Decimal places (IMMUTABLE)
        "maxSupply": "1000000.000",    # Maximum ever mintable
        "url": "https://myapp.com",    # Project URL
        "isSignedWithActiveKey": True   # REQUIRED — proves active key auth
    }
}, required_auths=["myaccount"])
```

### Step 2: Enable Staking (Optional)

```python
# Allow users to stake your token
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "tokens",
    "contractAction": "enableStaking",
    "contractPayload": {
        "symbol": "MYTOKEN",
        "unstakingCooldown": 7,         # Days to unstake
        "numberTransactions": 7,        # Split unstake into N payouts
        "isSignedWithActiveKey": True
    }
}, required_auths=["myaccount"])
```

### Step 3: Issue (Mint) Tokens

```python
# Mint tokens to yourself or others
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "tokens",
    "contractAction": "issue",
    "contractPayload": {
        "symbol": "MYTOKEN",
        "to": "myaccount",             # Recipient
        "quantity": "100000.000",       # Amount to mint
        "isSignedWithActiveKey": True
    }
}, required_auths=["myaccount"])
```

### Step 4: Verify Creation

```python
# Check token exists
resp = requests.post("https://api.hive-engine.com/rpc/contracts", json={
    "jsonrpc": "2.0", "id": 1, "method": "findOne",
    "params": {
        "contract": "tokens",
        "table": "tokens",
        "query": {"symbol": "MYTOKEN"}
    }
})
token = resp.json()["result"]
print(f"Token: {token['symbol']} ({token['name']})")
print(f"Supply: {token['supply']} / {token['maxSupply']}")
print(f"Precision: {token['precision']}")
```

### Key Gotchas

1. **Precision is immutable**: Choose carefully — 3 decimals for currencies, 0 for NFT-like tokens, 8 for high-precision trading.
2. **`isSignedWithActiveKey: True`**: Must be in the payload for token creation, staking setup, and issuing. Without it, the operation silently fails.
3. **Symbol format**: 3-10 uppercase letters only. No numbers, no lowercase. Check availability first.
4. **SWAP.HIVE required for trading**: Users must deposit HIVE to get SWAP.HIVE before they can trade your token on the market.
5. **100 BEE cost**: This fee is burned, not refundable. Test on the testnet first if available.'''),

    ("hive_deep1_17", r'''How do I interact with Hive-Engine diesel pools (liquidity pools / AMM)? Show me how to add liquidity and swap tokens.''', r'''<think>
Diesel pools are Hive-Engine's AMM (Automated Market Maker) — similar to Uniswap but on the Hive sidechain. Key operations:
- Adding liquidity to a pool
- Removing liquidity
- Swapping tokens
- Querying pool information

All operations go through custom_json with the ssc-mainnet-hive ID. The contract is "marketpools" instead of "tokens" or "market".
</think>

## Hive-Engine Diesel Pools (AMM)

Diesel pools are Hive-Engine's liquidity pools — similar to Uniswap. They allow automated token swaps with price determined by the constant product formula (x × y = k).

### Querying Pool Info

```python
import requests

def get_pool(token_pair):
    """Get pool info for a token pair like 'SWAP.HIVE:BEE'."""
    resp = requests.post("https://api.hive-engine.com/rpc/contracts", json={
        "jsonrpc": "2.0", "id": 1, "method": "find",
        "params": {
            "contract": "marketpools",
            "table": "pools",
            "query": {"tokenPair": token_pair},
            "limit": 1
        }
    })
    result = resp.json()["result"]
    return result[0] if result else None

pool = get_pool("SWAP.HIVE:BEE")
if pool:
    print(f"Pool: {pool['tokenPair']}")
    print(f"Base quantity: {pool['baseQuantity']}")    # SWAP.HIVE
    print(f"Quote quantity: {pool['quoteQuantity']}")  # BEE
    print(f"Total shares: {pool['totalShares']}")
    # Price = baseQuantity / quoteQuantity
    price = float(pool['baseQuantity']) / float(pool['quoteQuantity'])
    print(f"Price: {price:.6f} SWAP.HIVE per BEE")
```

### Adding Liquidity

```python
from beem import Hive
import json

h = Hive(keys=["5K...active_wif"])

# Add liquidity to the SWAP.HIVE:BEE pool
# Both tokens are added proportional to the current pool ratio
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "marketpools",
    "contractAction": "addLiquidity",
    "contractPayload": {
        "tokenPair": "SWAP.HIVE:BEE",
        "baseQuantity": "10.00000000",   # SWAP.HIVE amount
        "quoteQuantity": "50.000",       # BEE amount
        "isSignedWithActiveKey": True
    }
}, required_auths=["myaccount"])
# You receive LP shares proportional to your contribution
```

### Swapping Tokens

```python
# Swap SWAP.HIVE → BEE
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "marketpools",
    "contractAction": "swapTokens",
    "contractPayload": {
        "tokenPair": "SWAP.HIVE:BEE",
        "tokenSymbol": "SWAP.HIVE",     # Token you're sending
        "tokenAmount": "5.00000000",    # Amount to swap
        "tradeType": "exactInput",      # or "exactOutput"
        "minAmountOut": "20.000",       # Slippage protection
        "isSignedWithActiveKey": True
    }
}, required_auths=["myaccount"])
```

### Removing Liquidity

```python
# Check your LP shares first
resp = requests.post("https://api.hive-engine.com/rpc/contracts", json={
    "jsonrpc": "2.0", "id": 1, "method": "find",
    "params": {
        "contract": "marketpools",
        "table": "liquidityPositions",
        "query": {"account": "myaccount", "tokenPair": "SWAP.HIVE:BEE"},
        "limit": 1
    }
})
position = resp.json()["result"]
if position:
    shares = position[0]["shares"]
    print(f"Your LP shares: {shares}")

# Remove liquidity
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "marketpools",
    "contractAction": "removeLiquidity",
    "contractPayload": {
        "tokenPair": "SWAP.HIVE:BEE",
        "sharesOut": shares,  # or a portion of your shares
        "isSignedWithActiveKey": True
    }
}, required_auths=["myaccount"])
```

### Important Concepts

- **Impermanent loss**: Like all AMMs, providing liquidity exposes you to impermanent loss when token prices diverge. The trade-off is earning swap fees.
- **Slippage protection**: Always set `minAmountOut` to prevent front-running or large price impacts.
- **SWAP.HIVE precision**: SWAP.HIVE has 8 decimal places. Match precision exactly or the operation fails.
- **Trading fees**: Pools charge a configurable fee (typically 0.25%) that goes to liquidity providers.'''),

    ("hive_deep1_18", r'''How do I use the Hive Application Framework (HAF) to build a custom indexer? I want to track all transfers above 1000 HIVE.''', r'''<think>
HAF (Hive Application Framework) is a SQL-based framework for building Hive apps. It replays the blockchain into PostgreSQL, letting you query chain data with SQL.

For tracking large transfers, the user needs to:
1. Set up a HAF app context
2. Create tables to store tracked transfers
3. Write a processor that filters transfer operations by amount
4. Query results with standard SQL

HAF handles block tracking, fork handling, and reversible blocks automatically. The key advantage over API streaming is that you get full SQL query power and don't depend on an external API.
</think>

## Building a HAF Indexer for Large Transfers

HAF replays the Hive blockchain into PostgreSQL tables, giving you SQL access to all chain data. Here's how to build a transfer tracker:

### 1. Set Up Your App Context

```sql
-- Register your app with HAF
SELECT hive.app_create_context('large_transfers', 'lt_schema');

-- Create your app's schema and tables
CREATE SCHEMA IF NOT EXISTS lt_schema;

CREATE TABLE lt_schema.big_transfers (
    id SERIAL PRIMARY KEY,
    block_num INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    trx_id VARCHAR(40) NOT NULL,
    from_account VARCHAR(16) NOT NULL,
    to_account VARCHAR(16) NOT NULL,
    amount NUMERIC(20, 3) NOT NULL,
    asset VARCHAR(4) NOT NULL,  -- HIVE or HBD
    memo TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for fast queries
CREATE INDEX idx_big_transfers_block ON lt_schema.big_transfers(block_num);
CREATE INDEX idx_big_transfers_from ON lt_schema.big_transfers(from_account);
CREATE INDEX idx_big_transfers_to ON lt_schema.big_transfers(to_account);
CREATE INDEX idx_big_transfers_amount ON lt_schema.big_transfers(amount DESC);
```

### 2. Process Blocks

```python
import psycopg2
import json
import re

def process_blocks(conn, start_block, end_block):
    """Process a range of blocks, extracting large transfers."""
    cur = conn.cursor()

    # HAF stores all operations in hive.operations
    # op_type_id 2 = transfer operation
    cur.execute("""
        SELECT o.block_num, b.created_at, o.trx_id, o.body
        FROM hive.operations o
        JOIN hive.blocks b ON b.num = o.block_num
        WHERE o.block_num BETWEEN %s AND %s
        AND o.op_type_id = 2  -- transfer
        ORDER BY o.block_num, o.id
    """, (start_block, end_block))

    inserts = []
    for block_num, timestamp, trx_id, body in cur.fetchall():
        op = json.loads(body)

        # Parse amount: "1500.000 HIVE" → (1500.0, "HIVE")
        amount_str = op.get("amount", "0 HIVE")
        match = re.match(r'([\d.]+)\s+(\w+)', amount_str)
        if not match:
            continue

        amount = float(match.group(1))
        asset = match.group(2)

        # Filter: only track transfers >= 1000
        if amount >= 1000:
            inserts.append((
                block_num, timestamp, trx_id,
                op["from"], op["to"], amount, asset,
                op.get("memo", "")
            ))

    if inserts:
        cur.executemany("""
            INSERT INTO lt_schema.big_transfers
            (block_num, timestamp, trx_id, from_account, to_account,
             amount, asset, memo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, inserts)
        conn.commit()

    return len(inserts)
```

### 3. Main Event Loop

```python
def run_indexer():
    """Main loop: process new blocks as they arrive."""
    conn = psycopg2.connect("dbname=haf_db user=haf_user")

    # Get last processed block
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(block_num), 0) FROM lt_schema.big_transfers")
    last_block = cur.fetchone()[0]

    # Get current head block from HAF
    cur.execute("SELECT hive.app_get_irreversible_block()")
    head_block = cur.fetchone()[0]

    print(f"Processing blocks {last_block + 1} to {head_block}")

    # Process in batches of 1000 blocks
    batch_size = 1000
    for start in range(last_block + 1, head_block + 1, batch_size):
        end = min(start + batch_size - 1, head_block)
        count = process_blocks(conn, start, end)
        if count:
            print(f"Blocks {start}-{end}: found {count} large transfers")

    conn.close()
```

### 4. Query Your Data

```sql
-- Top 10 largest transfers ever
SELECT from_account, to_account, amount, asset, timestamp
FROM lt_schema.big_transfers
ORDER BY amount DESC LIMIT 10;

-- Daily volume of large transfers
SELECT DATE(timestamp) as day,
       COUNT(*) as tx_count,
       SUM(amount) as total_volume,
       asset
FROM lt_schema.big_transfers
GROUP BY day, asset
ORDER BY day DESC;

-- Most active large senders
SELECT from_account, COUNT(*) as tx_count, SUM(amount) as total_sent
FROM lt_schema.big_transfers
WHERE asset = 'HIVE'
GROUP BY from_account
ORDER BY total_sent DESC LIMIT 20;
```

### Why HAF over API Streaming

- **SQL power**: Complex aggregations, joins, and window functions
- **No rate limits**: Query your local database as fast as you want
- **Fork handling**: HAF manages reversible blocks automatically
- **Historical data**: Full chain history available, not just live stream
- **Reliability**: No network dependency after initial sync'''),

    ("hive_deep1_19", r'''How do I deposit HIVE to get SWAP.HIVE on Hive-Engine, and withdraw SWAP.HIVE back to HIVE? Explain the bridge mechanism.''', r'''<think>
SWAP.HIVE is Hive-Engine's wrapped version of HIVE. To trade on Hive-Engine's DEX, you need SWAP.HIVE, not raw HIVE.

The deposit process: Transfer HIVE to the @honey-swap gateway account → receive SWAP.HIVE on Hive-Engine.
The withdrawal process: Send a withdraw custom_json → receive HIVE back.

This is a critical concept because many developers get confused between HIVE and SWAP.HIVE. They're not the same — SWAP.HIVE is a sidechain token.
</think>

## SWAP.HIVE Bridge: Depositing and Withdrawing

SWAP.HIVE is Hive-Engine's wrapped version of native HIVE. You need SWAP.HIVE to trade on the Hive-Engine DEX. They maintain a 1:1 peg through a gateway.

### Depositing HIVE → SWAP.HIVE

```python
from beem import Hive

h = Hive(keys=["5K...active_wif"])

# Deposit: transfer HIVE to the gateway account
# The memo is empty or can be your account name
h.transfer(
    to="honey-swap",           # Gateway account
    amount=100.0,
    asset="HIVE",
    memo="",                   # No memo needed
    account="myaccount"
)
# Your Hive-Engine account is automatically credited
# with 100.00000000 SWAP.HIVE (8 decimal precision)
```

### Withdrawing SWAP.HIVE → HIVE

```python
import json

# Withdraw: custom_json to Hive-Engine
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "hivepegged",
    "contractAction": "withdraw",
    "contractPayload": {
        "quantity": "50.00000000"   # SWAP.HIVE amount (8 decimals)
    }
}, required_auths=["myaccount"])
# Gateway sends 50.000 HIVE back to your Hive account
# Small fee may apply (typically 0.75%)
```

### Checking Your SWAP.HIVE Balance

```python
import requests

resp = requests.post("https://api.hive-engine.com/rpc/contracts", json={
    "jsonrpc": "2.0", "id": 1, "method": "find",
    "params": {
        "contract": "tokens",
        "table": "balances",
        "query": {"account": "myaccount", "symbol": "SWAP.HIVE"},
        "limit": 1
    }
})
result = resp.json()["result"]
if result:
    bal = result[0]
    print(f"SWAP.HIVE balance: {bal['balance']}")
    print(f"SWAP.HIVE staked: {bal.get('stake', '0')}")
```

### Key Points

1. **1:1 peg**: 1 SWAP.HIVE = 1 HIVE, maintained by the gateway. The withdrawal fee makes it slightly less than 1:1 when withdrawing.
2. **Precision difference**: HIVE has 3 decimal places, SWAP.HIVE has 8. Always use 8 decimals for SWAP.HIVE amounts.
3. **Gateway account**: Currently `honey-swap` (previously `@hive-engine`). Verify the current gateway before sending.
4. **HBD equivalent**: SWAP.HBD works the same way — deposit HBD, get SWAP.HBD for trading.
5. **Processing time**: Deposits typically credit within 1-2 minutes. Withdrawals may take longer depending on gateway processing.
6. **Why not just use HIVE directly?**: Hive-Engine is a sidechain with its own token ledger. Raw HIVE exists on Layer 1; SWAP.HIVE is the L2 representation needed for the sidechain's smart contracts.'''),

    ("hive_deep1_20", r'''How do I query NFTs on Hive-Engine? Show me how to check ownership, list NFTs for sale, and transfer them.''', r'''<think>
Hive-Engine has an NFT system built into its smart contracts. The contract name is "nft" and it handles creation, transfers, market listings, and ownership queries.

Key operations:
- Query NFT instances and ownership
- Transfer NFTs between accounts
- List NFTs for sale on the marketplace
- Buy listed NFTs

I should show both the query API and the broadcast operations via custom_json.
</think>

## Hive-Engine NFTs: Query, Transfer, and Trade

Hive-Engine's `nft` contract manages non-fungible tokens on the sidechain.

### Querying NFT Ownership

```python
import requests

def get_nft_instances(symbol, owner=None, limit=100):
    """Get NFT instances, optionally filtered by owner."""
    query = {"symbol": symbol}
    if owner:
        query["account"] = owner

    resp = requests.post("https://api.hive-engine.com/rpc/contracts", json={
        "jsonrpc": "2.0", "id": 1, "method": "find",
        "params": {
            "contract": "nft",
            "table": f"{symbol}instances",  # Table name = SYMBOLinstances
            "query": query,
            "limit": limit
        }
    })
    return resp.json()["result"]

# Get all NFTs of type "MYCARDS" owned by a user
my_nfts = get_nft_instances("MYCARDS", owner="myaccount")
for nft in my_nfts:
    print(f"ID: {nft['_id']}, Properties: {nft.get('properties', {})}")
```

### Querying NFT Collection Info

```python
def get_nft_info(symbol):
    """Get NFT collection metadata."""
    resp = requests.post("https://api.hive-engine.com/rpc/contracts", json={
        "jsonrpc": "2.0", "id": 1, "method": "findOne",
        "params": {
            "contract": "nft",
            "table": "nfts",
            "query": {"symbol": symbol}
        }
    })
    return resp.json()["result"]

info = get_nft_info("MYCARDS")
print(f"Name: {info['name']}")
print(f"Issuer: {info['issuer']}")
print(f"Supply: {info['supply']} / {info['maxSupply']}")
```

### Transferring NFTs

```python
from beem import Hive
import json

h = Hive(keys=["5K...active_wif"])

# Transfer NFTs to another account
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "nft",
    "contractAction": "transfer",
    "contractPayload": {
        "to": "recipient",
        "nfts": [
            {"symbol": "MYCARDS", "ids": ["123", "456"]},  # Transfer specific IDs
        ],
        "isSignedWithActiveKey": True
    }
}, required_auths=["myaccount"])
```

### Listing NFTs for Sale

```python
# List an NFT on the marketplace
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "nftmarket",
    "contractAction": "sell",
    "contractPayload": {
        "symbol": "MYCARDS",
        "nfts": ["123"],                # NFT instance IDs to sell
        "price": "10.00000000",         # Price in SWAP.HIVE
        "priceSymbol": "SWAP.HIVE",     # Payment token
        "fee": 500,                      # Marketplace fee (500 = 5%)
        "isSignedWithActiveKey": True
    }
}, required_auths=["myaccount"])

# Buy a listed NFT
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "nftmarket",
    "contractAction": "buy",
    "contractPayload": {
        "symbol": "MYCARDS",
        "nfts": ["123"],
        "marketAccount": "nftmarket",   # Market contract account
        "isSignedWithActiveKey": True
    }
}, required_auths=["buyer_account"])

# Cancel a listing
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "nftmarket",
    "contractAction": "cancel",
    "contractPayload": {
        "symbol": "MYCARDS",
        "nfts": ["123"],
        "isSignedWithActiveKey": True
    }
}, required_auths=["myaccount"])
```

### Querying Market Listings

```python
def get_market_listings(symbol, limit=20):
    """Get NFTs currently for sale."""
    resp = requests.post("https://api.hive-engine.com/rpc/contracts", json={
        "jsonrpc": "2.0", "id": 1, "method": "find",
        "params": {
            "contract": "nftmarket",
            "table": f"{symbol}sellBook",
            "query": {},
            "limit": limit,
            "indexes": [{"index": "priceDec", "descending": False}]
        }
    })
    return resp.json()["result"]

listings = get_market_listings("MYCARDS")
for item in listings:
    print(f"NFT #{item['nftId']} - {item['price']} {item['priceSymbol']} "
          f"by {item['account']}")
```

### Important Notes

- **Table naming**: NFT instance tables are named `{SYMBOL}instances` (e.g., `MYCARDSinstances`). This catches people off guard.
- **IDs are strings**: NFT instance IDs must be passed as strings, not integers.
- **Active key required**: All NFT operations that involve ownership changes require active authority.
- **Batch transfers**: You can transfer multiple NFTs from different collections in a single operation by adding multiple entries to the `nfts` array.'''),

    # ── hive_security (pairs 21-25) ──────────────────────────────────────────
    ("hive_deep1_21", r'''How does Hive's key hierarchy work? Explain the different key levels and when to use each one.''', r'''<think>
Hive's key hierarchy is one of its most important security features. There are 4 key levels plus a master password. Each key has different permissions:

1. Owner key — nuclear option, can change all other keys
2. Active key — financial operations (transfers, power up/down)
3. Posting key — social operations (post, vote, follow)
4. Memo key — encrypt/decrypt transfer memos

The master password derives all 4 keys but should never be stored. The hierarchy allows users to expose only the minimum permission level needed, following the principle of least privilege.
</think>

## Hive Key Hierarchy

Hive uses a 4-level key system that follows the **principle of least privilege**. Each key level controls specific operations, so compromising a lower-level key doesn't expose higher-level capabilities.

### The Four Key Levels

| Key | Permission Level | Controls | Daily Use? |
|-----|-----------------|----------|------------|
| **Owner** | Highest | Change all keys, set recovery partner, transfer ownership | **Never** — cold storage only |
| **Active** | High | Transfers, power up/down, witness votes, convert HBD, Hive-Engine ops | Only for financial ops |
| **Posting** | Medium | Post, comment, vote, follow, reblog, social custom_json | Daily app usage |
| **Memo** | Lowest | Encrypt/decrypt transfer memos | Reading private memos |

### Key Derivation from Master Password

```python
from beemgraphenebase.account import PasswordKey

master_password = "P5K..."  # Given at account creation — NEVER store

# Derive all four key pairs
for role in ["owner", "active", "posting", "memo"]:
    pk = PasswordKey("myaccount", master_password, role)
    private_wif = str(pk.get_private_key())    # 5K... or 5J... (WIF format)
    public_key = str(pk.get_public_key())      # STM7... (53 chars)
    print(f"{role:>8}: private={private_wif[:8]}... public={public_key[:12]}...")
```

### Practical Key Usage

```python
from beem import Hive

# For posting operations — use posting key
h_post = Hive(keys=["5K...posting_wif"])
h_post.post(
    title="My Post",
    body="Content here",
    author="myaccount",
    tags=["hive"]
)

# For financial operations — use active key
h_active = Hive(keys=["5K...active_wif"])
h_active.transfer("recipient", 10.0, "HIVE", memo="payment", account="myaccount")

# For key changes — use owner key (rare!)
h_owner = Hive(keys=["5K...owner_wif"])
h_owner.change_recovery_account("trusted_friend", account="myaccount")
```

### Security Best Practices

```
SAFE:
  ✓ Store owner key offline (paper wallet, encrypted USB)
  ✓ Use Hive Keychain browser extension for web apps
  ✓ Use posting key for daily app interactions
  ✓ Only load active key when making transfers
  ✓ Set a trusted recovery account (not the default "steem")

DANGEROUS:
  ✗ Storing master password in any app
  ✗ Using owner key for posting operations
  ✗ Putting private keys in environment variables on shared servers
  ✗ Committing keys to git (even in .env files)
  ✗ Sharing keys over Discord, email, or any messaging platform
```

### Why This Design Matters

The hierarchy means that **if your posting key is compromised**, an attacker can spam posts and votes but **cannot steal your funds**. They'd need the active key for that. And even if the active key is compromised, they can't lock you out — you need the owner key to change keys. This layered defense is why Hive accounts are more resilient than single-key blockchain systems.'''),

    ("hive_deep1_22", r'''How do I set up multi-sig (multi-signature) on a Hive account? Show me how to configure 2-of-3 authority.''', r'''<think>
Hive's authority system supports weight-based multi-sig at every key level. A 2-of-3 setup means you need at least 2 of 3 authorized parties to sign a transaction.

Key concepts:
- weight_threshold: minimum total weight needed
- key_auths: individual keys with their weights
- account_auths: other accounts whose keys can also sign

I need to show:
1. How to set up multi-sig on the active authority
2. How to create and broadcast a multi-sig transaction
3. Common patterns (team treasuries, DAOs)
</think>

## Multi-Signature Accounts on Hive

Hive's authority system supports weight-based multi-sig at every key level. Here's how to configure a 2-of-3 setup.

### Setting Up 2-of-3 Multi-Sig

```python
from beem import Hive
from beem.account import Account

h = Hive(keys=["5K...owner_wif"])  # Need owner key to change authorities

# Configure 2-of-3 on the active authority
# Any 2 of the 3 keys can authorize financial operations
h.update_account(
    account="treasury_account",
    active={
        "weight_threshold": 2,      # Need total weight >= 2
        "key_auths": [
            ["STM7abc...pubkey1", 1],  # Signer A (weight 1)
            ["STM7def...pubkey2", 1],  # Signer B (weight 1)
            ["STM7ghi...pubkey3", 1],  # Signer C (weight 1)
        ],
        "account_auths": []
    }
)
```

### Account-Based Multi-Sig

Instead of raw keys, you can authorize other accounts:

```python
# 2-of-3 using account authorities
# The active key of each named account can sign
h.update_account(
    account="dao_treasury",
    active={
        "weight_threshold": 2,
        "key_auths": [],  # No direct keys
        "account_auths": [
            ["council_member_1", 1],
            ["council_member_2", 1],
            ["council_member_3", 1],
        ]
    }
)
# Now council_member_1's active key + council_member_2's active key
# together can authorize transfers from dao_treasury
```

### Broadcasting Multi-Sig Transactions

```python
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer

h = Hive()  # No keys — we'll add signers manually

# Build the transaction
tx = TransactionBuilder(blockchain_instance=h)
tx.appendOps(Transfer(**{
    "from": "treasury_account",
    "to": "contractor",
    "amount": "1000.000 HIVE",
    "memo": "Invoice #42 payment"
}))

# Signer A signs
tx.appendWif("5K...signerA_active_wif")
tx.sign()

# At this point, tx is partially signed (weight = 1, need 2)
# Export the partially-signed transaction
partial_tx = tx.json()

# Signer B receives partial_tx and adds their signature
tx2 = TransactionBuilder(tx=partial_tx, blockchain_instance=h)
tx2.appendWif("5K...signerB_active_wif")
tx2.sign()

# Now threshold is met (weight = 2 >= 2) — broadcast!
result = tx2.broadcast()
print(f"Multi-sig transaction broadcast: {result['id']}")
```

### Weighted Multi-Sig (Unequal Authority)

```python
# CEO has weight 2, others have weight 1
# CEO alone can authorize, OR any 2 non-CEO members together
h.update_account(
    account="company_account",
    active={
        "weight_threshold": 2,
        "key_auths": [
            ["STM7_ceo_pubkey", 2],      # CEO: weight 2 (can act alone)
            ["STM7_cfo_pubkey", 1],      # CFO: weight 1
            ["STM7_cto_pubkey", 1],      # CTO: weight 1
        ],
        "account_auths": []
    }
)
```

### Common Patterns

| Use Case | Setup | Why |
|----------|-------|-----|
| Team treasury | 2-of-3 accounts | No single person can drain funds |
| DAO governance | 3-of-5 council | Democratic spending approval |
| Business account | CEO (weight 2) + officers (weight 1) | CEO can act fast, officers can act together |
| Cold storage | 2-of-2 (online + offline key) | Requires both keys — no single point of compromise |

### Important Gotchas

1. **Owner key needed**: Changing authorities requires the owner key, not active.
2. **Don't lock yourself out**: Always ensure the threshold is reachable by available keys. If you set threshold=3 with only 2 keys of weight 1, the account is permanently locked.
3. **Authority propagation**: If account A authorizes account B, and B authorizes C, that does NOT mean C can sign for A. Authority doesn't chain transitively.
4. **Recovery still works**: Even with multi-sig, the account recovery process works with the owner key, providing a safety net.'''),

    ("hive_deep1_23", r'''How do I detect phishing attempts on Hive? What patterns should my app watch for to protect users?''', r'''<think>
Phishing on Hive takes specific forms that differ from traditional web phishing. Common vectors:
1. Fake login pages that mimic Hivesigner or Hive Keychain
2. Malicious memos with phishing links
3. Fake witness/proposal voting links that actually sign transfers
4. Authority change attacks (tricking users into adding attacker's key)
5. Custom_json payloads that look like social ops but are financial

I should show practical detection patterns — things an app developer can implement to protect users.
</think>

## Detecting Hive Phishing Attacks

Phishing on Hive has unique patterns. Here's what to watch for and how to protect your users:

### 1. Malicious Memo Detection

```python
import re

PHISHING_PATTERNS = [
    r'https?://[^\s]*(?:hivesigner|hive-signer|hiveblog|peakd)\.[^\s]*\.(?:com|io|xyz)',  # Fake domains
    r'(?:claim|verify|confirm|unlock|secure).*(?:wallet|account|reward|airdrop)',  # Urgency language
    r'https?://[^\s]*(?:bit\.ly|t\.co|tinyurl)',  # URL shorteners (hiding destination)
    r'(?:send|transfer).*(?:active|owner|master)\s*key',  # Key harvesting
    r'you\s*(?:have\s*)?(?:won|earned|received)\s*\d+\s*(?:HIVE|HBD)',  # Fake rewards
]

def check_memo_phishing(memo: str) -> list[str]:
    """Check a transfer memo for phishing indicators."""
    warnings = []
    memo_lower = memo.lower()

    for pattern in PHISHING_PATTERNS:
        if re.search(pattern, memo_lower):
            warnings.append(f"Phishing pattern detected: {pattern}")

    # Check for look-alike domains
    legit_domains = ["hive.blog", "peakd.com", "ecency.com", "hivesigner.com"]
    urls = re.findall(r'https?://([^\s/]+)', memo)
    for url in urls:
        for legit in legit_domains:
            # Levenshtein-like check: similar but not exact
            if url != legit and legit.split('.')[0] in url:
                warnings.append(f"Suspicious domain: {url} (similar to {legit})")

    return warnings

# Example usage in a transfer processor
memo = "Congratulations! You won 500 HIVE! Claim at https://hive-blog.xyz/claim"
warnings = check_memo_phishing(memo)
if warnings:
    print(f"⚠ PHISHING DETECTED: {warnings}")
```

### 2. Authority Change Monitoring

```python
from beem.blockchain import Blockchain

def monitor_authority_changes():
    """Alert when account authorities are modified."""
    blockchain = Blockchain()

    # Watch for account_update operations (type 10)
    for op in blockchain.stream(opNames=["account_update"]):
        account = op.get("account")

        # Check if new keys/accounts were added to authorities
        for auth_type in ["owner", "active", "posting"]:
            auth = op.get(auth_type, {})
            if not auth:
                continue

            key_auths = auth.get("key_auths", [])
            acct_auths = auth.get("account_auths", [])

            if acct_auths:
                # Someone added account-based authority
                # This is how attackers gain persistent access
                print(f"⚠ ALERT: {account}'s {auth_type} authority "
                      f"now includes accounts: {acct_auths}")

            if len(key_auths) > 1:
                print(f"⚠ ALERT: {account}'s {auth_type} authority "
                      f"now has {len(key_auths)} keys")
```

### 3. Fake Operation Detection

```python
def validate_operation_intent(op):
    """Check that a custom_json operation matches its claimed purpose."""

    # Red flag: financial authority for a "social" protocol ID
    social_protocols = {"follow", "community", "notify", "reblog"}

    if op["id"] in social_protocols and op.get("required_auths"):
        return {
            "risk": "HIGH",
            "reason": f"Social operation '{op['id']}' using active key — "
                     f"legitimate social ops only need posting key"
        }

    # Red flag: custom_json that claims to be one thing but isn't
    if op["id"] == "follow":
        try:
            data = json.loads(op["json"])
            if not isinstance(data, list) or data[0] not in ("follow", "reblog"):
                return {
                    "risk": "MEDIUM",
                    "reason": f"Follow protocol with unexpected action: {data[0]}"
                }
        except (json.JSONDecodeError, IndexError, KeyError):
            return {"risk": "MEDIUM", "reason": "Malformed follow operation"}

    return {"risk": "LOW", "reason": "No suspicious patterns detected"}
```

### 4. User-Facing Protections

```python
def pre_sign_warning(operation):
    """Generate warnings before user signs a transaction."""
    warnings = []

    op_type = operation[0] if isinstance(operation, list) else operation.get("type")

    if op_type == "account_update":
        warnings.append("⚠ This changes your account keys/authorities. "
                        "Verify you intended to do this.")

    if op_type == "transfer":
        amount = operation[1].get("amount", "0 HIVE")
        if float(amount.split()[0]) > 100:
            warnings.append(f"⚠ Large transfer: {amount}. Double-check the recipient.")

    if op_type == "custom_json":
        if operation[1].get("required_auths"):
            warnings.append("⚠ This operation requires your active key "
                          "(financial permissions). Verify the app is trusted.")

    return warnings
```

### Key Takeaways

1. **Memos are attack vectors**: Never auto-open URLs from transfer memos. Always warn users.
2. **Authority changes are critical events**: Monitor and alert immediately.
3. **Active key for social ops is a red flag**: Legitimate social operations only need posting authority.
4. **Hive Keychain is the safest option**: It shows exactly what's being signed before the user confirms.
5. **URL shorteners in memos**: Almost always phishing. Legitimate services use their real domain.'''),

    ("hive_deep1_24", r'''How do I implement memo encryption and decryption on Hive? Show me how private memos work.''', r'''<think>
Hive transfer memos can be encrypted so only the sender and recipient can read them. This uses the memo keys of both parties with ECIES (Elliptic Curve Integrated Encryption Scheme).

Key details:
- Encrypted memos start with '#' character
- Uses the memo private key (lowest privilege level)
- Shared secret derived from sender's memo private + recipient's memo public (or vice versa)
- beem handles the encryption/decryption automatically

I should show both the beem high-level API and explain the cryptographic mechanism.
</think>

## Hive Memo Encryption

Hive supports encrypted transfer memos using ECIES (Elliptic Curve Integrated Encryption Scheme). Only the sender and recipient can decrypt the memo.

### Sending Encrypted Memos

```python
from beem import Hive

# Need both active key (for transfer) AND memo key (for encryption)
h = Hive(keys=["5K...active_wif", "5K...memo_wif"])

# Prefix memo with '#' to encrypt it
h.transfer(
    to="recipient",
    amount=1.0,
    asset="HIVE",
    memo="#This is a secret message only recipient can read",
    account="sender"
)
# The '#' prefix tells beem to encrypt using:
# - Sender's memo private key
# - Recipient's memo public key
# Result on-chain: "#SjdU8fk2l..." (encrypted blob)
```

### Decrypting Memos

```python
from beem import Hive
from beem.account import Account

# Load with memo key to decrypt
h = Hive(keys=["5K...memo_wif"])

# Get transfer history
acc = Account("myaccount", blockchain_instance=h)
history = acc.get_account_history(-1, 100, only_ops=["transfer"])

for op in history:
    memo = op["memo"]
    if memo.startswith("#"):
        # beem automatically decrypts if you have the memo key
        try:
            decrypted = h.decode_memo(memo)
            print(f"From {op['from']}: {decrypted}")
        except Exception as e:
            print(f"Cannot decrypt memo from {op['from']}: {e}")
    else:
        print(f"From {op['from']} (plaintext): {memo}")
```

### How Encryption Works Under the Hood

```python
# The cryptographic process (simplified):
#
# 1. Sender has: memo_private_sender, memo_public_recipient
# 2. ECDH shared secret: shared = ECDH(memo_private_sender, memo_public_recipient)
# 3. Derive AES key from shared secret
# 4. Encrypt memo with AES-256-CBC
# 5. Prepend sender's memo public key (so recipient knows who sent it)
# 6. Base58-encode the whole thing
#
# Recipient reverses:
# 1. Extract sender's memo public key from encrypted memo
# 2. ECDH shared secret: shared = ECDH(memo_private_recipient, memo_public_sender)
# 3. Same shared secret! (ECDH property)
# 4. Derive same AES key
# 5. Decrypt memo

# Low-level decryption (normally beem handles this)
from beemgraphenebase.ecdsasig import decrypt_message

encrypted_memo = "#SjdU8fk2l..."  # From blockchain
memo_private_key = "5K..."         # Your memo WIF

decrypted = decrypt_message(
    encrypted_memo[1:],  # Strip the '#' prefix
    memo_private_key
)
```

### Practical Use Cases

```python
# 1. Private payment references
h.transfer("vendor", 50.0, "HIVE",
    memo="#Invoice #12345 — payment for consulting services",
    account="buyer")

# 2. Exchange deposit IDs (exchanges use memo for routing)
h.transfer("exchange_account", 100.0, "HIVE",
    memo="#deposit_id:abc123",  # Encrypted so only exchange sees your ID
    account="myaccount")

# 3. Encrypted messaging (using 0.001 HIVE transfers as carrier)
h.transfer("friend", 0.001, "HIVE",
    memo="#Hey, let's meet at the usual place tomorrow at 3pm",
    account="myaccount")
```

### Important Notes

1. **Only memo key needed**: You don't need active or owner key to decrypt — just the memo key. This is by design: memo decryption is the lowest privilege level.
2. **Both parties can decrypt**: Both sender and recipient can read the memo because ECDH produces the same shared secret from either side.
3. **On-chain forever**: Encrypted memos are stored on the blockchain permanently. If someone obtains your memo key in the future, they can decrypt all historical memos.
4. **Not for large data**: Memos have a ~2KB limit. For larger encrypted payloads, encrypt off-chain and put a hash/link in the memo.
5. **`#` prefix is the trigger**: Without `#`, the memo is plaintext and visible to everyone.'''),

    ("hive_deep1_25", r'''How do I validate that a Hive transaction was properly signed and authorized before processing it in my application?''', r'''<think>
Transaction validation is critical for any Hive application that processes operations server-side. Key aspects:

1. Verify the transaction signature is valid
2. Check that the signer has the required authority
3. Verify the transaction hasn't expired
4. Check ref_block for replay protection

This is especially important for applications that accept signed transactions from clients — you need to verify before processing.
</think>

## Validating Hive Transaction Signatures

When your application receives a signed transaction from a client, you must verify it before processing. Here's how to validate signatures and authorities.

### Basic Transaction Verification

```python
from beem import Hive
from beem.account import Account
from beemgraphenebase.ecdsasig import verify_message
import json

h = Hive()

def verify_transaction(signed_tx):
    """Verify a signed transaction is valid and properly authorized."""
    errors = []

    # 1. Check transaction hasn't expired
    from datetime import datetime, timezone
    expiration = datetime.fromisoformat(
        signed_tx["expiration"].replace("Z", "+00:00")
    )
    if expiration < datetime.now(timezone.utc):
        errors.append("Transaction has expired")

    # 2. Verify signatures exist
    if not signed_tx.get("signatures"):
        errors.append("No signatures found")
        return {"valid": False, "errors": errors}

    # 3. Check each operation's authority requirements
    for op in signed_tx["operations"]:
        op_type = op[0] if isinstance(op, list) else op["type"]
        op_data = op[1] if isinstance(op, list) else op

        if op_type == "transfer":
            # Transfer requires active authority of 'from' account
            account_name = op_data["from"]
            required_auth = "active"
        elif op_type == "vote":
            account_name = op_data["voter"]
            required_auth = "posting"
        elif op_type == "custom_json":
            if op_data.get("required_auths"):
                account_name = op_data["required_auths"][0]
                required_auth = "active"
            elif op_data.get("required_posting_auths"):
                account_name = op_data["required_posting_auths"][0]
                required_auth = "posting"
            else:
                errors.append("custom_json has no authority specified")
                continue
        else:
            continue  # Add more op types as needed

        # 4. Verify the signer has the required authority
        try:
            acc = Account(account_name, blockchain_instance=h)
            auth = acc.get(required_auth, {})
            authorized_keys = [k[0] for k in auth.get("key_auths", [])]

            # Recover public key from signature and verify it's authorized
            # beem does this internally when you use verify_authority
        except Exception as e:
            errors.append(f"Cannot verify account {account_name}: {e}")

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }
```

### Using beem's Built-in Verification

```python
from beem.transactionbuilder import TransactionBuilder

def verify_with_beem(signed_tx_json):
    """Use beem's built-in verification."""
    h = Hive()

    try:
        tx = TransactionBuilder(tx=signed_tx_json, blockchain_instance=h)

        # verify_authority checks:
        # 1. Signature is cryptographically valid
        # 2. Recovered public key matches an authorized key
        # 3. Weight threshold is met
        tx.verify_authority()

        return {"valid": True, "operations": len(tx.ops)}
    except Exception as e:
        return {"valid": False, "error": str(e)}
```

### Verifying HiveSigner Tokens

```python
import requests

def verify_hivesigner_token(access_token):
    """Verify a HiveSigner OAuth token and get the user."""
    resp = requests.get(
        "https://hivesigner.com/api/me",
        headers={"Authorization": access_token}
    )

    if resp.status_code == 200:
        user_data = resp.json()
        return {
            "valid": True,
            "account": user_data["account"]["name"],
            "scope": user_data.get("scope", []),
        }
    return {"valid": False, "error": resp.text}
```

### Verifying Hive Keychain Signatures

```python
def verify_keychain_signature(username, message, signature, key_type="posting"):
    """Verify a message signed by Hive Keychain."""
    from beem.account import Account
    from beemgraphenebase.ecdsasig import verify_message

    acc = Account(username, blockchain_instance=Hive())
    auth = acc.get(key_type, {})
    authorized_keys = [k[0] for k in auth.get("key_auths", [])]

    # Recover the public key from the signature
    # and check it matches an authorized key
    try:
        recovered_key = verify_message(message.encode(), signature)
        pub_key_str = str(recovered_key)

        if pub_key_str in authorized_keys:
            return {"valid": True, "account": username, "key_type": key_type}
        else:
            return {"valid": False, "error": "Recovered key not in account authorities"}
    except Exception as e:
        return {"valid": False, "error": str(e)}
```

### Security Checklist for Transaction Processing

1. **Always verify server-side**: Never trust client-side validation alone
2. **Check expiration**: Reject expired transactions to prevent replay attacks
3. **Verify authority level**: A posting-key-signed transfer must be rejected
4. **Check weight threshold**: For multi-sig accounts, ensure enough signatures meet the threshold
5. **Validate ref_block**: The `ref_block_num` should reference a recent block (prevents cross-fork replay)
6. **Rate limit**: Even valid transactions should be rate-limited per account to prevent abuse'''),

    # ── hive_architecture (pairs 26-30) ──────────────────────────────────────
    ("hive_deep1_26", r'''How does Hive's DPoS consensus work? Explain witness scheduling, block production, and how blocks become irreversible.''', r'''<think>
Hive uses Delegated Proof of Stake (DPoS) for consensus. Key mechanics:
- 21 active witnesses produce blocks in round-robin
- Top 20 elected by HP-weighted stake voting + 1 backup rotated in
- 3-second block time
- Irreversibility after 2/3 supermajority confirmation (~45 seconds)

I should explain the full lifecycle: witness election → scheduling → block production → propagation → irreversibility.
</think>

## Hive DPoS Consensus

Hive uses Delegated Proof of Stake (DPoS), where stakeholders elect block producers (witnesses) through HP-weighted voting.

### Witness Election

```python
from beem import Hive
from beem.witness import Witness, Witnesses

h = Hive()

# Get top 21 active witnesses
active_witnesses = Witnesses(blockchain_instance=h)
top_21 = list(active_witnesses)[:21]

for i, w in enumerate(top_21):
    print(f"#{i+1:2d} {w['owner']:20s} votes: {w['votes']}")

# Vote for a witness (max 30 votes per account)
h_with_key = Hive(keys=["5K...active_wif"])
h_with_key.approve_witness("good_witness", account="myaccount")

# Remove a witness vote
h_with_key.disapprove_witness("bad_witness", account="myaccount")

# Set a proxy (delegate ALL witness votes to another account)
h_with_key.set_proxy("trusted_voter", account="myaccount")
```

### Block Production Schedule

```
Round = 21 blocks (63 seconds total)
├── Top 20 witnesses: each gets 1 slot (deterministic order)
├── 1 backup witness: rotated in from rank 21+ (lottery weighted by votes)
└── Shuffled each round: order randomized to prevent prediction

Block time: 3 seconds
Round time: 63 seconds (21 × 3s)
Miss penalty: witnesses who miss blocks drop in reliability ranking
```

```python
# Get the current witness schedule
schedule = h.get_witness_schedule()
current_witnesses = schedule["current_shuffled_witnesses"]
print(f"Current round witnesses: {current_witnesses}")
print(f"Median props: {schedule['median_props']}")
# median_props includes: account_creation_fee, maximum_block_size, etc.
```

### Block Lifecycle

```
1. PENDING:     Witness creates block, broadcasts to network
2. REVERSIBLE:  Block received by nodes, included in chain
                (but could be undone if witness misbehaves)
3. IRREVERSIBLE: 2/3 of witnesses (14/21) confirm the block
                  Takes ~15 blocks × 3s = ~45 seconds
```

```python
# Check irreversibility
props = h.get_dynamic_global_properties()
head_block = props["head_block_number"]
irreversible = props["last_irreversible_block_num"]
pending_blocks = head_block - irreversible

print(f"Head block: {head_block}")
print(f"Last irreversible: {irreversible}")
print(f"Pending confirmation: {pending_blocks} blocks")
# Typically 15-20 blocks behind head
```

### Why DPoS Works for Hive

| Feature | DPoS (Hive) | PoW (Bitcoin) | PoS (Ethereum) |
|---------|-------------|---------------|-----------------|
| Block time | 3 seconds | ~10 minutes | ~12 seconds |
| Finality | ~45 seconds | ~60 minutes | ~15 minutes |
| Energy use | Minimal | Massive | Low |
| Throughput | ~10K ops/block | ~3K tx/block | ~30 tx/sec |
| Governance | Stake-weighted voting | None (miners) | Validators |

### Important for App Developers

1. **Wait for irreversibility**: For financial operations, don't consider a transaction "confirmed" until `block_num <= last_irreversible_block_num`.
2. **Handle microforks**: Blocks can be undone before irreversibility. Design your state machine to handle replays.
3. **3-second blocks**: Don't poll faster than 3 seconds — there won't be new data.
4. **Witness votes matter**: If you build a dApp with users who stake HP, encourage them to vote for reliable witnesses. It's ecosystem governance.'''),

    ("hive_deep1_27", r'''How do I set up and query different Hive API nodes? What are the different API types and when should I use each?''', r'''<think>
Hive has multiple API layers, each serving different purposes:
1. condenser_api — Legacy Steem-compatible API (most commonly used)
2. database_api — Low-level chain queries
3. block_api — Block data
4. rc_api — Resource credits
5. account_history_api — Account operation history
6. network_broadcast_api — Transaction broadcasting

Different node types expose different APIs. Full API nodes are expensive to run, so many community nodes only expose a subset. I should show how to query each API and explain failover patterns.
</think>

## Hive API Nodes and Query Patterns

### Available API Nodes

```python
# Public API nodes (community-run)
API_NODES = [
    "https://api.hive.blog",        # Official
    "https://api.deathwing.me",     # DeathWing
    "https://hive-api.arcange.eu",  # Arcange
    "https://api.openhive.network", # OpenHive
    "https://rpc.mahdiyari.info",   # Mahdiyari
]

# Using beem with multiple nodes (automatic failover)
from beem import Hive
h = Hive(node=API_NODES)  # Tries each in order if one fails
```

### API Categories

#### condenser_api (Legacy — Most Common)

```python
import requests

def condenser_call(method, params, node="https://api.hive.blog"):
    """Make a condenser_api call."""
    resp = requests.post(node, json={
        "jsonrpc": "2.0", "id": 1,
        "method": f"condenser_api.{method}",
        "params": params
    })
    return resp.json()["result"]

# Get account info
accounts = condenser_call("get_accounts", [["username"]])
print(f"Balance: {accounts[0]['balance']}")
print(f"HP: {accounts[0]['vesting_shares']}")

# Get post content
post = condenser_call("get_content", ["author", "permlink"])
print(f"Title: {post['title']}")
print(f"Votes: {post['net_votes']}")

# Get trending posts
trending = condenser_call("get_discussions_by_trending", [{"tag": "hive", "limit": 10}])
```

#### database_api (Low-Level)

```python
# database_api uses a different parameter format
def database_call(method, params, node="https://api.hive.blog"):
    resp = requests.post(node, json={
        "jsonrpc": "2.0", "id": 1,
        "method": f"database_api.{method}",
        "params": params  # Named params (dict), not positional (list)
    })
    return resp.json()["result"]

# Find accounts
result = database_call("find_accounts", {"accounts": ["username"]})

# List witnesses by vote
result = database_call("list_witnesses", {
    "start": "", "limit": 21, "order": "by_vote_name"
})
```

#### rc_api (Resource Credits)

```python
# Check RC for an account
result = requests.post("https://api.hive.blog", json={
    "jsonrpc": "2.0", "id": 1,
    "method": "rc_api.find_rc_accounts",
    "params": {"accounts": ["username"]}
}).json()["result"]

rc = result["rc_accounts"][0]
print(f"RC mana: {rc['rc_manabar']['current_mana']}")
print(f"RC max: {rc['max_rc']}")
rc_pct = int(rc["rc_manabar"]["current_mana"]) / max(int(rc["max_rc"]), 1) * 100
print(f"RC: {rc_pct:.1f}%")
```

### Failover Pattern

```python
class HiveAPI:
    """API client with automatic failover across multiple nodes."""

    def __init__(self, nodes=None):
        self.nodes = nodes or API_NODES
        self.current = 0

    def call(self, method, params, max_retries=3):
        for attempt in range(max_retries):
            node = self.nodes[self.current % len(self.nodes)]
            try:
                resp = requests.post(node, json={
                    "jsonrpc": "2.0", "id": 1,
                    "method": method, "params": params
                }, timeout=10)
                result = resp.json()
                if "error" in result:
                    raise Exception(result["error"]["message"])
                return result["result"]
            except Exception as e:
                print(f"Node {node} failed: {e}")
                self.current += 1  # Try next node

        raise Exception(f"All {max_retries} attempts failed")

api = HiveAPI()
accounts = api.call("condenser_api.get_accounts", [["username"]])
```

### When to Use Each API

| Need | API | Why |
|------|-----|-----|
| Get account info | `condenser_api.get_accounts` | Simple, well-documented |
| Browse posts | `condenser_api.get_discussions_by_*` | Served by Hivemind |
| Transaction history | `account_history_api.get_account_history` | Indexed by account |
| Check RC | `rc_api.find_rc_accounts` | RC-specific data |
| Block data | `block_api.get_block` | Raw block content |
| Broadcast tx | `network_broadcast_api.broadcast_transaction` | Send transactions |
| Complex queries | HAF (SQL) | Joins, aggregations, full history |'''),

    ("hive_deep1_28", r'''What is Hivemind and how does it work? How do posts, communities, and social features get indexed?''', r'''<think>
Hivemind is the social consensus layer of Hive. It's a separate process that indexes social data from the blockchain into PostgreSQL. This is how frontends like PeakD and Ecency get post data, community info, follows, trending rankings, etc.

Key concepts:
- Hivemind is NOT part of hived (the blockchain node) — it runs alongside it
- It reads operations from the blockchain and builds a social database
- It serves social APIs (discussions, communities, follows)
- Post ranking algorithms (trending, hot) run inside Hivemind
</think>

## Hivemind: The Social Consensus Layer

Hivemind is a separate process that indexes social data from the Hive blockchain into PostgreSQL, providing the social API layer for frontends.

### Architecture

```
Hive Blockchain (hived)
        │
        │ streams operations
        ▼
    Hivemind (Python process)
        │
        │ indexes into
        ▼
    PostgreSQL Database
        │
        │ serves via
        ▼
    Social APIs (discussions, communities, follows, trending)
        │
        │ consumed by
        ▼
    Frontends (PeakD, Ecency, Hive.blog)
```

### What Hivemind Indexes

| Data | Source Operation | Stored As |
|------|-----------------|-----------|
| Posts & comments | `comment` op | Threaded post tree with metadata |
| Votes | `vote` op | Vote records, reputation scores |
| Follows/mutes | `custom_json` (id: "follow") | Social graph |
| Communities | `custom_json` (id: "community") | Community membership, roles, settings |
| Reblogs | `custom_json` (id: "reblog") | Reblog records |
| Post metadata | `comment_options` op | Beneficiaries, max payout, payout type |

### Querying Posts Through Hivemind

```python
import requests

def get_discussions(sort="trending", tag=None, limit=10):
    """Get posts from Hivemind's discussion APIs."""
    params = {"limit": limit}
    if tag:
        params["tag"] = tag

    # These APIs are served by Hivemind, not hived directly
    resp = requests.post("https://api.hive.blog", json={
        "jsonrpc": "2.0", "id": 1,
        "method": f"condenser_api.get_discussions_by_{sort}",
        "params": [params]
    })
    return resp.json()["result"]

# Get trending posts
trending = get_discussions("trending", tag="hive", limit=5)
for post in trending:
    print(f"  {post['author']}/{post['permlink']}: {post['title']}")
    print(f"    votes: {post['net_votes']}, payout: {post['pending_payout_value']}")

# Available sort methods:
# trending, created, hot, promoted, payout, payout_comments
```

### Community APIs

```python
# List communities
resp = requests.post("https://api.hive.blog", json={
    "jsonrpc": "2.0", "id": 1,
    "method": "bridge.list_communities",
    "params": {"limit": 10, "sort": "rank"}
})
communities = resp.json()["result"]
for c in communities:
    print(f"  {c['name']}: {c['title']} ({c['subscribers']} subscribers)")

# Get posts in a community
resp = requests.post("https://api.hive.blog", json={
    "jsonrpc": "2.0", "id": 1,
    "method": "bridge.get_ranked_posts",
    "params": {"sort": "trending", "tag": "hive-169321", "limit": 5}
})
```

### Using beem for Social Queries

```python
from beem import Hive
from beem.discussions import Query, Discussions_by_trending

h = Hive()

# Get trending discussions
q = Query(limit=10, tag="hive")
trending = Discussions_by_trending(q, blockchain_instance=h)

for post in trending:
    print(f"{post.author}/{post.permlink}")
    print(f"  Title: {post.title}")
    print(f"  Pending payout: {post.pending_payout_value}")
    print(f"  Votes: {post.net_votes}")

# Get a specific post with all replies
from beem.comment import Comment
post = Comment("@author/permlink", blockchain_instance=h)
print(f"Title: {post.title}")
print(f"Body: {post.body[:200]}...")

# Get all replies
replies = post.get_replies()
for reply in replies:
    print(f"  Reply by {reply.author}: {reply.body[:100]}...")
```

### Trending Algorithm

Hivemind's trending score uses a time-decay formula:

```
trending_score = rshares / (time_since_creation + CONTENT_CONSTANT)^ORDER
```

Where:
- **rshares**: Total reward shares (HP-weighted vote value)
- **time_since_creation**: Hours since post was created
- **CONTENT_CONSTANT**: Prevents division by zero, smooths early scores
- **ORDER**: Decay exponent (higher = faster decay)

This means that recent posts with high vote value trend higher, but all posts eventually decay off the trending page. The "hot" algorithm is similar but decays faster, favoring very recent engagement.

### Key Points for Developers

1. **Hivemind is eventually consistent**: There's a small delay between a blockchain operation and it appearing in Hivemind queries (usually <3 seconds).
2. **Not all nodes run Hivemind**: If your API calls for discussions return errors, you might be hitting a node without Hivemind.
3. **bridge API**: The `bridge.*` methods are Hivemind-specific and provide richer data than `condenser_api`.
4. **Community moderation**: Communities can mute posts (hide from feed) but cannot delete them from the blockchain — they're still there if you query directly.'''),

    ("hive_deep1_29", r'''How do I run my own Hive API node? What are the hardware requirements and configuration options?''', r'''<think>
Running a Hive node involves setting up hived (the blockchain daemon), and optionally Hivemind for social APIs. The hardware requirements depend on which plugins/APIs you want to serve.

Key decisions:
- Full API node vs minimal node
- Which API plugins to enable
- Replay from genesis vs snapshot
- Docker vs bare metal
</think>

## Running a Hive API Node

### Hardware Requirements

| Node Type | Disk | RAM | CPU | Use Case |
|-----------|------|-----|-----|----------|
| **Witness (consensus)** | ~50 GB SSD | 16 GB | 4 cores | Block production only |
| **Minimal API** | ~100 GB SSD | 32 GB | 4 cores | Basic queries, no history |
| **Full API** | ~500 GB+ NVMe | 64 GB+ | 8+ cores | All APIs, full history |
| **Full + Hivemind** | ~700 GB+ NVMe | 96 GB+ | 8+ cores | Social APIs + chain data |
| **HAF node** | ~1 TB+ NVMe | 64 GB+ | 8+ cores | SQL-based app framework |

### Docker Setup (Recommended)

```bash
# Pull the latest Hive image
docker pull hiveio/hive:latest

# Create data directory
mkdir -p /opt/hive/datadir

# Generate default config
docker run --rm -v /opt/hive/datadir:/hive/datadir \
  hiveio/hive --dump-config > /opt/hive/datadir/config.ini
```

### Configuration (config.ini)

```ini
# === Minimal API Node ===
# Network
p2p-endpoint = 0.0.0.0:2001
webserver-http-endpoint = 0.0.0.0:8091
webserver-ws-endpoint = 0.0.0.0:8090

# Plugins — choose what APIs to serve
plugin = condenser_api
plugin = database_api
plugin = block_api
plugin = rc_api
plugin = network_broadcast_api

# For account history (optional, uses more disk)
# plugin = account_history_api
# plugin = account_history_rocksdb

# Memory optimization
shared-file-size = 24G

# Seed nodes (for initial sync)
p2p-seed-node = seed.hive.blog:2001
p2p-seed-node = seed.openhive.network:2001
p2p-seed-node = anyx.io:2001
```

### Starting the Node

```bash
# Start with Docker
docker run -d --name hived \
  -v /opt/hive/datadir:/hive/datadir \
  -p 8091:8091 \
  -p 2001:2001 \
  --restart unless-stopped \
  hiveio/hive

# Monitor sync progress
docker logs -f hived 2>&1 | grep -E "block|sync|replay"

# Check if node is synced
curl -s http://localhost:8091 -d '{
  "jsonrpc":"2.0","id":1,
  "method":"condenser_api.get_dynamic_global_properties","params":[]
}' | python -m json.tool | grep head_block
```

### Sync Options

```bash
# Option 1: Replay from genesis (slowest — days to weeks)
docker run -d --name hived \
  -v /opt/hive/datadir:/hive/datadir \
  hiveio/hive --replay-blockchain

# Option 2: Use a snapshot (fastest — hours)
# Download snapshot from a trusted source
wget https://gtg.openhive.network/get/snapshot/block_log
mv block_log /opt/hive/datadir/blockchain/
docker run -d --name hived \
  -v /opt/hive/datadir:/hive/datadir \
  hiveio/hive --replay-blockchain
```

### Adding Hivemind (Social APIs)

```bash
# Hivemind runs alongside hived, indexing into PostgreSQL
docker run -d --name hivemind \
  -e DATABASE_URL=postgresql://hivemind:pass@postgres:5432/hivemind \
  -e STEEMD_URL=http://hived:8091 \
  -p 8080:8080 \
  hiveio/hivemind

# Hivemind sync takes 24-48 hours for initial indexing
```

### Health Monitoring

```python
import requests

def check_node_health(url="http://localhost:8091"):
    """Check if your node is healthy and synced."""
    try:
        resp = requests.post(url, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "condenser_api.get_dynamic_global_properties",
            "params": []
        }, timeout=5)
        props = resp.json()["result"]

        head_block = props["head_block_number"]
        head_time = props["time"]
        irreversible = props["last_irreversible_block_num"]

        # Check if node is behind
        from datetime import datetime, timezone
        block_time = datetime.fromisoformat(head_time.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - block_time).total_seconds()

        return {
            "healthy": age < 30,  # Should be within 30 seconds
            "head_block": head_block,
            "irreversible": irreversible,
            "age_seconds": int(age),
            "behind": age > 30
        }
    except Exception as e:
        return {"healthy": False, "error": str(e)}
```

### Cost Considerations

- **Full API node**: ~$100-200/month (VPS with NVMe + RAM)
- **Witness node**: ~$30-50/month (minimal resources)
- **Storage growth**: ~1-2 GB/month for block data
- **Bandwidth**: Moderate for private use, high for public API service
- **Alternative**: Use public API nodes for development, own node for production reliability'''),

    ("hive_deep1_30", r'''What is the Hive Decentralized Fund (DHF/DAO) and how do I create and vote on proposals programmatically?''', r'''<think>
The DHF (Decentralized Hive Fund), also known as the DAO, is Hive's treasury system. Stakeholders vote on proposals to fund development, marketing, and community projects. Funded from a portion of the inflation.

Key operations:
- Creating proposals
- Voting on proposals
- Querying active proposals
- Tracking proposal funding

I should show beem API calls and explain how the funding threshold works.
</think>

## Hive Decentralized Fund (DHF/DAO)

The DHF is Hive's on-chain treasury. A portion of daily HIVE inflation goes into the fund, and stakeholders vote to direct those funds to proposals.

### How Funding Works

```
Daily HIVE Inflation
        │
        ├── 65% → Author/Curator Rewards
        ├── 15% → HP holders (vesting)
        ├── 10% → DHF (Decentralized Fund)
        └── 10% → Witnesses

DHF proposals are funded IF:
  proposal_votes > return_proposal_votes

The "return proposal" is a special proposal that sets the funding threshold.
Any proposal with more votes gets funded; those with fewer do not.
```

### Querying Proposals

```python
from beem import Hive
from beem.account import Account
import requests

h = Hive()

# Get all active proposals
resp = requests.post("https://api.hive.blog", json={
    "jsonrpc": "2.0", "id": 1,
    "method": "database_api.list_proposals",
    "params": {
        "start": [""],
        "limit": 100,
        "order": "by_total_votes",
        "order_direction": "descending",
        "status": "active"
    }
})
proposals = resp.json()["result"]["proposals"]

for p in proposals[:10]:
    print(f"#{p['id']}: {p['subject']}")
    print(f"  Creator: {p['creator']}")
    print(f"  Daily pay: {p['daily_pay']}")
    print(f"  Total votes: {p['total_votes']}")
    print(f"  Status: {p['status']}")
    print()
```

### Voting on Proposals

```python
h = Hive(keys=["5K...active_wif"])

# Vote FOR a proposal
h.update_proposal_votes(
    proposal_ids=[42],      # Proposal ID(s)
    approve=True,           # True = support, False = remove vote
    account="myaccount"
)

# Remove vote from a proposal
h.update_proposal_votes(
    proposal_ids=[42],
    approve=False,
    account="myaccount"
)

# Vote for multiple proposals at once
h.update_proposal_votes(
    proposal_ids=[42, 55, 67],
    approve=True,
    account="myaccount"
)
```

### Creating a Proposal

```python
from datetime import datetime, timedelta

h = Hive(keys=["5K...active_wif"])

# Create a funding proposal
# Requires a Hive post as the proposal body (create the post first)
h.create_proposal(
    creator="myaccount",
    receiver="myaccount",           # Who receives the daily pay
    start_date=datetime.utcnow(),
    end_date=datetime.utcnow() + timedelta(days=90),
    daily_pay="50.000 HBD",        # Daily funding amount
    subject="Fund MyApp Development",
    permlink="my-proposal-post",    # Permlink of the proposal description post
)
# Creating a proposal costs 10 HBD (burned) + 1 HBD refundable
```

### Tracking Proposal Funding

```python
def check_proposal_funding(proposal_id):
    """Check if a proposal is above the funding threshold."""
    resp = requests.post("https://api.hive.blog", json={
        "jsonrpc": "2.0", "id": 1,
        "method": "database_api.find_proposals",
        "params": {"proposal_ids": [proposal_id]}
    })
    proposal = resp.json()["result"]["proposals"][0]

    # Get the return proposal (threshold)
    resp2 = requests.post("https://api.hive.blog", json={
        "jsonrpc": "2.0", "id": 1,
        "method": "database_api.find_proposals",
        "params": {"proposal_ids": [0]}  # Return proposal is always ID 0
    })
    return_proposal = resp2.json()["result"]["proposals"][0]

    is_funded = int(proposal["total_votes"]) > int(return_proposal["total_votes"])

    return {
        "id": proposal_id,
        "subject": proposal["subject"],
        "daily_pay": proposal["daily_pay"],
        "total_votes": proposal["total_votes"],
        "threshold_votes": return_proposal["total_votes"],
        "is_funded": is_funded,
        "status": proposal["status"]
    }

status = check_proposal_funding(42)
print(f"Proposal #{status['id']}: {status['subject']}")
print(f"  Funded: {'YES' if status['is_funded'] else 'NO'}")
print(f"  Votes: {status['total_votes']} (threshold: {status['threshold_votes']})")
```

### Key Points

1. **Return proposal is the threshold**: The special "return" proposal (ID 0) determines the funding cutoff. Vote for it to raise the bar; vote for other proposals to fund them.
2. **Daily pay in HBD**: Proposals are paid daily in HBD (Hive Backed Dollars), providing stable funding.
3. **No retroactive funding**: Proposals only receive funds for days they are active AND above the threshold.
4. **Anyone can propose**: Creating a proposal costs 10 HBD (burned) to prevent spam, plus 1 HBD refundable when the proposal ends.
5. **HP-weighted voting**: Your vote power is proportional to your Hive Power stake. Large stakeholders have more influence.
6. **Governance participation**: Voting on proposals is a key governance mechanism — encourage your dApp users to participate.'''),
]
