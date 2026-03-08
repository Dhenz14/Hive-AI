"""Split v8 training data into per-category JSONL files with replay buffer mixed in.

Each category file contains:
  - All pairs from that category in v8.jsonl
  - A proportional slice of the replay buffer (40% of category size, max 300)

This ensures each category LoRA:
  1. Learns its specialty deeply (focused data)
  2. Doesn't forget general knowledge (replay buffer)

Usage:
    python scripts/prepare_category_data.py
    python scripts/prepare_category_data.py --v8 loras/training_data/v8.jsonl
"""
import argparse
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Category detection patterns — order matters (first match wins)
CATEGORY_PATTERNS = {
    "go":   r"\bgo\b|\.go\b|package\s+main|goroutine|chan\s+\w+|go\s+func|sync\.Mutex",
    "cpp":  r"\b(?:c\+\+|cpp)\b|#include\s*<|std::|template\s*<|vector<|unique_ptr",
    "rust": r"\brust\b|fn\s+main|cargo|use\s+std::|impl\s+\w+|\.rs\b|tokio::",
    "hive": r"\bhive\b|hive\s*blockchain|hive\s*api|hive\s*engine|dhive|hivejs|dpos|hbd|hive\s*power",
}

# Categories we train separately (must match keys in CATEGORY_PATTERNS)
TRAIN_CATEGORIES = ["go", "cpp", "rust", "hive"]


def detect_category(item: dict) -> str:
    """Detect primary category from metadata + content."""
    meta = item.get("metadata", {})
    source = meta.get("source", "")
    tag = meta.get("tag", "")

    # Fast path: check metadata tags first
    combined = f"{source} {tag}".lower()
    for cat in TRAIN_CATEGORIES:
        if cat in combined:
            return cat
        if cat == "cpp" and "c++" in combined:
            return cat

    # Slow path: regex on content
    text = " ".join(str(v) for v in item.values()).lower()
    for cat, pattern in CATEGORY_PATTERNS.items():
        if re.search(pattern, text):
            return cat

    return "general"


def prepare_category_data(v8_path: str, replay_path: str, output_dir: str):
    """Split v8 data by category and mix in replay buffer."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Load replay buffer
    replay = []
    rp = Path(replay_path)
    if rp.exists():
        with open(rp, "r", encoding="utf-8") as f:
            replay = [json.loads(line) for line in f if line.strip()]
        print(f"Replay buffer: {len(replay)} pairs loaded")
    else:
        print(f"WARNING: No replay buffer at {replay_path} — training without memory protection!")

    # Categorize v8 data
    category_data = {cat: [] for cat in TRAIN_CATEGORIES}
    general_count = 0

    with open(v8_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            cat = detect_category(item)
            if cat in category_data:
                category_data[cat].append(item)
            else:
                general_count += 1

    print(f"\nCategory split from {v8_path}:")
    total = sum(len(v) for v in category_data.values()) + general_count
    print(f"  Total pairs: {total} ({general_count} general/other)")

    # Write per-category files with replay mixed in
    for cat, items in category_data.items():
        # Proportional replay: 40% of category size, capped at 300
        replay_count = min(300, max(50, int(len(items) * 0.4)))
        replay_count = min(replay_count, len(replay))
        mixed = items + replay[:replay_count]

        # Safety warning
        if len(mixed) < 50:
            print(f"  WARNING: {cat.upper()} has only {len(mixed)} examples — may be unstable!")

        out_path = out / f"{cat}_with_replay.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for item in mixed:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        print(f"  {cat.upper():6s}: {len(items):4d} new + {replay_count:3d} replay = {len(mixed):4d} total -> {out_path.name}")

    return {cat: str(out / f"{cat}_with_replay.jsonl") for cat in TRAIN_CATEGORIES}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split v8 data by category with replay buffer")
    parser.add_argument("--v8", default=str(PROJECT_ROOT / "loras" / "training_data" / "v8.jsonl"))
    parser.add_argument("--replay", default=str(PROJECT_ROOT / "loras" / "training_data" / "replay_buffer.jsonl"))
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "loras" / "training_data" / "categories"))
    args = parser.parse_args()

    prepare_category_data(args.v8, args.replay, args.output_dir)
