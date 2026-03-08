#!/usr/bin/env python3
"""Sync scripts from Windows to WSL, fixing CRLF -> LF."""
import pathlib
import os

src = pathlib.Path("/mnt/c/Users/theyc/HiveAi/Hive-AI/scripts")
dst = pathlib.Path("/opt/hiveai/project/scripts")

files = [
    "run_train_v8.sh",
    "train_v5.py",
    "prepare_category_data.py",
    "build_replay_buffer.py",
    "merge_category_loras.py",
    "training_watchdog.py",
]

for f in files:
    s = src / f
    d = dst / f
    if s.exists():
        data = s.read_bytes()
        clean = data.replace(b"\r\n", b"\n")
        d.write_bytes(clean)
        removed = data.count(b"\r\n")
        print("Synced: {} ({} CRs fixed, {} bytes)".format(f, removed, len(clean)))
    else:
        print("MISSING: {}".format(f))

# Make shell scripts executable
os.chmod(str(dst / "run_train_v8.sh"), 0o755)
print("\nAll scripts synced. Ready to launch training.")
