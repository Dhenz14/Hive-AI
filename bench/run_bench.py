#!/usr/bin/env python3
"""HiveAI Model Benchmark Harness.

Measures coding model quality across 4 categories:
  1. Single-shot code generation
  2. Multi-file refactoring
  3. Iterative debugging
  4. Long-context retention

Usage:
  # Benchmark Ollama model
  python bench/run_bench.py --model qwen2.5-coder:14b-q5_K_M

  # Benchmark llama-server model
  python bench/run_bench.py --model qwen2.5-coder-14b --backend llama-server --url http://localhost:8080

  # Compare two models
  python bench/run_bench.py --model qwen3.5:9b --compare qwen2.5-coder:14b-q5_K_M

  # Run specific category only
  python bench/run_bench.py --model qwen3.5:9b --category single_shot
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from bench.runner import ModelConfig, GenerationResult, generate, get_vram_usage_mb
from bench.tasks import get_all_tasks, TaskResult


SYSTEM_PROMPT = (
    "You are an expert Python programmer. Write clean, correct, well-structured code. "
    "Always include complete implementations, not pseudocode. "
    "When fixing bugs, explain the root cause before showing the fix."
)


def run_single_task(config: ModelConfig, task: dict) -> dict:
    """Run a single task and return combined metrics."""
    vram_before = get_vram_usage_mb()
    gen_result = generate(config, task["prompt"], system=SYSTEM_PROMPT)
    vram_after = get_vram_usage_mb()

    if gen_result.error:
        return {
            "task_id": task["id"],
            "category": task["category"],
            "error": gen_result.error,
            "passed": False,
            "score": 0.0,
        }

    evaluator = task["evaluator"]
    task_result = evaluator(gen_result.text, task)

    return {
        "task_id": task["id"],
        "category": task["category"],
        "passed": task_result.passed,
        "score": task_result.score,
        "details": task_result.details,
        "perf": {
            "tokens_generated": gen_result.tokens_generated,
            "tokens_per_sec": round(gen_result.tokens_per_sec, 1),
            "time_to_first_token_ms": round(gen_result.time_to_first_token_ms, 1),
            "total_time_ms": round(gen_result.total_time_ms, 1),
            "vram_peak_mb": round(max(vram_before, vram_after), 1),
        },
        "spec_decode": {
            "draft_tokens": gen_result.draft_tokens,
            "accepted_tokens": gen_result.accepted_tokens,
            "acceptance_rate": round(gen_result.acceptance_rate, 3),
        },
    }


def run_benchmark(config: ModelConfig, categories: list[str] | None = None) -> dict:
    """Run the full benchmark suite against a model."""
    all_tasks = get_all_tasks()
    if categories:
        all_tasks = [t for t in all_tasks if t["category"] in categories]

    print(f"\nBenchmarking: {config.name} ({config.backend})")
    print(f"Tasks: {len(all_tasks)}")
    print("-" * 60)

    results = []
    for i, task in enumerate(all_tasks, 1):
        label = f"[{i}/{len(all_tasks)}] {task['category']}/{task['id']}"
        print(f"  {label}...", end=" ", flush=True)

        task_result = run_single_task(config, task)
        results.append(task_result)

        status = "PASS" if task_result["passed"] else "FAIL"
        score = task_result["score"]
        tps = task_result.get("perf", {}).get("tokens_per_sec", 0)
        ttft = task_result.get("perf", {}).get("time_to_first_token_ms", 0)

        if task_result.get("error"):
            print(f"ERROR: {task_result['error'][:60]}")
        else:
            print(f"{status} (score={score:.2f}, {tps:.0f} t/s, TTFT={ttft:.0f}ms)")

    # Aggregate
    summary = _compute_summary(results, config)
    print("\n" + "=" * 60)
    _print_summary(summary)

    return {
        "model": config.name,
        "backend": config.backend,
        "draft_model": config.draft_model,
        "context_size": config.context_size,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "results": results,
    }


def _compute_summary(results: list[dict], config: ModelConfig) -> dict:
    """Compute aggregate summary statistics."""
    by_category = {}
    for r in results:
        cat = r["category"]
        by_category.setdefault(cat, []).append(r)

    category_summaries = {}
    for cat, cat_results in by_category.items():
        scores = [r["score"] for r in cat_results if "error" not in r]
        passed = sum(1 for r in cat_results if r.get("passed"))
        tps_values = [r["perf"]["tokens_per_sec"] for r in cat_results
                      if "perf" in r and r["perf"]["tokens_per_sec"] > 0]
        ttft_values = [r["perf"]["time_to_first_token_ms"] for r in cat_results
                       if "perf" in r and r["perf"]["time_to_first_token_ms"] > 0]
        vram_values = [r["perf"]["vram_peak_mb"] for r in cat_results
                       if "perf" in r and r["perf"]["vram_peak_mb"] > 0]

        category_summaries[cat] = {
            "tasks": len(cat_results),
            "passed": passed,
            "pass_rate": round(passed / len(cat_results), 3) if cat_results else 0,
            "avg_score": round(sum(scores) / len(scores), 3) if scores else 0,
            "avg_tokens_per_sec": round(sum(tps_values) / len(tps_values), 1) if tps_values else 0,
            "avg_ttft_ms": round(sum(ttft_values) / len(ttft_values), 1) if ttft_values else 0,
            "vram_peak_mb": round(max(vram_values), 1) if vram_values else 0,
        }

    # Overall
    all_scores = [r["score"] for r in results if "error" not in r]
    all_passed = sum(1 for r in results if r.get("passed"))
    all_tps = [r["perf"]["tokens_per_sec"] for r in results
               if "perf" in r and r["perf"]["tokens_per_sec"] > 0]
    all_ttft = [r["perf"]["time_to_first_token_ms"] for r in results
                if "perf" in r and r["perf"]["time_to_first_token_ms"] > 0]

    # Speculative decoding aggregate
    spec_drafted = sum(r.get("spec_decode", {}).get("draft_tokens", 0) for r in results)
    spec_accepted = sum(r.get("spec_decode", {}).get("accepted_tokens", 0) for r in results)

    return {
        "total_tasks": len(results),
        "total_passed": all_passed,
        "overall_pass_rate": round(all_passed / len(results), 3) if results else 0,
        "overall_avg_score": round(sum(all_scores) / len(all_scores), 3) if all_scores else 0,
        "avg_tokens_per_sec": round(sum(all_tps) / len(all_tps), 1) if all_tps else 0,
        "avg_ttft_ms": round(sum(all_ttft) / len(all_ttft), 1) if all_ttft else 0,
        "spec_decode_acceptance": round(spec_accepted / spec_drafted, 3) if spec_drafted > 0 else 0,
        "categories": category_summaries,
    }


def _print_summary(summary: dict):
    """Print a formatted summary to stdout."""
    print(f"Overall: {summary['total_passed']}/{summary['total_tasks']} passed "
          f"(score={summary['overall_avg_score']:.3f})")
    print(f"Speed:   {summary['avg_tokens_per_sec']:.1f} t/s avg, "
          f"TTFT={summary['avg_ttft_ms']:.0f}ms avg")
    if summary["spec_decode_acceptance"] > 0:
        print(f"Spec decode acceptance: {summary['spec_decode_acceptance']:.1%}")
    print()

    for cat, stats in summary["categories"].items():
        print(f"  {cat:15s}  {stats['passed']}/{stats['tasks']} passed  "
              f"score={stats['avg_score']:.3f}  "
              f"{stats['avg_tokens_per_sec']:.0f} t/s  "
              f"VRAM={stats['vram_peak_mb']:.0f}MB")


def compare_models(results: list[dict]):
    """Print a side-by-side comparison of benchmark results."""
    if len(results) < 2:
        return

    print("\n" + "=" * 70)
    print("MODEL COMPARISON")
    print("=" * 70)

    # Header
    names = [r["model"][:25] for r in results]
    print(f"{'Metric':<25s}", end="")
    for name in names:
        print(f"  {name:>20s}", end="")
    print()
    print("-" * (25 + 22 * len(names)))

    # Rows
    metrics = [
        ("Pass rate", lambda s: f"{s['overall_pass_rate']:.1%}"),
        ("Avg score", lambda s: f"{s['overall_avg_score']:.3f}"),
        ("Tokens/sec", lambda s: f"{s['avg_tokens_per_sec']:.1f}"),
        ("TTFT (ms)", lambda s: f"{s['avg_ttft_ms']:.0f}"),
        ("Spec decode accept", lambda s: f"{s['spec_decode_acceptance']:.1%}" if s['spec_decode_acceptance'] > 0 else "n/a"),
    ]

    for label, fmt in metrics:
        print(f"{label:<25s}", end="")
        for r in results:
            print(f"  {fmt(r['summary']):>20s}", end="")
        print()

    # Per-category
    all_cats = set()
    for r in results:
        all_cats.update(r["summary"]["categories"].keys())

    print()
    for cat in sorted(all_cats):
        print(f"  {cat}:")
        for sub_metric, sub_fmt in [
            ("  score", lambda s: f"{s.get('avg_score', 0):.3f}"),
            ("  pass_rate", lambda s: f"{s.get('pass_rate', 0):.1%}"),
            ("  t/s", lambda s: f"{s.get('avg_tokens_per_sec', 0):.1f}"),
        ]:
            print(f"  {sub_metric:<23s}", end="")
            for r in results:
                cat_stats = r["summary"]["categories"].get(cat, {})
                print(f"  {sub_fmt(cat_stats):>20s}", end="")
            print()


def save_results(data: dict, results_dir: Path):
    """Save benchmark results to a timestamped JSON file."""
    results_dir.mkdir(parents=True, exist_ok=True)
    model_slug = data["model"].replace("/", "_").replace(":", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"bench_{model_slug}_{ts}.json"
    filepath = results_dir / filename
    filepath.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"\nResults saved: {filepath}")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="HiveAI Model Benchmark Harness")
    parser.add_argument("--model", required=True, help="Model name (e.g. qwen2.5-coder:14b-q5_K_M)")
    parser.add_argument("--backend", default="ollama", choices=["ollama", "llama-server"],
                        help="Backend type (default: ollama)")
    parser.add_argument("--url", default=None,
                        help="Base URL (default: localhost:11434 for ollama, localhost:8080 for llama-server)")
    parser.add_argument("--draft", default="", help="Draft model for speculative decoding")
    parser.add_argument("--context", type=int, default=8192, help="Context window size (default: 8192)")
    parser.add_argument("--max-tokens", type=int, default=2048, help="Max generation tokens (default: 2048)")
    parser.add_argument("--category", nargs="*", default=None,
                        choices=["single_shot", "refactor", "debug", "context"],
                        help="Run only specific categories")
    parser.add_argument("--compare", default=None, help="Second model to compare against")
    parser.add_argument("--compare-backend", default="ollama", choices=["ollama", "llama-server"])
    parser.add_argument("--compare-url", default=None)
    parser.add_argument("--output", default="bench/results", help="Results directory")

    args = parser.parse_args()

    default_urls = {"ollama": "http://localhost:11434", "llama-server": "http://localhost:8080"}

    config = ModelConfig(
        name=args.model,
        backend=args.backend,
        base_url=args.url or default_urls[args.backend],
        draft_model=args.draft,
        context_size=args.context,
        max_tokens=args.max_tokens,
    )

    results_dir = Path(args.output)
    all_results = []

    # Run primary model
    data = run_benchmark(config, categories=args.category)
    save_results(data, results_dir)
    all_results.append(data)

    # Run comparison model if specified
    if args.compare:
        compare_config = ModelConfig(
            name=args.compare,
            backend=args.compare_backend,
            base_url=args.compare_url or default_urls[args.compare_backend],
            context_size=args.context,
            max_tokens=args.max_tokens,
        )
        compare_data = run_benchmark(compare_config, categories=args.category)
        save_results(compare_data, results_dir)
        all_results.append(compare_data)

    # Comparison table
    if len(all_results) > 1:
        compare_models(all_results)


if __name__ == "__main__":
    main()
