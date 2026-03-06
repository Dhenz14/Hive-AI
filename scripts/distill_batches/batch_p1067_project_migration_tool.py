PAIRS = [
    ("projects/migration-tool", r'''<think>
A database migration tool needs to track which migrations have been applied,
support both forward and rollback operations, and handle dependencies
between migrations. I will build a CLI-friendly system with file-based migrations.
</think>
Build a migration tool with schema versioning, file-based migration discovery, and tracking.''', r'''import hashlib
import importlib.util
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


@dataclass
class MigrationFile:
    """Represents a migration file on disk."""
    version: str
    name: str
    filepath: str
    up_fn: Optional[Callable] = None
    down_fn: Optional[Callable] = None
    checksum: str = ""
    dependencies: List[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return f"{self.version}_{self.name}"


class MigrationDiscovery:
    """Discovers migration files from a directory."""

    def __init__(self, migrations_dir: str = "migrations"):
        self._dir = Path(migrations_dir)

    def discover(self) -> List[MigrationFile]:
        """Find and load all migration files."""
        if not self._dir.exists():
            return []

        migrations = []
        for filepath in sorted(self._dir.glob("*.py")):
            if filepath.name.startswith("_"):
                continue
            migration = self._load_migration(filepath)
            if migration:
                migrations.append(migration)

        return migrations

    def _load_migration(self, filepath: Path) -> Optional[MigrationFile]:
        """Load a single migration file."""
        name = filepath.stem
        parts = name.split("_", 1)
        if len(parts) != 2:
            return None

        version = parts[0]
        description = parts[1]

        # Calculate checksum
        with open(filepath, "rb") as f:
            checksum = hashlib.md5(f.read()).hexdigest()

        # Load the module
        try:
            spec = importlib.util.spec_from_file_location(f"migration_{version}", str(filepath))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"Error loading migration {filepath}: {e}")
            return None

        up_fn = getattr(module, "up", None)
        down_fn = getattr(module, "down", None)
        deps = getattr(module, "dependencies", [])

        if not up_fn:
            return None

        return MigrationFile(
            version=version,
            name=description,
            filepath=str(filepath),
            up_fn=up_fn,
            down_fn=down_fn,
            checksum=checksum,
            dependencies=deps,
        )


class MigrationTracker:
    """Tracks applied migrations in the database."""

    TRACKING_TABLE = "_schema_migrations"

    def __init__(self, connection):
        self._conn = connection
        self._ensure_table()

    def _ensure_table(self) -> None:
        self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TRACKING_TABLE} (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT,
                applied_at REAL NOT NULL,
                execution_time_ms REAL
            )
        """)
        self._conn.commit()

    def is_applied(self, version: str) -> bool:
        row = self._conn.execute(
            f"SELECT 1 FROM {self.TRACKING_TABLE} WHERE version = ?", (version,)
        ).fetchone()
        return row is not None

    def mark_applied(self, migration: MigrationFile, execution_time_ms: float) -> None:
        self._conn.execute(
            f"INSERT INTO {self.TRACKING_TABLE} (version, name, checksum, applied_at, execution_time_ms) VALUES (?, ?, ?, ?, ?)",
            (migration.version, migration.name, migration.checksum, time.time(), execution_time_ms),
        )
        self._conn.commit()

    def mark_reverted(self, version: str) -> None:
        self._conn.execute(f"DELETE FROM {self.TRACKING_TABLE} WHERE version = ?", (version,))
        self._conn.commit()

    def get_applied(self) -> List[dict]:
        rows = self._conn.execute(
            f"SELECT version, name, checksum, applied_at FROM {self.TRACKING_TABLE} ORDER BY version"
        ).fetchall()
        return [{"version": r[0], "name": r[1], "checksum": r[2], "applied_at": r[3]} for r in rows]

    def get_last_version(self) -> Optional[str]:
        row = self._conn.execute(
            f"SELECT version FROM {self.TRACKING_TABLE} ORDER BY version DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None
'''),
    ("projects/migration-tool", r'''Implement up/down migration execution with dry-run mode, transaction support, and error handling.''', r'''import time
import sys
import traceback
from typing import List, Optional


class MigrationExecutor:
    """Executes migrations with transaction support and error handling."""

    def __init__(self, connection, tracker, discovery):
        self._conn = connection
        self._tracker = tracker
        self._discovery = discovery

    def migrate_up(
        self,
        target: Optional[str] = None,
        dry_run: bool = False,
        verbose: bool = True,
    ) -> dict:
        """Apply pending migrations up to the target version."""
        all_migrations = self._discovery.discover()
        applied = {m["version"] for m in self._tracker.get_applied()}
        pending = [m for m in all_migrations if m.version not in applied]

        if target:
            pending = [m for m in pending if m.version <= target]

        if not pending:
            if verbose:
                print("No pending migrations.")
            return {"applied": 0, "errors": 0}

        # Resolve dependency order
        pending = self._resolve_order(pending)

        applied_count = 0
        errors = 0

        for migration in pending:
            if verbose:
                action = "[DRY RUN] Would apply" if dry_run else "Applying"
                print(f"{action}: {migration.display_name}", end="")
                sys.stdout.flush()

            if dry_run:
                if verbose:
                    print(" ... skipped (dry run)")
                applied_count += 1
                continue

            start = time.perf_counter()
            try:
                # Run in a transaction
                self._conn.execute("BEGIN")
                migration.up_fn(self._conn)
                elapsed_ms = (time.perf_counter() - start) * 1000

                self._tracker.mark_applied(migration, elapsed_ms)
                self._conn.execute("COMMIT")

                if verbose:
                    print(f" ... done ({elapsed_ms:.0f}ms)")
                applied_count += 1

            except Exception as e:
                self._conn.execute("ROLLBACK")
                elapsed_ms = (time.perf_counter() - start) * 1000
                errors += 1
                if verbose:
                    print(f" ... FAILED ({elapsed_ms:.0f}ms)")
                    print(f"  Error: {e}")
                    traceback.print_exc()
                break  # Stop on first error

        return {"applied": applied_count, "errors": errors}

    def migrate_down(
        self,
        steps: int = 1,
        dry_run: bool = False,
        verbose: bool = True,
    ) -> dict:
        """Rollback the last N migrations."""
        all_migrations = self._discovery.discover()
        migration_map = {m.version: m for m in all_migrations}
        applied = self._tracker.get_applied()

        if not applied:
            if verbose:
                print("No migrations to rollback.")
            return {"reverted": 0, "errors": 0}

        to_revert = list(reversed(applied[-steps:]))
        reverted = 0
        errors = 0

        for record in to_revert:
            migration = migration_map.get(record["version"])
            if not migration:
                if verbose:
                    print(f"Warning: Migration {record['version']} not found in files")
                continue

            if not migration.down_fn:
                if verbose:
                    print(f"Warning: Migration {migration.display_name} has no down function")
                errors += 1
                break

            if verbose:
                action = "[DRY RUN] Would revert" if dry_run else "Reverting"
                print(f"{action}: {migration.display_name}", end="")
                sys.stdout.flush()

            if dry_run:
                if verbose:
                    print(" ... skipped (dry run)")
                reverted += 1
                continue

            start = time.perf_counter()
            try:
                self._conn.execute("BEGIN")
                migration.down_fn(self._conn)
                self._tracker.mark_reverted(migration.version)
                self._conn.execute("COMMIT")

                elapsed_ms = (time.perf_counter() - start) * 1000
                if verbose:
                    print(f" ... done ({elapsed_ms:.0f}ms)")
                reverted += 1

            except Exception as e:
                self._conn.execute("ROLLBACK")
                errors += 1
                if verbose:
                    print(f" ... FAILED")
                    print(f"  Error: {e}")
                break

        return {"reverted": reverted, "errors": errors}

    def _resolve_order(self, migrations: list) -> list:
        """Sort migrations respecting dependency order."""
        by_version = {m.version: m for m in migrations}
        resolved = []
        visited = set()
        visiting = set()

        def visit(version: str):
            if version in visited:
                return
            if version in visiting:
                raise ValueError(f"Circular dependency detected at {version}")
            visiting.add(version)

            migration = by_version.get(version)
            if migration:
                for dep in migration.dependencies:
                    visit(dep)
                resolved.append(migration)
                visited.add(version)
            visiting.discard(version)

        for m in migrations:
            visit(m.version)

        return resolved

    def status(self) -> List[dict]:
        """Get migration status."""
        all_migrations = self._discovery.discover()
        applied = {m["version"]: m for m in self._tracker.get_applied()}
        result = []
        for m in all_migrations:
            app = applied.get(m.version)
            result.append({
                "version": m.version,
                "name": m.name,
                "applied": app is not None,
                "applied_at": app["applied_at"] if app else None,
                "checksum_match": app["checksum"] == m.checksum if app else None,
            })
        return result
'''),
    ("projects/migration-tool", r'''Implement migration file generation with automatic diff detection between model definitions.''', r'''import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class ColumnDef:
    """Represents a database column definition."""
    def __init__(self, name: str, col_type: str, nullable: bool = True, default: Optional[str] = None, primary_key: bool = False):
        self.name = name
        self.col_type = col_type
        self.nullable = nullable
        self.default = default
        self.primary_key = primary_key

    def to_sql(self) -> str:
        parts = [self.name, self.col_type]
        if self.primary_key:
            parts.append("PRIMARY KEY")
        if not self.nullable:
            parts.append("NOT NULL")
        if self.default is not None:
            parts.append(f"DEFAULT {self.default}")
        return " ".join(parts)


class TableDef:
    """Represents a table definition for diff comparison."""
    def __init__(self, name: str, columns: Optional[List[ColumnDef]] = None):
        self.name = name
        self.columns = {c.name: c for c in (columns or [])}

    def add_column(self, col: ColumnDef) -> None:
        self.columns[col.name] = col


class SchemaDiff:
    """Computes the diff between two schema definitions."""

    def diff(self, old_tables: Dict[str, TableDef], new_tables: Dict[str, TableDef]) -> dict:
        """Compare two schemas and return the differences."""
        old_names = set(old_tables.keys())
        new_names = set(new_tables.keys())

        added_tables = new_names - old_names
        removed_tables = old_names - new_names
        common_tables = old_names & new_names

        changes = {
            "added_tables": [],
            "removed_tables": list(removed_tables),
            "modified_tables": [],
        }

        for table_name in added_tables:
            table = new_tables[table_name]
            changes["added_tables"].append({
                "name": table_name,
                "columns": [c.to_sql() for c in table.columns.values()],
            })

        for table_name in common_tables:
            old_table = old_tables[table_name]
            new_table = new_tables[table_name]
            table_changes = self._diff_table(old_table, new_table)
            if table_changes:
                changes["modified_tables"].append({
                    "name": table_name,
                    **table_changes,
                })

        return changes

    def _diff_table(self, old: TableDef, new: TableDef) -> Optional[dict]:
        old_cols = set(old.columns.keys())
        new_cols = set(new.columns.keys())

        added = new_cols - old_cols
        removed = old_cols - new_cols
        common = old_cols & new_cols

        modified = []
        for col_name in common:
            old_col = old.columns[col_name]
            new_col = new.columns[col_name]
            if old_col.to_sql() != new_col.to_sql():
                modified.append({
                    "column": col_name,
                    "old": old_col.to_sql(),
                    "new": new_col.to_sql(),
                })

        if not added and not removed and not modified:
            return None

        return {
            "added_columns": [new.columns[c].to_sql() for c in added],
            "removed_columns": list(removed),
            "modified_columns": modified,
        }


class MigrationGenerator:
    """Generates migration files from schema diffs."""

    def __init__(self, migrations_dir: str = "migrations"):
        self._dir = Path(migrations_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def generate(self, name: str, changes: dict) -> str:
        """Generate a migration file from schema changes."""
        version = time.strftime("%Y%m%d%H%M%S")
        filename = f"{version}_{name}.py"
        filepath = self._dir / filename

        up_sql = self._generate_up_sql(changes)
        down_sql = self._generate_down_sql(changes)

        content = self._render_template(version, name, up_sql, down_sql)

        with open(filepath, "w") as f:
            f.write(content)

        return str(filepath)

    def _generate_up_sql(self, changes: dict) -> List[str]:
        statements = []
        for table in changes.get("added_tables", []):
            cols = ",\n    ".join(table["columns"])
            statements.append(f"CREATE TABLE {table['name']} (\n    {cols}\n)")

        for table_name in changes.get("removed_tables", []):
            statements.append(f"DROP TABLE IF EXISTS {table_name}")

        for table in changes.get("modified_tables", []):
            for col_sql in table.get("added_columns", []):
                col_parts = col_sql.split(" ", 1)
                statements.append(f"ALTER TABLE {table['name']} ADD COLUMN {col_sql}")
            for col_name in table.get("removed_columns", []):
                statements.append(f"ALTER TABLE {table['name']} DROP COLUMN {col_name}")

        return statements

    def _generate_down_sql(self, changes: dict) -> List[str]:
        statements = []
        # Reverse of up operations
        for table in changes.get("added_tables", []):
            statements.append(f"DROP TABLE IF EXISTS {table['name']}")

        for table in changes.get("modified_tables", []):
            for col_sql in table.get("added_columns", []):
                col_name = col_sql.split(" ")[0]
                statements.append(f"ALTER TABLE {table['name']} DROP COLUMN {col_name}")

        return statements

    def _render_template(self, version: str, name: str, up_stmts: List[str], down_stmts: List[str]) -> str:
        up_code = "\n".join(f'    conn.execute("{stmt}")'for stmt in up_stmts)
        down_code = "\n".join(f'    conn.execute("{stmt}")' for stmt in down_stmts)

        if not up_code:
            up_code = "    pass  # Add migration SQL here"
        if not down_code:
            down_code = "    pass  # Add rollback SQL here"

        return f"""# Migration: {version}_{name}
# Generated at {time.strftime("%Y-%m-%d %H:%M:%S")}

dependencies = []


def up(conn):
    \"\"\"Apply this migration.\"\"\"
{up_code}


def down(conn):
    \"\"\"Rollback this migration.\"\"\"
{down_code}
"""

    def create_empty(self, name: str) -> str:
        """Create an empty migration file."""
        return self.generate(name, {})
'''),
    ("projects/migration-tool", r'''<think>
Rollback safety is critical for production databases. I need to implement
a rollback plan that can undo multiple migrations atomically, with
verification steps and backup creation before applying changes.
</think>
Implement rollback safety with backup creation, verification steps, and atomic multi-migration rollback.''', r'''import json
import os
import shutil
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional


class MigrationBackup:
    """Creates and manages database backups before migrations."""

    def __init__(self, backup_dir: str = "backups"):
        self._dir = Path(backup_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, db_path: str, label: str = "") -> str:
        """Create a backup of the database before migration."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        suffix = f"_{label}" if label else ""
        backup_name = f"backup_{timestamp}{suffix}.db"
        backup_path = self._dir / backup_name

        shutil.copy2(db_path, backup_path)
        return str(backup_path)

    def restore_backup(self, backup_path: str, db_path: str) -> None:
        """Restore a database from a backup."""
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup not found: {backup_path}")
        shutil.copy2(backup_path, db_path)

    def list_backups(self) -> List[dict]:
        """List all available backups."""
        backups = []
        for filepath in sorted(self._dir.glob("backup_*.db"), reverse=True):
            stat = filepath.stat()
            backups.append({
                "path": str(filepath),
                "name": filepath.name,
                "size_bytes": stat.st_size,
                "created_at": stat.st_mtime,
            })
        return backups

    def cleanup(self, keep_count: int = 5) -> int:
        """Remove old backups, keeping the most recent N."""
        backups = sorted(self._dir.glob("backup_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        removed = 0
        for backup in backups[keep_count:]:
            backup.unlink()
            removed += 1
        return removed


class MigrationVerifier:
    """Verifies database state before and after migrations."""

    def __init__(self, connection):
        self._conn = connection

    def get_table_list(self) -> List[str]:
        """Get list of all tables in the database."""
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]

    def get_table_schema(self, table_name: str) -> List[dict]:
        """Get column info for a table."""
        rows = self._conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return [
            {"name": r[1], "type": r[2], "nullable": not r[3], "default": r[4], "pk": bool(r[5])}
            for r in rows
        ]

    def get_row_counts(self) -> Dict[str, int]:
        """Get row counts for all tables."""
        counts = {}
        for table in self.get_table_list():
            if table.startswith("_"):
                continue
            row = self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[table] = row[0]
        return counts

    def create_snapshot(self) -> dict:
        """Create a complete schema snapshot."""
        tables = {}
        for table_name in self.get_table_list():
            tables[table_name] = {
                "columns": self.get_table_schema(table_name),
                "row_count": self._conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0],
            }
        return {"timestamp": time.time(), "tables": tables}

    def compare_snapshots(self, before: dict, after: dict) -> dict:
        """Compare two schema snapshots."""
        before_tables = set(before["tables"].keys())
        after_tables = set(after["tables"].keys())

        return {
            "added_tables": list(after_tables - before_tables),
            "removed_tables": list(before_tables - after_tables),
            "row_count_changes": {
                table: {
                    "before": before["tables"][table]["row_count"],
                    "after": after["tables"][table]["row_count"],
                }
                for table in before_tables & after_tables
                if before["tables"][table]["row_count"] != after["tables"][table]["row_count"]
            },
        }


class SafeMigrationRunner:
    """Runs migrations with safety checks and automatic rollback on failure."""

    def __init__(self, executor, db_path: str):
        self._executor = executor
        self._db_path = db_path
        self._backup = MigrationBackup()
        self._verifier = MigrationVerifier(executor._conn)

    def run_safe(
        self,
        direction: str = "up",
        steps: int = 1,
        dry_run: bool = False,
        create_backup: bool = True,
    ) -> dict:
        """Run migrations with safety checks."""
        result = {"success": False, "backup_path": None, "details": {}}

        # Create backup
        backup_path = None
        if create_backup and not dry_run:
            backup_path = self._backup.create_backup(self._db_path, label=direction)
            result["backup_path"] = backup_path
            print(f"Backup created: {backup_path}")

        # Take before snapshot
        before = self._verifier.create_snapshot()

        try:
            if direction == "up":
                details = self._executor.migrate_up(dry_run=dry_run)
            else:
                details = self._executor.migrate_down(steps=steps, dry_run=dry_run)

            result["details"] = details

            if details.get("errors", 0) > 0:
                if backup_path and not dry_run:
                    print("Errors detected. Restoring from backup...")
                    self._backup.restore_backup(backup_path, self._db_path)
                    print("Backup restored.")
                result["success"] = False
            else:
                result["success"] = True

            # Take after snapshot and compare
            if not dry_run:
                after = self._verifier.create_snapshot()
                result["changes"] = self._verifier.compare_snapshots(before, after)

        except Exception as e:
            if backup_path and not dry_run:
                print(f"Migration failed: {e}")
                print("Restoring from backup...")
                self._backup.restore_backup(backup_path, self._db_path)
                print("Backup restored.")
            result["success"] = False
            result["error"] = str(e)

        return result
'''),
    ("projects/migration-tool", r'''Build a migration CLI with commands for create, up, down, status, and rollback.''', r'''import argparse
import sqlite3
import sys
from typing import Optional


def build_cli() -> argparse.ArgumentParser:
    """Build the migration CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="migrate",
        description="Database migration tool",
    )
    parser.add_argument("--database", "-d", default="app.db", help="Database file path")
    parser.add_argument("--migrations-dir", "-m", default="migrations", help="Migrations directory")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # create
    create_parser = subparsers.add_parser("create", help="Create a new migration")
    create_parser.add_argument("name", help="Migration name (e.g., add_users_table)")

    # up
    up_parser = subparsers.add_parser("up", help="Apply pending migrations")
    up_parser.add_argument("--target", "-t", help="Target version")
    up_parser.add_argument("--dry-run", action="store_true", help="Show what would be applied")
    up_parser.add_argument("--no-backup", action="store_true", help="Skip backup creation")

    # down
    down_parser = subparsers.add_parser("down", help="Rollback migrations")
    down_parser.add_argument("--steps", "-n", type=int, default=1, help="Number of migrations to rollback")
    down_parser.add_argument("--dry-run", action="store_true", help="Show what would be reverted")

    # status
    subparsers.add_parser("status", help="Show migration status")

    # verify
    subparsers.add_parser("verify", help="Verify migration checksums")

    # backups
    backup_parser = subparsers.add_parser("backups", help="Manage backups")
    backup_parser.add_argument("action", choices=["list", "restore", "cleanup"])
    backup_parser.add_argument("--path", help="Backup path for restore")
    backup_parser.add_argument("--keep", type=int, default=5, help="Backups to keep for cleanup")

    return parser


def cmd_create(args, generator) -> int:
    """Create a new migration file."""
    filepath = generator.create_empty(args.name)
    print(f"Created migration: {filepath}")
    return 0


def cmd_status(args, executor) -> int:
    """Show migration status."""
    statuses = executor.status()
    if not statuses:
        print("No migrations found.")
        return 0

    print(f"{'Version':<16} {'Name':<30} {'Status':<10} {'Applied At':<20}")
    print("-" * 76)
    for s in statuses:
        status = "applied" if s["applied"] else "pending"
        applied = ""
        if s["applied_at"]:
            import time as t
            applied = t.strftime("%Y-%m-%d %H:%M", t.localtime(s["applied_at"]))

        checksum_warn = ""
        if s["checksum_match"] is False:
            checksum_warn = " [MODIFIED]"

        print(f"{s['version']:<16} {s['name']:<30} {status:<10} {applied:<20}{checksum_warn}")

    return 0


def cmd_up(args, runner) -> int:
    """Apply pending migrations."""
    result = runner.run_safe(
        direction="up",
        dry_run=args.dry_run,
        create_backup=not args.no_backup,
    )
    if result["success"]:
        applied = result["details"].get("applied", 0)
        print(f"\nSuccessfully applied {applied} migration(s).")
        return 0
    else:
        print(f"\nMigration failed. See errors above.")
        return 1


def cmd_down(args, runner) -> int:
    """Rollback migrations."""
    result = runner.run_safe(
        direction="down",
        steps=args.steps,
        dry_run=args.dry_run,
    )
    if result["success"]:
        reverted = result["details"].get("reverted", 0)
        print(f"\nSuccessfully reverted {reverted} migration(s).")
        return 0
    else:
        print(f"\nRollback failed. See errors above.")
        return 1


def main(argv: Optional[list] = None) -> int:
    """Main CLI entry point."""
    parser = build_cli()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    conn = sqlite3.connect(args.database)

    from .discovery import MigrationDiscovery
    from .tracker import MigrationTracker
    from .executor import MigrationExecutor
    from .generator import MigrationGenerator
    from .safety import SafeMigrationRunner

    discovery = MigrationDiscovery(args.migrations_dir)
    tracker = MigrationTracker(conn)
    executor = MigrationExecutor(conn, tracker, discovery)
    generator = MigrationGenerator(args.migrations_dir)
    runner = SafeMigrationRunner(executor, args.database)

    commands = {
        "create": lambda: cmd_create(args, generator),
        "up": lambda: cmd_up(args, runner),
        "down": lambda: cmd_down(args, runner),
        "status": lambda: cmd_status(args, executor),
    }

    handler = commands.get(args.command)
    if handler:
        return handler()

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
'''),
]
