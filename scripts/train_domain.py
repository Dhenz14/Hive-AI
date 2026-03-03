#!/usr/bin/env python3
"""
Train a domain-specialized LoRA adapter from existing training data.

Filters v5.jsonl (or other data files) by domain keywords, then trains
a domain-specific LoRA on the merge-cycled base model.

    python scripts/train_domain.py --domain python
    python scripts/train_domain.py --domain hive --base models/qwen3.5-9b-cycle1
    python scripts/train_domain.py --domain rust --data loras/training_data/v5.jsonl
    python scripts/train_domain.py --list  # show available domains
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hiveai.lora.molora import DOMAINS
from hiveai.lora.merge_cycle import get_current_base, PROJECT_ROOT


DEFAULT_DATA_FILE = os.path.join(PROJECT_ROOT, "loras", "training_data", "v5.jsonl")
DEFAULT_BASE = os.path.join(PROJECT_ROOT, "models", "qwen3.5-9b")
MIN_DOMAIN_PAIRS = 50
SUPPLEMENT_PAIRS = 500  # add general pairs if domain has too few


def load_jsonl(path: str) -> list[dict]:
    pairs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    return pairs


def filter_by_domain(pairs: list[dict], domain: str) -> tuple[list[dict], list[dict]]:
    """Split pairs into domain-matching and non-matching."""
    config = DOMAINS.get(domain, {})
    keywords = config.get("keywords", [])
    if not keywords:
        return pairs, []

    domain_pairs = []
    general_pairs = []
    for pair in pairs:
        text = (pair.get("instruction", "") + " " + pair.get("response", "")).lower()
        if any(kw in text for kw in keywords):
            domain_pairs.append(pair)
        else:
            general_pairs.append(pair)
    return domain_pairs, general_pairs


def list_domains():
    print(f"{'Domain':>12}  {'Keywords':>8}  {'Ollama Model':30}  {'Adapter Path'}")
    print("-" * 80)
    for domain, config in DOMAINS.items():
        print(f"{domain:>12}  {len(config.get('keywords', [])):>8}  "
              f"{config['ollama_model']:30}  {config['adapter_path']}")


def main():
    parser = argparse.ArgumentParser(description="Train a domain-specialized LoRA adapter")
    parser.add_argument("--domain", type=str, help="Domain to train (e.g., python, hive, rust)")
    parser.add_argument("--data", type=str, default=DEFAULT_DATA_FILE, help="Training data JSONL file")
    parser.add_argument("--base", type=str, help="Base model directory (default: latest cycle or models/qwen3.5-9b)")
    parser.add_argument("--output", type=str, help="Output adapter directory (default: loras/domains/{domain}/)")
    parser.add_argument("--min-pairs", type=int, default=MIN_DOMAIN_PAIRS, help="Minimum domain pairs required")
    parser.add_argument("--supplement", type=int, default=SUPPLEMENT_PAIRS, help="Max general pairs to add if domain has too few")
    parser.add_argument("--list", action="store_true", help="List available domains")
    parser.add_argument("--dry-run", action="store_true", help="Filter data and show stats, don't train")
    args = parser.parse_args()

    if args.list:
        list_domains()
        return

    if not args.domain:
        parser.error("--domain is required (e.g., --domain python). Use --list to see options.")

    if args.domain not in DOMAINS or args.domain == "general":
        print(f"Error: unknown domain '{args.domain}'. Available: {[d for d in DOMAINS if d != 'general']}")
        sys.exit(1)

    # Resolve paths
    data_file = args.data
    if not os.path.isabs(data_file):
        data_file = os.path.join(PROJECT_ROOT, data_file)

    if not os.path.exists(data_file):
        print(f"Error: data file not found: {data_file}")
        sys.exit(1)

    if args.base:
        base_dir = args.base if os.path.isabs(args.base) else os.path.join(PROJECT_ROOT, args.base)
    else:
        base_dir = get_current_base() or DEFAULT_BASE
        if not os.path.isabs(base_dir):
            base_dir = os.path.join(PROJECT_ROOT, base_dir)

    output_dir = args.output or os.path.join(PROJECT_ROOT, "loras", "domains", args.domain)

    # Load and filter data
    print(f"Loading training data from {data_file}...")
    all_pairs = load_jsonl(data_file)
    print(f"  Total pairs: {len(all_pairs)}")

    domain_pairs, general_pairs = filter_by_domain(all_pairs, args.domain)
    print(f"  {args.domain} domain pairs: {len(domain_pairs)}")
    print(f"  General pairs: {len(general_pairs)}")

    if len(domain_pairs) < args.min_pairs:
        print(f"\n  Warning: only {len(domain_pairs)} domain pairs (min: {args.min_pairs})")
        supplement_count = min(args.supplement - len(domain_pairs), len(general_pairs))
        if supplement_count > 0:
            # Add general pairs to reach supplement target
            import random
            random.shuffle(general_pairs)
            domain_pairs.extend(general_pairs[:supplement_count])
            print(f"  Supplemented with {supplement_count} general pairs → {len(domain_pairs)} total")

    if len(domain_pairs) < 10:
        print(f"\nError: only {len(domain_pairs)} pairs — not enough to train. Need at least 10.")
        sys.exit(1)

    # Write filtered data
    domain_data_file = os.path.join(PROJECT_ROOT, "loras", "training_data", f"{args.domain}.jsonl")
    os.makedirs(os.path.dirname(domain_data_file), exist_ok=True)
    with open(domain_data_file, "w") as f:
        for pair in domain_pairs:
            f.write(json.dumps(pair) + "\n")
    print(f"\n  Domain training data: {domain_data_file} ({len(domain_pairs)} pairs)")

    if args.dry_run:
        print("\n  [DRY RUN] Would train with:")
        print(f"    Base:    {base_dir}")
        print(f"    Data:    {domain_data_file}")
        print(f"    Output:  {output_dir}")
        print(f"    Pairs:   {len(domain_pairs)}")
        return

    # Train using train_v5.py with --data and --output overrides
    print(f"\n  Training {args.domain} domain LoRA...")
    print(f"  Base:   {base_dir}")
    print(f"  Output: {output_dir}")

    import subprocess
    train_script = os.path.join(PROJECT_ROOT, "scripts", "train_v5.py")
    cmd = [
        sys.executable, train_script,
        "--data", domain_data_file,
        "--output", output_dir,
        "--model-path", base_dir,
    ]
    print(f"  Command: {' '.join(cmd)}")
    print(f"\n  Note: Run this in WSL2 for GPU training:")
    print(f"  wsl -d Ubuntu-24.04 -- bash -c 'source /opt/hiveai-env/bin/activate && "
          f"cd /opt/hiveai/project && python scripts/train_v5.py "
          f"--data loras/training_data/{args.domain}.jsonl "
          f"--output loras/domains/{args.domain}/'")


if __name__ == "__main__":
    main()
