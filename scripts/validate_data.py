#!/usr/bin/env python3
"""Validate training data files for common issues that crash Unsloth."""
import json
import sys
from pathlib import Path

root = Path("/opt/hiveai/project/loras/training_data/categories")
files = list(root.glob("*_with_replay.jsonl"))

if not files:
    print("No category files found!")
    sys.exit(1)

REQUIRED = {"instruction", "input", "output"}
total_issues = 0

for f in sorted(files):
    issues = []
    lines = f.read_text(encoding="utf-8").strip().split("\n")
    for i, line in enumerate(lines):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            issues.append("  Line {}: invalid JSON".format(i+1))
            continue

        # Check all required fields exist and are strings
        for key in REQUIRED:
            val = d.get(key)
            if val is None:
                issues.append("  Line {}: {} is None".format(i+1, key))
            elif not isinstance(val, str):
                issues.append("  Line {}: {} is {} not str".format(i+1, key, type(val).__name__))
            elif len(val) == 0 and key != "input":
                issues.append("  Line {}: {} is empty string".format(i+1, key))

        # Check for extra columns
        extra = set(d.keys()) - REQUIRED
        if extra:
            issues.append("  Line {}: extra columns: {}".format(i+1, extra))

    if issues:
        print("ISSUES in {}:".format(f.name))
        for issue in issues[:10]:
            print(issue)
        if len(issues) > 10:
            print("  ... and {} more".format(len(issues) - 10))
        total_issues += len(issues)
    else:
        print("OK: {} ({} rows, 3 string columns only)".format(f.name, len(lines)))

if total_issues > 0:
    print("\nTotal issues: {}".format(total_issues))
    sys.exit(1)
else:
    print("\nAll data files validated successfully.")
