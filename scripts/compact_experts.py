"""
Physically remove pruned experts from the model tensors.

The initial pruning (prune_experts.py) ZEROED pruned expert weights and
suppressed their gate rows. The tensors are still full-size (256 experts).
This means the model is still ~17.5GB in 4-bit — too large for 16GB VRAM.

This script REMOVES the dead experts entirely:
  - gate_up_proj: (256, 1024, 2048) → (128, 1024, 2048)
  - down_proj:    (256, 2048, 512)  → (128, 2048, 512)
  - gate.weight:  (256, 2048)       → (128, 2048)
  - config.json:  num_experts: 256  → 128

Result: ~9.5GB in 4-bit → fits in 16GB Unsloth with room to spare.
Zero quality loss — removed experts were already gate-suppressed.

Usage:
    python scripts/compact_experts.py
    python scripts/compact_experts.py --dry-run
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


def load_prune_map(model_dir):
    """Load the pruning map from pruning_meta.json."""
    meta_path = os.path.join(model_dir, "pruning_meta.json")
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"No pruning_meta.json in {model_dir}")
    with open(meta_path) as f:
        meta = json.load(f)
    prune_map = {int(k): set(v) for k, v in meta["prune_map"].items()}
    logger.info(f"Loaded prune map: {len(prune_map)} layers, "
                f"{len(next(iter(prune_map.values())))} pruned per layer")
    return prune_map


def get_surviving_indices(prune_map, num_experts=256):
    """For each layer, compute sorted list of surviving expert indices."""
    surviving = {}
    for layer_idx, pruned_set in prune_map.items():
        surviving[layer_idx] = sorted(set(range(num_experts)) - pruned_set)
    return surviving


def compact_shard(shard_path, surviving_map, dry_run=False):
    """Remove pruned expert rows from tensors in a single shard."""
    import torch
    from safetensors.torch import load_file, save_file

    shard_name = os.path.basename(shard_path)
    logger.info(f"  Loading {shard_name}...")

    tensors = load_file(shard_path, device="cpu")

    # Patterns for expert and gate tensors (post fix_model_keys.py naming)
    expert_pattern = re.compile(r"model\.layers\.(\d+)\.mlp\.experts\.(gate_up_proj|down_proj)$")
    gate_pattern = re.compile(r"model\.layers\.(\d+)\.mlp\.gate\.weight$")

    new_tensors = {}
    compacted = 0

    for name, tensor in tensors.items():
        # Expert fused tensors: slice to surviving experts only
        match = expert_pattern.search(name)
        if match:
            layer_idx = int(match.group(1))
            if layer_idx in surviving_map:
                indices = surviving_map[layer_idx]
                # tensor shape: (256, ...) → (128, ...)
                idx_tensor = torch.tensor(indices, dtype=torch.long)
                new_tensor = tensor.index_select(0, idx_tensor).clone()
                new_tensors[name] = new_tensor
                compacted += 1
                if compacted <= 3:
                    logger.info(f"    {name}: {tuple(tensor.shape)} → {tuple(new_tensor.shape)}")
                continue

        # Gate weights: slice to surviving expert rows
        gate_match = gate_pattern.search(name)
        if gate_match:
            layer_idx = int(gate_match.group(1))
            if layer_idx in surviving_map:
                indices = surviving_map[layer_idx]
                idx_tensor = torch.tensor(indices, dtype=torch.long)
                new_tensor = tensor.index_select(0, idx_tensor).clone()
                new_tensors[name] = new_tensor
                compacted += 1
                if compacted <= 3:
                    logger.info(f"    {name}: {tuple(tensor.shape)} → {tuple(new_tensor.shape)}")
                continue

        # Non-expert tensor: keep as-is (clone to detach from mmap)
        new_tensors[name] = tensor.clone()

    # Release mmap
    del tensors
    gc.collect()

    if not dry_run and compacted > 0:
        tmp_path = shard_path + ".tmp"
        save_file(new_tensors, tmp_path)
        del new_tensors
        gc.collect()
        os.replace(tmp_path, shard_path)
        logger.info(f"    Saved: {compacted} tensors compacted")
    elif not dry_run:
        # No expert tensors in this shard, still need to save (cloned tensors)
        # Actually, if nothing changed, skip the save
        del new_tensors
        gc.collect()
        logger.info(f"    No expert tensors in shard — skipped")
    else:
        del new_tensors
        gc.collect()
        logger.info(f"    [DRY RUN] Would compact {compacted} tensors")

    return compacted


def update_config(model_dir, num_surviving, dry_run=False):
    """Update config.json with new expert count."""
    config_path = os.path.join(model_dir, "config.json")
    with open(config_path) as f:
        config = json.load(f)

    old_experts = config.get("num_experts", 256)
    if old_experts == num_surviving:
        logger.info(f"config.json already has num_experts={num_surviving}")
        return

    if not dry_run:
        config["num_experts"] = num_surviving
        config["_compacted_from"] = old_experts
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"config.json updated: num_experts {old_experts} → {num_surviving}")
    else:
        logger.info(f"[DRY RUN] Would update num_experts: {old_experts} → {num_surviving}")


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
    logger.info(f"Index rebuilt: {len(weight_map)} keys, {total_size/1e9:.1f}GB total")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Physically remove pruned experts")
    parser.add_argument("--model-dir", default=MODEL_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    model_dir = args.model_dir
    logger.info(f"Model: {model_dir}")

    # Check if already compacted
    config_path = os.path.join(model_dir, "config.json")
    with open(config_path) as f:
        config = json.load(f)
    if config.get("num_experts", 256) < 256:
        logger.info(f"Model already compacted (num_experts={config['num_experts']})")
        return

    # Load prune map
    prune_map = load_prune_map(model_dir)
    surviving_map = get_surviving_indices(prune_map)

    num_surviving = len(next(iter(surviving_map.values())))
    logger.info(f"Will compact: 256 → {num_surviving} experts per layer")

    if args.dry_run:
        logger.info("DRY RUN — no files will be modified")

    # Process each shard
    start = time.time()
    shard_files = sorted(
        f for f in os.listdir(model_dir)
        if f.endswith(".safetensors") and "index" not in f
    )

    total_compacted = 0
    for shard_file in shard_files:
        shard_path = os.path.join(model_dir, shard_file)
        c = compact_shard(shard_path, surviving_map, dry_run=args.dry_run)
        total_compacted += c
        gc.collect()

    logger.info(f"\nCompacted {total_compacted} tensors across {len(shard_files)} shards")

    if not args.dry_run:
        update_config(model_dir, num_surviving)
        rebuild_index(model_dir)

        # Update pruning_meta.json
        meta_path = os.path.join(model_dir, "pruning_meta.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            meta["compacted"] = True
            meta["num_experts_after_compact"] = num_surviving
            meta["compacted_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)

    elapsed = time.time() - start
    logger.info(f"Done in {elapsed:.0f}s")
    logger.info(f"Model size should be ~{num_surviving/256*100:.0f}% of original expert params")
    logger.info(f"Estimated 4-bit size: ~{(num_surviving/256 * 16 + 1.5):.1f}GB (fits 16GB VRAM)")


if __name__ == "__main__":
    main()
