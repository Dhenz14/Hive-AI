#!/usr/bin/env python3
"""
HiveAI v5 Data Preparation — Combine, deduplicate, filter, and curriculum-sort
all training data into a single maxed-out dataset for Qwen3.5-9B dense training.

Usage:
    python scripts/prepare_v5_data.py              # Report + generate v5.jsonl
    python scripts/prepare_v5_data.py --dry-run     # Report only, no output
"""
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "loras" / "training_data"
OUTPUT_FILE = DATA_DIR / "v5.jsonl"

# Quality gates (from config.py)
MIN_TRAINING_QUALITY = 0.70
MIN_CODE_BLOCKS = 1

# Dedup threshold — first N chars of instruction for prefix matching
DEDUP_PREFIX_LEN = 200

# Files to include (order matters — first file's version of a dupe wins)
DATA_FILES = [
    ("v4.jsonl", "v4"),              # Primary: superset of v3 + DBC + MoE
    ("v1_6.jsonl", "v1_6"),          # Extended v1
    ("v2_expanded.jsonl", "v2_exp"), # Genetic expansion of v2
    ("dbc_pairs.jsonl", "dbc"),      # Expert blockchain pairs
    ("moe_advanced_pairs.jsonl", "moe_adv"),  # ML research knowledge
    ("moe_kernel_optimization_pairs.jsonl", "moe_kern"),  # Perf optimization
    ("moe_pruning_pairs.jsonl", "moe_prune"),  # ML knowledge
]

# Hive domain detection (from distiller.py)
HIVE_STRONG_TERMS = {
    "dpos", "rc credits", "resource credits", "vest", "vesting",
    "witness", "custom_json", "dhive", "hivejs", "beem",
    "hive-engine", "splinterlands", "hive keychain", "posting key",
    "active key", "owner key", "memo key", "hive power",
    "hbd", "hive dollar", "curation", "upvote weight",
    "beneficiaries", "power up", "power down", "delegation",
    "witness vote", "proposal system", "dhf", "hive api",
    "condenser_api", "bridge", "hivemind", "hive node",
    "account_history_api", "rc_api", "broadcast",
}

HIVE_CODE_PATTERNS = [
    r"from\s+beem", r"import\s+dhive", r"broadcast\.", r"getAccounts",
    r"condenser_api", r"hive\.blog", r"@\w+/\w+",
]


def count_code_blocks(text):
    return len(re.findall(r"```", text)) // 2


def estimate_quality(pair):
    """Estimate quality for pairs missing metadata quality score."""
    output = pair.get("output", "")
    words = len(output.split())
    code_blocks = count_code_blocks(output)

    score = 0.0

    # Content depth (max 0.20)
    if words >= 1200:
        score += 0.20
    elif words >= 800:
        score += 0.18
    elif words >= 600:
        score += 0.15
    elif words >= 400:
        score += 0.12
    elif words >= 200:
        score += 0.08

    # Code presence (max 0.15)
    if code_blocks >= 3:
        score += 0.15
    elif code_blocks >= 2:
        score += 0.10
    elif code_blocks >= 1:
        score += 0.06

    # Has function/class definitions (max 0.10)
    if re.search(r"\bdef\s+\w+|class\s+\w+", output):
        score += 0.10

    # Reasoning markers (max 0.10)
    reasoning_markers = len(re.findall(
        r"\b(because|therefore|however|trade-?off|edge case|performance)\b",
        output, re.IGNORECASE
    ))
    score += min(reasoning_markers * 0.02, 0.10)

    # Structure (max 0.10)
    headers = len(re.findall(r"^#{1,3}\s", output, re.MULTILINE))
    if headers >= 2:
        score += 0.05
    lists = len(re.findall(r"^[\-\*]\s", output, re.MULTILINE))
    if lists >= 3:
        score += 0.05

    # Instruction quality (max 0.10)
    inst_words = len(pair.get("instruction", "").split())
    if inst_words >= 8:
        score += 0.10
    elif inst_words >= 4:
        score += 0.05

    # Penalties
    if words < 100:
        score -= 0.25
    elif words < 150:
        score -= 0.10
    if code_blocks < MIN_CODE_BLOCKS:
        # Check Hive exception
        text_lower = output.lower()
        is_hive = any(term in text_lower for term in HIVE_STRONG_TERMS)
        if not is_hive:
            score = min(score, 0.49)

    return round(max(0.0, min(1.0, score)), 3)


def classify_difficulty(pair):
    """Classify difficulty for pairs missing metadata."""
    output = pair.get("output", "")
    inst = pair.get("instruction", "").lower()
    code_blocks = count_code_blocks(output)
    words = len(output.split())

    # Keywords suggesting difficulty
    advanced_kw = {"decorator", "metaclass", "async", "concurrent", "distributed",
                   "optimization", "architecture", "design pattern", "microservice",
                   "consensus", "blockchain", "cryptograph", "neural", "gradient"}
    basic_kw = {"basic", "simple", "beginner", "introduction", "hello world",
                "what is", "explain", "how to"}

    inst_lower = inst
    if any(kw in inst_lower for kw in advanced_kw):
        return "expert"
    if any(kw in inst_lower for kw in basic_kw):
        return "beginner"

    # Heuristic: longer + more code = harder
    if code_blocks >= 4 and words >= 800:
        return "expert"
    if code_blocks >= 2 and words >= 400:
        return "intermediate"
    return "beginner"


def is_hive_domain(pair):
    """Check if pair is Hive blockchain domain."""
    text = (pair.get("instruction", "") + " " + pair.get("output", "")).lower()
    if any(term in text for term in HIVE_STRONG_TERMS):
        return True
    for pattern in HIVE_CODE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 60)
    print("  HiveAI v5 Data Preparation")
    print("=" * 60)

    # ── Load all data files ──
    all_pairs = []
    file_stats = []

    for filename, source_tag in DATA_FILES:
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"  SKIP: {filename} (not found)")
            continue

        pairs = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    pair = json.loads(line)
                    pair["_source_file"] = source_tag
                    pairs.append(pair)
                except json.JSONDecodeError:
                    pass

        all_pairs.extend(pairs)
        file_stats.append((filename, len(pairs)))
        print(f"  Loaded: {filename} — {len(pairs)} pairs")

    print(f"\n  Total raw: {len(all_pairs)} pairs")

    # ── Deduplicate by instruction prefix ──
    seen_prefixes = set()
    deduped = []
    dup_count = 0

    for pair in all_pairs:
        inst = pair.get("instruction", "").strip()
        prefix = inst[:DEDUP_PREFIX_LEN].lower()
        if prefix in seen_prefixes:
            dup_count += 1
            continue
        seen_prefixes.add(prefix)
        deduped.append(pair)

    print(f"  After dedup: {len(deduped)} pairs ({dup_count} duplicates removed)")

    # ── Quality filtering ──
    filtered = []
    low_quality = 0
    no_code = 0

    for pair in deduped:
        # Get quality from metadata or estimate
        meta = pair.get("metadata", {})
        quality = meta.get("quality")
        if quality is None:
            quality = estimate_quality(pair)
            if "metadata" not in pair:
                pair["metadata"] = {}
            pair["metadata"]["quality"] = quality
            pair["metadata"]["quality_estimated"] = True

        if quality < MIN_TRAINING_QUALITY:
            low_quality += 1
            continue

        # Code block gate (except Hive content)
        output = pair.get("output", "")
        if count_code_blocks(output) < MIN_CODE_BLOCKS:
            if not is_hive_domain(pair):
                no_code += 1
                continue

        filtered.append(pair)

    print(f"  After quality filter: {len(filtered)} pairs "
          f"({low_quality} low quality, {no_code} no code)")

    # ── Classify difficulty ──
    for pair in filtered:
        meta = pair.get("metadata", {})
        if not meta.get("difficulty"):
            pair["metadata"]["difficulty"] = classify_difficulty(pair)

    # ── Hive domain tagging + oversampling ──
    hive_pairs = []
    general_pairs = []

    for pair in filtered:
        if is_hive_domain(pair):
            pair["metadata"]["domain"] = "hive"
            hive_pairs.append(pair)
        else:
            pair["metadata"]["domain"] = "general"
            general_pairs.append(pair)

    # Oversample Hive pairs 2x (proven in v3)
    oversampled = general_pairs + hive_pairs + hive_pairs  # 2x Hive
    print(f"  Hive pairs: {len(hive_pairs)} (oversampled 2x)")
    print(f"  General pairs: {len(general_pairs)}")
    print(f"  After oversampling: {len(oversampled)} total")

    # ── Curriculum sort ──
    difficulty_order = {"beginner": 0, "intermediate": 1, "expert": 2}
    oversampled.sort(key=lambda p: difficulty_order.get(
        p.get("metadata", {}).get("difficulty", "intermediate"), 1
    ))

    # Count by difficulty
    diff_counts = defaultdict(int)
    for pair in oversampled:
        diff_counts[pair.get("metadata", {}).get("difficulty", "unknown")] += 1
    print(f"  Curriculum: {dict(diff_counts)}")

    # Count by source
    source_counts = defaultdict(int)
    for pair in oversampled:
        source_counts[pair.get("_source_file", "unknown")] += 1
    print(f"  Sources: {dict(source_counts)}")

    # ── Write output ──
    if not dry_run:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for pair in oversampled:
                # Remove internal tracking fields
                clean = {k: v for k, v in pair.items() if not k.startswith("_")}
                f.write(json.dumps(clean, ensure_ascii=False) + "\n")
        print(f"\n  Written: {OUTPUT_FILE}")
        print(f"  Pairs: {len(oversampled)}")
    else:
        print(f"\n  DRY RUN — would write {len(oversampled)} pairs to {OUTPUT_FILE}")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
