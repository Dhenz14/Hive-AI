"""
Fix pruned model for AutoModelForCausalLM loading.

The Qwen3.5-35B-A3B checkpoint ships as a VL (Vision-Language) model
(Qwen3_5MoeForConditionalGeneration) with tensor keys like:
    model.language_model.layers.X.*

AutoModelForCausalLM loads Qwen3_5MoeForCausalLM which expects:
    model.layers.X.*

This script:
1. Renames tensor keys: model.language_model.X → model.X
2. Drops vision-related keys (model.visual.*) — saves ~2.4GB
3. Updates config.json for CausalLM architecture
4. Generates a new, correct safetensors index

After running this, the model loads cleanly with AutoModelForCausalLM
or Unsloth — no fix functions or runtime patches needed.

Usage:
    python scripts/fix_model_keys.py
    python scripts/fix_model_keys.py --model-dir models/qwen3.5-35b-a3b-pruned
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
DEFAULT_MODEL_DIR = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b-pruned")


def read_safetensors_header(path):
    """Read tensor metadata from safetensors header (no data loaded)."""
    with open(path, "rb") as fh:
        hlen = struct.unpack("<Q", fh.read(8))[0]
        hdr = json.loads(fh.read(hlen).decode("utf-8"))
    metadata = hdr.pop("__metadata__", {})
    return hdr, metadata


def fix_shard(shard_path, dry_run=False):
    """Rename keys in a single safetensors shard. Returns (renamed, dropped, kept) counts."""
    from safetensors.torch import load_file, save_file

    logger.info(f"  Loading {os.path.basename(shard_path)}...")
    tensors = load_file(shard_path, device="cpu")

    new_tensors = {}
    renamed = 0
    dropped = 0
    kept = 0

    for key, tensor in tensors.items():
        # Drop vision keys
        if key.startswith("model.visual."):
            dropped += 1
            continue

        # Clone to detach from mmap (required to overwrite the same file)
        cloned = tensor.clone()

        # Rename language_model keys
        if key.startswith("model.language_model."):
            new_key = "model." + key[len("model.language_model."):]
            new_tensors[new_key] = cloned
            renamed += 1
        else:
            # Keep as-is (lm_head.weight, mtp.*, etc.)
            new_tensors[key] = cloned
            kept += 1

    # Release mmap before writing
    del tensors
    gc.collect()

    if not dry_run and (renamed > 0 or dropped > 0):
        logger.info(f"    Saving: {renamed} renamed, {dropped} dropped, {kept} kept")
        # Save to temp file first (Windows holds mmap even after del)
        tmp_path = shard_path + ".tmp"
        save_file(new_tensors, tmp_path)
        del new_tensors
        gc.collect()
        # Replace original with temp
        os.replace(tmp_path, shard_path)
    else:
        logger.info(f"    [DRY RUN] Would rename {renamed}, drop {dropped}, keep {kept}")
        del new_tensors
        gc.collect()

    return renamed, dropped, kept


def fix_config(model_dir, dry_run=False):
    """Update config.json from VL wrapper to CausalLM architecture."""
    config_path = os.path.join(model_dir, "config.json")
    with open(config_path, "r") as f:
        config = json.load(f)

    if config.get("architectures") == ["Qwen3_5MoeForCausalLM"]:
        logger.info("config.json already uses CausalLM architecture — skipping")
        return False

    # Extract text_config fields
    text_config = config.get("text_config", {})

    # Build new CausalLM config
    new_config = {}
    new_config["architectures"] = ["Qwen3_5MoeForCausalLM"]
    new_config["model_type"] = text_config.get("model_type", "qwen3_5_moe_text")

    # Copy all text_config fields to top level
    for k, v in text_config.items():
        new_config[k] = v

    # Preserve some top-level fields
    if "tie_word_embeddings" in config:
        new_config["tie_word_embeddings"] = config["tie_word_embeddings"]
    if "transformers_version" in config:
        new_config["transformers_version"] = config["transformers_version"]
    if "unsloth_fixed" in config:
        new_config["unsloth_fixed"] = config["unsloth_fixed"]

    # Mark as converted
    new_config["_converted_from_vl"] = True

    if not dry_run:
        # Backup original
        backup_path = config_path + ".vl_backup"
        if not os.path.exists(backup_path):
            with open(backup_path, "w") as f:
                json.dump(config, f, indent=2)
            logger.info(f"  Original config backed up to {backup_path}")

        with open(config_path, "w") as f:
            json.dump(new_config, f, indent=2)
        logger.info(f"  config.json updated: {config['architectures']} → {new_config['architectures']}")
    else:
        logger.info(f"  [DRY RUN] Would update: {config['architectures']} → ['Qwen3_5MoeForCausalLM']")

    return True


def rebuild_index(model_dir, dry_run=False):
    """Generate a new model.safetensors.index.json from actual shard contents."""
    index_path = os.path.join(model_dir, "model.safetensors.index.json")

    shard_files = sorted(
        f for f in os.listdir(model_dir)
        if f.endswith(".safetensors") and "index" not in f
    )

    weight_map = {}
    total_size = 0

    for shard_file in shard_files:
        shard_path = os.path.join(model_dir, shard_file)
        hdr, _ = read_safetensors_header(shard_path)
        for key, info in hdr.items():
            weight_map[key] = shard_file
            # Calculate tensor size from shape and dtype
            shape = info.get("shape", [])
            dtype = info.get("dtype", "BF16")
            dtype_bytes = {"BF16": 2, "F16": 2, "F32": 4, "I32": 4, "I64": 8, "U8": 1}.get(dtype, 2)
            numel = 1
            for d in shape:
                numel *= d
            total_size += numel * dtype_bytes

    index = {
        "metadata": {"total_size": total_size},
        "weight_map": dict(sorted(weight_map.items()))
    }

    if not dry_run:
        # Backup original
        backup_path = index_path + ".vl_backup"
        if not os.path.exists(backup_path) and os.path.exists(index_path):
            os.rename(index_path, backup_path)
            logger.info(f"  Original index backed up to {backup_path}")

        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)
        logger.info(f"  Index rebuilt: {len(weight_map)} keys across {len(shard_files)} shards")
    else:
        logger.info(f"  [DRY RUN] Would rebuild index: {len(weight_map)} keys across {len(shard_files)} shards")

    return len(weight_map)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fix pruned model keys for CausalLM loading")
    parser.add_argument("--model-dir", default=DEFAULT_MODEL_DIR, help="Path to pruned model directory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without modifying files")
    args = parser.parse_args()

    model_dir = args.model_dir
    if not os.path.isdir(model_dir):
        logger.error(f"Model directory not found: {model_dir}")
        sys.exit(1)

    shard_files = sorted(
        f for f in os.listdir(model_dir)
        if f.endswith(".safetensors") and "index" not in f
    )
    logger.info(f"Model directory: {model_dir}")
    logger.info(f"Found {len(shard_files)} safetensors shards")
    if args.dry_run:
        logger.info("DRY RUN — no files will be modified")

    # Check if already converted
    config_path = os.path.join(model_dir, "config.json")
    with open(config_path) as f:
        config = json.load(f)
    if config.get("_converted_from_vl"):
        logger.info("Model already converted from VL to CausalLM — nothing to do")
        return

    # Phase 1: Fix tensor keys in each shard
    start = time.time()
    total_renamed = 0
    total_dropped = 0
    total_kept = 0
    for shard_file in shard_files:
        shard_path = os.path.join(model_dir, shard_file)
        r, d, k = fix_shard(shard_path, dry_run=args.dry_run)
        total_renamed += r
        total_dropped += d
        total_kept += k
        gc.collect()

    logger.info(f"\nShard processing complete:")
    logger.info(f"  Renamed: {total_renamed} keys (model.language_model.X → model.X)")
    logger.info(f"  Dropped: {total_dropped} keys (vision encoder)")
    logger.info(f"  Kept:    {total_kept} keys (lm_head, mtp, etc.)")

    # Phase 2: Update config.json
    logger.info("\nUpdating config.json...")
    fix_config(model_dir, dry_run=args.dry_run)

    # Phase 3: Rebuild safetensors index
    logger.info("\nRebuilding safetensors index...")
    n_keys = rebuild_index(model_dir, dry_run=args.dry_run)

    elapsed = time.time() - start
    logger.info(f"\nDone in {elapsed:.0f}s")
    logger.info(f"Total keys in fixed model: {n_keys}")
    logger.info(f"Model is now loadable with AutoModelForCausalLM or Unsloth FastLanguageModel")


if __name__ == "__main__":
    main()
