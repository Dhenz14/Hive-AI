#!/usr/bin/env python3
"""
scripts/distill_multilang.py

Multi-language distillation: generate training pairs for C++, Rust, and Go
using the existing distiller infrastructure.

These languages have topic lists and templates defined in distiller.py but
have ZERO actual training pairs generated. This script fills that gap.

Usage:
    python scripts/distill_multilang.py --lang cpp              # C++ only
    python scripts/distill_multilang.py --lang rust             # Rust only
    python scripts/distill_multilang.py --lang go               # Go only
    python scripts/distill_multilang.py --lang js               # JavaScript only
    python scripts/distill_multilang.py --all                   # All 4 languages
    python scripts/distill_multilang.py --lang cpp --dry-run    # Preview without saving
    python scripts/distill_multilang.py --lang cpp --export     # Generate + export JSONL
    python scripts/distill_multilang.py --stats                 # Show per-language stats

Options:
    --pairs N       Pairs per topic (default 5, max 7)
    --topics N      Limit to first N topics (for testing)
    --export        After generation, export to loras/training_data/<lang>.jsonl
    --dry-run       Show what would be generated, don't save to DB
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("distill_multilang")

LANG_MAP = {
    "cpp": {"func": "distill_cpp", "label": "C++", "topics_attr": "CPP_TOPICS"},
    "c++": {"func": "distill_cpp", "label": "C++", "topics_attr": "CPP_TOPICS"},
    "rust": {"func": "distill_rust", "label": "Rust", "topics_attr": "RUST_TOPICS"},
    "go": {"func": "distill_go", "label": "Go", "topics_attr": "GO_TOPICS"},
    "js": {"func": "distill_javascript", "label": "JavaScript", "topics_attr": None},
    "javascript": {"func": "distill_javascript", "label": "JavaScript", "topics_attr": None},
}

DATA_DIR = PROJECT_ROOT / "loras" / "training_data"


def show_stats():
    """Show per-language training pair counts from the DB."""
    try:
        from hiveai.models import SessionLocal, TrainingPair
        from sqlalchemy import func
    except ImportError:
        print("Cannot import models — is the project set up? Run setup.bat first.")
        return

    db = SessionLocal()
    try:
        total = db.query(TrainingPair).count()
        print(f"\nTotal training pairs in DB: {total}\n")

        # Group by source
        sources = (
            db.query(TrainingPair.source, func.count(TrainingPair.id), func.avg(TrainingPair.quality))
            .group_by(TrainingPair.source)
            .all()
        )
        print(f"{'Source':<25} {'Count':>7} {'Avg Quality':>12}")
        print("-" * 48)
        for source, count, avg_q in sorted(sources, key=lambda x: -x[1]):
            print(f"{source:<25} {count:>7} {avg_q:>12.3f}")

        # Language detection from topic names
        print("\n--- Language coverage (estimated from topic names) ---\n")
        for lang_key, lang_info in [("cpp", "C++"), ("rust", "Rust"), ("go", "Go")]:
            prefix = lang_info + " " if lang_info != "Go" else "Go "
            count = db.query(TrainingPair).filter(
                TrainingPair.topic.ilike(f"%{prefix}%")
            ).count()
            eligible = db.query(TrainingPair).filter(
                TrainingPair.topic.ilike(f"%{prefix}%"),
                TrainingPair.is_eligible == True,
            ).count()
            print(f"{lang_info:<15} {count:>5} pairs ({eligible} eligible)")

    finally:
        db.close()


def export_language(lang_key: str):
    """Export training pairs for a language to JSONL."""
    try:
        from hiveai.models import SessionLocal, TrainingPair
    except ImportError:
        print("Cannot import models.")
        return 0

    lang_info = LANG_MAP.get(lang_key, LANG_MAP.get("cpp"))
    label = lang_info["label"]

    # Determine topic prefix for filtering
    if lang_key in ("cpp", "c++"):
        topic_filter = "C++ %"
    elif lang_key == "rust":
        topic_filter = "Rust %"
    elif lang_key == "go":
        topic_filter = "Go %"
    elif lang_key in ("js", "javascript"):
        topic_filter = "%JavaScript%"
    else:
        topic_filter = f"%{label}%"

    db = SessionLocal()
    try:
        pairs = (
            db.query(TrainingPair)
            .filter(
                TrainingPair.topic.ilike(topic_filter),
                TrainingPair.is_eligible == True,
            )
            .all()
        )

        if not pairs:
            print(f"No eligible {label} pairs found in DB. Run distillation first.")
            return 0

        # Normalize lang key for filename
        fname = {"cpp": "cpp", "c++": "cpp", "rust": "rust", "go": "go",
                 "js": "javascript", "javascript": "javascript"}[lang_key]
        output_file = DATA_DIR / f"{fname}.jsonl"

        with open(output_file, "w", encoding="utf-8") as f:
            for p in pairs:
                record = {
                    "instruction": p.instruction,
                    "input": p.topic,
                    "output": p.response,
                    "quality": round(p.quality, 4),
                    "source": p.source,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        print(f"Exported {len(pairs)} {label} pairs to {output_file}")
        return len(pairs)

    finally:
        db.close()


def run_distill(lang_key: str, pairs_per_topic: int = 5, max_topics: int = 0,
                dry_run: bool = False, do_export: bool = False):
    """Run distillation for a specific language."""
    from hiveai.lora.distiller import (
        distill_cpp, distill_rust, distill_go, distill_javascript,
        distill_batch, CPP_TOPICS, RUST_TOPICS, GO_TOPICS,
    )

    lang_info = LANG_MAP[lang_key]
    label = lang_info["label"]

    # Get topic list for preview
    topics_attr = lang_info["topics_attr"]
    if topics_attr:
        from hiveai.lora import distiller as _d
        topics = getattr(_d, topics_attr)
    else:
        topics = []  # JS builds its own list internally

    if max_topics > 0 and topics:
        topics = topics[:max_topics]

    print(f"\n{'='*60}")
    print(f"  {label} Distillation")
    print(f"  Topics: {len(topics) if topics else '(auto)'}")
    print(f"  Pairs per topic: {pairs_per_topic}")
    print(f"  Expected pairs: ~{len(topics) * pairs_per_topic if topics else '?'}")
    print(f"  Dry run: {dry_run}")
    print(f"{'='*60}\n")

    if dry_run:
        if topics:
            for i, t in enumerate(topics, 1):
                print(f"  {i:3}. {t}")
        print(f"\nDRY RUN — would generate ~{len(topics) * pairs_per_topic} pairs. Use without --dry-run to execute.")
        return []

    # Get DB session
    from hiveai.models import SessionLocal
    db = SessionLocal()

    t0 = time.time()
    try:
        if max_topics > 0 and topics:
            # Use distill_batch directly with trimmed topic list
            lang_code = {"cpp": "cpp", "c++": "cpp", "rust": "rust",
                         "go": "go", "js": "javascript", "javascript": "javascript"}[lang_key]
            results = distill_batch(topics, pairs_per_topic=pairs_per_topic,
                                    db=db, language=lang_code)
        else:
            # Use the convenience function (full topic list)
            func_map = {
                "cpp": distill_cpp, "c++": distill_cpp,
                "rust": distill_rust, "go": distill_go,
                "js": distill_javascript, "javascript": distill_javascript,
            }
            func = func_map[lang_key]
            results = func(pairs_per_topic=pairs_per_topic, db=db)
    finally:
        db.close()

    elapsed = time.time() - t0
    eligible = sum(1 for r in results if r.get("is_eligible"))

    print(f"\n--- {label} Results ---")
    print(f"  Generated: {len(results)} pairs")
    print(f"  Eligible:  {eligible} ({eligible/max(len(results),1)*100:.0f}%)")
    print(f"  Time:      {elapsed:.0f}s ({elapsed/60:.1f} min)")

    if results:
        qualities = [r["quality"] for r in results]
        print(f"  Quality:   avg={sum(qualities)/len(qualities):.3f}, "
              f"min={min(qualities):.3f}, max={max(qualities):.3f}")

    if do_export and eligible > 0:
        print()
        export_language(lang_key)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Multi-language training pair distillation (C++, Rust, Go, JS)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--lang", type=str, help="Language to distill: cpp, rust, go, js")
    parser.add_argument("--all", action="store_true", help="Distill all languages")
    parser.add_argument("--pairs", type=int, default=5, help="Pairs per topic (default 5, max 7)")
    parser.add_argument("--topics", type=int, default=0, help="Limit to first N topics (0=all)")
    parser.add_argument("--export", action="store_true", help="Export to JSONL after generation")
    parser.add_argument("--dry-run", action="store_true", help="Preview without generating")
    parser.add_argument("--stats", action="store_true", help="Show per-language DB stats")
    parser.add_argument("--export-only", type=str, help="Export existing DB pairs for a language (no generation)")
    args = parser.parse_args()

    pairs_per_topic = min(args.pairs, 7)

    if args.stats:
        show_stats()
        return

    if args.export_only:
        lang = args.export_only.lower()
        if lang not in LANG_MAP:
            print(f"Unknown language '{lang}'. Choose: {', '.join(LANG_MAP.keys())}")
            sys.exit(1)
        export_language(lang)
        return

    if not args.lang and not args.all:
        parser.print_help()
        print("\nExamples:")
        print("  python scripts/distill_multilang.py --lang cpp --dry-run")
        print("  python scripts/distill_multilang.py --lang cpp --pairs 5")
        print("  python scripts/distill_multilang.py --all --pairs 3")
        print("  python scripts/distill_multilang.py --stats")
        return

    languages = ["cpp", "rust", "go", "js"] if args.all else [args.lang.lower()]

    for lang in languages:
        if lang not in LANG_MAP:
            print(f"Unknown language '{lang}'. Choose: {', '.join(LANG_MAP.keys())}")
            sys.exit(1)

    total_results = []
    for lang in languages:
        results = run_distill(
            lang, pairs_per_topic=pairs_per_topic,
            max_topics=args.topics, dry_run=args.dry_run,
            do_export=args.export,
        )
        total_results.extend(results)

    if len(languages) > 1 and not args.dry_run:
        eligible = sum(1 for r in total_results if r.get("is_eligible"))
        print(f"\n{'='*60}")
        print(f"  TOTAL: {len(total_results)} pairs, {eligible} eligible")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
