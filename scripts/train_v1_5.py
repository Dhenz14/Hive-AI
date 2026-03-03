"""
Train HiveAI LoRA v1.5 on Qwen3-14B (proven hardware path).

Why v1.5 instead of v2:
    Qwen3.5-35B-A3B requires ~70GB peak RAM during bf16 loading before 4-bit
    quantization. With 16GB VRAM + ~53GB free RAM = 69GB available, we're 1GB
    short. v1.5 uses Qwen3-14B which fits easily in 16GB VRAM and uses the
    proven Unsloth path from v1.

What's new vs v1:
    - 1,999 premium pairs (quality >= 0.75) vs 1,104 pairs in v1
    - 2 epochs (was 3, but more data means fewer passes needed)
    - Better data quality (avg 0.829 from re-mining with all 4 templates)

One-command training:
    python scripts/train_v1_5.py
"""
import logging
import os
import subprocess
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAINING_JSONL = os.path.join(PROJECT_ROOT, "loras", "training_data", "v2_expanded.jsonl")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "loras", "v1.5")
# v1 base model (HuggingFace; already cached from v1 training)
BASE_MODEL = "unsloth/Qwen3-14B"
# v1 GGUF for llama-server (Ollama blob)
BASE_GGUF = r"C:\Users\theyc\.ollama\models\blobs\sha256-a8cc1361f3145dc01f6d77c6c82c9116b9ffe3c97b34716fe20418455876c40e"
CONVERT_SCRIPT = r"C:\Users\theyc\llama.cpp\convert_lora_to_gguf.py"
ADAPTER_GGUF = os.path.join(OUTPUT_DIR, "hiveai-v1.5-lora.gguf")


def check_prerequisites():
    if not os.path.exists(TRAINING_JSONL):
        logger.error(f"BLOCKER: Training data not found: {TRAINING_JSONL}")
        sys.exit(1)

    try:
        import unsloth  # noqa: F401
    except ImportError:
        logger.error("BLOCKER: Unsloth not installed. Run: pip install unsloth")
        sys.exit(1)

    if not os.path.exists(CONVERT_SCRIPT):
        logger.warning(f"LoRA converter not found: {CONVERT_SCRIPT} (will skip GGUF conversion)")

    logger.info("All prerequisites OK")


def train():
    """Run LoRA training via Unsloth on Qwen3-14B."""
    logger.info(f"Loading base model: {BASE_MODEL}")
    logger.info(f"Training data: {TRAINING_JSONL}")

    with open(TRAINING_JSONL, "r", encoding="utf-8") as f:
        pair_count = sum(1 for line in f if line.strip())
    logger.info(f"Training pairs: {pair_count}")

    from unsloth import FastLanguageModel

    start = time.time()
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=2048,
        load_in_4bit=True,
    )
    logger.info(f"Model loaded in {time.time() - start:.0f}s")

    # Full LoRA — all attention + MLP modules (same as v1)
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )
    logger.info("LoRA applied (r=16, alpha=32, all attention+MLP modules)")

    from datasets import load_dataset
    dataset = load_dataset("json", data_files=TRAINING_JSONL, split="train")

    # Qwen3 uses <|im_end|> as EOS (token 151645)
    eos = tokenizer.eos_token or "<|im_end|>"
    logger.info(f"EOS token: '{eos}' (id={tokenizer.eos_token_id})")

    ALPACA = (
        "Below is an instruction that describes a task. "
        "Write a response that appropriately completes the request.\n\n"
        "### Instruction:\n{instruction}\n\n"
        "### Input:\n{input}\n\n"
        "### Response:\n{output}"
    )

    def format_prompt(examples):
        texts = []
        for inst, inp, out in zip(examples["instruction"], examples["input"], examples["output"]):
            texts.append(ALPACA.format(instruction=inst, input=inp or "", output=out) + eos)
        return {"text": texts}

    dataset = dataset.map(format_prompt, batched=True)
    logger.info(f"Dataset ready: {len(dataset)} examples")

    from trl import SFTTrainer, SFTConfig

    sft_config = SFTConfig(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        num_train_epochs=2,
        learning_rate=2e-4,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        bf16=True,
        logging_steps=10,
        save_steps=200,
        weight_decay=0.01,
        max_grad_norm=1.0,
        seed=42,
        report_to="none",
        dataset_text_field="text",
        max_length=2048,
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        args=sft_config,
    )

    logger.info("Starting training...")
    start = time.time()
    stats = trainer.train()
    elapsed = time.time() - start
    loss = stats.metrics.get("train_loss", "N/A")
    logger.info(f"Training complete: loss={loss}, time={elapsed:.0f}s ({elapsed/60:.1f}min)")

    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    logger.info(f"Adapter saved to {OUTPUT_DIR}")

    import json
    meta = {
        "version": "v1.5",
        "base_model": BASE_MODEL,
        "pair_count": pair_count,
        "loss": loss,
        "training_time_s": round(elapsed),
        "lora_config": {"r": 16, "alpha": 32,
                        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj",
                                           "gate_proj", "up_proj", "down_proj"]},
        "training_config": {"batch": 1, "grad_accum": 8, "epochs": 2, "lr": 2e-4, "seq_len": 2048},
        "eos_token": eos,
        "eos_token_id": tokenizer.eos_token_id,
        "note": "Qwen3-14B + 1999 premium pairs (quality>=0.75). v2 (35B) blocked by VRAM.",
    }
    with open(os.path.join(OUTPUT_DIR, "training_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    return loss


def convert_to_gguf():
    if not os.path.exists(CONVERT_SCRIPT):
        logger.warning("convert_lora_to_gguf.py not found, skipping GGUF conversion")
        return False

    logger.info("Converting adapter to GGUF...")
    cmd = [
        sys.executable, CONVERT_SCRIPT,
        "--base-model-id", BASE_MODEL,
        OUTPUT_DIR,
    ]
    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode == 0:
        for f in os.listdir(OUTPUT_DIR):
            if f.endswith(".gguf"):
                src = os.path.join(OUTPUT_DIR, f)
                if src != ADAPTER_GGUF:
                    os.rename(src, ADAPTER_GGUF)
                size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
                logger.info(f"GGUF adapter: {ADAPTER_GGUF} ({size_mb:.0f} MB)")
                return True
        logger.error("Conversion succeeded but no .gguf file found")
        return False
    else:
        logger.error(f"GGUF conversion failed (exit {result.returncode})")
        if result.stderr:
            logger.error(f"stderr: {result.stderr[:500]}")
        return False


def print_next_steps():
    print("\n" + "=" * 60)
    print("  HiveAI v1.5 Training Complete!")
    print("=" * 60)
    print(f"\n  Adapter: {OUTPUT_DIR}")
    if os.path.exists(ADAPTER_GGUF):
        size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
        print(f"  GGUF:    {ADAPTER_GGUF} ({size_mb:.0f} MB)")
    print(f"\n  Start llama-server (v1.5):")
    print(f'    llama-server.exe \\')
    print(f'      -m "{BASE_GGUF}" \\')
    print(f'      --lora "{ADAPTER_GGUF}" \\')
    print(f'      --port 11435 --n-gpu-layers 999 --ctx-size 8192 --threads 8')
    print(f"\n  Then update .env:")
    print(f'    LLAMA_SERVER_MODEL=hiveai-v1.5')
    print("=" * 60)


if __name__ == "__main__":
    logger.info("HiveAI LoRA v1.5 Training Pipeline")
    logger.info("Base: Qwen3-14B (proven 16GB VRAM fit)")
    logger.info("Data: 1999 premium pairs (quality >= 0.75)")

    check_prerequisites()
    loss = train()
    convert_to_gguf()
    print_next_steps()
