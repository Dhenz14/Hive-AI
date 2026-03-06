"""Hive blockchain training pairs: real-time streaming and block monitoring."""

PAIRS = [
    (
        "hive/stream-blocks-python",
        r'''How do I stream blocks from the Hive blockchain in real-time using Python? Show both operation-level and block-level streaming.''',
        r'''Streaming blocks from Hive in real-time is the foundation for building indexers, bots, and real-time applications. Here are multiple approaches using beem:

```python
from beem import Hive
from beem.blockchain import Blockchain
import json
import time

hive = Hive(node=[
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://api.openhive.network"
])
blockchain = Blockchain(hive_instance=hive)

# Approach 1: Stream individual operations
def stream_operations(op_types=None, start_block=None):
    """Stream operations filtered by type.

    Args:
        op_types: List of operation names to filter, e.g. ["transfer", "vote"]
                  None means all operations
        start_block: Block number to start from (None = head block)
    """
    stream = blockchain.stream(
        opNames=op_types,
        start=start_block,
        raw_ops=False,
        threading=False,
        max_batch_size=50
    )

    for op in stream:
        op_type = op.get("type", "unknown")
        block_num = op.get("block_num", "?")
        timestamp = op.get("timestamp", "?")
        print(f"[{block_num}] {timestamp} {op_type}: {json.dumps(op, indent=2)[:200]}")
        yield op

# Approach 2: Stream full blocks
def stream_blocks(start_block=None):
    """Stream complete blocks with all transactions."""
    stream = blockchain.blocks(
        start=start_block,
        threading=False,
        max_batch_size=50
    )

    for block in stream:
        block_num = block.get("block_num", block.get("block_id", "?"))
        witness = block.get("witness", "?")
        tx_count = len(block.get("transactions", []))
        op_count = sum(
            len(tx.get("operations", []))
            for tx in block.get("transactions", [])
        )
        print(f"Block {block_num} by @{witness}: "
              f"{tx_count} txs, {op_count} ops")
        yield block

# Approach 3: Stream specific operations with processing
def stream_transfers(min_amount=0):
    """Stream and filter transfer operations."""
    stream = blockchain.stream(
        opNames=["transfer"],
        raw_ops=False,
        threading=False
    )

    for op in stream:
        amount_str = op.get("amount", "0 HIVE")
        parts = amount_str.split()
        amount = float(parts[0])
        asset = parts[1] if len(parts) > 1 else "HIVE"

        if amount >= min_amount:
            print(f"Transfer: @{op['from']} -> @{op['to']}: "
                  f"{amount:.3f} {asset}")
            if op.get("memo"):
                print(f"  Memo: {op['memo'][:100]}")
            yield op

# Approach 4: Stream with error recovery
def resilient_stream(op_types=None, checkpoint_file="checkpoint.txt"):
    """Stream with automatic reconnection and checkpointing."""
    # Load last processed block
    try:
        with open(checkpoint_file, "r") as f:
            start_block = int(f.read().strip())
        print(f"Resuming from block {start_block}")
    except (FileNotFoundError, ValueError):
        start_block = None
        print("Starting from head block")

    while True:
        try:
            stream = blockchain.stream(
                opNames=op_types,
                start=start_block,
                raw_ops=False,
                threading=False
            )
            for op in stream:
                block_num = op.get("block_num", 0)
                # Process the operation
                yield op

                # Checkpoint every 100 blocks
                if block_num % 100 == 0:
                    with open(checkpoint_file, "w") as f:
                        f.write(str(block_num))
                    start_block = block_num

        except Exception as e:
            print(f"Stream error: {e}, reconnecting in 5s...")
            time.sleep(5)

# Usage examples:

# Stream all votes
# for op in stream_operations(["vote"]):
#     print(f"@{op['voter']} voted on @{op['author']}/{op['permlink']}")

# Stream large transfers
# for op in stream_transfers(min_amount=1000):
#     pass

# Stream full blocks
# for block in stream_blocks():
#     pass
```

Key performance tips:
- Use opNames filter to avoid processing irrelevant operations
- Use threading=False for simplicity; True for higher throughput
- Implement checkpointing to resume after crashes
- Use multiple nodes in the node list for automatic failover
- raw_ops=False gives parsed operations; True gives raw format
- max_batch_size controls how many blocks are fetched per API call
'''
    ),
    (
        "hive/stream-operations-javascript",
        r'''How do I stream operations from the Hive blockchain using JavaScript (dhive)? Show real-time monitoring with WebSocket support.''',
        r'''Here is how to stream operations in real-time using dhive in JavaScript, including both polling and WebSocket approaches:

```javascript
const dhive = require("@hiveio/dhive");

const client = new dhive.Client([
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://api.openhive.network"
]);

// Approach 1: Stream using dhive's built-in blockchain stream
async function streamOperations(opTypes = null) {
    const stream = client.blockchain.getOperationsStream();

    stream.on("data", (operation) => {
        const [opType, opData] = operation.op;

        if (opTypes && !opTypes.includes(opType)) return;

        console.log(`[Block ${operation.block_num}] ${opType}:`);
        console.log(JSON.stringify(opData, null, 2).substring(0, 200));
    });

    stream.on("error", (err) => {
        console.error("Stream error:", err.message);
    });

    return stream;
}

// Approach 2: Manual block polling with processing
async function pollBlocks(startBlock = null, callback) {
    let currentBlock = startBlock;

    if (!currentBlock) {
        const props = await client.database.getDynamicGlobalProperties();
        currentBlock = props.head_block_number;
    }

    console.log(`Starting from block ${currentBlock}`);

    while (true) {
        try {
            const props = await client.database.getDynamicGlobalProperties();
            const headBlock = props.head_block_number;

            while (currentBlock <= headBlock) {
                const block = await client.database.getBlock(currentBlock);
                if (block) {
                    for (const tx of block.transactions || []) {
                        for (const op of tx.operations || []) {
                            await callback(op[0], op[1], currentBlock, block.timestamp);
                        }
                    }
                }
                currentBlock++;
            }

            // Wait for next block (3 seconds)
            await new Promise((resolve) => setTimeout(resolve, 1000));
        } catch (err) {
            console.error("Poll error:", err.message);
            await new Promise((resolve) => setTimeout(resolve, 3000));
        }
    }
}

// Approach 3: WebSocket streaming for lowest latency
function streamViaWebSocket(wsUrl, callback) {
    const WebSocket = require("ws");
    const ws = new WebSocket(wsUrl || "wss://api.hive.blog");

    ws.on("open", () => {
        console.log("WebSocket connected");
        // Subscribe to block operations
        ws.send(JSON.stringify({
            jsonrpc: "2.0",
            method: "condenser_api.set_block_applied_callback",
            params: [0],  // 0 = head block, 1 = irreversible
            id: 1
        }));
    });

    ws.on("message", (data) => {
        try {
            const msg = JSON.parse(data.toString());
            if (msg.method === "notice" && msg.params) {
                const block = msg.params[0];
                callback(block);
            }
        } catch (err) {
            console.error("Parse error:", err.message);
        }
    });

    ws.on("error", (err) => {
        console.error("WS error:", err.message);
    });

    ws.on("close", () => {
        console.log("WS closed, reconnecting in 3s...");
        setTimeout(() => streamViaWebSocket(wsUrl, callback), 3000);
    });

    return ws;
}

// Example: Monitor specific operation types
async function monitorTransfers() {
    await pollBlocks(null, async (opType, opData, blockNum, timestamp) => {
        if (opType === "transfer") {
            const amount = opData.amount;
            const value = parseFloat(amount.split(" ")[0]);
            if (value >= 100) {
                console.log(`[${timestamp}] Large transfer: ` +
                    `@${opData.from} -> @${opData.to}: ${amount}`);
            }
        }
    });
}

// Example: Track custom_json for a specific dApp
async function monitorDApp(dappId) {
    await pollBlocks(null, async (opType, opData, blockNum, timestamp) => {
        if (opType === "custom_json" && opData.id === dappId) {
            const payload = JSON.parse(opData.json);
            const account = (opData.required_posting_auths[0] ||
                            opData.required_auths[0]);
            console.log(`[${blockNum}] ${dappId} from @${account}:`,
                        JSON.stringify(payload));
        }
    });
}

// Run
// streamOperations(["transfer", "vote"]);
// monitorTransfers();
// monitorDApp("splinterlands");
```

The polling approach gives you the most control and reliability. WebSocket streaming offers the lowest latency but requires reconnection handling. The dhive built-in stream is the simplest but may miss blocks during network issues. For production use, combine polling with checkpointing for guaranteed delivery.
'''
    ),
    (
        "hive/head-block-tracking",
        r'''How do I track the head block and irreversible block on Hive? What is the difference and why does it matter?''',
        r'''<think>
On Hive:
- Head block: the latest block produced (may be reversed in rare cases)
- Last irreversible block (LIB): the last block that cannot be reversed (confirmed by 2/3 of witnesses)

The gap between head and LIB is typically 15-20 blocks (45-60 seconds). For financial applications, you should wait for irreversibility. For social features (votes, posts), head block is usually fine.

This distinction matters for:
- Exchange deposits: must wait for irreversibility
- Bot operations: usually head block is fine
- Indexers: need to handle potential micro-forks near head
</think>

The head block and last irreversible block (LIB) serve different purposes on Hive. Here is how to track both and when each matters:

```python
from beem import Hive
from beem.blockchain import Blockchain
import time
import json

hive = Hive(node=["https://api.hive.blog", "https://api.deathwing.me"])

def get_block_status():
    """Get current head block and irreversible block info."""
    props = hive.rpc.get_dynamic_global_properties()

    head_block = props["head_block_number"]
    head_block_id = props["head_block_id"]
    lib = props["last_irreversible_block_num"]
    block_time = props["time"]
    current_witness = props["current_witness"]

    gap = head_block - lib

    print(f"Head block:         {head_block}")
    print(f"Head block ID:      {head_block_id}")
    print(f"Irreversible block: {lib}")
    print(f"Gap:                {gap} blocks (~{gap * 3}s)")
    print(f"Block time:         {block_time}")
    print(f"Current witness:    @{current_witness}")

    return head_block, lib, gap

def wait_for_irreversibility(block_num, timeout=120):
    """Wait until a specific block becomes irreversible."""
    start = time.time()
    print(f"Waiting for block {block_num} to become irreversible...")

    while True:
        props = hive.rpc.get_dynamic_global_properties()
        lib = props["last_irreversible_block_num"]

        if lib >= block_num:
            elapsed = time.time() - start
            print(f"Block {block_num} is now irreversible! "
                  f"(took {elapsed:.1f}s)")
            return True

        if time.time() - start > timeout:
            print(f"Timeout: block {block_num} not yet irreversible "
                  f"(LIB: {lib})")
            return False

        remaining = block_num - lib
        print(f"  LIB: {lib}, {remaining} blocks to go...")
        time.sleep(3)

def monitor_block_production(duration_seconds=60):
    """Monitor block production rate and witness performance."""
    blockchain = Blockchain(hive_instance=hive)
    start_time = time.time()
    block_count = 0
    witnesses_seen = {}
    last_block_num = None

    print(f"Monitoring block production for {duration_seconds}s...\n")

    for block in blockchain.blocks(threading=False):
        block_num = block.get("block_num", 0)
        witness = block.get("witness", "unknown")
        timestamp = block.get("timestamp", "?")
        tx_count = len(block.get("transactions", []))

        # Track timing
        if last_block_num is not None:
            skipped = block_num - last_block_num - 1
            if skipped > 0:
                print(f"  WARNING: {skipped} block(s) skipped!")

        witnesses_seen[witness] = witnesses_seen.get(witness, 0) + 1
        block_count += 1
        last_block_num = block_num

        print(f"  Block {block_num} by @{witness:20s} "
              f"({tx_count} txs) at {timestamp}")

        if time.time() - start_time > duration_seconds:
            break

    elapsed = time.time() - start_time
    rate = block_count / elapsed if elapsed > 0 else 0

    print(f"\nResults:")
    print(f"  Blocks seen: {block_count}")
    print(f"  Duration: {elapsed:.1f}s")
    print(f"  Rate: {rate:.2f} blocks/sec (expected: 0.33)")
    print(f"  Unique witnesses: {len(witnesses_seen)}")
    for w, count in sorted(witnesses_seen.items(),
                           key=lambda x: -x[1]):
        print(f"    @{w}: {count} blocks")

class TransactionConfirmationTracker:
    """Track transaction confirmation status."""

    def __init__(self, hive_instance):
        self.hive = hive_instance

    def confirm_transaction(self, tx_id, block_num=None):
        """Check if a transaction is confirmed and irreversible."""
        props = self.hive.rpc.get_dynamic_global_properties()
        lib = props["last_irreversible_block_num"]
        head = props["head_block_number"]

        if block_num:
            if block_num <= lib:
                return {"status": "irreversible", "block": block_num}
            elif block_num <= head:
                return {"status": "confirmed", "block": block_num,
                        "blocks_to_lib": block_num - lib}
            else:
                return {"status": "pending"}

        # Search recent blocks for the transaction
        result = self.hive.rpc.get_transaction(
            {"id": tx_id}, api="condenser_api"
        )
        if result:
            tx_block = result.get("block_num", 0)
            if tx_block <= lib:
                return {"status": "irreversible", "block": tx_block}
            return {"status": "confirmed", "block": tx_block}

        return {"status": "not_found"}

# Usage
head, lib, gap = get_block_status()
# wait_for_irreversibility(head)
# monitor_block_production(60)
```

When to use head block vs LIB:
- Head block: social operations (votes, posts, comments), UI updates, non-critical reads
- Irreversible block: exchange deposits/withdrawals, payment confirmations, financial operations
- The gap is typically 15-20 blocks (45-60 seconds) under normal conditions
- During network issues, the gap may increase, signaling consensus problems
'''
    ),
    (
        "hive/operation-filtering-patterns",
        r'''What are the most efficient patterns for filtering specific operations from the Hive blockchain stream?''',
        r'''Efficient operation filtering is crucial for building responsive Hive applications. Here are patterns ranging from simple to advanced:

```python
from beem import Hive
from beem.blockchain import Blockchain
import json
import re
from typing import Callable

hive = Hive(node=["https://api.hive.blog"])
blockchain = Blockchain(hive_instance=hive)

# Pattern 1: Simple type-based filtering (most efficient)
def filter_by_type(op_types):
    """Let the blockchain stream handle filtering (server-side)."""
    stream = blockchain.stream(
        opNames=op_types,
        raw_ops=False,
        threading=False
    )
    for op in stream:
        yield op

# Pattern 2: Account-specific filtering
def filter_by_account(accounts, op_types=None):
    """Filter operations involving specific accounts."""
    account_set = set(accounts)
    stream = blockchain.stream(
        opNames=op_types,
        raw_ops=False,
        threading=False
    )
    for op in stream:
        # Check common account fields
        involved = set()
        for field in ["author", "voter", "from", "to", "account",
                      "creator", "delegator", "delegatee"]:
            if field in op:
                involved.add(op[field])

        # Check posting/active auths for custom_json
        if op.get("type") == "custom_json":
            involved.update(op.get("required_posting_auths", []))
            involved.update(op.get("required_auths", []))

        if involved & account_set:
            yield op

# Pattern 3: Custom JSON dApp filtering with payload parsing
def filter_custom_json(dapp_ids, payload_filter=None):
    """Filter custom_json by dApp ID and optional payload criteria."""
    id_set = set(dapp_ids)
    stream = blockchain.stream(
        opNames=["custom_json"],
        raw_ops=False,
        threading=False
    )
    for op in stream:
        if op.get("id") not in id_set:
            continue
        try:
            payload = json.loads(op["json"])
        except (json.JSONDecodeError, KeyError):
            continue

        if payload_filter is None or payload_filter(payload):
            op["_parsed"] = payload
            yield op

# Pattern 4: Amount-based transfer filtering
def filter_transfers(min_amount=0, asset=None, accounts=None):
    """Filter transfers by amount, asset type, and accounts."""
    stream = blockchain.stream(
        opNames=["transfer"],
        raw_ops=False,
        threading=False
    )
    for op in stream:
        amount_str = op.get("amount", "0 HIVE")
        parts = amount_str.split()
        amount = float(parts[0])
        token = parts[1] if len(parts) > 1 else "HIVE"

        if amount < min_amount:
            continue
        if asset and token != asset:
            continue
        if accounts:
            if op["from"] not in accounts and op["to"] not in accounts:
                continue

        op["_amount"] = amount
        op["_asset"] = token
        yield op

# Pattern 5: Composable filter chain
class OperationFilter:
    """Composable filter system for operation streams."""

    def __init__(self):
        self.filters = []

    def add(self, filter_fn):
        self.filters.append(filter_fn)
        return self

    def matches(self, op):
        return all(f(op) for f in self.filters)

    def apply(self, stream):
        for op in stream:
            if self.matches(op):
                yield op

# Build complex filters
def is_whale_transfer(op):
    """Check if transfer is from a high-value account."""
    if op.get("type") != "transfer":
        return False
    amount = float(op.get("amount", "0").split()[0])
    return amount >= 10000

def is_hbd(op):
    """Check if the operation involves HBD."""
    amount_str = op.get("amount", "")
    return "HBD" in amount_str

def has_memo(op):
    """Check if transfer has a non-empty memo."""
    return bool(op.get("memo", "").strip())

# Compose filters
whale_hbd_filter = OperationFilter()
whale_hbd_filter.add(is_whale_transfer).add(is_hbd).add(has_memo)

# Pattern 6: Regex-based memo filtering
def filter_by_memo_pattern(pattern):
    """Filter transfers by memo content using regex."""
    compiled = re.compile(pattern)
    stream = blockchain.stream(
        opNames=["transfer"],
        raw_ops=False,
        threading=False
    )
    for op in stream:
        memo = op.get("memo", "")
        if compiled.search(memo):
            yield op

# Usage examples:
# Large HBD transfers with memos
# for op in whale_hbd_filter.apply(stream_operations(["transfer"])):
#     print(f"Whale: @{op['from']} -> @{op['to']}: {op['amount']}")

# Splinterlands game operations
# for op in filter_custom_json(["sm_battle"], lambda p: p.get("type") == "submit_team"):
#     print(f"Battle: {op['_parsed']}")

# Transfers mentioning "exchange"
# for op in filter_by_memo_pattern(r"exchange|deposit|withdraw"):
#     print(f"Exchange-related: {op['from']} {op['amount']}")
```

Performance tips:
- Always use opNames in the stream constructor for server-side filtering
- Build account sets for O(1) lookup instead of iterating lists
- Parse JSON payloads lazily (only when type filter passes)
- For high-throughput, process in batches rather than one-by-one
- Use compiled regex patterns for memo filtering
'''
    ),
    (
        "hive/irreversible-block-monitoring",
        r'''How do I build a reliable system that only processes irreversible blocks on Hive, suitable for exchange deposit tracking?''',
        r'''For financial applications like exchange deposit tracking, you must only process irreversible blocks to avoid double-spend scenarios from micro-forks. Here is a production-grade implementation:

```python
from beem import Hive
from beem.blockchain import Blockchain
import json
import time
import logging
import sqlite3
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("irrev_monitor")

class IrreversibleBlockProcessor:
    """Process only irreversible blocks for financial safety."""

    def __init__(self, nodes, db_path="irrev_state.db"):
        self.hive = Hive(node=nodes)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize SQLite state database."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS deposits (
                tx_id TEXT PRIMARY KEY,
                block_num INTEGER,
                timestamp TEXT,
                from_account TEXT,
                to_account TEXT,
                amount REAL,
                asset TEXT,
                memo TEXT,
                processed INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def get_last_processed_block(self):
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT value FROM state WHERE key='last_block'"
        ).fetchone()
        conn.close()
        return int(row[0]) if row else None

    def save_last_processed_block(self, block_num):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
            ("last_block", str(block_num))
        )
        conn.commit()
        conn.close()

    def record_deposit(self, tx_id, block_num, timestamp,
                       from_acct, to_acct, amount, asset, memo):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """INSERT OR IGNORE INTO deposits
                   (tx_id, block_num, timestamp, from_account,
                    to_account, amount, asset, memo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (tx_id, block_num, timestamp, from_acct,
                 to_acct, amount, asset, memo)
            )
            conn.commit()
        finally:
            conn.close()

    def process_block(self, block, block_num):
        """Process a single irreversible block."""
        if not block or "transactions" not in block:
            return

        timestamp = block.get("timestamp", "")
        for tx in block["transactions"]:
            tx_id = tx.get("transaction_id", "")
            for op in tx.get("operations", []):
                if isinstance(op, list):
                    op_type, op_data = op[0], op[1]
                else:
                    op_type = op.get("type", "").replace("_operation", "")
                    op_data = op.get("value", op)

                self._handle_operation(
                    op_type, op_data, tx_id, block_num, timestamp
                )

    def _handle_operation(self, op_type, op_data, tx_id,
                          block_num, timestamp):
        """Handle specific operation types."""
        if op_type == "transfer":
            to_account = op_data.get("to", "")
            # Check if this is a deposit to our exchange accounts
            if to_account in self.watched_accounts:
                amount_str = op_data.get("amount", "0 HIVE")
                parts = amount_str.split()
                amount = float(parts[0])
                asset = parts[1] if len(parts) > 1 else "HIVE"
                memo = op_data.get("memo", "")

                logger.info(
                    f"DEPOSIT: {amount} {asset} from "
                    f"@{op_data['from']} to @{to_account} "
                    f"memo='{memo}' block={block_num}"
                )
                self.record_deposit(
                    tx_id, block_num, timestamp,
                    op_data["from"], to_account,
                    amount, asset, memo
                )

    def run(self, watched_accounts, start_block=None):
        """Main processing loop - only irreversible blocks."""
        self.watched_accounts = set(watched_accounts)
        last_block = start_block or self.get_last_processed_block()

        if last_block is None:
            props = self.hive.rpc.get_dynamic_global_properties()
            last_block = props["last_irreversible_block_num"]

        logger.info(f"Starting from block {last_block}")
        logger.info(f"Watching accounts: {watched_accounts}")

        blockchain = Blockchain(hive_instance=self.hive)

        while True:
            try:
                props = self.hive.rpc.get_dynamic_global_properties()
                lib = props["last_irreversible_block_num"]

                while last_block < lib:
                    last_block += 1
                    block = blockchain.get_block(last_block)
                    self.process_block(block, last_block)

                    if last_block % 100 == 0:
                        self.save_last_processed_block(last_block)
                        logger.info(f"Processed up to block {last_block} "
                                    f"(LIB: {lib})")

                self.save_last_processed_block(last_block)
                time.sleep(3)  # Wait for next block

            except Exception as e:
                logger.error(f"Processing error: {e}")
                time.sleep(5)

# Usage
processor = IrreversibleBlockProcessor(
    nodes=["https://api.hive.blog", "https://api.deathwing.me"],
    db_path="exchange_deposits.db"
)
# processor.run(watched_accounts=["myexchange", "myexchange-hot"])
```

This processor guarantees that only finalized (irreversible) blocks are processed, uses SQLite for crash recovery and deduplication, and logs all deposits with full transaction details. The irreversible block number is tracked by the LIB property, which advances as 2/3+ of witnesses confirm blocks.
'''
    ),
]
