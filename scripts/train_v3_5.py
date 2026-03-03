"""
Train HiveAI LoRA v3.5 on activation-pruned Qwen3.5-35B-A3B.

Thin wrapper around train_v3.py — reuses all training infrastructure
(monkey-patches, system optimizer, dataset formatting, callbacks) but
points at the v3.5 activation-pruned base model.

Usage:
    python scripts/train_v3_5.py                 # full training
    python scripts/train_v3_5.py --max-steps 10  # smoke test (10 steps)
    python scripts/train_v3_5.py --resume         # resume from checkpoint

What changed in v3.5 vs v3:
    - Base model: activation-pruned (not L2-norm), 8 super experts (not 3)
    - Same training data, same hyperparameters, same monkey-patches
    - Pre-validated base: passes coding generation test before training
"""
import argparse
import json
import logging
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# v3.5 paths — override train_v3 constants before importing its functions
# ---------------------------------------------------------------------------
V35_BASE_MODEL = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b-v3.5")
V35_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "loras", "v3.5")
V35_ADAPTER_GGUF = os.path.join(V35_OUTPUT_DIR, "hiveai-v3.5-lora.gguf")


def main():
    parser = argparse.ArgumentParser(description="Train HiveAI LoRA v3.5")
    parser.add_argument("--max-steps", type=int, default=0,
                        help="Stop after N steps (0=full training)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from latest checkpoint")
    parser.add_argument("--no-gguf", action="store_true",
                        help="Skip GGUF conversion after training")
    args = parser.parse_args()

    # Import train_v3 module and override its path constants
    import scripts.train_v3 as tv3

    tv3.BASE_MODEL = V35_BASE_MODEL
    tv3.OUTPUT_DIR = V35_OUTPUT_DIR
    tv3.ADAPTER_GGUF = V35_ADAPTER_GGUF
    # Training data is the same
    # tv3.TRAINING_JSONL stays as v3.jsonl (2,385 pairs, reused)

    logger.info("=" * 60)
    logger.info("  HiveAI LoRA v3.5 Training Pipeline")
    logger.info("=" * 60)
    logger.info("  Base: activation-pruned Qwen3.5-35B-A3B (8 super experts/layer)")
    logger.info(f"  Model: {V35_BASE_MODEL}")
    logger.info(f"  Data:  {tv3.TRAINING_JSONL}")
    logger.info(f"  Output: {V35_OUTPUT_DIR}")
    if args.max_steps:
        logger.info(f"  MODE: smoke test ({args.max_steps} steps)")
    else:
        logger.info("  MODE: full training")
    logger.info("=" * 60)

    # Verify the v3.5 base model exists
    if not os.path.isdir(V35_BASE_MODEL):
        logger.error(f"v3.5 base model not found: {V35_BASE_MODEL}")
        logger.error("Run activation-based pruning first:")
        logger.error("  python scripts/prune_experts.py \\")
        logger.error("    --model-dir models/qwen3.5-35b-a3b \\")
        logger.error("    --output-dir models/qwen3.5-35b-a3b-v3.5 \\")
        logger.error("    --ratio 0.5 --activation-aware --layer-adaptive")
        sys.exit(1)

    # Verify activation-aware pruning was used
    meta_path = os.path.join(V35_BASE_MODEL, "pruning_meta.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        if not meta.get("activation_aware"):
            logger.warning("WARNING: Base model was NOT activation-pruned!")
            logger.warning("This may produce the same garbage output as v3.")
            logger.warning("Re-prune with --activation-aware flag.")
        else:
            logger.info(f"  Pruning: activation-aware, "
                        f"{meta.get('super_experts_protected', '?')} super experts, "
                        f"{meta.get('routing_capacity_retained', 0):.1%} capacity retained")

    # Free GPU + maximize system resources
    tv3.unload_ollama_model()
    tv3.optimize_system()

    # Check prerequisites (uses overridden BASE_MODEL)
    model_path = tv3.check_prerequisites()

    # Train
    max_steps = args.max_steps
    loss = tv3.train_v3(model_path, max_steps=max_steps)

    if max_steps:
        logger.info(f"Smoke test complete ({max_steps} steps). Loss: {loss}")
        print(f"\nSmoke test PASSED. Loss: {loss}")
        print(f"To run full training: python scripts/train_v3_5.py")
    else:
        logger.info(f"Full training complete. Loss: {loss}")

        # Override the training_meta.json with v3.5-specific info
        meta_out_path = os.path.join(V35_OUTPUT_DIR, "training_meta.json")
        if os.path.exists(meta_out_path):
            with open(meta_out_path) as f:
                training_meta = json.load(f)
            training_meta["version"] = "v3.5"
            training_meta["base_model"] = V35_BASE_MODEL
            training_meta["pruning"] = "activation-aware, 8 super experts/layer"
            training_meta["loading_method"] = "unfused experts + BnB 4-bit NF4 (true ~9GB)"
            with open(meta_out_path, "w") as f:
                json.dump(training_meta, f, indent=2)
            logger.info("Updated training_meta.json with v3.5 info")

        # GGUF conversion (skip by default — llama.cpp broken for this arch)
        if not args.no_gguf:
            tv3.convert_to_gguf()

        # Print next steps
        print("\n" + "=" * 60)
        print("  v3.5 Training Complete -- Next Steps")
        print("=" * 60)
        print(f"""
  1. Start Python inference server:
     python scripts/serve_model.py \\
       --model {V35_BASE_MODEL} \\
       --lora {V35_OUTPUT_DIR} \\
       --port 11435

  2. Run eval:
     python scripts/run_eval.py --model hiveai-v3.5 \\
       --base-url http://localhost:11435

  3. Compare: qwen3:14b=0.741, hiveai-v1=0.853 (+15%)
""")
        print("=" * 60)


if __name__ == "__main__":
    main()
