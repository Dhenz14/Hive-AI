"""
Rescore all training pairs in the DB with the v3 quality scorer.
Updates quality scores and is_eligible flags in-place.

Usage:
    python scripts/rescore_pairs.py             # Dry run (show changes)
    python scripts/rescore_pairs.py --apply      # Apply changes to DB
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from hiveai.models import SessionLocal, TrainingPair
from hiveai.lora.distiller import _score_quality
from hiveai.config import MIN_TRAINING_QUALITY


def main():
    parser = argparse.ArgumentParser(description="Rescore all training pairs with v3 scorer")
    parser.add_argument("--apply", action="store_true", help="Apply changes to DB (default: dry run)")
    args = parser.parse_args()

    db = SessionLocal()
    pairs = db.query(TrainingPair).all()
    print(f"Found {len(pairs)} training pairs")
    print(f"MIN_TRAINING_QUALITY threshold: {MIN_TRAINING_QUALITY}")
    print()

    changes = {"upgraded": 0, "downgraded": 0, "unchanged": 0,
               "newly_eligible": 0, "newly_ineligible": 0}
    total_old = 0.0
    total_new = 0.0

    for p in pairs:
        old_q = p.quality
        new_q = _score_quality(p.instruction, p.response)
        old_elig = p.is_eligible
        new_elig = new_q >= MIN_TRAINING_QUALITY

        total_old += old_q
        total_new += new_q

        delta = new_q - old_q
        if abs(delta) < 0.005:
            changes["unchanged"] += 1
        elif delta > 0:
            changes["upgraded"] += 1
        else:
            changes["downgraded"] += 1

        if not old_elig and new_elig:
            changes["newly_eligible"] += 1
        elif old_elig and not new_elig:
            changes["newly_ineligible"] += 1

        if args.apply:
            p.quality = new_q
            p.is_eligible = new_elig

    n = len(pairs)
    print(f"Average quality: {total_old/n:.3f} -> {total_new/n:.3f} ({total_new/n - total_old/n:+.3f})")
    print(f"Upgraded:   {changes['upgraded']}")
    print(f"Downgraded: {changes['downgraded']}")
    print(f"Unchanged:  {changes['unchanged']}")
    print(f"Newly eligible:   {changes['newly_eligible']}")
    print(f"Newly ineligible: {changes['newly_ineligible']}")

    old_elig = sum(1 for p in pairs if p.is_eligible)
    new_elig = sum(1 for p in pairs if _score_quality(p.instruction, p.response) >= MIN_TRAINING_QUALITY)
    print(f"Eligible count: {old_elig} -> {new_elig}")

    if args.apply:
        db.commit()
        print("\nChanges applied to database.")
    else:
        print("\nDRY RUN — no changes made. Use --apply to update DB.")

    db.close()


if __name__ == "__main__":
    main()
