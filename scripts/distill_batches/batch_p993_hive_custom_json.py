"""Hive blockchain training pairs: custom_json operations."""

PAIRS = [
    (
        "hive/custom-json-broadcast",
        r'''How do I broadcast a custom_json operation on the Hive blockchain using Python's beem library? I want to send structured data for a dApp.''',
        r'''<think>
The user wants to broadcast a custom_json operation. Let me think about what that involves. custom_json could be done through several beem methods... I could suggest the commit.custom_json shortcut, but wait -- they said they want to send structured data for a dApp, so they probably need full control over the operation fields.

The key parameters are required_auths vs required_posting_auths. Hmm, which should I recommend? I was initially thinking required_auths since it sounds more "official," but actually that would be wrong for most dApp use cases -- required_auths needs the active key, which is riskier. Most dApps use required_posting_auths because the posting key has a narrower blast radius if compromised. So posting auth is the safer default here.

Now, the id field -- could be up to 64 characters? No wait, I need to double-check that. The max length for id is 32 characters, not 64. And the json payload is limited to 8192 bytes, which matters because larger payloads will simply be rejected at the node level.

I should show both TransactionBuilder (for full control) and the simpler hive.custom_json method, since different situations call for different approaches. Hive Engine uses "ssc-mainnet-hive" as its id, which is a good real-world reference point.
</think>

Broadcasting a custom_json operation with beem involves creating the operation dict and pushing it through the TransactionBuilder or using the built-in commit method.

Here is a complete example using beem:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json

# Connect with your posting key
hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingPrivateKeyHere"]
)

# Define the custom_json payload
payload = {
    "app": "myapp/1.0",
    "action": "register_user",
    "data": {
        "username": "newuser123",
        "preferences": {"theme": "dark", "lang": "en"},
        "timestamp": "2025-01-15T12:00:00"
    }
}

# Method 1: Using TransactionBuilder for full control
tx = TransactionBuilder(hive_instance=hive)
op = Custom_json(**{
    "required_auths": [],
    "required_posting_auths": ["youraccount"],
    "id": "myapp",
    "json": json.dumps(payload)
})
tx.appendOps(op)
tx.appendSigner("youraccount", "posting")
tx.sign()
result = tx.broadcast()
print(f"Transaction ID: {result['id']}")

# Method 2: Simpler approach using hive.custom_json
result = hive.custom_json(
    id="myapp",
    json_data=payload,
    required_posting_auths=["youraccount"]
)
print(f"Broadcast result: {result}")
```

Key constraints to remember:
- The "id" field is limited to 32 characters and identifies your dApp
- The "json" payload is limited to 8192 bytes
- Use required_posting_auths for social/non-financial operations (safer)
- Use required_auths only when the operation needs active authority
- Each custom_json costs Resource Credits (RC), not fees
- Multiple apps can share the same id, so design your payload schema carefully
'''
    ),
    (
        "hive/custom-json-hive-engine-transfer",
        r'''Show me how to transfer Hive Engine tokens using custom_json operations with the dhive JavaScript library.''',
        r'''Hive Engine tokens are managed entirely through custom_json operations on the Hive blockchain. The sidechain nodes watch for operations with the id "ssc-mainnet-hive" and process them accordingly.

Here is how to transfer Hive Engine tokens using dhive:

```javascript
const dhive = require("@hiveio/dhive");

const client = new dhive.Client([
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://api.openhive.network"
]);

const privateKey = dhive.PrivateKey.fromString("5YourActiveKeyHere");

async function transferHiveEngineToken(from, to, symbol, quantity, memo) {
    const jsonPayload = {
        contractName: "tokens",
        contractAction: "transfer",
        contractPayload: {
            symbol: symbol,
            to: to,
            quantity: quantity.toString(),
            memo: memo || ""
        }
    };

    const op = {
        required_auths: [from],
        required_posting_auths: [],
        id: "ssc-mainnet-hive",
        json: JSON.stringify(jsonPayload)
    };

    try {
        const result = await client.broadcast.json(op, privateKey);
        console.log("Transfer broadcast:", result.id);

        // Verify on sidechain after a few seconds
        const verifyUrl = "https://api.hive-engine.com/rpc/contracts";
        const resp = await fetch(verifyUrl, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                jsonrpc: "2.0",
                id: 1,
                method: "find",
                params: {
                    contract: "tokens",
                    table: "balances",
                    query: {account: from, symbol: symbol}
                }
            })
        });
        const balance = await resp.json();
        console.log("Updated balance:", balance.result);
    } catch (err) {
        console.error("Transfer failed:", err.message);
    }
}

// Transfer 10 BEE tokens
transferHiveEngineToken("alice", "bob", "BEE", "10", "Payment for services");
```

Important notes:
- Hive Engine transfers require active authority (required_auths), not posting
- The quantity must be a string, not a number
- The id must be exactly "ssc-mainnet-hive" for mainnet operations
- Sidechain confirmation takes a few seconds after the Hive block is produced
- You can query balances via the Hive Engine API at api.hive-engine.com
'''
    ),
    (
        "hive/custom-json-nft-operations",
        r'''How do I create and transfer NFTs on Hive using custom_json? Show me the Hive Engine NFT contract operations.''',
        r'''NFTs on Hive Engine use the "nft" contract through custom_json operations. Here is a complete workflow for creating an NFT collection, issuing tokens, and transferring them:

```javascript
const dhive = require("@hiveio/dhive");

const client = new dhive.Client(["https://api.hive.blog"]);
const activeKey = dhive.PrivateKey.fromString("5YourActiveKeyHere");

// Helper to broadcast Hive Engine operations
async function broadcastHE(account, payload) {
    const op = {
        required_auths: [account],
        required_posting_auths: [],
        id: "ssc-mainnet-hive",
        json: JSON.stringify(payload)
    };
    return await client.broadcast.json(op, activeKey);
}

// Step 1: Create an NFT collection
async function createNFTCollection() {
    const payload = {
        contractName: "nft",
        contractAction: "create",
        contractPayload: {
            symbol: "MYART",
            name: "My Art Collection",
            maxSupply: 1000,
            url: "https://myapp.com/nft",
            authorizedIssuingAccounts: ["youraccount"],
            authorizedIssuingContracts: []
        }
    };
    const result = await broadcastHE("youraccount", payload);
    console.log("NFT collection created:", result.id);
}

// Step 2: Add data properties to the NFT
async function addNFTProperties() {
    const payload = {
        contractName: "nft",
        contractAction: "addProperty",
        contractPayload: {
            symbol: "MYART",
            name: "image_url",
            type: "string",
            isReadOnly: true
        }
    };
    await broadcastHE("youraccount", payload);

    const rarityProp = {
        contractName: "nft",
        contractAction: "addProperty",
        contractPayload: {
            symbol: "MYART",
            name: "rarity",
            type: "string",
            isReadOnly: true
        }
    };
    await broadcastHE("youraccount", rarityProp);
}

// Step 3: Issue (mint) NFT instances
async function mintNFT(toAccount, properties) {
    const payload = {
        contractName: "nft",
        contractAction: "issue",
        contractPayload: {
            symbol: "MYART",
            to: toAccount,
            feeSymbol: "BEE",
            properties: properties
        }
    };
    return await broadcastHE("youraccount", payload);
}

// Step 4: Transfer an NFT
async function transferNFT(from, to, nftId) {
    const payload = {
        contractName: "nft",
        contractAction: "transfer",
        contractPayload: {
            to: to,
            nfts: [
                {symbol: "MYART", ids: [nftId]}
            ]
        }
    };
    return await broadcastHE(from, payload);
}

// Usage
async function main() {
    await createNFTCollection();
    await addNFTProperties();
    await mintNFT("collector1", {
        image_url: "https://myapp.com/art/001.png",
        rarity: "legendary"
    });
    await transferNFT("collector1", "collector2", "1");
}

main().catch(console.error);
```

Each NFT operation costs BEE tokens as a sidechain fee. Creating a collection costs 100 BEE, issuing costs 0.001 BEE per instance. These fees are subject to change via sidechain governance.
'''
    ),
    (
        "hive/custom-json-game-state",
        r'''I am building a blockchain game on Hive. How should I structure custom_json operations for game state updates like player moves, inventory changes, and battle results?''',
        r'''<think>
A blockchain game on Hive -- interesting. My first instinct is to put all game state on-chain, but wait, that would be extremely expensive in RC terms. Every player move, every inventory update would consume resource credits. So the real question is: what needs to go on-chain vs what can stay off-chain?

I initially considered having separate custom_json ids for each action type (one for moves, one for crafting, one for trades), but actually that would make indexing harder. Splinterlands and dCrops use a single dApp id with an "action" field inside the JSON to distinguish operation types -- and that makes more sense because you only need to filter on one id when streaming blocks.

Now for auth levels... hmm, should gameplay actions use active or posting authority? Since gameplay moves are non-financial, posting auth is the right call -- it is lower risk if a key leaks. But wait, what about trading in-game assets for tokens? That involves value transfer, so those operations specifically should require active auth. Therefore I need a mixed approach: posting for social/gameplay actions, active for anything involving asset transfers.

The server-side validation pattern is also critical here. Because custom_json is just arbitrary data, the game engine must replay all operations deterministically to derive the current state. Without that, players could broadcast invalid moves.
</think>

Here is a robust pattern for structuring a Hive blockchain game using custom_json:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json
import hashlib
import time

GAME_ID = "mygame"

class HiveGameClient:
    def __init__(self, account, posting_key, node=None):
        self.account = account
        self.hive = Hive(
            node=node or ["https://api.hive.blog"],
            keys=[posting_key]
        )

    def _broadcast_action(self, action, data, use_active=False):
        payload = {
            "app": f"{GAME_ID}/1.0",
            "action": action,
            "data": data,
            "ts": int(time.time())
        }
        auths = {
            "required_auths": [self.account] if use_active else [],
            "required_posting_auths": [] if use_active else [self.account],
            "id": GAME_ID,
            "json": json.dumps(payload)
        }
        return self.hive.custom_json(**auths)

    def submit_move(self, match_id, move_type, position):
        """Submit a player move in a match."""
        return self._broadcast_action("move", {
            "match_id": match_id,
            "move": move_type,
            "pos": position,
            "nonce": hashlib.sha256(
                f"{self.account}{match_id}{time.time()}".encode()
            ).hexdigest()[:16]
        })

    def craft_item(self, recipe_id, materials):
        """Craft an item by consuming materials."""
        return self._broadcast_action("craft", {
            "recipe": recipe_id,
            "materials": materials
        })

    def trade_asset(self, to_player, asset_id, price_token, price_amount):
        """Trade a game asset (requires active auth)."""
        return self._broadcast_action("trade", {
            "to": to_player,
            "asset_id": asset_id,
            "price": {"token": price_token, "amount": str(price_amount)}
        }, use_active=True)

    def submit_battle_result(self, match_id, seed, team_hash):
        """Submit battle lineup with commit-reveal pattern."""
        return self._broadcast_action("battle_commit", {
            "match_id": match_id,
            "team_hash": team_hash,
            "seed": seed
        })


# Server-side: replay custom_json to build game state
class GameStateEngine:
    def __init__(self):
        self.players = {}
        self.matches = {}

    def process_operation(self, op):
        if op["id"] != GAME_ID:
            return
        data = json.loads(op["json"])
        action = data.get("action")
        account = (op.get("required_posting_auths") or
                   op.get("required_auths", []))[0]

        if action == "move":
            self._handle_move(account, data["data"])
        elif action == "craft":
            self._handle_craft(account, data["data"])
        elif action == "trade":
            self._handle_trade(account, data["data"])

    def _handle_move(self, player, data):
        match = self.matches.get(data["match_id"], {})
        match.setdefault("moves", []).append({
            "player": player,
            "move": data["move"],
            "pos": data["pos"]
        })
        self.matches[data["match_id"]] = match
```

This pattern gives you verifiable game state through operation replay, commit-reveal for hidden information, and clear separation between social actions (posting key) and financial actions (active key).
'''
    ),
    (
        "hive/custom-json-parsing-filtering",
        r'''How do I parse and filter custom_json operations from the Hive blockchain to find operations for my specific dApp?''',
        r'''To parse and filter custom_json operations from Hive, you can use the account_history_api, stream blocks in real-time, or query specific operations. Here are multiple approaches:

```python
from beem import Hive
from beem.blockchain import Blockchain
from beem.account import Account
import json

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

# Approach 1: Stream custom_json operations in real-time
def stream_dapp_operations(dapp_id, callback):
    blockchain = Blockchain(hive_instance=hive)
    stream = blockchain.stream(
        opNames=["custom_json"],
        raw_ops=False,
        threading=False
    )
    for op in stream:
        if op.get("id") == dapp_id:
            try:
                parsed = json.loads(op["json"])
                account = (op.get("required_posting_auths") or
                           op.get("required_auths", [None]))[0]
                callback(account, parsed, op)
            except json.JSONDecodeError:
                continue

# Approach 2: Get historical custom_json for a specific account
def get_account_custom_json(account_name, dapp_id, limit=100):
    account = Account(account_name, hive_instance=hive)
    history = account.get_account_history(
        index=-1,
        limit=limit,
        only_ops=["custom_json"]
    )
    results = []
    for entry in history:
        op = entry["op"]
        if isinstance(op, list):
            op_data = op[1]
        else:
            op_data = op
        if op_data.get("id") == dapp_id:
            results.append({
                "block": entry.get("block"),
                "timestamp": entry.get("timestamp"),
                "account": account_name,
                "data": json.loads(op_data["json"])
            })
    return results

# Approach 3: Scan a range of blocks for custom_json
def scan_blocks_for_custom_json(start_block, end_block, dapp_id):
    blockchain = Blockchain(hive_instance=hive)
    ops = []
    for block_num in range(start_block, end_block + 1):
        block = blockchain.get_block(block_num)
        if not block or "transactions" not in block:
            continue
        for tx in block["transactions"]:
            for op in tx["operations"]:
                op_type = op[0] if isinstance(op, list) else op["type"]
                op_data = op[1] if isinstance(op, list) else op["value"]
                if op_type == "custom_json" and op_data.get("id") == dapp_id:
                    parsed = json.loads(op_data["json"])
                    ops.append({
                        "block": block_num,
                        "data": parsed,
                        "accounts": (op_data.get("required_posting_auths", []) +
                                     op_data.get("required_auths", []))
                    })
    return ops

# Example usage: monitor a game's operations
def on_game_event(account, data, raw_op):
    action = data.get("action", "unknown")
    print(f"[{action}] {account}: {json.dumps(data, indent=2)}")

# Stream all operations for our game
stream_dapp_operations("mygame", on_game_event)
```

When filtering at scale, prefer streaming with opNames filter to avoid processing irrelevant operations. For historical analysis, the account_history approach is more efficient than scanning every block. The block scanning method is useful for building a complete index of all operations for a given dApp across all accounts.
'''
    ),
]
