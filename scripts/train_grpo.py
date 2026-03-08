"""
Train HiveAI LoRA via GRPO (Group Relative Policy Optimization).

GRPO trains the model to generate better responses by:
1. Generating multiple responses per prompt (group_size)
2. Scoring each with a reward function (code quality + concept coverage)
3. Optimizing toward higher-scoring responses relative to the group mean

Prerequisites:
    - Stable SFT baseline (v7/v8 LoRA verified non-degrading)
    - Unsloth 2026.2.1+ in WSL venv (/opt/hiveai-env/)
    - v8.jsonl training data exported

Usage:
    python scripts/train_grpo.py                          # Full GRPO run
    python scripts/train_grpo.py --test 5                 # Smoke test (5 steps)
    python scripts/train_grpo.py --warm-start loras/v7    # Start from v7 adapter
    python scripts/train_grpo.py --no-unsloth             # Standard TRL path

Architecture:
    - Base: Qwen2.5-Coder-14B-Instruct (4-bit QLoRA via Unsloth)
    - LoRA: r=16, alpha=32 (same as SFT v7)
    - Reward: composite score from code validity + concept coverage + explanation quality
    - Group size: 4 responses per prompt (fits 16GB with Unsloth's 7x context savings)
    - KL penalty: beta=0.1 (prevents reward hacking while allowing improvement)
"""
import faulthandler
import json
import logging
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, "reconfigure") else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, "reconfigure") else None
faulthandler.enable(file=sys.stderr, all_threads=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

TRAINING_JSONL = os.path.join(PROJECT_ROOT, "loras", "training_data", "v8.jsonl")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "loras", "v8-grpo")

# ---------------------------------------------------------------------------
# GRPO Configuration
# ---------------------------------------------------------------------------
MAX_SEQ_LENGTH = 2048
SMOKE_SEQ_LENGTH = 512

LORA_CONFIG = {
    "r": 16,
    "lora_alpha": 32,
    "target_modules": [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    "lora_dropout": 0.0,
    "bias": "none",
    "use_dora": False,
    "use_rslora": True,
}

GRPO_CONFIG = {
    "per_device_train_batch_size": 1,
    "gradient_accumulation_steps": 4,      # Smaller effective batch for GRPO (more updates)
    "num_train_epochs": 1,                 # GRPO is more sample-efficient than SFT
    "learning_rate": 5e-5,                 # Lower LR than SFT (2e-4) — RL is more sensitive
    "warmup_ratio": 0.1,                   # Longer warmup for stability
    "lr_scheduler_type": "cosine",
    "bf16": True,
    "logging_steps": 1,                    # Log every step for GRPO (want to see reward trends)
    "save_steps": 50,
    "weight_decay": 0.01,
    "max_grad_norm": 0.5,                  # Tighter clipping for RL stability
    "seed": 42,
    # GRPO-specific
    "num_generations": 4,                  # Group size: 4 responses per prompt
    "max_completion_length": 1024,         # Max tokens per generated response
    "beta": 0.1,                           # KL penalty (prevents reward hacking)
    "temperature": 0.7,                    # Higher temp for diverse generations
}


# ---------------------------------------------------------------------------
# Reward Function
# ---------------------------------------------------------------------------
def build_reward_functions():
    """Build reward functions for GRPO scoring.

    Returns a list of reward functions, each taking (prompts, completions, **kwargs)
    and returning a list of float rewards.

    Scoring dimensions:
    1. Code presence (0.3): Does the response contain code blocks?
    2. Code structure (0.3): Is the code well-structured (functions, classes, imports)?
    3. Explanation quality (0.2): Does it explain concepts?
    4. Completeness (0.2): Is it a thorough response (length, sections)?
    """

    def reward_code_presence(prompts, completions, **kwargs):
        """Reward for containing code blocks."""
        rewards = []
        for completion in completions:
            text = completion[0]["content"] if isinstance(completion, list) else completion
            # Check for code blocks
            code_blocks = re.findall(r"```[\w]*\n(.*?)```", text, re.DOTALL)
            if code_blocks:
                # More code blocks = better (up to 3)
                score = min(len(code_blocks) / 3.0, 1.0)
                # Bonus for substantial code (not just one-liners)
                total_code_lines = sum(len(b.strip().split("\n")) for b in code_blocks)
                if total_code_lines >= 10:
                    score = min(score + 0.2, 1.0)
            else:
                # Check for inline code patterns
                if re.search(r"(def |class |import |from |fn |func |struct |impl )", text):
                    score = 0.3
                else:
                    score = 0.0
            rewards.append(score)
        return rewards

    def reward_code_structure(prompts, completions, **kwargs):
        """Reward for well-structured code (functions, error handling, types)."""
        rewards = []
        for completion in completions:
            text = completion[0]["content"] if isinstance(completion, list) else completion
            score = 0.0
            checks = [
                (r"\bdef \w+\(", 0.15),         # Python functions
                (r"\bclass \w+", 0.15),          # Classes
                (r"\btry\b.*\bexcept\b", 0.1),   # Error handling
                (r"(->|:\s*\w+)", 0.1),           # Type hints
                (r"\bimport \w+", 0.1),           # Imports
                (r"(fn |func |pub fn)", 0.15),    # Rust/Go functions
                (r"(async |await )", 0.1),         # Async patterns
                (r"#\[|//!|///", 0.05),           # Doc comments
                (r"\btest\b|\bassert\b", 0.1),    # Testing patterns
            ]
            for pattern, weight in checks:
                if re.search(pattern, text, re.DOTALL):
                    score += weight
            rewards.append(min(score, 1.0))
        return rewards

    def reward_explanation(prompts, completions, **kwargs):
        """Reward for explaining concepts (not just code dumps)."""
        rewards = []
        explanation_markers = [
            "because", "this works by", "the key insight", "note that",
            "important", "this approach", "the reason", "under the hood",
            "in practice", "the tradeoff", "complexity", "O(",
            "advantage", "disadvantage", "alternatively", "compared to",
            "step 1", "step 2", "first,", "second,", "finally,",
            "for example", "consider", "notice how", "here we",
        ]
        for completion in completions:
            text = completion[0]["content"] if isinstance(completion, list) else completion
            text_lower = text.lower()
            # Count explanation markers
            marker_count = sum(1 for m in explanation_markers if m in text_lower)
            # Normalize: 5+ markers = full score
            marker_score = min(marker_count / 5.0, 1.0)

            # Prose ratio: good responses mix code and explanation
            lines = text.split("\n")
            prose_lines = [l for l in lines if l.strip() and not l.strip().startswith(("```", "#", "//", "/*", "*"))]
            code_lines = len(lines) - len(prose_lines)
            total = len(lines) or 1
            # Ideal: 40-60% prose
            prose_ratio = len(prose_lines) / total
            ratio_score = 1.0 - abs(prose_ratio - 0.5) * 2  # Peak at 50/50 mix
            ratio_score = max(ratio_score, 0.0)

            rewards.append(marker_score * 0.7 + ratio_score * 0.3)
        return rewards

    def reward_completeness(prompts, completions, **kwargs):
        """Reward for thorough, complete responses."""
        rewards = []
        for completion in completions:
            text = completion[0]["content"] if isinstance(completion, list) else completion
            score = 0.0
            # Length bonus (200-1500 chars is ideal for most coding responses)
            char_count = len(text)
            if char_count < 100:
                score += 0.0
            elif char_count < 500:
                score += 0.3
            elif char_count < 1500:
                score += 0.6
            elif char_count < 3000:
                score += 0.4  # Slightly penalize very long responses
            else:
                score += 0.2  # Heavy penalty for walls of text

            # Structural completeness markers
            if "```" in text:
                score += 0.2  # Has code
            if any(h in text for h in ["##", "**", "###"]):
                score += 0.1  # Has structure/headers
            if re.search(r"(test|assert|expect)", text, re.I):
                score += 0.1  # Mentions testing

            rewards.append(min(score, 1.0))
        return rewards

    return [
        reward_code_presence,
        reward_code_structure,
        reward_explanation,
        reward_completeness,
    ]


# ---------------------------------------------------------------------------
# Prompt Dataset Preparation
# ---------------------------------------------------------------------------
def load_prompts(jsonl_path: str, max_prompts: int = 0):
    """Load prompts from training JSONL for GRPO.

    GRPO only needs the prompts (instructions) — the model generates its own
    responses which get scored by the reward function.
    """
    from hiveai.llm.prompts import CODING_SYSTEM_PROMPT

    prompts = []
    seen = set()
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            instruction = row.get("instruction", "")
            inp = row.get("input", "")

            # Combine instruction + input as the prompt
            prompt = instruction
            if inp:
                prompt = f"{instruction}\n\n{inp}"

            # Deduplicate
            key = prompt[:200]
            if key in seen:
                continue
            seen.add(key)

            # Format as chat messages (Qwen chat template)
            prompts.append([
                {"role": "system", "content": CODING_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])

    if max_prompts > 0:
        prompts = prompts[:max_prompts]

    logger.info(f"Loaded {len(prompts)} unique prompts for GRPO")
    return prompts


# ---------------------------------------------------------------------------
# System Optimizer (reuse from train_v5.py)
# ---------------------------------------------------------------------------
def optimize_system():
    """Pre-model-load optimizations."""
    import psutil

    logger.info("=" * 60)
    logger.info("  System Auto-Optimizer (GRPO)")
    logger.info("=" * 60)

    cpu_count = os.cpu_count() or 4
    ram_total = psutil.virtual_memory().total / (1024**3)
    ram_avail = psutil.virtual_memory().available / (1024**3)
    logger.info(f"  CPU: {cpu_count} cores")
    logger.info(f"  RAM: {ram_total:.1f}GB total, {ram_avail:.1f}GB available")

    # Unload ALL Ollama models to free GPU VRAM
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/ps", method="GET")
        resp = urllib.request.urlopen(req, timeout=3)
        ps_data = json.loads(resp.read().decode())
        for m in ps_data.get("models", []):
            model_name = m.get("name", "")
            if model_name:
                unload_req = urllib.request.Request(
                    "http://localhost:11434/api/generate",
                    data=json.dumps({"model": model_name, "keep_alive": 0}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(unload_req, timeout=5)
                logger.info(f"  Unloaded Ollama model: {model_name}")
    except Exception:
        pass

    # Set process priority
    try:
        p = psutil.Process()
        if sys.platform == "win32":
            p.nice(psutil.HIGH_PRIORITY_CLASS)
        else:
            p.nice(-10)
    except (psutil.AccessDenied, OSError):
        pass

    # PyTorch thread pools
    try:
        import torch
        torch.set_num_threads(min(cpu_count, 8))
        torch.set_num_interop_threads(min(cpu_count // 2, 4))
    except Exception:
        pass

    os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "0")
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF",
                          "expandable_segments:False,"
                          "garbage_collection_threshold:0.6")
    os.environ.setdefault("TORCHINDUCTOR_USE_CUDAGRAPHS", "0")
    os.environ.setdefault("TRITON_CACHE_DIR", os.path.join(PROJECT_ROOT, ".triton_cache"))

    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# GRPO Training
# ---------------------------------------------------------------------------
def train_grpo(model_path: str, max_steps: int = 0, skip_unsloth: bool = False,
               warm_start: str = None, max_prompts: int = 0):
    """Train LoRA via GRPO on Qwen2.5-Coder-14B-Instruct."""
    import torch

    # --- Load model ---
    FastLanguageModel = None
    if not skip_unsloth:
        try:
            from unsloth import FastLanguageModel as _FLM
            FastLanguageModel = _FLM
            logger.info("Unsloth imported (patches applied)")
        except ImportError:
            logger.warning("Unsloth not installed — using standard path")

    seq_length = SMOKE_SEQ_LENGTH if max_steps > 0 else MAX_SEQ_LENGTH

    load_start = time.time()
    use_unsloth = False

    if FastLanguageModel is not None and not skip_unsloth:
        try:
            if warm_start and os.path.isdir(warm_start):
                load_name = warm_start
                logger.info(f"WARM START from {warm_start}")
            elif os.path.isdir(model_path) and os.path.exists(os.path.join(model_path, "config.json")):
                load_name = model_path
            else:
                load_name = "unsloth/Qwen2.5-Coder-14B-Instruct-bnb-4bit"

            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=load_name,
                max_seq_length=seq_length,
                dtype=None,
                load_in_4bit=True,
            )
            use_unsloth = True
            logger.info(f"Model loaded via Unsloth in {time.time() - load_start:.0f}s")
        except Exception as e:
            logger.warning(f"Unsloth failed ({e}), falling back to standard")
            torch.cuda.empty_cache()
            import gc; gc.collect()
            skip_unsloth = True

    if skip_unsloth or not use_unsloth:
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        load_path = model_path if os.path.isdir(model_path) else "Qwen/Qwen2.5-Coder-14B-Instruct"
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
        tokenizer = AutoTokenizer.from_pretrained(load_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            load_path,
            quantization_config=bnb_config,
            device_map={"": 0},
            torch_dtype=torch.bfloat16,
            trust_remote_code=True,
        )

    # --- Apply LoRA ---
    if use_unsloth:
        model = FastLanguageModel.get_peft_model(
            model,
            r=LORA_CONFIG["r"],
            lora_alpha=LORA_CONFIG["lora_alpha"],
            target_modules=LORA_CONFIG["target_modules"],
            lora_dropout=LORA_CONFIG["lora_dropout"],
            bias=LORA_CONFIG["bias"],
            use_rslora=LORA_CONFIG["use_rslora"],
        )
    else:
        from peft import LoraConfig, TaskType, get_peft_model
        lora_cfg = LoraConfig(
            r=LORA_CONFIG["r"],
            lora_alpha=LORA_CONFIG["lora_alpha"],
            target_modules=LORA_CONFIG["target_modules"],
            lora_dropout=LORA_CONFIG["lora_dropout"],
            bias=LORA_CONFIG["bias"],
            use_rslora=LORA_CONFIG["use_rslora"],
            task_type=TaskType.CAUSAL_LM,
        )
        model = get_peft_model(model, lora_cfg)

    # Post-load CUDA optimizations
    if torch.cuda.is_available():
        cap = torch.cuda.get_device_capability(0)
        if cap[0] >= 8:
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
        vram = torch.cuda.memory_allocated() / 1e9
        logger.info(f"VRAM after model load: {vram:.1f}GB")

    # --- Load prompts ---
    prompts = load_prompts(TRAINING_JSONL, max_prompts=max_prompts)

    # Convert to dataset format expected by GRPOTrainer
    from datasets import Dataset
    dataset = Dataset.from_list([{"prompt": p} for p in prompts])

    # --- Build reward functions ---
    reward_fns = build_reward_functions()
    logger.info(f"Reward functions: {len(reward_fns)} "
                f"({', '.join(f.__name__ for f in reward_fns)})")

    # --- Configure GRPO ---
    from trl import GRPOConfig, GRPOTrainer

    grpo_config = GRPOConfig(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=GRPO_CONFIG["per_device_train_batch_size"],
        gradient_accumulation_steps=GRPO_CONFIG["gradient_accumulation_steps"],
        num_train_epochs=GRPO_CONFIG["num_train_epochs"],
        learning_rate=GRPO_CONFIG["learning_rate"],
        warmup_ratio=GRPO_CONFIG["warmup_ratio"],
        lr_scheduler_type=GRPO_CONFIG["lr_scheduler_type"],
        bf16=GRPO_CONFIG["bf16"],
        logging_steps=GRPO_CONFIG["logging_steps"],
        save_steps=GRPO_CONFIG["save_steps"],
        weight_decay=GRPO_CONFIG["weight_decay"],
        max_grad_norm=GRPO_CONFIG["max_grad_norm"],
        seed=GRPO_CONFIG["seed"],
        # GRPO-specific
        num_generations=GRPO_CONFIG["num_generations"],
        max_completion_length=GRPO_CONFIG["max_completion_length"],
        beta=GRPO_CONFIG["beta"],
        temperature=GRPO_CONFIG["temperature"],
        # Logging
        report_to="none",
        # Max steps override for smoke tests
        max_steps=max_steps if max_steps > 0 else -1,
    )

    # --- Train ---
    logger.info("=" * 60)
    logger.info("  HiveAI GRPO Training — Qwen2.5-Coder-14B")
    logger.info("=" * 60)
    logger.info(f"  Base model:     {model_path}")
    logger.info(f"  Prompts:        {len(prompts)}")
    logger.info(f"  Group size:     {GRPO_CONFIG['num_generations']} responses/prompt")
    logger.info(f"  KL beta:        {GRPO_CONFIG['beta']}")
    logger.info(f"  Temperature:    {GRPO_CONFIG['temperature']}")
    logger.info(f"  Max completion: {GRPO_CONFIG['max_completion_length']} tokens")
    logger.info(f"  LR:             {GRPO_CONFIG['learning_rate']}")
    logger.info(f"  Output:         {OUTPUT_DIR}")
    if max_steps:
        logger.info(f"  TEST MODE:      {max_steps} steps")
    logger.info("=" * 60)

    trainer = GRPOTrainer(
        model=model,
        processing_class=tokenizer,
        reward_funcs=reward_fns,
        args=grpo_config,
        train_dataset=dataset,
    )

    train_start = time.time()
    trainer.train()
    elapsed = time.time() - train_start
    logger.info(f"GRPO training complete in {elapsed / 3600:.1f}h")

    # --- Save ---
    logger.info(f"Saving adapter to {OUTPUT_DIR}")
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    # Save training metadata
    meta = {
        "training_type": "GRPO",
        "base_model": model_path,
        "lora_config": LORA_CONFIG,
        "grpo_config": GRPO_CONFIG,
        "num_prompts": len(prompts),
        "elapsed_hours": round(elapsed / 3600, 2),
        "reward_functions": [f.__name__ for f in reward_fns],
        "warm_start": warm_start,
    }
    meta_path = os.path.join(OUTPUT_DIR, "training_meta.json")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    logger.info(f"Training metadata saved to {meta_path}")

    logger.info("=" * 60)
    logger.info("  GRPO TRAINING COMPLETE")
    logger.info(f"  Adapter: {OUTPUT_DIR}")
    logger.info(f"  Next: convert to GGUF and evaluate")
    logger.info(f"    python convert_lora_to_gguf.py --base <hf_model> {OUTPUT_DIR} --outfile hiveai-v8-grpo.gguf")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Train HiveAI via GRPO (reinforcement learning)")
    parser.add_argument("--test", type=int, default=0,
                        help="Smoke test: stop after N steps")
    parser.add_argument("--no-unsloth", action="store_true",
                        help="Skip Unsloth (standard transformers path)")
    parser.add_argument("--model", type=str, default=None,
                        help="Override base model path")
    parser.add_argument("--warm-start", type=str, default=None,
                        help="Continue from existing adapter (e.g., loras/v7)")
    parser.add_argument("--data", type=str, default=None,
                        help="Override training data JSONL path")
    parser.add_argument("--max-prompts", type=int, default=0,
                        help="Limit number of prompts (0=all)")
    args = parser.parse_args()

    BASE_MODEL = os.path.join(PROJECT_ROOT, "models", "qwen2.5-coder-14b")
    model_path = args.model or BASE_MODEL

    if args.data:
        TRAINING_JSONL = os.path.abspath(args.data)

    if not os.path.exists(TRAINING_JSONL):
        logger.error(f"Training data not found: {TRAINING_JSONL}")
        logger.error("Run: python scripts/prepare_v5_data.py --export")
        sys.exit(1)

    if args.test and not args.no_unsloth:
        # Auto-skip Unsloth in test mode (Triton JIT takes 15+ min)
        args.no_unsloth = True
        logger.info("Test mode: auto-skipping Unsloth")

    optimize_system()
    train_grpo(model_path, max_steps=args.test, skip_unsloth=args.no_unsloth,
               warm_start=args.warm_start, max_prompts=args.max_prompts)
