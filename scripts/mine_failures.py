#!/usr/bin/env python3
"""
mine_failures.py — Analyze eval results to find weaknesses and generate v9 training prompts.

Reads eval report JSON(s), categorizes failures by dimension/category/topic,
identifies systematic weaknesses, and generates targeted Claude prompts
for creating training pairs that address each gap.

Usage:
    python scripts/mine_failures.py                              # Latest eval report
    python scripts/mine_failures.py --report evals/foo.json      # Specific report
    python scripts/mine_failures.py --threshold 0.8              # Higher bar
    python scripts/mine_failures.py --generate                   # Write batch templates
    python scripts/mine_failures.py --compare evals/a.json evals/b.json  # Diff two reports
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = PROJECT_ROOT / "evals"
CHALLENGES_PATH = PROJECT_ROOT / "scripts" / "eval_challenges.json"
OUTPUT_DIR = PROJECT_ROOT / "scripts" / "distill_batches"

# Weakness thresholds
FAIL_THRESHOLD = 0.60       # Hard failure
MARGINAL_THRESHOLD = 0.70   # Needs improvement
WEAK_DIM_THRESHOLD = 0.50   # Dimension-level weakness


def load_report(path: str) -> dict:
    """Load an eval report JSON."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_latest_report() -> str | None:
    """Find the most recent eval report by file modification time."""
    if not EVALS_DIR.exists():
        return None
    reports = sorted(EVALS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    # Skip failure_analysis files
    reports = [r for r in reports if "failure_analysis" not in r.name]
    return str(reports[0]) if reports else None


def load_challenges() -> dict:
    """Load challenge definitions keyed by ID."""
    with open(CHALLENGES_PATH, encoding="utf-8") as f:
        challenges = json.load(f)
    return {c["id"]: c for c in challenges}


def analyze_failures(report: dict, threshold: float = MARGINAL_THRESHOLD) -> dict:
    """Deep analysis of failures from an eval report.

    Returns structured weakness report with multiple views:
    - by_category: which domains are weakest
    - by_dimension: which scoring dimensions drag scores down
    - by_topic: specific topics that fail
    - by_difficulty: failure rate by difficulty level
    - worst_challenges: ranked list of worst-performing challenges
    - systematic_gaps: patterns across multiple failures
    """
    challenges = report.get("challenges", [])
    scored = [c for c in challenges if c.get("scores") and not c.get("error")]

    if not scored:
        return {"error": "No scored challenges found in report"}

    # --- By Category ---
    by_category = defaultdict(lambda: {"scores": [], "failures": [], "dimensions": defaultdict(list)})
    for c in scored:
        cat = c["category"]
        overall = c["scores"]["overall"]
        by_category[cat]["scores"].append(overall)
        if overall < threshold:
            by_category[cat]["failures"].append(c)
        for dim in ["code_validity", "test_passing", "concept_coverage", "explanation"]:
            val = c["scores"].get(dim)
            if val is not None:
                by_category[cat]["dimensions"][dim].append(val)

    category_summary = {}
    for cat, data in sorted(by_category.items()):
        avg_score = sum(data["scores"]) / len(data["scores"])
        fail_rate = len(data["failures"]) / len(data["scores"])
        dim_avgs = {d: sum(v) / len(v) for d, v in data["dimensions"].items() if v}
        weakest_dim = min(dim_avgs, key=dim_avgs.get) if dim_avgs else "unknown"
        category_summary[cat] = {
            "avg_score": round(avg_score, 3),
            "fail_rate": round(fail_rate, 3),
            "total": len(data["scores"]),
            "failures": len(data["failures"]),
            "weakest_dimension": weakest_dim,
            "dimension_avgs": {k: round(v, 3) for k, v in dim_avgs.items()},
            "failed_ids": [c["id"] for c in data["failures"]],
        }

    # --- By Dimension (across all categories) ---
    dim_scores = defaultdict(list)
    dim_failures = defaultdict(list)
    for c in scored:
        for dim in ["code_validity", "test_passing", "concept_coverage", "explanation"]:
            val = c["scores"].get(dim)
            if val is not None:
                dim_scores[dim].append(val)
                if val < WEAK_DIM_THRESHOLD:
                    dim_failures[dim].append({
                        "id": c["id"],
                        "category": c["category"],
                        "topic": c.get("topic", ""),
                        "score": val,
                    })

    dimension_summary = {}
    for dim in ["code_validity", "test_passing", "concept_coverage", "explanation"]:
        scores = dim_scores.get(dim, [])
        if scores:
            dimension_summary[dim] = {
                "avg": round(sum(scores) / len(scores), 3),
                "min": round(min(scores), 3),
                "failures_below_50": len(dim_failures.get(dim, [])),
                "worst_3": sorted(dim_failures.get(dim, []), key=lambda x: x["score"])[:3],
            }

    # --- By Topic ---
    by_topic = defaultdict(lambda: {"scores": [], "failures": []})
    for c in scored:
        topic = c.get("topic", "unknown")
        overall = c["scores"]["overall"]
        by_topic[topic]["scores"].append(overall)
        if overall < threshold:
            by_topic[topic]["failures"].append(c["id"])

    topic_summary = {}
    for topic, data in by_topic.items():
        if data["failures"]:
            topic_summary[topic] = {
                "avg_score": round(sum(data["scores"]) / len(data["scores"]), 3),
                "fail_count": len(data["failures"]),
                "total": len(data["scores"]),
                "failed_ids": data["failures"],
            }

    # --- By Difficulty ---
    by_diff = defaultdict(lambda: {"scores": [], "failures": 0})
    for c in scored:
        diff = c.get("difficulty", 0)
        overall = c["scores"]["overall"]
        by_diff[diff]["scores"].append(overall)
        if overall < threshold:
            by_diff[diff]["failures"] += 1

    difficulty_summary = {}
    for diff in sorted(by_diff.keys()):
        data = by_diff[diff]
        difficulty_summary[f"D{diff}"] = {
            "avg_score": round(sum(data["scores"]) / len(data["scores"]), 3),
            "fail_rate": round(data["failures"] / len(data["scores"]), 3),
            "total": len(data["scores"]),
            "failures": data["failures"],
        }

    # --- Worst Challenges ---
    worst = sorted(scored, key=lambda c: c["scores"]["overall"])[:20]
    worst_list = []
    for c in worst:
        worst_list.append({
            "id": c["id"],
            "category": c["category"],
            "topic": c.get("topic", ""),
            "difficulty": c.get("difficulty", 0),
            "overall": c["scores"]["overall"],
            "code_validity": c["scores"].get("code_validity", 0),
            "test_passing": c["scores"].get("test_passing"),
            "concept_coverage": c["scores"].get("concept_coverage", 0),
            "explanation": c["scores"].get("explanation", 0),
        })

    # --- Systematic Gaps ---
    gaps = []

    # Gap: categories with >50% failure rate
    for cat, data in category_summary.items():
        if data["fail_rate"] > 0.5:
            gaps.append({
                "type": "category_weak",
                "category": cat,
                "fail_rate": data["fail_rate"],
                "recommendation": f"Generate 20+ deep {cat} training pairs with <think> traces",
            })

    # Gap: dimensions consistently low
    for dim, data in dimension_summary.items():
        if data["avg"] < 0.6:
            gaps.append({
                "type": "dimension_weak",
                "dimension": dim,
                "avg_score": data["avg"],
                "recommendation": f"Focus training pairs on improving {dim.replace('_', ' ')}",
            })

    # Gap: high difficulty failures (D4-D5 with low scores)
    for diff_label, data in difficulty_summary.items():
        if diff_label in ("D4", "D5") and data["fail_rate"] > 0.6:
            gaps.append({
                "type": "difficulty_gap",
                "difficulty": diff_label,
                "fail_rate": data["fail_rate"],
                "recommendation": f"Add expert-level ({diff_label}) reasoning pairs",
            })

    # Gap: explanation quality (common weakness)
    if dimension_summary.get("explanation", {}).get("avg", 1) < 0.5:
        gaps.append({
            "type": "explanation_weak",
            "avg_score": dimension_summary["explanation"]["avg"],
            "recommendation": "Train with pairs that have detailed prose explanations, not just code",
        })

    return {
        "model": report.get("model", "unknown"),
        "overall_score": report.get("overall_score", 0),
        "total_scored": len(scored),
        "total_failures": len([c for c in scored if c["scores"]["overall"] < threshold]),
        "threshold": threshold,
        "by_category": category_summary,
        "by_dimension": dimension_summary,
        "by_topic": dict(sorted(topic_summary.items(), key=lambda x: x[1]["avg_score"])),
        "by_difficulty": difficulty_summary,
        "worst_challenges": worst_list,
        "systematic_gaps": gaps,
    }


def generate_training_prompts(analysis: dict, challenges_db: dict) -> list[dict]:
    """Generate Claude prompts for creating targeted training pairs.

    Each prompt targets a specific weakness found in the analysis.
    Returns list of {category, topic, difficulty, prompt, rationale}.
    """
    prompts = []

    # For each worst challenge, generate a targeted prompt
    for item in analysis.get("worst_challenges", [])[:15]:
        challenge = challenges_db.get(item["id"])
        if not challenge:
            continue

        # Determine what dimension needs the most help
        dims = {
            "code_validity": item.get("code_validity", 1),
            "concept_coverage": item.get("concept_coverage", 1),
            "explanation": item.get("explanation", 1),
        }
        weakest = min(dims, key=dims.get)

        dim_guidance = {
            "code_validity": "Include complete, runnable code with proper error handling, imports, and edge case handling. The code MUST compile/execute without errors.",
            "concept_coverage": "Explicitly cover ALL expected concepts: " + ", ".join(challenge.get("expected_concepts", [])),
            "explanation": "Include detailed prose explanation: WHY this approach works, trade-offs, complexity analysis, and step-by-step reasoning. Use headers, bold terms, and structured sections.",
        }

        prompt = {
            "category": item["category"],
            "topic": item.get("topic", "general"),
            "difficulty": item.get("difficulty", 3),
            "target_weakness": weakest,
            "original_score": item["overall"],
            "prompt": f"""Write a high-quality training pair for a coding assistant. The user asks:

"{challenge['instruction']}"

Requirements:
- Include deep <think> reasoning before the answer (5-15 lines analyzing the problem, approach, edge cases)
- {dim_guidance[weakest]}
- Response should be 300-800 words with a good mix of code and explanation
- Use markdown formatting: headers, code blocks, bold terms
- Mention at least 2 edge cases or common mistakes
- If relevant, show a usage example after the implementation""",
            "rationale": f"Challenge {item['id']} scored {item['overall']:.3f} overall, {dims[weakest]:.3f} on {weakest}",
        }
        prompts.append(prompt)

    # For weak categories, generate category-level prompts
    for cat, data in analysis.get("by_category", {}).items():
        if data["fail_rate"] > 0.4 and data["total"] >= 3:
            weak_dim = data["weakest_dimension"]
            prompts.append({
                "category": cat,
                "topic": "category_reinforcement",
                "difficulty": 3,
                "target_weakness": weak_dim,
                "original_score": data["avg_score"],
                "prompt": f"""Generate 5 diverse {cat} training pairs at difficulty 3-4.

Category weakness: {weak_dim.replace('_', ' ')} (avg {data['dimension_avgs'].get(weak_dim, 0):.3f})
Failed challenge IDs: {', '.join(data['failed_ids'][:5])}

Each pair should:
- Have a realistic, specific coding question (not generic)
- Include <think> reasoning traces
- Focus on improving {weak_dim.replace('_', ' ')}
- Cover different sub-topics within {cat}
- Be production-quality with error handling and tests""",
                "rationale": f"Category {cat}: {data['fail_rate']:.0%} failure rate, weakest on {weak_dim}",
            })

    return prompts


def generate_batch_template(prompts: list[dict], batch_num: int) -> str:
    """Generate a Python batch file template from training prompts."""
    lines = [
        f'"""',
        f'batch_p{batch_num}_failure_mining.py -- Targeted training pairs from failure analysis.',
        f'Auto-generated by mine_failures.py. Fill responses with Claude.',
        f'"""',
        f'',
        f'PAIRS = [',
    ]

    for i, p in enumerate(prompts):
        tag = f"fm_{p['category']}_{i+1:02d}"
        lines.append(f'    # {p["rationale"]}')
        lines.append(f'    ("{tag}",')
        instruction = p["prompt"].split('"')[1] if p["prompt"].count('"') >= 2 else f"[{p['category']}] {p['topic']} question"
        lines.append(f"     r'''{instruction}''',")
        lines.append(f"     r'''<think>")
        lines.append(f"[FILL: Analyze the problem, approach, and edge cases]")
        lines.append(f"</think>")
        lines.append(f"")
        lines.append(f"[FILL: Complete response with code, explanation, and examples]")
        lines.append(f"'''),")
        lines.append(f"")

    lines.append("]")
    return "\n".join(lines)


def compare_reports(path_a: str, path_b: str, threshold: float) -> dict:
    """Compare two eval reports and show improvements/regressions."""
    a = load_report(path_a)
    b = load_report(path_b)
    analysis_a = analyze_failures(a, threshold)
    analysis_b = analyze_failures(b, threshold)

    comparison = {
        "report_a": {"path": path_a, "model": a.get("model"), "overall": a.get("overall_score")},
        "report_b": {"path": path_b, "model": b.get("model"), "overall": b.get("overall_score")},
        "delta_overall": round(b.get("overall_score", 0) - a.get("overall_score", 0), 3),
        "category_deltas": {},
        "improved": [],
        "regressed": [],
    }

    cats_a = analysis_a.get("by_category", {})
    cats_b = analysis_b.get("by_category", {})
    all_cats = set(list(cats_a.keys()) + list(cats_b.keys()))

    for cat in sorted(all_cats):
        score_a = cats_a.get(cat, {}).get("avg_score", 0)
        score_b = cats_b.get(cat, {}).get("avg_score", 0)
        delta = round(score_b - score_a, 3)
        comparison["category_deltas"][cat] = {
            "before": score_a, "after": score_b, "delta": delta
        }
        if delta > 0.05:
            comparison["improved"].append(cat)
        elif delta < -0.05:
            comparison["regressed"].append(cat)

    return comparison


def print_analysis(analysis: dict):
    """Pretty-print the failure analysis."""
    print("=" * 70)
    print(f"  FAILURE MINING REPORT -- {analysis['model']}")
    print(f"  Overall: {analysis['overall_score']:.3f} | "
          f"Scored: {analysis['total_scored']} | "
          f"Failures (<{analysis['threshold']}): {analysis['total_failures']}")
    print("=" * 70)

    # Category breakdown
    print("\n--- BY CATEGORY ---")
    print(f"{'Category':<20} {'Score':>6} {'Fail%':>6} {'N':>4} {'Weakest Dimension':<20}")
    print("-" * 60)
    for cat, data in sorted(analysis["by_category"].items(), key=lambda x: x[1]["avg_score"]):
        marker = " !!!" if data["fail_rate"] > 0.5 else ""
        print(f"{cat:<20} {data['avg_score']:>6.3f} {data['fail_rate']:>5.0%} {data['total']:>4} "
              f"{data['weakest_dimension']:<20}{marker}")

    # Dimension breakdown
    print("\n--- BY DIMENSION ---")
    print(f"{'Dimension':<22} {'Avg':>6} {'Min':>6} {'Weak(<0.5)':>10}")
    print("-" * 50)
    for dim, data in analysis["by_dimension"].items():
        marker = " !!!" if data["avg"] < 0.6 else ""
        print(f"{dim:<22} {data['avg']:>6.3f} {data['min']:>6.3f} {data['failures_below_50']:>10}{marker}")

    # Difficulty breakdown
    print("\n--- BY DIFFICULTY ---")
    print(f"{'Level':<8} {'Score':>6} {'Fail%':>6} {'N':>4}")
    print("-" * 30)
    for diff, data in analysis["by_difficulty"].items():
        print(f"{diff:<8} {data['avg_score']:>6.3f} {data['fail_rate']:>5.0%} {data['total']:>4}")

    # Worst challenges
    print("\n--- WORST 10 CHALLENGES ---")
    print(f"{'ID':<20} {'Cat':<15} {'Overall':>7} {'Code':>6} {'Test':>6} {'Concept':>7} {'Explain':>7}")
    print("-" * 80)
    for c in analysis["worst_challenges"][:10]:
        test = f"{c['test_passing']:.3f}" if c["test_passing"] is not None else "  n/a"
        print(f"{c['id']:<20} {c['category']:<15} {c['overall']:>7.3f} "
              f"{c['code_validity']:>6.3f} {test:>6} {c['concept_coverage']:>7.3f} "
              f"{c['explanation']:>7.3f}")

    # Systematic gaps
    if analysis["systematic_gaps"]:
        print("\n--- SYSTEMATIC GAPS ---")
        for gap in analysis["systematic_gaps"]:
            print(f"  [{gap['type']}] {gap['recommendation']}")

    # Failed topics
    if analysis["by_topic"]:
        print("\n--- WEAKEST TOPICS ---")
        for topic, data in list(analysis["by_topic"].items())[:10]:
            print(f"  {topic}: {data['avg_score']:.3f} ({data['fail_count']}/{data['total']} failed)")


def main():
    parser = argparse.ArgumentParser(description="Mine eval failures for v9 training data")
    parser.add_argument("--report", type=str, help="Path to eval report JSON")
    parser.add_argument("--threshold", type=float, default=MARGINAL_THRESHOLD,
                        help=f"Failure threshold (default: {MARGINAL_THRESHOLD})")
    parser.add_argument("--generate", action="store_true",
                        help="Generate batch file templates for weak areas")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"),
                        help="Compare two eval reports")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.compare:
        comparison = compare_reports(args.compare[0], args.compare[1], args.threshold)
        if args.json:
            print(json.dumps(comparison, indent=2))
        else:
            print(f"\nComparing: {comparison['report_a']['model']} -> {comparison['report_b']['model']}")
            print(f"Overall: {comparison['report_a']['overall']:.3f} -> {comparison['report_b']['overall']:.3f} "
                  f"(delta {comparison['delta_overall']:+.3f})")
            print(f"\nImproved: {', '.join(comparison['improved']) or 'none'}")
            print(f"Regressed: {', '.join(comparison['regressed']) or 'none'}")
            for cat, d in sorted(comparison["category_deltas"].items(), key=lambda x: x[1]["delta"]):
                marker = "^" if d["delta"] > 0.05 else "v" if d["delta"] < -0.05 else " "
                print(f"  {marker} {cat:<20} {d['before']:.3f} -> {d['after']:.3f} ({d['delta']:+.3f})")
        return

    # Load report
    report_path = args.report or find_latest_report()
    if not report_path:
        print("No eval reports found in evals/. Run an eval first:")
        print("  python scripts/run_eval.py --model <model> --base-url <url>")
        sys.exit(1)

    print(f"Loading: {report_path}")
    report = load_report(report_path)
    analysis = analyze_failures(report, args.threshold)

    if args.json:
        print(json.dumps(analysis, indent=2))
        return

    print_analysis(analysis)

    # Generate training prompts
    challenges_db = load_challenges()
    prompts = generate_training_prompts(analysis, challenges_db)

    print(f"\n--- GENERATED {len(prompts)} TRAINING PROMPTS ---")
    for i, p in enumerate(prompts):
        print(f"  [{i+1}] {p['category']}/{p['topic']} (targeting: {p['target_weakness']}, "
              f"was: {p['original_score']:.3f})")

    if args.generate and prompts:
        # Find next batch number
        existing = list(OUTPUT_DIR.glob("batch_p*_failure_mining*.py"))
        batch_nums = []
        for f in existing:
            try:
                num = int(f.stem.split("_")[1][1:])
                batch_nums.append(num)
            except (IndexError, ValueError):
                pass
        next_num = max(batch_nums, default=1350) + 1

        template = generate_batch_template(prompts, next_num)
        out_path = OUTPUT_DIR / f"batch_p{next_num}_failure_mining.py"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(template)
        print(f"\n  Batch template written to: {out_path}")
        print(f"  Fill in the responses with Claude, then rebuild v5.jsonl")

    # Save analysis
    analysis_path = EVALS_DIR / f"failure_analysis_{analysis['model']}_{report.get('timestamp', 'unknown')[:10]}.json"
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2)
    print(f"\n  Full analysis saved to: {analysis_path}")


if __name__ == "__main__":
    main()
