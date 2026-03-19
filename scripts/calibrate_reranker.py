#!/usr/bin/env python3
"""Analyze shadow reranker traces and recommend calibration thresholds.

Reads from two sources:
1. SQLite telemetry_events.retrieval_trace_json (live persisted traces)
2. data/synthetic_results.jsonl (synthetic traffic results with ground truth labels)

Outputs:
- Score distribution analysis
- Separation metrics (labeled data: FA vs FR)
- Per-query-class breakdown
- Threshold recommendations
- Latency profile

Usage:
    python scripts/calibrate_reranker.py [--db hiveai.db]
                                          [--results data/synthetic_results.jsonl]
                                          [--output data/calibration_report.json]
"""

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict


def load_traces_from_db(db_path: str) -> list[dict]:
    """Load retrieval traces from telemetry_events table."""
    if not os.path.exists(db_path):
        print(f"  [SKIP] Database not found: {db_path}")
        return []

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("""
            SELECT retrieval_trace_json, created_at
            FROM telemetry_events
            WHERE retrieval_trace_json IS NOT NULL
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
    except sqlite3.OperationalError as e:
        print(f"  [SKIP] DB query failed: {e}")
        return []
    finally:
        conn.close()

    traces = []
    for trace_json, created_at in rows:
        try:
            trace = json.loads(trace_json)
            trace["_source"] = "db"
            trace["_created_at"] = created_at
            traces.append(trace)
        except (json.JSONDecodeError, TypeError):
            continue

    print(f"  Database: {len(traces)} traces loaded from {db_path}")
    return traces


def load_traces_from_results(results_path: str) -> list[dict]:
    """Load traces from synthetic_results.jsonl."""
    if not os.path.exists(results_path):
        print(f"  [SKIP] Results file not found: {results_path}")
        return []

    traces = []
    with open(results_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if row.get("error"):
                    continue
                # Synthetic results have trace fields flattened at top level
                trace = {
                    "reranker_shadow_applied": row.get("reranker_shadow_applied"),
                    "reranker_best_score": row.get("reranker_best_score"),
                    "reranker_shadow_latency_ms": row.get("reranker_shadow_latency_ms"),
                    "would_suppress_reranker": row.get("would_suppress_reranker"),
                    "initial_best_score": row.get("initial_best_score"),
                    "confidence_gate_evaluated": row.get("confidence_gate_evaluated"),
                    "rewrite_gate_entered": row.get("rewrite_gate_entered"),
                    "rewrite_applied": row.get("rewrite_applied"),
                    "retrieval_suppressed": row.get("retrieval_suppressed"),
                    "hard_section_count": row.get("hard_section_count"),
                    # Metadata from synthetic query
                    "_source": "synthetic",
                    "_query": row.get("query", ""),
                    "_query_class": row.get("query_class", "unknown"),
                    "_has_label": row.get("has_label", False),
                    "_relevance_label": row.get("relevance_label"),
                    "_dataset_source": row.get("source", "unknown"),
                }
                traces.append(trace)
            except (json.JSONDecodeError, TypeError):
                continue

    print(f"  Results: {len(traces)} traces loaded from {results_path}")
    return traces


def percentile(values: list[float], p: float) -> float:
    """Compute percentile (0-100) of a sorted list."""
    if not values:
        return 0.0
    k = (len(values) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1 if f + 1 < len(values) else f
    d = k - f
    return values[f] + d * (values[c] - values[f])


def compute_histogram(values: list[float], bins: int = 10) -> list[dict]:
    """Compute a simple histogram."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if lo == hi:
        return [{"bin_start": lo, "bin_end": hi, "count": len(values)}]
    width = (hi - lo) / bins
    hist = []
    for i in range(bins):
        start = lo + i * width
        end = start + width
        count = sum(1 for v in values if start <= v < end or (i == bins - 1 and v == end))
        hist.append({"bin_start": round(start, 4), "bin_end": round(end, 4), "count": count})
    return hist


def analyze(traces: list[dict]) -> dict:
    """Run full calibration analysis on traces."""
    report = {
        "total_traces": len(traces),
        "shadow_applied": 0,
        "shadow_not_applied": 0,
    }

    # Split by shadow applied
    shadow_traces = [t for t in traces if t.get("reranker_shadow_applied")]
    report["shadow_applied"] = len(shadow_traces)
    report["shadow_not_applied"] = len(traces) - len(shadow_traces)

    if not shadow_traces:
        report["error"] = "No shadow reranker traces found. Run synthetic traffic first."
        return report

    # --- Score distribution ---
    scores = [t["reranker_best_score"] for t in shadow_traces
              if t.get("reranker_best_score") is not None]
    scores.sort()

    if scores:
        report["score_distribution"] = {
            "count": len(scores),
            "min": round(min(scores), 4),
            "max": round(max(scores), 4),
            "mean": round(sum(scores) / len(scores), 4),
            "p10": round(percentile(scores, 10), 4),
            "p25": round(percentile(scores, 25), 4),
            "p50": round(percentile(scores, 50), 4),
            "p75": round(percentile(scores, 75), 4),
            "p90": round(percentile(scores, 90), 4),
            "histogram": compute_histogram(scores, bins=10),
        }

    # --- Latency profile ---
    latencies = [t["reranker_shadow_latency_ms"] for t in shadow_traces
                 if t.get("reranker_shadow_latency_ms") is not None]
    latencies.sort()

    if latencies:
        report["latency_profile"] = {
            "count": len(latencies),
            "p50": round(percentile(latencies, 50), 1),
            "p75": round(percentile(latencies, 75), 1),
            "p90": round(percentile(latencies, 90), 1),
            "p95": round(percentile(latencies, 95), 1),
            "p99": round(percentile(latencies, 99), 1),
            "mean": round(sum(latencies) / len(latencies), 1),
        }

    # --- Confidence gate analysis ---
    gate_traces = [t for t in traces if t.get("confidence_gate_evaluated")]
    if gate_traces:
        initial_scores = [t["initial_best_score"] for t in gate_traces
                          if t.get("initial_best_score") is not None]
        initial_scores.sort()
        rewrite_entered = sum(1 for t in gate_traces if t.get("rewrite_gate_entered"))
        rewrite_applied = sum(1 for t in gate_traces if t.get("rewrite_applied"))
        suppressed = sum(1 for t in gate_traces if t.get("retrieval_suppressed"))

        report["confidence_gate"] = {
            "evaluated": len(gate_traces),
            "rewrite_entered": rewrite_entered,
            "rewrite_entered_pct": round(rewrite_entered / len(gate_traces) * 100, 1),
            "rewrite_applied": rewrite_applied,
            "rewrite_applied_pct": round(rewrite_applied / len(gate_traces) * 100, 1) if gate_traces else 0,
            "suppressed": suppressed,
            "suppressed_pct": round(suppressed / len(gate_traces) * 100, 1),
            "initial_score_distribution": {
                "p25": round(percentile(initial_scores, 25), 4) if initial_scores else None,
                "p50": round(percentile(initial_scores, 50), 4) if initial_scores else None,
                "p75": round(percentile(initial_scores, 75), 4) if initial_scores else None,
            },
        }

    # --- Labeled data separation (CoSQA ground truth) ---
    labeled = [t for t in shadow_traces if t.get("_has_label") and t.get("reranker_best_score") is not None]
    if labeled:
        relevant = [t["reranker_best_score"] for t in labeled if t.get("_relevance_label") == 1]
        irrelevant = [t["reranker_best_score"] for t in labeled if t.get("_relevance_label") == 0]
        relevant.sort()
        irrelevant.sort()

        report["labeled_separation"] = {
            "relevant_count": len(relevant),
            "irrelevant_count": len(irrelevant),
        }
        if relevant:
            report["labeled_separation"]["relevant"] = {
                "min": round(min(relevant), 4),
                "max": round(max(relevant), 4),
                "mean": round(sum(relevant) / len(relevant), 4),
                "p25": round(percentile(relevant, 25), 4),
                "p50": round(percentile(relevant, 50), 4),
            }
        if irrelevant:
            report["labeled_separation"]["irrelevant"] = {
                "min": round(min(irrelevant), 4),
                "max": round(max(irrelevant), 4),
                "mean": round(sum(irrelevant) / len(irrelevant), 4),
                "p75": round(percentile(irrelevant, 75), 4),
                "p50": round(percentile(irrelevant, 50), 4),
            }
        if relevant and irrelevant:
            gap = min(relevant) - max(irrelevant)
            report["labeled_separation"]["gap"] = round(gap, 4)
            report["labeled_separation"]["clean_separation"] = gap > 0

    # --- Per-query-class breakdown ---
    class_groups = defaultdict(list)
    for t in shadow_traces:
        cls = t.get("_query_class", "unknown")
        if t.get("reranker_best_score") is not None:
            class_groups[cls].append(t["reranker_best_score"])

    if class_groups:
        report["per_query_class"] = {}
        for cls, cls_scores in sorted(class_groups.items()):
            cls_scores.sort()
            report["per_query_class"][cls] = {
                "count": len(cls_scores),
                "mean": round(sum(cls_scores) / len(cls_scores), 4),
                "p25": round(percentile(cls_scores, 25), 4),
                "p50": round(percentile(cls_scores, 50), 4),
                "p75": round(percentile(cls_scores, 75), 4),
            }

    # --- Per-dataset-source breakdown ---
    source_groups = defaultdict(list)
    for t in shadow_traces:
        src = t.get("_dataset_source", "organic")
        if t.get("reranker_best_score") is not None:
            source_groups[src].append(t["reranker_best_score"])

    if source_groups:
        report["per_dataset_source"] = {}
        for src, src_scores in sorted(source_groups.items()):
            src_scores.sort()
            report["per_dataset_source"][src] = {
                "count": len(src_scores),
                "mean": round(sum(src_scores) / len(src_scores), 4),
                "p50": round(percentile(src_scores, 50), 4),
            }

    # --- Threshold recommendations ---
    if scores:
        # Suppress threshold: should catch clearly irrelevant results
        # Recommend p10 of score distribution (bottom 10% get suppressed)
        suppress_rec = round(percentile(scores, 10), 4)

        # Rewrite threshold: should trigger for weak-but-not-terrible results
        # Recommend p25 of score distribution
        rewrite_rec = round(percentile(scores, 25), 4)

        report["threshold_recommendations"] = {
            "suppress_threshold": suppress_rec,
            "suppress_rationale": f"p10 of reranker score distribution — {suppress_rec:.4f} would suppress bottom 10%",
            "rewrite_threshold": rewrite_rec,
            "rewrite_rationale": f"p25 of reranker score distribution — {rewrite_rec:.4f} would trigger rewrite for bottom 25%",
            "current_candidate_threshold": 0.075,
            "note": "These are data-driven recommendations. Review per-class breakdown before applying.",
        }

        # If we have labeled data, use that instead
        if labeled and report.get("labeled_separation", {}).get("clean_separation"):
            irrel_max = max(t["reranker_best_score"] for t in labeled if t.get("_relevance_label") == 0)
            rel_min = min(t["reranker_best_score"] for t in labeled if t.get("_relevance_label") == 1)
            midpoint = round((irrel_max + rel_min) / 2, 4)
            report["threshold_recommendations"]["labeled_midpoint"] = midpoint
            report["threshold_recommendations"]["labeled_note"] = (
                f"Labeled data suggests suppress threshold at {midpoint:.4f} "
                f"(midpoint of gap: irrelevant max={irrel_max:.4f}, relevant min={rel_min:.4f})"
            )

    return report


def print_report(report: dict):
    """Print a human-readable calibration report."""
    print(f"\n{'='*70}")
    print(f"  SHADOW RERANKER CALIBRATION REPORT")
    print(f"{'='*70}")

    print(f"\nTotal traces: {report['total_traces']}")
    print(f"Shadow applied: {report['shadow_applied']}")
    print(f"Shadow not applied: {report['shadow_not_applied']}")

    if report.get("error"):
        print(f"\nERROR: {report['error']}")
        return

    sd = report.get("score_distribution", {})
    if sd:
        print(f"\n--- Score Distribution (reranker_best_score) ---")
        print(f"  Count: {sd['count']}")
        print(f"  Range: [{sd['min']}, {sd['max']}]")
        print(f"  Mean:  {sd['mean']}")
        print(f"  p10={sd['p10']}  p25={sd['p25']}  p50={sd['p50']}  p75={sd['p75']}  p90={sd['p90']}")
        print(f"\n  Histogram:")
        for b in sd.get("histogram", []):
            bar = "#" * min(b["count"], 50)
            print(f"    [{b['bin_start']:>7.4f}, {b['bin_end']:>7.4f}) {b['count']:>4d} {bar}")

    lp = report.get("latency_profile", {})
    if lp:
        print(f"\n--- Latency Profile (ms) ---")
        print(f"  p50={lp['p50']}  p75={lp['p75']}  p90={lp['p90']}  p95={lp['p95']}  p99={lp['p99']}")

    cg = report.get("confidence_gate", {})
    if cg:
        print(f"\n--- Confidence Gate ---")
        print(f"  Evaluated: {cg['evaluated']}")
        print(f"  Rewrite entered: {cg['rewrite_entered']} ({cg['rewrite_entered_pct']}%)")
        print(f"  Rewrite applied: {cg['rewrite_applied']} ({cg['rewrite_applied_pct']}%)")
        print(f"  Suppressed: {cg['suppressed']} ({cg['suppressed_pct']}%)")

    ls = report.get("labeled_separation", {})
    if ls:
        print(f"\n--- Labeled Data Separation ---")
        print(f"  Relevant: {ls['relevant_count']}  Irrelevant: {ls['irrelevant_count']}")
        if ls.get("relevant"):
            r = ls["relevant"]
            print(f"  Relevant scores:   mean={r['mean']}  p25={r['p25']}  p50={r['p50']}")
        if ls.get("irrelevant"):
            ir = ls["irrelevant"]
            print(f"  Irrelevant scores: mean={ir['mean']}  p50={ir['p50']}  p75={ir['p75']}")
        if "gap" in ls:
            sep = "CLEAN" if ls["clean_separation"] else "OVERLAP"
            print(f"  Gap: {ls['gap']}  ({sep})")

    pqc = report.get("per_query_class", {})
    if pqc:
        print(f"\n--- Per Query Class ---")
        for cls, stats in pqc.items():
            print(f"  {cls:20s}  n={stats['count']:>3d}  mean={stats['mean']:.4f}  p50={stats['p50']:.4f}")

    tr = report.get("threshold_recommendations", {})
    if tr:
        print(f"\n--- Threshold Recommendations ---")
        print(f"  Suppress: {tr['suppress_threshold']}  ({tr['suppress_rationale']})")
        print(f"  Rewrite:  {tr['rewrite_threshold']}  ({tr['rewrite_rationale']})")
        if tr.get("labeled_midpoint"):
            print(f"  Labeled:  {tr['labeled_midpoint']}  ({tr['labeled_note']})")
        print(f"\n  Current candidate threshold: {tr['current_candidate_threshold']}")
        print(f"  NOTE: {tr['note']}")

    print(f"\n{'='*70}")


def main():
    parser = argparse.ArgumentParser(description="Calibrate shadow reranker from collected traces")
    parser.add_argument("--db", default="hiveai.db",
                        help="SQLite database path (default: hiveai.db)")
    parser.add_argument("--results", default="data/synthetic_results.jsonl",
                        help="Synthetic results JSONL (default: data/synthetic_results.jsonl)")
    parser.add_argument("--output", default="data/calibration_report.json",
                        help="Output JSON report (default: data/calibration_report.json)")
    args = parser.parse_args()

    print("Loading traces...")
    db_traces = load_traces_from_db(args.db)
    result_traces = load_traces_from_results(args.results)

    all_traces = db_traces + result_traces
    if not all_traces:
        print("\nERROR: No traces found. Run synthetic_traffic.py first.")
        sys.exit(1)

    print(f"\nTotal: {len(all_traces)} traces ({len(db_traces)} DB + {len(result_traces)} synthetic)")

    report = analyze(all_traces)
    print_report(report)

    # Save JSON report
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nFull report saved to: {args.output}")


if __name__ == "__main__":
    main()
