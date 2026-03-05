"""
scripts/claude_distill_v2.py

Claude Opus 4.6 distillation — Batch 2: Filling critical gaps.

Targets P0-P2 gaps identified by coverage analysis:
  P0: MCP, agentic workflows, chain-of-thought, self-play, inference engines
  P1: C++23, WASM, eBPF, Solana, modern web (HTMX/Astro), Zig
  P2: Rust ecosystem, DPO variants, constrained decoding, long context

Usage:
    python scripts/claude_distill_v2.py                 # Dry run
    python scripts/claude_distill_v2.py --persist       # Score, dedup, save to DB
    python scripts/claude_distill_v2.py --stats         # Show stats
"""
import sys
import argparse
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("claude_distill_v2")

# ---------------------------------------------------------------------------
# Each pair is (topic, instruction, response).
# ---------------------------------------------------------------------------

CLAUDE_PAIRS_V2 = [
    # =========================================================================
    # BATCH 1: P0 — MCP, Agentic Workflows, Chain-of-Thought, Self-Play
    # =========================================================================
]

# We'll import pairs from separate batch files to keep this manageable
from pathlib import Path
import importlib

def _load_batch(name):
    """Load a batch module from scripts/distill_batches/."""
    batch_dir = Path(__file__).parent / "distill_batches"
    batch_dir.mkdir(exist_ok=True)
    mod_path = batch_dir / f"{name}.py"
    if mod_path.exists():
        spec = importlib.util.spec_from_file_location(name, mod_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "PAIRS", [])
    return []


def get_all_pairs():
    """Collect pairs from all batch files + inline."""
    all_pairs = list(CLAUDE_PAIRS_V2)
    batch_dir = Path(__file__).parent / "distill_batches"
    if batch_dir.exists():
        for batch_file in sorted(batch_dir.glob("batch_*.py")):
            batch_name = batch_file.stem
            pairs = _load_batch(batch_name)
            if pairs:
                logger.info(f"Loaded {len(pairs)} pairs from {batch_name}")
                all_pairs.extend(pairs)
    return all_pairs


def persist_pairs(pairs, dry_run=False):
    """Score, dedup, and persist Claude-distilled pairs."""
    from hiveai.models import SessionLocal, TrainingPair
    from hiveai.lora.distiller import _score_quality
    from hiveai.config import MIN_TRAINING_QUALITY

    db = SessionLocal()
    stats = {"total": 0, "persisted": 0, "duplicate": 0, "below_threshold": 0}

    try:
        existing = set()
        for (instr,) in db.query(TrainingPair.instruction).all():
            existing.add(instr.strip()[:200])

        for topic, instruction, response in pairs:
            stats["total"] += 1
            quality = _score_quality(instruction, response)
            is_eligible = quality >= MIN_TRAINING_QUALITY

            if instruction.strip()[:200] in existing:
                stats["duplicate"] += 1
                status = "DEDUP"
            elif not is_eligible:
                stats["below_threshold"] += 1
                status = f"LOW_Q ({quality:.2f})"
            else:
                status = f"OK (q={quality:.2f})"
                if not dry_run:
                    pair = TrainingPair(
                        source="claude_distill_v2",
                        topic=topic,
                        instruction=instruction,
                        response=response,
                        quality=quality,
                        is_eligible=is_eligible,
                    )
                    db.add(pair)
                    existing.add(instruction.strip()[:200])
                stats["persisted"] += 1

            print(f"  [{status:>15}] {topic[:55]}")

        if not dry_run:
            db.commit()

        print(f"\nResults: {stats['total']} total, {stats['persisted']} persisted, "
              f"{stats['duplicate']} dedup, {stats['below_threshold']} below threshold")
        if dry_run:
            print("DRY RUN — no changes saved. Use --persist to save.")

    finally:
        db.close()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Claude Opus 4.6 distillation v2 — gap filling")
    parser.add_argument("--persist", action="store_true", help="Score and save pairs to DB")
    parser.add_argument("--stats", action="store_true", help="Show pair statistics")
    args = parser.parse_args()

    if args.stats:
        from hiveai.models import SessionLocal, TrainingPair
        db = SessionLocal()
        pairs = db.query(TrainingPair).filter(TrainingPair.source == "claude_distill_v2").all()
        if not pairs:
            print("No v2 pairs in DB yet. Run with --persist first.")
        else:
            avg_q = sum(p.quality for p in pairs) / len(pairs)
            eligible = sum(1 for p in pairs if p.is_eligible)
            print(f"V2 pairs: {len(pairs)}, eligible: {eligible}, avg quality: {avg_q:.3f}")
        db.close()
        return

    all_pairs = get_all_pairs()
    print(f"Claude Opus 4.6 distillation v2 — {len(all_pairs)} pairs")
    persist_pairs(all_pairs, dry_run=not args.persist)


if __name__ == "__main__":
    main()
