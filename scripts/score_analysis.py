"""Analyze quality scoring: compare v2 stored scores vs v3 recalculated scores."""
import sys, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hiveai.models import SessionLocal, TrainingPair
from hiveai.lora.distiller import _score_quality
from datetime import datetime


def main():
    db = SessionLocal()
    cutoff = datetime(2026, 2, 22, 13, 28, 43)

    all_p1 = db.query(TrainingPair).filter(TrainingPair.created_at < cutoff).all()
    all_p2 = db.query(TrainingPair).filter(TrainingPair.created_at >= cutoff).all()

    print(f"Phase 1: {len(all_p1)} pairs")
    print(f"Phase 2: {len(all_p2)} pairs")
    print()

    # Rescore all with v3
    random.seed(42)
    p1_sample = random.sample(all_p1, min(80, len(all_p1)))

    p1_old = [p.quality for p in p1_sample]
    p1_new = [_score_quality(p.instruction, p.response) for p in p1_sample]
    p2_old = [p.quality for p in all_p2]
    p2_new = [_score_quality(p.instruction, p.response) for p in all_p2]

    print("=== v3 RESCORING IMPACT ===")
    print(f"{'':>20} {'Stored (v1/v2)':>15} {'v3 Rescore':>15} {'Delta':>10}")
    print("-" * 62)
    print(f"{'Phase 1 avg':>20} {sum(p1_old)/len(p1_old):>15.3f} {sum(p1_new)/len(p1_new):>15.3f} "
          f"{sum(p1_new)/len(p1_new) - sum(p1_old)/len(p1_old):>+10.3f}")
    print(f"{'Phase 2 avg':>20} {sum(p2_old)/len(p2_old):>15.3f} {sum(p2_new)/len(p2_new):>15.3f} "
          f"{sum(p2_new)/len(p2_new) - sum(p2_old)/len(p2_old):>+10.3f}")
    print()

    # Distribution check
    p1_elig = sum(1 for s in p1_new if s >= 0.70)
    p2_elig = sum(1 for s in p2_new if s >= 0.70)
    print(f"Phase 1 eligibility (>=0.70): {p1_elig}/{len(p1_new)} ({p1_elig/len(p1_new)*100:.0f}%)")
    print(f"Phase 2 eligibility (>=0.70): {p2_elig}/{len(p2_new)} ({p2_elig/len(p2_new)*100:.0f}%)")
    print()

    # Score distribution
    for label, scores in [("Phase 1 v3", p1_new), ("Phase 2 v3", p2_new)]:
        bins = {"0.0-0.3": 0, "0.3-0.5": 0, "0.5-0.7": 0, "0.7-0.8": 0, "0.8-0.9": 0, "0.9-1.0": 0}
        for s in scores:
            if s < 0.3: bins["0.0-0.3"] += 1
            elif s < 0.5: bins["0.3-0.5"] += 1
            elif s < 0.7: bins["0.5-0.7"] += 1
            elif s < 0.8: bins["0.7-0.8"] += 1
            elif s < 0.9: bins["0.8-0.9"] += 1
            else: bins["0.9-1.0"] += 1
        print(f"  {label}: {bins}")

    # Top/bottom from each phase
    print()
    print("=== Phase 1 — Bottom 5 (v3 rescored) ===")
    p1_rescored = [(p, _score_quality(p.instruction, p.response)) for p in p1_sample]
    p1_rescored.sort(key=lambda x: x[1])
    for p, s in p1_rescored[:5]:
        print(f"  v3={s:.2f} (was {p.quality:.2f}) | {p.topic[:55]}")

    print()
    print("=== Phase 2 — Top 5 (v3 rescored) ===")
    p2_rescored = [(p, _score_quality(p.instruction, p.response)) for p in all_p2]
    p2_rescored.sort(key=lambda x: x[1], reverse=True)
    for p, s in p2_rescored[:5]:
        print(f"  v3={s:.2f} (was {p.quality:.2f}) | {p.topic[:55]}")

    print()
    print("=== Phase 2 — Bottom 5 (v3 rescored) ===")
    for p, s in p2_rescored[-5:]:
        print(f"  v3={s:.2f} (was {p.quality:.2f}) | {p.topic[:55]}")

    db.close()


if __name__ == "__main__":
    main()
