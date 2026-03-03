"""
Repair missing expert tensors in the pruned Qwen3.5-35B-A3B model.

Layers 12, 18, 29, 30, 31 are missing gate_projs and up_projs tensors.
These were lost when shard 6 became a duplicate of shard 1 during the
compact/unfuse pipeline.

This script:
1. Downloads original shard 5 from HuggingFace (contains all 5 layers)
2. Extracts gate_up_proj for the missing layers
3. Fixes key naming (VL → CausalLM)
4. Compacts from 256 → 128 experts using prune_map
5. Unfuses into individual gate_projs + up_projs
6. Injects into shard 6 (replacing the duplicate data)
7. Rebuilds the safetensors index

Usage:
    python scripts/repair_missing_experts.py
"""
import gc
import json
import logging
import os
import struct
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b-pruned")
MISSING_LAYERS = [12, 18, 29, 30, 31]
ORIGINAL_SHARD = "model.safetensors-00005-of-00014.safetensors"
TARGET_SHARD = "model.safetensors-00006-of-00014.safetensors"


def download_original_shard():
    """Download the original shard 5 from HuggingFace."""
    from huggingface_hub import hf_hub_download

    logger.info(f"Downloading {ORIGINAL_SHARD} from unsloth/Qwen3.5-35B-A3B...")
    path = hf_hub_download(
        repo_id="unsloth/Qwen3.5-35B-A3B",
        filename=ORIGINAL_SHARD,
        cache_dir=os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b", ".cache"),
    )
    logger.info(f"Downloaded to: {path}")
    return path


def load_prune_map():
    """Load the pruning map for the missing layers."""
    meta_path = os.path.join(MODEL_DIR, "pruning_meta.json")
    with open(meta_path) as f:
        meta = json.load(f)
    prune_map = {int(k): set(v) for k, v in meta["prune_map"].items()}
    return prune_map


def repair():
    """Main repair flow."""
    import torch
    from safetensors.torch import load_file, save_file

    start = time.time()

    # Step 1: Download original shard
    shard_path = download_original_shard()
    logger.info(f"Loading original shard...")
    original_tensors = load_file(shard_path, device="cpu")

    # Step 2: Extract gate_up_proj for missing layers
    logger.info(f"Extracting gate_up_proj for layers {MISSING_LAYERS}...")
    prune_map = load_prune_map()
    num_experts_orig = 256

    new_expert_tensors = {}
    for layer_idx in MISSING_LAYERS:
        # Original key uses VL naming
        vl_key = f"model.language_model.layers.{layer_idx}.mlp.experts.gate_up_proj"
        if vl_key not in original_tensors:
            # Try without language_model prefix
            vl_key = f"model.layers.{layer_idx}.mlp.experts.gate_up_proj"
        if vl_key not in original_tensors:
            logger.error(f"  Key not found: {vl_key}")
            logger.error(f"  Available keys with layer {layer_idx}:")
            for k in original_tensors:
                if f"layers.{layer_idx}" in k:
                    logger.error(f"    {k}: {original_tensors[k].shape}")
            sys.exit(1)

        tensor = original_tensors[vl_key]
        logger.info(f"  Layer {layer_idx}: gate_up_proj shape = {tuple(tensor.shape)}")

        # Step 3: Compact from 256 → 128 using prune_map
        pruned_set = prune_map[layer_idx]
        surviving = sorted(set(range(num_experts_orig)) - pruned_set)
        idx_tensor = torch.tensor(surviving, dtype=torch.long)
        compacted = tensor.index_select(0, idx_tensor).clone()
        logger.info(f"    Compacted: {tuple(tensor.shape)} → {tuple(compacted.shape)}")

        # Step 4: Unfuse into gate_projs + up_projs
        num_experts = compacted.shape[0]  # 128
        intermediate = compacted.shape[1] // 2  # 512

        for i in range(num_experts):
            expert_slice = compacted[i]  # (1024, 2048)
            gate_w = expert_slice[:intermediate].clone()   # (512, 2048)
            up_w = expert_slice[intermediate:].clone()     # (512, 2048)
            new_expert_tensors[f"model.layers.{layer_idx}.mlp.experts.gate_projs.{i}.weight"] = gate_w
            new_expert_tensors[f"model.layers.{layer_idx}.mlp.experts.up_projs.{i}.weight"] = up_w

        logger.info(f"    Unfused: {num_experts} × gate({intermediate}, {compacted.shape[2]}) "
                     f"+ {num_experts} × up({intermediate}, {compacted.shape[2]})")

    del original_tensors
    gc.collect()

    logger.info(f"\nGenerated {len(new_expert_tensors)} new expert tensors")

    # Step 5: Load target shard 6 and replace duplicate content
    target_path = os.path.join(MODEL_DIR, TARGET_SHARD)
    logger.info(f"Loading target shard {TARGET_SHARD}...")
    target_tensors = load_file(target_path, device="cpu")

    # Remove duplicate keys (layers 0, 14, 15, 19, 26 which are already in shard 1)
    duplicate_layers = {0, 14, 15, 19, 26}
    keys_to_remove = []
    for k in target_tensors:
        for dl in duplicate_layers:
            if f"layers.{dl}." in k:
                keys_to_remove.append(k)
                break

    for k in keys_to_remove:
        del target_tensors[k]
    logger.info(f"  Removed {len(keys_to_remove)} duplicate keys from shard 6")

    # Add new expert tensors
    target_tensors.update(new_expert_tensors)
    logger.info(f"  Added {len(new_expert_tensors)} new expert tensors")
    logger.info(f"  Shard 6 now has {len(target_tensors)} keys")

    # Save
    tmp_path = target_path + ".tmp"
    save_file(target_tensors, tmp_path)
    del target_tensors, new_expert_tensors
    gc.collect()
    os.replace(tmp_path, target_path)
    logger.info(f"  Saved {TARGET_SHARD}")

    # Step 6: Rebuild index
    rebuild_index(MODEL_DIR)

    # Step 7: Verify
    verify(MODEL_DIR)

    elapsed = time.time() - start
    logger.info(f"\nRepair complete in {elapsed:.0f}s")


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


def verify(model_dir):
    """Verify all 40 layers have complete expert tensors."""
    index_path = os.path.join(model_dir, "model.safetensors.index.json")
    with open(index_path) as f:
        idx = json.load(f)

    wm = idx["weight_map"]
    all_ok = True
    for layer in range(40):
        gate = sum(1 for k in wm if f"layers.{layer}.mlp.experts.gate_projs" in k)
        up = sum(1 for k in wm if f"layers.{layer}.mlp.experts.up_projs" in k)
        down = sum(1 for k in wm if f"layers.{layer}.mlp.experts.down_projs" in k)
        if gate != 128 or up != 128 or down != 128:
            logger.error(f"  Layer {layer}: gate={gate}, up={up}, down={down} ← STILL BROKEN")
            all_ok = False

    total_gate = sum(1 for k in wm if "gate_projs" in k)
    total_up = sum(1 for k in wm if "up_projs" in k)
    total_down = sum(1 for k in wm if "down_projs" in k)
    logger.info(f"Expert tensor counts: gate={total_gate}, up={total_up}, down={total_down}")
    logger.info(f"Expected: 5120 each (128 × 40)")

    if all_ok:
        logger.info("✓ All 40 layers verified complete!")
    else:
        logger.error("✗ Verification FAILED — some layers still incomplete")
        sys.exit(1)


if __name__ == "__main__":
    repair()
