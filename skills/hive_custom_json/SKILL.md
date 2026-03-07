# Hive Custom JSON Operations

Custom JSON is Hive's extensibility layer — any app can broadcast structured data on-chain without a hard fork. This powers all Layer 2 protocols, games, and dApps.

## Structure
```json
{
  "id": "app_identifier",           // max 32 chars, identifies your protocol
  "required_auths": [],             // active key signers (financial ops)
  "required_posting_auths": ["user"], // posting key signers (social ops)
  "json": "{\"action\":\"value\"}"  // stringified JSON payload, max 8192 bytes
}
```

## Authority Rules
| Operation Type | Auth Field | Key Required |
|---------------|-----------|-------------|
| Social (votes, follows, reblogs) | `required_posting_auths` | Posting key |
| Financial (token transfers, staking) | `required_auths` | Active key |
| **Never mix both** — use one or the other per operation | | |

## Hard Limits
- **JSON payload**: 8,192 bytes max (stringified)
- **ID length**: 32 characters max
- **One custom_json per transaction** is typical, but you can batch multiple ops in one tx
- **RC cost**: ~proportional to payload size. Small JSONs ~0.5% of daily RC

## Common Protocol IDs

### Hive Native
| ID | Purpose | Auth |
|----|---------|------|
| `follow` | Follow/unfollow/mute users, reblog | posting |
| `community` | Community subscribe/roles/moderation | posting |
| `notify` | Notification markers | posting |
| `rc` | RC delegation | active |

### Hive-Engine (Layer 2 Tokens)
| ID | Purpose | Auth |
|----|---------|------|
| `ssc-mainnet-hive` | All Hive-Engine operations | active (transfers), posting (social) |

```python
# Transfer Hive-Engine token
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "tokens",
    "contractAction": "transfer",
    "contractPayload": {
        "symbol": "BEE",
        "to": "recipient",
        "quantity": "10.000",
        "memo": "payment"
    }
}, required_auths=["sender"])

# Stake Hive-Engine token
h.custom_json("ssc-mainnet-hive", json_data={
    "contractName": "tokens",
    "contractAction": "stake",
    "contractPayload": {
        "symbol": "BEE",
        "to": "recipient",
        "quantity": "100.000"
    }
}, required_auths=["sender"])
```

### Splinterlands
| ID | Purpose | Auth |
|----|---------|------|
| `sm_find_match` | Queue for battle | posting |
| `sm_submit_team` | Submit battle team | posting |
| `sm_market_sale` | List card for sale | active |
| `sm_token_transfer` | Transfer in-game assets | active |

### Design Your Own Protocol
```python
# Define a clear schema with versioning
PROTOCOL_ID = "myapp"  # short, unique, lowercase

# Always include version + action for future-proofing
payload = {
    "v": 1,                    # schema version
    "action": "create_post",   # action type
    "data": {                  # action-specific payload
        "title": "Hello",
        "tags": ["intro"]
    }
}

h.custom_json(PROTOCOL_ID, json_data=payload,
              required_posting_auths=["username"])
```

## Processing Patterns

### Deterministic Processing (Critical for L2)
```python
# Custom JSON is ORDERED by block inclusion
# All nodes see the SAME order — this enables deterministic state machines

for op in blockchain.stream(opNames=["custom_json"]):
    if op["id"] == "myapp":
        data = json.loads(op["json"])
        # Process deterministically — same input = same output
        # NO external API calls, NO randomness, NO timestamps
        # Use block_num and tx_index for ordering
```

### Validation Checklist
1. Check `id` matches your protocol
2. Verify signer has authority for the action
3. Parse JSON safely (handle malformed payloads)
4. Validate all fields exist and have correct types
5. Check business rules (sufficient balance, valid target, etc.)
6. Apply state change only after all validation passes

## Common Mistakes
- **Forgetting to stringify**: `json` field must be a string, not an object
- **Wrong auth type**: Using posting auth for financial ops (will silently succeed on-chain but your L2 should reject it)
- **Exceeding 8KB**: Large payloads fail silently — compress or split across multiple ops
- **Non-deterministic processing**: Using `datetime.now()` or external APIs in your processor breaks consensus
- **Not handling reorgs**: On rare microforks, blocks can be replayed — make processing idempotent
