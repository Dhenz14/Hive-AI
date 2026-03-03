"""
Save only the missing safetensors shards (5 and 6) for the GGUF export.

Instead of re-running the full export (~3 hours for all 6 shards),
this loads the merged model and saves only shards 5-6 (~1 hour).
Then the GGUF conversion can proceed.
"""
import json
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GGUF_DIR = os.path.join(PROJECT_ROOT, "loras", "v1", "gguf")
ADAPTER_DIR = os.path.join(PROJECT_ROOT, "loras", "v1")


def main():
    # Step 1: Load index to find which tensors go in shards 5-6
    index_path = os.path.join(GGUF_DIR, "model.safetensors.index.json")
    with open(index_path) as f:
        index = json.load(f)

    weight_map = index["weight_map"]
    missing_shards = {
        "model-00005-of-00006.safetensors": [],
        "model-00006-of-00006.safetensors": [],
    }

    for param_name, shard_file in weight_map.items():
        if shard_file in missing_shards:
            missing_shards[shard_file].append(param_name)

    for shard, params in missing_shards.items():
        logger.info("Shard %s: %d tensors needed", shard, len(params))

    # Step 2: Load model with Unsloth
    logger.info("Loading model + LoRA adapter from %s", ADAPTER_DIR)
    t0 = time.time()

    from unsloth import FastLanguageModel
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=ADAPTER_DIR,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)
    logger.info("Model loaded in %.1fs", time.time() - t0)

    # Step 3: Get state dict and extract needed tensors
    logger.info("Getting model state_dict (this dequantizes 4-bit to float16)...")
    t1 = time.time()

    # Use model.state_dict() but only keep the params we need
    # First get all param names from the model
    all_params = set()
    for shard_params in missing_shards.values():
        all_params.update(shard_params)

    logger.info("Need %d parameters total for missing shards", len(all_params))

    # Get full state dict — this triggers dequantization
    import torch
    import gc

    state_dict = model.state_dict()
    logger.info("State dict obtained in %.1fs (%d params)", time.time() - t1, len(state_dict))

    # Step 4: Save each missing shard
    from safetensors.torch import save_file

    for shard_name, param_names in missing_shards.items():
        shard_path = os.path.join(GGUF_DIR, shard_name)
        logger.info("Saving %s (%d tensors)...", shard_name, len(param_names))
        t2 = time.time()

        shard_dict = {}
        missing_params = []
        for pname in param_names:
            if pname in state_dict:
                tensor = state_dict[pname]
                # Convert to float16 for compatibility with existing shards
                if tensor.dtype == torch.float32:
                    tensor = tensor.half()
                elif tensor.dtype not in (torch.float16, torch.bfloat16):
                    tensor = tensor.to(torch.float16)
                shard_dict[pname] = tensor.contiguous().cpu()
            else:
                missing_params.append(pname)

        if missing_params:
            logger.warning("Missing %d params for %s: %s",
                          len(missing_params), shard_name,
                          missing_params[:5])

        save_file(shard_dict, shard_path)
        size_gb = os.path.getsize(shard_path) / 1e9
        logger.info("Saved %s (%.2f GB) in %.1fs",
                    shard_name, size_gb, time.time() - t2)

    # Step 5: Verify all shards exist
    logger.info("\n=== Verification ===")
    all_present = True
    for i in range(1, 7):
        shard = f"model-{i:05d}-of-00006.safetensors"
        path = os.path.join(GGUF_DIR, shard)
        if os.path.exists(path):
            size = os.path.getsize(path) / 1e9
            logger.info("  [OK] %s (%.2f GB)", shard, size)
        else:
            logger.error("  [MISSING] %s", shard)
            all_present = False

    if all_present:
        logger.info("\nAll 6 shards present! Ready for GGUF conversion.")
        logger.info("Next step: run GGUF conversion with llama.cpp or Unsloth")
    else:
        logger.error("\nSome shards still missing!")
        sys.exit(1)

    # Cleanup
    del state_dict, model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    logger.info("Done! Total time: %.1fs", time.time() - t0)


if __name__ == "__main__":
    main()
