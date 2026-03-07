"""
Hive blockchain thinking pairs - custom JSON architecture decisions
"""

pairs = [
    {
        "instruction": r'''I am building a decentralized game on Hive. Players can attack, defend, trade items, and join guilds. How should I design my custom_json schema for these actions?''',
        "output": r'''<think>
Okay, designing a custom_json schema for a game on Hive. Let me think about the constraints first. Each custom_json operation has a max payload of 8192 bytes. The "id" field is the operation type identifier, and "json" contains the payload.

Should I use one id for everything like "mygame" or separate ids like "mygame_attack", "mygame_trade"? Hmm, if I use one id, then indexers only need to filter for one operation type, which is simpler. But the payload needs a "type" or "action" field to distinguish actions. If I use separate ids, filtering is easier per action type, but registering many ids clutters the namespace.

I initially thought separate ids would be cleaner, but actually most successful Hive games (Splinterlands uses "sm_" prefix with separate ids) use a prefix with separate ids per action. Wait, but Splinterlands is a special case because they have SO many operations. For a simpler game, a single id with an action field might be better.

The tradeoff is: single id = simpler indexer setup, multiple ids = faster filtering when you only care about one action type. For a game with 4 action types, single id is fine. For 50+ action types, separate ids.

I also need to think about schema versioning. What happens when I add new fields? I should include a version field from day one. And the payload should be as compact as possible to stay under the 8192 byte limit -- short field names matter for things like trade inventories.
</think>

For a game with a moderate number of action types, use a single custom_json id with an action discriminator and schema version:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json
import time

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)

GAME_ID = "mygame"
SCHEMA_VERSION = 1

# === Schema Definitions ===

def make_payload(action, data):
    """Wrap game action with version and timestamp."""
    payload = {
        "v": SCHEMA_VERSION,
        "a": action,      # short key names save bytes
        "t": int(time.time()),
        "d": data
    }
    encoded = json.dumps(payload, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 8192:
        raise ValueError(f"Payload too large: {len(encoded)} bytes")
    return encoded


def broadcast_action(account, action, data):
    """Broadcast a game action as custom_json."""
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [account],
        "id": GAME_ID,
        "json": make_payload(action, data)
    }))
    tx.appendSigner(account, "posting")
    tx.sign()
    return tx.broadcast()


# === Game Actions ===

def attack(player, target, weapon_id, coords):
    """Attack another player."""
    return broadcast_action(player, "atk", {
        "tgt": target,
        "wid": weapon_id,
        "x": coords[0],
        "y": coords[1]
    })


def defend(player, shield_id, stance):
    """Set defensive stance."""
    return broadcast_action(player, "def", {
        "sid": shield_id,
        "st": stance  # "block", "parry", "dodge"
    })


def trade_offer(player, target, offer_items, want_items):
    """Propose a trade with another player."""
    return broadcast_action(player, "trd", {
        "to": target,
        "off": offer_items,   # [{"id": 42, "qty": 1}, ...]
        "want": want_items,
        "exp": int(time.time()) + 3600  # expires in 1 hour
    })


def join_guild(player, guild_id):
    """Request to join a guild."""
    return broadcast_action(player, "gjoin", {
        "gid": guild_id
    })


# === Indexer Side (reading these operations) ===

def process_game_operation(op_json_str):
    """Parse and route a game operation."""
    data = json.loads(op_json_str)
    version = data.get("v", 0)
    action = data.get("a")

    # Version migration
    if version < SCHEMA_VERSION:
        data = migrate_payload(data, version)

    handlers = {
        "atk": handle_attack,
        "def": handle_defend,
        "trd": handle_trade,
        "gjoin": handle_guild_join,
    }

    handler = handlers.get(action)
    if handler:
        handler(data["d"])
    else:
        print(f"Unknown action: {action}")


def migrate_payload(data, from_version):
    """Migrate old schema versions to current."""
    # Example: v0 used "action" instead of "a"
    if from_version == 0:
        data["a"] = data.pop("action", data.get("a"))
        data["v"] = 1
    return data
```

Key design decisions:
- Single id (`mygame`) -- 4 action types does not justify multiple ids
- Short keys (`a`, `v`, `d`, `tgt`) -- saves bytes in the 8192-byte limit
- Version field from day one -- you will change the schema, guaranteed
- Timestamps in payload -- block timestamps exist but payload timestamps let you detect delayed broadcasts
- Compact JSON with `separators=(",",":")` -- no whitespace waste'''
    },
    {
        "instruction": r'''Should I store my dApp user preferences in posting_json_metadata on their profile, or in custom_json operations? What are the tradeoffs?''',
        "output": r'''<think>
This is an interesting architectural question. Let me think about what each option means.

posting_json_metadata is a field on the account object itself. You update it with account_update2 operation. It persists as the "current state" on the account. Anyone can read it with a single API call to get the account. But it requires the posting key and each update overwrites the entire field.

custom_json operations are individual transactions in blocks. They form an append-only log. To get the "current" preferences, an indexer has to replay all custom_json ops for that user and compute the final state. But they are cheaper in terms of RC and more flexible.

Hmm, wait actually -- account_update2 for posting_json_metadata uses the posting key, same as custom_json. So key requirements are the same. But the RC cost differs. Account updates are more expensive in RC than custom_json operations.

I initially thought posting_json_metadata would be simpler because it is "just there" on the account, but there is a size limit. The json_metadata fields have a combined limit, and if the user's profile data (avatar, bio, etc.) is already large, adding app preferences could push it over.

Could be a hybrid approach too -- use posting_json_metadata for critical display preferences (theme, language) that need to be available instantly, and custom_json for detailed settings that your app indexes separately.

The tradeoff is: posting_json_metadata = instant reads, higher RC cost, size limits, overwrites. custom_json = needs indexer, cheaper RC, unlimited history, append-only.
</think>

Both approaches work, but they serve different access patterns. Here is a comparison and a hybrid solution:

```python
from beem import Hive
from beem.account import Account
from beembase.operations import Account_update2, Custom_json
from beem.transactionbuilder import TransactionBuilder
import json

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)

# =========================================
# OPTION A: posting_json_metadata
# Pros: Instant reads via condenser_api, no indexer needed
# Cons: Higher RC, overwrites entire field, size limit
# =========================================

def set_profile_preferences(account, preferences):
    """Store preferences in posting_json_metadata.

    WARNING: This overwrites the entire posting_json_metadata field.
    Must merge with existing data first.
    """
    acc = Account(account, blockchain_instance=hive)
    existing = json.loads(acc.get("posting_json_metadata", "{}") or "{}")

    # Merge under an app-specific namespace to avoid conflicts
    if "myapp" not in existing:
        existing["myapp"] = {}
    existing["myapp"]["prefs"] = preferences

    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Account_update2(**{
        "account": account,
        "json_metadata": "",  # leave unchanged
        "posting_json_metadata": json.dumps(existing),
        "extensions": []
    }))
    tx.appendSigner(account, "posting")
    tx.sign()
    return tx.broadcast()


def get_profile_preferences(account):
    """Read preferences -- no indexer needed."""
    acc = Account(account, blockchain_instance=hive)
    meta = json.loads(acc.get("posting_json_metadata", "{}") or "{}")
    return meta.get("myapp", {}).get("prefs", {})


# =========================================
# OPTION B: custom_json
# Pros: Cheaper RC, append-only history, no size worries
# Cons: Requires an indexer to compute current state
# =========================================

def set_preferences_custom_json(account, preferences):
    """Store preferences as custom_json -- needs indexer to read."""
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [account],
        "id": "myapp_prefs",
        "json": json.dumps({
            "action": "set",
            "prefs": preferences
        }, separators=(",", ":"))
    }))
    tx.appendSigner(account, "posting")
    tx.sign()
    return tx.broadcast()


# =========================================
# RECOMMENDED: Hybrid approach
# Core display prefs in profile metadata (instant reads)
# Detailed settings in custom_json (cheap, historical)
# =========================================

def update_user_settings(account, display_prefs=None, app_settings=None):
    """Hybrid: display prefs in profile, detailed settings in custom_json."""
    results = {}

    if display_prefs:
        # Theme, language, avatar frame -- things other apps might read
        results["profile"] = set_profile_preferences(account, display_prefs)

    if app_settings:
        # Notification filters, keybindings, detailed configs
        results["settings"] = set_preferences_custom_json(
            account, app_settings)

    return results


# Usage
update_user_settings(
    "myuser",
    display_prefs={"theme": "dark", "lang": "en"},
    app_settings={
        "notifications": {"votes": True, "replies": True, "transfers": False},
        "editor": {"preview": "split", "font_size": 14}
    }
)
```

Decision matrix:
- Few settings, need instant reads, no indexer: use posting_json_metadata
- Many settings, have an indexer, want history: use custom_json
- Both: put display-critical prefs in profile, everything else in custom_json'''
    },
    {
        "instruction": r'''My Hive dApp has been running for a year with custom_json v1 schema. I need to add new fields and rename some existing ones. How do I handle schema versioning without breaking existing data?''',
        "output": r'''<think>
Schema versioning on an immutable blockchain -- this is tricky because you cannot go back and update old operations. The old v1 data is on-chain forever. So the indexer needs to handle both v1 and v2 (and eventually v3, v4...) formats.

Let me think about the approaches. One option is to include a version field in every payload and have the indexer transform old formats to the current internal representation. Another is to use a separate custom_json id for v2 operations, like "myapp_v2" instead of "myapp".

Hmm, using separate ids is tempting because the indexer can just subscribe to the new id going forward. But wait, if you want historical data, you still need to parse v1 operations. And having multiple ids makes the system harder to reason about over time.

I initially thought renaming fields would require a migration operation, but actually since the blockchain is append-only, you just start using new field names in new operations. The indexer maps old names to new internal names during ingestion.

The tradeoff is complexity in the indexer vs complexity in the schema. I think a version field in the payload plus a migration layer in the indexer is the cleanest approach. Each version bump gets a migration function that normalizes old data to the latest format.

Actually, could also consider a "schema declaration" custom_json that announces the new schema on-chain, so third-party indexers know what changed. That is nice for ecosystem interop.
</think>

Use a version field in payloads and a migration pipeline in your indexer. Old data stays on-chain as-is; the indexer normalizes everything to the latest format during ingestion:

```python
import json
from copy import deepcopy

# === Schema Evolution Strategy ===

# V1 (original, year-old data on chain):
# {"type": "post_reaction", "post_id": "@user/slug", "reaction": "like"}

# V2 (new requirements):
# - Renamed "post_id" to "ref" (shorter, more general)
# - Added "intensity" field (1-5 scale)
# - Added "context" for where the reaction happened
# V2: {"v": 2, "type": "reaction", "ref": "@user/slug",
#       "reaction": "like", "intensity": 3, "ctx": "feed"}

CURRENT_VERSION = 2

# === Migration Functions ===

def migrate_v1_to_v2(data):
    """Transform v1 payload to v2 format."""
    migrated = {
        "v": 2,
        "type": data.get("type", "").replace("post_", ""),
        "ref": data.get("post_id", ""),
        "reaction": data.get("reaction", ""),
        "intensity": 3,  # default for old data
        "ctx": "unknown"  # old data has no context
    }
    return migrated


MIGRATIONS = {
    (1, 2): migrate_v1_to_v2,
    # Future: (2, 3): migrate_v2_to_v3,
}


def normalize_payload(raw_json_str):
    """Parse any version of payload and return current-version dict."""
    data = json.loads(raw_json_str)

    # Detect version: v1 had no version field
    version = data.get("v", 1)

    # Apply migrations sequentially
    while version < CURRENT_VERSION:
        next_version = version + 1
        migration_key = (version, next_version)
        if migration_key not in MIGRATIONS:
            raise ValueError(
                f"No migration path from v{version} to v{next_version}"
            )
        data = MIGRATIONS[migration_key](deepcopy(data))
        version = next_version

    return data


# === Broadcasting New Operations ===

from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)

APP_ID = "myapp"  # same id for all versions


def broadcast_reaction(account, post_ref, reaction, intensity=3, context="app"):
    """Broadcast a v2 reaction."""
    payload = {
        "v": CURRENT_VERSION,
        "type": "reaction",
        "ref": post_ref,
        "reaction": reaction,
        "intensity": intensity,
        "ctx": context
    }

    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [account],
        "id": APP_ID,
        "json": json.dumps(payload, separators=(",", ":"))
    }))
    tx.appendSigner(account, "posting")
    tx.sign()
    return tx.broadcast()


# === Indexer Integration ===

class SchemaAwareIndexer:
    """Index custom_json ops with automatic schema migration."""

    def __init__(self):
        self.reactions = {}  # ref -> [reactions]

    def process_operation(self, op):
        """Called for each custom_json with id='myapp'."""
        if op["id"] != APP_ID:
            return

        try:
            normalized = normalize_payload(op["json"])
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Skipping malformed op: {e}")
            return

        op_type = normalized.get("type")
        if op_type == "reaction":
            self._index_reaction(normalized, op)

    def _index_reaction(self, data, raw_op):
        ref = data["ref"]
        if ref not in self.reactions:
            self.reactions[ref] = []
        self.reactions[ref].append({
            "user": raw_op["required_posting_auths"][0],
            "reaction": data["reaction"],
            "intensity": data["intensity"],
            "context": data["ctx"],
            "block": raw_op.get("block_num")
        })


# === Optional: Announce Schema On-Chain ===

def announce_schema_version(admin_account, version, changelog):
    """Publish schema change notice for third-party indexers."""
    payload = {
        "v": version,
        "type": "_schema",
        "changelog": changelog,
        "fields": {
            "reaction": {
                "v": "int, schema version",
                "type": "str, operation type",
                "ref": "str, content reference (@author/permlink)",
                "reaction": "str, reaction type",
                "intensity": "int 1-5, reaction strength",
                "ctx": "str, UI context where reaction occurred"
            }
        }
    }
    return broadcast_reaction.__wrapped__(admin_account, payload)
```

Key principles: same custom_json id across versions (keeps indexing simple), version field in every payload (v1 assumed when missing), sequential migration functions (composable and testable), normalize on read (old data is never modified on-chain).'''
    },
    {
        "instruction": r'''I want to store structured data on Hive for a supply chain tracking app. Each item has a lot of metadata -- sometimes over 8KB. How do I handle the custom_json size limit?''',
        "output": r'''<think>
The custom_json payload limit is 8192 bytes. For supply chain data with lots of metadata (origin, certifications, inspection reports, GPS coordinates, photos hashes, etc.), that could easily exceed 8KB.

Let me think about the options. First option: split the data across multiple custom_json operations. Link them with a common identifier. The indexer reassembles them. But this is fragile -- what if one of the chunks fails to broadcast? You get incomplete data.

Second option: store a hash/reference on-chain and put the full data off-chain (IPFS, Arweave, or a regular database). The blockchain provides the immutable audit trail, and the off-chain storage has the full details. This is actually how most real dApps work.

Third option: use a post/comment instead of custom_json. Posts can hold much more data in the body field. But posts are meant for content, not structured data. They also have different economic implications (rewards, curation).

Hmm, wait -- actually, could I use comment operations with an empty parent (a root post) in a dedicated community, with the body containing my structured data as JSON? The body field can be up to 64KB. But that feels like an abuse of the content system.

I initially thought IPFS would be the obvious answer, but it adds infrastructure complexity and a dependency. For a supply chain app where data integrity is critical, having the hash on-chain and data on IPFS is actually a great pattern -- the hash proves the data has not been tampered with.

The tradeoff is: on-chain only (multiple custom_json) = more RC cost, complex reassembly, but fully decentralized. Hybrid (hash on-chain + IPFS) = single cheap custom_json, needs IPFS infrastructure, but data integrity is still provable via hash.
</think>

For data exceeding 8KB, use a hybrid approach: store a content hash on-chain via custom_json and the full payload on IPFS. The blockchain provides the tamper-proof audit trail:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json
import hashlib
import requests

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)

APP_ID = "supplychain"

# === IPFS Integration ===

IPFS_API = "http://localhost:5001/api/v0"  # local IPFS node
# Or use a pinning service: Pinata, Web3.Storage, etc.


def pin_to_ipfs(data_dict):
    """Upload JSON data to IPFS and return the CID."""
    json_bytes = json.dumps(data_dict, sort_keys=True).encode("utf-8")
    resp = requests.post(
        f"{IPFS_API}/add",
        files={"file": ("data.json", json_bytes)}
    )
    resp.raise_for_status()
    return resp.json()["Hash"]  # IPFS CID


def fetch_from_ipfs(cid):
    """Retrieve data from IPFS by CID."""
    resp = requests.post(f"{IPFS_API}/cat?arg={cid}")
    resp.raise_for_status()
    return json.loads(resp.text)


# === On-Chain Anchoring ===

def compute_hash(data_dict):
    """Deterministic SHA-256 hash of JSON data."""
    canonical = json.dumps(data_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_supply_chain_event(account, item_id, event_type, full_data):
    """Record a supply chain event with on-chain hash and off-chain data.

    full_data can be any size -- only the hash goes on-chain.
    """
    # Step 1: Pin full data to IPFS
    ipfs_cid = pin_to_ipfs(full_data)

    # Step 2: Compute verification hash
    data_hash = compute_hash(full_data)

    # Step 3: Anchor on Hive (small payload, well under 8KB)
    on_chain_record = {
        "v": 1,
        "type": event_type,
        "item": item_id,
        "hash": data_hash,
        "ipfs": ipfs_cid,
        # Include critical fields directly for quick queries
        "loc": full_data.get("location", {}).get("code", ""),
        "ts": full_data.get("timestamp", ""),
        "status": full_data.get("status", "")
    }

    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [account],
        "id": APP_ID,
        "json": json.dumps(on_chain_record, separators=(",", ":"))
    }))
    tx.appendSigner(account, "posting")
    tx.sign()
    result = tx.broadcast()

    return {
        "tx_id": result["id"],
        "ipfs_cid": ipfs_cid,
        "data_hash": data_hash
    }


def verify_supply_chain_data(on_chain_record, off_chain_data):
    """Verify off-chain data matches on-chain hash."""
    expected_hash = on_chain_record["hash"]
    actual_hash = compute_hash(off_chain_data)
    return expected_hash == actual_hash


# === Usage Example ===

large_inspection_data = {
    "item_id": "BATCH-2024-0042",
    "timestamp": "2024-03-15T10:30:00Z",
    "status": "inspected",
    "location": {
        "code": "PORT-LAX",
        "name": "Port of Los Angeles",
        "gps": {"lat": 33.7395, "lon": -118.2601}
    },
    "inspector": "cert-agency-xyz",
    "certifications": ["ISO-9001", "HACCP", "FDA-APPROVED"],
    "measurements": [
        {"param": "temperature", "value": 4.2, "unit": "celsius"},
        {"param": "humidity", "value": 65, "unit": "percent"},
        # ... potentially hundreds of measurements
    ],
    "photo_hashes": [
        "sha256:abc123...",
        "sha256:def456..."
    ],
    "documents": [
        {"type": "bill_of_lading", "hash": "sha256:..."},
        {"type": "customs_declaration", "hash": "sha256:..."}
    ]
}

result = record_supply_chain_event(
    account="supplychain-tracker",
    item_id="BATCH-2024-0042",
    event_type="inspection",
    full_data=large_inspection_data
)
print(f"Anchored on Hive: {result['tx_id']}")
print(f"Full data on IPFS: {result['ipfs_cid']}")
```

This pattern gives you: immutable audit trail on Hive (tamper-proof), unlimited data size via IPFS, verifiable integrity via hash comparison, and key fields duplicated on-chain for quick indexer queries without fetching IPFS.'''
    },
    {
        "instruction": r'''For my Hive app custom_json operations, should I use required_auths (active key) or required_posting_auths (posting key)? When would I choose one over the other?''',
        "output": r'''<think>
This is about key hierarchy on Hive. Let me think about what each authority level means and when you would want one vs the other.

The posting key is meant for social actions -- voting, posting, commenting, and custom_json with required_posting_auths. The active key is for financial operations -- transfers, power ups, and custom_json with required_auths.

So the question is: does my custom_json operation have financial implications? If my app is a game where custom_json triggers token transfers on Hive Engine, then hmm... actually the custom_json itself does not transfer tokens. The sidechain (Hive Engine) interprets the custom_json and does the transfer on the L2. So the Hive layer 1 operation is "just" a custom_json.

Wait, but there is a security consideration. If someone compromises a posting key, they can broadcast custom_json with required_posting_auths. If your app interprets those operations as "transfer 1000 tokens to account X" on a sidechain, then a posting key compromise leads to financial loss on the sidechain.

I initially thought posting key was always fine for custom_json since it is just data, but the SEMANTIC meaning matters. If the data triggers financial actions on an indexer or L2, you should require the active key to match the security expectations.

The tradeoff is usability vs security. Posting key is more convenient (users share it more freely, apps request it more readily). Active key requires more trust from users. For social features, posting key is appropriate. For anything with financial implications, even on L2, active key is the responsible choice.

Actually, Splinterlands uses posting key for gameplay but active key for market transactions. That is a good model -- split by financial impact.
</think>

The choice depends on whether the operation has financial implications, even on Layer 2. Here is a guide with examples:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json

# === POSTING KEY: Social / non-financial actions ===
# Users share posting keys more freely with apps
# Lower security risk if compromised

hive_posting = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourPostingKey"]
)


def social_action_example(account, action_data):
    """Follow, reblog, vote preferences -- use posting key."""
    tx = TransactionBuilder(blockchain_instance=hive_posting)
    tx.appendOps(Custom_json(**{
        "required_auths": [],                    # empty
        "required_posting_auths": [account],     # posting key signs
        "id": "myapp_social",
        "json": json.dumps(action_data, separators=(",", ":"))
    }))
    tx.appendSigner(account, "posting")
    tx.sign()
    return tx.broadcast()


# Good uses for posting key:
# - Game moves, chat messages, profile updates
# - Content curation signals, bookmarks
# - Community membership, subscriptions
# - Any action where compromise = annoyance, not financial loss


# === ACTIVE KEY: Financial / high-security actions ===
# Users are cautious about sharing active keys
# Required when the custom_json triggers value transfer

hive_active = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourActiveKey"]
)


def financial_action_example(account, action_data):
    """Token transfers, market orders -- use active key."""
    tx = TransactionBuilder(blockchain_instance=hive_active)
    tx.appendOps(Custom_json(**{
        "required_auths": [account],             # active key signs
        "required_posting_auths": [],            # empty
        "id": "myapp_market",
        "json": json.dumps(action_data, separators=(",", ":"))
    }))
    tx.appendSigner(account, "active")
    tx.sign()
    return tx.broadcast()


# Good uses for active key:
# - Hive Engine token transfers, market orders
# - NFT purchases, auctions
# - Escrow operations, DeFi interactions
# - Any action where compromise = financial loss


# === HYBRID APP: Split by operation type ===

class HiveApp:
    """App that uses both key levels appropriately."""

    def __init__(self, account, posting_key=None, active_key=None):
        self.account = account
        self.hive_posting = None
        self.hive_active = None

        if posting_key:
            self.hive_posting = Hive(
                node=["https://api.hive.blog"],
                keys=[posting_key]
            )
        if active_key:
            self.hive_active = Hive(
                node=["https://api.hive.blog"],
                keys=[active_key]
            )

    def _broadcast(self, op_id, data, use_active=False):
        if use_active:
            if not self.hive_active:
                raise ValueError("Active key not provided")
            inst = self.hive_active
            auths = {"required_auths": [self.account],
                     "required_posting_auths": []}
            role = "active"
        else:
            if not self.hive_posting:
                raise ValueError("Posting key not provided")
            inst = self.hive_posting
            auths = {"required_auths": [],
                     "required_posting_auths": [self.account]}
            role = "posting"

        tx = TransactionBuilder(blockchain_instance=inst)
        tx.appendOps(Custom_json(**{
            **auths,
            "id": op_id,
            "json": json.dumps(data, separators=(",", ":"))
        }))
        tx.appendSigner(self.account, role)
        tx.sign()
        return tx.broadcast()

    # Social features -- posting key
    def play_card(self, card_id, target):
        return self._broadcast("myapp_game", {
            "action": "play", "card": card_id, "target": target
        }, use_active=False)

    # Financial features -- active key
    def buy_card(self, listing_id, price):
        return self._broadcast("myapp_market", {
            "action": "buy", "listing": listing_id, "price": price
        }, use_active=True)

    def sell_card(self, card_id, price):
        return self._broadcast("myapp_market", {
            "action": "sell", "card": card_id, "price": price
        }, use_active=True)
```

Rule of thumb: if a compromised key could cause financial loss (even on Layer 2 / Hive Engine), require the active key. For everything else, posting key provides better UX since users grant it more willingly.'''
    },
]
