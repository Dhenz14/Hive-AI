"""
Train HiveAI LoRA v7 on Qwen2.5-Coder-14B-Instruct (QLoRA via Unsloth).

One-command training:
    python scripts/train_v5.py
    python scripts/train_v5.py --test 5    # smoke test (5 steps)
    python scripts/train_v5.py --no-kl     # disable KL anchoring

What's new in v7 (fixes from v6 overfitting analysis):
    - Response-only loss masking (assistant_only_loss) — no more training on prompts
    - LoRA r=16 (was 32), alpha=32, dropout=0.1 (was 0.0), RSLoRA enabled
    - 2 epochs (was 3) — v6 overfitted past epoch 2 (loss 0.51 but eval unchanged)
    - Packing disabled — required for correct loss masking
    - KL regularization ON by default (lambda=0.3)
    - 5,998 training pairs from 1,156 batch files, quality-filtered
"""
import faulthandler
import json
import logging
import os
import subprocess
import sys
import threading
import time

sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, "reconfigure") else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, "reconfigure") else None
faulthandler.enable(file=sys.stderr, all_threads=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logging.getLogger("transformers").setLevel(logging.INFO)
logging.getLogger("trl").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

TRAINING_JSONL = os.path.join(PROJECT_ROOT, "loras", "training_data", "v7.jsonl")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "loras", "v7")

# Qwen2.5-Coder-14B-Instruct — code-specialized, text-only, standard architecture.
# QLoRA via Unsloth: 4-bit base (~8-9GB) + bf16 LoRA adapters (~0.5GB) = fits 16GB.
BASE_MODEL = os.path.join(PROJECT_ROOT, "models", "qwen2.5-coder-14b")

# ---------------------------------------------------------------------------
# v7 Training Configuration — Qwen2.5-Coder-14B QLoRA
# ---------------------------------------------------------------------------
# Changes from v6: r=16 (was 32), dropout=0.1 (was 0.0), rslora=True,
# 2 epochs (was 3), response-only loss masking (was full-sequence loss).
MAX_SEQ_LENGTH = 2048     # 2048 fits reliably on 16GB; v6 hit VRAM ceiling at 4096
SMOKE_SEQ_LENGTH = 512    # Shorter for smoke tests — catches same shape/VRAM errors 4x faster

LORA_CONFIG = {
    "r": 16,                          # r=16 — standard for QLoRA (r=32 was overparameterized for our data)
    "lora_alpha": 32,                 # 2x rank for stable scaling
    "target_modules": [
        "q_proj", "k_proj", "v_proj", "o_proj",   # attention
        "gate_proj", "up_proj", "down_proj",        # MLP layers
    ],
    "lora_dropout": 0.1,             # Regularization — prevents adapter memorization (was 0.0)
    "bias": "none",
    "use_dora": True,                 # DoRA: weight-decomposed LoRA (+1-4% over standard LoRA, PEFT 0.18+)
    "use_rslora": True,               # Rank-stabilized LoRA — better scaling at any rank
}

TRAINING_CONFIG = {
    "per_device_train_batch_size": 1,      # batch=1 for 14B on 16GB (fused CE needs VRAM headroom)
    "gradient_accumulation_steps": 16,     # Effective batch = 16
    "num_train_epochs": 2,                 # 2 epochs — v6 overfitted at 3 (loss 0.51 but eval unchanged)
    "learning_rate": 2e-4,                 # Standard for QLoRA fine-tuning
    "warmup_ratio": 0.05,                  # 5% warmup — ensures model sees multiple curriculum phases before full LR
    "lr_scheduler_type": "cosine",
    "bf16": True,
    "logging_steps": 5,
    "save_steps": 100,
    "weight_decay": 0.01,
    "max_grad_norm": 1.0,
    "seed": 42,
    "neftune_noise_alpha": 5.0,            # NEFTune: +0.5-1% quality, zero cost
}

# KL-Anchored SFT — prevents catastrophic forgetting
KL_CONFIG = {
    "lambda": 0.3,        # KL weight in loss (30% regularization to prevent catastrophic forgetting)
    "temperature": 1.0,   # Softmax temperature
    "seq_limit": 512,     # Max tokens for KL (safe with cut_cross_entropy on 14B)
}


# ---------------------------------------------------------------------------
# System Optimizer (from train_v3.py — hardware auto-detection)
# ---------------------------------------------------------------------------
def optimize_system_pre_load():
    """Pre-model-load optimizations. CRITICAL: Do NOT call torch.cuda.get_device_*()
    here — initializing the CUDA primary context before BnB model loading causes
    'CUDA driver error: out of memory' on WSL2/16GB GPUs."""
    import psutil

    logger.info("=" * 60)
    logger.info("  System Auto-Optimizer (pre-load)")
    logger.info("=" * 60)
    optimizations = []

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
                optimizations.append(f"unloaded {model_name}")
    except Exception:
        pass

    # Set process priority
    try:
        p = psutil.Process()
        if sys.platform == "win32":
            p.nice(psutil.HIGH_PRIORITY_CLASS)
        else:
            p.nice(-10)
        optimizations.append("priority elevated")
    except (psutil.AccessDenied, OSError):
        pass

    # PyTorch thread pools (does NOT init CUDA)
    try:
        import torch
        torch.set_num_threads(min(cpu_count, 8))
        torch.set_num_interop_threads(min(cpu_count // 2, 4))
        optimizations.append("threads tuned")
    except Exception:
        pass

    # Env vars only — no CUDA context init
    os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "0")
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF",
                          "expandable_segments:False,"
                          "garbage_collection_threshold:0.6")
    optimizations.append("CUDA env vars set")

    # Check for available VRAM optimizations (import only, no CUDA init)
    try:
        import flash_attn  # noqa: F401
        optimizations.append(f"flash_attn v{flash_attn.__version__} (O(seq) attention memory)")
    except ImportError:
        logger.warning("  flash-attn NOT installed — attention uses O(seq²) memory")

    try:
        import cut_cross_entropy  # noqa: F401
        os.environ["CUT_CROSS_ENTROPY"] = "1"
        optimizations.append(f"cut_cross_entropy v{cut_cross_entropy.__version__} (logits tensor eliminated)")
    except ImportError:
        logger.warning("  cut_cross_entropy NOT installed — 248K vocab will materialize ~1GB logits")

    import gc
    gc.set_threshold(700, 10, 5)

    logger.info(f"  Applied: {', '.join(optimizations)}")
    logger.info("=" * 60)
    return optimizations


def optimize_system_post_load():
    """Post-model-load CUDA optimizations. Safe to call after BnB quantization."""
    import torch
    optimizations = []

    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        vram_total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        capability = torch.cuda.get_device_capability(0)
        logger.info(f"  GPU: {gpu_name} ({vram_total:.1f}GB VRAM, "
                    f"compute {capability[0]}.{capability[1]})")

        if capability[0] >= 8:
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            torch.set_float32_matmul_precision("high")
            optimizations.append("TF32 enabled")
        if hasattr(torch.backends.cuda, "flash_sdp_enabled"):
            torch.backends.cuda.enable_flash_sdp(True)
            torch.backends.cuda.enable_mem_efficient_sdp(True)
            optimizations.append("Flash SDP enabled")

    if optimizations:
        logger.info(f"  Post-load: {', '.join(optimizations)}")


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def train_v5(model_path: str, max_steps: int = 0, use_kl: bool = True,
             skip_unsloth: bool = False, step_timeout: int = 0,
             seq_length_override: int = 0, warm_start: str = None):
    """Train LoRA v7 on Qwen2.5-Coder-14B-Instruct (QLoRA via Unsloth)."""
    import torch
    import torch.nn.functional as F

    # CRITICAL: Disable CUDA graphs before any torch.compile call.
    # BnB 4-bit dequantization creates temporary tensors with non-deterministic
    # lifetimes, which breaks CUDA graph recording/replay.
    os.environ.setdefault("TORCHINDUCTOR_USE_CUDAGRAPHS", "0")

    # Persist Triton compilation cache so Unsloth kernels don't recompile every run
    os.environ.setdefault("TRITON_CACHE_DIR", os.path.join(PROJECT_ROOT, ".triton_cache"))

    # CRITICAL: Import Unsloth BEFORE transformers/peft/trl!
    # Unsloth patches these libraries for 2x speed + 70% less VRAM.
    # Importing them first means patches don't apply → OOM on model loading.
    FastLanguageModel = None
    if not skip_unsloth:
        try:
            from unsloth import FastLanguageModel as _FLM
            FastLanguageModel = _FLM
            logger.info("Unsloth imported first (patches applied to transformers/peft/trl)")
        except ImportError:
            logger.warning("Unsloth not installed — using standard transformers path")

    # --- Sequence length selection ---
    # 248K vocab makes logits massive, but cut_cross_entropy + tiled MLP eliminate
    # the bottleneck. seq=2048 now fits on 16GB with these optimizations.
    if seq_length_override > 0:
        seq_length = seq_length_override
        logger.info(f"Sequence length: {seq_length} (--seq-length override)")
    elif max_steps > 0:
        seq_length = SMOKE_SEQ_LENGTH
        logger.info(f"Smoke test: seq_length={seq_length} (reduced from {MAX_SEQ_LENGTH})")
    else:
        seq_length = MAX_SEQ_LENGTH  # 2048: FA2 + CCE + tiled MLP fit on 16GB
        logger.info(f"Sequence length: {seq_length}")

    if step_timeout <= 0:
        if max_steps > 0:
            step_timeout = 300  # 5 min per step default in test mode
        else:
            step_timeout = 200  # Full run: catch VRAM spillover early (normal ~70s/step)

    # Now safe to import transformers/peft (Unsloth patches already applied)
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import LoraConfig, TaskType, get_peft_model
    from datasets import load_dataset
    # NOTE: SFTTrainer/SFTConfig imported AFTER model loads (see below).
    # TRL's SFTTrainer.__init__ isinstance() check compares against the *patched*
    # class, so a pre-patch SFTConfig instance fails.
    from transformers import TrainerCallback
    import psutil

    from hiveai.llm.prompts import CODING_SYSTEM_PROMPT

    logger.info("=" * 60)
    logger.info("  HiveAI LoRA v7 Training — Qwen2.5-Coder-14B QLoRA")
    logger.info("=" * 60)
    logger.info(f"  Base model:  {model_path}")
    logger.info(f"  Data:        {TRAINING_JSONL}")
    logger.info(f"  Output:      {OUTPUT_DIR}")
    logger.info(f"  LoRA:        r={LORA_CONFIG['r']}, alpha={LORA_CONFIG['lora_alpha']}, "
                f"DoRA={LORA_CONFIG.get('use_dora')}, "
                f"modules={LORA_CONFIG['target_modules']}")
    eff_batch = (TRAINING_CONFIG["per_device_train_batch_size"]
                 * TRAINING_CONFIG["gradient_accumulation_steps"])
    logger.info(f"  Training:    batch={TRAINING_CONFIG['per_device_train_batch_size']}x"
                f"{TRAINING_CONFIG['gradient_accumulation_steps']}="
                f"{eff_batch} effective, "
                f"epochs={TRAINING_CONFIG['num_train_epochs']}, "
                f"lr={TRAINING_CONFIG['learning_rate']}")
    logger.info(f"  Context:     {seq_length} tokens")
    logger.info(f"  NEFTune:     alpha={TRAINING_CONFIG['neftune_noise_alpha']}")
    logger.info(f"  KL anchor:   {'ON' if use_kl else 'OFF'} "
                f"(lambda={KL_CONFIG['lambda']}, seq_limit={KL_CONFIG['seq_limit']})")
    logger.info(f"  Architecture: DENSE 14B, QLoRA 4-bit base + bf16 adapters")
    if max_steps:
        logger.info(f"  TEST MODE:   stopping after {max_steps} steps")
    logger.info("=" * 60)

    # Count pairs
    with open(TRAINING_JSONL, "r", encoding="utf-8") as f:
        pair_count = sum(1 for line in f if line.strip())
    logger.info(f"Training pairs: {pair_count}")

    total_steps = (pair_count * TRAINING_CONFIG["num_train_epochs"]) // eff_batch
    logger.info(f"Expected steps: ~{total_steps}")

    # ── Load model — try Unsloth first (2x faster), fallback to standard ──
    use_unsloth = False
    load_start = time.time()

    def _load_with_unsloth():
        nonlocal use_unsloth
        logger.info("Using Unsloth FastLanguageModel for 2x speed + 70% less VRAM")

        if warm_start and os.path.isdir(warm_start):
            # Warm start: load base + existing adapter from previous training
            unsloth_model_name = warm_start
            logger.info(f"  WARM START: loading base + adapter from {warm_start}")
        elif os.path.isdir(model_path) and os.path.exists(os.path.join(model_path, "config.json")):
            unsloth_model_name = model_path
            logger.info(f"  Using local weights: {unsloth_model_name}")
        else:
            # Use Unsloth's pre-quantized 4-bit model — much smaller download (~8GB vs 28GB)
            unsloth_model_name = "unsloth/Qwen2.5-Coder-14B-Instruct-bnb-4bit"
            logger.info(f"  Using Unsloth pre-quantized 4-bit model: {unsloth_model_name}")

        _model, _tokenizer = FastLanguageModel.from_pretrained(
            model_name=unsloth_model_name,
            max_seq_length=seq_length,
            dtype=None,          # Let Unsloth auto-detect optimal dtype
            load_in_4bit=True,   # QLoRA: 4-bit base + bf16 LoRA = ~10GB on 16GB card
        )
        use_unsloth = True
        logger.info(f"Model loaded via Unsloth in {time.time() - load_start:.0f}s")
        return _model, _tokenizer

    def _load_standard():
        load_path = model_path
        if not os.path.isdir(model_path) or not os.path.exists(os.path.join(model_path, "config.json")):
            load_path = "Qwen/Qwen2.5-Coder-14B-Instruct"
            logger.info(f"  Local path not found, using HF model: {load_path}")

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
        logger.info(f"Loading tokenizer from {load_path}...")
        _tokenizer = AutoTokenizer.from_pretrained(load_path, trust_remote_code=True)
        logger.info(f"Loading Qwen2.5-Coder-14B in 4-bit QLoRA (~8-9GB VRAM)...")
        # Use flash_attention_2 if available (standard attention, no hybrid issues)
        attn_impl = "eager"
        try:
            import flash_attn  # noqa: F401
            attn_impl = "flash_attention_2"
        except ImportError:
            pass
        _model = AutoModelForCausalLM.from_pretrained(
            load_path,
            quantization_config=bnb_config,
            device_map={"": 0},
            torch_dtype=torch.bfloat16,
            trust_remote_code=True,
            attn_implementation=attn_impl,
        )
        logger.info(f"Model loaded via standard transformers in {time.time() - load_start:.0f}s")
        return _model, _tokenizer

    if skip_unsloth or FastLanguageModel is None:
        logger.info("Unsloth SKIPPED — using standard transformers+PEFT path")
        model, tokenizer = _load_standard()
    else:
        try:
            model, tokenizer = _load_with_unsloth()
        except Exception as e:
            logger.warning(f"Unsloth loading failed ({e}), falling back to standard transformers+PEFT")
            # Clean up any partial CUDA allocations from failed Unsloth load
            torch.cuda.empty_cache()
            import gc; gc.collect()
            model, tokenizer = _load_standard()

    # Import TRL — AFTER Unsloth loads (if used) to get patched classes
    from trl import SFTTrainer, SFTConfig  # noqa: E402

    # Now safe to init CUDA context (model already loaded + quantized)
    optimize_system_post_load()

    vram_alloc = torch.cuda.memory_allocated() / 1e9
    vram_reserved = torch.cuda.memory_reserved() / 1e9
    logger.info(f"VRAM: {vram_alloc:.1f}GB allocated, {vram_reserved:.1f}GB reserved")

    # Verify no meta-device params
    meta_params = [(n, p) for n, p in model.named_parameters() if p.device.type == "meta"]
    if meta_params:
        logger.error(f"BLOCKER: {len(meta_params)} parameters still on meta device!")
        for n, p in meta_params[:10]:
            logger.error(f"  meta: {n} shape={tuple(p.shape)}")
        sys.exit(1)
    logger.info("All parameters materialized (no meta-device params)")

    # Count quantized modules
    n_quantized = sum(1 for _, m in model.named_modules()
                      if hasattr(m, "weight") and hasattr(m.weight, "quant_state"))
    logger.info(f"Quantized modules: {n_quantized} Linear4bit")

    # ── Apply LoRA + Freeze base + gradient checkpointing ──
    if use_unsloth and warm_start:
        # Warm start: adapter already loaded by from_pretrained, just enable training
        from unsloth import FastLanguageModel as _FLM
        _FLM.for_training(model)
        logger.info("WARM START: adapter already loaded, enabled training mode + gradient checkpointing")
    elif use_unsloth:
        # Unsloth handles LoRA application, freezing, and gradient checkpointing
        model = FastLanguageModel.get_peft_model(
            model,
            r=LORA_CONFIG["r"],
            lora_alpha=LORA_CONFIG["lora_alpha"],
            target_modules=LORA_CONFIG["target_modules"],
            lora_dropout=LORA_CONFIG["lora_dropout"],
            bias=LORA_CONFIG["bias"],
            use_gradient_checkpointing="unsloth",  # Unsloth's optimized version (2x faster)
            use_rslora=LORA_CONFIG.get("use_rslora", True),
            use_dora=LORA_CONFIG["use_dora"],
        )
        logger.info("LoRA applied via Unsloth (optimized gradient checkpointing)")
    else:
        # Standard PEFT path
        for param in model.parameters():
            param.requires_grad = False

        if hasattr(model, "enable_input_require_grads"):
            model.enable_input_require_grads()
        else:
            def _make_inputs_require_grad(module, input, output):
                output.requires_grad_(True)
            model.get_input_embeddings().register_forward_hook(_make_inputs_require_grad)

        model.gradient_checkpointing_enable(
            gradient_checkpointing_kwargs={
                "use_reentrant": False,
                "preserve_rng_state": False,
            }
        )
        logger.info("Gradient checkpointing enabled")

        lora_config = LoraConfig(
            r=LORA_CONFIG["r"],
            lora_alpha=LORA_CONFIG["lora_alpha"],
            target_modules=LORA_CONFIG["target_modules"],
            lora_dropout=LORA_CONFIG["lora_dropout"],
            bias=LORA_CONFIG["bias"],
            task_type=TaskType.CAUSAL_LM,
            use_dora=LORA_CONFIG["use_dora"],
        )
        model = get_peft_model(model, lora_config)

    model.print_trainable_parameters()

    # Cast LoRA adapter weights to bf16 (if not already done by Unsloth)
    if not use_unsloth:
        n_cast = 0
        for name, param in model.named_parameters():
            if param.requires_grad and param.dtype == torch.float32:
                param.data = param.data.to(torch.bfloat16)
                n_cast += 1
        if n_cast:
            logger.info(f"Cast {n_cast} LoRA adapter params float32 -> bf16")

    # ── torch.compile ──
    # DISABLED for all paths:
    # - Unsloth: uses own Triton kernels (torch.compile is redundant)
    # - Standard + BnB 4-bit: transformers 5.2.0 raises ValueError
    #   "You cannot fine-tune quantized model with torch.compile()"
    # - BnB dequantization + CUDA graphs = crash (tensor lifetime mismatch)
    if use_unsloth:
        logger.info("torch.compile: skipped (Unsloth provides its own Triton kernels)")
    else:
        logger.info("torch.compile: skipped (BnB 4-bit incompatible with torch.compile in transformers 5.2.0)")

    # ── Defragment VRAM before training ──
    # Model loading + LoRA setup creates fragmentation; clean up before training starts
    import gc
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    vram_alloc = torch.cuda.memory_allocated() / 1e9
    vram_reserved = torch.cuda.memory_reserved() / 1e9
    logger.info(f"VRAM after cleanup: {vram_alloc:.1f}GB allocated, {vram_reserved:.1f}GB reserved")

    # ── Load and format dataset ──
    dataset = load_dataset("json", data_files=TRAINING_JSONL, split="train")
    logger.info(f"EOS token: '{tokenizer.eos_token}' (id={tokenizer.eos_token_id})")

    def format_to_messages(examples):
        """Convert instruction/output pairs to messages format for assistant-only loss.

        Returns a 'messages' column (list of message dicts) instead of pre-formatted text.
        SFTTrainer applies the chat template and masks non-assistant tokens from loss.
        """
        all_messages = []
        n_truncated = 0
        for inst, inp, out in zip(
            examples["instruction"], examples["input"], examples["output"]
        ):
            user_content = inst
            if inp:
                user_content += "\n" + inp

            messages = [
                {"role": "system", "content": CODING_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": out},
            ]

            # Truncate long responses to fit seq_length
            try:
                text = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=False
                )
            except Exception:
                text = f"system\n{CODING_SYSTEM_PROMPT}\nuser\n{user_content}\nassistant\n{out}"

            n_tokens = len(tokenizer.encode(text))
            if n_tokens > seq_length:
                overhead_messages = [
                    {"role": "system", "content": CODING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": ""},
                ]
                try:
                    overhead_text = tokenizer.apply_chat_template(
                        overhead_messages, tokenize=False, add_generation_prompt=False
                    )
                    overhead_tokens = len(tokenizer.encode(overhead_text))
                except Exception:
                    overhead_tokens = n_tokens - len(tokenizer.encode(out))

                budget = seq_length - overhead_tokens - 1
                out_tokens = tokenizer.encode(out, add_special_tokens=False)[:budget]
                truncated_out = tokenizer.decode(out_tokens, skip_special_tokens=False)
                messages[-1]["content"] = truncated_out
                n_truncated += 1

            all_messages.append(messages)

        if n_truncated > 0:
            logger.info(f"  format_to_messages: truncated {n_truncated}/{len(all_messages)} "
                        f"to fit {seq_length} tokens")
        return {"messages": all_messages}

    dataset = dataset.map(format_to_messages, batched=True,
                          remove_columns=dataset.column_names)

    # Trim dataset for smoke tests — no point tokenizing 2500+ pairs for 3 steps
    if max_steps > 0:
        batch_size_est = TRAINING_CONFIG["per_device_train_batch_size"]
        grad_accum_est = TRAINING_CONFIG["gradient_accumulation_steps"]
        needed = batch_size_est * grad_accum_est * max_steps * 2  # 2x safety
        needed = max(needed, 64)  # minimum 64 samples
        if len(dataset) > needed:
            dataset = dataset.select(range(needed))
            logger.info(f"Smoke test: trimmed dataset to {len(dataset)} samples "
                        f"(from {pair_count})")

    # Split 5% for validation (early stopping)
    eval_dataset = None
    if len(dataset) > 200:
        split = dataset.train_test_split(test_size=0.05, seed=42)
        dataset = split["train"]
        eval_dataset = split["test"]
        logger.info(f"Validation split: {len(dataset)} train, {len(eval_dataset)} eval")

    logger.info(f"Dataset ready: {len(dataset)} examples")

    sample_msgs = dataset[0]["messages"]
    sample_text = tokenizer.apply_chat_template(sample_msgs, tokenize=False, add_generation_prompt=False)
    sample_len = len(tokenizer.encode(sample_text))
    ends_with_eos = sample_text.rstrip().endswith("<|im_end|>")
    logger.info(f"Sample: {sample_len} tokens, {len(sample_msgs)} messages, ends_with_EOS={ends_with_eos}")
    logger.info(f"  System: {sample_msgs[0]['content'][:80]}...")
    logger.info(f"  User: {sample_msgs[1]['content'][:80]}...")
    logger.info(f"  Assistant: {sample_msgs[2]['content'][:80]}...")

    # ── KL-Anchored Loss Setup ──
    # Chunked approach: backbone(full seq) → lm_head(kl_slice positions only)
    # Peak logit VRAM = kl_slice × 248K × 2 bytes = ~240MB (not 970MB for full seq).
    # Compatible with CCE: we never rely on outputs.logits from the SFT pass.
    # k3 estimator: (r-1) - log(r), same as GRPO. O(seq_len) not O(seq×vocab).
    kl_state = {"disabled": False, "last_kl": 0.0, "last_sft": 0.0}
    _original_compute_loss = SFTTrainer.compute_loss

    def _chunked_log_probs(model_arg, inputs, label_slice, kl_slice, with_grad):
        """
        Get per-token log-probs for last kl_slice positions WITHOUT materializing
        the full seq×vocab logit tensor.

        Strategy: run backbone (Qwen2ForModel) over full seq for correct attention
        context, then apply lm_head only to the last kl_slice hidden states.
        Peak logit tensor: kl_slice × vocab × 2 bytes ≈ 240MB (vs 970MB for full seq).

        Works with CCE (we never touch outputs.logits from the SFT pass).
        Works with PEFT/LoRA/Unsloth: disable_adapter_layers() gates all adapters.
        """
        # Navigate to backbone and lm_head under PEFT wrapper.
        # PEFT layout: PeftModel → .base_model (LoraModel) → .model (Qwen2ForCausalLM)
        #              Qwen2ForCausalLM → .model (Qwen2Model backbone) + .lm_head
        try:
            causal_lm = model_arg.base_model.model   # Qwen2ForCausalLM
            backbone = causal_lm.model               # Qwen2Model
            lm_head = causal_lm.lm_head
        except AttributeError:
            backbone = model_arg.model               # Non-PEFT fallback
            lm_head = model_arg.lm_head

        ctx = torch.enable_grad() if with_grad else torch.no_grad()
        with ctx:
            hidden_out = backbone(
                input_ids=inputs.get("input_ids"),
                attention_mask=inputs.get("attention_mask"),
                use_cache=False,
            )
            # Slice BEFORE lm_head: kl_slice × 4096 → kl_slice × 248K
            hidden_slice = hidden_out.last_hidden_state[:, -kl_slice:, :].contiguous()
            del hidden_out

            logits_slice = lm_head(hidden_slice)   # [B, kl_slice, vocab] ~240MB
            del hidden_slice

            lse = torch.logsumexp(logits_slice, dim=-1)
            sel = torch.gather(
                logits_slice, dim=-1, index=label_slice.unsqueeze(-1)
            ).squeeze(-1)
            log_prob = sel - lse
            del logits_slice, lse, sel

        return log_prob

    def compute_loss_with_kl(self_trainer, model_arg, inputs,
                              return_outputs=False, num_items_in_batch=None, **kwargs):
        import gc
        parent_kwargs = {}
        if num_items_in_batch is not None:
            parent_kwargs["num_items_in_batch"] = num_items_in_batch

        # Phase 1: Normal SFT forward pass (CCE — no logits materialized)
        result = _original_compute_loss(
            self_trainer, model_arg, inputs,
            return_outputs=True, **parent_kwargs, **kwargs,
        )
        if isinstance(result, tuple):
            sft_loss, outputs = result
        else:
            sft_loss = result
            outputs = None

        kl_loss_val = 0.0
        if use_kl and KL_CONFIG["lambda"] > 0 and not kl_state["disabled"]:
            labels = inputs.get("labels", inputs.get("input_ids"))
            kl_slice = min(labels.shape[1], KL_CONFIG["seq_limit"])
            label_slice = labels[:, -kl_slice:].clone()
            ignore_mask = label_slice < 0
            label_slice[ignore_mask] = 0

            try:
                gc.collect()
                torch.cuda.empty_cache()

                # Phase 2a: Tuned log-probs via chunked backbone+lm_head
                # (adapters ON, with_grad=True so KL loss flows into LoRA grads)
                tuned_log_prob = _chunked_log_probs(
                    model_arg, inputs, label_slice, kl_slice, with_grad=True
                )
                torch.cuda.empty_cache()

                # Phase 2b: Reference log-probs (adapters OFF, no_grad)
                model_arg.disable_adapter_layers()
                try:
                    ref_log_prob = _chunked_log_probs(
                        model_arg, inputs, label_slice, kl_slice, with_grad=False
                    )
                finally:
                    model_arg.enable_adapter_layers()
                torch.cuda.empty_cache()

                # Phase 3: k3 KL estimator — O(seq_len) memory, not O(seq×vocab)
                log_ratio = tuned_log_prob - ref_log_prob.detach()
                ratio = torch.exp(log_ratio)
                kl_per_token = (ratio - 1) - log_ratio
                kl_per_token[ignore_mask] = 0.0
                n_valid = (~ignore_mask).sum().clamp(min=1)
                kl_loss = kl_per_token.sum() / n_valid

                kl_loss_val = kl_loss.item()
                sft_loss = sft_loss + KL_CONFIG["lambda"] * kl_loss

                del tuned_log_prob, ref_log_prob, log_ratio, ratio, kl_per_token
                torch.cuda.empty_cache()

            except torch.cuda.OutOfMemoryError:
                model_arg.enable_adapter_layers()
                torch.cuda.empty_cache()
                if not kl_state["disabled"]:
                    logger.warning("KL chunked OOM — disabling for rest of training")
                    kl_state["disabled"] = True
            except Exception as e:
                model_arg.enable_adapter_layers()
                torch.cuda.empty_cache()
                if not kl_state["disabled"]:
                    logger.warning(f"KL chunked error ({type(e).__name__}: {e}) — disabling")
                    kl_state["disabled"] = True

        kl_state["last_kl"] = kl_loss_val
        kl_state["last_sft"] = (sft_loss.item() - KL_CONFIG["lambda"] * kl_loss_val
                                 if kl_loss_val else sft_loss.item())

        if return_outputs:
            return sft_loss, outputs
        return sft_loss

    if use_kl:
        SFTTrainer.compute_loss = compute_loss_with_kl

    # ── Callbacks ──
    class V5LoggingCallback(TrainerCallback):
        def __init__(self):
            self._start_time = time.time()
            self._step_start = time.time()
            self._step_timeout = step_timeout

        def on_log(self, args, state, control, logs=None, **kwargs):
            if logs is None:
                return
            step = state.global_step
            total = state.max_steps
            loss = logs.get("loss", logs.get("train_loss"))
            lr = logs.get("learning_rate")
            elapsed = time.time() - self._start_time
            step_time = time.time() - self._step_start
            eta_s = (elapsed / max(step, 1)) * (total - step) if step > 0 else 0

            parts = [f"Step {step}/{total}"]
            if loss is not None:
                parts.append(f"loss={loss:.4f}")
            if use_kl and kl_state["last_kl"] > 0:
                parts.append(f"sft={kl_state['last_sft']:.4f}")
                parts.append(f"kl={kl_state['last_kl']:.4f}")
            if lr is not None:
                parts.append(f"lr={lr:.2e}")
            parts.append(f"step_time={step_time:.1f}s")
            parts.append(f"elapsed={elapsed/3600:.1f}h")
            parts.append(f"ETA={eta_s/3600:.1f}h")
            logger.info(" | ".join(parts))
            sys.stderr.flush()

        def on_step_begin(self, args, state, control, **kwargs):
            self._step_start = time.time()

        def on_step_end(self, args, state, control, **kwargs):
            step_elapsed = time.time() - self._step_start
            logger.info(f"  Step {state.global_step} completed in {step_elapsed:.1f}s")

            # Step timeout — kill training if a step takes way too long
            # (catches VRAM spilling to system RAM before it wastes hours)
            if self._step_timeout > 0 and step_elapsed > self._step_timeout:
                logger.error(f"STEP TIMEOUT: step {state.global_step} took "
                             f"{step_elapsed:.0f}s > {self._step_timeout}s limit. "
                             f"Stopping training.")
                control.should_training_stop = True

            # Log VRAM every step for first 20 steps (catch gradual growth),
            # then every 50 steps for the rest of training.
            if state.global_step <= 20 or state.global_step % 50 == 0:
                self._log_memory(state.global_step)

            # Proactive VRAM pressure relief: always release reserved-but-unused
            # blocks after each step. PyTorch's caching allocator over-reserves
            # (17GB reserved on a 16GB card) causing spill to system RAM.
            try:
                reserved = torch.cuda.memory_reserved()
                total = torch.cuda.get_device_properties(0).total_memory
                reserved_pct = reserved / total
                torch.cuda.empty_cache()
                new_reserved = torch.cuda.memory_reserved()
                freed = (reserved - new_reserved) / (1024**2)
                if freed > 100:  # Log if we freed >100MB
                    logger.info(
                        f"[VRAM cleanup] step={state.global_step} "
                        f"reserved {reserved/(1024**2):.0f}MB -> "
                        f"{new_reserved/(1024**2):.0f}MB "
                        f"(freed {freed:.0f}MB)"
                    )
            except Exception:
                pass

        def on_train_begin(self, args, state, control, **kwargs):
            self._start_time = time.time()
            self._step_start = time.time()
            self._log_memory(0)
            logger.info(f"Training started: {state.max_steps} total steps"
                        + (f" (step timeout: {self._step_timeout}s)" if self._step_timeout else ""))

        def _log_memory(self, step):
            try:
                proc = psutil.Process()
                ram_gb = proc.memory_info().rss / (1024**3)
                gpu_line = ""
                try:
                    alloc_mb = torch.cuda.memory_allocated() / (1024**2)
                    reserved_mb = torch.cuda.memory_reserved() / (1024**2)
                    peak_mb = torch.cuda.max_memory_allocated() / (1024**2)
                    total_mb = torch.cuda.get_device_properties(0).total_memory / (1024**2)
                    free_mb = total_mb - reserved_mb
                    gpu_line = (f" | GPU alloc={alloc_mb:.0f}MB "
                                f"reserved={reserved_mb:.0f}MB "
                                f"peak={peak_mb:.0f}MB "
                                f"free={free_mb:.0f}MB "
                                f"({alloc_mb/total_mb:.0%})")
                except Exception as e:
                    logger.warning(f"torch.cuda metrics failed: {type(e).__name__}: {e}")
                    try:
                        out = subprocess.check_output(
                            ["nvidia-smi", "--query-gpu=memory.used,memory.free",
                             "--format=csv,noheader,nounits"],
                            text=True, timeout=5,
                        ).strip()
                        gpu_used, gpu_free = out.split(", ")
                        gpu_line = f" | GPU={gpu_used}MB used, {gpu_free}MB free (nvidia-smi)"
                    except Exception:
                        pass
                logger.info(f"[MEM step={step}] RAM={ram_gb:.1f}GB{gpu_line}")
            except Exception:
                pass

    # Heartbeat thread
    _heartbeat_stop = threading.Event()
    _hb_interval = 30 if max_steps > 0 else 300  # 30s for smoke tests, 5min for full
    def _heartbeat():
        n = 0
        while not _heartbeat_stop.wait(_hb_interval):
            n += 1
            try:
                import psutil as _ps
                ram_gb = _ps.Process().memory_info().rss / (1024**3)
                logger.info(f"[HEARTBEAT #{n}] alive, RAM={ram_gb:.1f}GB")
                sys.stderr.flush()
            except Exception:
                pass
    _hb_thread = threading.Thread(target=_heartbeat, daemon=True)
    _hb_thread.start()

    # ── Build SFTConfig ──
    # Adjust batch size: Unsloth saves ~4GB VRAM, so we can go bigger
    batch_size = TRAINING_CONFIG["per_device_train_batch_size"]
    grad_accum = TRAINING_CONFIG["gradient_accumulation_steps"]
    if use_unsloth:
        batch_size = 1    # batch=1 for 14B on 16GB (fused CE loss needs VRAM headroom)
        grad_accum = 16   # Keep effective batch = 16
        logger.info(f"Unsloth QLoRA mode: batch_size={batch_size}, grad_accum={grad_accum} "
                     f"(effective={batch_size * grad_accum})")

    # Packing disabled: incompatible with assistant_only_loss (response-only masking).
    # assistant_only_loss is critical for preventing catastrophic forgetting — the model
    # should only learn to predict assistant responses, not system prompts or user questions.
    logger.info("Sequence packing: OFF (required for assistant_only_loss)")
    logger.info("Loss masking: assistant_only_loss=True (only train on response tokens)")

    sft_kwargs = dict(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_accum,
        num_train_epochs=TRAINING_CONFIG["num_train_epochs"],
        learning_rate=TRAINING_CONFIG["learning_rate"] / 2 if warm_start else TRAINING_CONFIG["learning_rate"],
        warmup_ratio=TRAINING_CONFIG["warmup_ratio"],
        lr_scheduler_type=TRAINING_CONFIG["lr_scheduler_type"],
        bf16=TRAINING_CONFIG["bf16"],
        logging_steps=TRAINING_CONFIG["logging_steps"],
        logging_strategy="steps",
        save_steps=TRAINING_CONFIG["save_steps"],
        weight_decay=TRAINING_CONFIG["weight_decay"],
        max_grad_norm=TRAINING_CONFIG["max_grad_norm"],
        seed=TRAINING_CONFIG["seed"],
        report_to="none",
        disable_tqdm=True,
        gradient_checkpointing=True,
        optim="adamw_torch_fused" if not use_unsloth else "adamw_8bit",  # 8-bit Adam with Unsloth
        dataloader_num_workers=min(4, (os.cpu_count() or 4) // 2),
        dataloader_pin_memory=True,
        dataloader_persistent_workers=True,
        dataloader_prefetch_factor=2,
        dataloader_drop_last=True,
        logging_first_step=True,
        save_total_limit=3,
        skip_memory_metrics=True,
        max_length=seq_length,
        packing=False,                    # Disabled: incompatible with assistant_only_loss
        assistant_only_loss=True,         # Only compute loss on assistant response tokens
        neftune_noise_alpha=TRAINING_CONFIG["neftune_noise_alpha"],
        torch_compile=False,              # BnB 4-bit causes 39+ graph breaks with full-model compile;
                                          # norm layers compiled individually above (non-Unsloth), Unsloth uses own Triton
    )
    # Early stopping: eval every 50 steps, stop if val_loss stagnates for 150 steps
    if eval_dataset is not None:
        sft_kwargs["eval_strategy"] = "steps"
        sft_kwargs["eval_steps"] = 50
        sft_kwargs["load_best_model_at_end"] = True
        sft_kwargs["metric_for_best_model"] = "eval_loss"
        sft_kwargs["greater_is_better"] = False
        logger.info("Early stopping enabled: eval every 50 steps, patience ~150 steps")

    if max_steps > 0:
        sft_kwargs["max_steps"] = max_steps
        sft_kwargs["save_steps"] = max_steps + 1
        logger.info(f"Test mode: max_steps={max_steps}")

    sft_config = SFTConfig(**sft_kwargs)

    # Early stopping callback
    callbacks = [V5LoggingCallback()]
    if eval_dataset is not None:
        from transformers import EarlyStoppingCallback
        callbacks.append(EarlyStoppingCallback(early_stopping_patience=3))  # 3 evals = 150 steps
        logger.info("EarlyStoppingCallback added (patience=3 evals)")

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        eval_dataset=eval_dataset,
        args=sft_config,
        callbacks=callbacks,
        formatting_func=lambda example: example["messages"],
    )

    # Preserve curriculum ordering
    from torch.utils.data import SequentialSampler
    trainer._get_train_sampler = lambda ds: SequentialSampler(ds)

    # Monkey-patch training_step to call empty_cache() after every micro-batch.
    # Without this, PyTorch's caching allocator reserves 16-17GB on our 16GB card
    # during the 16 gradient accumulation sub-steps, spilling to system RAM (300s+ steps).
    # Cost: ~1-5ms per call × 16 calls/step = ~16-80ms overhead (negligible vs 70s steps).
    _orig_training_step = trainer.training_step
    def _training_step_with_vram_cleanup(model_arg, inputs, num_items_in_batch=None):
        result = _orig_training_step(model_arg, inputs, num_items_in_batch=num_items_in_batch)
        torch.cuda.empty_cache()
        return result
    trainer.training_step = _training_step_with_vram_cleanup

    # Check for existing checkpoints
    resume_checkpoint = None
    if os.path.exists(OUTPUT_DIR):
        checkpoints = sorted(
            [d for d in os.listdir(OUTPUT_DIR) if d.startswith("checkpoint-")],
            key=lambda x: int(x.split("-")[-1]) if x.split("-")[-1].isdigit() else 0,
        )
        if checkpoints:
            resume_checkpoint = os.path.join(OUTPUT_DIR, checkpoints[-1])
            logger.info(f"Resuming from checkpoint: {resume_checkpoint}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Final VRAM cleanup before training — free all cached allocations
    gc.collect()
    torch.cuda.empty_cache()
    pre_train_alloc = torch.cuda.memory_allocated() / 1e9
    pre_train_reserved = torch.cuda.memory_reserved() / 1e9
    pre_train_total = torch.cuda.get_device_properties(0).total_memory / 1e9
    logger.info(f"Pre-train VRAM: {pre_train_alloc:.2f}GB alloc, "
                f"{pre_train_reserved:.2f}GB reserved, "
                f"{pre_train_total - pre_train_reserved:.2f}GB truly free")

    logger.info("Starting training...")
    sys.stderr.flush()
    start_time = time.time()

    try:
        stats = trainer.train(resume_from_checkpoint=resume_checkpoint)
    except Exception as e:
        logger.error(f"Training FAILED: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        _heartbeat_stop.set()
        raise
    finally:
        _heartbeat_stop.set()

    elapsed = time.time() - start_time
    loss = stats.metrics.get("train_loss", "N/A")
    logger.info(f"Training complete: loss={loss}, time={elapsed:.0f}s ({elapsed/3600:.1f}h)")

    # ── Save adapter ──
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    logger.info(f"Adapter saved to {OUTPUT_DIR}")

    # Save training metadata
    meta = {
        "version": "v7.0",
        "base_model": model_path,
        "base_model_name": "Qwen2.5-Coder-14B-Instruct",
        "architecture": "dense 14B, QLoRA 4-bit",
        "unsloth": use_unsloth,
        "pair_count": pair_count,
        "loss": loss if isinstance(loss, (int, float)) else None,
        "training_time_s": round(elapsed),
        "lora_config": LORA_CONFIG,
        "training_config": TRAINING_CONFIG,
        "kl_config": KL_CONFIG if use_kl else None,
        "kl_disabled_during_training": kl_state["disabled"],
        "max_seq_length": seq_length,
        "system_prompt": "CODING_SYSTEM_PROMPT (hiveai.llm.prompts)",
        "format": "ChatML via tokenizer.apply_chat_template",
        "eos_token": tokenizer.eos_token,
        "eos_token_id": tokenizer.eos_token_id,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(os.path.join(OUTPUT_DIR, "training_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    # ── Print next steps ──
    print("\n" + "=" * 60)
    print("  v7 Training Complete — Next Steps")
    print("=" * 60)
    print(f"""
  1. Quick eval (2 min):
     python scripts/quick_eval.py

  2. Convert LoRA to GGUF:
     python convert_lora_to_gguf.py loras/v7 --base models/qwen2.5-coder-14b-base \\
       --outfile models/hiveai-v7-lora-f16.gguf --outtype f16

  3. Deploy to llama-server:
     llama-server --model models/Qwen2.5-Coder-14B-Instruct-Q5_K_M.gguf \\
       --lora models/hiveai-v7-lora-f16.gguf --port 11435

  4. Full eval (165 challenges):
     python scripts/run_eval.py --model hiveai-v7 --base-url http://localhost:11435
""")
    print("=" * 60)

    return loss


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Train HiveAI v6 on Qwen2.5-Coder-14B QLoRA")
    parser.add_argument("--test", type=int, default=0,
                        help="Smoke test: stop after N steps")
    parser.add_argument("--no-kl", action="store_true",
                        help="Disable KL-anchored SFT")
    parser.add_argument("--no-unsloth", action="store_true",
                        help="Skip Unsloth (standard transformers path). "
                             "Auto-enabled in --test mode for fast startup.")
    parser.add_argument("--force-unsloth", action="store_true",
                        help="Force Unsloth even in --test mode (slow: Triton JIT)")
    parser.add_argument("--model", type=str, default=None,
                        help="Override base model path")
    parser.add_argument("--seq-length", type=int, default=0,
                        help="Override max sequence length (default: 1024 for 16GB, "
                             "2048 for 24GB+, 512 for smoke tests)")
    parser.add_argument("--step-timeout", type=int, default=0,
                        help="Kill training if a single step exceeds N seconds "
                             "(default: 300 in --test mode, 0=disabled otherwise)")
    parser.add_argument("--warm-start", type=str, default=None,
                        help="Continue training from an existing adapter directory "
                             "(e.g., loras/v6). Loads base+adapter, skips new LoRA init.")
    parser.add_argument("--data", type=str, default=None,
                        help="Override training data JSONL path (default: v7.jsonl)")
    args = parser.parse_args()

    # In --test mode, auto-skip Unsloth unless --force-unsloth.
    # Unsloth's Triton JIT compilation takes 15+ minutes — the standard
    # transformers+PEFT path catches the exact same shape/VRAM/config errors.
    if args.test and not args.force_unsloth:
        args.no_unsloth = True
        logger.info("Test mode: auto-skipping Unsloth (use --force-unsloth to override)")

    model_path = args.model or BASE_MODEL

    if args.data:
        TRAINING_JSONL = os.path.abspath(args.data)

    if not os.path.exists(TRAINING_JSONL):
        logger.error(f"Training data not found: {TRAINING_JSONL}")
        logger.error("Run: python scripts/prepare_v5_data.py")
        sys.exit(1)

    if not os.path.exists(model_path):
        if args.no_unsloth:
            logger.error(f"Base model not found: {model_path}")
            logger.error("Download: huggingface-cli download Qwen/Qwen2.5-Coder-14B-Instruct "
                          "--local-dir models/qwen2.5-coder-14b")
            sys.exit(1)
        else:
            logger.info(f"Local model not found at {model_path} — Unsloth will download from HuggingFace")

    optimize_system_pre_load()
    train_v5(model_path, max_steps=args.test, use_kl=not args.no_kl,
             skip_unsloth=args.no_unsloth, step_timeout=args.step_timeout,
             seq_length_override=args.seq_length, warm_start=args.warm_start)
