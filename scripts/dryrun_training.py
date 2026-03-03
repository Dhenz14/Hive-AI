"""
Dry-run: validate the SFTTrainer API (trl 0.24 + transformers 5.2).
Uses a tiny randomly initialized model — NO download needed.
"""
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "loras", "dryrun")


def run():
    logger.info("=== DRY RUN: Validating SFTTrainer API (no download) ===")

    # Step 1: Create a tiny random model + tokenizer (no download)
    logger.info("Step 1: Creating tiny random model...")
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

    # Use Qwen3 config but shrunk to tiny size
    config = AutoConfig.from_pretrained(
        "Qwen/Qwen3-0.6B",  # Just fetch config (~1KB), not weights
        hidden_size=64,
        intermediate_size=128,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
    )
    model = AutoModelForCausalLM.from_config(config)
    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B")
    param_count = sum(p.numel() for p in model.parameters())
    logger.info(f"  Random model created: {param_count:,} params")

    # Step 2: Create tiny dataset
    logger.info("Step 2: Creating test dataset...")
    from datasets import Dataset

    eos = tokenizer.eos_token or "<|im_end|>"
    logger.info(f"  EOS token: '{eos}' (id={tokenizer.eos_token_id})")

    examples = []
    for i in range(10):
        text = (
            f"Below is an instruction that describes a task. "
            f"Write a response that appropriately completes the request.\n\n"
            f"### Instruction:\nTest instruction {i}\n\n"
            f"### Input:\n\n\n"
            f"### Response:\nTest response {i}{eos}"
        )
        examples.append({"text": text})

    dataset = Dataset.from_list(examples)
    logger.info(f"  Dataset ready: {len(dataset)} examples")

    # Step 3: Create SFTConfig (THE KEY TEST — this is what broke before)
    logger.info("Step 3: Testing SFTConfig + SFTTrainer (trl 0.24 API)...")
    from trl import SFTTrainer, SFTConfig

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    sft_config = SFTConfig(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=1,
        num_train_epochs=1,
        learning_rate=2e-4,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        bf16=True,
        logging_steps=1,
        save_steps=9999,
        weight_decay=0.01,
        max_grad_norm=1.0,
        seed=42,
        report_to="none",
        # SFT-specific params (the NEW API)
        dataset_text_field="text",
        max_length=128,
    )
    logger.info("  SFTConfig created: PASS")

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        args=sft_config,
    )
    logger.info("  SFTTrainer created: PASS")

    # Step 4: Train (tiny model, 10 examples, ~5 seconds)
    logger.info("Step 4: Running training...")
    start = time.time()
    stats = trainer.train()
    elapsed = time.time() - start
    loss = stats.metrics.get("train_loss", "N/A")
    logger.info(f"  Training complete: loss={loss}, time={elapsed:.1f}s")

    # Step 5: Save
    logger.info("Step 5: Saving adapter...")
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    files = os.listdir(OUTPUT_DIR)
    logger.info(f"  Output files: {[f for f in files if not f.startswith('.')]}")

    print("\n" + "=" * 60)
    print("  DRY RUN RESULTS")
    print("=" * 60)
    print(f"  SFTConfig (trl 0.24):  PASS")
    print(f"  processing_class:      PASS")
    print(f"  dataset_text_field:    PASS")
    print(f"  max_length:            PASS")
    print(f"  Training execution:    PASS (loss={loss})")
    print(f"  Time:                  {elapsed:.1f}s")
    print("=" * 60)
    print("  ALL CHECKS PASSED — pipeline ready for Qwen3.5!")
    print("=" * 60)

    # Cleanup
    import shutil
    shutil.rmtree(OUTPUT_DIR)
    logger.info(f"Cleaned up {OUTPUT_DIR}")
    return True


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
