"""
Reindex pruned experts to contiguous 0-N indices.

PROBLEM: After pruning 256→128 experts, the kept expert indices span the full
0-255 range (e.g., experts 0, 9, 129, 219...). But config says num_experts=128
and the model creates expert modules 0-127. Loading maps by key name, so:
  - Experts with index >= 128: silently LOST (weights in file, no model slot)
  - Expert slots for PRUNED indices < 128: loaded with ZEROED weights

SOLUTION: Renumber kept experts to contiguous 0-127 and rebuild the gate.

Usage:
    python scripts/reindex_experts.py
    python scripts/reindex_experts.py --dry-run
"""
import gc
import json
import logging
import os
import re
import struct
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent

# The ORIGINAL unpruned model (for correct gate weights)
ORIGINAL_MODEL_DIR = PROJECT_ROOT / "models" / "qwen3.5-35b-a3b"
# The pruned+unfused model to fix
PRUNED_MODEL_DIR = PROJECT_ROOT / "models" / "qwen3.5-35b-a3b-v3.5"


def load_original_gate_weights(original_dir: str, num_layers: int = 40) -> dict:
    """Load the original (256, 2048) gate weights from the unpruned model."""
    import torch
    from safetensors import safe_open

    gate_pattern = re.compile(r"layers\.(\d+)\.mlp\.gate\.weight$")
    gates = {}

    shard_files = sorted(Path(original_dir).glob("model*.safetensors"))
    for shard_path in shard_files:
        if "index" in shard_path.name:
            continue
        f = safe_open(str(shard_path), framework="pt")
        for key in f.keys():
            match = gate_pattern.search(key)
            if match:
                layer_idx = int(match.group(1))
                gates[layer_idx] = f.get_tensor(key)  # (256, 2048)

    logger.info(f"Loaded original gate weights for {len(gates)} layers")
    assert len(gates) == num_layers, f"Expected {num_layers} gate weights, got {len(gates)}"
    return gates


def reindex_shard(shard_path: str, layer_kept_map: dict, original_gates: dict,
                  dry_run: bool = False) -> dict:
    """
    Reindex expert weights in a single shard.

    layer_kept_map: {layer_idx: [kept_original_idx_0, kept_original_idx_1, ...]}
                    where the list is sorted (these are the experts to keep, in order)
    """
    import torch
    from safetensors.torch import load_file, save_file

    shard_name = os.path.basename(shard_path)
    tensors = load_file(shard_path, device="cpu")

    # Patterns for unfused expert weights
    expert_pattern = re.compile(
        r"model\.layers\.(\d+)\.mlp\.experts\.(gate_projs|up_projs|down_projs)\.(\d+)\.weight$"
    )
    gate_pattern = re.compile(
        r"model\.layers\.(\d+)\.mlp\.gate\.weight$"
    )

    new_tensors = {}
    reindexed_count = 0
    dropped_count = 0
    gate_fixed_count = 0

    # Build reverse mapping: for each layer, original_idx -> new_contiguous_idx
    reindex_maps = {}
    for layer_idx, kept_list in layer_kept_map.items():
        mapping = {}
        for new_idx, orig_idx in enumerate(sorted(kept_list)):
            mapping[orig_idx] = new_idx
        reindex_maps[layer_idx] = mapping

    for name, tensor in tensors.items():
        # Handle expert weight tensors
        match = expert_pattern.search(name)
        if match:
            layer_idx = int(match.group(1))
            proj_type = match.group(2)  # gate_projs, up_projs, down_projs
            expert_idx = int(match.group(3))

            if layer_idx in reindex_maps:
                mapping = reindex_maps[layer_idx]
                if expert_idx in mapping:
                    new_idx = mapping[expert_idx]
                    new_key = f"model.layers.{layer_idx}.mlp.experts.{proj_type}.{new_idx}.weight"
                    new_tensors[new_key] = tensor
                    reindexed_count += 1
                else:
                    # This expert was pruned — drop it
                    dropped_count += 1
            else:
                # Layer not in prune map (shouldn't happen) — keep as-is
                new_tensors[name] = tensor
            continue

        # Handle gate weight tensors — rebuild from original
        match = gate_pattern.search(name)
        if match:
            layer_idx = int(match.group(1))
            if layer_idx in layer_kept_map and layer_idx in original_gates:
                orig_gate = original_gates[layer_idx]  # (256, 2048)
                kept_indices = sorted(layer_kept_map[layer_idx])
                # Select only the kept rows, in contiguous order
                import torch as _torch
                new_gate = orig_gate[_torch.tensor(kept_indices)]  # (128, 2048)
                new_tensors[name] = new_gate
                gate_fixed_count += 1
                if gate_fixed_count <= 2:
                    logger.info(f"    Gate layer {layer_idx}: ({orig_gate.shape[0]}, {orig_gate.shape[1]}) "
                              f"→ ({new_gate.shape[0]}, {new_gate.shape[1]}) "
                              f"[kept indices: {kept_indices[:5]}...{kept_indices[-3:]}]")
            else:
                new_tensors[name] = tensor
            continue

        # Non-expert tensor — keep as-is
        new_tensors[name] = tensor

    if reindexed_count == 0 and dropped_count == 0 and gate_fixed_count == 0:
        del new_tensors
        gc.collect()
        return {"reindexed": 0, "dropped": 0, "gates_fixed": 0, "shard": shard_name}

    if not dry_run:
        tmp_path = shard_path + ".tmp"
        save_file(new_tensors, tmp_path)
        del new_tensors
        gc.collect()
        os.replace(tmp_path, shard_path)
    else:
        del new_tensors
        gc.collect()

    return {
        "reindexed": reindexed_count,
        "dropped": dropped_count,
        "gates_fixed": gate_fixed_count,
        "shard": shard_name,
    }


def rebuild_index(model_dir: str):
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
    parser = argparse.ArgumentParser(description="Reindex pruned experts to contiguous indices")
    parser.add_argument("--model-dir", default=str(PRUNED_MODEL_DIR))
    parser.add_argument("--original-dir", default=str(ORIGINAL_MODEL_DIR))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    model_dir = args.model_dir
    original_dir = args.original_dir

    # Load pruning metadata
    meta_path = os.path.join(model_dir, "pruning_meta.json")
    if not os.path.exists(meta_path):
        logger.error(f"No pruning_meta.json found in {model_dir}")
        sys.exit(1)

    with open(meta_path) as f:
        meta = json.load(f)

    prune_map = meta["prune_map"]  # layer_idx -> list of KEPT expert indices
    num_kept = meta["total_experts_after"] // len(prune_map)

    logger.info(f"Model: {model_dir}")
    logger.info(f"Original (for gate weights): {original_dir}")
    logger.info(f"Prune map: {len(prune_map)} layers, {num_kept} kept experts/layer")

    # Validate
    for layer_idx, kept in prune_map.items():
        assert len(kept) == num_kept, f"Layer {layer_idx}: expected {num_kept} kept, got {len(kept)}"

    # Build layer_kept_map with int keys
    layer_kept_map = {int(k): v for k, v in prune_map.items()}

    # Check how many experts are currently lost
    total_lost = 0
    for layer_idx, kept in layer_kept_map.items():
        lost = len([e for e in kept if e >= num_kept])
        total_lost += lost
    logger.info(f"Currently LOST experts (index >= {num_kept}): {total_lost} / {len(prune_map) * num_kept} "
                f"({total_lost / (len(prune_map) * num_kept) * 100:.1f}%)")

    if total_lost == 0:
        logger.info("No lost experts — model is already correctly indexed!")
        return

    # Load original gate weights
    logger.info(f"Loading original gate weights from {original_dir}...")
    original_gates = load_original_gate_weights(original_dir)

    # Process each shard
    start = time.time()
    shard_files = sorted(
        f for f in os.listdir(model_dir)
        if f.endswith(".safetensors") and "index" not in f
    )

    total_stats = {"reindexed": 0, "dropped": 0, "gates_fixed": 0}
    for shard_file in shard_files:
        shard_path = os.path.join(model_dir, shard_file)
        logger.info(f"Processing {shard_file}...")
        stats = reindex_shard(shard_path, layer_kept_map, original_gates, dry_run=args.dry_run)
        for k in total_stats:
            total_stats[k] += stats[k]
        if stats["reindexed"] > 0 or stats["dropped"] > 0:
            logger.info(f"  {shard_file}: {stats['reindexed']} reindexed, "
                       f"{stats['dropped']} dropped, {stats['gates_fixed']} gates fixed")
        gc.collect()

    elapsed = time.time() - start
    logger.info(f"\nReindexing complete in {elapsed:.0f}s:")
    logger.info(f"  Expert weights reindexed: {total_stats['reindexed']}")
    logger.info(f"  Pruned experts dropped: {total_stats['dropped']}")
    logger.info(f"  Gate weights rebuilt: {total_stats['gates_fixed']}")

    if not args.dry_run and total_stats["reindexed"] > 0:
        logger.info("Rebuilding safetensors index...")
        rebuild_index(model_dir)

        # Update meta
        meta["reindexed"] = True
        meta["reindexed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        logger.info("Updated pruning_meta.json with reindex info")

    logger.info("Done! Run validate_base.py to verify the model generates coherent code.")


if __name__ == "__main__":
    main()
