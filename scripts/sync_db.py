#!/usr/bin/env python3
"""
Sync specific tables between WSL and Windows databases WITHOUT overwriting.

The problem: WSL DB has promoted BookSections, Windows DB has telemetry events.
Copying one over the other destroys data.

Solution: Merge only the tables that each side owns:
  - WSL → Windows: book_sections (promoted examples with embeddings)
  - Windows → WSL: telemetry_events (chat telemetry from Flask)

Usage:
    python scripts/sync_db.py --direction wsl-to-windows   # after promotion
    python scripts/sync_db.py --direction windows-to-wsl    # sync telemetry to WSL
    python scripts/sync_db.py --direction both               # bidirectional merge
"""
import argparse
import sqlite3
import os
import sys
import time

WINDOWS_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hiveai.db")
WSL_DB_VIA_MNT = "/mnt/c/Users/theyc/HiveAi/Hive-AI/hiveai.db"
WSL_DB_NATIVE = "/opt/hiveai/project/hiveai.db"


def count_rows(conn, table):
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except Exception:
        return 0


def sync_book_sections(source, target):
    """Sync book_sections from source to target (insert new, skip existing)."""
    src = sqlite3.connect(source)
    tgt = sqlite3.connect(target)

    src_count = count_rows(src, "book_sections")
    tgt_count = count_rows(tgt, "book_sections")
    print(f"  book_sections: source={src_count}, target={tgt_count}")

    if src_count <= tgt_count:
        print(f"  SKIP: target already has >= source rows")
        return 0

    # Get IDs already in target
    existing_ids = set(r[0] for r in tgt.execute("SELECT id FROM book_sections").fetchall())

    # Get all columns
    cols = [r[1] for r in src.execute("PRAGMA table_info(book_sections)").fetchall()]
    tgt_cols = [r[1] for r in tgt.execute("PRAGMA table_info(book_sections)").fetchall()]
    shared_cols = [c for c in cols if c in tgt_cols]

    # Fetch new rows from source
    rows = src.execute(f"SELECT {','.join(shared_cols)} FROM book_sections").fetchall()
    id_idx = shared_cols.index("id")

    added = 0
    placeholders = ",".join(["?" for _ in shared_cols])
    for row in rows:
        if row[id_idx] not in existing_ids:
            try:
                tgt.execute(
                    f"INSERT INTO book_sections ({','.join(shared_cols)}) VALUES ({placeholders})",
                    row,
                )
                added += 1
            except Exception as e:
                pass  # skip conflicts

    tgt.commit()
    print(f"  ADDED: {added} new book_sections")
    src.close()
    tgt.close()
    return added


def sync_telemetry(source, target):
    """Sync telemetry_events from source to target."""
    src = sqlite3.connect(source)
    tgt = sqlite3.connect(target)

    # Ensure table exists in target
    try:
        tgt.execute("SELECT COUNT(*) FROM telemetry_events")
    except Exception:
        # Create table from source schema
        schema = src.execute(
            "SELECT sql FROM sqlite_master WHERE name='telemetry_events'"
        ).fetchone()
        if schema:
            tgt.execute(schema[0])
            tgt.commit()
        else:
            print("  SKIP: telemetry_events doesn't exist in source")
            return 0

    src_count = count_rows(src, "telemetry_events")
    tgt_count = count_rows(tgt, "telemetry_events")
    print(f"  telemetry_events: source={src_count}, target={tgt_count}")

    if src_count <= tgt_count:
        print(f"  SKIP: target already has >= source rows")
        return 0

    # Get existing request_ids in target (dedup key)
    existing = set(
        r[0] for r in tgt.execute("SELECT request_id FROM telemetry_events").fetchall()
    )

    cols = [r[1] for r in src.execute("PRAGMA table_info(telemetry_events)").fetchall()]
    tgt_cols = [r[1] for r in tgt.execute("PRAGMA table_info(telemetry_events)").fetchall()]
    shared_cols = [c for c in cols if c in tgt_cols]

    req_idx = shared_cols.index("request_id") if "request_id" in shared_cols else None

    rows = src.execute(f"SELECT {','.join(shared_cols)} FROM telemetry_events").fetchall()
    added = 0
    placeholders = ",".join(["?" for _ in shared_cols])
    for row in rows:
        if req_idx is not None and row[req_idx] in existing:
            continue
        try:
            tgt.execute(
                f"INSERT INTO telemetry_events ({','.join(shared_cols)}) VALUES ({placeholders})",
                row,
            )
            added += 1
        except Exception:
            pass

    tgt.commit()
    print(f"  ADDED: {added} new telemetry_events")
    src.close()
    tgt.close()
    return added


def main():
    parser = argparse.ArgumentParser(description="Sync HiveAI databases safely")
    parser.add_argument(
        "--direction",
        choices=["wsl-to-windows", "windows-to-wsl", "both"],
        default="both",
    )
    args = parser.parse_args()

    # Both DBs accessed from Windows via filesystem paths
    on_windows = os.name == "nt"
    if on_windows:
        windows_db = WINDOWS_DB
        # Access WSL DB through \\wsl$ network path
        wsl_db = r"\\wsl$\Ubuntu-24.04\opt\hiveai\project\hiveai.db"
        if not os.path.exists(wsl_db):
            # Fallback: WSL not mounted, use the same Windows DB (no-op)
            print("WARNING: Cannot access WSL DB from Windows. Run this from WSL instead:")
            print("  cd /opt/hiveai/project && python3 scripts/sync_db.py --direction both")
            sys.exit(1)
    else:
        windows_db = WSL_DB_VIA_MNT
        wsl_db = WSL_DB_NATIVE

    print(f"Windows DB: {windows_db}")
    print(f"WSL DB: {wsl_db}")
    print(f"Direction: {args.direction}\n")

    if args.direction in ("wsl-to-windows", "both"):
        print("[WSL -> Windows] Syncing book_sections (promoted examples)...")
        sync_book_sections(wsl_db, windows_db)

    if args.direction in ("windows-to-wsl", "both"):
        print("[Windows -> WSL] Syncing telemetry_events...")
        sync_telemetry(windows_db, wsl_db)

    # Final counts
    w = sqlite3.connect(windows_db)
    print(f"\nWindows DB: {count_rows(w, 'book_sections')} sections, {count_rows(w, 'telemetry_events')} telemetry")
    w.close()

    print("Done. No data was overwritten.")


if __name__ == "__main__":
    main()
