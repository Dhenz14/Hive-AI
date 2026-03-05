#!/usr/bin/env python3
"""Generator script for distill batches p182-p189. Run once then delete."""
import os, textwrap

BASE = os.path.dirname(os.path.abspath(__file__))

def w(name, content):
    path = os.path.join(BASE, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"Wrote {name} ({len(content)} bytes)")

# This script just validates we can write. The actual files
# are written by the main process.
if __name__ == "__main__":
    print("Generator helper ready")
