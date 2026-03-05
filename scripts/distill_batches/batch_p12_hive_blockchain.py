PAIRS = [
    (
        "hive-blockchain/custom-json-operations",
        r"""Explain Hive blockchain custom JSON operations including broadcasting transactions with dhive, layer-2 protocol design patterns, transaction signing and authority levels, custom JSON indexing with HAF, and building decentralized applications on Hive.""",
        r"""## Hive Blockchain Custom JSON Operations: Layer-2 Protocols and Decentralized Applications

**Hive's custom_json operation** is the foundation for building layer-2 protocols on Hive blockchain. Unlike smart contract platforms, Hive uses a **consensus-optional** model where the base layer provides ordering and immutability while layer-2 nodes interpret the JSON payloads. This is a deliberate **trade-off**: Hive sacrifices Turing-complete on-chain execution for 3-second block times and zero transaction fees, making it ideal for high-frequency social and gaming applications.

### Broadcasting Custom JSON Transactions

**Best practice**: use the `dhive` library for TypeScript/JavaScript or `beem` for Python to broadcast transactions. **Because** custom_json operations are feeless on Hive, they only require **Resource Credits (RC)** — a regenerating resource based on staked HIVE.

```python
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import json
import hashlib
import time

class AuthorityLevel(Enum):
    POSTING = "posting"   # social actions, votes, comments
    ACTIVE = "active"     # financial transfers, witness votes
    OWNER = "owner"       # account recovery, key changes

@dataclass
class CustomJsonOp:
    # Custom JSON operation structure
    # required_auths: active authority (for financial operations)
    # required_posting_auths: posting authority (for social operations)
    id: str                    # protocol identifier, max 32 chars
    json_payload: dict         # the actual data (max 8192 bytes)
    required_posting_auths: list[str] = field(default_factory=list)
    required_auths: list[str] = field(default_factory=list)

    def validate(self) -> bool:
        # Common mistake: exceeding the 8192 byte JSON limit
        # because Hive nodes reject oversized operations silently
        payload_str = json.dumps(self.json_payload)
        if len(payload_str.encode("utf-8")) > 8192:
            raise ValueError(f"JSON payload too large: {len(payload_str)} bytes (max 8192)")
        if len(self.id) > 32:
            raise ValueError(f"Operation ID too long: {len(self.id)} chars (max 32)")
        if not self.required_posting_auths and not self.required_auths:
            raise ValueError("Must specify at least one authority")
        return True

class HiveTransactionBuilder:
    # Builds and signs Hive transactions
    # Pitfall: using active authority when posting authority suffices
    # because active key exposure risks financial loss

    def __init__(self, node_url: str = "https://api.hive.blog"):
        self.node_url = node_url
        self.operations = []
        self.expiration_seconds = 60

    def add_custom_json(self, op: CustomJsonOp):
        op.validate()
        self.operations.append([
            "custom_json",
            {
                "required_auths": op.required_auths,
                "required_posting_auths": op.required_posting_auths,
                "id": op.id,
                "json": json.dumps(op.json_payload),
            }
        ])
        return self

    async def broadcast(self, signing_key: str) -> dict:
        # Build transaction with reference block
        import httpx
        # Get dynamic global properties for reference block
        async with httpx.AsyncClient() as client:
            response = await client.post(self.node_url, json={
                "jsonrpc": "2.0",
                "method": "condenser_api.get_dynamic_global_properties",
                "params": [],
                "id": 1,
            })
            props = response.json()["result"]

        ref_block_num = props["head_block_number"] & 0xFFFF
        ref_block_prefix = int(props["head_block_id"][8:16], 16)

        transaction = {
            "ref_block_num": ref_block_num,
            "ref_block_prefix": ref_block_prefix,
            "expiration": self._compute_expiration(props["time"]),
            "operations": self.operations,
            "extensions": [],
        }

        # Sign with the appropriate key
        # However, actual signing requires the Hive cryptographic library
        # Best practice: use dhive (JS) or beem (Python) for signing
        signed_tx = self._sign_transaction(transaction, signing_key)
        return signed_tx

    def _compute_expiration(self, head_time: str) -> str:
        from datetime import datetime, timedelta
        head_dt = datetime.strptime(head_time, "%Y-%m-%dT%H:%M:%S")
        exp_dt = head_dt + timedelta(seconds=self.expiration_seconds)
        return exp_dt.strftime("%Y-%m-%dT%H:%M:%S")

    def _sign_transaction(self, tx: dict, key: str) -> dict:
        # Placeholder for actual ECDSA signing
        # In production, use beem.transactionbuilder
        tx["signatures"] = ["placeholder_signature"]
        return tx
```

### Layer-2 Protocol Design on Hive

Layer-2 protocols on Hive follow a specific pattern: broadcast structured JSON, run a consensus node that replays all blocks, and maintain an off-chain state machine. **Therefore**, the protocol is deterministic — every node processing the same blocks arrives at the same state.

```python
from typing import Callable, Any
from collections import defaultdict
from datetime import datetime

@dataclass
class L2State:
    # Layer-2 state machine for a custom protocol
    balances: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    nonces: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_block: int = 0
    operations_processed: int = 0

class HiveL2Protocol:
    # Framework for building Hive layer-2 protocols
    # Examples: Hive Engine (tokens), Splinterlands (gaming), PeakD (social)
    # Trade-off: no on-chain validation means L2 nodes must validate independently
    # However, anyone can verify by replaying from genesis block

    PROTOCOL_ID = "hiveai_refinery"  # registered on-chain identifier

    def __init__(self):
        self.state = L2State()
        self.handlers: dict[str, Callable] = {}
        self.validators: dict[str, Callable] = {}

    def register_operation(
        self,
        op_name: str,
        handler: Callable,
        validator: Callable,
    ):
        self.handlers[op_name] = handler
        self.validators[op_name] = validator

    def process_block(self, block: dict) -> list[dict]:
        # Process all custom_json operations in a block that match our protocol
        # Best practice: process operations in block order for determinism
        # Common mistake: non-deterministic processing (random, time-dependent)
        results = []
        block_num = block["block_num"]

        for tx in block.get("transactions", []):
            for op_type, op_data in tx.get("operations", []):
                if op_type != "custom_json":
                    continue
                if op_data.get("id") != self.PROTOCOL_ID:
                    continue

                try:
                    payload = json.loads(op_data["json"])
                    action = payload.get("action")
                    signer = (
                        op_data.get("required_posting_auths", [None])[0]
                        or op_data.get("required_auths", [None])[0]
                    )

                    if action not in self.handlers:
                        continue

                    # Validate operation
                    if action in self.validators:
                        is_valid = self.validators[action](self.state, signer, payload)
                        if not is_valid:
                            results.append({"action": action, "status": "invalid", "signer": signer})
                            continue

                    # Execute operation (must be deterministic!)
                    result = self.handlers[action](self.state, signer, payload)
                    results.append({"action": action, "status": "success", **result})
                    self.state.operations_processed += 1

                except (json.JSONDecodeError, KeyError, IndexError):
                    # Malformed operations are silently skipped
                    # Pitfall: crashing on malformed input breaks consensus
                    continue

        self.state.last_block = block_num
        return results

# Example: HiveAI Knowledge Contribution Protocol
class KnowledgeProtocol:
    # L2 protocol for tracking knowledge contributions to HiveAI
    # Users submit knowledge, reviewers validate, contributors earn reputation

    def __init__(self):
        self.protocol = HiveL2Protocol()
        self.protocol.PROTOCOL_ID = "hiveai_knowledge"
        self._register_operations()

    def _register_operations(self):
        self.protocol.register_operation(
            "submit_knowledge",
            self._handle_submit,
            self._validate_submit,
        )
        self.protocol.register_operation(
            "review_knowledge",
            self._handle_review,
            self._validate_review,
        )
        self.protocol.register_operation(
            "stake_reputation",
            self._handle_stake,
            self._validate_stake,
        )

    def _validate_submit(self, state: L2State, signer: str, payload: dict) -> bool:
        # Validate knowledge submission
        required_fields = ["content_hash", "topic", "quality_score"]
        return all(f in payload for f in required_fields)

    def _handle_submit(self, state: L2State, signer: str, payload: dict) -> dict:
        # Record knowledge submission
        # Therefore, all submissions are permanently recorded on Hive
        submission_id = f"{signer}:{payload['content_hash'][:16]}"
        # Track submission in state (would be persisted to a database)
        return {
            "submission_id": submission_id,
            "contributor": signer,
            "topic": payload["topic"],
        }

    def _validate_review(self, state: L2State, signer: str, payload: dict) -> bool:
        return "submission_id" in payload and "score" in payload

    def _handle_review(self, state: L2State, signer: str, payload: dict) -> dict:
        return {"reviewer": signer, "submission_id": payload["submission_id"]}

    def _validate_stake(self, state: L2State, signer: str, payload: dict) -> bool:
        return "amount" in payload and payload["amount"] > 0

    def _handle_stake(self, state: L2State, signer: str, payload: dict) -> dict:
        state.balances[signer] += payload["amount"]
        return {"new_balance": state.balances[signer]}
```

### HAF (Hive Application Framework) Indexing

**HAF** provides a PostgreSQL-based framework for indexing Hive blockchain data. **Because** replaying 80M+ blocks is time-consuming, HAF maintains a synchronized database that L2 protocols can query efficiently.

```python
class HAFIndexer:
    # Indexes custom_json operations into PostgreSQL via HAF
    # Best practice: use HAF's block processing hooks for efficient indexing
    # Trade-off: HAF adds infrastructure complexity but provides SQL queryability

    def __init__(self, db_connection, protocol_id: str):
        self.db = db_connection
        self.protocol_id = protocol_id

    async def setup_tables(self):
        # Create tables for indexing protocol operations
        await self.db.execute(
            "CREATE TABLE IF NOT EXISTS protocol_operations ("
            "  id SERIAL PRIMARY KEY,"
            "  block_num BIGINT NOT NULL,"
            "  tx_id VARCHAR(40) NOT NULL,"
            "  signer VARCHAR(16) NOT NULL,"
            "  action VARCHAR(64) NOT NULL,"
            "  payload JSONB NOT NULL,"
            "  processed_at TIMESTAMP DEFAULT NOW(),"
            "  status VARCHAR(16) DEFAULT 'pending'"
            ")"
        )
        await self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ops_block "
            "ON protocol_operations(block_num)"
        )
        await self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ops_signer "
            "ON protocol_operations(signer)"
        )
        await self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ops_action "
            "ON protocol_operations(action)"
        )

    async def index_block(self, block: dict):
        # Process and store all matching operations from a block
        # However, indexing must be idempotent for replay safety
        block_num = block["block_num"]

        # Check if already indexed (idempotent)
        existing = await self.db.fetchval(
            "SELECT COUNT(*) FROM protocol_operations WHERE block_num = $1",
            block_num,
        )
        if existing > 0:
            return  # Already indexed

        for tx in block.get("transactions", []):
            tx_id = tx.get("transaction_id", "")
            for op_type, op_data in tx.get("operations", []):
                if op_type != "custom_json" or op_data.get("id") != self.protocol_id:
                    continue

                try:
                    payload = json.loads(op_data["json"])
                    signer = (
                        op_data.get("required_posting_auths", [None])[0]
                        or op_data.get("required_auths", [None])[0]
                    )
                    await self.db.execute(
                        "INSERT INTO protocol_operations "
                        "(block_num, tx_id, signer, action, payload) "
                        "VALUES ($1, $2, $3, $4, $5)",
                        block_num, tx_id, signer,
                        payload.get("action", "unknown"),
                        json.dumps(payload),
                    )
                except (json.JSONDecodeError, KeyError):
                    continue

    async def get_contributor_stats(self, account: str) -> dict:
        # Query aggregated stats for a contributor
        # Common mistake: scanning the entire operations table without indexes
        submissions = await self.db.fetchval(
            "SELECT COUNT(*) FROM protocol_operations "
            "WHERE signer = $1 AND action = 'submit_knowledge'",
            account,
        )
        reviews = await self.db.fetchval(
            "SELECT COUNT(*) FROM protocol_operations "
            "WHERE signer = $1 AND action = 'review_knowledge'",
            account,
        )
        return {
            "account": account,
            "submissions": submissions,
            "reviews": reviews,
        }
```

### Key Takeaways

- **Custom JSON operations** are feeless (only require RC) — **because** they don't transfer value, they only record data, making them ideal for social and gaming protocols
- **Layer-2 determinism** is critical — every node must arrive at the same state, **therefore** never use non-deterministic operations (random, system time) in state transitions
- **Common mistake**: using active authority for social operations — **best practice** is posting authority for non-financial actions (lower risk if key is compromised)
- **HAF indexing** enables SQL queries over blockchain data — the **trade-off** is additional infrastructure vs. query flexibility
- **Pitfall**: exceeding the 8192-byte JSON limit — always validate payload size before broadcasting
- **However**, Hive's consensus-optional model means L2 protocols must validate operations themselves — unlike smart contracts, there's no on-chain enforcement
"""
    ),
    (
        "hive-blockchain/content-rewards-tokenomics",
        r"""Explain Hive blockchain content reward mechanics including the reward pool algorithm, curation reward distribution, vote weight and mana system, beneficiary routing, and economic incentive design for decentralized content platforms.""",
        r"""## Hive Content Rewards: Reward Pool, Curation, and Tokenomic Incentive Design

**Hive's reward system** distributes new tokens to content creators and curators through a unique **Proof-of-Brain** mechanism. Unlike proof-of-work mining, Hive uses stakeholder voting to allocate rewards — users with more HIVE Power (staked HIVE) have proportionally more influence over reward distribution. **However**, this creates complex game-theoretic dynamics around vote timing, self-voting, and delegation markets. Understanding these mechanics is essential **because** they underpin the economic sustainability of decentralized content platforms.

### Reward Pool Mechanics

The **reward pool** grows by a fixed inflation rate (~0.97 HBD per block, decreasing yearly). Posts and comments compete for shares of this pool through voting. The **trade-off** is between rewarding quality content and preventing gaming by wealthy stakeholders.

```python
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timedelta
import math

@dataclass
class Vote:
    voter: str
    weight: int       # -10000 to 10000 (percentage * 100)
    rshares: int      # reward shares (stake * weight * remaining_mana)
    timestamp: datetime
    is_curation: bool = True

@dataclass
class Post:
    author: str
    permlink: str
    created: datetime
    total_rshares: int = 0
    net_rshares: int = 0       # positive - negative votes
    abs_rshares: int = 0       # |positive| + |negative|
    votes: list[Vote] = field(default_factory=list)
    beneficiaries: list[tuple[str, int]] = field(default_factory=list)  # (account, weight_bps)
    payout_at: Optional[datetime] = None
    is_paid_out: bool = False

    def __post_init__(self):
        if self.payout_at is None:
            self.payout_at = self.created + timedelta(days=7)

class RewardCalculator:
    # Calculates post rewards from the reward pool
    # Best practice: understand the non-linear reward curve
    # Common mistake: assuming linear relationship between votes and rewards

    def __init__(self, reward_fund: float, recent_claims: int):
        self.reward_fund = reward_fund    # total HIVE in reward pool
        self.recent_claims = recent_claims  # sum of all pending rshares^2
        self.hbd_print_rate = 10000        # 100% HBD printing

    def calculate_payout(self, post: Post) -> dict:
        if post.net_rshares <= 0:
            return {"total": 0, "author_hbd": 0, "author_hp": 0, "curators": 0}

        # Reward curve: convergent linear (post-HF25)
        # claims = rshares * rshares / (rshares + 2*s)
        # where s is a parameter that reduces dust rewards
        # Therefore, small posts get proportionally less than large ones
        # However, the curve is less aggressive than the old quadratic curve
        s = 2 ** 17  # ~131072, the convergent linear parameter
        claims = (post.net_rshares * post.net_rshares) / (post.net_rshares + 2 * s)

        # Post's share of the reward pool
        # Pitfall: not accounting for the ratio between claims and recent_claims
        if self.recent_claims == 0:
            return {"total": 0, "author_hbd": 0, "author_hp": 0, "curators": 0}

        payout = self.reward_fund * claims / self.recent_claims

        # Split: 50% to curators, 50% to author (configurable per post)
        curation_share = payout * 0.50
        author_share = payout * 0.50

        # Author can receive 50% HBD + 50% HIVE Power
        # or 100% HIVE Power (decline payout or power up 100%)
        author_hbd = author_share * 0.50
        author_hp = author_share * 0.50

        # Apply beneficiaries (deducted from author's share)
        beneficiary_total = 0
        for account, weight_bps in post.beneficiaries:
            beneficiary_total += author_share * weight_bps / 10000

        author_total = author_share - beneficiary_total

        return {
            "total": payout,
            "author_hbd": author_total * 0.50,
            "author_hp": author_total * 0.50,
            "curators": curation_share,
            "beneficiaries": beneficiary_total,
        }

class VotingManaSystem:
    # Hive voting mana (previously "voting power")
    # Regenerates 20% per day, full mana = 10000 basis points
    # Trade-off: vote more frequently with less weight, or less frequently with more impact

    FULL_MANA = 10000
    REGEN_RATE = 20  # percent per day

    def __init__(self, account: str, vesting_shares: int):
        self.account = account
        self.vesting_shares = vesting_shares
        self.current_mana = self.FULL_MANA
        self.last_vote_time = datetime.utcnow()

    def get_current_mana(self) -> int:
        # Mana regenerates linearly over time
        elapsed = (datetime.utcnow() - self.last_vote_time).total_seconds()
        regen = int(elapsed * self.FULL_MANA * self.REGEN_RATE / 100 / 86400)
        return min(self.FULL_MANA, self.current_mana + regen)

    def calculate_vote_rshares(self, weight_percent: int) -> int:
        # rshares = vesting_shares * current_mana * vote_weight / (FULL_MANA * FULL_MANA)
        # Therefore, a 100% upvote at full mana uses the maximum possible rshares
        # Best practice: large stakeholders should spread votes across many posts
        effective_mana = self.get_current_mana()
        rshares = (
            self.vesting_shares * effective_mana * abs(weight_percent)
        ) // (self.FULL_MANA * self.FULL_MANA)

        # Consume mana proportional to vote weight
        mana_consumed = (effective_mana * abs(weight_percent)) // self.FULL_MANA
        self.current_mana = effective_mana - mana_consumed
        self.last_vote_time = datetime.utcnow()

        return rshares if weight_percent > 0 else -rshares
```

### Curation Reward Distribution

**Curation rewards** incentivize early discovery of quality content. Curators who vote early on posts that later become popular receive more curation rewards.

```python
class CurationCalculator:
    # Distributes curation rewards among voters
    # Early voters get more rewards (incentivizes content discovery)
    # However, this creates a game where bots try to front-run human curators
    # Common mistake: voting at exactly 0 minutes (bot behavior, often penalized)

    def distribute_curation(self, post: Post, total_curation: float) -> dict[str, float]:
        if not post.votes or total_curation <= 0:
            return {}

        # Filter to positive votes only (downvotes don't earn curation)
        positive_votes = [v for v in post.votes if v.rshares > 0]
        if not positive_votes:
            return {}

        # Sort by timestamp (earlier voters get more weight)
        positive_votes.sort(key=lambda v: v.timestamp)

        # Curation reward formula: each voter gets proportional share
        # based on their rshares relative to total rshares at time of vote
        # Trade-off: this rewards early discovery but also enables front-running
        payouts = {}
        running_rshares = 0

        for vote in positive_votes:
            # Weight based on: vote_rshares / sqrt(total_rshares_at_vote_time + vote_rshares)
            # Therefore, early voters on posts with few existing votes get more
            old_weight = self._claim_weight(running_rshares)
            running_rshares += vote.rshares
            new_weight = self._claim_weight(running_rshares)

            # This voter's curation claim
            claim = new_weight - old_weight
            payouts[vote.voter] = claim

        # Normalize to total curation amount
        total_claims = sum(payouts.values())
        if total_claims > 0:
            for voter in payouts:
                payouts[voter] = (payouts[voter] / total_claims) * total_curation

        return payouts

    def _claim_weight(self, rshares: int) -> float:
        # Square root curve: diminishing returns for later voters
        # Pitfall: the exact curve changed across hard forks
        # Best practice: always check current HF parameters
        if rshares <= 0:
            return 0
        return math.sqrt(float(rshares))

class BeneficiaryRouter:
    # Routes a portion of author rewards to specified accounts
    # Used for: app fees, referral programs, community funds, DAO treasury
    # Best practice: be transparent about beneficiary settings

    MAX_BENEFICIARIES = 8
    MAX_TOTAL_WEIGHT = 10000  # 100% in basis points

    def __init__(self):
        self.routes: list[tuple[str, int]] = []

    def add_beneficiary(self, account: str, weight_bps: int):
        # Weight in basis points: 1000 = 10%, 5000 = 50%
        if len(self.routes) >= self.MAX_BENEFICIARIES:
            raise ValueError(f"Max {self.MAX_BENEFICIARIES} beneficiaries")

        total = sum(w for _, w in self.routes) + weight_bps
        if total > self.MAX_TOTAL_WEIGHT:
            raise ValueError(f"Total weight {total} exceeds maximum {self.MAX_TOTAL_WEIGHT}")

        # Common mistake: beneficiaries must be sorted alphabetically
        # because Hive consensus requires deterministic ordering
        self.routes.append((account, weight_bps))
        self.routes.sort(key=lambda x: x[0])

    def distribute(self, author_payout: float) -> dict[str, float]:
        # Calculate each beneficiary's share
        distribution = {}
        remaining = author_payout

        for account, weight_bps in self.routes:
            share = author_payout * weight_bps / 10000
            distribution[account] = share
            remaining -= share

        distribution["_author"] = remaining
        return distribution

    def to_operation_data(self) -> list[dict]:
        # Format for inclusion in comment_options operation
        # However, beneficiaries must be set before any votes are cast
        return [{"account": acct, "weight": w} for acct, w in self.routes]
```

### Key Takeaways

- **Proof-of-Brain** allocates new tokens based on stakeholder voting — the **trade-off** is between democratic content discovery and plutocratic influence
- The **convergent linear reward curve** reduces dust rewards — **therefore** very small votes produce minimal payouts, discouraging spam
- **Curation rewards** incentivize early voting — **however** this creates front-running incentives that bots exploit (a **common mistake** is voting at 0 seconds)
- **Voting mana** regenerates 20% per day — **best practice** is spreading votes across posts rather than using all mana on one post
- **Beneficiary routing** enables revenue sharing — **pitfall**: beneficiaries must be alphabetically sorted and set before any votes
- **Because** Hive has zero fees, anti-spam relies on the RC (Resource Credit) system — accounts with more staked HIVE can transact more frequently
"""
    ),
]
