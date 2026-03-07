"""
Hive blockchain thinking pairs - transaction design decisions
"""

pairs = [
    {
        "instruction": r'''I need to post an article on Hive and also set beneficiaries and vote on it in the same transaction. Should I batch these into one transaction or send them separately with beem?''',
        "output": r'''<think>
Hmm, let me think about this carefully. The user wants to post, set beneficiaries, and self-vote -- three operations in one go. With beem you can use TransactionBuilder to batch multiple operations into a single transaction. But wait, actually beneficiaries are set via comment_options which must be in the same transaction as the comment (post) operation, or at least broadcast before any votes. If you send them separately, there is a race condition where someone could vote before comment_options is applied, and the beneficiary split would not apply to that vote.

So batching is not just a convenience here -- it is a correctness requirement. Could I do them as separate transactions? Technically yes, but the window between the post broadcast and the comment_options broadcast could let votes slip through without beneficiary routing. The tradeoff is that a single larger transaction uses slightly more RC, but it guarantees atomicity.

I initially thought self-voting in the same transaction might cause ordering issues, but actually Hive processes operations within a transaction sequentially, so as long as comment comes first, then comment_options, then vote, it works.
</think>

You should batch all three into a single transaction. This is not just an optimization -- it is required for correctness when using beneficiaries. Here is how to do it with beem:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import (
    Comment, Comment_options, Vote
)
import json
from datetime import datetime

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)

author = "youraccount"
permlink = f"my-post-{datetime.now().strftime('%Y%m%d%H%M%S')}"
parent_permlink = "hive-dev"  # community tag

tx = TransactionBuilder(blockchain_instance=hive)

# Operation 1: The post itself
comment_op = Comment(**{
    "parent_author": "",
    "parent_permlink": parent_permlink,
    "author": author,
    "permlink": permlink,
    "title": "My Hive Development Post",
    "body": "Content of the post goes here...",
    "json_metadata": json.dumps({
        "tags": ["hive-dev", "python", "beem"],
        "app": "myapp/1.0"
    })
})
tx.appendOps(comment_op)

# Operation 2: Set beneficiaries (MUST be in same tx)
comment_options_op = Comment_options(**{
    "author": author,
    "permlink": permlink,
    "max_accepted_payout": "1000000.000 HBD",
    "percent_hbd": 10000,
    "allow_votes": True,
    "allow_curation_rewards": True,
    "extensions": [[0, {
        "beneficiaries": [
            {"account": "beneficiary1", "weight": 500},
            {"account": "beneficiary2", "weight": 300}
        ]
    }]]
})
tx.appendOps(comment_options_op)

# Operation 3: Self-vote
vote_op = Vote(**{
    "voter": author,
    "author": author,
    "permlink": permlink,
    "weight": 10000  # 100%
})
tx.appendOps(vote_op)

# Sign and broadcast atomically
tx.appendSigner(author, "posting")
tx.sign()
result = tx.broadcast()
print(f"Transaction ID: {result['id']}")
```

Key points:
- Operations execute in order within the transaction, so comment must come before comment_options and vote
- Beneficiaries in comment_options only apply if set before or alongside the first vote
- If any operation fails, the entire transaction is rejected -- no partial state
- RC cost for a batched transaction is roughly the sum of individual costs, so there is no penalty for batching'''
    },
    {
        "instruction": r'''I am building a Hive tool that needs to delegate HP, transfer HIVE, and transfer HBD to a new user as part of onboarding. These require different key authorities. How should I structure the transactions?''',
        "output": r'''<think>
Let me think about the key authority requirements here. Delegation (delegate_vesting_shares) requires the active key. Transfer of HIVE requires the active key. Transfer of HBD also requires the active key. Wait, actually all three need the active key, so they could theoretically go in one transaction.

But hmm, should they? The tradeoff is atomicity vs error recovery. If I batch them into one transaction and, say, the delegation fails because the user does not have enough HP, then none of the transfers happen either. That might not be what we want -- maybe we still want the HIVE and HBD to arrive even if delegation fails.

I initially thought splitting them would be safer, but actually for an onboarding flow, it is better if it is all-or-nothing. If the delegation fails, you probably want to investigate before sending tokens. A partial onboarding where only some assets arrive would be confusing.

Could be worth doing a pre-check though -- verify the account has enough liquid HIVE, enough HP to delegate, and enough HBD before building the transaction. That way failures at broadcast time are rare.
</think>

Since all three operations require the active key, you can batch them into a single atomic transaction. For onboarding, all-or-nothing is usually the right choice:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import (
    Transfer, Delegate_vesting_shares
)
from beem.amount import Amount

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)

def onboard_user(sponsor, new_user, hive_amount="5.000 HIVE",
                 hbd_amount="3.000 HBD", hp_delegation_vests="10000.000000 VESTS"):
    """Send HIVE, HBD, and delegate HP in one atomic transaction."""

    # Pre-flight checks to catch errors before broadcast
    sponsor_acc = Account(sponsor, blockchain_instance=hive)
    balance_hive = sponsor_acc.get_balance("available", "HIVE")
    balance_hbd = sponsor_acc.get_balance("available", "HBD")
    available_vests = float(sponsor_acc.get_balance("available", "VESTS"))

    needed_vests = float(Amount(hp_delegation_vests))
    if available_vests < needed_vests:
        raise ValueError(
            f"Not enough undelegated VESTS: have {available_vests:.6f}, "
            f"need {needed_vests:.6f}"
        )

    # Verify target account exists
    try:
        Account(new_user, blockchain_instance=hive)
    except Exception:
        raise ValueError(f"Account @{new_user} does not exist")

    tx = TransactionBuilder(blockchain_instance=hive)

    # Transfer HIVE
    tx.appendOps(Transfer(**{
        "from": sponsor,
        "to": new_user,
        "amount": hive_amount,
        "memo": "Welcome to Hive! Here is some HIVE to get started."
    }))

    # Transfer HBD
    tx.appendOps(Transfer(**{
        "from": sponsor,
        "to": new_user,
        "amount": hbd_amount,
        "memo": "Welcome to Hive! Here is some HBD."
    }))

    # Delegate HP (as VESTS)
    tx.appendOps(Delegate_vesting_shares(**{
        "delegator": sponsor,
        "delegatee": new_user,
        "vesting_shares": hp_delegation_vests
    }))

    tx.appendSigner(sponsor, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Onboarding transaction: {result['id']}")
    return result

# Usage
onboard_user("myaccount", "newuser123")
```

Pre-flight checks prevent most broadcast failures. If the transaction still fails (e.g., network issue), nothing is applied -- you can safely retry the entire batch.'''
    },
    {
        "instruction": r'''My Hive bot does 50+ custom_json operations per hour. Each one costs RC. Should I batch them into fewer, larger transactions to save RC, or keep them individual?''',
        "output": r'''<think>
Okay, RC cost optimization for custom_json. Let me think about how RC costs work on Hive. Each transaction has a base cost (for the transaction envelope, signatures, etc.) plus a per-operation cost based on the size of the operation data. So batching multiple custom_json ops into one transaction would save the per-transaction overhead.

But wait, actually there is a complication. Custom_json has a size limit -- the json field can be at most 8192 bytes per operation. And a transaction itself has a maximum size too (65536 bytes). So you could fit maybe 7-8 custom_json ops in one transaction before hitting the transaction size limit.

Hmm, but there is another tradeoff I should consider. If you batch operations and the transaction fails, all operations fail. With individual transactions, a failure is isolated. For a bot doing 50+ ops per hour, that is roughly one every 72 seconds. Batching every 5-10 minutes would group about 4-8 operations together.

I initially thought the RC savings would be huge, but let me reconsider. The base transaction cost is about 1% of a typical custom_json RC cost. So batching 5 ops saves maybe 4-5% RC total. Not massive. The real benefit is reducing the number of transactions the node has to process, which is more about being a good network citizen than saving RC.

Actually, because each transaction needs a signature verification on the witness nodes, reducing transaction count does help network throughput. So there are benefits beyond just RC.
</think>

Batching saves some RC but the main benefit is reducing network load. Here is a practical approach:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json
import time
from threading import Lock

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)

class BatchedCustomJson:
    """Accumulate custom_json ops and flush periodically."""

    MAX_BATCH_SIZE = 6       # stay under tx size limit
    FLUSH_INTERVAL = 300     # flush every 5 minutes
    MAX_JSON_BYTES = 8192    # per-operation limit

    def __init__(self, account, blockchain_instance=None):
        self.account = account
        self.hive = blockchain_instance or hive
        self.pending = []
        self.lock = Lock()
        self.last_flush = time.time()

    def add(self, op_id, payload, required_posting_auths=None):
        """Queue a custom_json operation for batched broadcast."""
        json_str = json.dumps(payload, separators=(",", ":"))
        if len(json_str.encode("utf-8")) > self.MAX_JSON_BYTES:
            raise ValueError(
                f"JSON payload is {len(json_str)} bytes, "
                f"max is {self.MAX_JSON_BYTES}"
            )

        op = Custom_json(**{
            "required_auths": [],
            "required_posting_auths": required_posting_auths or [self.account],
            "id": op_id,
            "json": json_str
        })

        with self.lock:
            self.pending.append(op)

            if (len(self.pending) >= self.MAX_BATCH_SIZE or
                    time.time() - self.last_flush > self.FLUSH_INTERVAL):
                return self._flush()
        return None

    def _flush(self):
        """Broadcast all pending ops in one transaction."""
        if not self.pending:
            return None

        ops = self.pending[:]
        self.pending.clear()
        self.last_flush = time.time()

        tx = TransactionBuilder(blockchain_instance=self.hive)
        for op in ops:
            tx.appendOps(op)
        tx.appendSigner(self.account, "posting")
        tx.sign()

        try:
            result = tx.broadcast()
            print(f"Flushed {len(ops)} ops in tx {result['id']}")
            return result
        except Exception as e:
            # On failure, fall back to individual broadcasts
            print(f"Batch failed: {e}, retrying individually")
            for op in ops:
                try:
                    single_tx = TransactionBuilder(blockchain_instance=self.hive)
                    single_tx.appendOps(op)
                    single_tx.appendSigner(self.account, "posting")
                    single_tx.sign()
                    single_tx.broadcast()
                except Exception as inner_e:
                    print(f"Individual op failed: {inner_e}")
            return None

    def force_flush(self):
        """Flush remaining ops (call on shutdown)."""
        with self.lock:
            return self._flush()


# Usage
batcher = BatchedCustomJson("mybot")

# These accumulate and auto-flush
batcher.add("myapp_action", {"type": "follow", "target": "user1"})
batcher.add("myapp_action", {"type": "reblog", "post": "@author/permlink"})

# On shutdown
batcher.force_flush()
```

RC savings per batch of 6: roughly 5% vs individual transactions. The bigger win is reducing witness processing load and avoiding rate-limiting from API nodes that throttle per-transaction.'''
    },
    {
        "instruction": r'''My multi-step Hive operation sometimes fails partway through: I post, then set beneficiaries in a second transaction, then vote. If the beneficiary tx fails, I have a post without beneficiaries. How do I handle error recovery?''',
        "output": r'''<think>
Wait, actually the first question I should ask is: why are these separate transactions at all? Beneficiaries via comment_options MUST be set before any vote is cast, and ideally in the same transaction as the post. The user has a design problem, not just an error recovery problem.

But let me think about this more broadly -- what if they have a legitimate reason for multi-step transactions? Maybe they are using different keys, or the operations are conditional on some external check between steps.

Hmm, for the specific case of post + beneficiaries + vote, these all use the posting key, so there is no key-authority reason to split them. The right fix is to batch them. But I should also address the general pattern of error recovery for cases where batching is not possible.

For the general case, you need an idempotent retry mechanism. The challenge with blockchain is that a transaction might have been included in a block even if the API returned an error (network timeout, node issue). So before retrying, you need to check whether the operation actually landed on-chain.

I initially thought you could just retry blindly, but that could lead to duplicate posts or double votes. You need to verify on-chain state before each retry.
</think>

The root cause is that post + comment_options + vote should be a single atomic transaction (they all need the posting key). But for the general pattern of multi-step error recovery on Hive, here is a robust approach:

```python
from beem import Hive
from beem.comment import Comment
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import (
    Comment as CommentOp, Comment_options, Vote
)
import json
import time
from datetime import datetime

hive = Hive(
    node=[
        "https://api.hive.blog",
        "https://api.deathwing.me",
        "https://api.openhive.network"
    ],
    keys=["5YourPostingKey"]
)

# SOLUTION 1: Batch into one transaction (preferred)
def post_with_beneficiaries_atomic(author, title, body, beneficiaries,
                                    tags, self_vote_weight=10000):
    """Post, set beneficiaries, and vote atomically."""
    permlink = f"{title.lower().replace(' ', '-')[:200]}-{int(time.time())}"

    tx = TransactionBuilder(blockchain_instance=hive)

    tx.appendOps(CommentOp(**{
        "parent_author": "",
        "parent_permlink": tags[0],
        "author": author,
        "permlink": permlink,
        "title": title,
        "body": body,
        "json_metadata": json.dumps({"tags": tags, "app": "myapp/1.0"})
    }))

    tx.appendOps(Comment_options(**{
        "author": author,
        "permlink": permlink,
        "max_accepted_payout": "1000000.000 HBD",
        "percent_hbd": 10000,
        "allow_votes": True,
        "allow_curation_rewards": True,
        "extensions": [[0, {"beneficiaries": beneficiaries}]]
    }))

    if self_vote_weight > 0:
        tx.appendOps(Vote(**{
            "voter": author,
            "author": author,
            "permlink": permlink,
            "weight": self_vote_weight
        }))

    tx.appendSigner(author, "posting")
    tx.sign()
    return tx.broadcast()


# SOLUTION 2: When you genuinely need multi-step with recovery
class HiveMultiStepTransaction:
    """Execute multi-step operations with on-chain verification."""

    def __init__(self, blockchain_instance):
        self.hive = blockchain_instance
        self.completed_steps = []

    def _verify_post_exists(self, author, permlink):
        """Check if a post landed on-chain."""
        try:
            c = Comment(f"@{author}/{permlink}",
                       blockchain_instance=self.hive)
            c.refresh()
            return True
        except Exception:
            return False

    def _verify_vote_exists(self, voter, author, permlink):
        """Check if a vote landed on-chain."""
        try:
            c = Comment(f"@{author}/{permlink}",
                       blockchain_instance=self.hive)
            c.refresh()
            for v in c.get("active_votes", []):
                if v["voter"] == voter:
                    return True
            return False
        except Exception:
            return False

    def execute_with_recovery(self, author, permlink, steps):
        """Run steps with verification between each.

        Each step is a dict with:
          - name: human-readable step name
          - build_tx: callable that returns a TransactionBuilder
          - verify: callable that returns True if step succeeded
          - can_skip: whether to continue if step fails
        """
        for step in steps:
            # Check if already done (idempotency)
            if step["verify"]():
                print(f"Step '{step['name']}' already completed, skipping")
                self.completed_steps.append(step["name"])
                continue

            retries = 3
            success = False
            for attempt in range(retries):
                try:
                    tx = step["build_tx"]()
                    tx.broadcast()
                    # Wait for block confirmation
                    time.sleep(4)
                    if step["verify"]():
                        success = True
                        self.completed_steps.append(step["name"])
                        break
                    else:
                        print(f"Step '{step['name']}' broadcast OK "
                              f"but not confirmed, retry {attempt+1}")
                except Exception as e:
                    print(f"Step '{step['name']}' failed: {e}")
                    # Check if it actually went through despite error
                    time.sleep(4)
                    if step["verify"]():
                        success = True
                        self.completed_steps.append(step["name"])
                        break

            if not success and not step.get("can_skip"):
                raise RuntimeError(
                    f"Step '{step['name']}' failed after {retries} retries. "
                    f"Completed: {self.completed_steps}"
                )

        return self.completed_steps
```

The key insight: always verify on-chain state before retrying. A transaction might succeed even if the API returns an error (timeout, node crash). Blind retries can create duplicate posts or conflicting operations.'''
    },
    {
        "instruction": r'''I want to do a large airdrop on Hive -- sending tokens to 500 accounts. What is the best transaction strategy considering RC costs and reliability?''',
        "output": r'''<think>
Okay, 500 transfers is a lot. Let me think about the constraints. Each transfer operation requires the active key. A single Hive transaction can contain multiple operations, but there is a transaction size limit of 65536 bytes. Each transfer op is roughly 150-200 bytes, so I could fit maybe 300+ transfers in one transaction. But wait, actually that would be a massive transaction and could be rejected by nodes or cause timeout issues.

Hmm, the RC cost is also a concern. 500 transfers will consume significant RC. Let me think about what a typical transfer costs in RC terms... roughly 1-2 billion RC per transfer. With 500 transfers, you would need substantial HP staked. A new account could not do this.

I initially thought batching everything into a few large transactions would be optimal, but there is a reliability tradeoff. If a transaction with 100 transfers fails, you lose all 100 and have to figure out which ones need retrying. With smaller batches of 10-20, a failure affects fewer recipients.

Could also consider using Hive Engine for the airdrop if these are custom tokens -- that uses custom_json which is cheaper on RC. But the user said "tokens" which might mean HIVE/HBD native transfers.

The tradeoff is: bigger batches = less RC overhead from transaction envelopes, but more risk per failure. I think batches of 20-30 transfers each is a good sweet spot. That gives you about 17-25 transactions total, manageable error handling, and reasonable RC savings.

Actually, I should also think about rate limiting. API nodes may throttle if you broadcast 25 transactions in rapid succession. Need a delay between batches.
</think>

For a 500-account airdrop, use batched transactions of 20-25 transfers each with progress tracking and retry logic:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer
import json
import time
import os

hive = Hive(
    node=[
        "https://api.hive.blog",
        "https://api.deathwing.me",
        "https://api.openhive.network"
    ],
    keys=["5YourActiveKey"]
)

BATCH_SIZE = 20
DELAY_BETWEEN_BATCHES = 6  # seconds, avoid rate limiting
PROGRESS_FILE = "airdrop_progress.json"


def load_progress():
    """Load previously completed transfers for resumability."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {"completed": [], "failed": []}


def save_progress(progress):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def check_rc_budget(account_name, num_remaining):
    """Verify we have enough RC to complete the airdrop."""
    acc = Account(account_name, blockchain_instance=hive)
    current_mana = acc.get_rc_manabar()
    current_rc = current_mana["current_mana"]
    # Rough estimate: 1.5 billion RC per transfer
    estimated_cost = num_remaining * 1_500_000_000
    if current_rc < estimated_cost:
        pct = (current_rc / estimated_cost) * 100
        print(f"WARNING: RC may run out. Have enough for ~{pct:.0f}% "
              f"of remaining transfers.")
        print(f"Current RC: {current_rc:,.0f}")
        print(f"Estimated need: {estimated_cost:,.0f}")
        return False
    return True


def execute_airdrop(sender, recipients, amount="1.000 HIVE", memo="Airdrop!"):
    """Execute airdrop with batching, progress tracking, and retry.

    recipients: list of account name strings
    """
    progress = load_progress()
    completed_set = set(progress["completed"])

    # Filter out already-completed recipients
    remaining = [r for r in recipients if r not in completed_set]
    print(f"Total: {len(recipients)}, Already done: {len(completed_set)}, "
          f"Remaining: {len(remaining)}")

    if not remaining:
        print("Airdrop already complete!")
        return progress

    # RC budget check
    check_rc_budget(sender, len(remaining))

    # Split into batches
    batches = []
    for i in range(0, len(remaining), BATCH_SIZE):
        batches.append(remaining[i:i + BATCH_SIZE])

    print(f"Processing {len(batches)} batches of up to {BATCH_SIZE}")

    for batch_idx, batch in enumerate(batches):
        print(f"\nBatch {batch_idx + 1}/{len(batches)} "
              f"({len(batch)} transfers)")

        tx = TransactionBuilder(blockchain_instance=hive)
        for recipient in batch:
            tx.appendOps(Transfer(**{
                "from": sender,
                "to": recipient,
                "amount": amount,
                "memo": memo
            }))
        tx.appendSigner(sender, "active")
        tx.sign()

        retries = 3
        for attempt in range(retries):
            try:
                result = tx.broadcast()
                print(f"  TX: {result['id']}")
                # Mark all in batch as completed
                progress["completed"].extend(batch)
                save_progress(progress)
                break
            except Exception as e:
                err_str = str(e)
                if "not enough RC" in err_str.lower():
                    print(f"  RC exhausted. Stopping. Resume later.")
                    save_progress(progress)
                    return progress
                print(f"  Attempt {attempt+1} failed: {err_str}")
                if attempt == retries - 1:
                    # Fall back to individual transfers
                    print(f"  Batch failed, trying individually...")
                    for recipient in batch:
                        try:
                            single_tx = TransactionBuilder(
                                blockchain_instance=hive)
                            single_tx.appendOps(Transfer(**{
                                "from": sender,
                                "to": recipient,
                                "amount": amount,
                                "memo": memo
                            }))
                            single_tx.appendSigner(sender, "active")
                            single_tx.sign()
                            single_tx.broadcast()
                            progress["completed"].append(recipient)
                        except Exception as inner_e:
                            print(f"    Failed for {recipient}: {inner_e}")
                            progress["failed"].append(recipient)
                    save_progress(progress)
                time.sleep(3)

        time.sleep(DELAY_BETWEEN_BATCHES)

    print(f"\nAirdrop complete. Success: {len(progress['completed'])}, "
          f"Failed: {len(progress['failed'])}")
    return progress


# Usage
recipients = ["user1", "user2", "user3"]  # load your 500 accounts
execute_airdrop("airdrop-account", recipients, amount="10.000 HIVE")
```

Design decisions: batch size of 20 balances RC efficiency against failure blast radius. Progress file enables resuming after RC exhaustion or crashes. Individual fallback ensures partial batch failures do not lose the whole batch.'''
    },
]
