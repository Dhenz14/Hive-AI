"""
Hive blockchain NFT training pairs: NFT creation, marketplace integration,
collection management, metadata standards, Hive NFT gaming.
"""

PAIRS = [
    (
        "hive-nft-creation",
        r'''How do I create and issue NFTs on Hive Engine using the nft contract? Show me the complete process from defining the NFT to minting instances.''',
        r'''<think>
NFTs on Hive Engine... I think they use some kind of token contract. Could be the "tokens" contract since that handles fungible tokens, but wait -- NFTs are non-fungible, so there must be a separate "nft" contract specifically for this. Let me think through the steps.

The process could be as simple as just minting tokens directly, but actually that would skip the definition step. You first need to create an NFT definition (symbol, name, properties), then add data properties to the schema, and only then can you mint instances. I initially considered whether enabling issuance was a separate step, but hmm, looking at the contract design, issuance is controlled by the authorizedIssuingAccounts field set during creation, so it is part of the create action rather than a standalone step.

All operations are custom_json broadcasts through ssc-mainnet-hive -- not ssc-mainnet1, since that was the old Steem Engine identifier. Therefore I need to show the full lifecycle with real contract actions, because a partial example would leave the reader unable to actually mint anything.
</think>

NFTs on Hive Engine are managed through the **nft** contract. The process involves creating an NFT definition, configuring its properties, and then minting individual token instances. Each NFT symbol is unique on the sidechain and can have custom data properties attached to every instance.

Here is a complete Python workflow using beem:

```python
from beem import Hive
import json
import time

hive = Hive(keys=["5KactiveKeyHere"], node=["https://api.hive.blog"])
ACCOUNT = "myaccount"

def broadcast_engine(contract_name, contract_action, payload):
    """Helper to broadcast Hive Engine custom_json operations."""
    data = {
        "contractName": contract_name,
        "contractAction": contract_action,
        "contractPayload": payload
    }
    hive.custom_json(
        "ssc-mainnet-hive",
        json.dumps(data),
        required_auths=[ACCOUNT],
        required_posting_auths=[]
    )
    print(f"Broadcast: {contract_name}.{contract_action}")
    time.sleep(4)  # Wait for sidechain block

def create_nft_definition():
    """
    Step 1: Create the NFT symbol on Hive Engine.
    This costs BEE tokens (creation fee set by sidechain governance).
    Symbol must be unique, uppercase, 3-10 chars.
    """
    broadcast_engine("nft", "create", {
        "symbol": "MYART",
        "name": "My Art Collection",
        "maxSupply": 10000,  # 0 for unlimited
        "url": "https://mysite.com/collection",
        "authorizedIssuingAccounts": [ACCOUNT],
        "authorizedIssuingContracts": []
    })

def add_nft_properties():
    """
    Step 2: Define data properties for NFT instances.
    Each property has a name, type, and whether it is read-only after minting.
    Supported types: number, string, boolean
    """
    properties = [
        {"name": "name", "type": "string", "isReadOnly": True},
        {"name": "image", "type": "string", "isReadOnly": True},
        {"name": "description", "type": "string", "isReadOnly": True},
        {"name": "edition", "type": "number", "isReadOnly": True},
        {"name": "rarity", "type": "string", "isReadOnly": True},
        {"name": "artist", "type": "string", "isReadOnly": True},
    ]
    for prop in properties:
        broadcast_engine("nft", "addProperty", {
            "symbol": "MYART",
            "name": prop["name"],
            "type": prop["type"],
            "isReadOnly": prop["isReadOnly"]
        })
        print(f"  Added property: {prop['name']}")

def mint_nft_instances(editions):
    """
    Step 3: Mint individual NFT instances with metadata.
    Each instance gets a unique _id on the sidechain.
    """
    for edition in editions:
        broadcast_engine("nft", "issue", {
            "symbol": "MYART",
            "to": edition.get("to", ACCOUNT),
            "feeSymbol": "BEE",
            "properties": {
                "name": edition["name"],
                "image": edition["image"],
                "description": edition["description"],
                "edition": edition["number"],
                "rarity": edition["rarity"],
                "artist": edition["artist"]
            }
        })
        print(f"  Minted: {edition['name']} #{edition['number']}")

def batch_mint(symbol, recipients, properties_list):
    """Batch mint multiple NFTs in a single transaction (up to sidechain limits)."""
    instances = []
    for i, (recipient, props) in enumerate(zip(recipients, properties_list)):
        instances.append({
            "symbol": symbol,
            "to": recipient,
            "feeSymbol": "BEE",
            "properties": props
        })
    # Hive Engine supports batch issuing via issueMultiple
    broadcast_engine("nft", "issueMultiple", {
        "instances": instances
    })
    print(f"Batch minted {len(instances)} NFTs")

# Execute the full creation flow
create_nft_definition()
add_nft_properties()
editions = [
    {"name": "Sunset Valley", "image": "https://ipfs.io/ipfs/Qm123abc",
     "description": "Digital landscape painting", "number": 1,
     "rarity": "legendary", "artist": "hiveartist", "to": ACCOUNT},
    {"name": "Sunset Valley", "image": "https://ipfs.io/ipfs/Qm123abc",
     "description": "Digital landscape painting", "number": 2,
     "rarity": "rare", "artist": "hiveartist", "to": "collector1"},
    {"name": "Sunset Valley", "image": "https://ipfs.io/ipfs/Qm123abc",
     "description": "Digital landscape painting", "number": 3,
     "rarity": "common", "artist": "hiveartist", "to": "collector2"},
]
mint_nft_instances(editions)
```

Key details: NFT creation requires BEE tokens for fees. The `maxSupply` of 0 means unlimited. Properties marked `isReadOnly: True` cannot be changed after minting. Images should be stored on IPFS or a permanent host since only the URL is stored on-chain. Use `issueMultiple` for batch mints to save on transaction costs. Each minted instance receives an auto-incrementing `_id` that serves as the unique token identifier within that NFT symbol.'''
    ),
    (
        "hive-nft-marketplace",
        r'''How do I list NFTs for sale and handle purchases on the Hive Engine NFT marketplace programmatically?''',
        r'''The Hive Engine NFT marketplace uses the **nftmarket** contract for listing, buying, and managing NFT sales. All marketplace operations are custom_json transactions. Here is a complete marketplace integration:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");
const axios = require("axios");

const client = new Client(["https://api.hive.blog"]);
const ENGINE_RPC = "https://engine.rishipanthee.com/contracts";

class NFTMarketplace {
    constructor(account, activeKey) {
        this.account = account;
        this.key = PrivateKey.fromString(activeKey);
    }

    async broadcast(contractName, contractAction, payload) {
        const json = JSON.stringify({ contractName, contractAction, contractPayload: payload });
        return client.broadcast.json(
            { required_auths: [this.account], required_posting_auths: [],
              id: "ssc-mainnet-hive", json },
            this.key
        );
    }

    async query(contract, table, queryObj, limit = 100) {
        const resp = await axios.post(ENGINE_RPC, {
            jsonrpc: "2.0", id: 1, method: "find",
            params: { contract, table, query: queryObj, limit }
        });
        return resp.data.result || [];
    }

    async listForSale(symbol, nftIds, price, priceSymbol = "SWAP.HIVE") {
        /**
         * List one or more NFTs for sale on the marketplace.
         * nftIds: array of string IDs from the NFT instances
         * price: price per NFT in the specified token
         */
        return this.broadcast("nftmarket", "sell", {
            symbol: symbol,
            nfts: nftIds,
            price: price.toFixed(8),
            priceSymbol: priceSymbol,
            fee: 500  // 5% marketplace fee in basis points
        });
    }

    async buyNFT(symbol, nftIds, marketAccount = "nftmarket") {
        /**
         * Purchase listed NFTs. Payment is automatically handled
         * by the sidechain from buyer's token balance.
         */
        return this.broadcast("nftmarket", "buy", {
            symbol: symbol,
            nfts: nftIds,
            marketAccount: marketAccount
        });
    }

    async cancelSale(symbol, nftIds) {
        return this.broadcast("nftmarket", "cancel", {
            symbol: symbol,
            nfts: nftIds
        });
    }

    async changePrice(symbol, nftIds, newPrice) {
        return this.broadcast("nftmarket", "changePrice", {
            symbol: symbol,
            nfts: nftIds,
            price: newPrice.toFixed(8)
        });
    }

    async getListedNFTs(symbol, limit = 50) {
        const listings = await this.query("nftmarket", symbol + "sellBook", {}, limit);
        return listings.map(l => ({
            nftId: l.nftId,
            account: l.account,
            price: l.price,
            priceSymbol: l.priceSymbol,
            timestamp: l.timestamp
        }));
    }

    async getMyListings(symbol) {
        return this.query("nftmarket", symbol + "sellBook",
            { account: this.account }, 100);
    }

    async getNFTInstances(symbol, queryFilter = {}, limit = 100) {
        return this.query("nft", symbol + "instances", queryFilter, limit);
    }

    async getMyNFTs(symbol) {
        return this.getNFTInstances(symbol, { account: this.account });
    }

    async getFloorPrice(symbol) {
        const listings = await this.getListedNFTs(symbol, 500);
        if (!listings.length) return null;
        const prices = listings.map(l => parseFloat(l.price));
        prices.sort((a, b) => a - b);
        return {
            floor: prices[0],
            median: prices[Math.floor(prices.length / 2)],
            ceiling: prices[prices.length - 1],
            totalListed: prices.length
        };
    }

    async transferNFT(symbol, nftIds, toAccount) {
        return this.broadcast("nft", "transfer", {
            to: toAccount,
            nfts: [{ symbol, ids: nftIds }]
        });
    }

    async burnNFT(symbol, nftIds) {
        return this.broadcast("nft", "burn", {
            nfts: [{ symbol, ids: nftIds }]
        });
    }
}

// Usage example: list, query, and buy NFTs
(async () => {
    const market = new NFTMarketplace("myaccount", "5KactiveKey");
    // List 3 NFTs for 10 SWAP.HIVE each
    await market.listForSale("MYART", ["1", "2", "3"], 10.0, "SWAP.HIVE");
    console.log("Listed 3 NFTs for sale");
    // Check floor price
    const floor = await market.getFloorPrice("MYART");
    console.log("Floor price:", floor);
    // Get all my owned NFTs
    const myNfts = await market.getMyNFTs("MYART");
    console.log("My NFTs:", myNfts.length);
    // Buy an NFT (as a different user)
    const buyer = new NFTMarketplace("buyeraccount", "5KbuyerActive");
    await buyer.buyNFT("MYART", ["1"]);
    console.log("Purchased NFT #1");
})();
```

Important marketplace details: the `fee` parameter on sell orders is in basis points (500 = 5%). The buyer must have sufficient token balance (e.g., SWAP.HIVE) in their Hive Engine wallet before calling buy. The sell book table name is the NFT symbol concatenated with "sellBook" (e.g., "MYARTsellBook"). NFT transfers and burns use the core "nft" contract, not "nftmarket". Always verify the NFT instance data before purchasing by querying the instances table to check properties and provenance.'''
    ),
    (
        "hive-nft-collection-management",
        r'''How do I build an NFT collection management system on Hive that tracks ownership, handles royalties, and manages collection metadata?''',
        r'''<think>
Building a collection management system... this could involve several approaches. My first thought was to just query NFT instances and display ownership, but wait -- the user also wants royalties and provenance tracking, which are fundamentally different problems.

For provenance, I considered using account_history to trace transfers, but actually the sidechain stores its own transfer history in the NFT instances table, so querying Hive Engine directly makes more sense since it avoids parsing every custom_json on the main chain.

Now for royalties -- hmm, do Hive Engine NFTs have built-in royalty support like ERC-2981 on Ethereum? Let me think... no, they do not. The nft and nftmarket contracts have no royalty enforcement mechanism. Therefore royalties must be enforced at the application layer or through a custom wrapper contract. This is a significant limitation, because sellers could simply bypass any off-chain royalty system. I will build a comprehensive manager that calculates royalties owed from trade history, even though enforcement remains a social-layer problem.
</think>

Hive Engine NFTs do not have protocol-level royalties, so collection management requires application-layer logic. Here is a comprehensive collection manager in Python:

```python
import requests
import json
from datetime import datetime
from beem import Hive

ENGINE_RPC = "https://engine.rishipanthee.com/contracts"
ENGINE_HISTORY = "https://history.hive-engine.com/accountHistory"

class NFTCollectionManager:
    def __init__(self, symbol, creator_account, active_key=None):
        self.symbol = symbol
        self.creator = creator_account
        self.royalty_pct = 5.0  # 5% royalty on secondary sales
        if active_key:
            self.hive = Hive(keys=[active_key], node=["https://api.hive.blog"])
        else:
            self.hive = None

    def engine_query(self, contract, table, query, limit=1000, offset=0):
        resp = requests.post(ENGINE_RPC, json={
            "jsonrpc": "2.0", "id": 1, "method": "find",
            "params": {"contract": contract, "table": table,
                       "query": query, "limit": limit, "offset": offset}
        })
        return resp.json().get("result", [])

    def get_collection_stats(self):
        """Get comprehensive collection statistics."""
        instances = self.engine_query("nft", f"{self.symbol}instances", {}, 1000)
        if not instances:
            return {"error": "No instances found"}
        owners = {}
        rarity_dist = {}
        for inst in instances:
            owner = inst.get("account", "unknown")
            owners[owner] = owners.get(owner, 0) + 1
            props = inst.get("properties", {})
            rarity = props.get("rarity", "unknown")
            rarity_dist[rarity] = rarity_dist.get(rarity, 0) + 1
        # Check marketplace listings
        listings = self.engine_query("nftmarket", f"{self.symbol}sellBook", {}, 1000)
        listed_prices = [float(l["price"]) for l in listings]
        floor_price = min(listed_prices) if listed_prices else None
        return {
            "symbol": self.symbol,
            "total_supply": len(instances),
            "unique_owners": len(owners),
            "top_holders": sorted(owners.items(), key=lambda x: -x[1])[:10],
            "rarity_distribution": rarity_dist,
            "listed_count": len(listings),
            "floor_price": floor_price,
            "ownership_concentration": max(owners.values()) / len(instances) * 100
        }

    def get_provenance(self, nft_id):
        """Track full ownership history of a specific NFT instance."""
        instance = self.engine_query("nft", f"{self.symbol}instances",
                                     {"_id": int(nft_id)}, 1)
        if not instance:
            return {"error": f"NFT {nft_id} not found"}
        inst = instance[0]
        # Query transfer history from sidechain
        transfers = self.engine_query("nft", f"{self.symbol}transferHistory",
                                      {"nftId": str(nft_id)}, 100)
        history = []
        for t in transfers:
            history.append({
                "from": t.get("from", "mint"),
                "to": t.get("to"),
                "timestamp": t.get("timestamp"),
                "type": t.get("type", "transfer")
            })
        return {
            "nft_id": nft_id,
            "symbol": self.symbol,
            "current_owner": inst.get("account"),
            "properties": inst.get("properties", {}),
            "transfer_count": len(history),
            "provenance": history
        }

    def calculate_royalties_owed(self):
        """
        Scan recent marketplace sales and calculate royalties owed to creator.
        Since Hive Engine has no built-in royalties, this tracks what
        should be paid and can be enforced via community agreement
        or a separate royalty collection bot.
        """
        # Query completed trades from sidechain history
        trades = self.engine_query("nftmarket", f"{self.symbol}tradeHistory",
                                   {}, 500)
        royalties = []
        total_owed = 0.0
        for trade in trades:
            sale_price = float(trade.get("price", 0))
            royalty_amount = sale_price * (self.royalty_pct / 100)
            total_owed += royalty_amount
            royalties.append({
                "nft_id": trade.get("nftId"),
                "seller": trade.get("account"),
                "buyer": trade.get("buyer", "unknown"),
                "sale_price": sale_price,
                "royalty_owed": round(royalty_amount, 8),
                "price_symbol": trade.get("priceSymbol", "SWAP.HIVE")
            })
        return {
            "royalty_pct": self.royalty_pct,
            "total_sales": len(royalties),
            "total_royalties_owed": round(total_owed, 8),
            "details": royalties
        }

    def update_collection_metadata(self, new_url=None, new_authorized_accounts=None):
        """Update collection-level settings (requires creator authority)."""
        if not self.hive:
            raise ValueError("Active key required for metadata updates")
        if new_url:
            payload = {
                "contractName": "nft", "contractAction": "updateUrl",
                "contractPayload": {"symbol": self.symbol, "url": new_url}
            }
            self.hive.custom_json(
                "ssc-mainnet-hive", json.dumps(payload),
                required_auths=[self.creator], required_posting_auths=[]
            )
        if new_authorized_accounts:
            for acct in new_authorized_accounts:
                payload = {
                    "contractName": "nft",
                    "contractAction": "addAuthorizedIssuingAccounts",
                    "contractPayload": {
                        "symbol": self.symbol,
                        "accounts": [acct]
                    }
                }
                self.hive.custom_json(
                    "ssc-mainnet-hive", json.dumps(payload),
                    required_auths=[self.creator], required_posting_auths=[]
                )

    def export_collection_data(self):
        """Export all NFT instances with properties for off-chain analytics."""
        all_instances = []
        offset = 0
        while True:
            batch = self.engine_query("nft", f"{self.symbol}instances",
                                      {}, 1000, offset)
            if not batch:
                break
            all_instances.extend(batch)
            offset += len(batch)
            if len(batch) < 1000:
                break
        return [{
            "id": inst["_id"],
            "owner": inst.get("account"),
            "properties": inst.get("properties", {}),
            "delegated_to": inst.get("ownedBy", "u")
        } for inst in all_instances]

# Usage
manager = NFTCollectionManager("MYART", "myaccount", "5KactiveKey")
stats = manager.get_collection_stats()
print(f"Collection: {stats['symbol']}")
print(f"Supply: {stats['total_supply']}, Owners: {stats['unique_owners']}")
print(f"Floor: {stats['floor_price']} SWAP.HIVE")
print(f"Rarity dist: {stats['rarity_distribution']}")
provenance = manager.get_provenance("1")
print(f"NFT #1 owner: {provenance['current_owner']}, transfers: {provenance['transfer_count']}")
```

This system provides collection analytics, provenance tracking, and royalty calculation. Since royalties are not enforced at the protocol level on Hive Engine, creators typically enforce them through social contracts, marketplace agreements, or by building royalty payment into a custom marketplace smart contract that wraps the nftmarket operations. For production collections, store extended metadata on IPFS and reference the CID in the NFT properties.'''
    ),
    (
        "hive-nft-metadata-standards",
        r'''What are the metadata standards and best practices for Hive NFTs, including IPFS integration and property schemas?''',
        r'''Hive Engine NFTs store properties directly on the sidechain as key-value pairs. For rich metadata, the standard practice combines on-chain properties with off-chain JSON metadata hosted on IPFS. Here is the recommended approach:

```python
import json
import hashlib
import requests
from datetime import datetime

class HiveNFTMetadataBuilder:
    """
    Build standards-compliant metadata for Hive Engine NFTs.
    Follows community conventions compatible with NFTMart, Tribaldex,
    and other Hive NFT marketplaces.
    """

    # Standard on-chain properties that marketplaces recognize
    STANDARD_SCHEMA = {
        "name": {"type": "string", "isReadOnly": True,
                 "desc": "Display name of the NFT"},
        "image": {"type": "string", "isReadOnly": True,
                  "desc": "Primary image URL (IPFS preferred)"},
        "type": {"type": "string", "isReadOnly": True,
                 "desc": "Media type: image, video, audio, document"},
        "rarity": {"type": "string", "isReadOnly": True,
                   "desc": "Rarity tier: common, uncommon, rare, epic, legendary"},
        "edition": {"type": "number", "isReadOnly": True,
                    "desc": "Edition number within a series"},
        "metadata": {"type": "string", "isReadOnly": True,
                     "desc": "IPFS CID or URL to full JSON metadata"},
    }

    # Extended on-chain properties for gaming NFTs
    GAMING_SCHEMA = {
        "level": {"type": "number", "isReadOnly": False},
        "power": {"type": "number", "isReadOnly": False},
        "xp": {"type": "number", "isReadOnly": False},
        "class": {"type": "string", "isReadOnly": True},
        "element": {"type": "string", "isReadOnly": True},
    }

    def __init__(self, collection_name, creator):
        self.collection_name = collection_name
        self.creator = creator
        self.metadata_cache = {}

    def build_offchain_metadata(self, name, description, image_cid,
                                 attributes=None, animation_url=None):
        """
        Build off-chain JSON metadata document following the community standard.
        This gets uploaded to IPFS, and the CID stored on-chain.
        """
        metadata = {
            "name": name,
            "description": description,
            "image": f"ipfs://{image_cid}",
            "collection": {
                "name": self.collection_name,
                "creator": self.creator,
                "chain": "hive",
                "sidechain": "hive-engine"
            },
            "created": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "attributes": attributes or [],
            "properties": {
                "content_type": "image/png",
                "content_hash": image_cid,
                "license": "CC BY-NC 4.0"
            }
        }
        if animation_url:
            metadata["animation_url"] = animation_url
            metadata["properties"]["has_animation"] = True
        return metadata

    def upload_to_ipfs(self, metadata_dict, pinata_jwt=None):
        """
        Upload metadata JSON to IPFS via Pinata or local node.
        Returns the IPFS CID for on-chain reference.
        """
        json_bytes = json.dumps(metadata_dict, indent=2).encode("utf-8")
        if pinata_jwt:
            # Pinata pinning API
            headers = {"Authorization": f"Bearer {pinata_jwt}"}
            files = {"file": ("metadata.json", json_bytes, "application/json")}
            resp = requests.post(
                "https://api.pinata.cloud/pinning/pinFileToIPFS",
                headers=headers, files=files
            )
            resp.raise_for_status()
            cid = resp.json()["IpfsHash"]
        else:
            # Local IPFS node
            resp = requests.post(
                "http://localhost:5001/api/v0/add",
                files={"file": json_bytes}
            )
            cid = resp.json()["Hash"]
        return cid

    def build_onchain_properties(self, name, image_cid, metadata_cid,
                                  rarity="common", edition=1, nft_type="image"):
        """
        Build the on-chain properties dict for minting.
        These are stored directly on Hive Engine sidechain.
        """
        return {
            "name": name,
            "image": f"https://ipfs.io/ipfs/{image_cid}",
            "type": nft_type,
            "rarity": rarity,
            "edition": edition,
            "metadata": f"ipfs://{metadata_cid}"
        }

    def validate_properties(self, properties, schema=None):
        """Validate properties against schema before minting."""
        schema = schema or self.STANDARD_SCHEMA
        errors = []
        for key, config in schema.items():
            if key not in properties:
                errors.append(f"Missing required property: {key}")
                continue
            value = properties[key]
            expected_type = config["type"]
            if expected_type == "string" and not isinstance(value, str):
                errors.append(f"{key} must be string, got {type(value).__name__}")
            elif expected_type == "number" and not isinstance(value, (int, float)):
                errors.append(f"{key} must be number, got {type(value).__name__}")
            elif expected_type == "boolean" and not isinstance(value, bool):
                errors.append(f"{key} must be boolean, got {type(value).__name__}")
        # Check string length limits (Hive Engine enforces max property sizes)
        for key, value in properties.items():
            if isinstance(value, str) and len(value) > 1000:
                errors.append(f"{key} exceeds 1000 char limit ({len(value)} chars)")
        return {"valid": len(errors) == 0, "errors": errors}

    def generate_collection_manifest(self, items):
        """
        Generate a collection manifest for batch minting.
        Items: list of dicts with name, image_cid, description, rarity, edition
        """
        manifest = {
            "collection": self.collection_name,
            "creator": self.creator,
            "total_items": len(items),
            "generated": datetime.utcnow().isoformat(),
            "items": []
        }
        for item in items:
            metadata = self.build_offchain_metadata(
                name=item["name"],
                description=item["description"],
                image_cid=item["image_cid"],
                attributes=item.get("attributes", [])
            )
            onchain = self.build_onchain_properties(
                name=item["name"],
                image_cid=item["image_cid"],
                metadata_cid="PENDING_UPLOAD",
                rarity=item.get("rarity", "common"),
                edition=item.get("edition", 1)
            )
            validation = self.validate_properties(onchain)
            manifest["items"].append({
                "offchain_metadata": metadata,
                "onchain_properties": onchain,
                "validation": validation
            })
        valid_count = sum(1 for i in manifest["items"] if i["validation"]["valid"])
        manifest["valid_items"] = valid_count
        manifest["invalid_items"] = len(items) - valid_count
        return manifest

# Usage
builder = HiveNFTMetadataBuilder("Cosmic Creatures", "nftcreator")
metadata = builder.build_offchain_metadata(
    name="Galaxy Dragon #1",
    description="A rare cosmic dragon from the Andromeda nebula series",
    image_cid="QmT8K5xYz9abc123def456",
    attributes=[
        {"trait_type": "Background", "value": "Nebula"},
        {"trait_type": "Wings", "value": "Crystalline"},
        {"trait_type": "Power Level", "value": 9500, "display_type": "number"}
    ]
)
print(json.dumps(metadata, indent=2))
onchain = builder.build_onchain_properties(
    "Galaxy Dragon #1", "QmT8K5xYz9abc123def456",
    "QmMetadataCID789", "legendary", 1
)
print("Validation:", builder.validate_properties(onchain))
```

Best practices: (1) Always use IPFS for images and extended metadata -- HTTP URLs can go offline. (2) Keep on-chain properties minimal since sidechain storage costs BEE tokens per property. (3) Use the `metadata` property to link to a full JSON document with attributes, provenance, and license info. (4) Pin your IPFS content with multiple services (Pinata, Infura, local node) for redundancy. (5) Use `isReadOnly: True` for immutable traits and `False` for game stats that evolve.'''
    ),
    (
        "hive-nft-gaming",
        r'''Show me how to build an NFT-based game item system on Hive where items have mutable stats that change through gameplay.''',
        r'''<think>
Gaming NFTs on Hive Engine need properties that change over time -- stats like level, XP, power. But wait, can NFT properties even be modified after minting? On most blockchains they cannot, which would make this impossible. Hmm, actually Hive Engine's nft contract has an isReadOnly flag per property. If isReadOnly is set to false, the property can be updated after minting via setProperties. That is the key mechanism here.

I initially thought any account could call setProperties on any NFT, but that would be a disaster for game integrity since players could just set their own stats. Actually, only the authorizedIssuingAccounts (the game server account) can modify properties, so the security model is built into the contract authorization layer. Therefore the game server acts as a trusted intermediary -- it validates gameplay events and then broadcasts the stat changes.

The remaining challenge is ensuring the game server key is kept secure, because if it leaks, someone could forge stat updates for any item. Since all state changes are recorded on the sidechain, at least any cheating would be auditable after the fact.
</think>

Hive Engine NFTs support mutable properties, making them ideal for game items with evolving stats. The game server (an authorized account) updates properties via custom_json. Here is a complete game item system:

```javascript
const { Client, PrivateKey } = require("@hiveio/dhive");
const axios = require("axios");

const client = new Client(["https://api.hive.blog"]);
const ENGINE_RPC = "https://engine.rishipanthee.com/contracts";

class GameItemSystem {
    constructor(gameAccount, activeKey, nftSymbol) {
        this.gameAccount = gameAccount;
        this.key = PrivateKey.fromString(activeKey);
        this.symbol = nftSymbol;
    }

    async broadcast(contractName, contractAction, payload) {
        const json = JSON.stringify({ contractName, contractAction, contractPayload: payload });
        return client.broadcast.json(
            { required_auths: [this.gameAccount], required_posting_auths: [],
              id: "ssc-mainnet-hive", json },
            this.key
        );
    }

    async query(table, queryObj, limit = 100) {
        const resp = await axios.post(ENGINE_RPC, {
            jsonrpc: "2.0", id: 1, method: "find",
            params: { contract: "nft", table, query: queryObj, limit }
        });
        return resp.data.result || [];
    }

    async setupGameNFT() {
        // Create NFT with both immutable (base traits) and mutable (game stats) properties
        await this.broadcast("nft", "create", {
            symbol: this.symbol,
            name: "Hive Quest Items",
            maxSupply: 0,
            url: "https://hivequest.game/items",
            authorizedIssuingAccounts: [this.gameAccount],
            authorizedIssuingContracts: []
        });
        // Immutable properties (set at mint, never change)
        const immutableProps = [
            { name: "name", type: "string", isReadOnly: true },
            { name: "image", type: "string", isReadOnly: true },
            { name: "itemClass", type: "string", isReadOnly: true },
            { name: "element", type: "string", isReadOnly: true },
            { name: "maxLevel", type: "number", isReadOnly: true },
            { name: "rarity", type: "string", isReadOnly: true },
        ];
        // Mutable properties (game server can update these)
        const mutableProps = [
            { name: "level", type: "number", isReadOnly: false },
            { name: "xp", type: "number", isReadOnly: false },
            { name: "attack", type: "number", isReadOnly: false },
            { name: "defense", type: "number", isReadOnly: false },
            { name: "durability", type: "number", isReadOnly: false },
            { name: "enchantment", type: "string", isReadOnly: false },
        ];
        for (const prop of [...immutableProps, ...mutableProps]) {
            await this.broadcast("nft", "addProperty", {
                symbol: this.symbol, ...prop
            });
            console.log(`Added property: ${prop.name} (${prop.isReadOnly ? "immutable" : "mutable"})`);
        }
    }

    async mintItem(toPlayer, itemData) {
        return this.broadcast("nft", "issue", {
            symbol: this.symbol,
            to: toPlayer,
            feeSymbol: "BEE",
            properties: {
                name: itemData.name,
                image: itemData.image,
                itemClass: itemData.itemClass,
                element: itemData.element,
                maxLevel: itemData.maxLevel,
                rarity: itemData.rarity,
                level: 1,
                xp: 0,
                attack: itemData.baseAttack,
                defense: itemData.baseDefense,
                durability: 100,
                enchantment: "none"
            }
        });
    }

    async updateItemStats(nftId, updates) {
        /**
         * Update mutable properties of a game item.
         * Only the authorized issuing account (game server) can do this.
         * updates: object with property names and new values
         */
        const properties = {};
        for (const [key, value] of Object.entries(updates)) {
            properties[key] = value;
        }
        return this.broadcast("nft", "setProperties", {
            symbol: this.symbol,
            nfts: [{ id: nftId.toString(), properties }]
        });
    }

    async gainXP(nftId, xpAmount) {
        const instances = await this.query(
            `${this.symbol}instances`, { _id: parseInt(nftId) }, 1);
        if (!instances.length) throw new Error("Item not found");
        const item = instances[0].properties;
        const currentXP = item.xp + xpAmount;
        const currentLevel = item.level;
        const maxLevel = item.maxLevel;
        // Level up formula: 100 * level^1.5 XP needed per level
        const xpForNextLevel = Math.floor(100 * Math.pow(currentLevel, 1.5));
        const updates = { xp: currentXP };
        if (currentXP >= xpForNextLevel && currentLevel < maxLevel) {
            updates.level = currentLevel + 1;
            updates.xp = currentXP - xpForNextLevel;
            // Stat gains on level up
            updates.attack = item.attack + Math.floor(Math.random() * 3) + 1;
            updates.defense = item.defense + Math.floor(Math.random() * 2) + 1;
            console.log(`LEVEL UP! ${item.name} is now level ${updates.level}`);
        }
        await this.updateItemStats(nftId, updates);
        return updates;
    }

    async applyEnchantment(nftId, enchantmentName, attackBonus, defenseBonus) {
        const instances = await this.query(
            `${this.symbol}instances`, { _id: parseInt(nftId) }, 1);
        if (!instances.length) throw new Error("Item not found");
        const item = instances[0].properties;
        await this.updateItemStats(nftId, {
            enchantment: enchantmentName,
            attack: item.attack + attackBonus,
            defense: item.defense + defenseBonus
        });
        console.log(`Applied ${enchantmentName} to ${item.name}`);
    }

    async takeDurabilityDamage(nftId, damage) {
        const instances = await this.query(
            `${this.symbol}instances`, { _id: parseInt(nftId) }, 1);
        if (!instances.length) throw new Error("Item not found");
        const item = instances[0].properties;
        const newDurability = Math.max(0, item.durability - damage);
        await this.updateItemStats(nftId, { durability: newDurability });
        if (newDurability === 0) {
            console.log(`WARNING: ${item.name} is broken! Needs repair.`);
        }
        return newDurability;
    }

    async repairItem(nftId) {
        await this.updateItemStats(nftId, { durability: 100 });
    }

    async getPlayerInventory(playerAccount) {
        const items = await this.query(
            `${this.symbol}instances`, { account: playerAccount }, 100);
        return items.map(i => ({
            id: i._id,
            ...i.properties,
            isBroken: i.properties.durability === 0
        }));
    }
}

// Game server usage
(async () => {
    const game = new GameItemSystem("hivequestgame", "5KgameActiveKey", "HQITEM");
    // Mint a sword for a player who completed a quest
    await game.mintItem("player1", {
        name: "Flame Sword of Valor",
        image: "https://ipfs.io/ipfs/QmSwordImage123",
        itemClass: "weapon",
        element: "fire",
        maxLevel: 50,
        rarity: "epic",
        baseAttack: 25,
        baseDefense: 5
    });
    // Player wins a battle, gains XP
    await game.gainXP("1", 150);
    // Apply enchantment from crafting
    await game.applyEnchantment("1", "Blazing Fury", 10, 0);
    // Item takes damage in combat
    await game.takeDurabilityDamage("1", 15);
    // Check player inventory
    const inv = await game.getPlayerInventory("player1");
    console.log("Player inventory:", JSON.stringify(inv, null, 2));
})();
```

Key design principles: (1) Immutable properties (isReadOnly: true) define the item identity and cannot be changed after mint, preventing counterfeiting. (2) Mutable properties (isReadOnly: false) hold game state that evolves through gameplay. (3) Only the authorized game account can call setProperties, so players cannot cheat stats. (4) All state changes are recorded on the sidechain, giving full auditability. (5) Items remain tradeable on the NFT marketplace even with mutable stats, enabling play-to-earn economies. The sidechain processes state updates in roughly 3-second blocks, so batch stat updates when possible to reduce operation count.'''
    ),
]
