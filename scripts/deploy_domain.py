#!/usr/bin/env python3
"""
Deploy a domain-specialized LoRA adapter as an Ollama model.

Merges the domain adapter into the base (or cycle) model, exports to GGUF,
and registers with Ollama.

    python scripts/deploy_domain.py --domain python
    python scripts/deploy_domain.py --domain hive --base models/qwen3.5-9b-cycle1
    python scripts/deploy_domain.py --domain rust --quant Q4_K_M
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hiveai.lora.molora import DOMAINS
from hiveai.lora.merge_cycle import (
    verify_adapter_files,
    merge_model,
    verify_merged_model,
    export_gguf,
    create_ollama_model,
    run_eval,
    get_current_base,
    PROJECT_ROOT,
)


DEFAULT_BASE = os.path.join(PROJECT_ROOT, "models", "qwen3.5-9b")


def main():
    parser = argparse.ArgumentParser(description="Deploy a domain LoRA adapter to Ollama")
    parser.add_argument("--domain", type=str, required=True, help="Domain to deploy (e.g., python, hive, rust)")
    parser.add_argument("--base", type=str, help="Base model directory (default: latest cycle or models/qwen3.5-9b)")
    parser.add_argument("--adapter", type=str, help="Adapter directory (default: loras/domains/{domain}/)")
    parser.add_argument("--quant", default="Q8_0", help="GGUF quantization (default: Q8_0)")
    parser.add_argument("--eval", action="store_true", help="Run eval after deployment")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    args = parser.parse_args()

    if args.domain not in DOMAINS or args.domain == "general":
        print(f"Error: unknown domain '{args.domain}'. Available: {[d for d in DOMAINS if d != 'general']}")
        sys.exit(1)

    config = DOMAINS[args.domain]
    ollama_model = config["ollama_model"]

    # Resolve paths
    adapter_dir = args.adapter or os.path.join(PROJECT_ROOT, config["adapter_path"])
    if not os.path.isabs(adapter_dir):
        adapter_dir = os.path.join(PROJECT_ROOT, adapter_dir)

    if args.base:
        base_dir = args.base if os.path.isabs(args.base) else os.path.join(PROJECT_ROOT, args.base)
    else:
        base_dir = get_current_base() or DEFAULT_BASE
        if not os.path.isabs(base_dir):
            base_dir = os.path.join(PROJECT_ROOT, base_dir)

    merged_dir = os.path.join(PROJECT_ROOT, "models", f"{ollama_model}-merged")
    gguf_path = os.path.join(merged_dir, f"{ollama_model}.gguf")

    print("=" * 60)
    print(f"  Deploy Domain: {args.domain}")
    print("=" * 60)
    print(f"  Adapter:   {adapter_dir}")
    print(f"  Base:      {base_dir}")
    print(f"  Merged:    {merged_dir}")
    print(f"  GGUF:      {gguf_path}")
    print(f"  Ollama:    {ollama_model}")
    print(f"  Quant:     {args.quant}")
    print("=" * 60)

    if args.dry_run:
        print("\n  [DRY RUN] Would deploy above configuration.")
        return

    # 1. Verify adapter
    if not verify_adapter_files(adapter_dir):
        print(f"\nError: adapter not found at {adapter_dir}")
        print(f"  Train it first: python scripts/train_domain.py --domain {args.domain}")
        sys.exit(1)

    # 2. Merge
    print("\nMerging adapter into base...")
    if not merge_model(base_dir, adapter_dir, merged_dir):
        print("Error: merge failed!")
        sys.exit(1)

    if not verify_merged_model(merged_dir):
        print("Error: merged model verification failed!")
        sys.exit(1)

    # 3. Export GGUF
    print("\nExporting to GGUF...")
    if not export_gguf(merged_dir, gguf_path, quant=args.quant):
        print("Error: GGUF export failed!")
        sys.exit(1)

    # 4. Create Ollama model
    print("\nCreating Ollama model...")
    if not create_ollama_model(gguf_path, ollama_model):
        print("Error: Ollama model creation failed!")
        sys.exit(1)

    # 5. Eval (optional)
    score = None
    if args.eval:
        print("\nRunning eval...")
        score = run_eval(ollama_model)

    # Summary
    print("\n" + "=" * 60)
    print(f"  Domain '{args.domain}' deployed as '{ollama_model}'")
    print("=" * 60)
    if score is not None:
        print(f"  Eval score: {score:.3f}")
    print(f"\n  Test: ollama run {ollama_model} 'Hello, test query'")
    print(f"  Enable routing: set MOLORA_ENABLED=true in .env")
    print("=" * 60)


if __name__ == "__main__":
    main()
