"""Hive blockchain training pairs: testing Hive applications."""

PAIRS = [
    (
        "hive/testnet-usage",
        r'''How do I use the Hive testnet for testing my dApp? How do I connect to it and get test accounts?''',
        r'''The Hive testnet is a separate blockchain for testing without risking real funds. Here is how to use it:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer, Custom_json
import json

# Connect to the Hive testnet
TESTNET_NODE = "https://testnet.openhive.network"
TESTNET_CHAIN_ID = "18dcf0a285365fc58b71f18b3d3fec954aa0c141c44e4e5cb4cf777b9eab274e"

testnet = Hive(
    node=[TESTNET_NODE],
    chain_id=TESTNET_CHAIN_ID,
    keys=["5JNHfZYKGaomSFvd4NUdQ9qMcEAC43kujbfjueTHpVapX1Kzq2n"]  # testnet initminer key
)

def create_testnet_account(username, creator="initminer"):
    """Create a test account on the testnet."""
    from beemgraphenebase.account import PasswordKey
    from beembase.operations import Account_create

    password = "testpassword123"
    keys = {}
    for role in ["owner", "active", "posting", "memo"]:
        pk = PasswordKey(username, password, role=role)
        keys[role] = str(pk.get_public_key())

    op = Account_create(**{
        "fee": "3.000 TESTS",  # Testnet uses TESTS instead of HIVE
        "creator": creator,
        "new_account_name": username,
        "owner": {"weight_threshold": 1, "account_auths": [],
                  "key_auths": [[keys["owner"], 1]]},
        "active": {"weight_threshold": 1, "account_auths": [],
                   "key_auths": [[keys["active"], 1]]},
        "posting": {"weight_threshold": 1, "account_auths": [],
                    "key_auths": [[keys["posting"], 1]]},
        "memo_key": keys["memo"],
        "json_metadata": "{}"
    })

    tx = TransactionBuilder(hive_instance=testnet)
    tx.appendOps(op)
    tx.appendSigner(creator, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Testnet account @{username} created")
    return result, password

def fund_testnet_account(username, amount="1000.000 TESTS"):
    """Transfer testnet tokens to an account."""
    op = Transfer(**{
        "from": "initminer",
        "to": username,
        "amount": amount,
        "memo": "Testnet funding"
    })
    tx = TransactionBuilder(hive_instance=testnet)
    tx.appendOps(op)
    tx.appendSigner("initminer", "active")
    tx.sign()
    return tx.broadcast()

def test_custom_json(account, dapp_id, payload, posting_key):
    """Test a custom_json operation on testnet."""
    test_hive = Hive(
        node=[TESTNET_NODE],
        chain_id=TESTNET_CHAIN_ID,
        keys=[posting_key]
    )
    op = Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [account],
        "id": dapp_id,
        "json": json.dumps(payload)
    })
    tx = TransactionBuilder(hive_instance=test_hive)
    tx.appendOps(op)
    tx.appendSigner(account, "posting")
    tx.sign()
    result = tx.broadcast()
    print(f"Custom JSON on testnet: {result}")
    return result

# Testnet setup workflow
def setup_test_environment():
    """Set up a complete test environment."""
    # Create test accounts
    accounts = ["testuser1", "testuser2", "testdapp"]
    for username in accounts:
        try:
            create_testnet_account(username)
            fund_testnet_account(username, "10000.000 TESTS")
            print(f"@{username} ready with 10000 TESTS")
        except Exception as e:
            print(f"@{username}: {e}")

    # Verify setup
    for username in accounts:
        try:
            acct = Account(username, hive_instance=testnet)
            balance = acct["balance"]
            print(f"@{username} balance: {balance}")
        except Exception as e:
            print(f"@{username} check failed: {e}")

# setup_test_environment()
```

Testnet differences from mainnet:
- Uses TESTS and TBD instead of HIVE and HBD
- Has a different chain_id
- The initminer account has unlimited funds for testing
- Blocks may be produced less frequently
- The testnet may be reset periodically
- No real economic value -- perfect for testing
'''
    ),
    (
        "hive/mock-transactions",
        r'''How do I create mock transactions and unit tests for my Hive dApp without broadcasting to any blockchain?''',
        r'''Testing Hive dApps without a blockchain connection requires mocking the RPC layer. Here is how to set up comprehensive unit tests:

```python
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
import json
from datetime import datetime

# Mock the Hive RPC responses
class MockHiveRPC:
    """Mock Hive RPC for testing without a blockchain."""

    def __init__(self):
        self.accounts = {
            "alice": {
                "name": "alice",
                "balance": "100.000 HIVE",
                "hbd_balance": "50.000 HBD",
                "vesting_shares": "1000000.000000 VESTS",
                "received_vesting_shares": "500000.000000 VESTS",
                "delegated_vesting_shares": "0.000000 VESTS",
                "voting_power": 9800,
                "posting": {
                    "weight_threshold": 1,
                    "account_auths": [["myapp", 1]],
                    "key_auths": [["STM7abc...", 1]]
                },
                "savings_hbd_balance": "1000.000 HBD",
                "pending_claimed_accounts": 5,
                "recovery_account": "hive.blog"
            },
            "bob": {
                "name": "bob",
                "balance": "50.000 HIVE",
                "hbd_balance": "25.000 HBD",
                "vesting_shares": "500000.000000 VESTS",
                "received_vesting_shares": "0.000000 VESTS",
                "delegated_vesting_shares": "0.000000 VESTS",
                "voting_power": 10000,
                "posting": {
                    "weight_threshold": 1,
                    "account_auths": [],
                    "key_auths": [["STM7def...", 1]]
                }
            }
        }
        self.broadcast_log = []

    def get_accounts(self, names):
        return [self.accounts.get(n, None) for n in names if n in self.accounts]

    def get_dynamic_global_properties(self):
        return {
            "head_block_number": 80000000,
            "last_irreversible_block_num": 79999980,
            "time": "2025-01-15T12:00:00",
            "current_witness": "blocktrades",
            "total_vesting_fund_hive": "200000000.000 HIVE",
            "total_vesting_shares": "400000000000.000000 VESTS",
            "hbd_interest_rate": 2000,
            "current_hbd_supply": "30000000.000 HBD",
            "current_supply": "400000000.000 HIVE",
        }

    def broadcast_transaction(self, tx):
        self.broadcast_log.append(tx)
        return {"id": "mock_tx_" + str(len(self.broadcast_log))}


# Your dApp class to test
class MyHiveDApp:
    def __init__(self, hive_instance):
        self.hive = hive_instance

    def check_user_authority(self, username):
        accounts = self.hive.rpc.get_accounts([username])
        if not accounts:
            return False
        posting = accounts[0].get("posting", {})
        authorized = [a[0] for a in posting.get("account_auths", [])]
        return "myapp" in authorized

    def calculate_hp(self, username):
        accounts = self.hive.rpc.get_accounts([username])
        if not accounts:
            return 0
        props = self.hive.rpc.get_dynamic_global_properties()
        total_hive = float(props["total_vesting_fund_hive"].split()[0])
        total_vests = float(props["total_vesting_shares"].split()[0])
        own_vests = float(accounts[0]["vesting_shares"].split()[0])
        received = float(accounts[0]["received_vesting_shares"].split()[0])
        delegated = float(accounts[0]["delegated_vesting_shares"].split()[0])
        effective = own_vests + received - delegated
        return effective * total_hive / total_vests


# Unit tests
class TestMyHiveDApp(unittest.TestCase):
    def setUp(self):
        self.mock_rpc = MockHiveRPC()
        self.mock_hive = MagicMock()
        self.mock_hive.rpc = self.mock_rpc
        self.dapp = MyHiveDApp(self.mock_hive)

    def test_check_authority_granted(self):
        """Test that authority check returns True for authorized account."""
        result = self.dapp.check_user_authority("alice")
        self.assertTrue(result)

    def test_check_authority_not_granted(self):
        """Test that authority check returns False for unauthorized account."""
        result = self.dapp.check_user_authority("bob")
        self.assertFalse(result)

    def test_check_authority_unknown_account(self):
        """Test authority check for non-existent account."""
        result = self.dapp.check_user_authority("unknown")
        self.assertFalse(result)

    def test_calculate_hp(self):
        """Test HP calculation from VESTS."""
        hp = self.dapp.calculate_hp("alice")
        # 1500000 VESTS * (200M HIVE / 400B VESTS) = 750 HP
        self.assertAlmostEqual(hp, 750.0, places=1)

    def test_calculate_hp_no_delegations(self):
        """Test HP calculation without delegations."""
        hp = self.dapp.calculate_hp("bob")
        # 500000 VESTS * (200M / 400B) = 250 HP
        self.assertAlmostEqual(hp, 250.0, places=1)


if __name__ == "__main__":
    unittest.main()
```

This mock-based testing approach lets you test business logic without any blockchain connection. Mock the RPC layer, provide realistic account data, and verify your dApp's behavior. For integration tests, use the testnet; for unit tests, use mocks.
'''
    ),
    (
        "hive/integration-testing",
        r'''How do I write integration tests for a Hive dApp that verify end-to-end transaction flows?''',
        r'''Integration tests for Hive dApps should verify complete transaction flows on the testnet. Here is a testing framework that handles setup, execution, and verification:

```python
import unittest
import time
import json
from beem import Hive
from beem.account import Account
from beem.comment import Comment
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer, Vote, Custom_json, Comment as CommentOp

TESTNET_NODE = "https://testnet.openhive.network"
TESTNET_CHAIN_ID = "18dcf0a285365fc58b71f18b3d3fec954aa0c141c44e4e5cb4cf777b9eab274e"

class HiveIntegrationTestCase(unittest.TestCase):
    """Base class for Hive integration tests."""

    @classmethod
    def setUpClass(cls):
        cls.hive = Hive(
            node=[TESTNET_NODE],
            chain_id=TESTNET_CHAIN_ID,
            keys=["5TestActiveKey", "5TestPostingKey"]
        )
        cls.test_account = "testuser1"
        cls.wait_blocks = 2

    def wait_for_block(self, blocks=None):
        """Wait for N blocks to pass (for confirmation)."""
        n = blocks or self.wait_blocks
        time.sleep(n * 3 + 1)

    def assert_balance_changed(self, account, asset, expected_change):
        """Assert that an account's balance changed by expected amount."""
        acct = Account(account, hive_instance=self.hive)
        if asset == "TESTS":
            balance = float(str(acct["balance"]).split()[0])
        elif asset == "TBD":
            balance = float(str(acct["hbd_balance"]).split()[0])
        else:
            self.fail(f"Unknown asset: {asset}")
        # Store and compare (simplified)
        return balance

    def broadcast_and_verify(self, ops, signer, key_type="posting"):
        """Broadcast operations and verify success."""
        tx = TransactionBuilder(hive_instance=self.hive)
        for op in ops:
            tx.appendOps(op)
        tx.appendSigner(signer, key_type)
        tx.sign()
        result = tx.broadcast()
        self.assertIn("id", result)
        return result


class TestTransferFlow(HiveIntegrationTestCase):
    """Test transfer operations end-to-end."""

    def test_basic_transfer(self):
        """Test a basic HIVE transfer."""
        op = Transfer(**{
            "from": self.test_account,
            "to": "testuser2",
            "amount": "0.001 TESTS",
            "memo": "integration test"
        })
        result = self.broadcast_and_verify([op], self.test_account, "active")
        self.assertIsNotNone(result["id"])

    def test_transfer_with_memo(self):
        """Test transfer with memo content."""
        op = Transfer(**{
            "from": self.test_account,
            "to": "testuser2",
            "amount": "0.001 TESTS",
            "memo": "test-memo-" + str(int(time.time()))
        })
        result = self.broadcast_and_verify([op], self.test_account, "active")
        self.wait_for_block()

        # Verify via account history
        acct = Account("testuser2", hive_instance=self.hive)
        history = acct.get_account_history(
            index=-1, limit=5, only_ops=["transfer"]
        )
        found = False
        for entry in history:
            op_data = entry["op"][1] if isinstance(entry["op"], list) else entry["op"]
            if "test-memo" in str(op_data.get("memo", "")):
                found = True
                break
        self.assertTrue(found, "Transfer not found in history")


class TestCustomJsonFlow(HiveIntegrationTestCase):
    """Test custom_json operations."""

    def test_dapp_operation(self):
        """Test broadcasting a dApp custom_json."""
        payload = {
            "app": "test/1.0",
            "action": "test_action",
            "data": {"key": "value", "ts": int(time.time())}
        }
        op = Custom_json(**{
            "required_auths": [],
            "required_posting_auths": [self.test_account],
            "id": "testapp",
            "json": json.dumps(payload)
        })
        result = self.broadcast_and_verify([op], self.test_account, "posting")
        self.assertIsNotNone(result["id"])

    def test_max_payload_size(self):
        """Test custom_json at maximum payload size."""
        large_data = "x" * 8000  # Near 8192 byte limit
        payload = {"data": large_data}
        serialized = json.dumps(payload)
        self.assertLess(len(serialized), 8192)

        op = Custom_json(**{
            "required_auths": [],
            "required_posting_auths": [self.test_account],
            "id": "testapp",
            "json": serialized
        })
        result = self.broadcast_and_verify([op], self.test_account, "posting")
        self.assertIsNotNone(result["id"])


class TestPostFlow(HiveIntegrationTestCase):
    """Test post creation and interaction."""

    def test_create_and_vote(self):
        """Test creating a post and voting on it."""
        permlink = f"test-post-{int(time.time())}"

        # Create post
        post_op = CommentOp(**{
            "parent_author": "",
            "parent_permlink": "test",
            "author": self.test_account,
            "permlink": permlink,
            "title": "Integration Test Post",
            "body": "This is an automated integration test post.",
            "json_metadata": json.dumps({"tags": ["test"]})
        })
        self.broadcast_and_verify([post_op], self.test_account, "posting")
        self.wait_for_block()

        # Vote on post
        vote_op = Vote(**{
            "voter": self.test_account,
            "author": self.test_account,
            "permlink": permlink,
            "weight": 10000
        })
        result = self.broadcast_and_verify(
            [vote_op], self.test_account, "posting"
        )
        self.assertIsNotNone(result["id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

Integration testing best practices for Hive:
- Always use testnet, never mainnet
- Wait for block confirmation between dependent operations
- Clean up test data when possible (blank posts)
- Test edge cases (max payload size, empty memo, zero amount)
- Verify operations via account history, not just broadcast success
- Use unique permlinks/memos with timestamps for traceability
'''
    ),
    (
        "hive/replay-based-testing",
        r'''How do I use blockchain replay to test my Hive application against historical data?''',
        r'''Replay-based testing processes historical blocks through your application to verify it handles real-world data correctly. This catches edge cases you might miss with synthetic test data:

```python
from beem import Hive
from beem.blockchain import Blockchain
import json
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("replay_test")

class ReplayTester:
    """Test your application by replaying historical blockchain data."""

    def __init__(self, nodes, app_processor):
        self.hive = Hive(node=nodes)
        self.blockchain = Blockchain(hive_instance=self.hive)
        self.processor = app_processor
        self.stats = {
            "blocks": 0,
            "operations": 0,
            "errors": 0,
            "processed": 0
        }

    def replay_range(self, start_block, end_block, op_types=None):
        """Replay a range of blocks through the processor."""
        logger.info(f"Replaying blocks {start_block} to {end_block}")
        start_time = time.time()

        for block_num in range(start_block, end_block + 1):
            try:
                block = self.blockchain.get_block(block_num)
                if not block:
                    continue

                self.stats["blocks"] += 1
                timestamp = block.get("timestamp", "")

                for tx in block.get("transactions", []):
                    for op in tx.get("operations", []):
                        if isinstance(op, list):
                            op_type, op_data = op[0], op[1]
                        else:
                            op_type = op.get("type", "").replace("_operation", "")
                            op_data = op.get("value", op)

                        self.stats["operations"] += 1

                        if op_types and op_type not in op_types:
                            continue

                        try:
                            self.processor(op_type, op_data, block_num, timestamp)
                            self.stats["processed"] += 1
                        except Exception as e:
                            self.stats["errors"] += 1
                            logger.error(f"Block {block_num} {op_type}: {e}")

                if block_num % 1000 == 0:
                    elapsed = time.time() - start_time
                    rate = self.stats["blocks"] / elapsed if elapsed > 0 else 0
                    logger.info(f"Block {block_num}: {rate:.0f} blocks/s, "
                                f"{self.stats['errors']} errors")

            except Exception as e:
                logger.error(f"Block {block_num} fetch error: {e}")
                self.stats["errors"] += 1

        elapsed = time.time() - start_time
        self.print_stats(elapsed)

    def replay_recent(self, hours=1, op_types=None):
        """Replay the most recent N hours of blocks."""
        props = self.hive.rpc.get_dynamic_global_properties()
        head = props["head_block_number"]
        blocks_per_hour = 1200  # 3-second blocks
        start = head - int(hours * blocks_per_hour)
        self.replay_range(start, head, op_types)

    def print_stats(self, elapsed):
        print(f"\n=== Replay Test Results ===")
        print(f"Blocks processed:    {self.stats['blocks']:,}")
        print(f"Operations seen:     {self.stats['operations']:,}")
        print(f"Operations handled:  {self.stats['processed']:,}")
        print(f"Errors:              {self.stats['errors']:,}")
        print(f"Duration:            {elapsed:.1f}s")
        if elapsed > 0:
            print(f"Rate:                {self.stats['blocks']/elapsed:.0f} blocks/s")
        error_rate = (self.stats['errors'] / max(self.stats['processed'], 1) * 100)
        print(f"Error rate:          {error_rate:.2f}%")

# Example: Test a transfer processor
class TransferProcessor:
    def __init__(self):
        self.transfers = []
        self.large_transfers = []

    def process(self, op_type, op_data, block_num, timestamp):
        if op_type != "transfer":
            return

        amount_str = op_data.get("amount", "0 HIVE")
        parts = amount_str.split()
        amount = float(parts[0])
        asset = parts[1] if len(parts) > 1 else "HIVE"

        record = {
            "block": block_num,
            "from": op_data["from"],
            "to": op_data["to"],
            "amount": amount,
            "asset": asset,
            "memo": op_data.get("memo", "")
        }
        self.transfers.append(record)

        if amount >= 10000:
            self.large_transfers.append(record)

    def report(self):
        print(f"\nTransfer Analysis:")
        print(f"  Total transfers:  {len(self.transfers):,}")
        print(f"  Large (>10k):     {len(self.large_transfers):,}")

# Run replay test
processor = TransferProcessor()
tester = ReplayTester(
    nodes=["https://api.hive.blog"],
    app_processor=processor.process
)

# Test with last hour of data
# tester.replay_recent(hours=1, op_types=["transfer"])
# processor.report()

# Test with specific historical range
# tester.replay_range(80000000, 80001000, op_types=["transfer"])
```

Replay testing benefits:
- Catches real-world edge cases (unusual amounts, special characters in memos)
- Verifies performance under realistic load
- Tests handling of all operation variants
- Can reproduce specific bugs by replaying the exact block range
- No risk to real accounts or funds
'''
    ),
    (
        "hive/local-devnet",
        r'''How do I set up a local Hive development network for testing without relying on any external services?''',
        r'''A local devnet gives you a private Hive blockchain for testing with full control over block production, accounts, and timing. Here is how to set it up:

```bash
#!/bin/bash
# Local Hive devnet setup using Docker

# Create data directory
mkdir -p /tmp/hive-devnet/data

# Minimal config.ini for a single-witness devnet
cat > /tmp/hive-devnet/data/config.ini << 'ENDCONFIG'
# Local devnet configuration
witness = "initminer"
private-key = 5JNHfZYKGaomSFvd4NUdQ9qMcEAC43kujbfjueTHpVapX1Kzq2n

plugin = witness
plugin = p2p
plugin = webserver
plugin = condenser_api
plugin = database_api
plugin = block_api
plugin = rc_api
plugin = network_broadcast_api
plugin = account_by_key
plugin = account_by_key_api

webserver-http-endpoint = 0.0.0.0:8091
webserver-ws-endpoint = 0.0.0.0:8090

shared-file-size = 1G

# Enable stale production for single-witness devnet
enable-stale-production = true
required-participation = 0
ENDCONFIG

# Start the devnet
docker run -d --name hive-devnet \
    -v /tmp/hive-devnet/data:/hive/data \
    -p 8090:8090 -p 8091:8091 \
    hiveio/hive:latest \
    --data-dir=/hive/data
```

Python helper for managing the local devnet:

```python
import requests
import time
import json
import subprocess
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Account_create, Transfer
from beemgraphenebase.account import PasswordKey

DEVNET_URL = "http://localhost:8091"

# The initminer private key (well-known for devnet)
INITMINER_KEY = "5JNHfZYKGaomSFvd4NUdQ9qMcEAC43kujbfjueTHpVapX1Kzq2n"

class HiveDevnet:
    """Helper for managing a local Hive devnet."""

    def __init__(self, url=DEVNET_URL):
        self.url = url
        self.hive = None

    def wait_for_ready(self, timeout=60):
        """Wait for the devnet to start producing blocks."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = requests.post(self.url, json={
                    "jsonrpc": "2.0",
                    "method": "condenser_api.get_dynamic_global_properties",
                    "params": [],
                    "id": 1
                }, timeout=3)
                data = resp.json().get("result", {})
                block = data.get("head_block_number", 0)
                if block > 1:
                    print(f"Devnet ready at block {block}")
                    self.hive = Hive(
                        node=[self.url],
                        keys=[INITMINER_KEY]
                    )
                    return True
            except (requests.ConnectionError, requests.Timeout):
                pass
            time.sleep(2)
        return False

    def create_account(self, username, password="test123"):
        """Create a funded test account."""
        keys = {}
        for role in ["owner", "active", "posting", "memo"]:
            pk = PasswordKey(username, password, role=role)
            keys[role] = str(pk.get_public_key())
            keys[f"{role}_private"] = str(pk.get_private_key())

        op = Account_create(**{
            "fee": "0.000 HIVE",
            "creator": "initminer",
            "new_account_name": username,
            "owner": {"weight_threshold": 1, "account_auths": [],
                      "key_auths": [[keys["owner"], 1]]},
            "active": {"weight_threshold": 1, "account_auths": [],
                       "key_auths": [[keys["active"], 1]]},
            "posting": {"weight_threshold": 1, "account_auths": [],
                        "key_auths": [[keys["posting"], 1]]},
            "memo_key": keys["memo"],
            "json_metadata": "{}"
        })

        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner("initminer", "active")
        tx.sign()
        tx.broadcast()

        # Fund the account
        fund_op = Transfer(**{
            "from": "initminer",
            "to": username,
            "amount": "10000.000 HIVE",
            "memo": ""
        })
        tx2 = TransactionBuilder(hive_instance=self.hive)
        tx2.appendOps(fund_op)
        tx2.appendSigner("initminer", "active")
        tx2.sign()
        tx2.broadcast()

        print(f"Created @{username} with 10000 HIVE")
        return keys

    def advance_blocks(self, count=1):
        """Wait for N blocks to be produced."""
        time.sleep(count * 3 + 1)

    def get_block_num(self):
        """Get current block number."""
        resp = requests.post(self.url, json={
            "jsonrpc": "2.0",
            "method": "condenser_api.get_dynamic_global_properties",
            "params": [], "id": 1
        })
        return resp.json()["result"]["head_block_number"]

    def reset(self):
        """Reset the devnet (stop, clear data, restart)."""
        subprocess.run(["docker", "stop", "hive-devnet"], capture_output=True)
        subprocess.run(["docker", "rm", "hive-devnet"], capture_output=True)
        subprocess.run(["rm", "-rf", "/tmp/hive-devnet/data/blockchain"],
                       capture_output=True)
        # Restart with docker run command...
        print("Devnet reset. Run docker start command to restart.")

# Usage in tests
# devnet = HiveDevnet()
# devnet.wait_for_ready()
# keys = devnet.create_account("testuser")
# devnet.advance_blocks(2)
```

A local devnet gives you complete control: instant block production, unlimited test funds, no rate limits, and the ability to reset state between test runs. This is ideal for CI/CD pipelines where you need reproducible test environments.
'''
    ),
]
