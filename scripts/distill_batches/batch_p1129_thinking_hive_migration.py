"""
Hive blockchain thinking pairs - migration and upgrade reasoning
"""

pairs = [
    {
        "instruction": r'''I have a Steem-based dApp that I want to migrate to Hive. What are the key differences I need to handle and what is the migration strategy?''',
        "output": r'''<think>
Steem to Hive migration -- this is a real scenario many developers faced when Hive forked from Steem in March 2020. Let me think about the key differences.

First, the blockchain-level differences:
- Different chain_id (transactions signed for Steem will not work on Hive)
- Different API nodes (api.hive.blog instead of api.steemit.com)
- Different token names (HIVE instead of STEEM, HBD instead of SBD)
- Resource Credits system (same concept, different parameters)

Second, the library differences:
- beem supports both, just change the node URLs
- steem-python is Steem-only, need to switch to beem
- JavaScript: steem-js -> dhive or @hiveio/hive-js

Hmm, but there are also feature differences that accumulated since the fork. Hive has had several hard forks that Steem did not:
- HF24: changed resource credit costs
- HF25: linear curation, removed reverse auction
- HF26: various protocol improvements
- Account recovery periods might differ

I initially thought it would be a simple find-and-replace of "steem" with "hive", but it is more nuanced. The custom_json ids should change (if they referenced "steem" in the name). Database schemas need updating for new token names. And the app needs to handle accounts that exist on both chains with potentially different states.

The tradeoff is: big-bang migration (switch everything at once, clean break) vs gradual migration (support both chains during transition). For most apps, a clean break is simpler. The only reason to support both is if you have users on both chains.

For the database, if the app indexed Steem data, you need to decide: migrate historical Steem data to the Hive tables, or start fresh from the Hive fork block? Starting fresh is simpler but loses pre-fork history.
</think>

Here is a systematic migration guide covering code changes, database migration, and deployment strategy:

```python
# === Key Differences: Steem vs Hive ===
#
# | Aspect          | Steem              | Hive                    |
# |-----------------|--------------------|-----------------------  |
# | Tokens          | STEEM, SBD, VESTS  | HIVE, HBD, VESTS        |
# | API nodes       | api.steemit.com    | api.hive.blog           |
# | Chain ID        | 0x00...00          | beeab0de00...00         |
# | Library         | steem-python       | beem                    |
# | Curation        | Non-linear + 5min  | Linear, no reverse      |
# |                 | reverse auction    | auction (post-HF25)     |
# | Custom JSON     | Same format        | Same format             |
# | Fork block      | N/A                | 41,818,752              |

# === Step 1: Update Library Imports and Configuration ===

# BEFORE (Steem):
# from steem import Steem
# s = Steem(nodes=['https://api.steemit.com'])

# AFTER (Hive):
from beem import Hive
from beem.account import Account
from beem.comment import Comment
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer, Custom_json, Vote
import json

# Node configuration
HIVE_NODES = [
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://api.openhive.network",
]

hive = Hive(node=HIVE_NODES, keys=["5YourPostingKey"])


# === Step 2: Token Name Changes ===

class TokenMigrator:
    """Handle token name changes in code and data."""

    TOKEN_MAP = {
        "STEEM": "HIVE",
        "SBD": "HBD",
        # VESTS stays the same
    }

    @staticmethod
    def convert_amount(amount_str):
        """Convert Steem amount strings to Hive format.

        '10.000 STEEM' -> '10.000 HIVE'
        '5.000 SBD' -> '5.000 HBD'
        """
        parts = amount_str.strip().split()
        if len(parts) == 2:
            value, token = parts
            token = TokenMigrator.TOKEN_MAP.get(token.upper(), token)
            return f"{value} {token}"
        return amount_str

    @staticmethod
    def convert_operation(op_data):
        """Convert operation data from Steem format to Hive."""
        data = dict(op_data)
        for key in ("amount", "fee", "max_accepted_payout",
                     "reward_hive", "reward_hbd", "reward_vests"):
            if key in data and isinstance(data[key], str):
                data[key] = TokenMigrator.convert_amount(data[key])
        return data


# === Step 3: Custom JSON ID Migration ===

def migrate_custom_json_id(old_id):
    """Update custom_json IDs that referenced Steem.

    Best practice: use app-specific IDs that are chain-agnostic.
    """
    id_map = {
        "steem_app_action": "myapp_action",
        "steem_game_move": "myapp_game_move",
        # "follow" stays "follow" (standard operation)
    }
    return id_map.get(old_id, old_id)


# === Step 4: Database Migration ===

DB_MIGRATION_SQL = """
-- Rename token columns
ALTER TABLE balances RENAME COLUMN steem_balance TO hive_balance;
ALTER TABLE balances RENAME COLUMN sbd_balance TO hbd_balance;

-- Update token references in transaction history
UPDATE transaction_log SET currency = 'HIVE' WHERE currency = 'STEEM';
UPDATE transaction_log SET currency = 'HBD' WHERE currency = 'SBD';

-- Update custom_json IDs
UPDATE app_operations
SET json_id = REPLACE(json_id, 'steem_', 'myapp_')
WHERE json_id LIKE 'steem_%';

-- Add column for chain identifier (useful during transition)
ALTER TABLE posts ADD COLUMN IF NOT EXISTS chain TEXT DEFAULT 'hive';
ALTER TABLE transaction_log ADD COLUMN IF NOT EXISTS chain TEXT DEFAULT 'hive';

-- Mark pre-fork data
UPDATE posts SET chain = 'steem' WHERE block_num < 41818752;
UPDATE transaction_log SET chain = 'steem' WHERE block_num < 41818752;
"""


# === Step 5: API Compatibility Layer ===

class HiveCompatAPI:
    """Wrapper that provides a consistent API during migration."""

    def __init__(self, blockchain_instance):
        self.hive = blockchain_instance

    def get_account(self, username):
        """Get account data in a chain-agnostic format."""
        acc = Account(username, blockchain_instance=self.hive)
        return {
            "name": username,
            "liquid_token": float(acc.get_balance("available", "HIVE")),
            "stable_token": float(acc.get_balance("available", "HBD")),
            "staked_token": float(acc.get_hive_power()),
            "reputation": float(acc.get_reputation()),
            "voting_power": acc.get_voting_power(),
        }

    def transfer(self, from_account, to_account, amount, token, memo=""):
        """Transfer tokens using chain-agnostic token names."""
        # Accept both old and new names
        token = token.upper()
        if token in ("STEEM", "LIQUID", "HIVE"):
            token = "HIVE"
        elif token in ("SBD", "STABLE", "HBD"):
            token = "HBD"

        tx = TransactionBuilder(blockchain_instance=self.hive)
        tx.appendOps(Transfer(**{
            "from": from_account,
            "to": to_account,
            "amount": f"{amount:.3f} {token}",
            "memo": memo
        }))
        tx.appendSigner(from_account, "active")
        tx.sign()
        return tx.broadcast()

    def custom_json(self, account, op_id, data, key_type="posting"):
        """Broadcast custom_json with migrated ID."""
        migrated_id = migrate_custom_json_id(op_id)
        tx = TransactionBuilder(blockchain_instance=self.hive)

        if key_type == "posting":
            auths = {"required_auths": [],
                     "required_posting_auths": [account]}
        else:
            auths = {"required_auths": [account],
                     "required_posting_auths": []}

        tx.appendOps(Custom_json(**{
            **auths,
            "id": migrated_id,
            "json": json.dumps(data, separators=(",", ":"))
        }))
        tx.appendSigner(account, key_type)
        tx.sign()
        return tx.broadcast()


# === Migration Checklist ===
#
# 1. [ ] Replace steem-python with beem
# 2. [ ] Update API node URLs
# 3. [ ] Change token names (STEEM->HIVE, SBD->HBD)
# 4. [ ] Update custom_json IDs
# 5. [ ] Run database migration SQL
# 6. [ ] Update frontend token names and logos
# 7. [ ] Update documentation and README
# 8. [ ] Test all operations on Hive testnet first
# 9. [ ] Deploy and verify
```

Migration strategy: do a clean break rather than supporting both chains. Update library, nodes, token names, and custom_json IDs. Run database migrations to rename columns and update stored token references. Test thoroughly on Hive testnet before deploying. Pre-fork historical data can be kept with a chain marker column.'''
    },
    {
        "instruction": r'''I need to upgrade my beem library from version 0.24 to the latest version. What breaking changes should I watch out for?''',
        "output": r'''<think>
Upgrading beem across major versions -- this can be tricky because the API surface has changed over time. Let me think about what typically changes between beem versions.

Common breaking changes in beem upgrades:
1. Method signatures changing (parameters renamed, reordered)
2. Return value format changes
3. Default node list changes
4. Deprecated methods removed
5. Changes in how keys are handled
6. Transaction building API changes

Hmm, I should think about a safe upgrade strategy. You cannot just pip install the latest version and hope everything works. You need to:
1. Read the changelog
2. Set up a test environment
3. Run existing tests against the new version
4. Fix any breakage
5. Test against Hive testnet
6. Deploy

I initially thought about doing an in-place upgrade, but a safer approach is to create a virtual environment with the new version and run the test suite. If tests fail, you can compare behavior between old and new versions side by side.

Wait, there is another concern: beem versions can also change how they interact with different Hive node versions. If the Hive node API changed (after a hard fork), the beem version needs to match. Running an old beem against a post-hard-fork node might cause subtle issues.

The tradeoff is: upgrade immediately after release (get new features and bug fixes, risk breakage) vs wait and upgrade conservatively (stable, but miss fixes and might have compatibility issues with updated nodes).

Actually, the most practical approach is: pin your beem version in requirements.txt, create a branch for the upgrade, run tests, fix issues, and merge when everything passes.
</think>

Here is a safe upgrade strategy with common breaking changes to watch for:

```python
# === Safe Upgrade Process ===
#
# Step 1: Document current state
# pip freeze | grep beem > beem_current_version.txt
#
# Step 2: Create upgrade branch
# git checkout -b upgrade-beem
#
# Step 3: Create test virtual environment
# python -m venv venv_upgrade
# source venv_upgrade/bin/activate  (or venv_upgrade\Scripts\activate)
# pip install beem  (latest)
# pip install -r requirements.txt  (other deps)
#
# Step 4: Run tests and fix issues

# === Common Breaking Changes ===

# CHANGE 1: Account balance methods
# Old (beem <= 0.24):
#   acc.balances  # returned dict
#   acc['balance']  # raw string like "10.000 HIVE"
#
# New (beem >= 0.24.x):
#   acc.get_balance("available", "HIVE")  # returns Amount object
#   float(acc.get_balance("available", "HIVE"))  # for numeric value

from beem import Hive
from beem.account import Account
from beem.amount import Amount

hive = Hive(node=["https://api.hive.blog"])


def get_balances_compatible(username):
    """Get balances in a way that works across beem versions."""
    acc = Account(username, blockchain_instance=hive)

    try:
        # Modern beem
        hive_balance = float(acc.get_balance("available", "HIVE"))
        hbd_balance = float(acc.get_balance("available", "HBD"))
        hp = float(acc.get_hive_power())
    except AttributeError:
        # Older beem fallback
        hive_balance = float(Amount(acc["balance"]))
        hbd_balance = float(Amount(acc["hbd_balance"]))
        hp = float(acc.get_steem_power())  # old name

    return {
        "hive": hive_balance,
        "hbd": hbd_balance,
        "hp": hp
    }


# CHANGE 2: Voting power
# Old: acc.get_voting_power() might return different scale
# New: returns percentage (0-100)

def get_voting_power_compatible(username):
    acc = Account(username, blockchain_instance=hive)
    vp = acc.get_voting_power()
    # Normalize to 0-100 range regardless of version
    if vp > 100:
        vp = vp / 100  # some versions returned 0-10000
    return vp


# CHANGE 3: Blockchain streaming
# Old: blockchain.stream() might have different parameter names
# New: opNames parameter for filtering

from beem.blockchain import Blockchain

def stream_compatible():
    chain = Blockchain(blockchain_instance=hive)
    try:
        # Modern beem
        for op in chain.stream(opNames=["vote", "comment"]):
            yield op
    except TypeError:
        # Older beem might use different parameter name
        for op in chain.stream(filter_by=["vote", "comment"]):
            yield op


# CHANGE 4: Transaction building
# The TransactionBuilder API has been relatively stable,
# but import paths may have changed

def build_tx_compatible():
    """Transaction building -- check import paths."""
    try:
        from beem.transactionbuilder import TransactionBuilder
        from beembase.operations import Transfer
    except ImportError:
        # Very old beem
        from beem.transactionbuilder import TransactionBuilder
        from beembase.operationids import operations
        # Operation construction might differ

    return TransactionBuilder


# CHANGE 5: Node configuration
# Old: some versions used 'nodes' parameter
# New: uses 'node' parameter (list of URLs)

def create_hive_compatible():
    try:
        return Hive(node=["https://api.hive.blog"])
    except TypeError:
        return Hive(nodes=["https://api.hive.blog"])


# === Upgrade Compatibility Wrapper ===

class BeemCompat:
    """Compatibility wrapper for cross-version beem usage."""

    def __init__(self, nodes=None, keys=None):
        self.hive = Hive(
            node=nodes or ["https://api.hive.blog"],
            keys=keys or []
        )
        self._detect_version()

    def _detect_version(self):
        """Detect beem version for compatibility decisions."""
        import beem
        self.version = getattr(beem, "__version__", "0.0.0")
        parts = self.version.split(".")
        self.major = int(parts[0]) if parts else 0
        self.minor = int(parts[1]) if len(parts) > 1 else 0
        print(f"beem version: {self.version}")

    def get_account_balance(self, username, token):
        acc = Account(username, blockchain_instance=self.hive)
        return float(acc.get_balance("available", token))

    def get_voting_power(self, username):
        acc = Account(username, blockchain_instance=self.hive)
        return acc.get_voting_power()

    def get_hive_power(self, username):
        acc = Account(username, blockchain_instance=self.hive)
        try:
            return float(acc.get_hive_power())
        except AttributeError:
            return float(acc.get_steem_power())


# === Test Suite for Upgrade Validation ===

def run_upgrade_tests():
    """Run these tests after upgrading beem."""
    compat = BeemCompat()
    errors = []

    # Test 1: Account lookup
    try:
        bal = compat.get_account_balance("hiveio", "HIVE")
        assert isinstance(bal, float), "Balance should be float"
        print(f"  [PASS] Account balance: {bal}")
    except Exception as e:
        errors.append(f"Account balance: {e}")
        print(f"  [FAIL] Account balance: {e}")

    # Test 2: Voting power
    try:
        vp = compat.get_voting_power("hiveio")
        assert 0 <= vp <= 100, f"VP out of range: {vp}"
        print(f"  [PASS] Voting power: {vp}")
    except Exception as e:
        errors.append(f"Voting power: {e}")
        print(f"  [FAIL] Voting power: {e}")

    # Test 3: Block fetching
    try:
        chain = Blockchain(blockchain_instance=compat.hive)
        block_num = chain.get_current_block_num()
        assert block_num > 0, "Block number should be positive"
        print(f"  [PASS] Current block: {block_num}")
    except Exception as e:
        errors.append(f"Block fetch: {e}")
        print(f"  [FAIL] Block fetch: {e}")

    # Test 4: Transaction building
    try:
        from beem.transactionbuilder import TransactionBuilder
        from beembase.operations import Transfer
        tx = TransactionBuilder(blockchain_instance=compat.hive)
        tx.appendOps(Transfer(**{
            "from": "test", "to": "test2",
            "amount": "0.001 HIVE", "memo": "test"
        }))
        # Do NOT sign or broadcast -- just verify construction works
        print(f"  [PASS] Transaction building")
    except Exception as e:
        errors.append(f"Transaction building: {e}")
        print(f"  [FAIL] Transaction building: {e}")

    if errors:
        print(f"\n{len(errors)} tests failed!")
    else:
        print("\nAll tests passed!")

    return errors


# run_upgrade_tests()
```

Upgrade strategy: pin your current version in requirements.txt, create a branch for the upgrade, run the compatibility test suite, fix any failures, test against Hive testnet with real operations, then merge and deploy. Never upgrade beem in production without testing first -- subtle changes in return types or parameter names can cause silent data corruption.'''
    },
    {
        "instruction": r'''My Hive indexer uses a PostgreSQL database and I need to add new columns and tables to support additional data I want to track. How do I handle the database migration safely?''',
        "output": r'''<think>
Database migration for a Hive indexer -- this needs to be handled carefully because the indexer is likely running continuously and downtime means falling behind on blocks.

Let me think about the migration scenarios:
1. Adding a new column to an existing table
2. Adding a new table
3. Changing a column type
4. Adding indexes

For PostgreSQL specifically:
- Adding a column with a default value (in PG 11+) is instant and does not lock the table
- Adding a column without a default is also instant
- Adding an index can be done CONCURRENTLY to avoid locking
- Changing a column type requires rewriting the table (SLOW for large tables)

Hmm, the tricky part is coordinating the migration with the indexer code. If I add a new column but the indexer code does not write to it yet, the column is just NULL. If I deploy new code that writes to the column before the migration runs, the code will fail with "column does not exist."

I initially thought about using a framework like Alembic (SQLAlchemy's migration tool), but for a standalone indexer, a simpler approach might be custom migration scripts with version tracking.

The tradeoff is: migration framework (structured, reversible, but adds dependency) vs custom scripts (simple, fits the project, but manual tracking). For a Hive indexer that is typically a single service, custom migration scripts with a version table are practical.

The deployment order should be:
1. Run migration (add column/table)
2. Deploy new indexer code (writes to new column)
3. Optionally backfill old data

Never the reverse, because new code writing to non-existent columns will crash.

For large tables (millions of rows), some operations need special handling:
- Adding an index: use CREATE INDEX CONCURRENTLY
- Backfilling a column: do it in batches to avoid long locks
- Changing a type: create new column, copy data in batches, rename
</think>

Use versioned migration scripts with a migration table, and design migrations to be safe for large tables:

```python
import psycopg2
import time
import os
from datetime import datetime

DB_CONFIG = {
    "host": "localhost",
    "dbname": "hive_indexer",
    "user": "indexer",
    "password": "password"
}


class MigrationRunner:
    """Run database migrations safely for a Hive indexer."""

    def __init__(self, db_config):
        self.conn = psycopg2.connect(**db_config)
        self.conn.autocommit = False
        self._ensure_migration_table()

    def _ensure_migration_table(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT NOW(),
                    execution_time_ms INTEGER
                )
            """)
            self.conn.commit()

    def get_current_version(self):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT MAX(version) FROM schema_migrations"
            )
            row = cur.fetchone()
            return row[0] or 0

    def run_migration(self, version, name, sql_statements):
        """Run a single migration if not already applied."""
        current = self.get_current_version()
        if version <= current:
            print(f"  Skip v{version} ({name}) -- already applied")
            return False

        print(f"  Applying v{version}: {name}")
        start = time.time()

        try:
            with self.conn.cursor() as cur:
                for i, sql in enumerate(sql_statements):
                    print(f"    Statement {i+1}/{len(sql_statements)}")
                    cur.execute(sql)

                elapsed_ms = int((time.time() - start) * 1000)
                cur.execute(
                    """INSERT INTO schema_migrations
                       (version, name, execution_time_ms)
                       VALUES (%s, %s, %s)""",
                    (version, name, elapsed_ms)
                )
            self.conn.commit()
            print(f"    Done ({elapsed_ms}ms)")
            return True
        except Exception as e:
            self.conn.rollback()
            print(f"    FAILED: {e}")
            raise

    def run_migration_no_transaction(self, version, name, sql_statements):
        """Run migration outside a transaction.

        Required for operations like CREATE INDEX CONCURRENTLY
        which cannot run inside a transaction.
        """
        current = self.get_current_version()
        if version <= current:
            print(f"  Skip v{version} ({name}) -- already applied")
            return False

        print(f"  Applying v{version}: {name} (no transaction)")
        old_autocommit = self.conn.autocommit
        self.conn.autocommit = True
        start = time.time()

        try:
            with self.conn.cursor() as cur:
                for i, sql in enumerate(sql_statements):
                    print(f"    Statement {i+1}/{len(sql_statements)}")
                    cur.execute(sql)

            elapsed_ms = int((time.time() - start) * 1000)
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO schema_migrations
                       (version, name, execution_time_ms)
                       VALUES (%s, %s, %s)""",
                    (version, name, elapsed_ms)
                )
            print(f"    Done ({elapsed_ms}ms)")
            return True
        except Exception as e:
            print(f"    FAILED: {e}")
            raise
        finally:
            self.conn.autocommit = old_autocommit


# === Migration Definitions ===

def run_all_migrations(db_config):
    runner = MigrationRunner(db_config)
    print(f"Current schema version: {runner.get_current_version()}")

    # --- Migration 1: Add community tracking ---
    runner.run_migration(1, "add_community_columns", [
        # Adding columns with defaults is instant in PG 11+
        """ALTER TABLE posts
           ADD COLUMN IF NOT EXISTS community TEXT DEFAULT ''""",
        """ALTER TABLE posts
           ADD COLUMN IF NOT EXISTS community_title TEXT DEFAULT ''""",
    ])

    # --- Migration 2: Add vote value tracking ---
    runner.run_migration(2, "add_vote_value_column", [
        """ALTER TABLE votes
           ADD COLUMN IF NOT EXISTS rshares BIGINT DEFAULT 0""",
        """ALTER TABLE votes
           ADD COLUMN IF NOT EXISTS vote_value NUMERIC(15, 6) DEFAULT 0""",
    ])

    # --- Migration 3: Create rewards table ---
    runner.run_migration(3, "create_rewards_table", [
        """CREATE TABLE IF NOT EXISTS author_rewards (
               id BIGSERIAL PRIMARY KEY,
               author TEXT NOT NULL,
               permlink TEXT NOT NULL,
               hbd_payout NUMERIC(15, 3) DEFAULT 0,
               hive_payout NUMERIC(15, 3) DEFAULT 0,
               vesting_payout NUMERIC(20, 6) DEFAULT 0,
               block_num INTEGER NOT NULL,
               payout_at TIMESTAMP NOT NULL
           )""",
    ])

    # --- Migration 4: Add indexes (CONCURRENTLY = no lock) ---
    runner.run_migration_no_transaction(4, "add_performance_indexes", [
        # CONCURRENTLY prevents table locking during index creation
        # Cannot be inside a transaction block
        """CREATE INDEX CONCURRENTLY IF NOT EXISTS
           idx_posts_community ON posts(community)
           WHERE community != ''""",
        """CREATE INDEX CONCURRENTLY IF NOT EXISTS
           idx_rewards_author ON author_rewards(author)""",
        """CREATE INDEX CONCURRENTLY IF NOT EXISTS
           idx_rewards_block ON author_rewards(block_num)""",
    ])

    # --- Migration 5: Backfill community data ---
    runner.run_migration(5, "backfill_community_data", [
        # Backfill in a single UPDATE for manageable table sizes
        # For very large tables, use the batched approach below
        """UPDATE posts
           SET community = parent_permlink
           WHERE community = ''
             AND parent_author = ''
             AND parent_permlink LIKE 'hive-%%'""",
    ])

    print(f"Migrations complete. Version: {runner.get_current_version()}")


# === Batched Backfill for Large Tables ===

def backfill_large_table(db_config, batch_size=10000):
    """Backfill data in batches to avoid long locks.

    Use this for tables with millions of rows.
    """
    conn = psycopg2.connect(**db_config)

    total_updated = 0
    while True:
        with conn.cursor() as cur:
            # Process a batch using a CTE with LIMIT
            cur.execute("""
                WITH batch AS (
                    SELECT post_id FROM posts
                    WHERE community = ''
                      AND parent_author = ''
                      AND parent_permlink LIKE 'hive-%%'
                    LIMIT %s
                )
                UPDATE posts
                SET community = parent_permlink
                WHERE post_id IN (SELECT post_id FROM batch)
            """, (batch_size,))

            updated = cur.rowcount
            conn.commit()

            total_updated += updated
            print(f"Backfilled {total_updated} rows "
                  f"(batch: {updated})")

            if updated < batch_size:
                break

            # Brief pause to let other queries through
            time.sleep(0.1)

    print(f"Backfill complete: {total_updated} rows updated")


# === Safe Column Type Change ===

def safe_column_type_change(db_config):
    """Change a column type without locking the table.

    Strategy: add new column, backfill, rename, drop old.
    """
    conn = psycopg2.connect(**db_config)

    steps = [
        # Step 1: Add new column with desired type
        "ALTER TABLE votes ADD COLUMN weight_new SMALLINT",

        # Step 2: Backfill (in batches for large tables)
        """UPDATE votes SET weight_new = weight::SMALLINT
           WHERE weight_new IS NULL""",

        # Step 3: Rename columns
        "ALTER TABLE votes RENAME COLUMN weight TO weight_old",
        "ALTER TABLE votes RENAME COLUMN weight_new TO weight",

        # Step 4: Drop old column (after verifying data)
        # "ALTER TABLE votes DROP COLUMN weight_old",
    ]

    with conn.cursor() as cur:
        for step in steps:
            print(f"Executing: {step[:60]}...")
            cur.execute(step)
    conn.commit()


# Usage
run_all_migrations(DB_CONFIG)
```

Migration safety rules: always add columns as nullable or with defaults (instant in PG 11+). Use CREATE INDEX CONCURRENTLY to avoid table locks. Deploy migrations BEFORE deploying code that uses new columns. Backfill large tables in batches with brief pauses. Never change column types directly -- use the add/copy/rename pattern. Keep a version-tracked migration history so migrations are idempotent and reviewable.'''
    },
    {
        "instruction": r'''I have a Hive indexer running in production and I need to reindex all data from scratch because of a schema change. How do I do this without downtime?''',
        "output": r'''<think>
Zero-downtime reindexing -- this is a classic database migration challenge. The production indexer is running and serving queries. I need to rebuild all the data with a new schema without interrupting service.

The standard approach is "blue-green" reindexing: build the new index in parallel, then switch over. Let me think about how this works for a Hive indexer.

Option 1: Dual-write. Start writing to both old and new tables simultaneously, then backfill the new tables with historical data, then switch reads to new tables, then drop old tables.

Option 2: Parallel indexer. Run a second indexer process that writes to new tables. Once it catches up to the head block, switch the API to read from new tables.

Option 3: PostgreSQL schema trick. Create new tables in a separate schema, run the reindex into that schema, then swap schemas.

Hmm, option 2 is cleanest because it completely separates the old and new data pipelines. The old indexer keeps running and serving queries. The new indexer builds everything from scratch. When the new indexer is caught up, swap the API endpoint.

But wait, there is a catch. The new indexer needs to catch up to the current head block while the chain keeps producing new blocks. If the new indexer is slower than block production, it will never catch up. It needs to process blocks faster than 1 per 3 seconds. During backfill (processing historical blocks), this should be easy because you can batch-fetch blocks. The bottleneck is processing speed and database insert speed.

I initially thought about doing the schema migration in-place (ALTER TABLE, backfill), but for a major schema change, a full reindex is cleaner and ensures data consistency.

The tradeoff is: in-place migration (no extra resources, but risky and may need downtime) vs parallel reindex (needs extra database/compute resources during migration, but zero downtime).

Actually, I should also consider: what if the reindex takes days? The new tables need significant disk space alongside the old tables. Plan for 2x disk usage during the transition.
</think>

Use a parallel reindex strategy: build new tables alongside old ones, then swap when caught up:

```python
import psycopg2
import time
import json
from beem import Hive
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

DB_CONFIG = {
    "host": "localhost",
    "dbname": "hive_indexer",
    "user": "indexer",
    "password": "password"
}

hive = Hive(node=[
    "https://api.hive.blog",
    "https://api.deathwing.me"
])


class ZeroDowntimeReindexer:
    """Reindex all Hive data without service interruption."""

    def __init__(self, db_config):
        self.conn = psycopg2.connect(**db_config)

    def phase1_create_new_schema(self):
        """Create new tables with the updated schema.

        Using a 'new_' prefix. After swap, these become the main tables.
        """
        print("Phase 1: Creating new schema...")
        with self.conn.cursor() as cur:
            # New posts table with improved schema
            cur.execute("""
                CREATE TABLE IF NOT EXISTS new_posts (
                    post_id BIGSERIAL PRIMARY KEY,
                    author TEXT NOT NULL,
                    permlink TEXT NOT NULL,
                    parent_author TEXT DEFAULT '',
                    parent_permlink TEXT DEFAULT '',
                    title TEXT DEFAULT '',
                    body TEXT DEFAULT '',
                    community TEXT DEFAULT '',
                    category TEXT DEFAULT '',

                    -- NEW: improved payout tracking
                    author_payout_hbd NUMERIC(15, 3) DEFAULT 0,
                    author_payout_hive NUMERIC(15, 3) DEFAULT 0,
                    curator_payout_vests NUMERIC(20, 6) DEFAULT 0,
                    is_paidout BOOLEAN DEFAULT FALSE,

                    -- NEW: engagement metrics
                    net_votes INTEGER DEFAULT 0,
                    total_vote_weight BIGINT DEFAULT 0,
                    reply_count INTEGER DEFAULT 0,

                    json_metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP NOT NULL,
                    block_num INTEGER NOT NULL,
                    is_comment BOOLEAN DEFAULT FALSE,

                    UNIQUE (author, permlink)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS new_votes (
                    vote_id BIGSERIAL PRIMARY KEY,
                    post_id BIGINT,
                    voter TEXT NOT NULL,
                    author TEXT NOT NULL,
                    permlink TEXT NOT NULL,
                    weight SMALLINT NOT NULL,
                    rshares BIGINT DEFAULT 0,
                    block_num INTEGER NOT NULL,
                    voted_at TIMESTAMP NOT NULL
                )
            """)

            # Reindex state tracker
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reindex_state (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    current_block INTEGER DEFAULT 0,
                    target_block INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'running',
                    started_at TIMESTAMP DEFAULT NOW(),
                    blocks_per_second REAL DEFAULT 0
                )
            """)

            self.conn.commit()
        print("  New tables created")

    def phase2_reindex(self, start_block, end_block, batch_size=1000):
        """Reindex historical data into new tables.

        The old indexer keeps running on the old tables.
        """
        print(f"Phase 2: Reindexing blocks {start_block} to {end_block}...")

        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO reindex_state (current_block, target_block)
                   VALUES (%s, %s)
                   ON CONFLICT (id) DO UPDATE SET
                       current_block = EXCLUDED.current_block,
                       target_block = EXCLUDED.target_block,
                       status = 'running'""",
                (start_block, end_block)
            )
            self.conn.commit()

        current = start_block
        last_report = time.time()
        start_time = time.time()

        while current < end_block:
            batch_end = min(current + batch_size, end_block)

            # Fetch and process batch
            ops_buffer = []
            for block_num in range(current, batch_end):
                block = hive.rpc.get_block(block_num)
                if block is None:
                    continue

                timestamp = block.get("timestamp", "")
                for tx in block.get("transactions", []):
                    for op in tx.get("operations", []):
                        op_type = op[0] if isinstance(op, list) else op.get("type")
                        op_data = op[1] if isinstance(op, list) else op.get("value")

                        if op_type in ("comment", "vote"):
                            ops_buffer.append(
                                (block_num, timestamp, op_type, op_data)
                            )

            # Bulk insert into new tables
            self._bulk_insert_ops(ops_buffer)

            # Update progress
            current = batch_end
            elapsed = time.time() - start_time
            bps = (current - start_block) / max(elapsed, 1)

            with self.conn.cursor() as cur:
                cur.execute(
                    """UPDATE reindex_state SET
                           current_block = %s,
                           blocks_per_second = %s""",
                    (current, bps)
                )
                self.conn.commit()

            # Progress report every 30 seconds
            if time.time() - last_report > 30:
                remaining = end_block - current
                eta_hours = remaining / max(bps, 1) / 3600
                pct = (current - start_block) / (end_block - start_block) * 100
                print(f"  Block {current:,} | {pct:.1f}% | "
                      f"{bps:.0f} blk/s | ETA: {eta_hours:.1f}h")
                last_report = time.time()

        print("  Reindex complete!")

    def _bulk_insert_ops(self, ops_buffer):
        """Insert operations into new tables."""
        post_rows = []
        vote_rows = []

        for block_num, timestamp, op_type, op_data in ops_buffer:
            if op_type == "comment":
                meta = {}
                try:
                    meta = json.loads(op_data.get("json_metadata", "{}") or "{}")
                except json.JSONDecodeError:
                    pass

                is_comment = bool(op_data.get("parent_author"))
                community = ""
                if not is_comment:
                    pp = op_data.get("parent_permlink", "")
                    if pp.startswith("hive-"):
                        community = pp

                post_rows.append((
                    op_data["author"], op_data["permlink"],
                    op_data.get("parent_author", ""),
                    op_data.get("parent_permlink", ""),
                    op_data.get("title", ""),
                    op_data.get("body", ""),
                    community,
                    json.dumps(meta),
                    timestamp, block_num, is_comment
                ))

            elif op_type == "vote":
                vote_rows.append((
                    op_data.get("voter", ""),
                    op_data.get("author", ""),
                    op_data.get("permlink", ""),
                    op_data.get("weight", 0),
                    block_num, timestamp
                ))

        with self.conn.cursor() as cur:
            if post_rows:
                from psycopg2.extras import execute_values
                execute_values(cur, """
                    INSERT INTO new_posts
                    (author, permlink, parent_author, parent_permlink,
                     title, body, community, json_metadata,
                     created_at, block_num, is_comment)
                    VALUES %s
                    ON CONFLICT (author, permlink) DO UPDATE SET
                        title = EXCLUDED.title,
                        body = EXCLUDED.body
                """, post_rows)

            if vote_rows:
                from psycopg2.extras import execute_values
                execute_values(cur, """
                    INSERT INTO new_votes
                    (voter, author, permlink, weight,
                     block_num, voted_at)
                    VALUES %s
                """, vote_rows)

        self.conn.commit()

    def phase3_catch_up(self):
        """Catch up new tables to the current head block.

        At this point, the new indexer should be close to head.
        Switch to real-time mode to close the gap.
        """
        print("Phase 3: Catching up to head block...")
        with self.conn.cursor() as cur:
            cur.execute("SELECT current_block FROM reindex_state")
            current = cur.fetchone()[0]

        head = hive.rpc.get_dynamic_global_properties()["head_block_number"]
        gap = head - current
        print(f"  Gap: {gap} blocks")

        # Process remaining blocks
        self.phase2_reindex(current, head, batch_size=100)

    def phase4_swap_tables(self):
        """Atomic table swap: new becomes current, old becomes backup."""
        print("Phase 4: Swapping tables...")
        with self.conn.cursor() as cur:
            # Rename in a single transaction for atomicity
            cur.execute("ALTER TABLE posts RENAME TO old_posts")
            cur.execute("ALTER TABLE new_posts RENAME TO posts")
            cur.execute("ALTER TABLE votes RENAME TO old_votes")
            cur.execute("ALTER TABLE new_votes RENAME TO votes")

            # Add indexes to the new tables
            # (do this BEFORE swap if possible, but shown here for clarity)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_community ON posts(community)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_votes_voter ON votes(voter)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_votes_post ON votes(author, permlink)")

            cur.execute(
                "UPDATE reindex_state SET status = 'complete'"
            )

        self.conn.commit()
        print("  Tables swapped!")
        print("  Old tables available as old_posts, old_votes")
        print("  Drop them when satisfied: DROP TABLE old_posts, old_votes")

    def run_full_reindex(self, start_block, end_block):
        """Execute the full zero-downtime reindex pipeline."""
        self.phase1_create_new_schema()
        self.phase2_reindex(start_block, end_block)
        self.phase3_catch_up()
        # IMPORTANT: Stop the old indexer before swapping
        print("\n>>> Stop the old indexer process now, then press Enter <<<")
        input()
        self.phase3_catch_up()  # final catch-up
        self.phase4_swap_tables()
        print("\n>>> Start the new indexer process now <<<")


# Usage
reindexer = ZeroDowntimeReindexer(DB_CONFIG)
reindexer.run_full_reindex(
    start_block=41818752,  # Hive genesis block
    end_block=80000000     # current approximate head
)
```

The four phases: (1) create new tables alongside old ones, (2) backfill historical data into new tables while old indexer serves queries, (3) catch up the gap between backfill and head block, (4) stop old indexer, final catch-up, atomic table rename, start new indexer. Total downtime is only the few seconds of phase 4 (table rename + final catch-up). Plan for 2x disk usage during the transition period.'''
    },
    {
        "instruction": r'''I want to switch my Hive bot from using a single API node to multiple nodes with automatic failover. How do I do this without disrupting the running service?''',
        "output": r'''<think>
Adding multi-node failover to a running bot -- this needs to be done carefully to avoid disrupting an active service. Let me think about the approach.

The simplest change is updating the node list in the Hive constructor. Beem already supports multiple nodes and will try the next node on failure. But there are more sophisticated improvements to make.

Hmm, should I just update the config and restart, or implement hot-reloading of the node list? For a bot that processes blocks, a restart means a brief gap in processing (which the checkpoint system handles), so it is usually fine.

I initially thought I would need complex connection pooling, but beem handles this internally. The main things to add are: a longer node list, health checking, and node rotation.

Wait, actually there is a subtlety. If the bot is in the middle of processing a batch of blocks and the current node goes down, beem will try the next node. But if the bot is using TransactionBuilder to broadcast, and the broadcast fails mid-way, I need to check whether the transaction actually made it on-chain before retrying.

The tradeoff is: simple config update + restart (5 seconds of downtime, simple) vs live migration with no restart (no downtime, more complex). For most bots, a brief restart is fine since the checkpoint system handles the gap.

Let me provide both approaches: a simple one for most cases and a hot-reload pattern for critical services.
</think>

For most bots, updating the config and doing a graceful restart is sufficient. For critical services, use a hot-reloadable node manager:

```python
# === Approach 1: Simple Config Update (recommended for most bots) ===

# Before: single node
# hive = Hive(node=["https://api.hive.blog"], keys=["5Key"])

# After: multiple nodes with failover
# Just update your config and restart the bot

import json
import os
import signal
import time
from beem import Hive
from beem.blockchain import Blockchain

# Store node list in config file for easy updates
CONFIG_FILE = "bot_config.json"

DEFAULT_CONFIG = {
    "nodes": [
        "https://api.hive.blog",
        "https://api.deathwing.me",
        "https://api.openhive.network",
        "https://hive-api.arcange.eu",
        "https://api.c0ff33a.uk",
    ],
    "bot_account": "mybotaccount",
    "checkpoint_file": "bot_checkpoint.json"
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    # Create default config
    with open(CONFIG_FILE, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    return DEFAULT_CONFIG


# === Approach 2: Hot-Reloadable Node Manager ===
# For bots that cannot afford even brief restarts

class HotReloadableHive:
    """Hive connection manager with live node list updates."""

    def __init__(self, config_file=CONFIG_FILE):
        self.config_file = config_file
        self.config = load_config()
        self.hive = None
        self._create_instance()
        self._config_mtime = os.path.getmtime(config_file)

        # Set up SIGHUP handler for manual reload
        try:
            signal.signal(signal.SIGHUP, self._handle_sighup)
        except (AttributeError, OSError):
            pass  # Windows does not have SIGHUP

    def _create_instance(self):
        """Create a new Hive instance with current config."""
        keys = []
        posting_key = os.environ.get("HIVE_BOT_POSTING_KEY")
        if posting_key:
            keys.append(posting_key)

        self.hive = Hive(
            node=self.config["nodes"],
            keys=keys
        )
        print(f"Hive instance created with {len(self.config['nodes'])} nodes")

    def _handle_sighup(self, signum, frame):
        """Reload config on SIGHUP signal."""
        print("SIGHUP received -- reloading config")
        self.reload()

    def check_for_config_change(self):
        """Check if config file has been modified."""
        try:
            current_mtime = os.path.getmtime(self.config_file)
            if current_mtime > self._config_mtime:
                self._config_mtime = current_mtime
                return True
        except OSError:
            pass
        return False

    def reload(self):
        """Reload configuration and recreate Hive instance."""
        try:
            new_config = load_config()
            old_nodes = set(self.config.get("nodes", []))
            new_nodes = set(new_config.get("nodes", []))

            if old_nodes != new_nodes:
                added = new_nodes - old_nodes
                removed = old_nodes - new_nodes
                if added:
                    print(f"  Added nodes: {added}")
                if removed:
                    print(f"  Removed nodes: {removed}")

                self.config = new_config
                self._create_instance()
                print("  Node list updated successfully")
            else:
                self.config = new_config
                print("  Config reloaded (nodes unchanged)")

        except Exception as e:
            print(f"  Config reload failed: {e}")
            print("  Keeping current configuration")

    def get_instance(self):
        """Get the current Hive instance, checking for config changes."""
        if self.check_for_config_change():
            self.reload()
        return self.hive


# === Integration with a Running Bot ===

class ResilientBot:
    """Bot that uses hot-reloadable Hive connections."""

    def __init__(self):
        self.hive_manager = HotReloadableHive()
        self.running = True
        self.checkpoint = self._load_checkpoint()

    def _load_checkpoint(self):
        config = self.hive_manager.config
        cp_file = config.get("checkpoint_file", "bot_checkpoint.json")
        try:
            with open(cp_file, "r") as f:
                return json.load(f).get("last_block", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            return 0

    def _save_checkpoint(self, block_num):
        config = self.hive_manager.config
        cp_file = config.get("checkpoint_file", "bot_checkpoint.json")
        with open(cp_file, "w") as f:
            json.dump({"last_block": block_num,
                       "saved_at": time.time()}, f)

    def process_block(self, block_num):
        """Process a single block. Override with your bot logic."""
        hive = self.hive_manager.get_instance()
        block = hive.rpc.get_block(block_num)
        if block is None:
            return False

        # Your bot logic here
        for tx in block.get("transactions", []):
            for op in tx.get("operations", []):
                pass  # process operations

        return True

    def run(self):
        """Main loop with automatic failover and config reload."""
        current = self.checkpoint + 1
        if current <= 1:
            hive = self.hive_manager.get_instance()
            chain = Blockchain(blockchain_instance=hive)
            current = chain.get_current_block_num()

        print(f"Bot starting from block {current}")
        consecutive_errors = 0
        blocks_since_checkpoint = 0

        while self.running:
            try:
                success = self.process_block(current)

                if not success:
                    time.sleep(1)
                    continue

                current += 1
                consecutive_errors = 0
                blocks_since_checkpoint += 1

                if blocks_since_checkpoint >= 10:
                    self._save_checkpoint(current - 1)
                    blocks_since_checkpoint = 0

            except KeyboardInterrupt:
                print("Shutting down gracefully...")
                self._save_checkpoint(current - 1)
                self.running = False

            except Exception as e:
                consecutive_errors += 1
                error_msg = str(e)
                print(f"Error at block {current}: {error_msg}")

                if consecutive_errors >= 5:
                    print("5 consecutive errors -- forcing node reload")
                    self.hive_manager.reload()
                    consecutive_errors = 0

                # Exponential backoff
                wait = min(2 ** consecutive_errors, 30)
                time.sleep(wait)


# === Deployment Steps ===
#
# 1. Update bot_config.json with new node list:
#    {"nodes": ["https://api.hive.blog", "https://new-node.com", ...]}
#
# 2a. Simple approach: restart the bot
#     systemctl restart hive-bot
#
# 2b. Hot-reload approach: send SIGHUP
#     kill -HUP $(pidof python bot.py)
#     Or just save the config file -- auto-detected on next check
#
# 3. Monitor logs for successful node switching

if __name__ == "__main__":
    bot = ResilientBot()
    bot.run()
```

For most bots, the simple approach (update config, restart) is fine -- the checkpoint system ensures no blocks are missed during the brief restart. For critical services, the hot-reload pattern detects config file changes automatically and recreates the Hive instance with the new node list without stopping block processing. Consecutive errors trigger an automatic reload as a recovery mechanism.'''
    },
]
