"""
scripts/select_experts_esft.py

Expert-Specialized Fine-Tuning (ESFT) expert selection for Qwen3.5-35B-A3B.

Based on DeepSeek's ESFT (EMNLP 2024): instead of training ALL experts with LoRA,
identify the top 10-15% of experts per layer that activate on coding tokens and
ONLY train those + attention LoRA. Results:
  - Matches or exceeds full fine-tune quality on coding benchmarks
  - 90% less storage than full fine-tune
  - 30% faster training
  - Better specialization (avoids catastrophic forgetting in unused experts)

Algorithm:
  1. Load model + tokenizer
  2. Run coding calibration prompts through the model
  3. Hook into each layer's MoE router to capture gate decisions
  4. Score each expert by mean gate activation on coding tokens
  5. Select top-K experts per layer (K = num_experts * select_ratio)
  6. Output: JSON config listing selected experts per layer
     → feed this into train_v4.py to only train selected expert MLPs

Usage:
    python scripts/select_experts_esft.py                      # default: top 15%
    python scripts/select_experts_esft.py --select-ratio 0.10  # top 10%
    python scripts/select_experts_esft.py --dry-run             # analysis only
    python scripts/select_experts_esft.py --use-pruned          # analyze pruned model

Requirements:
    pip install torch transformers safetensors
    ~48GB RAM for loading the full model (or use the pruned model)
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from collections import defaultdict

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / "qwen3.5-35b-a3b-pruned"
DEFAULT_OUTPUT = PROJECT_ROOT / "scripts" / "esft_config.json"

# Architecture constants
NUM_LAYERS = 40
NUM_EXPERTS_PER_LAYER = 256  # 128 if using pruned model
NUM_ACTIVE_EXPERTS = 8

# Calibration prompts — coding-focused to identify coding experts
CODING_CALIBRATION = [
    # Python algorithms
    "Implement a thread-safe LRU cache in Python with O(1) get and put using OrderedDict.",
    "Write a Python implementation of Dijkstra's algorithm for weighted directed graphs.",
    "Implement a B-tree in Python supporting insert, delete, search with configurable order.",
    # Systems programming
    "Implement a producer-consumer system using Python asyncio with backpressure and graceful shutdown.",
    "Write a connection pool in Python with max connections, health checks, and timeout handling.",
    "Build a rate limiter using the token bucket algorithm with per-user limits.",
    # C++/Systems concepts (in Python for tokenization but concepts matter)
    "Explain memory management in C++: RAII, smart pointers, move semantics, and rule of five.",
    "Implement a lock-free concurrent queue using compare-and-swap atomics.",
    "Write a custom memory allocator with free-list management and coalescing.",
    # Rust concepts
    "Explain Rust's ownership and borrowing system with lifetime annotations.",
    "Implement a thread-safe actor system using Rust channels and Arc<Mutex<T>>.",
    # Hive blockchain
    "Build a Hive blockchain transaction builder in Python using beem with RC checks.",
    "Write a dhive streaming processor in Node.js that indexes transfer operations.",
    "Implement a HAF-compatible block processor that tracks Hive Engine token balances.",
    # Web/API
    "Design a REST API with JWT authentication, rate limiting, and proper error handling.",
    "Implement a WebSocket server with connection pooling and heartbeat monitoring.",
    # Testing
    "Write comprehensive property-based tests using Hypothesis for a binary search tree.",
    "Implement a mutation testing framework that identifies weak test suites.",
    # Design patterns
    "Implement the circuit breaker pattern with half-open state and configurable thresholds.",
    "Build an event-driven architecture with pub/sub, dead letter queue, and retry logic.",
]

# Non-coding calibration (to identify experts that are NOT coding-specific)
GENERAL_CALIBRATION = [
    "What is the history of the Roman Empire and its fall?",
    "Explain the principles of quantum mechanics in simple terms.",
    "Write a poem about the beauty of nature in autumn.",
    "What are the main arguments for and against climate change policies?",
    "Describe the process of photosynthesis in plants.",
]


def collect_expert_activations(model_dir: str, prompts: list,
                                max_length: int = 512) -> dict:
    """
    Run prompts through the model and collect per-expert activation counts.

    Returns:
        dict mapping layer_idx -> numpy array of shape (num_experts,)
        with activation counts per expert.
    """
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM

    logger.info(f"Loading model from {model_dir}...")
    tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)

    # Try to load with minimal memory
    model = AutoModelForCausalLM.from_pretrained(
        model_dir,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map="cpu",
        low_cpu_mem_usage=True,
    )
    model.eval()

    # Detect actual number of experts from model
    actual_num_experts = NUM_EXPERTS_PER_LAYER
    try:
        gate_weight = model.model.language_model.layers[0].mlp.gate.weight
        actual_num_experts = gate_weight.shape[0]
        logger.info(f"Detected {actual_num_experts} experts per layer")
    except (AttributeError, IndexError):
        logger.warning("Could not detect expert count, using default")

    activation_counts = {}
    hooks = []

    def make_gate_hook(layer_idx):
        def hook(module, input_tensor, output):
            if isinstance(input_tensor, tuple):
                hidden = input_tensor[0]
            else:
                hidden = input_tensor

            # Gate output: (batch, seq, num_experts) or just the weight application
            # We want to see which experts the router selects
            with torch.no_grad():
                if hasattr(module, 'weight'):
                    gate_logits = torch.matmul(hidden.float(), module.weight.float().T)
                    topk = gate_logits.topk(NUM_ACTIVE_EXPERTS, dim=-1)
                    indices = topk.indices.reshape(-1)
                    for idx in indices.tolist():
                        if 0 <= idx < actual_num_experts:
                            activation_counts[layer_idx][idx] += 1
        return hook

    # Register hooks
    for layer_idx in range(NUM_LAYERS):
        activation_counts[layer_idx] = np.zeros(actual_num_experts, dtype=np.float64)
        try:
            gate_module = model.model.language_model.layers[layer_idx].mlp.gate
            hooks.append(gate_module.register_forward_hook(make_gate_hook(layer_idx)))
        except (AttributeError, IndexError):
            continue

    if not hooks:
        logger.error("No gate modules found!")
        del model
        return {}

    # Run prompts
    logger.info(f"Running {len(prompts)} calibration prompts...")
    with torch.no_grad():
        for i, prompt in enumerate(prompts):
            tokens = tokenizer(prompt, return_tensors="pt", truncation=True,
                             max_length=max_length)
            try:
                model(**tokens)
            except Exception as e:
                logger.warning(f"Prompt {i} failed: {e}")
            if (i + 1) % 5 == 0:
                logger.info(f"  Processed {i+1}/{len(prompts)} prompts")

    for h in hooks:
        h.remove()
    del model

    return activation_counts


def compute_coding_affinity(coding_activations: dict,
                            general_activations: dict) -> dict:
    """
    Compute per-expert coding affinity: how much more an expert activates
    on coding tokens vs general tokens.

    Returns:
        dict mapping layer_idx -> numpy array of coding affinity scores
    """
    affinity = {}
    for layer_idx in coding_activations:
        coding = coding_activations[layer_idx]
        general = general_activations.get(layer_idx, np.zeros_like(coding))

        # Normalize to frequencies
        c_total = coding.sum()
        g_total = general.sum()
        c_freq = coding / max(c_total, 1)
        g_freq = general / max(g_total, 1)

        # Affinity = coding frequency - general frequency
        # Positive = coding specialist, negative = general specialist
        aff = c_freq - g_freq

        # Also factor in absolute coding activation (don't want experts that
        # are slightly more coding but rarely fire at all)
        aff = aff * np.sqrt(c_freq)  # weight by sqrt of coding frequency

        affinity[layer_idx] = aff

    return affinity


def select_experts(affinity: dict, select_ratio: float = 0.15) -> dict:
    """
    Select top-K experts per layer based on coding affinity.

    Returns:
        dict mapping layer_idx -> list of selected expert indices
    """
    selected = {}
    for layer_idx in sorted(affinity.keys()):
        scores = affinity[layer_idx]
        num_experts = len(scores)
        k = max(int(num_experts * select_ratio), NUM_ACTIVE_EXPERTS)

        # Select top-K by affinity
        top_indices = np.argsort(scores)[::-1][:k].tolist()
        selected[layer_idx] = sorted(top_indices)

        logger.debug(f"  Layer {layer_idx}: selected {len(top_indices)}/{num_experts} "
                    f"experts (top affinity: {scores[top_indices[0]]:.4f})")

    return selected


def main():
    parser = argparse.ArgumentParser(
        description="ESFT Expert Selection for Qwen3.5-35B-A3B",
    )
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR),
                        help="Path to model directory")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT),
                        help="Output JSON config path")
    parser.add_argument("--select-ratio", type=float, default=0.15,
                        help="Fraction of experts to select per layer (default: 0.15)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Analysis only, don't save config")
    parser.add_argument("--use-pruned", action="store_true",
                        help="Use pruned model (128 experts instead of 256)")
    args = parser.parse_args()

    print("=" * 60)
    print("  ESFT Expert Selection — Qwen3.5-35B-A3B")
    print(f"  Select ratio: {args.select_ratio:.0%}")
    print(f"  Model: {args.model_dir}")
    print("=" * 60)

    if not os.path.isdir(args.model_dir):
        # Fallback to unpruned
        alt = str(PROJECT_ROOT / "models" / "qwen3.5-35b-a3b")
        if os.path.isdir(alt):
            args.model_dir = alt
            logger.info(f"Using unpruned model: {alt}")
        else:
            logger.error(f"Model directory not found: {args.model_dir}")
            sys.exit(1)

    # Check for /hf subdir
    hf_subdir = os.path.join(args.model_dir, "hf")
    model_dir = hf_subdir if os.path.isdir(hf_subdir) else args.model_dir

    # 1. Collect coding activations
    print("\n  Phase 1: Coding calibration...")
    coding_acts = collect_expert_activations(model_dir, CODING_CALIBRATION)

    # 2. Collect general activations
    print("\n  Phase 2: General calibration...")
    general_acts = collect_expert_activations(model_dir, GENERAL_CALIBRATION)

    if not coding_acts:
        logger.error("Failed to collect activations")
        sys.exit(1)

    # 3. Compute coding affinity
    print("\n  Phase 3: Computing coding affinity...")
    affinity = compute_coding_affinity(coding_acts, general_acts)

    # 4. Select experts
    selected = select_experts(affinity, select_ratio=args.select_ratio)

    # 5. Report
    print("\n" + "=" * 60)
    print("  ESFT Expert Selection Results")
    print("=" * 60)

    total_selected = 0
    total_experts = 0
    for layer_idx in sorted(selected.keys()):
        sel = selected[layer_idx]
        num = len(affinity[layer_idx])
        total_selected += len(sel)
        total_experts += num
        top_score = affinity[layer_idx][sel[0]] if sel else 0
        bar = "#" * int(len(sel) / num * 40)
        print(f"  Layer {layer_idx:2d}: {len(sel):3d}/{num:3d} experts "
              f"[{bar:<40s}] top_affinity={top_score:.4f}")

    print(f"\n  Total: {total_selected}/{total_experts} experts selected "
          f"({total_selected/total_experts:.1%})")
    print(f"  Storage: ~{total_selected * 0.001:.1f} GB adapter "
          f"(vs ~{total_experts * 0.001:.1f} GB full)")

    if args.dry_run:
        print("\n  --dry-run: No config saved.")
        return

    # 6. Save config
    config = {
        "method": "ESFT (Expert-Specialized Fine-Tuning)",
        "select_ratio": args.select_ratio,
        "model_dir": str(model_dir),
        "total_selected": total_selected,
        "total_experts": total_experts,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "selected_experts": {str(k): v for k, v in selected.items()},
        "coding_calibration_prompts": len(CODING_CALIBRATION),
        "general_calibration_prompts": len(GENERAL_CALIBRATION),
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(config, f, indent=2)
    print(f"\n  Config saved to: {args.output}")
    print(f"  Use with: python scripts/train_v4.py --esft-config {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
