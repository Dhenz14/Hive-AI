#!/usr/bin/env python3
"""
Sync canonical JSON Schema artifacts from HivePoA into Hive-AI.

Usage:
    python scripts/sync_schemas.py /path/to/HivePoA
    python scripts/sync_schemas.py /path/to/HivePoA --force       # overwrite changed files
    python scripts/sync_schemas.py /path/to/HivePoA --commit SHA  # pin to specific commit
    python scripts/sync_schemas.py /path/to/HivePoA --verify-only # CI mode: verify parity, no copy

This script:
1. Copies all *.json schemas from HivePoA/schemas/ into hiveai/schemas/
2. Copies all fixtures from HivePoA/schemas/fixtures/ into hiveai/schemas/fixtures/
3. Computes SHA-256 hashes for every copied file
4. Computes a fixture-set digest (single hash over all schemas + fixtures)
5. Writes SCHEMA_MANIFEST.json with provenance (full commit SHA + hashes + digest)
6. Fails if any existing file would change (unless --force)

In --verify-only mode (CI):
- Does NOT copy files
- Checks that vendored copies are byte-identical to source at the pinned SHA
- Verifies fixture-set digest matches SCHEMA_MANIFEST.json
- Exits non-zero on any divergence

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


def compute_fixture_set_digest(schemas_dir: Path) -> str:
    """Compute a single SHA-256 digest over all schema and fixture files.

    Deterministic: sorted filenames, filename + content concatenated, single hash.
    This changes if ANY schema or fixture file changes (content or set membership).
    """
    h = hashlib.sha256()
    # Schema files (sorted, exclude SCHEMA_MANIFEST.json)
    for f in sorted(schemas_dir.glob("*.json")):
        if f.name == "SCHEMA_MANIFEST.json":
            continue
        h.update(f.name.encode())
        h.update(f.read_bytes())
    # Fixture files (sorted)
    fixtures_dir = schemas_dir / "fixtures"
    if fixtures_dir.is_dir():
        for f in sorted(fixtures_dir.glob("*.json")):
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return f"sha256:{h.hexdigest()}"


def get_git_sha(repo_path: Path, full: bool = True) -> str:
    """Get git HEAD SHA. Full 40-char by default for immutable pinning."""
    fmt = "HEAD" if full else "--short"
    cmd = ["git", "rev-parse"]
    if not full:
        cmd.append("--short")
    cmd.append("HEAD")
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def checkout_commit(repo_path: Path, commit_sha: str) -> None:
    """Verify the repo is at the expected commit (or check it out)."""
    current = get_git_sha(repo_path, full=True)
    if current.startswith(commit_sha) or commit_sha.startswith(current):
        return  # Already at the right commit
    # Detached HEAD checkout to the pinned SHA
    subprocess.run(
        ["git", "checkout", commit_sha],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )


def verify_parity(source_dir: Path, dest_dir: Path) -> list[str]:
    """Compare source and dest files byte-for-byte. Returns list of mismatches."""
    mismatches = []

    # Check schema files
    for src in sorted(source_dir.glob("*.json")):
        dest = dest_dir / src.name
        if not dest.exists():
            mismatches.append(f"MISSING: {src.name} (in source but not vendored)")
        elif dest.read_bytes() != src.read_bytes():
            mismatches.append(f"DIVERGED: {src.name}")

    # Check fixture files
    src_fixtures = source_dir / "fixtures"
    dest_fixtures = dest_dir / "fixtures"
    if src_fixtures.is_dir():
        for src in sorted(src_fixtures.glob("*.json")):
            dest = dest_fixtures / src.name
            if not dest.exists():
                mismatches.append(f"MISSING: fixtures/{src.name}")
            elif dest.read_bytes() != src.read_bytes():
                mismatches.append(f"DIVERGED: fixtures/{src.name}")

    # Check for extra vendored files not in source
    for dest in sorted(dest_dir.glob("*.json")):
        if dest.name == "SCHEMA_MANIFEST.json":
            continue
        src = source_dir / dest.name
        if not src.exists():
            mismatches.append(f"EXTRA: {dest.name} (vendored but not in source)")

    if dest_fixtures.is_dir():
        for dest in sorted(dest_fixtures.glob("*.json")):
            src = src_fixtures / dest.name
            if not src.exists():
                mismatches.append(f"EXTRA: fixtures/{dest.name}")

    return mismatches


def main():
    parser = argparse.ArgumentParser(description="Sync HivePoA schemas into Hive-AI")
    parser.add_argument("hivepoa_path", type=Path, help="Path to HivePoA repo root")
    parser.add_argument(
        "--force", action="store_true", help="Overwrite changed files without prompting"
    )
    parser.add_argument(
        "--commit",
        type=str,
        default=None,
        help="Pin to specific HivePoA commit SHA (CI enforcement)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="CI mode: verify vendored copies match source, do not copy",
    )
    args = parser.parse_args()

    source_schemas = args.hivepoa_path / "schemas"
    source_fixtures = source_schemas / "fixtures"

    if not source_schemas.is_dir():
        print(f"ERROR: {source_schemas} does not exist", file=sys.stderr)
        sys.exit(1)

    # If --commit specified, verify or checkout to that SHA
    if args.commit:
        current_sha = get_git_sha(args.hivepoa_path, full=True)
        if not current_sha.startswith(args.commit[:12]):
            print(
                f"ERROR: HivePoA is at {current_sha[:12]} but pinned SHA is {args.commit[:12]}",
                file=sys.stderr,
            )
            print("Checkout HivePoA to the pinned commit first.", file=sys.stderr)
            sys.exit(1)

    dest_root = Path(__file__).resolve().parent.parent / "hiveai" / "schemas"
    dest_fixtures = dest_root / "fixtures"

    # --verify-only mode: compare without copying
    if args.verify_only:
        mismatches = verify_parity(source_schemas, dest_root)
        if mismatches:
            print("SCHEMA PARITY FAILURE:", file=sys.stderr)
            for m in mismatches:
                print(f"  {m}", file=sys.stderr)
            sys.exit(1)

        # Verify fixture-set digest
        manifest_path = dest_root / "SCHEMA_MANIFEST.json"
        if not manifest_path.exists():
            print("ERROR: SCHEMA_MANIFEST.json missing", file=sys.stderr)
            sys.exit(1)

        manifest = json.loads(manifest_path.read_text())
        expected_digest = manifest.get("fixture_set_digest")
        if not expected_digest:
            print("ERROR: fixture_set_digest missing from manifest", file=sys.stderr)
            sys.exit(1)

        # Compute digest from the SOURCE (canonical), not vendored
        actual_digest = compute_fixture_set_digest(source_schemas)
        if actual_digest != expected_digest:
            print(
                f"FIXTURE-SET DIGEST MISMATCH:\n"
                f"  manifest: {expected_digest}\n"
                f"  source:   {actual_digest}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Verify pinned commit if --commit provided
        if args.commit:
            manifest_sha = manifest.get("source_commit_full", "")
            if not manifest_sha.startswith(args.commit[:12]):
                print(
                    f"COMMIT MISMATCH: manifest pins {manifest_sha[:12]}, "
                    f"but --commit is {args.commit[:12]}",
                    file=sys.stderr,
                )
                sys.exit(1)

        schema_count = len(list(source_schemas.glob("*.json")))
        fixture_count = len(list(source_fixtures.glob("*.json")))
        print(f"VERIFIED: {schema_count} schemas + {fixture_count} fixtures match source")
        print(f"Digest: {actual_digest}")
        sys.exit(0)

    # Normal sync mode
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

    # Compute fixture-set digest from the destination (should match source)
    digest = compute_fixture_set_digest(dest_root)

    # Get full SHA (immutable reference)
    full_sha = get_git_sha(args.hivepoa_path, full=True)
    short_sha = get_git_sha(args.hivepoa_path, full=False)

    # Write manifest
    manifest = {
        "source_repo": "HivePoA",
        "source_commit": short_sha,
        "source_commit_full": full_sha,
        "schema_version": 2,
        "synced_at": __import__("datetime").date.today().isoformat(),
        "fixture_set_digest": digest,
        "schema_count": len(file_hashes),
        "fixture_count": len(fixture_hashes),
        "files": dict(sorted(file_hashes.items())),
        "fixtures": dict(sorted(fixture_hashes.items())),
    }

    manifest_path = dest_root / "SCHEMA_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Synced {len(file_hashes)} schemas + {len(fixture_hashes)} fixtures")
    print(f"Source: HivePoA @ {full_sha}")
    print(f"Digest: {digest}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
