"""Build a replay buffer from v7 training data for continual learning.

The replay buffer is a curated subset of previous training data that gets
mixed into every future training run. This prevents catastrophic forgetting
by ensuring the model always sees its most important learned examples.

Strategy: Diversity-based sampling — pick pairs that cover the widest range
of topics and languages, not just the first N.

Usage:
    python scripts/build_replay_buffer.py
    python scripts/build_replay_buffer.py --source loras/training_data/v7.jsonl --keep 500
"""
import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def detect_category(item: dict) -> str:
    """Detect the primary category of a training pair."""
    text = " ".join(str(v) for v in item.values()).lower()
    meta = item.get("metadata", {})
    source = meta.get("source", "")
    tag = meta.get("tag", "")

    # Check tag/source first (most reliable)
    combined = f"{source} {tag}".lower()
    if "hive" in combined:
        return "hive"
    if "go" in combined or "_go" in combined:
        return "go"
    if "cpp" in combined or "c++" in combined:
        return "cpp"
    if "rust" in combined:
        return "rust"
    if "javascript" in combined or "js" in combined or "typescript" in combined:
        return "javascript"

    # Fall back to content analysis
    if re.search(r"\bhive\b|hive blockchain|hive api|dhive|hivejs", text):
        return "hive"
    if re.search(r"\bpackage\s+main\b|go\s+func|goroutine|chan\s+\w+", text):
        return "go"
    if re.search(r"#include\s*<|std::|template\s*<|vector<", text):
        return "cpp"
    if re.search(r"\bfn\s+main|cargo|use\s+std::|impl\s+\w+", text):
        return "rust"
    if re.search(r"\bconst\s+\w+\s*=|async\s+function|=>\s*\{|\.tsx?\b", text):
        return "javascript"

    return "general"


def build_replay_buffer(source_path: str, output_path: str, keep: int = 500):
    """Build a diversity-sampled replay buffer."""
    print(f"Building replay buffer from {source_path}...")

    # Load all pairs
    data = []
    with open(source_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))

    print(f"  Source: {len(data)} pairs")

    # Categorize
    by_category = defaultdict(list)
    for item in data:
        cat = detect_category(item)
        by_category[cat].append(item)

    print(f"  Categories: {dict((k, len(v)) for k, v in sorted(by_category.items()))}")

    # Proportional sampling: each category gets slots proportional to its size
    # but with a minimum of 20 per category (floor guarantee)
    replay = []
    categories = sorted(by_category.keys())
    min_per_cat = min(20, keep // len(categories))
    remaining = keep

    # First pass: guarantee minimum per category
    for cat in categories:
        items = by_category[cat]
        n = min(min_per_cat, len(items))
        random.seed(42)
        sampled = random.sample(items, n)
        replay.extend(sampled)
        remaining -= n
        # Remove sampled from pool
        sampled_set = set(id(x) for x in sampled)
        by_category[cat] = [x for x in items if id(x) not in sampled_set]

    # Second pass: fill remaining proportionally
    if remaining > 0:
        total_remaining = sum(len(v) for v in by_category.values())
        for cat in categories:
            items = by_category[cat]
            if not items or total_remaining == 0:
                continue
            n = int(remaining * len(items) / total_remaining)
            n = min(n, len(items))
            sampled = random.sample(items, n)
            replay.extend(sampled)

    # Trim to exact count
    replay = replay[:keep]
    random.shuffle(replay)

    # Write
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        for item in replay:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Stats
    replay_cats = defaultdict(int)
    for item in replay:
        replay_cats[detect_category(item)] += 1

    print(f"  Replay buffer: {len(replay)} pairs -> {output_path}")
    print(f"  Distribution: {dict(sorted(replay_cats.items()))}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build diversity-sampled replay buffer")
    parser.add_argument("--source", default=str(PROJECT_ROOT / "loras" / "training_data" / "v7.jsonl"),
                        help="Source JSONL file (default: v7.jsonl)")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "loras" / "training_data" / "replay_buffer.jsonl"),
                        help="Output replay buffer path")
    parser.add_argument("--keep", type=int, default=500,
                        help="Number of pairs to keep (default: 500)")
    args = parser.parse_args()

    build_replay_buffer(args.source, args.output, args.keep)
