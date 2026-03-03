"""
Unfuse 3D expert tensors into individual 2D nn.Linear-compatible weights.

BitsAndBytes load_in_4bit only quantizes nn.Linear (2D weight matrices).
Qwen3.5 MoE stores experts as fused 3D nn.Parameter tensors:
    gate_up_proj: (128, 1024, 2048)   - NOT quantized by BnB
    down_proj:    (128, 2048, 512)    - NOT quantized by BnB

This means the model stays ~35GB even with "4-bit" — too large for 16GB VRAM.

This script UNFUSES them into individual 2D tensors:
    gate_projs.{i}.weight: (512, 2048)   - quantizable by BnB
    up_projs.{i}.weight:   (512, 2048)   - quantizable by BnB
    down_projs.{i}.weight: (2048, 512)   - quantizable by BnB

After unfusing + monkey-patching the model class:
    True 4-bit size: ~9GB → fits in 16GB VRAM → Unsloth works.

Naming convention: experts.gate_projs.{i}.weight (not experts.{i}.gate_proj.weight)
    This avoids collision with transformers' qwen2_moe conversion_mapping which
    would re-fuse experts.*.gate_proj.weight back into a 3D tensor.

Usage:
    python scripts/unfuse_experts.py
    python scripts/unfuse_experts.py --dry-run
"""
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
MODEL_DIR = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b-pruned")


def unfuse_shard(shard_path, dry_run=False):
    """Unfuse 3D expert tensors in a single shard into per-expert 2D tensors."""
    import torch
    from safetensors.torch import load_file, save_file

    shard_name = os.path.basename(shard_path)
    logger.info(f"  Loading {shard_name}...")

    tensors = load_file(shard_path, device="cpu")

    # Patterns for fused expert tensors
    gate_up_pattern = re.compile(
        r"model\.layers\.(\d+)\.mlp\.experts\.gate_up_proj$"
    )
    down_pattern = re.compile(
        r"model\.layers\.(\d+)\.mlp\.experts\.down_proj$"
    )

    new_tensors = {}
    unfused_count = 0

    for name, tensor in tensors.items():
        # Unfuse gate_up_proj: (N, 2*intermediate, hidden) → N × gate + N × up
        match = gate_up_pattern.search(name)
        if match:
            layer_idx = match.group(1)
            num_experts = tensor.shape[0]
            intermediate = tensor.shape[1] // 2  # 1024 / 2 = 512

            for i in range(num_experts):
                expert_slice = tensor[i]  # (1024, 2048)
                gate_w = expert_slice[:intermediate].clone()   # (512, 2048)
                up_w = expert_slice[intermediate:].clone()     # (512, 2048)
                new_tensors[f"model.layers.{layer_idx}.mlp.experts.gate_projs.{i}.weight"] = gate_w
                new_tensors[f"model.layers.{layer_idx}.mlp.experts.up_projs.{i}.weight"] = up_w

            unfused_count += 1
            if unfused_count <= 2:
                logger.info(
                    f"    {name}: ({num_experts}, {tensor.shape[1]}, {tensor.shape[2]}) "
                    f"→ {num_experts} × gate({intermediate}, {tensor.shape[2]}) "
                    f"+ {num_experts} × up({intermediate}, {tensor.shape[2]})"
                )
            continue

        # Unfuse down_proj: (N, hidden, intermediate) → N × down
        match = down_pattern.search(name)
        if match:
            layer_idx = match.group(1)
            num_experts = tensor.shape[0]

            for i in range(num_experts):
                down_w = tensor[i].clone()  # (2048, 512)
                new_tensors[f"model.layers.{layer_idx}.mlp.experts.down_projs.{i}.weight"] = down_w

            unfused_count += 1
            if unfused_count <= 2:
                logger.info(
                    f"    {name}: ({num_experts}, {tensor.shape[1]}, {tensor.shape[2]}) "
                    f"→ {num_experts} × down({tensor.shape[1]}, {tensor.shape[2]})"
                )
            continue

        # Non-expert tensor: keep as-is (clone to detach from mmap)
        new_tensors[name] = tensor.clone()

    # Release mmap
    del tensors
    gc.collect()

    if unfused_count == 0:
        del new_tensors
        gc.collect()
        logger.info(f"    No fused expert tensors — skipped")
        return 0

    if not dry_run:
        tmp_path = shard_path + ".tmp"
        save_file(new_tensors, tmp_path)
        del new_tensors
        gc.collect()
        os.replace(tmp_path, shard_path)
        logger.info(f"    Saved: {unfused_count} fused tensors → {unfused_count * 128 * 3 // 2 if unfused_count % 2 == 0 else '?'} individual tensors")
    else:
        num_new = sum(1 for k in new_tensors if 'gate_projs' in k or 'up_projs' in k or 'down_projs' in k)
        del new_tensors
        gc.collect()
        logger.info(f"    [DRY RUN] Would unfuse {unfused_count} fused tensors → {num_new} individual tensors")

    return unfused_count


def rebuild_index(model_dir):
    """Rebuild safetensors index from actual shard contents."""
    index_path = os.path.join(model_dir, "model.safetensors.index.json")
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
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    logger.info(f"Index rebuilt: {len(weight_map)} keys, {total_size / 1e9:.1f}GB total")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Unfuse 3D expert tensors for BitsAndBytes quantization")
    parser.add_argument("--model-dir", default=MODEL_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    model_dir = args.model_dir
    logger.info(f"Model: {model_dir}")

    # Check if already unfused
    index_path = os.path.join(model_dir, "model.safetensors.index.json")
    if os.path.exists(index_path):
        with open(index_path) as f:
            idx = json.load(f)
        if any("gate_projs" in k for k in idx["weight_map"]):
            logger.info("Model already unfused (found gate_projs keys) — nothing to do")
            return

    # Check that model is compacted
    config_path = os.path.join(model_dir, "config.json")
    with open(config_path) as f:
        config = json.load(f)
    num_experts = config.get("num_experts", 256)
    logger.info(f"num_experts: {num_experts}")

    if args.dry_run:
        logger.info("DRY RUN — no files will be modified")

    # Process each shard
    start = time.time()
    shard_files = sorted(
        f for f in os.listdir(model_dir)
        if f.endswith(".safetensors") and "index" not in f
    )

    total_unfused = 0
    for shard_file in shard_files:
        shard_path = os.path.join(model_dir, shard_file)
        c = unfuse_shard(shard_path, dry_run=args.dry_run)
        total_unfused += c
        gc.collect()

    logger.info(f"\nUnfused {total_unfused} tensors across {len(shard_files)} shards")

    if not args.dry_run and total_unfused > 0:
        rebuild_index(model_dir)

        # Update meta
        meta_path = os.path.join(model_dir, "pruning_meta.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            meta["unfused"] = True
            meta["unfused_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)

    elapsed = time.time() - start
    logger.info(f"Done in {elapsed:.0f}s")
    expected_keys = num_experts * 3 * config.get("num_hidden_layers", 40)
    logger.info(f"Expected ~{expected_keys} individual expert tensors (each 2D, quantizable by BnB)")
    logger.info(f"Estimated true 4-bit size: ~{num_experts / 256 * 9 + 1:.0f}GB")


if __name__ == "__main__":
    main()
