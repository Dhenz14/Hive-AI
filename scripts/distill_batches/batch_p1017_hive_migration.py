"""
Hive blockchain migration training pairs: Steem to Hive differences,
porting dApps, API compatibility, community migration patterns, data migration.
"""

PAIRS = [
    (
        "hive-migration-steem-differences",
        r'''What are the key technical differences between Steem and Hive blockchain that developers need to know when migrating?''',
        r'''<think>
Hive forked from Steem at block 41818752 on March 20, 2020. Since then, Hive has diverged significantly with multiple hard forks adding new features and changing parameters. Key differences include: governance changes (removing the ninja-mined stake), faster power down (changed in HF28), HBD interest rate (20% vs Steem's 0%), Resource Credits improvements, API endpoint differences, and new features like recurring transfers, community improvements, and HAF. I need to be comprehensive about the technical delta.
</think>

Hive forked from Steem at block 41818752 (March 20, 2020). Since then, significant technical divergence has occurred across multiple hard forks. Here is a comprehensive comparison for developers:

```python
"""
Steem vs Hive Technical Differences Reference
Updated for Hive HF28 and later
"""

CHAIN_DIFFERENCES = {
    "consensus": {
        "steem": "DPoS with 21 witnesses, ninja-mined stake voting power intact",
        "hive": "DPoS with 21 witnesses, ninja-mined stake excluded from governance",
        "note": "Hive removed Steemit Inc's stake from witness voting and DHF"
    },
    "power_down": {
        "steem": "13 weeks (91 days), 13 equal installments",
        "hive": "3 days since HF28 (previously 13 weeks)",
        "migration_impact": "Significantly faster liquidity on Hive"
    },
    "hbd_interest": {
        "steem": "SBD interest typically 0%, set by witnesses",
        "hive": "HBD interest currently 20% APR, paid on savings balance",
        "note": "HBD renamed from SBD; interest applies only to savings"
    },
    "api_nodes": {
        "steem": ["https://api.steemit.com", "https://api.justyy.com"],
        "hive": ["https://api.hive.blog", "https://api.deathwing.me",
                 "https://rpc.ausbit.dev", "https://api.openhive.network"],
    },
    "token_names": {
        "steem": {"native": "STEEM", "dollar": "SBD", "vesting": "VESTS"},
        "hive": {"native": "HIVE", "dollar": "HBD", "vesting": "VESTS"},
        "code_change": "Replace all STEEM/SBD string references with HIVE/HBD"
    },
    "recurring_transfers": {
        "steem": "Not supported",
        "hive": "Supported since HF25 - recurring_transfer operation",
    },
    "account_creation": {
        "steem": "create_claimed_account + claim_account",
        "hive": "Same operations, plus improved RC-based account creation",
    },
    "communities": {
        "steem": "Basic community support via Hivemind",
        "hive": "Enhanced communities with roles, moderation, muting"
    },
    "dhf_proposals": {
        "steem": "SPS (Steem Proposal System)",
        "hive": "DHF (Decentralized Hive Fund) - same mechanism, different name",
        "code_change": "Proposal operations are identical, just different chain"
    },
    "libraries": {
        "steem_python": "steem-python (deprecated), beem (supports both)",
        "hive_python": "beem (primary), lighthive (lightweight)",
        "steem_js": "steem-js, dsteem",
        "hive_js": "@hiveio/dhive (fork of dsteem), @hiveio/hive-js",
        "note": "beem supports both chains via node selection"
    },
    "custom_json_ids": {
        "steem": "follow, reblog, community, ssc-mainnet1 (steem-engine)",
        "hive": "follow, reblog, community, ssc-mainnet-hive (hive-engine)",
        "code_change": "Sidechain custom_json id changed"
    },
    "haf_framework": {
        "steem": "Not available",
        "hive": "HAF (Hive Application Framework) - PostgreSQL-based app framework"
    },
}

def generate_migration_checklist():
    """Generate a migration checklist for porting a dApp from Steem to Hive."""
    checklist = [
        "1. Update API node URLs from Steem endpoints to Hive endpoints",
        "2. Replace all 'STEEM' token references with 'HIVE'",
        "3. Replace all 'SBD' token references with 'HBD'",
        "4. Update library imports: steem-js -> @hiveio/dhive",
        "5. Update library imports: steem-python -> beem (with hive nodes)",
        "6. Change chain_id if using low-level signing",
        "7. Update sidechain custom_json id: ssc-mainnet1 -> ssc-mainnet-hive",
        "8. Update block explorer links: steemit.com -> peakd.com or hive.blog",
        "9. Update power-down period assumptions (3 days, not 13 weeks)",
        "10. Add HBD savings interest features (not available on Steem)",
        "11. Update Hivemind/bridge API calls for enhanced community features",
        "12. Test recurring_transfer if applicable (Hive-only feature)",
        "13. Update account history API calls (same format, different nodes)",
        "14. Verify witness/proposal voting code (same ops, different chain)",
        "15. Update any hardcoded chain_id for transaction signing",
    ]
    return checklist

# Chain IDs for transaction signing
CHAIN_IDS = {
    "steem_mainnet": "0000000000000000000000000000000000000000000000000000000000000000",
    "hive_mainnet": "beeab0de00000000000000000000000000000000000000000000000000000000",
}

def print_migration_guide():
    print("=" * 60)
    print("STEEM TO HIVE MIGRATION GUIDE")
    print("=" * 60)
    for category, details in CHAIN_DIFFERENCES.items():
        print(f"\n--- {category.upper()} ---")
        if isinstance(details, dict):
            for key, value in details.items():
                if key in ("steem", "hive", "note", "code_change", "migration_impact"):
                    print(f"  {key}: {value}")
    print("\n--- MIGRATION CHECKLIST ---")
    for item in generate_migration_checklist():
        print(f"  {item}")

print_migration_guide()
```

The most critical code changes when migrating are: (1) API node URLs, (2) token name strings (STEEM->HIVE, SBD->HBD), (3) JavaScript library swap from steem-js to dhive, (4) chain_id for low-level transaction signing, and (5) sidechain custom_json identifiers. The beem Python library supports both chains through node configuration, making Python migrations simpler. On the feature side, Hive's 3-day power down (vs 13 weeks), 20% HBD savings interest, and HAF framework are major additions that have no Steem equivalent.'''
    ),
    (
        "hive-migration-porting-dapps",
        r'''Show me a practical example of porting a Steem dApp to Hive, including code changes for both the backend and frontend.''',
        r'''Porting a dApp from Steem to Hive requires changes at multiple layers. Here is a practical before/after showing the key modifications for a typical social dApp:

```javascript
// ============================================================
// BEFORE: Steem dApp (steem-js based)
// ============================================================
// const steem = require("steem");
// steem.api.setOptions({ url: "https://api.steemit.com" });
//
// async function getPost(author, permlink) {
//     return new Promise((resolve, reject) => {
//         steem.api.getContent(author, permlink, (err, result) => {
//             if (err) reject(err);
//             else resolve(result);
//         });
//     });
// }
//
// async function vote(voter, wif, author, permlink, weight) {
//     return new Promise((resolve, reject) => {
//         steem.broadcast.vote(wif, voter, author, permlink, weight,
//             (err, result) => {
//                 if (err) reject(err);
//                 else resolve(result);
//             });
//     });
// }
//
// async function transfer(from, wif, to, amount, memo) {
//     // amount format: "1.000 STEEM" or "1.000 SBD"
//     return new Promise((resolve, reject) => {
//         steem.broadcast.transfer(wif, from, to, amount, memo,
//             (err, result) => {
//                 if (err) reject(err);
//                 else resolve(result);
//             });
//     });
// }

// ============================================================
// AFTER: Hive dApp (dhive based)
// ============================================================
const { Client, PrivateKey } = require("@hiveio/dhive");

// Multiple nodes for redundancy
const client = new Client([
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://rpc.ausbit.dev"
]);

async function getPost(author, permlink) {
    // dhive uses promises natively (no callback wrapping needed)
    return client.database.call("get_content", [author, permlink]);
}

// Alternative: use bridge API for richer post data
async function getPostBridge(author, permlink) {
    return client.call("bridge", "get_post", { author, permlink });
}

async function vote(voter, postingKey, author, permlink, weight) {
    const key = PrivateKey.fromString(postingKey);
    return client.broadcast.vote(
        { voter, author, permlink, weight },
        key
    );
}

async function transfer(from, activeKey, to, amount, asset, memo) {
    // Note: asset is "HIVE" or "HBD" (not "STEEM" or "SBD")
    const key = PrivateKey.fromString(activeKey);
    return client.broadcast.transfer(
        { from, to, amount: `${amount.toFixed(3)} ${asset}`, memo },
        key
    );
}

async function post(author, postingKey, title, body, tags, beneficiaries = []) {
    const key = PrivateKey.fromString(postingKey);
    const permlink = title.toLowerCase().replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "");
    const jsonMetadata = JSON.stringify({
        tags: tags,
        app: "myapp/1.0",  // Identify your dApp
        format: "markdown"
    });
    const operations = [
        ["comment", {
            parent_author: "",
            parent_permlink: tags[0] || "general",
            author: author,
            permlink: permlink,
            title: title,
            body: body,
            json_metadata: jsonMetadata
        }]
    ];
    if (beneficiaries.length > 0) {
        operations.push(["comment_options", {
            author: author,
            permlink: permlink,
            max_accepted_payout: "1000000.000 HBD",  // Changed from SBD
            percent_hbd: 10000,  // Changed from percent_steem_dollars
            allow_votes: true,
            allow_curation_rewards: true,
            extensions: [[0, {
                beneficiaries: beneficiaries.sort((a, b) =>
                    a.account.localeCompare(b.account))
            }]]
        }]);
    }
    return client.broadcast.sendOperations(operations, key);
}

// ============================================================
// Frontend changes (React example)
// ============================================================

// BEFORE (Steem):
// const EXPLORER_URL = "https://steemit.com";
// const IMAGE_PROXY = "https://steemitimages.com";
// const CHAIN_PREFIX = "STM";

// AFTER (Hive):
const EXPLORER_URL = "https://peakd.com";
const IMAGE_PROXY = "https://images.hive.blog";
const CHAIN_PREFIX = "STM";  // Note: Hive still uses STM prefix for keys

function buildPostUrl(author, permlink) {
    return `${EXPLORER_URL}/@${author}/${permlink}`;
}

function buildProfileUrl(username) {
    return `${EXPLORER_URL}/@${username}`;
}

function formatCurrency(amount, asset) {
    // STEEM -> HIVE, SBD -> HBD
    const assetMap = { "STEEM": "HIVE", "SBD": "HBD" };
    const displayAsset = assetMap[asset] || asset;
    return `${parseFloat(amount).toFixed(3)} ${displayAsset}`;
}

// Hive Keychain integration (replaces SteemKeychain)
function loginWithKeychain(username) {
    return new Promise((resolve, reject) => {
        if (!window.hive_keychain) {
            reject(new Error("Hive Keychain not installed"));
            return;
        }
        const memo = `login-${Date.now()}`;
        window.hive_keychain.requestSignBuffer(
            username, memo, "Posting",
            (response) => {
                if (response.success) {
                    resolve({
                        username: username,
                        publicKey: response.publicKey,
                        signature: response.result
                    });
                } else {
                    reject(new Error(response.message));
                }
            }
        );
    });
}

// ============================================================
// Backend Python changes (beem)
// ============================================================

// BEFORE:
// from steem import Steem
// s = Steem(nodes=["https://api.steemit.com"])
// s.commit.transfer("sender", 1.0, "STEEM", "memo", "receiver")

// AFTER:
// from beem import Hive
// h = Hive(node=["https://api.hive.blog"], keys=["5Kactive"])
// h.transfer("receiver", 1.0, "HIVE", "memo", account="sender")

module.exports = {
    getPost, getPostBridge, vote, transfer, post,
    buildPostUrl, buildProfileUrl, formatCurrency, loginWithKeychain
};
```

Key migration patterns: (1) steem-js callback style becomes dhive promise style. (2) All `STEEM` and `SBD` strings become `HIVE` and `HBD`. (3) `percent_steem_dollars` in comment_options becomes `percent_hbd`. (4) SteemKeychain becomes Hive Keychain (`window.hive_keychain`). (5) Image proxy changes from steemitimages.com to images.hive.blog. (6) Explorer links change to peakd.com or hive.blog. (7) The key prefix remains `STM` on both chains. (8) beem Python library works on both chains just by changing the node URL. For a smooth migration, create an abstraction layer with chain-specific constants so switching is a configuration change rather than code surgery.'''
    ),
    (
        "hive-migration-api-compatibility",
        r'''What API compatibility issues should I expect when migrating from Steem to Hive, and how do I handle the differences?''',
        r'''Most Steem APIs work identically on Hive since they share the same codebase origin. However, there are important differences in available APIs, response formats for newer features, and some deprecated endpoints. Here is a compatibility reference:

```python
"""
Hive vs Steem API Compatibility Matrix
Covers condenser_api, database_api, block_api, and bridge API
"""
import requests
import json

# API compatibility status
API_COMPATIBILITY = {
    "condenser_api": {
        "fully_compatible": [
            "get_content",
            "get_content_replies",
            "get_accounts",
            "get_block",
            "get_dynamic_global_properties",
            "get_chain_properties",
            "get_feed_history",
            "get_current_median_history_price",
            "get_witness_by_account",
            "get_witnesses_by_vote",
            "get_account_history",
            "get_active_witnesses",
            "get_block_header",
            "get_ops_in_block",
            "get_transaction",
            "get_config",
            "get_version",
            "broadcast_transaction",
            "broadcast_transaction_synchronous",
        ],
        "response_differs": {
            "get_accounts": "Hive includes rc_accounts data, different vesting fields",
            "get_dynamic_global_properties": "Hive has hbd_interest_rate, different field names",
            "get_config": "Chain-specific config values differ significantly",
        },
        "hive_only": [
            "find_rc_accounts",
            "list_rc_accounts",
            "find_recurrent_transfers",
        ],
        "deprecated_on_hive": [
            "get_trending_tags",  # Use bridge API instead
            "get_discussions_by_trending",  # Use bridge.get_ranked_posts
        ],
    },
    "database_api": {
        "status": "Fully available on Hive, same method signatures",
        "note": "database_api uses find_* and list_* methods with JSON params"
    },
    "block_api": {
        "status": "Fully compatible",
        "methods": ["get_block", "get_block_header", "get_block_range"]
    },
    "rc_api": {
        "status": "Hive has enhanced RC API",
        "hive_methods": [
            "find_rc_accounts",
            "get_resource_params",
            "get_resource_pool",
        ],
        "note": "Steem has basic RC; Hive RC API is more comprehensive"
    },
    "bridge": {
        "status": "Hive Hivemind bridge is more feature-rich",
        "hive_exclusive": [
            "get_community",
            "list_communities",
            "get_community_context",
            "list_subscribers",
            "account_notifications",
        ],
        "shared": [
            "get_post",
            "get_ranked_posts",
            "get_account_posts",
            "get_discussion",
            "get_profile",
        ]
    },
}

class APICompatibilityChecker:
    def __init__(self):
        self.hive_node = "https://api.hive.blog"

    def call_api(self, node, method, params=None):
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or [],
            "id": 1
        }
        try:
            resp = requests.post(node, json=payload, timeout=15)
            data = resp.json()
            if "error" in data:
                return {"available": False, "error": data["error"]["message"]}
            return {"available": True, "result_keys": list(data.get("result", {}).keys())
                    if isinstance(data.get("result"), dict) else "array_or_scalar"}
        except Exception as e:
            return {"available": False, "error": str(e)}

    def check_hive_api_availability(self, methods):
        """Test which API methods are available on the Hive node."""
        results = {}
        for method in methods:
            # Most condenser_api methods accept empty array params for testing
            result = self.call_api(self.hive_node, method, [])
            results[method] = result
            status = "OK" if result["available"] else "FAIL"
            print(f"  {status}: {method}")
        return results

    def compare_response_format(self, method, params):
        """Compare response format between Steem and Hive for same call."""
        hive_result = self.call_api(self.hive_node, method, params)
        return {
            "method": method,
            "hive": hive_result,
        }

    def test_field_name_differences(self):
        """Check for renamed fields in common API responses."""
        # get_dynamic_global_properties has renamed fields
        result = self.call_api(
            self.hive_node,
            "condenser_api.get_dynamic_global_properties",
            []
        )
        if result["available"]:
            field_mapping = {
                "sbd_interest_rate": "hbd_interest_rate (Hive)",
                "sbd_print_rate": "hbd_print_rate (Hive)",
                "total_reward_fund_steem": "total_reward_fund_hive (Hive)",
                "current_sbd_supply": "current_hbd_supply (Hive)",
                "sbd_supply": "hbd_supply (Hive)",
            }
            print("\nField name changes in get_dynamic_global_properties:")
            for steem_field, hive_field in field_mapping.items():
                print(f"  Steem: {steem_field}")
                print(f"  Hive:  {hive_field}")
                print()

def build_api_adapter():
    """
    Build an adapter that normalizes API responses between
    Steem and Hive format for gradual migration.
    """
    class ChainAPIAdapter:
        def __init__(self, node_url, chain="hive"):
            self.node = node_url
            self.chain = chain

        def call(self, method, params=None):
            payload = {
                "jsonrpc": "2.0", "method": method,
                "params": params or [], "id": 1
            }
            resp = requests.post(self.node, json=payload, timeout=15)
            return resp.json().get("result")

        def get_global_props(self):
            raw = self.call("condenser_api.get_dynamic_global_properties")
            # Normalize field names regardless of chain
            normalized = dict(raw)
            if self.chain == "hive":
                # Map Hive field names to generic names
                normalized["dollar_interest_rate"] = raw.get("hbd_interest_rate", 0)
                normalized["dollar_print_rate"] = raw.get("hbd_print_rate", 10000)
                normalized["dollar_supply"] = raw.get("current_hbd_supply", "0 HBD")
                normalized["native_token"] = "HIVE"
                normalized["dollar_token"] = "HBD"
            else:
                normalized["dollar_interest_rate"] = raw.get("sbd_interest_rate", 0)
                normalized["dollar_print_rate"] = raw.get("sbd_print_rate", 10000)
                normalized["dollar_supply"] = raw.get("current_sbd_supply", "0 SBD")
                normalized["native_token"] = "STEEM"
                normalized["dollar_token"] = "SBD"
            return normalized

        def get_account(self, username):
            accounts = self.call("condenser_api.get_accounts", [[username]])
            if not accounts:
                return None
            acct = accounts[0]
            # Normalize balance field names
            if self.chain == "hive":
                acct["native_balance"] = acct.get("balance", "0.000 HIVE")
                acct["dollar_balance"] = acct.get("hbd_balance", "0.000 HBD")
            else:
                acct["native_balance"] = acct.get("balance", "0.000 STEEM")
                acct["dollar_balance"] = acct.get("sbd_balance", "0.000 SBD")
            return acct

    return ChainAPIAdapter

# Usage
checker = APICompatibilityChecker()
print("Testing Hive API endpoints:")
checker.check_hive_api_availability([
    "condenser_api.get_dynamic_global_properties",
    "condenser_api.get_accounts",
    "condenser_api.get_version",
    "rc_api.find_rc_accounts",
    "bridge.get_post",
])
checker.test_field_name_differences()

# Build adapter for cross-chain compatibility
Adapter = build_api_adapter()
hive = Adapter("https://api.hive.blog", "hive")
props = hive.get_global_props()
print(f"Chain: {props['native_token']}, Dollar rate: {props['dollar_interest_rate']}")
```

The adapter pattern shown above normalizes field names so your application code does not need chain-specific conditionals everywhere. The main API incompatibilities are: (1) renamed token fields (sbd->hbd, steem->hive), (2) Hive-only features like RC API enhancements and recurring transfers, (3) bridge API community methods only on Hive, and (4) deprecated discussion-by-* methods that should use bridge.get_ranked_posts instead. For most dApps, 90% of API calls work identically on both chains with just a node URL change.'''
    ),
    (
        "hive-migration-community-patterns",
        r'''What are the common patterns for migrating a community or project from Steem to Hive, including handling dual-chain presence?''',
        r'''Community migration involves technical, social, and content aspects. Many projects maintained dual-chain presence during transition. Here are the patterns and tooling:

```python
"""
Community/Project Migration Patterns for Steem -> Hive
Covers dual-chain posting, account mapping, and progressive migration.
"""
from beem import Hive
from beem.account import Account
import json
import time

class DualChainManager:
    """
    Manage a project's presence on both Steem and Hive
    during migration period. Supports gradual transition.
    """

    def __init__(self, account, hive_posting_key, migration_phase="dual"):
        self.account = account
        self.hive = Hive(
            keys=[hive_posting_key],
            node=["https://api.hive.blog", "https://api.deathwing.me"]
        )
        self.phase = migration_phase  # "dual", "hive_primary", "hive_only"
        self.cross_post_footer = (
            "\n\n---\n"
            "*This post was originally published on [Hive]"
            "(https://peakd.com/@{author}/{permlink}). "
            "Follow us on Hive for the latest updates.*"
        )

    def post_to_hive(self, title, body, tags, beneficiaries=None):
        """Post content to Hive blockchain."""
        permlink = title.lower().replace(" ", "-")
        permlink = "".join(c for c in permlink if c.isalnum() or c == "-")
        permlink = permlink[:200]  # Max permlink length
        metadata = json.dumps({
            "tags": tags,
            "app": "migration-tool/1.0",
            "format": "markdown",
            "canonical_chain": "hive"
        })
        self.hive.post(
            title=title,
            body=body,
            author=self.account,
            permlink=permlink,
            tags=tags,
            json_metadata=metadata,
            beneficiaries=beneficiaries or []
        )
        return permlink

    def generate_migration_announcement(self, project_name, new_hive_account=None):
        """Generate a migration announcement post."""
        hive_account = new_hive_account or self.account
        title = f"{project_name} is Moving to Hive - Migration Guide"
        body = f"""# {project_name} is Migrating to Hive

We are excited to announce that **{project_name}** is officially moving to the Hive blockchain.

## Why Hive?

- **True decentralization**: No single entity controls the chain
- **Active development**: Regular hard forks with new features
- **20% HBD savings APR**: Better economics for content creators
- **3-day power down**: Faster access to your funds
- **Thriving community**: Active developers and users

## What You Need to Do

### 1. Claim Your Hive Account
If you had a Steem account before March 20, 2020, your account and
balance were automatically included in the Hive genesis snapshot.
Visit [https://hive.blog](https://hive.blog) to access your account.

### 2. Update Your Keys
For security, generate new keys on Hive:
- Visit your wallet on [https://wallet.hive.blog](https://wallet.hive.blog)
- Go to Permissions and change your keys

### 3. Follow Us on Hive
Our official Hive account: @{hive_account}
Community: hive-{project_name.lower().replace(' ', '')}

### 4. Update Your Tools
- Replace **steem-js** with **@hiveio/dhive**
- Replace **steemit.com** links with **peakd.com**
- Install **Hive Keychain** browser extension

## Migration Timeline

| Phase | Date | Action |
|-------|------|--------|
| Phase 1 | Week 1 | Dual posting to both chains |
| Phase 2 | Week 3 | Hive becomes primary, Steem gets cross-posts |
| Phase 3 | Week 5 | Steem posting stops, redirect notices posted |
| Phase 4 | Week 7 | Full Hive-only operation |

## Support

Join our Discord for migration help: [discord link]
Hive community: [community link]

---
*{project_name} Team*
"""
        return title, body

    def create_account_mapping(self, steem_accounts):
        """
        Create a mapping of Steem accounts to their Hive equivalents.
        Most accounts have the same name on both chains from the fork snapshot.
        """
        mapping = {}
        for steem_name in steem_accounts:
            try:
                hive_account = Account(steem_name, blockchain_instance=self.hive)
                mapping[steem_name] = {
                    "hive_name": steem_name,
                    "exists": True,
                    "reputation": hive_account.get_reputation(),
                    "last_active": str(hive_account.get("last_post", "never")),
                }
            except Exception:
                mapping[steem_name] = {
                    "hive_name": steem_name,
                    "exists": False,
                    "note": "Account does not exist on Hive (created after fork)"
                }
        return mapping


class ContentMigrator:
    """Migrate historical content references and links."""

    LINK_REPLACEMENTS = {
        "steemit.com": "peakd.com",
        "busy.org": "peakd.com",
        "steempeak.com": "peakd.com",
        "steemworld.org": "hiveworld.org",
        "steemd.com": "hiveblocks.com",
        "steemdb.com": "hiveblocks.com",
    }

    TOKEN_REPLACEMENTS = {
        "STEEM": "HIVE",
        "SBD": "HBD",
        "Steem Power": "Hive Power",
        "SP": "HP",
        "Steem Dollars": "Hive Backed Dollars",
        "steemconnect": "hivesigner",
        "SteemKeychain": "Hive Keychain",
    }

    @classmethod
    def migrate_content_links(cls, markdown_text):
        """Replace Steem-specific links with Hive equivalents."""
        result = markdown_text
        for old, new in cls.LINK_REPLACEMENTS.items():
            result = result.replace(old, new)
        return result

    @classmethod
    def migrate_token_references(cls, text):
        """Replace Steem token names with Hive equivalents."""
        result = text
        for old, new in cls.TOKEN_REPLACEMENTS.items():
            result = result.replace(old, new)
        return result

    @classmethod
    def migrate_full_content(cls, markdown_text):
        """Apply all content migrations."""
        text = cls.migrate_content_links(markdown_text)
        text = cls.migrate_token_references(text)
        return text

    @classmethod
    def generate_redirect_post(cls, original_author, original_permlink, hive_url):
        """Generate a redirect post for Steem pointing to Hive."""
        return {
            "title": "[Moved to Hive]",
            "body": (
                f"This content has moved to Hive.\n\n"
                f"Read the full post here: {hive_url}\n\n"
                f"---\n"
                f"*We have migrated to [Hive](https://hive.blog). "
                f"Please follow us there for all future updates.*"
            )
        }


# Usage
manager = DualChainManager("myproject", "5KpostingKey", "dual")

# Generate migration announcement
title, body = manager.generate_migration_announcement("MyProject")
permlink = manager.post_to_hive(title, body, ["myproject", "hive", "migration"])
print(f"Posted migration announcement: @myproject/{permlink}")

# Check which community members exist on Hive
members = ["user1", "user2", "user3", "user4"]
mapping = manager.create_account_mapping(members)
for name, info in mapping.items():
    status = "EXISTS" if info["exists"] else "MISSING"
    print(f"  @{name}: {status}")

# Migrate old content links
old_content = "Check out https://steemit.com/@dev/post and earn STEEM!"
new_content = ContentMigrator.migrate_full_content(old_content)
print(f"Migrated: {new_content}")
```

Migration best practices: (1) Announce the migration plan with a clear timeline at least 2 weeks in advance. (2) Run dual-chain posting during transition to avoid losing audience. (3) Use the account mapping tool to identify which community members already have Hive accounts. (4) Migrate content links and token references in documentation and historical posts. (5) Post redirect notices on Steem pointing to Hive after the full migration. (6) Keep the Steem account active for a period to redirect stragglers. The most successful migrations gave communities 4-6 weeks of dual-chain operation before going Hive-only.'''
    ),
    (
        "hive-migration-data-export",
        r'''How do I export my full content and data from Steem and archive it, or import historical data references into a Hive-based application?''',
        r'''Exporting data from either chain uses the same API patterns since they share the condenser_api interface. The key is paginating through account_history and content efficiently. Here is a comprehensive data export tool:

```python
import requests
import json
import os
import time
from datetime import datetime

class BlockchainDataExporter:
    """
    Export all account data from Steem or Hive for archival
    or migration purposes. Works with both chains via node URL.
    """

    def __init__(self, node_url, output_dir="./export"):
        self.node = node_url
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def api_call(self, method, params):
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        for attempt in range(3):
            try:
                resp = requests.post(self.node, json=payload, timeout=30)
                data = resp.json()
                if "result" in data:
                    return data["result"]
                if "error" in data:
                    print(f"API error: {data['error']}")
                    return None
            except Exception as e:
                print(f"Request failed (attempt {attempt + 1}): {e}")
                time.sleep(2 ** attempt)
        return None

    def export_account_info(self, username):
        """Export account profile and settings."""
        accounts = self.api_call("condenser_api.get_accounts", [[username]])
        if not accounts:
            return None
        account = accounts[0]
        filepath = os.path.join(self.output_dir, f"{username}_account.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(account, f, indent=2)
        print(f"Exported account info: {filepath}")
        return account

    def export_posts(self, username, limit=500):
        """Export all posts by an account using bridge API."""
        all_posts = []
        start_author = ""
        start_permlink = ""
        while len(all_posts) < limit:
            params = {
                "sort": "posts",
                "account": username,
                "limit": 20,
            }
            if start_author:
                params["start_author"] = start_author
                params["start_permlink"] = start_permlink
            posts = self.api_call("bridge.get_account_posts", params)
            if not posts:
                break
            # Skip first result if it is a continuation
            if start_author and posts:
                posts = posts[1:]
            if not posts:
                break
            all_posts.extend(posts)
            last = posts[-1]
            start_author = last["author"]
            start_permlink = last["permlink"]
            print(f"  Fetched {len(all_posts)} posts...")
            time.sleep(0.5)
        filepath = os.path.join(self.output_dir, f"{username}_posts.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(all_posts, f, indent=2)
        print(f"Exported {len(all_posts)} posts: {filepath}")
        return all_posts

    def export_comments(self, username, limit=1000):
        """Export all comments/replies by an account."""
        all_comments = []
        start_author = ""
        start_permlink = ""
        while len(all_comments) < limit:
            params = {
                "sort": "comments",
                "account": username,
                "limit": 20,
            }
            if start_author:
                params["start_author"] = start_author
                params["start_permlink"] = start_permlink
            comments = self.api_call("bridge.get_account_posts", params)
            if not comments:
                break
            if start_author and comments:
                comments = comments[1:]
            if not comments:
                break
            all_comments.extend(comments)
            last = comments[-1]
            start_author = last["author"]
            start_permlink = last["permlink"]
            time.sleep(0.5)
        filepath = os.path.join(self.output_dir, f"{username}_comments.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(all_comments, f, indent=2)
        print(f"Exported {len(all_comments)} comments: {filepath}")
        return all_comments

    def export_account_history(self, username, limit=10000):
        """
        Export full account operation history.
        This includes all transfers, votes, posts, delegations, etc.
        """
        all_ops = []
        last_id = -1
        batch_size = 1000
        while len(all_ops) < limit:
            result = self.api_call(
                "condenser_api.get_account_history",
                [username, last_id, min(batch_size, limit - len(all_ops))]
            )
            if not result:
                break
            for item in result:
                op_id = item[0]
                op_data = item[1]
                all_ops.append({
                    "id": op_id,
                    "block": op_data.get("block"),
                    "timestamp": op_data.get("timestamp"),
                    "op_type": op_data.get("op", [None])[0],
                    "op_data": op_data.get("op", [None, {}])[1],
                    "trx_id": op_data.get("trx_id"),
                })
            if len(result) < batch_size:
                break
            last_id = result[0][0] - 1
            if last_id < 0:
                break
            print(f"  Fetched {len(all_ops)} history entries...")
            time.sleep(0.5)
        # Sort chronologically
        all_ops.sort(key=lambda x: x["id"])
        filepath = os.path.join(self.output_dir, f"{username}_history.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(all_ops, f, indent=2)
        print(f"Exported {len(all_ops)} history entries: {filepath}")
        return all_ops

    def export_followers(self, username):
        """Export follower and following lists."""
        followers = []
        start = ""
        while True:
            result = self.api_call(
                "condenser_api.get_followers",
                [username, start, "blog", 1000]
            )
            if not result:
                break
            if start and result:
                result = result[1:]
            if not result:
                break
            followers.extend([f["follower"] for f in result])
            start = result[-1]["follower"]
            time.sleep(0.3)
        following = []
        start = ""
        while True:
            result = self.api_call(
                "condenser_api.get_following",
                [username, start, "blog", 1000]
            )
            if not result:
                break
            if start and result:
                result = result[1:]
            if not result:
                break
            following.extend([f["following"] for f in result])
            start = result[-1]["following"]
            time.sleep(0.3)
        data = {"followers": followers, "following": following}
        filepath = os.path.join(self.output_dir, f"{username}_social.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Exported {len(followers)} followers, {len(following)} following: {filepath}")
        return data

    def full_export(self, username):
        """Run complete data export for an account."""
        print(f"Starting full export for @{username}")
        print(f"Output directory: {self.output_dir}")
        print("=" * 50)
        self.export_account_info(username)
        self.export_posts(username)
        self.export_comments(username)
        self.export_followers(username)
        self.export_account_history(username)
        print("=" * 50)
        print(f"Export complete for @{username}")
        total_size = sum(
            os.path.getsize(os.path.join(self.output_dir, f))
            for f in os.listdir(self.output_dir)
            if f.startswith(username)
        )
        print(f"Total export size: {total_size / 1024 / 1024:.2f} MB")

# Export from Hive
hive_exporter = BlockchainDataExporter(
    "https://api.hive.blog",
    output_dir="./hive_export"
)
hive_exporter.full_export("myaccount")
```

This tool exports account info, all posts, all comments, follower/following lists, and full operation history. The data is saved as JSON files for archival or import into another system. For very active accounts with large histories, the export can take several minutes due to API pagination limits. The same code works against Steem nodes by simply changing the node URL. For archival purposes, store the exported JSON alongside IPFS-pinned images referenced in posts to create a complete offline backup of all blockchain content.'''
    ),
]
