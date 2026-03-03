"""
Fix missing gate_up_proj tensors by extracting them from the official Qwen repo shard.

The unsloth-downloaded model has scrambled shards: 5 gate_up_proj tensors
(layers 12, 18, 29, 30, 31) are missing from all files. This script:
1. Reads the official Qwen shard 5 (downloaded separately)
2. Extracts ONLY the missing gate_up_proj tensors
3. Saves them as an extra shard in the model directory
4. Rebuilds the index from actual file contents

Usage:
    python scripts/fix_missing_shards.py
"""
import json
import os
import struct
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    from safetensors import safe_open
    from safetensors.torch import save_file

    model_dir = "/opt/hiveai/project/models/qwen3.5-35b-a3b"
    official_shard = "/opt/hiveai/project/models/qwen3.5-official-shard5-temp/model.safetensors-00005-of-00014.safetensors"

    if not os.path.exists(official_shard):
        logger.error(f"Official shard not found: {official_shard}")
        sys.exit(1)

    # First, inventory what we're missing
    missing_layers = {12, 18, 29, 30, 31}
    logger.info(f"Looking for gate_up_proj for layers: {sorted(missing_layers)}")

    # Read the official shard
    f = safe_open(official_shard, framework="pt")
    official_keys = list(f.keys())
    logger.info(f"Official shard 5 has {len(official_keys)} keys:")
    for k in sorted(official_keys):
        logger.info(f"  {k}")

    # Extract only the missing gate_up_proj tensors
    extracted = {}
    for key in official_keys:
        if "gate_up_proj" in key:
            import re
            m = re.search(r"layers\.(\d+)\.", key)
            if m and int(m.group(1)) in missing_layers:
                tensor = f.get_tensor(key)
                extracted[key] = tensor
                logger.info(f"  EXTRACTED: {key} shape={list(tensor.shape)}")

    if not extracted:
        logger.error("No missing gate_up_proj tensors found in official shard!")
        # Show what IS there
        for key in official_keys:
            if "gate_up_proj" in key:
                logger.info(f"  Available: {key}")
        sys.exit(1)

    if len(extracted) != len(missing_layers):
        logger.warning(f"Expected {len(missing_layers)} tensors, got {len(extracted)}")

    # Save as extra shard
    extra_shard_path = os.path.join(model_dir, "model.safetensors-00005-extra.safetensors")
    save_file(extracted, extra_shard_path)
    logger.info(f"Saved {len(extracted)} tensors to {extra_shard_path}")

    # Verify: count gate_up_proj across all shards now
    import glob
    shard_files = sorted(glob.glob(os.path.join(model_dir, "model*.safetensors")))
    shard_files = [f for f in shard_files if "index" not in f]

    found_layers = set()
    for sf in shard_files:
        fh = safe_open(sf, framework="pt")
        for key in fh.keys():
            if "gate_up_proj" in key:
                import re
                m = re.search(r"layers\.(\d+)\.", key)
                if m:
                    found_layers.add(int(m.group(1)))

    missing_after = set(range(40)) - found_layers
    logger.info(f"\nAfter fix: {len(found_layers)}/40 layers have gate_up_proj")
    if missing_after:
        logger.error(f"Still missing: {sorted(missing_after)}")
    else:
        logger.info("ALL 40 layers now have gate_up_proj!")

    # Rebuild index from actual contents
    logger.info("\nRebuilding index from actual shard contents...")
    weight_map = {}
    total_size = 0
    for sf in shard_files:
        shard_name = os.path.basename(sf)
        with open(sf, "rb") as fh:
            hlen = struct.unpack("<Q", fh.read(8))[0]
            hdr = json.loads(fh.read(hlen).decode("utf-8"))
        for key, info in hdr.items():
            if key == "__metadata__":
                continue
            if key in weight_map:
                logger.warning(f"  DUPLICATE: {key} in {weight_map[key]} and {shard_name}")
            weight_map[key] = shard_name
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
    with open(index_path, "w") as f_out:
        json.dump(index, f_out, indent=2)
    logger.info(f"Index rebuilt: {len(weight_map)} keys, {total_size / 1e9:.1f}GB")
    logger.info("Done! Original model is now complete.")


if __name__ == "__main__":
    main()
