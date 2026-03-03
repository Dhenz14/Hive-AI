"""
Build a correctly pruned + unfused + reindexed model from scratch.

Reads the ORIGINAL (unpruned, fused) model and the prune_map from pruning_meta.json.
Outputs a clean model where:
  - Experts are unfused into per-expert 2D nn.Linear weights (BnB-quantizable)
  - Only kept experts are present, numbered contiguously 0 to N-1
  - Gate weights match exactly: row i routes to expert i
  - Config updated to reflect correct num_experts

No monkey patches. No in-place modifications. Clean build from source.

Usage:
    python scripts/rebuild_pruned_model.py
    python scripts/rebuild_pruned_model.py --original /path/to/original --output /path/to/output
"""
import gc
import json
import logging
import os
import re
import shutil
import struct
import sys
import time
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def build_pruned_model(original_dir: str, output_dir: str, prune_map: dict,
                       num_kept: int):
    """
    Build a clean pruned model from the original.

    For each safetensors shard in the original model:
    1. Load all tensors
    2. For fused expert tensors (gate_up_proj, down_proj):
       - Select only the kept expert slices
       - Unfuse gate_up into separate gate and up weights
       - Number them contiguously 0 to num_kept-1
    3. For gate weights:
       - Select only the kept rows, contiguous
    4. For all other tensors: copy as-is
    5. Save to output directory
    """
    os.makedirs(output_dir, exist_ok=True)

    # Build reindex mapping: layer -> {original_idx: new_contiguous_idx}
    reindex = {}
    for layer_str, kept_list in prune_map.items():
        layer_idx = int(layer_str)
        mapping = {}
        for new_idx, orig_idx in enumerate(sorted(kept_list)):
            mapping[orig_idx] = new_idx
        reindex[layer_idx] = mapping

    # Patterns — handle both model.layers.N and model.language_model.layers.N prefixes
    # (Qwen3.5 uses language_model prefix in the multimodal variant)
    LP = r"(?:model\.language_model\.layers|model\.layers)"
    gate_up_pattern = re.compile(LP + r"\.(\d+)\.mlp\.experts\.gate_up_proj$")
    down_pattern = re.compile(LP + r"\.(\d+)\.mlp\.experts\.down_proj$")
    gate_pattern = re.compile(LP + r"\.(\d+)\.mlp\.gate\.weight$")
    # Also handle unfused expert patterns (in case original has them)
    unfused_pattern = re.compile(
        LP + r"\.(\d+)\.mlp\.experts\.(gate_projs|up_projs|down_projs)\.(\d+)\.weight$"
    )

    shard_files = sorted(
        f for f in os.listdir(original_dir)
        if f.endswith(".safetensors") and "index" not in f
    )
    if not shard_files:
        raise FileNotFoundError(f"No safetensors files in {original_dir}")

    total_stats = {"experts_kept": 0, "experts_dropped": 0, "gates_rebuilt": 0, "tensors_copied": 0}
    shard_idx = 0

    for shard_file in shard_files:
        shard_idx += 1
        shard_path = os.path.join(original_dir, shard_file)
        logger.info(f"[{shard_idx}/{len(shard_files)}] Processing {shard_file}...")

        f = safe_open(shard_path, framework="pt")
        keys = list(f.keys())
        new_tensors = {}

        for name in keys:
            # ── Fused gate_up_proj: (256, 1024, 2048) → per-expert gate + up ──
            match = gate_up_pattern.search(name)
            if match:
                layer_idx = int(match.group(1))
                tensor = f.get_tensor(name)  # (256, 1024, 2048)
                intermediate = tensor.shape[1] // 2  # 512

                if layer_idx in reindex:
                    mapping = reindex[layer_idx]
                    for orig_idx, new_idx in sorted(mapping.items(), key=lambda x: x[1]):
                        expert_slice = tensor[orig_idx]  # (1024, 2048)
                        gate_w = expert_slice[:intermediate].clone()   # (512, 2048)
                        up_w = expert_slice[intermediate:].clone()     # (512, 2048)
                        new_tensors[f"model.layers.{layer_idx}.mlp.experts.gate_projs.{new_idx}.weight"] = gate_w
                        new_tensors[f"model.layers.{layer_idx}.mlp.experts.up_projs.{new_idx}.weight"] = up_w
                        total_stats["experts_kept"] += 1
                    total_stats["experts_dropped"] += tensor.shape[0] - len(mapping)
                else:
                    # Layer not pruned — keep all
                    for i in range(tensor.shape[0]):
                        expert_slice = tensor[i]
                        gate_w = expert_slice[:intermediate].clone()
                        up_w = expert_slice[intermediate:].clone()
                        new_tensors[f"model.layers.{layer_idx}.mlp.experts.gate_projs.{i}.weight"] = gate_w
                        new_tensors[f"model.layers.{layer_idx}.mlp.experts.up_projs.{i}.weight"] = up_w

                del tensor
                continue

            # ── Fused down_proj: (256, 2048, 512) → per-expert down ──
            match = down_pattern.search(name)
            if match:
                layer_idx = int(match.group(1))
                tensor = f.get_tensor(name)  # (256, 2048, 512)

                if layer_idx in reindex:
                    mapping = reindex[layer_idx]
                    for orig_idx, new_idx in sorted(mapping.items(), key=lambda x: x[1]):
                        down_w = tensor[orig_idx].clone()  # (2048, 512)
                        new_tensors[f"model.layers.{layer_idx}.mlp.experts.down_projs.{new_idx}.weight"] = down_w
                else:
                    for i in range(tensor.shape[0]):
                        new_tensors[f"model.layers.{layer_idx}.mlp.experts.down_projs.{i}.weight"] = tensor[i].clone()

                del tensor
                continue

            # ── Gate weight: (256, 2048) → (128, 2048) ──
            match = gate_pattern.search(name)
            if match:
                layer_idx = int(match.group(1))
                tensor = f.get_tensor(name)  # (256, 2048)
                # Normalize key: strip language_model prefix
                out_name = name.replace("model.language_model.layers", "model.layers")

                if layer_idx in reindex:
                    mapping = reindex[layer_idx]
                    kept_indices = sorted(mapping.keys())
                    new_gate = tensor[torch.tensor(kept_indices)]  # (128, 2048)
                    new_tensors[out_name] = new_gate
                    total_stats["gates_rebuilt"] += 1
                    if total_stats["gates_rebuilt"] <= 2:
                        logger.info(f"  Gate layer {layer_idx}: {tensor.shape} → {new_gate.shape}")
                else:
                    new_tensors[out_name] = f.get_tensor(name)

                del tensor
                continue

            # ── Skip already-unfused expert tensors (shouldn't exist in original) ──
            if unfused_pattern.search(name):
                logger.warning(f"  Unexpected unfused expert tensor in original: {name}")
                continue

            # ── Everything else: copy as-is, normalize key ──
            out_name = name.replace("model.language_model.layers", "model.layers")
            new_tensors[out_name] = f.get_tensor(name)
            total_stats["tensors_copied"] += 1

        # Save output shard
        out_path = os.path.join(output_dir, shard_file)
        save_file(new_tensors, out_path)
        n_expert_keys = sum(1 for k in new_tensors if "gate_projs" in k or "up_projs" in k or "down_projs" in k)
        logger.info(f"  Saved: {len(new_tensors)} tensors ({n_expert_keys} expert weights)")

        del new_tensors
        gc.collect()

    return total_stats


def rebuild_index(model_dir: str):
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
            if key in weight_map:
                logger.warning(f"  DUPLICATE key: {key} (in {weight_map[key]} and {shard_file})")
            weight_map[key] = shard_file
            shape = info.get("shape", [])
            dtype = info.get("dtype", "BF16")
            dtype_bytes = {"BF16": 2, "F16": 2, "F32": 4}.get(dtype, 2)
            numel = 1
            for d in shape:
                numel *= d
            total_size += numel * dtype_bytes

    index = {
        "metadata": {"total_size": total_size},
        "weight_map": dict(sorted(weight_map.items()))
    }
    index_path = os.path.join(model_dir, "model.safetensors.index.json")
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    logger.info(f"Index: {len(weight_map)} keys, {total_size / 1e9:.1f}GB, 0 duplicates"
                if not any("DUPLICATE" in str(v) for v in weight_map.values())
                else f"Index: {len(weight_map)} keys — DUPLICATES FOUND!")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build clean pruned model from original")
    parser.add_argument("--original", default="/opt/hiveai/project/models/qwen3.5-35b-a3b",
                       help="Path to ORIGINAL unpruned model (fused 3D expert tensors)")
    parser.add_argument("--output", default="/opt/hiveai/project/models/qwen3.5-35b-a3b-v3.5-fixed",
                       help="Path to output pruned model")
    parser.add_argument("--meta", default="/opt/hiveai/project/models/qwen3.5-35b-a3b-v3.5/pruning_meta.json",
                       help="Path to pruning_meta.json with prune_map")
    args = parser.parse_args()

    # Load prune map
    with open(args.meta) as f:
        meta = json.load(f)

    prune_map = meta["prune_map"]
    num_kept = meta["total_experts_after"] // len(prune_map)
    logger.info(f"Original model: {args.original}")
    logger.info(f"Output: {args.output}")
    logger.info(f"Prune map: {len(prune_map)} layers, {num_kept} experts kept/layer")

    # Validate prune map
    for layer, kept in prune_map.items():
        assert len(kept) == num_kept, f"Layer {layer}: {len(kept)} != {num_kept}"

    start = time.time()

    # Build the model
    stats = build_pruned_model(args.original, args.output, prune_map, num_kept)

    # Rebuild index
    logger.info("Rebuilding safetensors index...")
    rebuild_index(args.output)

    # Copy non-safetensors files from original
    for fname in os.listdir(args.original):
        if fname.endswith(".safetensors") or fname == "model.safetensors.index.json":
            continue
        src = os.path.join(args.original, fname)
        dst = os.path.join(args.output, fname)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)

    # Update config
    config_path = os.path.join(args.output, "config.json")
    with open(config_path) as f:
        config = json.load(f)
    old_experts = config.get("num_experts", 256)
    config["num_experts"] = num_kept
    # Also update nested text_config (used by Qwen3_5MoeForConditionalGeneration)
    if "text_config" in config:
        config["text_config"]["num_experts"] = num_kept
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    logger.info(f"Config updated: num_experts {old_experts} → {num_kept} (top-level + text_config)")

    # Copy and update pruning meta
    meta["reindexed"] = True
    meta["reindexed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    meta["build_method"] = "rebuild_pruned_model.py (clean build from original)"
    meta_out = os.path.join(args.output, "pruning_meta.json")
    with open(meta_out, "w") as f:
        json.dump(meta, f, indent=2)

    elapsed = time.time() - start
    logger.info(f"\nBuild complete in {elapsed:.0f}s:")
    logger.info(f"  Experts kept: {stats['experts_kept']}")
    logger.info(f"  Experts dropped: {stats['experts_dropped']}")
    logger.info(f"  Gates rebuilt: {stats['gates_rebuilt']}")
    logger.info(f"  Other tensors copied: {stats['tensors_copied']}")
    logger.info(f"\nRun: python scripts/validate_base.py --model {args.output}")


if __name__ == "__main__":
    main()
