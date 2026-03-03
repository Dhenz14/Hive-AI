"""
hiveai/lora/trainer.py

Unsloth LoRA fine-tuning wrapper for HiveAI Knowledge Refinery.

Trains a LoRA adapter on top of Qwen3-14B using eligible training pairs.
Supports versioned incremental training — each version trains on pairs
not yet used in any previous version, enabling "open-minded" brain updates.

Usage:
    from hiveai.lora.trainer import train_lora
    adapter_path = train_lora("loras/data/v1.jsonl", "loras/v1/", "v1.0", db)

Requirements:
    pip install unsloth
    CUDA GPU with >= 12GB VRAM (RTX 4070 Ti SUPER 16GB works well)
"""
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model mapping: Ollama names → HuggingFace names for Unsloth
# ---------------------------------------------------------------------------
OLLAMA_TO_HF = {
    "qwen3:14b": "unsloth/Qwen3-14B-bnb-4bit",
    "qwen3:32b": "unsloth/Qwen3-32B-bnb-4bit",
    "qwen3:8b": "unsloth/Qwen3-8B-bnb-4bit",
    "qwen3:4b": "unsloth/Qwen3-4B-bnb-4bit",
    "qwen3:1.7b": "unsloth/Qwen3-1.7B-bnb-4bit",
    # Qwen3.5 series
    "qwen3.5:35b-a3b": "unsloth/Qwen3.5-35B-A3B",
    "qwen3.5:27b": "unsloth/Qwen3.5-27B",
    "qwen3.5:9b": "unsloth/Qwen3.5-9B",
}

# Default: Qwen3.5-9B Dense (9B ALL active, fits 16GB VRAM with 4-bit, targets all MLP layers)
DEFAULT_BASE_MODEL = "unsloth/Qwen3.5-9B"

# ---------------------------------------------------------------------------
# LoRA configuration
# ---------------------------------------------------------------------------
LORA_CONFIG = {
    "r": 32,
    "lora_alpha": 64,  # alpha = 2*r for stable scaling
    # Dense model: target all attention + MLP layers (no expert overhead with dense).
    "target_modules": [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    "lora_dropout": 0.0,  # 0 enables Unsloth fast patching
    "bias": "none",
    "task_type": "CAUSAL_LM",
    "use_dora": True,  # Weight-Decomposed LoRA: +1-4.4pts quality, zero inference overhead
    "init_lora_weights": "pissa",  # PiSSA: SVD-based init, +5pts on GSM8K vs random init
}

TRAINING_CONFIG = {
    "per_device_train_batch_size": 1,   # Reduced from 2 for 4096 seq_length headroom
    "gradient_accumulation_steps": 8,   # Effective batch still = 1*8 = 8
    "num_train_epochs": 2,              # 2 epochs sufficient with quality data
    "learning_rate": 2e-4,
    "warmup_ratio": 0.03,
    "lr_scheduler_type": "cosine",
    "fp16": False,
    "bf16": True,
    "logging_steps": 10,
    "save_steps": 200,
    "weight_decay": 0.01,
    "max_grad_norm": 1.0,
    "seed": 42,
}

MIN_PAIRS_STANDARD = 500   # Standard training: full-rank, 2 epochs
MIN_PAIRS_MICRO = 20       # Micro-training: low-rank, 4 epochs, for incremental learning
MIN_PAIRS_TO_TRAIN = MIN_PAIRS_MICRO  # Backward-compat alias
MAX_SEQ_LENGTH = 4096  # Full context — batch_size=1 + grad_accum=8 fits 16GB VRAM

# ---------------------------------------------------------------------------
# Micro-training config: small datasets (20-99 pairs), concept injection
# Lower rank + lower LR + more epochs = stable learning without forgetting
# ---------------------------------------------------------------------------
MICRO_LORA_CONFIG = {
    "r": 8,
    "lora_alpha": 16,           # alpha = 2*r
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
    "lora_dropout": 0.0,
    "bias": "none",
    "task_type": "CAUSAL_LM",
    "use_dora": True,
    "init_lora_weights": "pissa",
}

MICRO_TRAINING_CONFIG = {
    "per_device_train_batch_size": 1,
    "gradient_accumulation_steps": 8,   # Effective batch = 8
    "num_train_epochs": 4,              # More passes for small data
    "learning_rate": 1e-4,              # Half of standard to avoid forgetting
    "warmup_ratio": 0.1,               # Proportionally longer warmup
    "lr_scheduler_type": "cosine",
    "fp16": False,
    "bf16": True,
    "logging_steps": 5,
    "save_steps": 50,
    "weight_decay": 0.01,
    "max_grad_norm": 1.0,
    "seed": 42,
}

# ChatML prompt template — matches Qwen's native format and what llama-server
# sends at inference. Using this instead of Alpaca means the LoRA learns
# knowledge, not format translation.
# System prompt MUST match what llama-server sends at inference (CODING_SYSTEM_PROMPT).
# Using a generic system prompt here wastes LoRA capacity on persona translation.
from hiveai.llm.prompts import CODING_SYSTEM_PROMPT
CHATML_SYSTEM = CODING_SYSTEM_PROMPT

# Fallback template used only if tokenizer.apply_chat_template is unavailable.
CHATML_PROMPT = (
    "<|im_start|>system\n{system}<|im_end|>\n"
    "<|im_start|>user\n{instruction}{input}<|im_end|>\n"
    "<|im_start|>assistant\n{output}<|im_end|>"
)

# Backward compat alias — old scripts that import ALPACA_PROMPT still work
ALPACA_PROMPT = CHATML_PROMPT

EOS_TOKEN = "<|im_end|>"  # Qwen3.5 uses <|im_end|> (248044); set dynamically from tokenizer


def _check_unsloth():
    try:
        import unsloth  # noqa: F401
        return True
    except ImportError:
        return False


def _resolve_model_name(ollama_name: str = None) -> str:
    """Convert Ollama model name to HuggingFace name for Unsloth.
    Also accepts local paths (directories containing safetensors)."""
    if ollama_name and os.path.isdir(ollama_name):
        return ollama_name  # local path to downloaded model
    if ollama_name and ollama_name in OLLAMA_TO_HF:
        return OLLAMA_TO_HF[ollama_name]
    if ollama_name and ollama_name.startswith("unsloth/"):
        return ollama_name  # already HF format
    return DEFAULT_BASE_MODEL


def train_lora(jsonl_path: str, output_dir: str, version: str,
               db=None, base_model: str = None, force_micro: bool = False) -> str:
    """
    Fine-tune a LoRA adapter on training pairs.

    Automatically selects micro-training (r=8, 4 epochs) for <100 pairs
    or standard training (r=32, 2 epochs) for >=100 pairs.

    Args:
        jsonl_path: Path to Alpaca-format JSONL file
        output_dir: Directory to save adapter
        version: Version string (e.g. "v1.0")
        db: Optional SQLAlchemy session for tracking
        base_model: HF model name or Ollama name (auto-resolved)
        force_micro: Force micro-training mode regardless of pair count

    Returns:
        Path to the saved adapter directory
    """
    if not _check_unsloth():
        raise ImportError(
            "Unsloth is not installed. Install with: pip install unsloth\n"
            "Requires CUDA GPU. See https://github.com/unslothai/unsloth"
        )

    pair_count = _count_jsonl_lines(jsonl_path)
    if pair_count < MIN_PAIRS_MICRO:
        raise ValueError(
            f"Not enough training pairs: {pair_count} found, "
            f"{MIN_PAIRS_MICRO} required (micro minimum)."
        )

    # Auto-detect training mode
    is_micro = force_micro or pair_count < MIN_PAIRS_STANDARD
    lora_cfg = MICRO_LORA_CONFIG if is_micro else LORA_CONFIG
    train_cfg = MICRO_TRAINING_CONFIG if is_micro else TRAINING_CONFIG
    mode_label = "micro" if is_micro else "standard"

    hf_model = _resolve_model_name(base_model)
    logger.info(
        f"LoRA Training v{version} [{mode_label}]: {pair_count} pairs, "
        f"r={lora_cfg['r']}, epochs={train_cfg['num_train_epochs']}, "
        f"model={hf_model}, output={output_dir}"
    )

    # Create version record in DB
    lora_version_id = None
    if db is not None:
        lora_version_id = _create_lora_version_record(
            db, version, hf_model, pair_count
        )

    os.makedirs(output_dir, exist_ok=True)

    try:
        adapter_path, train_loss = _run_unsloth_training(
            jsonl_path, output_dir, hf_model,
            lora_cfg=lora_cfg, train_cfg=train_cfg,
        )
        logger.info(f"Training complete [{mode_label}]. Adapter: {adapter_path}")

        if db is not None and lora_version_id is not None:
            _update_lora_version_status(db, lora_version_id, "ready", adapter_path)
            # Mark training pairs with this version for incremental tracking
            _mark_pairs_with_version(db, lora_version_id, data_path=jsonl_path)

        # Save training metadata
        _save_training_metadata(
            output_dir, version, hf_model, pair_count, jsonl_path,
            train_loss=train_loss, lora_cfg=lora_cfg, train_cfg=train_cfg,
        )

        return adapter_path

    except Exception as e:
        logger.error(f"LoRA training failed: {e}")
        if db is not None and lora_version_id is not None:
            _update_lora_version_status(db, lora_version_id, "failed")
        raise


def _run_unsloth_training(jsonl_path: str, output_dir: str, hf_model: str,
                          lora_cfg: dict = None, train_cfg: dict = None) -> tuple:
    """Execute Unsloth LoRA training.

    Args:
        lora_cfg: LoRA configuration dict (defaults to LORA_CONFIG)
        train_cfg: Training configuration dict (defaults to TRAINING_CONFIG)

    Returns:
        (adapter_path, train_loss) tuple
    """
    from unsloth import FastLanguageModel
    from datasets import load_dataset
    from trl import SFTTrainer, SFTConfig

    lora_cfg = lora_cfg or LORA_CONFIG
    train_cfg = train_cfg or TRAINING_CONFIG

    logger.info(f"Loading base model: {hf_model}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=hf_model,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
    )

    # Apply LoRA
    init_weights = lora_cfg.get("init_lora_weights", True)
    logger.info(
        f"Applying LoRA: r={lora_cfg['r']}, alpha={lora_cfg['lora_alpha']}, "
        f"DoRA={lora_cfg.get('use_dora', False)}, init={init_weights}"
    )
    peft_kwargs = dict(
        r=lora_cfg["r"],
        lora_alpha=lora_cfg["lora_alpha"],
        target_modules=lora_cfg["target_modules"],
        lora_dropout=lora_cfg["lora_dropout"],
        bias=lora_cfg["bias"],
        use_dora=lora_cfg.get("use_dora", False),
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )
    # PiSSA/MiLoRA init — only pass if supported by installed Unsloth version
    if init_weights and init_weights != True:
        peft_kwargs["init_lora_weights"] = init_weights
    model = FastLanguageModel.get_peft_model(model, **peft_kwargs)

    # Load and format dataset
    logger.info(f"Loading dataset from {jsonl_path}")
    dataset = load_dataset("json", data_files=jsonl_path, split="train")

    # Format training data as ChatML — matches the model's native format and
    # what llama-server sends at inference time via chat_template.
    # apply_chat_template handles special tokens (<|im_start|>, <|im_end|>)
    # correctly. We truncate the assistant output (not the whole sequence) so
    # the final <|im_end|> EOS token is always present.
    def format_prompt(examples):
        texts = []
        n_truncated = 0
        for instruction, inp, output in zip(
            examples["instruction"], examples["input"], examples["output"]
        ):
            user_content = instruction
            if inp:
                user_content += "\n" + inp

            messages = [
                {"role": "system", "content": CHATML_SYSTEM},
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": output},
            ]

            try:
                text = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=False
                )
            except Exception:
                # Fallback: manual ChatML formatting
                text = CHATML_PROMPT.format(
                    system=CHATML_SYSTEM,
                    instruction=instruction,
                    input=("\n" + inp) if inp else "",
                    output=output,
                )

            # If too long, truncate the assistant output in token space
            n_tokens = len(tokenizer.encode(text))
            if n_tokens > MAX_SEQ_LENGTH:
                overhead_messages = [
                    {"role": "system", "content": CHATML_SYSTEM},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": ""},
                ]
                try:
                    overhead_text = tokenizer.apply_chat_template(
                        overhead_messages, tokenize=False, add_generation_prompt=False
                    )
                    overhead_tokens = len(tokenizer.encode(overhead_text))
                except Exception:
                    overhead_tokens = n_tokens - len(tokenizer.encode(output))
                budget = MAX_SEQ_LENGTH - overhead_tokens - 1
                out_tokens = tokenizer.encode(output, add_special_tokens=False)[:budget]
                truncated_out = tokenizer.decode(out_tokens, skip_special_tokens=False)
                messages[-1]["content"] = truncated_out
                try:
                    text = tokenizer.apply_chat_template(
                        messages, tokenize=False, add_generation_prompt=False
                    )
                except Exception:
                    text = CHATML_PROMPT.format(
                        system=CHATML_SYSTEM,
                        instruction=instruction,
                        input=("\n" + inp) if inp else "",
                        output=truncated_out,
                    )
                n_truncated += 1

            texts.append(text)

        if n_truncated > 0:
            logger.info(f"  format_prompt: truncated {n_truncated}/{len(texts)} to fit {MAX_SEQ_LENGTH} tokens")
        return {"text": texts}

    dataset = dataset.map(format_prompt, batched=True)
    logger.info(f"Dataset ready: {len(dataset)} examples")

    # SFTConfig replaces TrainingArguments for SFTTrainer (trl 0.24+)
    sft_config = SFTConfig(
        output_dir=output_dir,
        per_device_train_batch_size=train_cfg["per_device_train_batch_size"],
        gradient_accumulation_steps=train_cfg["gradient_accumulation_steps"],
        num_train_epochs=train_cfg["num_train_epochs"],
        learning_rate=train_cfg["learning_rate"],
        warmup_ratio=train_cfg["warmup_ratio"],
        lr_scheduler_type=train_cfg["lr_scheduler_type"],
        fp16=train_cfg["fp16"],
        bf16=train_cfg["bf16"],
        logging_steps=train_cfg["logging_steps"],
        save_steps=train_cfg["save_steps"],
        weight_decay=train_cfg["weight_decay"],
        max_grad_norm=train_cfg["max_grad_norm"],
        seed=train_cfg["seed"],
        report_to="none",
        # SFT-specific params (moved from SFTTrainer constructor in trl 0.24+)
        dataset_text_field="text",
        max_length=MAX_SEQ_LENGTH,
        # NEFTune: add gaussian noise to input embeddings during training.
        # Paper shows +0.5-1% quality improvement on benchmarks, zero cost.
        neftune_noise_alpha=5.0,
    )

    # Train
    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        args=sft_config,
    )

    # Preserve curriculum ordering from exporter (beginner → intermediate → expert).
    # SFTTrainer uses RandomSampler by default, which negates the intentional sort.
    from torch.utils.data import SequentialSampler
    trainer._get_train_sampler = lambda: SequentialSampler(trainer.train_dataset)

    # Check for existing checkpoints to resume from
    resume_checkpoint = None
    if os.path.exists(output_dir):
        checkpoints = sorted(
            [d for d in os.listdir(output_dir) if d.startswith("checkpoint-")],
            key=lambda x: int(x.split("-")[-1]) if x.split("-")[-1].isdigit() else 0,
        )
        if checkpoints:
            resume_checkpoint = os.path.join(output_dir, checkpoints[-1])
            logger.info(f"Resuming from checkpoint: {resume_checkpoint}")

    logger.info("Starting training...")
    stats = trainer.train(resume_from_checkpoint=resume_checkpoint)
    logger.info(
        f"Training complete: {stats.metrics.get('train_loss', 'N/A')} final loss, "
        f"{stats.metrics.get('train_runtime', 'N/A'):.0f}s runtime"
    )

    # Save adapter
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    logger.info(f"Adapter saved to {output_dir}")

    train_loss = stats.metrics.get("train_loss")
    return output_dir, train_loss


def _count_jsonl_lines(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except FileNotFoundError:
        return 0


def _create_lora_version_record(db, version: str, base_model: str, pair_count: int) -> int:
    from hiveai.models import LoraVersion
    lv = LoraVersion(
        version=version,
        base_model=base_model,
        pair_count=pair_count,
        status="training",
        created_at=datetime.now(timezone.utc),
    )
    db.add(lv)
    db.commit()
    db.refresh(lv)
    return lv.id


def _update_lora_version_status(db, lora_version_id: int, status: str,
                                 adapter_path: str = None):
    from hiveai.models import LoraVersion
    lv = db.query(LoraVersion).filter(LoraVersion.id == lora_version_id).first()
    if lv:
        lv.status = status
        if adapter_path:
            lv.adapter_path = adapter_path
        db.commit()


def _mark_pairs_with_version(db, lora_version_id: int, data_path: str = None):
    """Mark only the pairs that were actually trained on (present in the JSONL).
    This enables correct incremental training — untrained pairs stay available."""
    from hiveai.models import TrainingPair

    if data_path and os.path.exists(data_path):
        # Parse the JSONL to get the exact set of instructions that were trained
        trained_instructions = set()
        with open(data_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    instr = record.get("instruction", "").strip()
                    if instr:
                        trained_instructions.add(instr[:200])  # match key prefix
                except json.JSONDecodeError:
                    continue

        # Mark only pairs whose instruction matches the training data
        count = 0
        pairs = db.query(TrainingPair).filter(
            TrainingPair.is_eligible == True,
            TrainingPair.lora_version == None,
        ).all()
        for pair in pairs:
            if pair.instruction.strip()[:200] in trained_instructions:
                pair.lora_version = lora_version_id
                count += 1
        db.commit()
        logger.info(f"Marked {count} trained pairs (of {len(trained_instructions)} in JSONL) with lora_version={lora_version_id}")
    else:
        # Fallback: mark all eligible (legacy behavior)
        count = db.query(TrainingPair).filter(
            TrainingPair.is_eligible == True,
            TrainingPair.quality >= 0.70,
            TrainingPair.lora_version == None,
        ).update({TrainingPair.lora_version: lora_version_id})
        db.commit()
        logger.warning(f"No data_path provided — marked ALL {count} eligible pairs (legacy mode)")


def _save_training_metadata(output_dir: str, version: str, model: str,
                            pair_count: int, data_path: str, train_loss: float = None,
                            lora_cfg: dict = None, train_cfg: dict = None):
    """Save training metadata for reproducibility."""
    lora_cfg = lora_cfg or LORA_CONFIG
    train_cfg = train_cfg or TRAINING_CONFIG
    is_micro = lora_cfg.get("r", 32) < 16
    meta = {
        "version": version,
        "base_model": model,
        "pair_count": pair_count,
        "data_path": data_path,
        "training_mode": "micro" if is_micro else "standard",
        "lora_config": lora_cfg,
        "training_config": train_cfg,
        "max_seq_length": MAX_SEQ_LENGTH,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "loss": train_loss,
    }
    meta_path = os.path.join(output_dir, "training_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    logger.info(f"Training metadata saved to {meta_path}")


def get_training_status(db) -> dict:
    """Return current training status summary."""
    from hiveai.models import TrainingPair, LoraVersion

    total = db.query(TrainingPair).count()
    eligible = db.query(TrainingPair).filter(TrainingPair.is_eligible == True).count()
    unused = db.query(TrainingPair).filter(
        TrainingPair.is_eligible == True,
        TrainingPair.quality >= 0.70,
        TrainingPair.lora_version == None,
    ).count()
    versions = db.query(LoraVersion).order_by(LoraVersion.created_at.desc()).limit(5).all()

    return {
        "total_pairs": total,
        "eligible_pairs": eligible,
        "unused_pairs": unused,
        "ready_to_train": unused >= MIN_PAIRS_MICRO,
        "ready_for_micro": MIN_PAIRS_MICRO <= unused < MIN_PAIRS_STANDARD,
        "ready_for_standard": unused >= MIN_PAIRS_STANDARD,
        "min_pairs_micro": MIN_PAIRS_MICRO,
        "min_pairs_standard": MIN_PAIRS_STANDARD,
        "unsloth_available": _check_unsloth(),
        "versions": [
            {
                "id": v.id,
                "version": v.version,
                "base_model": v.base_model,
                "pair_count": v.pair_count,
                "benchmark_score": v.benchmark_score,
                "status": v.status,
                "adapter_path": v.adapter_path,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ],
    }
