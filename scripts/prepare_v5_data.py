#!/usr/bin/env python3
"""Bridge: prepare v5 training JSONL for Qwen 2.5 LoRA training.

Converts 5,500+ raw training pairs into a curriculum-ordered, mix-enforced
JSONL file ready for train_v5.py. This is the critical bridge between raw
distillation data and actual LoRA training.

What this does:
  1. Loads all pairs (JSONL files + 560+ batch files)
  2. Deduplicates by instruction hash
  3. Quality-filters (min response length, min instruction length)
  4. Classifies each pair: direct-answer vs thinking-trace
  5. Assigns curriculum phase to thinking pairs (Foundation -> Advanced -> Meta -> Autonomy)
  6. Enforces mix ratio (~72% direct / ~28% thinking)
  7. Interleaves thinking pairs by curriculum phase throughout the dataset
  8. Hive-domain pairs oversampled 2x (proven in v3)
  9. Exports as loras/training_data/v5.jsonl

Output format (one JSON per line, consumed by train_v5.py's format_prompt):
  {"instruction": "...", "input": "", "output": "...", "metadata": {...}}

train_v5.py handles chat-template application at training time using
tokenizer.apply_chat_template() with CODING_SYSTEM_PROMPT.

Usage:
  python scripts/prepare_v5_data.py                    # Dry run (stats only)
  python scripts/prepare_v5_data.py --export           # Export v5.jsonl
  python scripts/prepare_v5_data.py --export --stats   # Export + detailed stats
"""

import argparse
import hashlib
import importlib.util
import json
import logging
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("prepare_v5_data")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TARGET_THINKING_RATIO = 0.28   # 28% thinking-trace pairs
MIN_RESPONSE_LEN = 100         # Minimum response length (chars)
MAX_RESPONSE_LEN = 15000       # Maximum response length (chars) — caps verbose v4 pairs
MIN_INSTRUCTION_LEN = 10       # Minimum instruction length (chars)
SEED = 42                      # Reproducible shuffling

# Phase boundaries for thinking-trace batch files
# Derived from THINKING_CURRICULUM.md
PHASE_RANGES = {
    "foundation": (410, 499),   # p410-p420 (foundation thinking)
    "advanced":   (500, 699),   # p500-p564 (advanced reasoning)
    "meta":       (700, 799),   # p700-p791 (meta-cognition)
    "autonomy":   (800, 899),   # p800-p886 (autonomous learning)
}
PHASE_ORDER = ["foundation", "advanced", "meta", "autonomy"]

# Hive domain detection
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


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
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
            match = re.search(r"batch_p(\d+)", batch_file.stem)
            batch_num = int(match.group(1)) if match else 0

            # Support both formats: PAIRS (tag, instruction, response) tuples
            # and pairs [{"instruction": ..., "output": ...}] dicts
            batch_pairs = getattr(mod, "PAIRS", None)
            if batch_pairs is not None:
                for tag, instruction, response in batch_pairs:
                    pairs.append({
                        "instruction": instruction,
                        "input": "",
                        "output": response,
                        "metadata": {
                            "source": f"batch/{batch_file.stem}",
                            "tag": tag,
                            "has_thinking": "<think>" in response,
                            "batch_num": batch_num,
                        },
                    })
            else:
                dict_pairs = getattr(mod, "pairs", [])
                for p in dict_pairs:
                    instruction = p.get("instruction", "")
                    response = p.get("output", "")
                    pairs.append({
                        "instruction": instruction,
                        "input": "",
                        "output": response,
                        "metadata": {
                            "source": f"batch/{batch_file.stem}",
                            "tag": batch_file.stem,
                            "has_thinking": "<think>" in response,
                            "batch_num": batch_num,
                        },
                    })
        except Exception as e:
            logger.warning(f"Failed to load {batch_file.name}: {e}")

    return pairs


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------
def deduplicate(pairs: list[dict]) -> list[dict]:
    """Remove duplicate instructions, keeping the longest response."""
    by_key = {}
    for pair in pairs:
        key = hashlib.md5(pair["instruction"].strip().lower().encode()).hexdigest()
        existing = by_key.get(key)
        if existing is None or len(pair["output"]) > len(existing["output"]):
            by_key[key] = pair
    return list(by_key.values())


def quality_filter(pairs: list[dict], min_response_len: int) -> list[dict]:
    """Quality filters: min/max response length, min instruction length."""
    filtered = []
    too_short = 0
    too_long = 0
    for pair in pairs:
        if len(pair["output"]) < min_response_len:
            too_short += 1
            continue
        if len(pair["output"]) > MAX_RESPONSE_LEN:
            too_long += 1
            continue
        if len(pair["instruction"]) < MIN_INSTRUCTION_LEN:
            too_short += 1
            continue
        filtered.append(pair)
    if too_long > 0:
        logger.info(f"  Quality filter: removed {too_short} too short, {too_long} too long (>{MAX_RESPONSE_LEN} chars)")
    return filtered


def is_hive_domain(pair: dict) -> bool:
    """Check if pair is Hive blockchain domain."""
    text = (pair.get("instruction", "") + " " + pair.get("output", "")).lower()
    return any(term in text for term in HIVE_STRONG_TERMS)


def classify_phase(pair: dict) -> str | None:
    """Classify a thinking-trace pair into its curriculum phase.
    Returns None for non-thinking pairs."""
    if not pair["metadata"].get("has_thinking"):
        return None

    batch_num = pair["metadata"].get("batch_num", 0)
    if batch_num == 0:
        # JSONL-sourced thinking pairs -- treat as foundation
        return "foundation"

    for phase, (lo, hi) in PHASE_RANGES.items():
        if lo <= batch_num <= hi:
            return phase

    # Thinking pair from non-thinking batch range -- treat as foundation
    return "foundation"


def build_curriculum_order(pairs: list[dict], seed: int) -> list[dict]:
    """Order pairs for optimal curriculum learning.

    Strategy:
    - Split into direct-answer and thinking-trace pools
    - Sort thinking pairs by phase: Foundation -> Advanced -> Meta -> Autonomy
    - Oversample Hive-domain pairs 2x (proven effective in v3)
    - Interleave thinking pairs evenly throughout the direct pairs
    - Within each phase, shuffle for variety (but phase order is preserved)
    - Result: the model sees Foundation thinking early, Autonomy thinking late,
      with direct-answer pairs providing steady skill reinforcement throughout
    """
    rng = random.Random(seed)

    # Split into pools
    direct_pairs = []
    thinking_by_phase = {phase: [] for phase in PHASE_ORDER}

    for pair in pairs:
        phase = classify_phase(pair)
        if phase is None:
            direct_pairs.append(pair)
        else:
            thinking_by_phase[phase].append(pair)

    # Hive oversampling: duplicate Hive-domain direct pairs only (2x total, not per-pool)
    # Thinking pairs are NOT oversampled to avoid excessive domain bias
    hive_direct = [p for p in direct_pairs if is_hive_domain(p)]
    direct_pairs.extend(hive_direct)  # 2x Hive direct only
    logger.info(f"  Hive oversampling: +{len(hive_direct)} direct pairs")

    # Shuffle within each pool for variety
    rng.shuffle(direct_pairs)
    for phase in PHASE_ORDER:
        rng.shuffle(thinking_by_phase[phase])

    # Build ordered thinking sequence: Foundation -> Advanced -> Meta -> Autonomy
    thinking_ordered = []
    for phase in PHASE_ORDER:
        thinking_ordered.extend(thinking_by_phase[phase])

    n_direct = len(direct_pairs)
    n_thinking = len(thinking_ordered)
    total = n_direct + n_thinking

    logger.info(f"  Direct pairs:   {n_direct}")
    logger.info(f"  Thinking pairs: {n_thinking}")
    for phase in PHASE_ORDER:
        logger.info(f"    {phase:12s}: {len(thinking_by_phase[phase])}")

    # Check mix ratio
    actual_ratio = n_thinking / total if total > 0 else 0
    logger.info(f"  Thinking ratio: {actual_ratio:.1%} (target: {TARGET_THINKING_RATIO:.0%})")

    if actual_ratio > TARGET_THINKING_RATIO + 0.05:
        # Too many thinking pairs -- downsample proportionally per phase
        target_thinking = int(n_direct * TARGET_THINKING_RATIO / (1 - TARGET_THINKING_RATIO))
        logger.info(f"  Downsampling thinking: {n_thinking} -> {target_thinking}")
        phase_counts = {p: len(thinking_by_phase[p]) for p in PHASE_ORDER}
        phase_total = sum(phase_counts.values())
        thinking_ordered = []
        for phase in PHASE_ORDER:
            phase_target = max(1, int(target_thinking * phase_counts[phase] / phase_total))
            thinking_ordered.extend(thinking_by_phase[phase][:phase_target])
        n_thinking = len(thinking_ordered)
        total = n_direct + n_thinking

    # Interleave: distribute thinking pairs evenly through direct pairs
    # Thinking pairs maintain curriculum order but are spaced so the model
    # alternates between practice and reasoning throughout training
    if n_thinking == 0:
        return direct_pairs

    result = []
    direct_idx = 0
    thinking_idx = 0

    for i in range(total):
        if thinking_idx < n_thinking:
            next_thinking_pos = thinking_idx * (total / n_thinking)
            if i >= next_thinking_pos:
                result.append(thinking_ordered[thinking_idx])
                thinking_idx += 1
                continue

        if direct_idx < n_direct:
            result.append(direct_pairs[direct_idx])
            direct_idx += 1
        elif thinking_idx < n_thinking:
            result.append(thinking_ordered[thinking_idx])
            thinking_idx += 1

    # Append any remaining
    while direct_idx < n_direct:
        result.append(direct_pairs[direct_idx])
        direct_idx += 1
    while thinking_idx < n_thinking:
        result.append(thinking_ordered[thinking_idx])
        thinking_idx += 1

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Prepare v5 training data for Qwen 2.5 LoRA")
    parser.add_argument("--export", action="store_true", help="Export to loras/training_data/v5.jsonl")
    parser.add_argument("--dry-run", action="store_true", help="Alias for default (no export)")
    parser.add_argument("--stats", action="store_true", help="Print detailed statistics")
    parser.add_argument("--include-old", action="store_true",
                        help="Include older JSONL versions (v1-v3)")
    parser.add_argument("--min-length", type=int, default=MIN_RESPONSE_LEN,
                        help=f"Minimum response length (default: {MIN_RESPONSE_LEN})")
    parser.add_argument("--seed", type=int, default=SEED, help=f"Random seed (default: {SEED})")
    args = parser.parse_args()

    all_pairs = []

    # 1. Load JSONL files
    training_dir = PROJECT_ROOT / "loras" / "training_data"
    if training_dir.exists():
        priority_files = ["v4.jsonl", "dbc_pairs.jsonl",
                          "moe_advanced_pairs.jsonl", "moe_kernel_optimization_pairs.jsonl",
                          "moe_pruning_pairs.jsonl", "v8_research_pairs.jsonl",
                          "v8_go_cpp_pairs.jsonl"]
        if args.include_old:
            priority_files.extend(["v1.jsonl", "v1_6.jsonl", "v2.jsonl",
                                   "v2_expanded.jsonl", "v3.jsonl"])

        for fname in priority_files:
            fpath = training_dir / fname
            if fpath.exists():
                pairs = load_jsonl_pairs(str(fpath))
                logger.info(f"  {fname}: {len(pairs)} pairs")
                all_pairs.extend(pairs)

    # 2. Load batch files (560+ files, including all thinking-trace curriculum)
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

    # 5. Curriculum ordering + mix enforcement + Hive oversampling
    logger.info("Building curriculum order...")
    ordered = build_curriculum_order(filtered, seed=args.seed)

    # 6. Summary
    thinking_count = sum(1 for p in ordered if p["metadata"].get("has_thinking"))
    direct_count = len(ordered) - thinking_count

    print(f"\n{'='*60}")
    print(f"  HIVE AI v5 TRAINING DATA -- Bridge Output")
    print(f"{'='*60}")
    print(f"  Target model:     Qwen 2.5 (LoRA fine-tune)")
    print(f"  Total pairs:      {len(ordered)}")
    print(f"  Direct-answer:    {direct_count} ({direct_count/len(ordered):.0%})")
    print(f"  Thinking-trace:   {thinking_count} ({thinking_count/len(ordered):.0%})")
    print(f"  Curriculum order: Foundation -> Advanced -> Meta -> Autonomy")
    print(f"  Mix strategy:     Thinking pairs interleaved throughout")

    if args.stats:
        sources = defaultdict(int)
        phases = defaultdict(int)
        for pair in ordered:
            src = pair["metadata"].get("source", "unknown").split("/")[0]
            sources[src] += 1
            phase = classify_phase(pair)
            phases[phase or "direct"] += 1

        print(f"\n  By source:")
        for src, count in sorted(sources.items(), key=lambda x: -x[1]):
            print(f"    {src:15s}  {count:5d}")

        print(f"\n  By curriculum phase:")
        for phase in ["direct"] + PHASE_ORDER:
            print(f"    {phase:15s}  {phases[phase]:5d}")

        # Verify ordering: check positions of first/last thinking per phase
        print(f"\n  First 5 pairs:")
        for i, p in enumerate(ordered[:5]):
            phase = classify_phase(p) or "direct"
            print(f"    [{i}] {phase:12s} {p['instruction'][:60]}...")

        print(f"\n  Last 5 pairs:")
        for i, p in enumerate(ordered[-5:]):
            phase = classify_phase(p) or "direct"
            idx = len(ordered) - 5 + i
            print(f"    [{idx}] {phase:12s} {p['instruction'][:60]}...")

    # 7. Export
    if args.export:
        output_path = training_dir / "v5.jsonl"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            for pair in ordered:
                # Clean metadata for export (remove internal fields)
                export_meta = {k: v for k, v in pair["metadata"].items()
                               if k != "batch_num"}
                row = {
                    "instruction": pair["instruction"],
                    "input": pair["input"],
                    "output": pair["output"],
                    "metadata": export_meta,
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        size_mb = output_path.stat().st_size / 1024 / 1024
        print(f"\n  Exported to: {output_path}")
        print(f"  File size:   {size_mb:.1f} MB")
        print(f"  Ready for:   python scripts/train_v5.py")
    else:
        print(f"\n  Dry run -- use --export to write v5.jsonl")

    print(f"{'='*60}")


if __name__ == "__main__":
    main()
