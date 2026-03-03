"""
Train HiveAI LoRA v5 on Qwen3.5-9B Dense.

One-command training:
    python scripts/train_v5.py
    python scripts/train_v5.py --test 5    # smoke test (5 steps)
    python scripts/train_v5.py --no-kl     # disable KL anchoring

What's new in v5:
    - Dense Qwen3.5-9B base (no MoE, no expert patching, no pruning)
    - 9B active params per token (3x more than pruned 35B-A3B's 3B active)
    - Aggressive LoRA: r=64, 7 target modules (attn + MLP), DoRA
    - KL-Anchored SFT (from v4) — prevents catastrophic forgetting
    - Combined dataset: ~3500+ pairs from v1-v4 + specialty (prepare_v5_data.py)
    - 3 epochs (dense benefits from repetition)
    - Effective batch size 16 (batch=2, grad_accum=8)
    - NEFTune + curriculum ordering + Hive oversampling
    - All v3 infrastructure: system optimizer, heartbeat, checkpoints, CUDA tuning
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

TRAINING_JSONL = os.path.join(PROJECT_ROOT, "loras", "training_data", "v5.jsonl")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "loras", "v5")

# Dense base model — no pruning, no expert patching
BASE_MODEL = os.path.join(PROJECT_ROOT, "models", "qwen3.5-9b")

# ---------------------------------------------------------------------------
# v5 Training Configuration — Aggressive Dense LoRA
# ---------------------------------------------------------------------------
MAX_SEQ_LENGTH = 4096

LORA_CONFIG = {
    "r": 64,                          # UP from 32 — dense has VRAM room
    "lora_alpha": 128,                # 2x rank for stable scaling
    "target_modules": [
        "q_proj", "k_proj", "v_proj", "o_proj",   # attention (proven in v3)
        "gate_proj", "up_proj", "down_proj",        # MLP layers (NEW for dense)
    ],
    "lora_dropout": 0.0,
    "bias": "none",
    "use_dora": True,                 # Weight-Decomposed LoRA: +1-4.4pts quality
}

TRAINING_CONFIG = {
    "per_device_train_batch_size": 2,      # UP from 1 (9B uses ~6.5GB vs ~11GB for MoE)
    "gradient_accumulation_steps": 8,      # Effective batch = 16
    "num_train_epochs": 3,                 # UP from 1 (dense benefits from repetition)
    "learning_rate": 1.5e-4,               # Slightly lower than 2e-4 for more modules
    "warmup_ratio": 0.03,                  # 3% warmup
    "lr_scheduler_type": "cosine",
    "bf16": True,
    "logging_steps": 5,
    "save_steps": 200,
    "weight_decay": 0.01,
    "max_grad_norm": 1.0,
    "seed": 42,
    "neftune_noise_alpha": 5.0,            # NEFTune: +0.5-1% quality, zero cost
}

# KL-Anchored SFT (from v4 — prevents catastrophic forgetting)
KL_CONFIG = {
    "lambda": 0.1,        # KL weight in loss
    "temperature": 1.0,   # Softmax temperature
    "seq_limit": 512,     # Max tokens for KL (VRAM safety)
}


# ---------------------------------------------------------------------------
# System Optimizer (from train_v3.py — hardware auto-detection)
# ---------------------------------------------------------------------------
def optimize_system():
    """Auto-detect hardware and maximize system resources for training."""
    import psutil

    logger.info("=" * 60)
    logger.info("  System Auto-Optimizer")
    logger.info("=" * 60)
    optimizations = []

    cpu_count = os.cpu_count() or 4
    ram_total = psutil.virtual_memory().total / (1024**3)
    ram_avail = psutil.virtual_memory().available / (1024**3)
    logger.info(f"  CPU: {cpu_count} cores")
    logger.info(f"  RAM: {ram_total:.1f}GB total, {ram_avail:.1f}GB available")

    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram_total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            capability = torch.cuda.get_device_capability(0)
            logger.info(f"  GPU: {gpu_name} ({vram_total:.1f}GB VRAM, "
                        f"compute {capability[0]}.{capability[1]})")
        else:
            capability = (0, 0)
    except Exception:
        capability = (0, 0)

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

    # PyTorch thread pools
    try:
        import torch
        torch.set_num_threads(min(cpu_count, 8))
        torch.set_num_interop_threads(min(cpu_count // 2, 4))
        optimizations.append("threads tuned")
    except Exception:
        pass

    # CUDA optimizations
    try:
        import torch
        if torch.cuda.is_available() and capability[0] >= 8:
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            torch.set_float32_matmul_precision("high")  # TF32 for ALL matmuls
            optimizations.append("TF32 enabled (high precision)")
        if hasattr(torch.backends.cuda, "flash_sdp_enabled"):
            torch.backends.cuda.enable_flash_sdp(True)
            torch.backends.cuda.enable_mem_efficient_sdp(True)
            optimizations.append("Flash SDP enabled")
        os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "0")
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        # Reduce CUDA memory fragmentation (huge win for long training runs)
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
        optimizations.append("CUDA expandable segments")
    except Exception:
        pass

    # Check for cut_cross_entropy (saves ~2GB VRAM, no quality loss)
    try:
        import cut_cross_entropy  # noqa: F401
        os.environ["CUT_CROSS_ENTROPY"] = "1"
        optimizations.append("cut_cross_entropy available")
    except ImportError:
        pass

    # GC tuning
    import gc
    gc.set_threshold(700, 10, 5)

    logger.info(f"  Applied: {', '.join(optimizations)}")
    logger.info("=" * 60)
    return optimizations


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def train_v5(model_path: str, max_steps: int = 0, use_kl: bool = True):
    """Train LoRA v5 on Qwen3.5-9B dense model."""
    import torch
    import torch.nn.functional as F
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import LoraConfig, TaskType, get_peft_model
    from datasets import load_dataset
    from trl import SFTTrainer, SFTConfig
    from transformers import TrainerCallback
    import psutil

    from hiveai.llm.prompts import CODING_SYSTEM_PROMPT

    logger.info("=" * 60)
    logger.info("  HiveAI LoRA v5 Training — Qwen3.5-9B Dense")
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
    logger.info(f"  Context:     {MAX_SEQ_LENGTH} tokens")
    logger.info(f"  NEFTune:     alpha={TRAINING_CONFIG['neftune_noise_alpha']}")
    logger.info(f"  KL anchor:   {'ON' if use_kl else 'OFF'} "
                f"(lambda={KL_CONFIG['lambda']}, seq_limit={KL_CONFIG['seq_limit']})")
    logger.info(f"  Architecture: DENSE (no expert patching needed)")
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

    try:
        from unsloth import FastLanguageModel
        logger.info("Unsloth detected — using FastLanguageModel for 2x speed + 70% less VRAM")

        # Unsloth handles quantization internally
        unsloth_model_name = model_path
        # Check for pre-quantized Unsloth model
        if os.path.basename(model_path) == "qwen3.5-9b":
            # Try local path first, then Unsloth HF model
            if os.path.isdir(model_path) and os.path.exists(os.path.join(model_path, "config.json")):
                unsloth_model_name = model_path
                logger.info(f"  Using local weights: {unsloth_model_name}")
            else:
                unsloth_model_name = "unsloth/Qwen3.5-9B"
                logger.info(f"  Using Unsloth HF model: {unsloth_model_name}")

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=unsloth_model_name,
            max_seq_length=MAX_SEQ_LENGTH,
            dtype=torch.bfloat16,
            load_in_4bit=True,
            trust_remote_code=True,
        )
        use_unsloth = True
        load_time = time.time() - load_start
        logger.info(f"Model loaded via Unsloth in {load_time:.0f}s")

    except Exception as e:
        logger.warning(f"Unsloth not available ({e}), falling back to standard transformers+PEFT")

        # Use local path if available, otherwise HF model ID
        load_path = model_path
        if not os.path.isdir(model_path) or not os.path.exists(os.path.join(model_path, "config.json")):
            load_path = "Qwen/Qwen3.5-9B"
            logger.info(f"  Local path not found, using HF model: {load_path}")

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )

        logger.info(f"Loading tokenizer from {load_path}...")
        tokenizer = AutoTokenizer.from_pretrained(load_path, trust_remote_code=True)

        logger.info(f"Loading Qwen3.5-9B with BnB 4-bit (dense, ~6.5GB VRAM)...")
        model = AutoModelForCausalLM.from_pretrained(
            load_path,
            quantization_config=bnb_config,
            device_map={"": 0},   # All on GPU 0 — 9B fits easily at 4-bit
            torch_dtype=torch.bfloat16,
            trust_remote_code=True,
        )
        load_time = time.time() - load_start
        logger.info(f"Model loaded via standard transformers in {load_time:.0f}s")

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
    if use_unsloth:
        # Unsloth handles LoRA application, freezing, and gradient checkpointing
        model = FastLanguageModel.get_peft_model(
            model,
            r=LORA_CONFIG["r"],
            lora_alpha=LORA_CONFIG["lora_alpha"],
            target_modules=LORA_CONFIG["target_modules"],
            lora_dropout=LORA_CONFIG["lora_dropout"],
            bias=LORA_CONFIG["bias"],
            use_gradient_checkpointing="unsloth",  # Unsloth's optimized version (2x faster)
            use_rslora=False,
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

    # ── torch.compile for normalization layers ──
    USE_COMPILE = os.environ.get("HIVE_TORCH_COMPILE", "1") == "1"
    if USE_COMPILE:
        try:
            base_model = model
            for attr in ("base_model", "model", "model"):
                if hasattr(base_model, attr):
                    base_model = getattr(base_model, attr)
            layers = getattr(base_model, "layers", None)
            if layers is None and hasattr(base_model, "language_model"):
                layers = getattr(base_model.language_model, "layers", None)
            if layers is not None:
                compiled = 0
                for layer in layers:
                    for norm_name in ("input_layernorm", "post_attention_layernorm"):
                        norm = getattr(layer, norm_name, None)
                        if norm is not None:
                            try:
                                setattr(layer, norm_name,
                                        torch.compile(norm, mode="reduce-overhead"))
                                compiled += 1
                            except Exception:
                                pass
                logger.info(f"torch.compile: {compiled} norm layers compiled")
        except Exception as e:
            logger.warning(f"torch.compile skipped: {e}")

    # ── Load and format dataset ──
    dataset = load_dataset("json", data_files=TRAINING_JSONL, split="train")
    logger.info(f"EOS token: '{tokenizer.eos_token}' (id={tokenizer.eos_token_id})")

    def format_prompt(examples):
        texts = []
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

            try:
                text = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=False
                )
            except Exception:
                text = (
                    f"<|im_start|>system\n{CODING_SYSTEM_PROMPT}<|im_end|>\n"
                    f"<|im_start|>user\n{user_content}<|im_end|>\n"
                    f"<|im_start|>assistant\n{out}<|im_end|>"
                )

            # Truncate if too long (preserve EOS)
            n_tokens = len(tokenizer.encode(text))
            if n_tokens > MAX_SEQ_LENGTH:
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

                budget = MAX_SEQ_LENGTH - overhead_tokens - 1
                out_tokens = tokenizer.encode(out, add_special_tokens=False)[:budget]
                truncated_out = tokenizer.decode(out_tokens, skip_special_tokens=False)

                messages[-1]["content"] = truncated_out
                try:
                    text = tokenizer.apply_chat_template(
                        messages, tokenize=False, add_generation_prompt=False
                    )
                except Exception:
                    text = (
                        f"<|im_start|>system\n{CODING_SYSTEM_PROMPT}<|im_end|>\n"
                        f"<|im_start|>user\n{user_content}<|im_end|>\n"
                        f"<|im_start|>assistant\n{truncated_out}<|im_end|>"
                    )
                n_truncated += 1

            texts.append(text)

        if n_truncated > 0:
            logger.info(f"  format_prompt: truncated {n_truncated}/{len(texts)} "
                        f"to fit {MAX_SEQ_LENGTH} tokens")
        return {"text": texts}

    dataset = dataset.map(format_prompt, batched=True)
    logger.info(f"Dataset ready: {len(dataset)} examples")

    sample = dataset[0]["text"]
    sample_len = len(tokenizer.encode(sample))
    ends_with_eos = sample.rstrip().endswith("<|im_end|>")
    logger.info(f"Sample: {sample_len} tokens, ends_with_EOS={ends_with_eos}")
    logger.info(f"First 400 chars:\n{sample[:400]}")

    # ── KL-Anchored Loss Setup ──
    kl_state = {"disabled": False, "last_kl": 0.0, "last_sft": 0.0}
    _original_compute_loss = SFTTrainer.compute_loss

    def compute_loss_with_kl(self_trainer, model_arg, inputs,
                              return_outputs=False, num_items_in_batch=None, **kwargs):
        parent_kwargs = {}
        if num_items_in_batch is not None:
            parent_kwargs["num_items_in_batch"] = num_items_in_batch

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
        if (use_kl and KL_CONFIG["lambda"] > 0
                and not kl_state["disabled"] and outputs is not None):
            tuned_logits = outputs.logits
            kl_slice = min(tuned_logits.shape[1], KL_CONFIG["seq_limit"])

            try:
                with torch.no_grad():
                    model_arg.disable_adapter_layers()
                    ref_outputs = model_arg(**inputs)
                    ref_logits = ref_outputs.logits[:, -kl_slice:, :].detach()
                    model_arg.enable_adapter_layers()

                kl_loss = F.kl_div(
                    F.log_softmax(
                        tuned_logits[:, -kl_slice:, :] / KL_CONFIG["temperature"],
                        dim=-1,
                    ),
                    F.log_softmax(ref_logits / KL_CONFIG["temperature"], dim=-1),
                    reduction="batchmean",
                    log_target=True,
                ) * (KL_CONFIG["temperature"] ** 2)

                kl_loss_val = kl_loss.item()
                sft_loss = sft_loss + KL_CONFIG["lambda"] * kl_loss

            except torch.cuda.OutOfMemoryError:
                model_arg.enable_adapter_layers()
                torch.cuda.empty_cache()
                if not kl_state["disabled"]:
                    logger.warning("KL anchoring OOM — disabling for rest of training")
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

        def on_log(self, args, state, control, logs=None, **kwargs):
            if logs is None:
                return
            step = state.global_step
            total = state.max_steps
            loss = logs.get("loss", logs.get("train_loss"))
            lr = logs.get("learning_rate")
            elapsed = time.time() - self._start_time
            eta_s = (elapsed / max(step, 1)) * (total - step) if step > 0 else 0

            parts = [f"Step {step}/{total}"]
            if loss is not None:
                parts.append(f"loss={loss:.4f}")
            if use_kl and kl_state["last_kl"] > 0:
                parts.append(f"sft={kl_state['last_sft']:.4f}")
                parts.append(f"kl={kl_state['last_kl']:.4f}")
            if lr is not None:
                parts.append(f"lr={lr:.2e}")
            parts.append(f"elapsed={elapsed/3600:.1f}h")
            parts.append(f"ETA={eta_s/3600:.1f}h")
            logger.info(" | ".join(parts))
            sys.stderr.flush()

        def on_step_end(self, args, state, control, **kwargs):
            if state.global_step % 10 == 0:
                torch.cuda.empty_cache()
            if state.global_step % 50 == 0 and state.global_step > 0:
                self._log_memory(state.global_step)

        def on_train_begin(self, args, state, control, **kwargs):
            self._start_time = time.time()
            self._log_memory(0)
            logger.info(f"Training started: {state.max_steps} total steps")

        def _log_memory(self, step):
            try:
                proc = psutil.Process()
                ram_gb = proc.memory_info().rss / (1024**3)
                gpu_line = ""
                try:
                    out = subprocess.check_output(
                        ["nvidia-smi", "--query-gpu=memory.used,memory.free",
                         "--format=csv,noheader,nounits"],
                        text=True, timeout=5,
                    ).strip()
                    gpu_used, gpu_free = out.split(", ")
                    gpu_line = f" | GPU={gpu_used}MB used, {gpu_free}MB free"
                except Exception:
                    pass
                logger.info(f"[MEM step={step}] RAM={ram_gb:.1f}GB{gpu_line}")
            except Exception:
                pass

    # Heartbeat thread
    _heartbeat_stop = threading.Event()
    def _heartbeat():
        n = 0
        while not _heartbeat_stop.wait(300):
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
        batch_size = 4   # UP from 2 — Unsloth frees enough VRAM
        grad_accum = 4   # Keep effective batch = 16
        logger.info(f"Unsloth VRAM savings: batch_size={batch_size}, grad_accum={grad_accum} "
                     f"(effective={batch_size * grad_accum})")

    # Packing: concatenate short sequences to fill context window (30-50% speedup)
    use_packing = True
    logger.info(f"Sequence packing: {'ON' if use_packing else 'OFF'}")

    sft_kwargs = dict(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_accum,
        num_train_epochs=TRAINING_CONFIG["num_train_epochs"],
        learning_rate=TRAINING_CONFIG["learning_rate"],
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
        dataloader_num_workers=2,
        dataloader_pin_memory=True,
        dataloader_persistent_workers=True,
        dataloader_prefetch_factor=2,
        dataloader_drop_last=True,
        logging_first_step=True,
        save_total_limit=3,
        skip_memory_metrics=True,
        dataset_text_field="text",
        max_length=MAX_SEQ_LENGTH,
        packing=use_packing,
        neftune_noise_alpha=TRAINING_CONFIG["neftune_noise_alpha"],
    )
    if max_steps > 0:
        sft_kwargs["max_steps"] = max_steps
        sft_kwargs["save_steps"] = max_steps + 1
        logger.info(f"Test mode: max_steps={max_steps}")

    sft_config = SFTConfig(**sft_kwargs)

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        args=sft_config,
        callbacks=[V5LoggingCallback()],
    )

    # Preserve curriculum ordering
    from torch.utils.data import SequentialSampler
    trainer._get_train_sampler = lambda ds: SequentialSampler(ds)

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
        "version": "v5.0",
        "base_model": model_path,
        "base_model_name": "Qwen3.5-9B",
        "architecture": "dense (no MoE)",
        "unsloth": use_unsloth,
        "pair_count": pair_count,
        "loss": loss if isinstance(loss, (int, float)) else None,
        "training_time_s": round(elapsed),
        "lora_config": LORA_CONFIG,
        "training_config": TRAINING_CONFIG,
        "kl_config": KL_CONFIG if use_kl else None,
        "kl_disabled_during_training": kl_state["disabled"],
        "max_seq_length": MAX_SEQ_LENGTH,
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
    print("  v5 Training Complete — Next Steps")
    print("=" * 60)
    print(f"""
  Deploy to Ollama:
     python scripts/deploy_v5.py --now --eval

  Or manually:
  1. Merge LoRA + export GGUF
  2. ollama create hiveai-v5 -f Modelfile
  3. python scripts/run_eval.py --model hiveai-v5

  Baselines: qwen3:14b=0.741, hiveai-v1=0.853 (+15%)
""")
    print("=" * 60)

    return loss


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Train HiveAI v5 on Qwen3.5-9B Dense")
    parser.add_argument("--test", type=int, default=0,
                        help="Smoke test: stop after N steps")
    parser.add_argument("--no-kl", action="store_true",
                        help="Disable KL-anchored SFT")
    parser.add_argument("--model", type=str, default=None,
                        help="Override base model path")
    args = parser.parse_args()

    model_path = args.model or BASE_MODEL

    if not os.path.exists(TRAINING_JSONL):
        logger.error(f"Training data not found: {TRAINING_JSONL}")
        logger.error("Run: python scripts/prepare_v5_data.py")
        sys.exit(1)

    if not os.path.exists(model_path):
        logger.error(f"Base model not found: {model_path}")
        logger.error("Download: huggingface-cli download Qwen/Qwen3.5-9B "
                      "--local-dir models/qwen3.5-9b")
        sys.exit(1)

    optimize_system()
    train_v5(model_path, max_steps=args.test, use_kl=not args.no_kl)
