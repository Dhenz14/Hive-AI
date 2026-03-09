#!/usr/bin/env python3
"""Master Data Pipeline — consolidate ALL training data sources into one dataset.

Sources (in priority order):
  1. Distill batches (1,210+ batch_p*.py files)        → load_batches.py
  2. Skill modules (15 SKILL.md files)                  → skills_to_pairs.py
  3. Public reasoning datasets (HF)                     → fetch_reasoning_data.py
  4. Existing training data (v1-v9 JSONL)               → loras/training_data/
  5. Replay buffers (per-domain JSONL)                   → replay/
  6. Datasets (thinking_pairs, hive_data)                → datasets/
  7. Mined pairs (from multi-provider miner)             → mined_pairs.jsonl
  8. Weakness patches (eval-driven pair gen)             → weakness_patches/
  9. Self-improve candidates                             → self_improve/candidates.jsonl

Pipeline: discover → extract → normalize → dedup → quality filter → domain balance → export

Usage:
    python scripts/build_training_dataset.py                     # dry run (stats)
    python scripts/build_training_dataset.py --export            # build master dataset
    python scripts/build_training_dataset.py --export --no-old   # skip v1-v7 archives
    python scripts/build_training_dataset.py --sources batches,skills,datasets  # subset
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "loras" / "training_data" / "master_dataset.jsonl"

# Quality thresholds
MIN_INSTRUCTION_LEN = 10
MIN_RESPONSE_LEN = 50
MAX_RESPONSE_LEN = 20_000

# All available sources
ALL_SOURCES = [
    "batches",      # distill_batches/ (load_batches.py)
    "skills",       # skills/ (skills_to_pairs.py)
    "datasets",     # datasets/*.jsonl
    "replay",       # replay/*.jsonl
    "training",     # loras/training_data/v*.jsonl (latest only by default)
    "mined",        # loras/training_data/mined_pairs.jsonl
    "weakness",     # loras/training_data/weakness_patches/
    "self_improve",  # loras/training_data/self_improve/candidates.jsonl
    "reasoning",    # public reasoning datasets (fetch_reasoning_data.py)
]


def instruction_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.md5(normalized.encode()).hexdigest()


def quality_filter(pair: dict) -> bool:
    inst = pair.get("instruction", "")
    out = pair.get("output", "")
    if len(inst) < MIN_INSTRUCTION_LEN:
        return False
    if len(out) < MIN_RESPONSE_LEN:
        return False
    if len(out) > MAX_RESPONSE_LEN:
        return False
    return True


def load_jsonl(filepath: Path) -> list[dict]:
    """Load a JSONL file, skip malformed lines."""
    pairs = []
    if not filepath.exists():
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "instruction" in obj:
                    pairs.append({
                        "instruction": str(obj["instruction"]).strip(),
                        "input": str(obj.get("input", "")).strip(),
                        "output": str(obj.get("output", obj.get("response", ""))).strip(),
                        "_source": filepath.stem,
                    })
            except json.JSONDecodeError:
                pass  # skip malformed
    return pairs


def detect_domain(pair: dict) -> str:
    """Detect domain from instruction + output content."""
    text = (pair.get("instruction", "") + " " + pair.get("output", "")[:500]).lower()
    if any(k in text for k in ["hive", "dhive", "beem", "hivemind", "splinterlands", "hive-engine"]):
        return "hive"
    if any(k in text for k in ["goroutine", "go func", "golang", "chan ", "sync.mutex"]):
        return "go"
    if any(k in text for k in ["rust", "cargo", "tokio", "async fn", "impl ", "borrow checker"]):
        return "rust"
    if any(k in text for k in ["c++", "cpp", "std::", "template<", "unique_ptr", "#include"]):
        return "cpp"
    if any(k in text for k in ["typescript", "react", "node.js", "javascript", "useState", "npm "]):
        return "javascript"
    if any(k in text for k in ["python", "django", "flask", "fastapi", "def ", "import "]):
        return "python"
    if "<think>" in text:
        return "thinking"
    return "general"


# ─── Source Loaders ───────────────────────────────────────────────────────

def load_batches(verbose: bool = True) -> list[dict]:
    """Load all distill batch files via load_batches.py."""
    tmp_output = PROJECT_ROOT / "loras" / "training_data" / "_tmp_batches.jsonl"
    script = PROJECT_ROOT / "scripts" / "load_batches.py"

    if verbose:
        print("  [batches] Extracting distill batch files...")

    result = subprocess.run(
        [sys.executable, str(script), "--export", "--output", str(tmp_output)],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )

    if result.returncode != 0:
        print(f"  WARN: load_batches.py failed: {result.stderr[:200]}", file=sys.stderr)
        return []

    pairs = load_jsonl(tmp_output)
    for p in pairs:
        p["_source"] = "batches"

    # Cleanup temp file
    tmp_output.unlink(missing_ok=True)

    if verbose:
        print(f"  [batches] {len(pairs)} pairs extracted")
    return pairs


def load_skills(verbose: bool = True) -> list[dict]:
    """Load skill module pairs via skills_to_pairs.py."""
    tmp_output = PROJECT_ROOT / "loras" / "training_data" / "_tmp_skills.jsonl"
    script = PROJECT_ROOT / "scripts" / "skills_to_pairs.py"

    if verbose:
        print("  [skills] Converting SKILL.md files to pairs...")

    result = subprocess.run(
        [sys.executable, str(script), "--export", "--output", str(tmp_output)],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )

    if result.returncode != 0:
        print(f"  WARN: skills_to_pairs.py failed: {result.stderr[:200]}", file=sys.stderr)
        return []

    pairs = load_jsonl(tmp_output)
    for p in pairs:
        p["_source"] = "skills"

    tmp_output.unlink(missing_ok=True)

    if verbose:
        print(f"  [skills] {len(pairs)} pairs extracted")
    return pairs


def load_datasets(verbose: bool = True) -> list[dict]:
    """Load datasets/*.jsonl (thinking_pairs, hive_data, etc.)."""
    datasets_dir = PROJECT_ROOT / "datasets"
    all_pairs = []

    if not datasets_dir.exists():
        return []

    for filepath in sorted(datasets_dir.glob("*.jsonl")):
        pairs = load_jsonl(filepath)
        for p in pairs:
            p["_source"] = f"datasets/{filepath.stem}"
        all_pairs.extend(pairs)
        if verbose:
            print(f"  [datasets] {filepath.name}: {len(pairs)} pairs")

    return all_pairs


def load_replay(verbose: bool = True) -> list[dict]:
    """Load replay/*.jsonl (per-domain replay buffers)."""
    replay_dir = PROJECT_ROOT / "replay"
    all_pairs = []

    if not replay_dir.exists():
        return []

    for filepath in sorted(replay_dir.glob("*.jsonl")):
        if filepath.name == "sampled.jsonl":
            continue  # Skip ephemeral sampled file
        pairs = load_jsonl(filepath)
        for p in pairs:
            p["_source"] = f"replay/{filepath.stem}"
        all_pairs.extend(pairs)
        if verbose:
            print(f"  [replay] {filepath.name}: {len(pairs)} pairs")

    return all_pairs


def load_training_data(include_old: bool = False, verbose: bool = True) -> list[dict]:
    """Load versioned training data (latest version only by default)."""
    td_dir = PROJECT_ROOT / "loras" / "training_data"
    all_pairs = []

    if not td_dir.exists():
        return []

    # Find all version files
    version_files = sorted(td_dir.glob("v*.jsonl"), key=lambda f: f.name)

    if not include_old and version_files:
        # Only load the latest version + any special files
        latest = version_files[-1]
        version_files = [latest]

    for filepath in version_files:
        # Skip generated files
        if filepath.name in ("master_dataset.jsonl", "batches_master.jsonl",
                              "skills_pairs.jsonl", "mined_pairs.jsonl",
                              "replay_buffer.jsonl"):
            continue
        pairs = load_jsonl(filepath)
        for p in pairs:
            p["_source"] = f"training/{filepath.stem}"
        all_pairs.extend(pairs)
        if verbose:
            print(f"  [training] {filepath.name}: {len(pairs)} pairs")

    # Also load special files
    for special in ["dbc_pairs.jsonl", "moe_advanced_pairs.jsonl",
                     "moe_kernel_optimization_pairs.jsonl", "moe_pruning_pairs.jsonl",
                     "v9_research_pairs.jsonl"]:
        filepath = td_dir / special
        if filepath.exists():
            pairs = load_jsonl(filepath)
            for p in pairs:
                p["_source"] = f"training/{filepath.stem}"
            all_pairs.extend(pairs)
            if verbose and pairs:
                print(f"  [training] {filepath.name}: {len(pairs)} pairs")

    return all_pairs


def load_mined(verbose: bool = True) -> list[dict]:
    """Load mined pairs from multi-provider miner."""
    filepath = PROJECT_ROOT / "loras" / "training_data" / "mined_pairs.jsonl"
    if not filepath.exists():
        if verbose:
            print("  [mined] No mined_pairs.jsonl found (run run_miner.py first)")
        return []

    pairs = load_jsonl(filepath)
    for p in pairs:
        p["_source"] = "mined"

    if verbose:
        print(f"  [mined] {len(pairs)} pairs")
    return pairs


def load_weakness_patches(verbose: bool = True) -> list[dict]:
    """Load eval-driven weakness patches."""
    patch_dir = PROJECT_ROOT / "loras" / "training_data" / "weakness_patches"
    all_pairs = []

    if not patch_dir.exists():
        if verbose:
            print("  [weakness] No weakness_patches/ found (run weakness_hunter.py first)")
        return []

    for filepath in sorted(patch_dir.glob("*.jsonl")):
        pairs = load_jsonl(filepath)
        for p in pairs:
            p["_source"] = f"weakness/{filepath.stem}"
        all_pairs.extend(pairs)

    if verbose:
        print(f"  [weakness] {len(all_pairs)} pairs from {len(list(patch_dir.glob('*.jsonl')))} patches")
    return all_pairs


def load_self_improve(verbose: bool = True) -> list[dict]:
    """Load self-improvement candidates."""
    filepath = PROJECT_ROOT / "loras" / "training_data" / "self_improve" / "candidates.jsonl"
    if not filepath.exists():
        if verbose:
            print("  [self_improve] No candidates.jsonl found (run self_improve.py first)")
        return []

    pairs = load_jsonl(filepath)
    for p in pairs:
        p["_source"] = "self_improve"

    if verbose:
        print(f"  [self_improve] {len(pairs)} pairs")
    return pairs


def load_reasoning(verbose: bool = True) -> list[dict]:
    """Check for reasoning dataset batches created by fetch_reasoning_data.py."""
    batch_dir = PROJECT_ROOT / "scripts" / "distill_batches"
    reasoning_files = sorted(batch_dir.glob("batch_p*_reasoning*.py"))

    if not reasoning_files:
        if verbose:
            print("  [reasoning] No reasoning batches found (run fetch_reasoning_data.py --pipeline first)")
        return []

    # These are loaded by load_batches() already
    if verbose:
        print(f"  [reasoning] {len(reasoning_files)} reasoning batch files (loaded via batches source)")
    return []  # Avoid double-counting — loaded by batches


# ─── Main Pipeline ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Master data pipeline — consolidate all sources")
    parser.add_argument("--export", action="store_true", help="Write master dataset JSONL")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    parser.add_argument("--sources", type=str, default=",".join(ALL_SOURCES),
                        help=f"Comma-separated sources ({','.join(ALL_SOURCES)})")
    parser.add_argument("--no-old", action="store_true", help="Skip v1-v7 training archives")
    parser.add_argument("--hive-boost", type=float, default=2.0,
                        help="Oversample Hive pairs by this factor (default 2x)")
    parser.add_argument("--thinking-ratio", type=float, default=0.4,
                        help="Target ratio of thinking pairs (default 0.4)")
    args = parser.parse_args()

    active_sources = set(args.sources.lower().split(","))
    print(f"=== Master Data Pipeline ===")
    print(f"Active sources: {', '.join(sorted(active_sources))}")
    print()

    # ─── Phase 1: Discover & Load ─────────────────────────────────────
    print("Phase 1: Loading sources...")
    all_pairs = []
    source_stats = {}

    source_loaders = {
        "batches": load_batches,
        "skills": load_skills,
        "datasets": load_datasets,
        "replay": load_replay,
        "training": lambda verbose=True: load_training_data(include_old=not args.no_old, verbose=verbose),
        "mined": load_mined,
        "weakness": load_weakness_patches,
        "self_improve": load_self_improve,
        "reasoning": load_reasoning,
    }

    for source_name, loader in source_loaders.items():
        if source_name not in active_sources:
            continue
        pairs = loader(verbose=True)
        source_stats[source_name] = len(pairs)
        all_pairs.extend(pairs)

    print(f"\nPhase 1 complete: {len(all_pairs)} raw pairs from {len(source_stats)} sources")

    # ─── Phase 2: Quality Filter ──────────────────────────────────────
    print("\nPhase 2: Quality filtering...")
    before = len(all_pairs)
    all_pairs = [p for p in all_pairs if quality_filter(p)]
    print(f"  Removed {before - len(all_pairs)} low-quality pairs, {len(all_pairs)} remaining")

    # ─── Phase 3: Deduplicate ─────────────────────────────────────────
    print("\nPhase 3: Deduplicating...")
    seen = {}
    for pair in all_pairs:
        h = instruction_hash(pair["instruction"])
        if h not in seen or len(pair["output"]) > len(seen[h]["output"]):
            seen[h] = pair
    before = len(all_pairs)
    all_pairs = list(seen.values())
    print(f"  Removed {before - len(all_pairs)} duplicates, {len(all_pairs)} unique pairs")

    # ─── Phase 4: Domain Analysis ─────────────────────────────────────
    print("\nPhase 4: Domain analysis...")
    domain_counts = Counter()
    thinking_count = 0
    for pair in all_pairs:
        domain = detect_domain(pair)
        domain_counts[domain] += 1
        if "<think>" in pair.get("output", ""):
            thinking_count += 1

    print(f"\n  {'Domain':15s} {'Count':>7s} {'Pct':>6s}")
    print(f"  {'-'*30}")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        pct = count / len(all_pairs) * 100
        print(f"  {domain:15s} {count:7d} {pct:5.1f}%")
    print(f"  {'-'*30}")
    print(f"  {'TOTAL':15s} {len(all_pairs):7d}")
    print(f"  Thinking pairs: {thinking_count} ({thinking_count/len(all_pairs)*100:.1f}%)")

    # ─── Phase 5: Domain Balancing ────────────────────────────────────
    if args.hive_boost > 1.0:
        hive_pairs = [p for p in all_pairs if detect_domain(p) == "hive"]
        if hive_pairs:
            boost_count = int(len(hive_pairs) * (args.hive_boost - 1))
            import random
            random.seed(42)
            boosted = random.choices(hive_pairs, k=boost_count)
            all_pairs.extend(boosted)
            print(f"\n  Hive boost: +{boost_count} oversampled pairs ({args.hive_boost}x)")

    # ─── Phase 6: Shuffle ─────────────────────────────────────────────
    import random
    random.seed(42)
    random.shuffle(all_pairs)

    # ─── Phase 7: Source Summary ──────────────────────────────────────
    print(f"\n--- Source Contribution ---")
    for source, count in sorted(source_stats.items(), key=lambda x: -x[1]):
        pct = count / sum(source_stats.values()) * 100 if source_stats else 0
        print(f"  {source:15s}: {count:6d} ({pct:5.1f}%)")

    # ─── Phase 8: Export ──────────────────────────────────────────────
    if args.export:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            for pair in all_pairs:
                clean = {
                    "instruction": pair["instruction"],
                    "input": pair.get("input", ""),
                    "output": pair["output"],
                }
                f.write(json.dumps(clean, ensure_ascii=False) + "\n")

        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"\n{'='*60}")
        print(f"EXPORTED: {len(all_pairs)} pairs to {output_path}")
        print(f"Size: {size_mb:.1f} MB")
        print(f"{'='*60}")
    else:
        print(f"\nDry run — use --export to write master dataset")
        print(f"Would produce: {len(all_pairs)} pairs")


if __name__ == "__main__":
    main()
