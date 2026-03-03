"""
scripts/mine_hive_knowledge.py

Mine Hive blockchain training pairs using self-distillation.

Uses the 70 Hive-specific topics defined in hiveai/lora/distiller.py HIVE_TOPICS
to generate high-quality training pairs for making HiveAI Hive-native.

Usage:
    python scripts/mine_hive_knowledge.py                # Mine all Hive topics (5 pairs each)
    python scripts/mine_hive_knowledge.py --pairs 3      # Quick pass (3 pairs per topic)
    python scripts/mine_hive_knowledge.py --stats        # Show current Hive pair counts
    python scripts/mine_hive_knowledge.py --dry-run      # Generate but don't save to DB

Requires: Ollama running with qwen3:14b (or configured model).
NOTE: Don't run while LoRA training is active — both need GPU/RAM.
"""
import sys
import argparse
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mine_hive")


def show_stats():
    """Show current Hive training pair statistics."""
    import sqlite3
    db_path = PROJECT_ROOT / "hiveai.db"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM training_pairs")
    total = c.fetchone()[0]

    c.execute(
        "SELECT COUNT(*) FROM training_pairs "
        "WHERE instruction LIKE '%hive%' OR instruction LIKE '%Hive%' "
        "OR topic LIKE '%hive%' OR topic LIKE '%Hive%'"
    )
    hive_total = c.fetchone()[0]

    c.execute(
        "SELECT COUNT(*) FROM training_pairs "
        "WHERE (instruction LIKE '%hive%' OR instruction LIKE '%Hive%' "
        "OR topic LIKE '%hive%' OR topic LIKE '%Hive%') "
        "AND quality >= 0.75"
    )
    hive_eligible = c.fetchone()[0]

    c.execute(
        "SELECT topic, COUNT(*), ROUND(AVG(quality), 3) FROM training_pairs "
        "WHERE topic LIKE '%hive%' OR topic LIKE '%Hive%' "
        "OR topic LIKE '%dhive%' OR topic LIKE '%beem%' "
        "OR topic LIKE '%HAF%' OR topic LIKE '%HBD%' "
        "OR topic LIKE '%DPoS%' OR topic LIKE '%Layer 2%' "
        "OR topic LIKE '%custom_json%' OR topic LIKE '%Keychain%' "
        "GROUP BY topic ORDER BY COUNT(*) DESC"
    )
    topics = c.fetchall()
    conn.close()

    print(f"\n{'='*60}")
    print(f"  Hive Knowledge Stats")
    print(f"{'='*60}")
    print(f"  Total pairs in DB:     {total}")
    print(f"  Hive-related pairs:    {hive_total} ({hive_total/total*100:.1f}%)")
    print(f"  Hive eligible (>=0.75): {hive_eligible}")
    print(f"\n  Topics with Hive pairs:")
    for topic, count, avg_q in topics:
        bar = "#" * min(count, 20)
        print(f"    {topic[:55]:55s} | {count:3d} | q={avg_q} | {bar}")
    print(f"{'='*60}\n")


def mine(pairs_per_topic: int = 5, dry_run: bool = False):
    """Run Hive knowledge distillation."""
    from hiveai.lora.distiller import distill_hive, HIVE_TOPICS

    logger.info(f"Mining Hive knowledge: {len(HIVE_TOPICS)} topics, {pairs_per_topic} pairs each")
    logger.info(f"Expected output: ~{len(HIVE_TOPICS) * pairs_per_topic} pairs")

    if dry_run:
        logger.info("DRY RUN — pairs will not be saved to database")
        results = distill_hive(pairs_per_topic=pairs_per_topic, db=None)
    else:
        from hiveai.models import get_db
        db = next(get_db())
        try:
            results = distill_hive(pairs_per_topic=pairs_per_topic, db=db)
            db.commit()
        finally:
            db.close()

    eligible = sum(1 for r in results if r.get("is_eligible", False))
    logger.info(f"Mining complete: {len(results)} total, {eligible} eligible (quality >= 0.75)")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mine Hive blockchain training pairs")
    parser.add_argument("--pairs", type=int, default=5,
                        help="Pairs per topic (default: 5)")
    parser.add_argument("--stats", action="store_true",
                        help="Show current Hive pair statistics")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate pairs without saving to DB")
    args = parser.parse_args()

    if args.stats:
        show_stats()
    else:
        mine(pairs_per_topic=args.pairs, dry_run=args.dry_run)
        show_stats()
