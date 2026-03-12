"""Consolidation Training: Post-merge stabilization epoch.

After merging a LoRA into the base weights, run 1 epoch at LR/20 on 100% replay
data to smooth out merge artifacts. Uses a tiny rank-2 LoRA that gets merged
back immediately after.

This is a thin wrapper around train_v5.py with consolidation-specific settings.

Based on: ProgLoRA (ACL 2025), Online-LoRA (WACV 2025)

Usage:
    python scripts/consolidation_train.py \\
        --base-model-hf /opt/hiveai/project/models/training/v1-hive/hf \\
        --replay-data replay/sampled.jsonl \\
        --output-dir loras/v1-hive_consolidation

    # Then merge the consolidation LoRA back (alpha=1.0):
    python scripts/safe_merge.py \\
        --base-gguf models/deploy/v1-hive/merged.gguf \\
        --lora-gguf models/consolidation-lora.gguf \\
        --output-dir models/deploy/v1-hive \\
        --alphas 1.0 \\
        --validation-data replay/sampled.jsonl
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description="Post-merge consolidation training")
    parser.add_argument("--base-model-hf", required=True,
                        help="Path to merged HF checkpoint (bf16)")
    parser.add_argument("--replay-data", required=True,
                        help="Path to replay JSONL (100%% replay for consolidation)")
    parser.add_argument("--output-dir", required=True,
                        help="Output directory for consolidation LoRA adapter")
    parser.add_argument("--rank", type=int, default=2,
                        help="LoRA rank for consolidation (default: 2, minimal interference)")
    parser.add_argument("--lr", type=float, default=1e-5,
                        help="Learning rate (default: 1e-5 = base_lr/20)")
    parser.add_argument("--epochs", type=int, default=1,
                        help="Number of epochs (default: 1)")
    # v3.0 pass-through flags
    parser.add_argument("--style-tokens", action="store_true",
                        help="Enable style tokens (passed through to train_v5.py)")
    parser.add_argument("--probe-aware", action="store_true",
                        help="Enable probe-aware loss during consolidation")
    parser.add_argument("--hidden-anchor", action="store_true",
                        help="Enable hidden state anchoring during consolidation")
    parser.add_argument("--curlora-init", action="store_true",
                        help="Use CURLoRA initialization during consolidation")
    args = parser.parse_args()

    # Validate inputs
    if not os.path.exists(args.replay_data):
        print(f"ERROR: Replay data not found: {args.replay_data}")
        sys.exit(1)

    if not os.path.exists(args.base_model_hf):
        print(f"ERROR: Base model not found: {args.base_model_hf}")
        sys.exit(1)

    # Count replay samples
    with open(args.replay_data, "r", encoding="utf-8") as f:
        n_samples = sum(1 for line in f if line.strip())
    print(f"Consolidation training:")
    print(f"  Base model: {args.base_model_hf}")
    print(f"  Replay data: {args.replay_data} ({n_samples} samples)")
    print(f"  Rank: {args.rank} (minimal — just smoothing merge artifacts)")
    print(f"  LR: {args.lr} (LR/20 — very gentle)")
    print(f"  Epochs: {args.epochs}")
    print(f"  Output: {args.output_dir}")

    # Build train_v5.py command
    train_script = str(PROJECT_ROOT / "scripts" / "train_v5.py")
    cmd = [
        sys.executable, train_script,
        "--base-model-hf", args.base_model_hf,
        "--data", args.replay_data,
        "--output-dir", args.output_dir,
        "--rank", str(args.rank),
        "--lr", str(args.lr),
        "--epochs", str(args.epochs),
        "--no-kl",                  # No KL needed — replay IS the anchor
        "--consolidation-only",     # Flags consolidation mode
        "--lora-plus",              # LoRA+ for faster convergence
    ]
    # v3.0 pass-through flags
    if args.style_tokens:
        cmd.extend(["--style-tokens", "--style-mode", "direct"])
    if args.probe_aware:
        cmd.extend(["--probe-aware", "--probe-weight", "0.05",  # Half weight for consolidation
                     "--probe-guard", "--probe-interval", "5"])  # Force frequent checks on short runs
    if args.hidden_anchor:
        cmd.extend(["--hidden-anchor", "--anchor-weight", "0.025"])
    if args.curlora_init:
        cmd.append("--curlora-init")

    print(f"\nRunning: {' '.join(cmd)}")
    print("=" * 60)

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("  Consolidation training COMPLETE")
        print(f"  Adapter saved to: {args.output_dir}")
        print("  Next step: merge this adapter back into the base (alpha=1.0)")
        print("=" * 60)
    else:
        print(f"\nERROR: Consolidation training failed (exit code {result.returncode})")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
