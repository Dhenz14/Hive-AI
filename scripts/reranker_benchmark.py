"""
scripts/reranker_benchmark.py

Benchmark the shadow reranker (BAAI/bge-reranker-v2-m3) using:
  1. Corrected negative labels (72 off-domain queries → all label=0)
  2. Positive controls (63 on-domain queries → all label=1)

Produces a calibration report with:
  - Score distributions for relevant vs irrelevant
  - Optimal threshold recommendation
  - Precision/recall at multiple thresholds
  - False positive analysis

Usage:
  python scripts/reranker_benchmark.py [--output data/reranker_benchmark_report.json]
"""

import json
import sys
import os
import time
import argparse
import statistics

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_corrected_negatives(path="data/reranker_labels_corrected.jsonl"):
    """Load the 72 manually-labeled negative traces."""
    traces = []
    with open(path) as f:
        for line in f:
            obj = json.loads(line.strip())
            traces.append({
                "trace_id": obj["trace_id"],
                "query": obj["query"],
                "reranker_best_score": obj["reranker_best_score"],
                "label": obj["corrected_label"],
                "reason": obj["reason"],
                "source": "corrected_shadow_trace",
            })
    return traces


def load_positive_controls(path="data/reranker_positive_controls.jsonl"):
    """Load the 63 hand-crafted positive control queries."""
    controls = []
    with open(path) as f:
        for line in f:
            obj = json.loads(line.strip())
            controls.append(obj)
    return controls


def score_positive_controls(controls, db_path="hiveai.db"):
    """Score positive controls by loading sections from DB and running reranker."""
    import sqlite3
    from sentence_transformers import CrossEncoder

    model = CrossEncoder("BAAI/bge-reranker-v2-m3")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    results = []
    total = len(controls)

    for i, ctrl in enumerate(controls):
        query = ctrl["query"]
        expected_ids = ctrl["expected_section_ids"]

        # Fetch expected sections
        placeholders = ",".join("?" * len(expected_ids))
        rows = conn.execute(
            f"SELECT id, header, content FROM book_sections WHERE id IN ({placeholders})",
            expected_ids,
        ).fetchall()

        if not rows:
            print(f"  [{i+1}/{total}] SKIP: no sections found for IDs {expected_ids}")
            continue

        # Also fetch 5 random OTHER sections as negative foils
        foil_rows = conn.execute(
            f"""SELECT id, header, content FROM book_sections
                WHERE id NOT IN ({placeholders})
                ORDER BY RANDOM() LIMIT 5""",
            expected_ids,
        ).fetchall()

        all_sections = list(rows) + list(foil_rows)

        # Score all pairs
        pairs = [(query, (dict(s)["content"] or dict(s)["header"])[:1500]) for s in all_sections]
        scores = model.predict(pairs)

        # Separate expected vs foil scores
        n_expected = len(rows)
        expected_scores = [float(scores[j]) for j in range(n_expected)]
        foil_scores = [float(scores[j]) for j in range(n_expected, len(scores))]

        best_expected = max(expected_scores) if expected_scores else 0
        best_foil = max(foil_scores) if foil_scores else 0

        results.append({
            "query": query,
            "domain": ctrl["domain"],
            "label": 1,
            "reranker_best_score": best_expected,
            "best_foil_score": best_foil,
            "expected_scores": [round(s, 6) for s in expected_scores],
            "foil_scores": [round(s, 6) for s in foil_scores],
            "separation": round(best_expected - best_foil, 6),
            "source": "positive_control",
        })

        status = "OK" if best_expected > best_foil else "FOIL_WINS"
        print(f"  [{i+1}/{total}] {status} expected={best_expected:.4f} foil={best_foil:.4f} q={query[:60]}")

    conn.close()
    return results


def compute_metrics(positives, negatives, threshold):
    """Compute precision, recall, F1 at a given threshold."""
    tp = sum(1 for p in positives if p["reranker_best_score"] >= threshold)
    fn = sum(1 for p in positives if p["reranker_best_score"] < threshold)
    fp = sum(1 for n in negatives if n["reranker_best_score"] >= threshold)
    tn = sum(1 for n in negatives if n["reranker_best_score"] < threshold)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0

    return {
        "threshold": threshold,
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "false_positive_rate": round(fp / (fp + tn), 4) if (fp + tn) > 0 else 0,
    }


def find_optimal_threshold(positives, negatives, thresholds):
    """Find the threshold that maximizes F1 score."""
    best = None
    for t in thresholds:
        m = compute_metrics(positives, negatives, t)
        if best is None or m["f1"] > best["f1"]:
            best = m
    return best


def main():
    parser = argparse.ArgumentParser(description="Benchmark shadow reranker with corrected labels")
    parser.add_argument("--output", default="data/reranker_benchmark_report.json")
    parser.add_argument("--db", default="hiveai.db")
    parser.add_argument("--skip-scoring", action="store_true",
                        help="Skip positive control scoring (use cached results)")
    args = parser.parse_args()

    print("=" * 70)
    print("Shadow Reranker Benchmark — Corrected Labels + Positive Controls")
    print("=" * 70)

    # 1. Load corrected negatives (already have reranker scores from traces)
    print("\n[1/4] Loading corrected negative labels...")
    negatives = load_corrected_negatives()
    print(f"  Loaded {len(negatives)} negative traces (all label=0)")

    # 2. Score positive controls
    cached_path = "data/reranker_positive_scored.jsonl"
    if args.skip_scoring and os.path.exists(cached_path):
        print(f"\n[2/4] Loading cached positive scores from {cached_path}...")
        with open(cached_path) as f:
            positives = [json.loads(line) for line in f]
        print(f"  Loaded {len(positives)} cached positive results")
    else:
        print(f"\n[2/4] Scoring {len(load_positive_controls())} positive controls against KB...")
        controls = load_positive_controls()
        positives = score_positive_controls(controls, args.db)

        # Cache results
        with open(cached_path, "w") as f:
            for p in positives:
                f.write(json.dumps(p) + "\n")
        print(f"  Scored and cached {len(positives)} positive controls")

    # 3. Analyze distributions
    print("\n[3/4] Analyzing score distributions...")
    pos_scores = [p["reranker_best_score"] for p in positives]
    neg_scores = [n["reranker_best_score"] for n in negatives]

    pos_stats = {
        "count": len(pos_scores),
        "min": round(min(pos_scores), 6),
        "max": round(max(pos_scores), 6),
        "mean": round(statistics.mean(pos_scores), 6),
        "median": round(statistics.median(pos_scores), 6),
        "stdev": round(statistics.stdev(pos_scores), 6) if len(pos_scores) > 1 else 0,
        "p10": round(sorted(pos_scores)[max(0, len(pos_scores) // 10)], 6),
        "p25": round(sorted(pos_scores)[max(0, len(pos_scores) // 4)], 6),
        "p75": round(sorted(pos_scores)[max(0, 3 * len(pos_scores) // 4)], 6),
        "p90": round(sorted(pos_scores)[max(0, 9 * len(pos_scores) // 10)], 6),
    }
    neg_stats = {
        "count": len(neg_scores),
        "min": round(min(neg_scores), 6),
        "max": round(max(neg_scores), 6),
        "mean": round(statistics.mean(neg_scores), 6),
        "median": round(statistics.median(neg_scores), 6),
        "stdev": round(statistics.stdev(neg_scores), 6) if len(neg_scores) > 1 else 0,
        "p10": round(sorted(neg_scores)[max(0, len(neg_scores) // 10)], 6),
        "p25": round(sorted(neg_scores)[max(0, len(neg_scores) // 4)], 6),
        "p75": round(sorted(neg_scores)[max(0, 3 * len(neg_scores) // 4)], 6),
        "p90": round(sorted(neg_scores)[max(0, 9 * len(neg_scores) // 10)], 6),
    }

    gap = pos_stats["mean"] - neg_stats["mean"]
    separation = pos_stats["p10"] - neg_stats["p90"]

    print(f"\n  POSITIVE (relevant) scores:")
    print(f"    n={pos_stats['count']}, mean={pos_stats['mean']:.4f}, "
          f"median={pos_stats['median']:.4f}, min={pos_stats['min']:.4f}, max={pos_stats['max']:.4f}")
    print(f"    p10={pos_stats['p10']:.4f}, p25={pos_stats['p25']:.4f}, "
          f"p75={pos_stats['p75']:.4f}, p90={pos_stats['p90']:.4f}")

    print(f"\n  NEGATIVE (irrelevant) scores:")
    print(f"    n={neg_stats['count']}, mean={neg_stats['mean']:.4f}, "
          f"median={neg_stats['median']:.4f}, min={neg_stats['min']:.4f}, max={neg_stats['max']:.4f}")
    print(f"    p10={neg_stats['p10']:.4f}, p25={neg_stats['p25']:.4f}, "
          f"p75={neg_stats['p75']:.4f}, p90={neg_stats['p90']:.4f}")

    print(f"\n  GAP (mean pos - mean neg): {gap:.4f}")
    print(f"  SEPARATION (p10 pos - p90 neg): {separation:.4f}")
    if separation > 0:
        print("  >>> CLEAN SEPARATION — threshold calibration is possible")
    else:
        print("  >>> OVERLAP — some false positives/negatives unavoidable")

    # 4. Threshold sweep
    print("\n[4/4] Threshold sweep...")
    thresholds = [round(t * 0.01, 2) for t in range(1, 100)]
    sweep_results = []
    for t in thresholds:
        m = compute_metrics(positives, negatives, t)
        sweep_results.append(m)

    optimal = find_optimal_threshold(positives, negatives, thresholds)
    print(f"\n  OPTIMAL THRESHOLD: {optimal['threshold']:.2f}")
    print(f"    Precision={optimal['precision']:.3f}, Recall={optimal['recall']:.3f}, "
          f"F1={optimal['f1']:.3f}, Accuracy={optimal['accuracy']:.3f}")
    print(f"    TP={optimal['tp']}, FP={optimal['fp']}, FN={optimal['fn']}, TN={optimal['tn']}")

    # Show key thresholds
    print("\n  Threshold sweep (selected):")
    print(f"  {'Thresh':>7} {'Prec':>6} {'Rec':>6} {'F1':>6} {'Acc':>6} {'FPR':>6} {'TP':>4} {'FP':>4} {'FN':>4} {'TN':>4}")
    for t in [0.01, 0.02, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]:
        m = compute_metrics(positives, negatives, t)
        print(f"  {t:>7.3f} {m['precision']:>6.3f} {m['recall']:>6.3f} {m['f1']:>6.3f} "
              f"{m['accuracy']:>6.3f} {m['false_positive_rate']:>6.3f} "
              f"{m['tp']:>4} {m['fp']:>4} {m['fn']:>4} {m['tn']:>4}")

    # False positive analysis
    false_positives = [n for n in negatives if n["reranker_best_score"] >= optimal["threshold"]]
    if false_positives:
        print(f"\n  FALSE POSITIVES at optimal threshold ({len(false_positives)}):")
        for fp in sorted(false_positives, key=lambda x: -x["reranker_best_score"])[:10]:
            print(f"    score={fp['reranker_best_score']:.4f} q={fp['query'][:60]}")

    # Build report
    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "model": "BAAI/bge-reranker-v2-m3",
        "positive_stats": pos_stats,
        "negative_stats": neg_stats,
        "gap_mean": round(gap, 6),
        "separation_p10_p90": round(separation, 6),
        "clean_separation": separation > 0,
        "optimal_threshold": optimal,
        "current_threshold": 0.075,
        "sweep": sweep_results,
        "false_positives_at_optimal": [
            {"query": fp["query"], "score": fp["reranker_best_score"], "reason": fp.get("reason", "")}
            for fp in sorted(false_positives, key=lambda x: -x["reranker_best_score"])
        ],
        "finding": "",
    }

    # Verdict
    if separation > 0.1:
        report["finding"] = (
            f"CLEAN SEPARATION. Positive and negative scores are well-separated "
            f"(gap={gap:.3f}, separation={separation:.3f}). "
            f"Recommended threshold: {optimal['threshold']:.2f} "
            f"(F1={optimal['f1']:.3f}). Shadow reranker is READY for promotion."
        )
    elif separation > 0:
        report["finding"] = (
            f"MARGINAL SEPARATION. Some overlap but threshold is viable "
            f"(gap={gap:.3f}, separation={separation:.3f}). "
            f"Recommended threshold: {optimal['threshold']:.2f} "
            f"(F1={optimal['f1']:.3f}). Consider promotion with monitoring."
        )
    else:
        report["finding"] = (
            f"OVERLAP. Positive/negative score distributions overlap "
            f"(gap={gap:.3f}, separation={separation:.3f}). "
            f"Best threshold: {optimal['threshold']:.2f} "
            f"(F1={optimal['f1']:.3f}). Reranker may need model upgrade or more data."
        )

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved to {args.output}")
    print(f"\n  VERDICT: {report['finding']}")


if __name__ == "__main__":
    main()
