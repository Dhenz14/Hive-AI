#!/usr/bin/env python3
"""Unified training data exporter for HiveAI.

Merges ALL training pair sources into a single deduplicated JSONL file:
  1. Existing JSONL files (v1-v4, dbc, moe)
  2. Batch files (472+ files in scripts/distill_batches/)

Output format (one JSON per line):
  {
    "instruction": "...",
    "input": "",
    "output": "...",
    "metadata": {"source": "...", "tag": "...", "has_thinking": true/false}
  }

Usage:
  python scripts/prepare_training_data.py                    # Dry run (stats only)
  python scripts/prepare_training_data.py --export           # Export to loras/training_data/
  python scripts/prepare_training_data.py --export --name v6 # Custom output name
"""

import argparse
import hashlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("prepare_training_data")

# Dedup threshold: instructions shorter than this are compared exactly,
# longer ones use first N chars to catch near-duplicates
DEDUP_PREFIX_LEN = 120


def _instruction_key(instruction: str) -> str:
    """Normalize instruction for dedup comparison."""
    normalized = instruction.strip().lower()
    # Use hash of full instruction for exact dedup
    return hashlib.md5(normalized.encode()).hexdigest()


def load_jsonl_pairs(jsonl_path: str) -> list[dict]:
    """Load pairs from a JSONL file."""
    pairs = []
    source = Path(jsonl_path).stem
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                instruction = data.get("instruction", "")
                output = data.get("output", data.get("response", ""))
                if not instruction or not output:
                    continue
                metadata = data.get("metadata", {})
                if isinstance(metadata, str):
                    metadata = {}
                metadata["source"] = f"jsonl/{source}"
                metadata["has_thinking"] = "<think>" in output
                pairs.append({
                    "instruction": instruction,
                    "input": data.get("input", ""),
                    "output": output,
                    "metadata": metadata,
                })
            except json.JSONDecodeError:
                continue
    return pairs


def load_batch_pairs() -> list[dict]:
    """Load pairs from all batch files in scripts/distill_batches/."""
    pairs = []
    batch_dir = PROJECT_ROOT / "scripts" / "distill_batches"
    if not batch_dir.exists():
        return pairs

    for batch_file in sorted(batch_dir.glob("batch_p*.py")):
        try:
            spec = importlib.util.spec_from_file_location("batch", str(batch_file))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            batch_pairs = getattr(mod, "PAIRS", [])
            for tag, instruction, response in batch_pairs:
                pairs.append({
                    "instruction": instruction,
                    "input": "",
                    "output": response,
                    "metadata": {
                        "source": f"batch/{batch_file.stem}",
                        "tag": tag,
                        "has_thinking": "<think>" in response,
                    },
                })
        except Exception as e:
            logger.warning(f"Failed to load {batch_file.name}: {e}")

    return pairs


def deduplicate(pairs: list[dict]) -> list[dict]:
    """Remove duplicate instructions, keeping the longest response."""
    by_key = {}
    for pair in pairs:
        key = _instruction_key(pair["instruction"])
        existing = by_key.get(key)
        if existing is None or len(pair["output"]) > len(existing["output"]):
            by_key[key] = pair

    return list(by_key.values())


def quality_filter(pairs: list[dict], min_response_len: int = 100) -> list[dict]:
    """Basic quality filters."""
    filtered = []
    for pair in pairs:
        if len(pair["output"]) < min_response_len:
            continue
        if len(pair["instruction"]) < 10:
            continue
        filtered.append(pair)
    return filtered


def main():
    parser = argparse.ArgumentParser(description="Unified training data exporter")
    parser.add_argument("--export", action="store_true", help="Export to JSONL file")
    parser.add_argument("--name", default="combined", help="Output filename (default: combined)")
    parser.add_argument("--include-old", action="store_true",
                        help="Include older JSONL versions (v1-v3). Default: only v4 + batches")
    parser.add_argument("--min-length", type=int, default=100,
                        help="Minimum response length (default: 100)")
    args = parser.parse_args()

    # Collect from all sources
    all_pairs = []

    # 1. Load JSONL files
    training_dir = PROJECT_ROOT / "loras" / "training_data"
    if training_dir.exists():
        # Always load v4 (latest comprehensive), dbc, moe
        priority_files = ["v4.jsonl", "dbc_pairs.jsonl",
                          "moe_advanced_pairs.jsonl", "moe_kernel_optimization_pairs.jsonl",
                          "moe_pruning_pairs.jsonl"]
        if args.include_old:
            priority_files.extend(["v1.jsonl", "v1_6.jsonl", "v2.jsonl",
                                   "v2_expanded.jsonl", "v3.jsonl"])

        for fname in priority_files:
            fpath = training_dir / fname
            if fpath.exists():
                pairs = load_jsonl_pairs(str(fpath))
                logger.info(f"  {fname}: {len(pairs)} pairs")
                all_pairs.extend(pairs)

    # 2. Load batch files
    batch_pairs = load_batch_pairs()
    logger.info(f"  Batch files: {len(batch_pairs)} pairs")
    all_pairs.extend(batch_pairs)

    logger.info(f"Total raw: {len(all_pairs)}")

    # 3. Deduplicate
    deduped = deduplicate(all_pairs)
    logger.info(f"After dedup: {len(deduped)} (removed {len(all_pairs) - len(deduped)})")

    # 4. Quality filter
    filtered = quality_filter(deduped, min_response_len=args.min_length)
    logger.info(f"After quality filter: {len(filtered)} (removed {len(deduped) - len(filtered)})")

    # 5. Stats
    sources = {}
    thinking_count = 0
    for pair in filtered:
        src = pair["metadata"].get("source", "unknown").split("/")[0]
        sources[src] = sources.get(src, 0) + 1
        if pair["metadata"].get("has_thinking"):
            thinking_count += 1

    print(f"\n{'='*50}")
    print(f"TRAINING DATA SUMMARY")
    print(f"{'='*50}")
    print(f"Total pairs:      {len(filtered)}")
    print(f"With <think>:     {thinking_count}")
    print(f"Without <think>:  {len(filtered) - thinking_count}")
    print(f"\nBy source:")
    for src, count in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"  {src:15s}  {count:5d}")

    # 6. Export
    if args.export:
        output_path = training_dir / f"{args.name}.jsonl"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for pair in filtered:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")
        print(f"\nExported to: {output_path}")
        print(f"File size: {output_path.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        print("\nDry run -- use --export to write JSONL file")


if __name__ == "__main__":
    main()
