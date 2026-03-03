"""
Rebuild pruned model with ACTIVATION-BASED expert selection AND correct alignment.

Combines:
  1. Expert selection from v3.5-activation (activation_proxy scoring)
  2. Correct gate-expert alignment from rebuild_pruned_correct.py

The v3.5-activation model had the RIGHT experts selected but WRONG alignment.
The v3.5-rebuild model had CORRECT alignment but WRONG expert selection (L2-norm).
This script combines the best of both.

Usage:
    python scripts/rebuild_activation_aligned.py
    python scripts/rebuild_activation_aligned.py --dry-run
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGINAL_MODEL = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b")
ACTIVATION_META = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b-v3.5-activation", "pruning_meta.json")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b-v3.5-act-aligned")

NUM_LAYERS = 40
NUM_EXPERTS = 256
NUM_ACTIVE = 8


def get_kept_from_activation_meta(meta_path):
    """
    Read the activation model's prune_map and compute KEPT expert indices.

    prune_map contains experts TO PRUNE (128 per layer).
    KEPT experts = set(range(256)) - prune_map.
    """
    logger.info(f"Reading activation expert selection from {meta_path}")
    meta = json.load(open(meta_path))

    assert meta.get("activation_aware") == True, "Not an activation-based model!"
    prune_map = meta["prune_map"]

    kept_map = {}
    for layer_str, pruned_indices in prune_map.items():
        layer_idx = int(layer_str)
        pruned_set = set(pruned_indices)
        all_experts = set(range(NUM_EXPERTS))
        kept_indices = sorted(all_experts - pruned_set)
        kept_map[layer_idx] = kept_indices

        if layer_idx == 0:
            logger.info(f"  Layer 0: pruned {len(pruned_set)} experts, keeping {len(kept_indices)}")
            logger.info(f"  Kept (first 10): {kept_indices[:10]}")

    logger.info(f"  Total layers: {len(kept_map)}")
    return kept_map


def rebuild_model(model_dir, output_dir, kept_map, dry_run=False):
    """
    Build a new pruned model from the original, with correct gate-expert alignment.
    Reuses rebuild logic from rebuild_pruned_correct.py.
    """
    import torch
    from safetensors.torch import load_file, save_file
    import glob as glob_mod
    import shutil

    os.makedirs(output_dir, exist_ok=True)

    expert_gu_pattern = re.compile(r"(model\.(?:language_model\.)?layers\.(\d+)\.mlp\.experts)\.gate_up_proj$")
    expert_down_pattern = re.compile(r"(model\.(?:language_model\.)?layers\.(\d+)\.mlp\.experts)\.down_proj$")
    gate_pattern = re.compile(r"(model\.(?:language_model\.)?layers\.(\d+)\.mlp)\.gate\.weight$")

    shard_files = sorted(glob_mod.glob(os.path.join(model_dir, "model*.safetensors")))
    if not shard_files:
        raise FileNotFoundError(f"No safetensors in {model_dir}")

    num_kept = len(next(iter(kept_map.values())))
    total_expert_tensors = 0
    total_gate_tensors = 0

    for shard_path in shard_files:
        shard_name = os.path.basename(shard_path)
        logger.info(f"Processing {shard_name}...")

        tensors = load_file(shard_path, device="cpu")
        new_tensors = {}

        for name, tensor in tensors.items():
            # gate_up_proj: (256, 2*intermediate, hidden) -> N x gate + N x up
            match = expert_gu_pattern.search(name)
            if match:
                layer_idx = int(match.group(2))
                kept_indices = kept_map.get(layer_idx)
                if kept_indices is None:
                    new_tensors[name] = tensor.clone()
                    continue

                intermediate = tensor.shape[1] // 2
                base = f"model.layers.{layer_idx}.mlp.experts"

                for new_idx, orig_idx in enumerate(kept_indices):
                    expert_slice = tensor[orig_idx]
                    gate_w = expert_slice[:intermediate].clone()
                    up_w = expert_slice[intermediate:].clone()
                    new_tensors[f"{base}.gate_projs.{new_idx}.weight"] = gate_w
                    new_tensors[f"{base}.up_projs.{new_idx}.weight"] = up_w

                total_expert_tensors += 1
                if total_expert_tensors <= 2:
                    logger.info(f"  {name}: ({tensor.shape[0]}, ...) -> {num_kept} x gate + up")
                continue

            # down_proj: (256, hidden, intermediate) -> N x down
            match = expert_down_pattern.search(name)
            if match:
                layer_idx = int(match.group(2))
                kept_indices = kept_map.get(layer_idx)
                if kept_indices is None:
                    new_tensors[name] = tensor.clone()
                    continue

                base = f"model.layers.{layer_idx}.mlp.experts"
                for new_idx, orig_idx in enumerate(kept_indices):
                    down_w = tensor[orig_idx].clone()
                    new_tensors[f"{base}.down_projs.{new_idx}.weight"] = down_w

                total_expert_tensors += 1
                if total_expert_tensors <= 2:
                    logger.info(f"  {name}: ({tensor.shape[0]}, ...) -> {num_kept} x down")
                continue

            # gate.weight: (256, 2048) -> (128, 2048)
            match = gate_pattern.search(name)
            if match:
                layer_idx = int(match.group(2))
                kept_indices = kept_map.get(layer_idx)
                if kept_indices is None:
                    new_tensors[name] = tensor.clone()
                    continue

                idx_tensor = torch.tensor(kept_indices, dtype=torch.long)
                new_gate = tensor.index_select(0, idx_tensor).clone()
                new_name = f"model.layers.{layer_idx}.mlp.gate.weight"
                new_tensors[new_name] = new_gate
                total_gate_tensors += 1
                if total_gate_tensors <= 2:
                    logger.info(f"  {name}: ({tensor.shape[0]}, 2048) -> ({num_kept}, 2048)")
                continue

            # Non-expert: rename to CausalLM format
            new_name = name.replace("model.language_model.", "model.")
            if "visual" in new_name or "image" in new_name:
                continue
            new_tensors[new_name] = tensor.clone()

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
        # Copy config files
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
        logger.info(f"Config updated: num_experts={num_kept}")

        # Rebuild index
        rebuild_index(output_dir)

        # Save pruning metadata
        meta = {
            "source_model": "qwen3.5-35b-a3b",
            "pruning_method": "REAP-Activation (correct alignment)",
            "build_method": "rebuild_activation_aligned.py",
            "activation_aware": True,
            "activation_source": "v3.5-activation/pruning_meta.json",
            "prune_ratio": 0.5,
            "experts_per_layer_before": NUM_EXPERTS,
            "experts_per_layer_after": num_kept,
            "total_experts_before": NUM_EXPERTS * NUM_LAYERS,
            "total_experts_after": num_kept * NUM_LAYERS,
            "kept_map": {str(k): v for k, v in kept_map.items()},
            "alignment_verified": False,  # Will be set to True after verify
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
    """Verify gate[i] in pruned model matches orig_gate[kept[i]] in original."""
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
    all_match = True
    for i in range(min(10, len(kept_l0))):
        orig_row = orig_gate[kept_l0[i]]
        pruned_row = pruned_gate[i]
        dist = torch.dist(orig_row.float(), pruned_row.float()).item()
        status = "OK" if dist < 1e-5 else "MISMATCH"
        if i < 5:
            logger.info(f"  gate[{i}] vs orig_gate[{kept_l0[i]}]: L2_dist={dist:.6f} [{status}]")
        if dist >= 1e-5:
            all_match = False

    if all_match:
        logger.info("  ALIGNMENT VERIFIED: All checked gate rows match expected originals")
        # Update meta
        meta_path = os.path.join(model_dir, "pruning_meta.json")
        if os.path.exists(meta_path):
            meta = json.load(open(meta_path))
            meta["alignment_verified"] = True
            json.dump(meta, open(meta_path, "w"), indent=2)
    else:
        logger.error("  ALIGNMENT FAILED: Gate-expert mismatch detected!")

    return all_match


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", default=ORIGINAL_MODEL)
    parser.add_argument("--activation-meta", default=ACTIVATION_META)
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    # Get kept expert indices from activation model
    kept_map = get_kept_from_activation_meta(args.activation_meta)

    if args.verify_only:
        verify_alignment(args.output_dir, args.model_dir, kept_map)
        return

    # Build the model
    logger.info(f"\nRebuilding with activation-based expert selection...")
    logger.info(f"  Source: {args.model_dir}")
    logger.info(f"  Activation meta: {args.activation_meta}")
    logger.info(f"  Output: {args.output_dir}")

    t0 = time.time()
    count = rebuild_model(args.model_dir, args.output_dir, kept_map, dry_run=args.dry_run)
    elapsed = time.time() - t0
    logger.info(f"\nBuild complete in {elapsed:.0f}s ({count} tensors processed)")

    if not args.dry_run:
        # Verify alignment
        verify_alignment(args.output_dir, args.model_dir, kept_map)


if __name__ == "__main__":
    main()
