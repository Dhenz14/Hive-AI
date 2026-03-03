"""
scripts/train_lora_v1.py

Launch LoRA v1.0 training on the exported training pairs.
Logs to both console and logs/lora_training_v1.log
"""
import logging
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Disable HuggingFace fast download (was causing stalls on Windows)
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"

# Force fused cross entropy to use only 1GB (prevents OOM on 16GB GPU)
os.environ["UNSLOTH_CE_LOSS_TARGET_GB"] = "1"

# Setup logging
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "lora_training_v1.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(log_file, mode="a"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def main():
    from hiveai.config import detect_hardware, get_hardware_profile
    hw = detect_hardware()
    profile = get_hardware_profile()
    logger.info(f"Hardware profile: {profile} "
                f"(CPUs={hw['cpus']}, RAM={hw['ram_gb']:.1f}GB)")

    jsonl_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "loras", "training_data", "v1.jsonl")
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "loras", "v1")

    if not os.path.exists(jsonl_path):
        logger.error(f"Training data not found: {jsonl_path}")
        sys.exit(1)

    # Count pairs
    with open(jsonl_path, encoding="utf-8") as f:
        pair_count = sum(1 for line in f if line.strip())
    logger.info(f"Training data: {pair_count} pairs from {jsonl_path}")

    # Get DB session for tracking
    try:
        from hiveai.models import SessionLocal
        db = SessionLocal()
        logger.info("Database session acquired for training tracking")
    except Exception as e:
        logger.warning(f"Could not get DB session (training will proceed without tracking): {e}")
        db = None

    start_time = time.time()

    try:
        from hiveai.lora.trainer import train_lora
        adapter_path = train_lora(
            jsonl_path=jsonl_path,
            output_dir=output_dir,
            version="v1.0",
            db=db,
            base_model="unsloth/Qwen3-14B-bnb-4bit",
        )
        elapsed = time.time() - start_time
        logger.info(f"LoRA v1.0 training COMPLETE in {elapsed/60:.1f} minutes")
        logger.info(f"Adapter saved to: {adapter_path}")

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"LoRA v1.0 training FAILED after {elapsed/60:.1f} minutes: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    main()
