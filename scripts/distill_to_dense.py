"""
scripts/distill_to_dense.py

Knowledge distillation: 35B MoE teacher → 8B dense student.

Uses the fine-tuned Qwen3.5-35B-A3B (via llama-server) as a teacher to generate
high-quality training data, then fine-tunes a compact dense student model.

Why distill?
  - 35B MoE needs ~20GB GGUF + 16GB VRAM → limits deployment
  - 8B dense runs on 8GB VRAM, 4x faster inference, same deployment pipeline
  - Teacher-student distillation retains 85-92% of coding quality
  - Dense model works with Ollama (no llama-server workaround needed)

Pipeline:
  Phase 1: Generate teacher outputs — run all training pairs through the fine-tuned
            teacher model to get its "gold" responses
  Phase 2: Train student — fine-tune Qwen3-8B (or Qwen3.5-8B) on teacher outputs
  Phase 3: Evaluate — compare student vs teacher on eval challenges

Usage:
    python scripts/distill_to_dense.py generate     # Phase 1: generate teacher data
    python scripts/distill_to_dense.py train         # Phase 2: train student
    python scripts/distill_to_dense.py eval          # Phase 3: evaluate student
    python scripts/distill_to_dense.py full          # all three phases

Requirements:
    - Teacher model running on llama-server (port 11435)
    - GPU with >= 12GB VRAM for student training
    - pip install unsloth datasets trl
"""
import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DB_FILE = PROJECT_ROOT / "hiveai.db"
DATA_DIR = PROJECT_ROOT / "loras" / "training_data"
STUDENT_DATA_FILE = DATA_DIR / "student_distill.jsonl"
STUDENT_OUTPUT_DIR = PROJECT_ROOT / "loras" / "student-8b"

# Teacher configuration (fine-tuned MoE on llama-server)
TEACHER_BASE_URL = "http://localhost:11435"
TEACHER_MODEL = "hiveai-v2"

# Student configuration
STUDENT_BASE_MODEL = "unsloth/Qwen3-8B-bnb-4bit"
STUDENT_VERSION = "student-8b-v1"

# Training config for student (smaller model = can use larger batch)
STUDENT_TRAINING_CONFIG = {
    "per_device_train_batch_size": 4,
    "gradient_accumulation_steps": 4,
    "num_train_epochs": 3,          # more epochs for smaller model to absorb knowledge
    "learning_rate": 2e-4,
    "warmup_ratio": 0.05,
    "lr_scheduler_type": "cosine",
    "fp16": False,
    "bf16": True,
    "logging_steps": 10,
    "save_steps": 500,
    "weight_decay": 0.01,
    "max_grad_norm": 1.0,
    "seed": 42,
}

STUDENT_LORA_CONFIG = {
    "r": 32,
    "lora_alpha": 64,
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
    "lora_dropout": 0.0,
    "bias": "none",
    "use_dora": True,
}

MAX_SEQ_LENGTH = 2048
MIN_QUALITY = 0.75


def query_teacher(instruction: str, max_tokens: int = 4096, temperature: float = 0.1) -> str:
    """Query the teacher model (fine-tuned MoE) via llama-server."""
    import urllib.request
    import urllib.error

    payload = {
        "model": TEACHER_MODEL,
        "messages": [
            {"role": "system", "content": (
                "You are an expert software engineer. Provide thorough, accurate responses "
                "with complete working code examples. Be precise and practical."
            )},
            {"role": "user", "content": instruction},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    req = urllib.request.Request(
        f"{TEACHER_BASE_URL}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
    except urllib.error.URLError as e:
        logger.warning(f"Teacher query failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Teacher query error: {e}")
        return None


def check_teacher_available() -> bool:
    """Check if the teacher model is accessible on llama-server."""
    import urllib.request
    try:
        urllib.request.urlopen(f"{TEACHER_BASE_URL}/health", timeout=5)
        return True
    except Exception:
        return False


# ── Phase 1: Generate teacher data ─────────────────────────────────────────

def generate_teacher_data(limit: int = None, resume: bool = True):
    """
    Generate training data by running instructions through the teacher model.

    Reads high-quality instructions from the DB, queries the teacher for responses,
    and saves as JSONL for student training.
    """
    if not check_teacher_available():
        logger.error(f"Teacher model not available at {TEACHER_BASE_URL}")
        logger.error("Start llama-server with the fine-tuned adapter first:")
        logger.error(f"  python scripts/deploy_v2.py --now")
        sys.exit(1)

    os.makedirs(DATA_DIR, exist_ok=True)

    # Load existing pairs to avoid re-generating
    existing_instructions = set()
    if resume and STUDENT_DATA_FILE.exists():
        with open(STUDENT_DATA_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    pair = json.loads(line)
                    existing_instructions.add(pair.get("instruction", "")[:100])
        logger.info(f"Resuming: {len(existing_instructions)} existing pairs found")

    # Fetch instructions from DB
    con = sqlite3.connect(str(DB_FILE))
    cur = con.cursor()
    cur.execute(
        "SELECT instruction, response, quality FROM training_pairs "
        "WHERE is_eligible = 1 AND quality >= ? "
        "ORDER BY quality DESC",
        (MIN_QUALITY,)
    )
    rows = cur.fetchall()
    con.close()

    logger.info(f"Found {len(rows)} eligible pairs in DB (quality >= {MIN_QUALITY})")

    if limit:
        rows = rows[:limit]
        logger.info(f"Limited to {limit} pairs")

    generated = 0
    skipped = 0
    failed = 0

    with open(STUDENT_DATA_FILE, "a", encoding="utf-8") as f:
        for i, (instruction, original_response, quality) in enumerate(rows):
            # Skip if already generated
            if instruction[:100] in existing_instructions:
                skipped += 1
                continue

            # Query teacher
            teacher_response = query_teacher(instruction)
            if not teacher_response or len(teacher_response.strip()) < 50:
                failed += 1
                continue

            # Format as Alpaca-style JSONL
            pair = {
                "instruction": instruction,
                "input": "",
                "output": teacher_response.strip(),
                "source": "teacher_distill",
                "teacher_model": TEACHER_MODEL,
                "original_quality": quality,
            }
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")
            generated += 1
            existing_instructions.add(instruction[:100])

            if (i + 1) % 10 == 0:
                logger.info(f"  Progress: {i+1}/{len(rows)} "
                           f"(generated={generated}, skipped={skipped}, failed={failed})")

            # Small delay to avoid overwhelming llama-server
            time.sleep(0.5)

    logger.info(f"\nTeacher data generation complete:")
    logger.info(f"  Generated: {generated}")
    logger.info(f"  Skipped (existing): {skipped}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Output: {STUDENT_DATA_FILE}")

    # Count total
    total = sum(1 for line in open(STUDENT_DATA_FILE, "r", encoding="utf-8") if line.strip())
    logger.info(f"  Total pairs in file: {total}")

    return str(STUDENT_DATA_FILE)


# ── Phase 2: Train student model ───────────────────────────────────────────

def train_student():
    """Fine-tune the student model on teacher-generated data."""
    try:
        from unsloth import FastLanguageModel
        from datasets import load_dataset
        from trl import SFTTrainer, SFTConfig
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        logger.error("Install with: pip install unsloth datasets trl")
        sys.exit(1)

    if not STUDENT_DATA_FILE.exists():
        logger.error(f"Training data not found: {STUDENT_DATA_FILE}")
        logger.error("Run 'python scripts/distill_to_dense.py generate' first")
        sys.exit(1)

    # Count pairs
    pair_count = sum(1 for line in open(STUDENT_DATA_FILE, "r", encoding="utf-8") if line.strip())
    if pair_count < 100:
        logger.error(f"Only {pair_count} pairs found, need at least 100 for quality training")
        sys.exit(1)

    logger.info(f"Training student model: {STUDENT_BASE_MODEL}")
    logger.info(f"  Training data: {STUDENT_DATA_FILE} ({pair_count} pairs)")
    logger.info(f"  Output: {STUDENT_OUTPUT_DIR}")

    # Load student model
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=STUDENT_BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
    )

    # Apply LoRA with DoRA
    model = FastLanguageModel.get_peft_model(
        model,
        r=STUDENT_LORA_CONFIG["r"],
        lora_alpha=STUDENT_LORA_CONFIG["lora_alpha"],
        target_modules=STUDENT_LORA_CONFIG["target_modules"],
        lora_dropout=STUDENT_LORA_CONFIG["lora_dropout"],
        bias=STUDENT_LORA_CONFIG["bias"],
        use_dora=STUDENT_LORA_CONFIG["use_dora"],
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # Load and format dataset
    dataset = load_dataset("json", data_files=str(STUDENT_DATA_FILE), split="train")

    eos = tokenizer.eos_token or "<|im_end|>"
    alpaca_prompt = (
        "Below is an instruction that describes a task. "
        "Write a response that appropriately completes the request.\n\n"
        "### Instruction:\n{instruction}\n\n"
        "### Input:\n{input}\n\n"
        "### Response:\n{output}"
    )

    def format_prompt(examples):
        texts = []
        for instruction, inp, output in zip(
            examples["instruction"], examples["input"], examples["output"]
        ):
            text = alpaca_prompt.format(
                instruction=instruction,
                input=inp or "",
                output=output,
            ) + eos
            texts.append(text)
        return {"text": texts}

    dataset = dataset.map(format_prompt, batched=True)
    logger.info(f"Dataset ready: {len(dataset)} examples")

    os.makedirs(str(STUDENT_OUTPUT_DIR), exist_ok=True)

    sft_config = SFTConfig(
        output_dir=str(STUDENT_OUTPUT_DIR),
        per_device_train_batch_size=STUDENT_TRAINING_CONFIG["per_device_train_batch_size"],
        gradient_accumulation_steps=STUDENT_TRAINING_CONFIG["gradient_accumulation_steps"],
        num_train_epochs=STUDENT_TRAINING_CONFIG["num_train_epochs"],
        learning_rate=STUDENT_TRAINING_CONFIG["learning_rate"],
        warmup_ratio=STUDENT_TRAINING_CONFIG["warmup_ratio"],
        lr_scheduler_type=STUDENT_TRAINING_CONFIG["lr_scheduler_type"],
        fp16=STUDENT_TRAINING_CONFIG["fp16"],
        bf16=STUDENT_TRAINING_CONFIG["bf16"],
        logging_steps=STUDENT_TRAINING_CONFIG["logging_steps"],
        save_steps=STUDENT_TRAINING_CONFIG["save_steps"],
        weight_decay=STUDENT_TRAINING_CONFIG["weight_decay"],
        max_grad_norm=STUDENT_TRAINING_CONFIG["max_grad_norm"],
        seed=STUDENT_TRAINING_CONFIG["seed"],
        report_to="none",
        dataset_text_field="text",
        max_length=MAX_SEQ_LENGTH,
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        args=sft_config,
    )

    logger.info("Starting student training...")
    start_time = time.time()
    stats = trainer.train()
    duration = time.time() - start_time

    logger.info(
        f"Training complete: loss={stats.metrics.get('train_loss', 'N/A')}, "
        f"runtime={duration:.0f}s"
    )

    # Save adapter
    model.save_pretrained(str(STUDENT_OUTPUT_DIR))
    tokenizer.save_pretrained(str(STUDENT_OUTPUT_DIR))

    # Save metadata
    meta = {
        "version": STUDENT_VERSION,
        "base_model": STUDENT_BASE_MODEL,
        "teacher_model": TEACHER_MODEL,
        "pair_count": pair_count,
        "loss": stats.metrics.get("train_loss"),
        "training_time_s": duration,
        "lora_config": STUDENT_LORA_CONFIG,
        "training_config": STUDENT_TRAINING_CONFIG,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    meta_path = STUDENT_OUTPUT_DIR / "training_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info(f"Student adapter saved to {STUDENT_OUTPUT_DIR}")
    logger.info(f"Metadata: {meta_path}")

    return str(STUDENT_OUTPUT_DIR)


# ── Phase 3: Evaluate student model ────────────────────────────────────────

def eval_student():
    """
    Run eval challenges against the student model and compare with teacher.
    Requires the student to be running on Ollama or llama-server.
    """
    import subprocess

    eval_script = PROJECT_ROOT / "scripts" / "run_eval.py"
    if not eval_script.exists():
        logger.error("run_eval.py not found")
        sys.exit(1)

    log_dir = PROJECT_ROOT / "logs"
    os.makedirs(str(log_dir), exist_ok=True)

    # Check if student GGUF exists
    student_gguf = STUDENT_OUTPUT_DIR / f"hiveai-{STUDENT_VERSION}-lora.gguf"
    if not student_gguf.exists():
        logger.warning(f"Student GGUF not found at {student_gguf}")
        logger.warning("Convert first: python llama.cpp/convert_lora_to_gguf.py --base-model-id unsloth/Qwen3-8B loras/student-8b/")

    # Run eval
    log_path = log_dir / f"eval_{STUDENT_VERSION}.log"
    logger.info(f"Running eval for {STUDENT_VERSION}...")

    cmd = [
        sys.executable, str(eval_script),
        "--model", STUDENT_VERSION,
        "--base-url", TEACHER_BASE_URL,
    ]
    logger.info(f"  {' '.join(cmd)}")

    with open(str(log_path), "w") as log_f:
        result = subprocess.run(cmd, stdout=log_f, stderr=log_f, timeout=7200)

    if result.returncode == 0:
        with open(str(log_path)) as f:
            eval_out = f.read()
        import re
        score_match = re.search(r"Overall.*?(0\.\d+)", eval_out)
        if score_match:
            score = float(score_match.group(1))
            logger.info(f"Student eval score: {score:.3f}")
            print(f"\n  Student ({STUDENT_VERSION}): {score:.3f}")
            print(f"  Baselines:")
            print(f"    qwen3:14b (base):     0.741")
            print(f"    hiveai-v1 (LoRA 14B): 0.853")
            print(f"    Teacher (MoE 35B):    TBD")
            retention = score / 0.853 * 100 if score > 0 else 0
            print(f"\n  Quality retention vs v1: {retention:.1f}%")
        else:
            logger.info("Eval complete (score not parsed)")
    else:
        logger.warning(f"Eval failed with code {result.returncode}")
        logger.warning(f"Check log: {log_path}")

    return str(log_path)


def main():
    parser = argparse.ArgumentParser(
        description="Dense Model Distillation: 35B MoE Teacher → 8B Dense Student",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Pipeline:
  1. generate — Query teacher model for all training pair responses
  2. train   — Fine-tune 8B student on teacher outputs
  3. eval    — Evaluate student vs teacher quality
  4. full    — Run all three phases sequentially

The teacher (fine-tuned Qwen3.5-35B-A3B) must be running on llama-server.
        """
    )
    parser.add_argument("phase", choices=["generate", "train", "eval", "full"],
                        help="Which phase to run")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of pairs to generate (for testing)")
    parser.add_argument("--no-resume", action="store_true",
                        help="Don't resume from existing teacher data file")
    args = parser.parse_args()

    print("=" * 60)
    print("  Dense Model Distillation")
    print(f"  Teacher: {TEACHER_MODEL} (Qwen3.5-35B-A3B MoE)")
    print(f"  Student: {STUDENT_BASE_MODEL} (8B dense)")
    print("=" * 60)

    if args.phase in ("generate", "full"):
        print("\n--- Phase 1: Generate Teacher Data ---")
        generate_teacher_data(limit=args.limit, resume=not args.no_resume)

    if args.phase in ("train", "full"):
        print("\n--- Phase 2: Train Student Model ---")
        train_student()

    if args.phase in ("eval", "full"):
        print("\n--- Phase 3: Evaluate Student ---")
        eval_student()

    print("\n" + "=" * 60)
    print("  Distillation Complete!")
    print("=" * 60)
    print(f"  Student adapter: {STUDENT_OUTPUT_DIR}")
    print(f"  Next steps:")
    print(f"    1. Convert to GGUF for llama-server deployment")
    print(f"    2. Or create Ollama Modelfile (dense model works with Ollama!)")
    print(f"    3. Compare eval scores: student vs teacher")
    print("=" * 60)


if __name__ == "__main__":
    main()
