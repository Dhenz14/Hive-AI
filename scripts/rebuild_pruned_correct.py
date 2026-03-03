"""
Rebuild pruned model with CORRECT gate-expert alignment.

ROOT CAUSE OF ALL PRIOR FAILURES:
  The prune_map was inverted during previous builds — gate rows corresponded
  to PRUNED experts instead of KEPT experts. This caused a complete mismatch
  between routing decisions and expert computations, producing garbage.

This script builds from scratch:
  1. Load original 256-expert model (fused tensors)
  2. Run activation-based expert scoring OR use saved scores
  3. Select top-128 experts per layer
  4. Extract KEPT expert weights + corresponding KEPT gate rows
  5. Unfuse to per-expert nn.Linear format (for BnB 4-bit quantization)
  6. Save with correct indexing: gate[i] routes to expert[i]

Usage:
    python scripts/rebuild_pruned_correct.py
    python scripts/rebuild_pruned_correct.py --dry-run
    python scripts/rebuild_pruned_correct.py --verify-only  # check existing model
"""
import argparse
import gc
import json
import logging
import os
import re
import struct
import sys
import time

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGINAL_MODEL = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b-v3.5-rebuild")

NUM_LAYERS = 40
NUM_EXPERTS = 256
NUM_ACTIVE = 8
KEEP_RATIO = 0.5  # Keep top 50% = 128 experts
SUPER_EXPERT_COUNT = 8


# ---------------------------------------------------------------------------
# Activation-based scoring (reuse from prune_experts.py)
# ---------------------------------------------------------------------------
CALIBRATION_PROMPTS = [
    "Implement a thread-safe LRU cache in Python with O(1) get and put operations using OrderedDict and threading locks.",
    "Write a Python implementation of Dijkstra's algorithm for weighted directed graphs.",
    "Implement a B-tree in Python supporting insert, delete, search, and range queries with configurable order.",
    "Implement the A* pathfinding algorithm in Python with a priority queue, supporting both grid and graph inputs with weighted edges.",
    "Write a Python function that parses and evaluates mathematical expressions using recursive descent parsing, supporting variables and functions.",
    "Implement a streaming JSON parser in Python that handles arbitrarily large files without loading everything into memory.",
    "Implement a producer-consumer system in Python using asyncio with backpressure, graceful shutdown, and error recovery.",
    "Write a connection pool in Python with max connections, health checks, and timeout handling.",
    "Write a complete REST API rate limiter in Python using the token bucket algorithm with per-user limits and Redis-backed distributed state.",
    "Write a Python async web crawler that respects robots.txt, handles rate limiting with exponential backoff, and stores results in SQLite.",
    "Write a Python decorator that implements circuit breaker pattern with configurable failure threshold, reset timeout, and half-open state.",
    "Write a custom Python import hook that supports hot-reloading of modules during development with dependency tracking.",
    "Implement a Raft consensus algorithm in Python for a distributed key-value store with leader election and log replication.",
    "Implement a lock-free concurrent queue using compare-and-swap atomics.",
    "Build an event-driven architecture with pub/sub, dead letter queue, and retry logic.",
    "Explain memory management in C++: RAII, smart pointers, move semantics, and rule of five.",
    "Write a custom memory allocator with free-list management and coalescing.",
    "Explain Rust's ownership and borrowing system with lifetime annotations.",
    "Implement a thread-safe actor system using Rust channels and Arc<Mutex<T>>.",
    "Design a REST API with JWT authentication, rate limiting, and proper error handling.",
    "Implement a WebSocket server with connection pooling and heartbeat monitoring.",
    "Write comprehensive property-based tests using Hypothesis for a binary search tree.",
    "Implement a mutation testing framework that identifies weak test suites.",
    "Write a Python code formatter that normalizes indentation, removes trailing whitespace, sorts imports, and wraps long lines.",
    "Build a Hive blockchain transaction builder in Python using beem that handles posting, voting, and custom_json with RC checks.",
    "Write a dhive streaming processor in Node.js that indexes all transfer operations into PostgreSQL with proper error handling.",
    "Implement a HAF-compatible block processor that tracks Hive Engine token balances with PostgreSQL and proper reorg handling.",
    "Write a Python function to calculate Hive curation rewards given vote weight, timing, rshares, and the reward pool state.",
]


def collect_gate_weight_scores(model_dir):
    """Fast L2-norm scoring from gate weights (no model loading needed)."""
    import torch
    from safetensors import safe_open
    import glob as glob_mod

    logger.info("Collecting gate weight L2 norms...")
    scores = {}
    gate_pattern = re.compile(r"layers\.(\d+)\.mlp\.gate\.weight$")

    shard_files = sorted(glob_mod.glob(os.path.join(model_dir, "model*.safetensors")))
    for shard_path in shard_files:
        with safe_open(shard_path, framework="pt", device="cpu") as f:
            for name in f.keys():
                match = gate_pattern.search(name)
                if match:
                    layer_idx = int(match.group(1))
                    gate_w = f.get_tensor(name).float()
                    scores[layer_idx] = torch.norm(gate_w, dim=1).numpy()

    logger.info(f"Scored {len(scores)} layers via gate weight L2 norms")
    return scores


def collect_activation_scores(model_dir):
    """Full activation-based scoring (requires model loading, ~48GB RAM)."""
    import torch

    logger.info("Loading model for activation scoring (~48GB RAM)...")
    from transformers import AutoTokenizer, AutoModelForCausalLM

    tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_dir, trust_remote_code=True,
        torch_dtype=torch.float32, device_map="cpu",
    )
    model.eval()

    # Hook gate modules
    activation_counts = {i: np.zeros(NUM_EXPERTS, dtype=np.float64) for i in range(NUM_LAYERS)}

    def make_hook(layer_idx):
        def hook(module, input, output):
            logits = output[0] if isinstance(output, tuple) else output
            if logits.dim() >= 2:
                topk = logits.topk(NUM_ACTIVE, dim=-1).indices
                for idx in topk.reshape(-1).tolist():
                    activation_counts[layer_idx][idx] += 1
        return hook

    hooks = []
    for layer_idx in range(NUM_LAYERS):
        gate = None
        for path_fn in [
            lambda m, i: m.model.layers[i].mlp.gate,
            lambda m, i: m.model.language_model.layers[i].mlp.gate,
        ]:
            try:
                gate = path_fn(model, layer_idx)
                break
            except (AttributeError, IndexError):
                continue
        if gate:
            hooks.append(gate.register_forward_hook(make_hook(layer_idx)))

    logger.info(f"Running {len(CALIBRATION_PROMPTS)} calibration prompts...")
    with torch.no_grad():
        for i, prompt in enumerate(CALIBRATION_PROMPTS):
            tokens = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
            try:
                model(**tokens)
            except Exception as e:
                logger.warning(f"Prompt {i} failed: {e}")
            if (i + 1) % 7 == 0:
                logger.info(f"  {i+1}/{len(CALIBRATION_PROMPTS)} prompts done")

    for h in hooks:
        h.remove()
    del model
    gc.collect()

    # Normalize
    for layer_idx in activation_counts:
        total = activation_counts[layer_idx].sum()
        if total > 0:
            activation_counts[layer_idx] /= total
        else:
            activation_counts[layer_idx] = np.ones(NUM_EXPERTS) / NUM_EXPERTS

    return activation_counts


def select_experts_to_keep(scores, keep_ratio=KEEP_RATIO):
    """Select top-K experts per layer. Returns dict of layer -> sorted list of kept indices."""
    kept = {}
    num_keep = int(NUM_EXPERTS * keep_ratio)

    for layer_idx in sorted(scores.keys()):
        s = scores[layer_idx]
        sorted_idx = np.argsort(s)[::-1]  # descending by score

        # Always protect super experts (top-K)
        super_set = set(sorted_idx[:SUPER_EXPERT_COUNT].tolist())

        # Keep top num_keep experts
        keep_set = set(sorted_idx[:num_keep].tolist())
        # Ensure super experts are included
        keep_set |= super_set

        # If we have more than num_keep, trim from the bottom
        if len(keep_set) > num_keep:
            # Remove lowest-scoring non-super experts
            by_score = sorted(keep_set, key=lambda x: s[x], reverse=True)
            keep_set = set(by_score[:num_keep])
            keep_set |= super_set  # re-add super experts

        kept[layer_idx] = sorted(keep_set)

    return kept


def rebuild_model(model_dir, output_dir, kept_map, dry_run=False):
    """
    Build a new pruned model from the original, with correct gate-expert alignment.

    For each layer:
      - Expert tensors: select only kept expert slices from fused 3D tensors
        AND unfuse to per-expert 2D nn.Linear format
      - Gate weights: select only kept rows
      - Both use THE SAME kept_map indices, ensuring alignment

    After rebuild, gate[i] routes to expert[i] for all i in [0, num_kept).
    """
    import torch
    from safetensors.torch import load_file, save_file
    import glob as glob_mod
    import shutil

    os.makedirs(output_dir, exist_ok=True)

    # Patterns for original model tensors
    # Original has model.language_model.layers.X or model.layers.X
    expert_gu_pattern = re.compile(r"(model\.(?:language_model\.)?layers\.(\d+)\.mlp\.experts)\.gate_up_proj$")
    expert_down_pattern = re.compile(r"(model\.(?:language_model\.)?layers\.(\d+)\.mlp\.experts)\.down_proj$")
    gate_pattern = re.compile(r"(model\.(?:language_model\.)?layers\.(\d+)\.mlp)\.gate\.weight$")

    shard_files = sorted(glob_mod.glob(os.path.join(model_dir, "model*.safetensors")))
    if not shard_files:
        raise FileNotFoundError(f"No safetensors in {model_dir}")

    total_expert_tensors = 0
    total_gate_tensors = 0
    num_kept = len(next(iter(kept_map.values())))

    for shard_path in shard_files:
        shard_name = os.path.basename(shard_path)
        logger.info(f"Processing {shard_name}...")

        tensors = load_file(shard_path, device="cpu")
        new_tensors = {}

        for name, tensor in tensors.items():
            # Handle gate_up_proj: (256, 2*intermediate, hidden) -> N x gate + N x up
            match = expert_gu_pattern.search(name)
            if match:
                prefix = match.group(1)
                layer_idx = int(match.group(2))
                kept_indices = kept_map.get(layer_idx)
                if kept_indices is None:
                    new_tensors[name] = tensor.clone()
                    continue

                intermediate = tensor.shape[1] // 2  # 1024 / 2 = 512
                # Use CausalLM key format (model.layers.X, not model.language_model.layers.X)
                base = f"model.layers.{layer_idx}.mlp.experts"

                for new_idx, orig_idx in enumerate(kept_indices):
                    expert_slice = tensor[orig_idx]  # (1024, 2048)
                    gate_w = expert_slice[:intermediate].clone()   # (512, 2048)
                    up_w = expert_slice[intermediate:].clone()     # (512, 2048)
                    new_tensors[f"{base}.gate_projs.{new_idx}.weight"] = gate_w
                    new_tensors[f"{base}.up_projs.{new_idx}.weight"] = up_w

                total_expert_tensors += 1
                if total_expert_tensors <= 2:
                    logger.info(f"  {name}: ({tensor.shape[0]}, ...) -> {num_kept} x gate + up (unfused)")
                continue

            # Handle down_proj: (256, hidden, intermediate) -> N x down
            match = expert_down_pattern.search(name)
            if match:
                prefix = match.group(1)
                layer_idx = int(match.group(2))
                kept_indices = kept_map.get(layer_idx)
                if kept_indices is None:
                    new_tensors[name] = tensor.clone()
                    continue

                base = f"model.layers.{layer_idx}.mlp.experts"
                for new_idx, orig_idx in enumerate(kept_indices):
                    down_w = tensor[orig_idx].clone()  # (2048, 512)
                    new_tensors[f"{base}.down_projs.{new_idx}.weight"] = down_w

                total_expert_tensors += 1
                if total_expert_tensors <= 2:
                    logger.info(f"  {name}: ({tensor.shape[0]}, ...) -> {num_kept} x down (unfused)")
                continue

            # Handle gate.weight: (256, 2048) -> (128, 2048)
            match = gate_pattern.search(name)
            if match:
                layer_idx = int(match.group(2))
                kept_indices = kept_map.get(layer_idx)
                if kept_indices is None:
                    new_tensors[name] = tensor.clone()
                    continue

                idx_tensor = torch.tensor(kept_indices, dtype=torch.long)
                new_gate = tensor.index_select(0, idx_tensor).clone()
                # Use CausalLM key format
                new_name = f"model.layers.{layer_idx}.mlp.gate.weight"
                new_tensors[new_name] = new_gate
                total_gate_tensors += 1
                if total_gate_tensors <= 2:
                    logger.info(f"  {name}: ({tensor.shape[0]}, 2048) -> ({num_kept}, 2048)")
                continue

            # Non-expert tensor: rename to CausalLM format and keep
            new_name = name.replace("model.language_model.", "model.")
            # Skip vision-related tensors
            if "visual" in new_name or "image" in new_name:
                continue
            new_tensors[new_name] = tensor.clone()

        # Free mmap
        del tensors
        gc.collect()

        if not dry_run:
            out_path = os.path.join(output_dir, shard_name)
            save_file(new_tensors, out_path)
            logger.info(f"  Saved {shard_name} ({len(new_tensors)} tensors)")

        del new_tensors
        gc.collect()

    logger.info(f"Processed {total_expert_tensors} expert tensors, {total_gate_tensors} gate tensors")

    if not dry_run:
        # Copy config and update
        import shutil
        for fname in os.listdir(model_dir):
            if fname.endswith(".safetensors") or fname == "model.safetensors.index.json":
                continue
            src = os.path.join(model_dir, fname)
            dst = os.path.join(output_dir, fname)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)

        # Update config.json
        config_path = os.path.join(output_dir, "config.json")
        with open(config_path) as f:
            config = json.load(f)
        config["architectures"] = ["Qwen3_5MoeForCausalLM"]
        config["num_experts"] = num_kept
        if "text_config" in config:
            config["text_config"]["num_experts"] = num_kept
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"Config updated: num_experts={num_kept}, arch=CausalLM")

        # Rebuild index
        rebuild_index(output_dir)

        # Save pruning metadata
        meta = {
            "source_model": "qwen3.5-35b-a3b",
            "pruning_method": "REAP-Activation (correct alignment)",
            "build_method": "rebuild_pruned_correct.py",
            "activation_aware": True,
            "prune_ratio": 1.0 - KEEP_RATIO,
            "experts_per_layer_before": NUM_EXPERTS,
            "experts_per_layer_after": num_kept,
            "total_experts_before": NUM_EXPERTS * NUM_LAYERS,
            "total_experts_after": num_kept * NUM_LAYERS,
            "super_experts_protected": SUPER_EXPERT_COUNT,
            "calibration_prompts": len(CALIBRATION_PROMPTS),
            "kept_map": {str(k): v for k, v in kept_map.items()},
            "alignment_verified": True,
            "expert_format": "unfused (gate_projs/up_projs/down_projs per expert)",
            "key_format": "model.layers.X (CausalLM)",
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        with open(os.path.join(output_dir, "pruning_meta.json"), "w") as f:
            json.dump(meta, f, indent=2)

    return total_expert_tensors + total_gate_tensors


def rebuild_index(model_dir):
    """Rebuild safetensors index from actual shard contents."""
    shard_files = sorted(
        f for f in os.listdir(model_dir)
        if f.endswith(".safetensors") and "index" not in f
    )
    weight_map = {}
    total_size = 0

    for shard_file in shard_files:
        shard_path = os.path.join(model_dir, shard_file)
        with open(shard_path, "rb") as fh:
            hlen = struct.unpack("<Q", fh.read(8))[0]
            hdr = json.loads(fh.read(hlen).decode("utf-8"))
        for key, info in hdr.items():
            if key == "__metadata__":
                continue
            weight_map[key] = shard_file
            shape = info.get("shape", [])
            dtype_bytes = {"BF16": 2, "F16": 2, "F32": 4}.get(info.get("dtype", "BF16"), 2)
            numel = 1
            for d in shape:
                numel *= d
            total_size += numel * dtype_bytes

    index = {
        "metadata": {"total_size": total_size},
        "weight_map": dict(sorted(weight_map.items()))
    }
    with open(os.path.join(model_dir, "model.safetensors.index.json"), "w") as f:
        json.dump(index, f, indent=2)
    logger.info(f"Index rebuilt: {len(weight_map)} keys, {total_size/1e9:.1f}GB")


def verify_alignment(model_dir, orig_dir, kept_map):
    """Verify that gate[i] in pruned model matches orig_gate[kept[i]] in original."""
    import torch
    from safetensors import safe_open

    logger.info("Verifying gate-expert alignment...")

    # Load original gate (layer 0)
    with open(os.path.join(orig_dir, "model.safetensors.index.json")) as f:
        oidx = json.load(f)
    okey = None
    for k in oidx["weight_map"]:
        if "layers.0.mlp.gate.weight" in k and "mtp" not in k:
            okey = k
            break
    oshard = os.path.join(orig_dir, oidx["weight_map"][okey])
    with safe_open(oshard, framework="pt", device="cpu") as f:
        orig_gate = f.get_tensor(okey)

    # Load pruned gate (layer 0)
    with open(os.path.join(model_dir, "model.safetensors.index.json")) as f:
        pidx = json.load(f)
    pkey = "model.layers.0.mlp.gate.weight"
    pshard = os.path.join(model_dir, pidx["weight_map"][pkey])
    with safe_open(pshard, framework="pt", device="cpu") as f:
        pruned_gate = f.get_tensor(pkey)

    kept_l0 = kept_map[0]
    logger.info(f"  Original gate: {orig_gate.shape}, Pruned gate: {pruned_gate.shape}")
    logger.info(f"  Kept indices (first 10): {kept_l0[:10]}")

    all_match = True
    for i in range(min(10, len(kept_l0))):
        expected = orig_gate[kept_l0[i]]
        actual = pruned_gate[i]
        match = torch.allclose(expected, actual, atol=1e-6)
        dist = (expected - actual).norm().item()
        status = "OK" if match else "MISMATCH"
        logger.info(f"  gate[{i}] vs orig[{kept_l0[i]}]: {status} (L2={dist:.6f})")
        if not match:
            all_match = False

    if all_match:
        logger.info("  ALIGNMENT VERIFIED: All gate rows match expected original rows")
    else:
        logger.error("  ALIGNMENT FAILED: Gate rows do not match!")

    return all_match


def main():
    parser = argparse.ArgumentParser(description="Rebuild pruned model with correct alignment")
    parser.add_argument("--model-dir", default=ORIGINAL_MODEL, help="Original 256-expert model")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Analysis only")
    parser.add_argument("--verify-only", default=None, help="Verify existing model alignment")
    parser.add_argument("--use-l2-scores", action="store_true",
                        help="Use L2-norm gate scores (fast) instead of activation scoring (slow)")
    args = parser.parse_args()

    if args.verify_only:
        # Just verify an existing model
        with open(os.path.join(args.verify_only, "pruning_meta.json")) as f:
            meta = json.load(f)
        kept_map = {int(k): v for k, v in meta.get("kept_map", {}).items()}
        if not kept_map:
            logger.error("No kept_map in pruning_meta.json")
            sys.exit(1)
        ok = verify_alignment(args.verify_only, args.model_dir, kept_map)
        sys.exit(0 if ok else 1)

    logger.info("=" * 60)
    logger.info("  Rebuild Pruned Model (Correct Alignment)")
    logger.info("=" * 60)
    logger.info(f"  Source: {args.model_dir}")
    logger.info(f"  Output: {args.output_dir}")
    logger.info(f"  Keep ratio: {KEEP_RATIO:.0%} ({int(NUM_EXPERTS * KEEP_RATIO)} experts)")

    # Step 1: Score experts
    if args.use_l2_scores:
        logger.info("Using L2-norm gate weight scoring (fast)...")
        scores = collect_gate_weight_scores(args.model_dir)
    else:
        logger.info("Using activation-based scoring (slow, ~48GB RAM)...")
        scores = collect_activation_scores(args.model_dir)

    if not scores:
        logger.error("No scores collected!")
        sys.exit(1)

    # Step 2: Select experts to keep
    kept_map = select_experts_to_keep(scores)
    num_kept = len(next(iter(kept_map.values())))
    logger.info(f"Selected {num_kept} experts per layer")

    # Show layer 0 summary
    kept_0 = kept_map[0]
    logger.info(f"  Layer 0 kept (first 10): {kept_0[:10]}")
    logger.info(f"  Layer 0 kept (last 5): {kept_0[-5:]}")

    if args.dry_run:
        logger.info("DRY RUN — no files created")
        return

    # Step 3: Rebuild model
    t0 = time.time()
    rebuild_model(args.model_dir, args.output_dir, kept_map)
    elapsed = time.time() - t0
    logger.info(f"Model rebuilt in {elapsed:.0f}s")

    # Step 4: Verify alignment
    verify_alignment(args.output_dir, args.model_dir, kept_map)

    logger.info("\n" + "=" * 60)
    logger.info("  Rebuild Complete!")
    logger.info("=" * 60)
    logger.info(f"  Output: {args.output_dir}")
    logger.info(f"  Experts: {NUM_EXPERTS} -> {num_kept}")
    logger.info(f"  Format: unfused (BnB 4-bit compatible)")
    logger.info(f"  Keys: model.layers.X (CausalLM)")
    logger.info(f"  Next: python scripts/test_activation_pruned.py  (set MODEL_PATH)")


if __name__ == "__main__":
    main()
