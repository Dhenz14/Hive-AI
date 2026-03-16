#!/usr/bin/env python3
"""
Sync canonical JSON Schema artifacts from HivePoA into Hive-AI.

Usage:
    python scripts/sync_schemas.py /path/to/HivePoA
    python scripts/sync_schemas.py /path/to/HivePoA --force   # overwrite changed files

This script:
1. Copies all *.json schemas from HivePoA/schemas/ into hiveai/schemas/
2. Copies all fixtures from HivePoA/schemas/fixtures/ into hiveai/schemas/fixtures/
3. Computes SHA-256 hashes for every copied file
4. Writes SCHEMA_MANIFEST.json with provenance (source commit + hashes)
5. Fails if any existing file would change (unless --force)

Hive-AI treats these as vendored contract artifacts, not hand-maintained source.
Changes go to HivePoA first, then sync here.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{h}"


def get_git_head(repo_path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main():
    parser = argparse.ArgumentParser(description="Sync HivePoA schemas into Hive-AI")
    parser.add_argument("hivepoa_path", type=Path, help="Path to HivePoA repo root")
    parser.add_argument(
        "--force", action="store_true", help="Overwrite changed files without prompting"
    )
    args = parser.parse_args()

    source_schemas = args.hivepoa_path / "schemas"
    source_fixtures = source_schemas / "fixtures"

    if not source_schemas.is_dir():
        print(f"ERROR: {source_schemas} does not exist", file=sys.stderr)
        sys.exit(1)

    dest_root = Path(__file__).resolve().parent.parent / "hiveai" / "schemas"
    dest_fixtures = dest_root / "fixtures"
    dest_root.mkdir(parents=True, exist_ok=True)
    dest_fixtures.mkdir(parents=True, exist_ok=True)

    schema_files = sorted(source_schemas.glob("*.json"))
    fixture_files = sorted(source_fixtures.glob("*.json"))

    if not schema_files:
        print("ERROR: No schema files found in source", file=sys.stderr)
        sys.exit(1)

    # Check for changes before overwriting
    changed = []
    for src in schema_files + fixture_files:
        if src.parent == source_fixtures:
            dest = dest_fixtures / src.name
        else:
            dest = dest_root / src.name
        if dest.exists() and dest.read_bytes() != src.read_bytes():
            changed.append(dest.name)

    if changed and not args.force:
        print("ERROR: The following files have diverged from source:", file=sys.stderr)
        for f in changed:
            print(f"  - {f}", file=sys.stderr)
        print("\nUse --force to overwrite, or investigate the drift.", file=sys.stderr)
        sys.exit(1)

    # Copy files
    file_hashes = {}
    fixture_hashes = {}

    for src in schema_files:
        dest = dest_root / src.name
        shutil.copy2(src, dest)
        file_hashes[src.name] = sha256_file(dest)

    for src in fixture_files:
        dest = dest_fixtures / src.name
        shutil.copy2(src, dest)
        fixture_hashes[src.name] = sha256_file(dest)

    # Write manifest
    manifest = {
        "source_repo": "HivePoA",
        "source_commit": get_git_head(args.hivepoa_path),
        "schema_version": 2,
        "synced_at": __import__("datetime").date.today().isoformat(),
        "files": dict(sorted(file_hashes.items())),
        "fixtures": dict(sorted(fixture_hashes.items())),
    }

    manifest_path = dest_root / "SCHEMA_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Synced {len(file_hashes)} schemas + {len(fixture_hashes)} fixtures")
    print(f"Source: HivePoA @ {manifest['source_commit']}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
