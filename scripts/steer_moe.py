"""
scripts/steer_moe.py

SteerMoE: Training-free inference-time expert steering for Qwen3.5-35B-A3B.

Based on Adobe Research's SteerMoE (arXiv 2509.09660):
  - Identifies which experts activate more for coding vs non-coding tokens
  - At inference time, boosts/suppresses specific experts via gate bias
  - +20-27% improvement on targeted behaviors with ZERO retraining

Algorithm:
  1. Run coding calibration prompts → collect expert activation frequencies
  2. Run general calibration prompts → collect expert activation frequencies
  3. Compute "coding expert score" per expert = coding_freq - general_freq
  4. Generate a gate bias vector that boosts coding experts
  5. Save bias config → apply at inference time via llama-server or HF generate

Usage:
    python scripts/steer_moe.py                    # analyze and generate bias config
    python scripts/steer_moe.py --boost 0.5        # stronger coding bias
    python scripts/steer_moe.py --dry-run           # analysis only
    python scripts/steer_moe.py --visualize         # print expert activation heatmap

The output config can be applied to:
  - HuggingFace generate() via custom forward hook
  - llama-server via gate bias injection (when supported)
  - Direct model patching for GGUF export

Requirements:
    pip install torch transformers safetensors numpy
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / "qwen3.5-35b-a3b-pruned"
DEFAULT_OUTPUT = PROJECT_ROOT / "scripts" / "steer_moe_config.json"

NUM_LAYERS = 40
NUM_ACTIVE_EXPERTS = 8

# Coding-focused calibration prompts
CODING_PROMPTS = [
    "Write a Python function to implement binary search on a sorted array.",
    "Implement a thread-safe producer-consumer queue using Python asyncio.",
    "Design a REST API for a user authentication system with JWT tokens.",
    "Write unit tests for a binary search tree implementation using pytest.",
    "Implement the observer pattern in Python for a real-time notification system.",
    "Build a rate limiter using the token bucket algorithm.",
    "Write a Hive blockchain custom_json transaction builder using beem.",
    "Implement Dijkstra's shortest path algorithm with a min-heap priority queue.",
    "Design a circuit breaker pattern with configurable failure thresholds.",
    "Write a streaming JSON parser that handles arbitrarily large files.",
    "Implement a C++ smart pointer wrapper using RAII and move semantics.",
    "Build a Go HTTP server with middleware, graceful shutdown, and health checks.",
    "Write Rust code for a concurrent hash map using Arc<RwLock<HashMap>>.",
    "Implement a WebSocket server with connection pooling and heartbeat monitoring.",
    "Design a database migration system with rollback support.",
]

# General/non-coding calibration prompts
GENERAL_PROMPTS = [
    "What is the history of the Roman Empire and its decline?",
    "Explain the theory of relativity in simple terms.",
    "Write a short story about a journey through space.",
    "What are the health benefits of regular exercise?",
    "Describe the process of photosynthesis in detail.",
    "What are the main causes of World War I?",
    "Explain how democracy works in different countries.",
    "What is the meaning of life according to various philosophies?",
    "Describe the water cycle and its importance.",
    "What are the major religions of the world and their beliefs?",
]


def analyze_expert_activations(model_dir: str) -> dict:
    """
    Analyze expert activation patterns for coding vs general prompts.

    Returns dict with per-layer analysis:
        {layer_idx: {
            coding_freq: array(num_experts),
            general_freq: array(num_experts),
            coding_score: array(num_experts),  # coding_freq - general_freq
            top_coding_experts: list[int],
            top_general_experts: list[int],
        }}
    """
    # Use the ESFT script's collection logic if available
    try:
        from select_experts_esft import collect_expert_activations
        logger.info("Using ESFT activation collector")
    except ImportError:
        logger.info("ESFT script not importable, using inline collector")
        # Inline minimal version
        return _inline_analyze(model_dir)

    coding_acts = collect_expert_activations(model_dir, CODING_PROMPTS)
    general_acts = collect_expert_activations(model_dir, GENERAL_PROMPTS)

    analysis = {}
    for layer_idx in coding_acts:
        c = coding_acts[layer_idx]
        g = general_acts.get(layer_idx, np.zeros_like(c))

        c_total = max(c.sum(), 1)
        g_total = max(g.sum(), 1)
        c_freq = c / c_total
        g_freq = g / g_total

        coding_score = c_freq - g_freq

        # Top 10 coding experts (highest positive score)
        top_coding = np.argsort(coding_score)[::-1][:10].tolist()
        # Top 10 general experts (most negative score = least coding)
        top_general = np.argsort(coding_score)[:10].tolist()

        analysis[layer_idx] = {
            "coding_freq": c_freq,
            "general_freq": g_freq,
            "coding_score": coding_score,
            "top_coding_experts": top_coding,
            "top_general_experts": top_general,
        }

    return analysis


def _inline_analyze(model_dir: str) -> dict:
    """Fallback inline analyzer when ESFT module isn't available."""
    logger.warning("Using gate weight norms as proxy (no model loading)")
    logger.warning("For true activation analysis, use --with-model flag")

    # Use gate weight norms as a rough proxy
    import torch
    from safetensors import safe_open
    import glob as glob_mod
    import re

    gate_pattern = re.compile(r"layers\.(\d+)\.mlp\.gate\.weight$")
    analysis = {}

    shard_files = sorted(glob_mod.glob(os.path.join(model_dir, "model*.safetensors")))
    for shard_path in shard_files:
        with safe_open(shard_path, framework="pt", device="cpu") as f:
            for name in f.keys():
                match = gate_pattern.search(name)
                if match:
                    layer_idx = int(match.group(1))
                    weights = f.get_tensor(name).float()
                    norms = torch.norm(weights, dim=1).numpy()

                    # Use norm distribution as proxy: higher norm = more specialized
                    freq = norms / max(norms.sum(), 1)
                    analysis[layer_idx] = {
                        "coding_freq": freq,
                        "general_freq": np.ones_like(freq) / len(freq),
                        "coding_score": freq - (1.0 / len(freq)),
                        "top_coding_experts": np.argsort(norms)[::-1][:10].tolist(),
                        "top_general_experts": np.argsort(norms)[:10].tolist(),
                    }

    return analysis


def generate_gate_bias(analysis: dict, boost: float = 0.3) -> dict:
    """
    Generate per-layer gate bias vectors that boost coding experts.

    The bias is added to gate logits BEFORE top-k selection but NOT to
    the output weighting (Loss-Free Balancing approach from DeepSeek-V3).

    Args:
        analysis: per-layer activation analysis
        boost: strength of coding expert boost (0.0-1.0)

    Returns:
        dict mapping layer_idx -> list of bias values per expert
    """
    gate_bias = {}
    for layer_idx in sorted(analysis.keys()):
        scores = analysis[layer_idx]["coding_score"]
        num_experts = len(scores)

        # Normalize scores to [-1, 1] range
        max_abs = max(abs(scores.max()), abs(scores.min()), 1e-8)
        normalized = scores / max_abs

        # Apply boost: positive bias for coding experts, negative for general
        bias = normalized * boost

        gate_bias[layer_idx] = bias.tolist()

    return gate_bias


def visualize_experts(analysis: dict):
    """Print a text-based heatmap of expert coding affinity per layer."""
    print("\n  Expert Coding Affinity Heatmap")
    print("  " + "=" * 70)
    print("  Green = coding specialist, Red = general specialist")
    print()

    for layer_idx in sorted(list(analysis.keys())[:40]):  # max 40 layers
        scores = analysis[layer_idx]["coding_score"]
        # Show top 10 coding and bottom 10 general
        top_c = analysis[layer_idx]["top_coding_experts"][:5]
        top_g = analysis[layer_idx]["top_general_experts"][:5]

        # Mini bar for overall coding specialization
        mean_score = scores.mean()
        std_score = scores.std()
        specialization = std_score  # higher std = more specialized experts

        bar_len = int(specialization * 200)
        bar = "+" * min(bar_len, 30)

        print(f"  L{layer_idx:2d} [{bar:<30s}] "
              f"std={std_score:.4f} "
              f"coding={top_c[:3]} "
              f"general={top_g[:3]}")


def main():
    parser = argparse.ArgumentParser(
        description="SteerMoE: Inference-time expert boosting for coding",
    )
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR),
                        help="Path to model directory")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT),
                        help="Output config path")
    parser.add_argument("--boost", type=float, default=0.3,
                        help="Coding expert boost strength (default: 0.3)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Analysis only, don't save config")
    parser.add_argument("--visualize", action="store_true",
                        help="Show expert activation heatmap")
    args = parser.parse_args()

    print("=" * 60)
    print("  SteerMoE — Inference-Time Expert Boosting")
    print(f"  Boost strength: {args.boost}")
    print(f"  Model: {args.model_dir}")
    print("=" * 60)

    if not os.path.isdir(args.model_dir):
        alt = str(PROJECT_ROOT / "models" / "qwen3.5-35b-a3b")
        hf_sub = os.path.join(alt, "hf")
        if os.path.isdir(hf_sub):
            args.model_dir = hf_sub
        elif os.path.isdir(alt):
            args.model_dir = alt
        else:
            logger.error(f"Model directory not found: {args.model_dir}")
            sys.exit(1)

    # Check for /hf subdir
    hf_subdir = os.path.join(args.model_dir, "hf")
    model_dir = hf_subdir if os.path.isdir(hf_subdir) else args.model_dir

    # 1. Analyze expert activations
    print("\n  Analyzing expert activation patterns...")
    analysis = analyze_expert_activations(model_dir)

    if not analysis:
        logger.error("No expert analysis data collected")
        sys.exit(1)

    # 2. Visualize
    if args.visualize:
        visualize_experts(analysis)

    # 3. Generate gate bias
    gate_bias = generate_gate_bias(analysis, boost=args.boost)

    # 4. Report
    print("\n" + "=" * 60)
    print("  SteerMoE Analysis Results")
    print("=" * 60)

    total_boosted = 0
    total_suppressed = 0
    for layer_idx in sorted(gate_bias.keys()):
        bias = np.array(gate_bias[layer_idx])
        boosted = (bias > 0.01).sum()
        suppressed = (bias < -0.01).sum()
        total_boosted += boosted
        total_suppressed += suppressed

    print(f"  Experts boosted for coding: {total_boosted}")
    print(f"  Experts suppressed: {total_suppressed}")
    print(f"  Boost strength: {args.boost}")

    if args.dry_run:
        print("\n  --dry-run: No config saved.")
        if not args.visualize:
            visualize_experts(analysis)
        return

    # 5. Save config
    config = {
        "method": "SteerMoE (Inference-Time Expert Boosting)",
        "boost_strength": args.boost,
        "model_dir": str(model_dir),
        "total_boosted": int(total_boosted),
        "total_suppressed": int(total_suppressed),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gate_bias": {str(k): v for k, v in gate_bias.items()},
        "usage": (
            "Apply gate_bias[layer][expert] to gate logits BEFORE top-k selection. "
            "The bias shifts routing toward coding-specialized experts without "
            "affecting the output weighting (Loss-Free Balancing approach)."
        ),
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(config, f, indent=2)
    print(f"\n  Config saved to: {args.output}")
    print(f"\n  To apply at inference time:")
    print(f"    1. Load config: bias = json.load(open('{args.output}'))")
    print(f"    2. Hook into gate.forward() in each MoE layer")
    print(f"    3. Add bias[layer][expert] to gate logits before top-k")
    print("=" * 60)


if __name__ == "__main__":
    main()
