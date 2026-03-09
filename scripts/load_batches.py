#!/usr/bin/env python3
"""Extract ALL training pairs from distill_batches/ into a single master JSONL.

Handles both formats:
  - PAIRS = [(tag, instruction, response), ...]   (1,070+ files)
  - pairs = [{"instruction": ..., "output": ...}]  (141+ files)

Deduplicates by instruction hash, keeps longest response on collision.
Outputs clean instruction/input/output JSONL (no metadata — Unsloth-safe).

Usage:
    python scripts/load_batches.py                          # dry run (stats only)
    python scripts/load_batches.py --export                 # write master JSONL
    python scripts/load_batches.py --export --output foo.jsonl  # custom output path
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BATCH_DIR = PROJECT_ROOT / "scripts" / "distill_batches"
DEFAULT_OUTPUT = PROJECT_ROOT / "loras" / "training_data" / "batches_master.jsonl"

# Quality thresholds
MIN_INSTRUCTION_LEN = 10
MIN_RESPONSE_LEN = 50
MAX_RESPONSE_LEN = 20_000


def load_module(filepath: Path) -> object:
    """Dynamically import a batch file as a Python module."""
    spec = importlib.util.spec_from_file_location(filepath.stem, str(filepath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def extract_pairs_from_file(filepath: Path) -> list[dict]:
    """Extract training pairs from a single batch file. Handles both formats."""
    pairs = []
    try:
        mod = load_module(filepath)
    except Exception as e:
        print(f"  WARN: Failed to load {filepath.name}: {e}", file=sys.stderr)
        return []

    batch_name = filepath.stem
    batch_match = re.search(r"batch_p(\d+)", batch_name)
    batch_num = int(batch_match.group(1)) if batch_match else 0

    # Format 1: PAIRS = [(tag, instruction, response), ...]
    if hasattr(mod, "PAIRS") and isinstance(mod.PAIRS, list):
        for item in mod.PAIRS:
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                tag, instruction, response = str(item[0]), str(item[1]), str(item[2])
                pairs.append({
                    "instruction": instruction.strip(),
                    "input": "",
                    "output": response.strip(),
                    "_tag": tag,
                    "_source": batch_name,
                    "_batch_num": batch_num,
                })
            elif isinstance(item, dict):
                # Some PAIRS lists contain dicts
                inst = str(item.get("instruction", item.get("prompt", "")))
                out = str(item.get("output", item.get("response", "")))
                if inst and out:
                    pairs.append({
                        "instruction": inst.strip(),
                        "input": "",
                        "output": out.strip(),
                        "_tag": item.get("tag", batch_name),
                        "_source": batch_name,
                        "_batch_num": batch_num,
                    })

    # Format 2: pairs = [{"instruction": ..., "output": ...}, ...]
    elif hasattr(mod, "pairs") and isinstance(mod.pairs, list):
        for item in mod.pairs:
            if isinstance(item, dict):
                inst = str(item.get("instruction", item.get("prompt", "")))
                out = str(item.get("output", item.get("response", "")))
                if inst and out:
                    pairs.append({
                        "instruction": inst.strip(),
                        "input": "",
                        "output": out.strip(),
                        "_tag": item.get("tag", batch_name),
                        "_source": batch_name,
                        "_batch_num": batch_num,
                    })

    if not pairs:
        # Try any list variable that looks like training data
        for attr_name in dir(mod):
            if attr_name.startswith("_"):
                continue
            val = getattr(mod, attr_name)
            if isinstance(val, list) and len(val) > 0:
                sample = val[0]
                if isinstance(sample, dict) and ("instruction" in sample or "prompt" in sample):
                    for item in val:
                        inst = str(item.get("instruction", item.get("prompt", "")))
                        out = str(item.get("output", item.get("response", "")))
                        if inst and out:
                            pairs.append({
                                "instruction": inst.strip(),
                                "input": "",
                                "output": out.strip(),
                                "_tag": item.get("tag", batch_name),
                                "_source": batch_name,
                                "_batch_num": batch_num,
                            })
                    break

    return pairs


def quality_filter(pair: dict) -> bool:
    """Basic quality gate."""
    inst = pair["instruction"]
    out = pair["output"]
    if len(inst) < MIN_INSTRUCTION_LEN:
        return False
    if len(out) < MIN_RESPONSE_LEN:
        return False
    if len(out) > MAX_RESPONSE_LEN:
        return False
    return True


def instruction_hash(text: str) -> str:
    """MD5 hash of normalized instruction for dedup."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.md5(normalized.encode()).hexdigest()


def deduplicate(pairs: list[dict]) -> list[dict]:
    """Dedup by instruction hash, keeping longest response on collision."""
    seen = {}
    for pair in pairs:
        h = instruction_hash(pair["instruction"])
        if h not in seen or len(pair["output"]) > len(seen[h]["output"]):
            seen[h] = pair
    return list(seen.values())


def main():
    parser = argparse.ArgumentParser(description="Extract all batch file pairs into master JSONL")
    parser.add_argument("--export", action="store_true", help="Write output JSONL (default: dry run)")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="Output JSONL path")
    parser.add_argument("--batch-dir", type=str, default=str(BATCH_DIR), help="Batch files directory")
    args = parser.parse_args()

    batch_dir = Path(args.batch_dir)
    if not batch_dir.exists():
        print(f"ERROR: Batch directory not found: {batch_dir}", file=sys.stderr)
        sys.exit(1)

    # Discover all batch files
    batch_files = sorted(batch_dir.glob("batch_p*.py"))
    # Also catch any other .py files that might have pairs
    other_files = sorted(f for f in batch_dir.glob("*.py") if f not in set(batch_files) and f.name != "__init__.py")
    all_files = batch_files + other_files

    print(f"Discovered {len(all_files)} batch files ({len(batch_files)} batch_p*, {len(other_files)} other)")

    # Extract all pairs
    all_pairs = []
    source_counts = Counter()
    failed_files = []
    empty_files = []

    for filepath in all_files:
        pairs = extract_pairs_from_file(filepath)
        if pairs:
            source_counts[filepath.stem] = len(pairs)
            all_pairs.extend(pairs)
        else:
            empty_files.append(filepath.name)

    print(f"\nExtracted {len(all_pairs)} raw pairs from {len(source_counts)} files")
    if empty_files:
        print(f"  ({len(empty_files)} files had no extractable pairs)")

    # Quality filter
    before_filter = len(all_pairs)
    all_pairs = [p for p in all_pairs if quality_filter(p)]
    filtered_out = before_filter - len(all_pairs)
    print(f"Quality filter: {filtered_out} removed, {len(all_pairs)} remaining")

    # Deduplicate
    before_dedup = len(all_pairs)
    all_pairs = deduplicate(all_pairs)
    dupes_removed = before_dedup - len(all_pairs)
    print(f"Dedup: {dupes_removed} duplicates removed, {len(all_pairs)} unique pairs")

    # Stats
    has_thinking = sum(1 for p in all_pairs if "<think>" in p["output"])
    source_domain = Counter()
    for p in all_pairs:
        src = p["_source"].lower()
        if "hive" in src:
            source_domain["hive"] += 1
        elif "think" in src or "reason" in src:
            source_domain["thinking"] += 1
        elif "go_" in src or "_go" in src:
            source_domain["go"] += 1
        elif "rust" in src:
            source_domain["rust"] += 1
        elif "cpp" in src or "c++" in src:
            source_domain["cpp"] += 1
        elif "js" in src or "typescript" in src or "react" in src:
            source_domain["javascript"] += 1
        elif "python" in src or "django" in src or "flask" in src or "fastapi" in src:
            source_domain["python"] += 1
        else:
            source_domain["general"] += 1

    print(f"\n--- Domain Breakdown ---")
    for domain, count in sorted(source_domain.items(), key=lambda x: -x[1]):
        print(f"  {domain:15s}: {count:5d} pairs")
    print(f"  {'thinking':15s}: {has_thinking:5d} pairs (with <think> blocks)")

    # Top 10 largest batch files
    print(f"\n--- Top 10 Batch Files ---")
    for name, count in source_counts.most_common(10):
        print(f"  {name}: {count} pairs")

    # Export
    if args.export:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            for pair in all_pairs:
                # Strip internal metadata — clean JSONL only
                clean = {
                    "instruction": pair["instruction"],
                    "input": pair["input"],
                    "output": pair["output"],
                }
                f.write(json.dumps(clean, ensure_ascii=False) + "\n")

        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"\nExported {len(all_pairs)} pairs to {output_path} ({size_mb:.1f} MB)")
    else:
        print(f"\nDry run — use --export to write JSONL")


if __name__ == "__main__":
    main()
