#!/usr/bin/env python3
"""
CLI for LoRA Merge Cycling.

    python scripts/auto_cycle.py --adapter loras/v5 --min-score 0.85
    python scripts/auto_cycle.py --adapter loras/v5 --deploy --eval
    python scripts/auto_cycle.py --adapter loras/v5 --dry-run
    python scripts/auto_cycle.py --history
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hiveai.lora.merge_cycle import (
    run_merge_cycle,
    load_merge_history,
    get_current_base,
    get_next_cycle_number,
    PROJECT_ROOT,
)


DEFAULT_BASE = os.path.join(PROJECT_ROOT, "models", "qwen3.5-9b")


def show_history():
    history = load_merge_history()
    if not history:
        print("No merge cycles recorded yet.")
        return
    print(f"{'Cycle':>5}  {'Base In':40}  {'Base Out':40}  {'Eval':>6}  {'Time':>6}")
    print("-" * 105)
    for h in history:
        eval_str = f"{h.get('eval_after', 0):.3f}" if h.get("eval_after") else "  n/a"
        time_str = f"{h.get('merge_time_s', 0):.0f}s"
        print(f"{h['cycle']:>5}  {h['base_in']:40}  {h['base_out']:40}  {eval_str:>6}  {time_str:>6}")


def main():
    parser = argparse.ArgumentParser(description="LoRA Merge Cycling — bake adapters into base weights")
    parser.add_argument("--adapter", type=str, help="Path to LoRA adapter directory (e.g., loras/v5)")
    parser.add_argument("--base", type=str, help="Base model directory (default: auto-detect from history or models/qwen3.5-9b)")
    parser.add_argument("--output", type=str, help="Output directory for merged model (default: models/qwen3.5-9b-cycleN)")
    parser.add_argument("--min-score", type=float, default=0.0, help="Minimum eval score to proceed (0 = skip gate)")
    parser.add_argument("--eval-model", type=str, help="Ollama model name for pre-merge eval")
    parser.add_argument("--deploy", action="store_true", help="Also export GGUF and register in Ollama")
    parser.add_argument("--ollama-name", type=str, help="Ollama model name for deployed model")
    parser.add_argument("--quant", default="Q8_0", help="GGUF quantization (default: Q8_0)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen, don't merge")
    parser.add_argument("--history", action="store_true", help="Show merge cycle history")
    args = parser.parse_args()

    if args.history:
        show_history()
        return

    if not args.adapter:
        parser.error("--adapter is required (e.g., --adapter loras/v5)")

    adapter_dir = os.path.join(PROJECT_ROOT, args.adapter) if not os.path.isabs(args.adapter) else args.adapter

    # Auto-detect base: use last merged output, or fallback to default
    if args.base:
        base_dir = os.path.join(PROJECT_ROOT, args.base) if not os.path.isabs(args.base) else args.base
    else:
        base_dir = get_current_base() or DEFAULT_BASE
        if not os.path.isabs(base_dir):
            base_dir = os.path.join(PROJECT_ROOT, base_dir)

    # Auto-generate output path
    cycle_num = get_next_cycle_number()
    if args.output:
        output_dir = os.path.join(PROJECT_ROOT, args.output) if not os.path.isabs(args.output) else args.output
    else:
        output_dir = os.path.join(PROJECT_ROOT, "models", f"qwen3.5-9b-cycle{cycle_num}")

    print("=" * 60)
    print(f"  LoRA Merge Cycle {cycle_num}")
    print("=" * 60)
    print(f"  Adapter:  {adapter_dir}")
    print(f"  Base:     {base_dir}")
    print(f"  Output:   {output_dir}")
    if args.deploy:
        name = args.ollama_name or f"hiveai-v5-cycle{cycle_num}"
        print(f"  Deploy:   {name} ({args.quant})")
    if args.min_score > 0:
        print(f"  Gate:     min score {args.min_score}")
    if args.dry_run:
        print(f"  Mode:     DRY RUN")
    print("=" * 60)

    ollama_name = args.ollama_name or (f"hiveai-v5-cycle{cycle_num}" if args.deploy else None)

    result = run_merge_cycle(
        adapter_dir=adapter_dir,
        base_model_dir=base_dir,
        output_base_dir=output_dir,
        min_eval_score=args.min_score,
        eval_model_name=args.eval_model,
        deploy_to_ollama=args.deploy,
        ollama_model_name=ollama_name,
        gguf_quant=args.quant,
        dry_run=args.dry_run,
    )

    print()
    if result.success:
        print(f"  CYCLE {result.cycle_number} {'(dry run) ' if args.dry_run else ''}COMPLETE")
        if result.eval_score_before is not None:
            print(f"  Eval before: {result.eval_score_before:.3f}")
        if result.eval_score_after is not None:
            print(f"  Eval after:  {result.eval_score_after:.3f}")
        if result.merge_time_s > 0:
            print(f"  Merge time:  {result.merge_time_s:.0f}s")
        print(f"\n  Next cycle base: {output_dir}")
    else:
        print(f"  CYCLE {result.cycle_number} FAILED: {result.error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
