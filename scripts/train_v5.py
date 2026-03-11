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
    "lora_dropout": 0.0,             # Unsloth kernels optimized for 0 dropout (fused Triton paths)
    "bias": "none",
    "use_dora": False,                # DoRA incompatible with Flash Attention (fp32 intermediates)
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

# EWC-LoRA — Elastic Weight Consolidation for LoRA parameters (ICLR 2026)
# Computes Fisher Information Matrix over replay data to identify important parameters,
# then adds a quadratic penalty preventing those parameters from changing.
# Result: +8.92% over vanilla LoRA on continual learning benchmarks.
EWC_CONFIG = {
    "lambda": 0.5,         # EWC penalty weight (0.3-0.7 recommended range)
    "fisher_samples": 200, # Number of replay samples for Fisher computation
    "enabled": True,       # Can disable for first cycle (no previous knowledge)
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

    # Force offline HF loading — all models are cached, no need to phone home
    # Prevents 120s timeout when HuggingFace is slow/down
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

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
# Auto GGUF Conversion
# ---------------------------------------------------------------------------
def auto_convert_gguf(adapter_dir):
    """Convert PEFT adapter to GGUF format for llama.cpp"""
    gguf_path = os.path.join(adapter_dir, "adapter.gguf")
    if os.path.exists(gguf_path):
        print(f"[GGUF] adapter.gguf already exists at {gguf_path}")
        return gguf_path

    # Try to find convert_lora_to_gguf.py
    search_paths = [
        "/tmp/llama_cpp_build/convert_lora_to_gguf.py",
        "/tmp/llama.cpp/convert_lora_to_gguf.py",
        os.path.expanduser("~/llama.cpp/convert_lora_to_gguf.py"),
    ]
    # Also check LLAMA_CPP_DIR env var
    llama_cpp_dir = os.environ.get("LLAMA_CPP_DIR", "")
    if llama_cpp_dir:
        search_paths.insert(0, os.path.join(llama_cpp_dir, "convert_lora_to_gguf.py"))

    convert_script = None
    for p in search_paths:
        if os.path.exists(p):
            convert_script = p
            break

    if not convert_script:
        print("[GGUF] convert_lora_to_gguf.py not found — skipping auto-conversion")
        print("[GGUF] Manually run: python convert_lora_to_gguf.py --outfile adapter.gguf <adapter_dir>")
        return None

    print(f"[GGUF] Converting adapter to GGUF format...")
    try:
        result = subprocess.run(
            ["python3", convert_script, "--outfile", gguf_path, adapter_dir],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0 and os.path.exists(gguf_path):
            size_mb = os.path.getsize(gguf_path) / (1024 * 1024)
            print(f"[GGUF] Successfully created {gguf_path} ({size_mb:.1f} MB)")
            return gguf_path
        else:
            print(f"[GGUF] Conversion failed: {result.stderr[:500]}")
            return None
    except subprocess.TimeoutExpired:
        print("[GGUF] Conversion timed out after 300s")
        return None
    except Exception as e:
        print(f"[GGUF] Conversion error: {e}")
        return None


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def train_v5(model_path: str, max_steps: int = 0, use_kl: bool = True,
             skip_unsloth: bool = False, step_timeout: int = 0,
             seq_length_override: int = 0, warm_start: str = None,
             epochs_override: int = 0, two_stage: bool = False,
             lora_plus: bool = False, use_ewc: bool = False,
             ewc_fisher_path: str = None, prev_lora_path: str = None,
             probe_guard: bool = False, probe_interval: int = 50,
             probe_server_url: str = "http://localhost:11435"):
    """Train LoRA on Qwen2.5-Coder-14B-Instruct (QLoRA via Unsloth).

    Lossless continual learning features:
    - EWC-LoRA: Fisher penalty prevents changing important parameters (--ewc-lambda)
    - Orthogonal init: Initialize new LoRA orthogonal to previous task (--prev-lora)
    """
    import torch
    import torch.nn.functional as F

    # CRITICAL: Disable CUDA graphs before any torch.compile call.
    # BnB 4-bit dequantization creates temporary tensors with non-deterministic
    # lifetimes, which breaks CUDA graph recording/replay.
    os.environ.setdefault("TORCHINDUCTOR_USE_CUDAGRAPHS", "0")

    # Persist Triton compilation cache so Unsloth kernels don't recompile every run
    os.environ.setdefault("TRITON_CACHE_DIR", os.path.join(PROJECT_ROOT, ".triton_cache"))

    # Fix Triton compilation deadlock on small datasets (<500 samples).
    # Default 20 compile workers deadlock waiting for kernel cache writes.
    os.environ.setdefault("TRITON_NUM_THREADS", "2")
    os.environ.setdefault("TORCH_COMPILE_THREADS", "2")
    # Python-level fix: env vars alone don't control compile_worker's --workers flag.
    # This directly limits torch._inductor's thread pool, preventing deadlock.
    try:
        import torch._inductor.config as inductor_config
        inductor_config.compile_threads = 2
    except (ImportError, AttributeError):
        pass  # older torch versions may not have this

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

    # Compute actual training params with overrides
    actual_epochs = epochs_override if epochs_override > 0 else (1 if warm_start else TRAINING_CONFIG["num_train_epochs"])
    actual_lr = TRAINING_CONFIG["learning_rate"] / 2 if warm_start else TRAINING_CONFIG["learning_rate"]
    eff_batch = (TRAINING_CONFIG["per_device_train_batch_size"]
                 * TRAINING_CONFIG["gradient_accumulation_steps"])

    logger.info("=" * 60)
    if warm_start:
        logger.info("  HiveAI WARM-START Training — Building on Previous Adapter")
    else:
        logger.info("  HiveAI LoRA Training — Qwen2.5-Coder-14B QLoRA")
    logger.info("=" * 60)
    logger.info(f"  Base model:  {model_path}")
    if warm_start:
        logger.info(f"  Warm-start:  {warm_start} (preserving learned weights)")
        logger.info(f"  Strategy:    half LR ({actual_lr}) + {actual_epochs} epoch(s) — gentle integration")
    logger.info(f"  Data:        {TRAINING_JSONL}")
    logger.info(f"  Output:      {OUTPUT_DIR}")
    logger.info(f"  LoRA:        r={LORA_CONFIG['r']}, alpha={LORA_CONFIG['lora_alpha']}, "
                f"DoRA={LORA_CONFIG.get('use_dora')}, "
                f"modules={LORA_CONFIG['target_modules']}")
    logger.info(f"  Training:    batch={TRAINING_CONFIG['per_device_train_batch_size']}x"
                f"{TRAINING_CONFIG['gradient_accumulation_steps']}="
                f"{eff_batch} effective, "
                f"epochs={actual_epochs}, "
                f"lr={actual_lr}")
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

    total_steps = (pair_count * actual_epochs) // eff_batch
    logger.info(f"Expected steps: ~{total_steps}")
    if warm_start:
        # Estimate time based on v7 throughput (~1.38 steps/min for 14B on 4070Ti)
        est_minutes = total_steps / 1.38
        logger.info(f"Estimated time: ~{est_minutes:.0f} min ({est_minutes/60:.1f}h) "
                    f"[warm-start: {actual_epochs} epoch × {pair_count} pairs]")

    # ── Load model — try Unsloth first (2x faster), fallback to standard ──
    use_unsloth = False
    load_start = time.time()

    def _load_with_unsloth():
        nonlocal use_unsloth
        logger.info("Using Unsloth FastLanguageModel for 2x speed + 70% less VRAM")

        if warm_start and os.path.isdir(warm_start):
            # Warm start: load the 4-bit BASE model first (from cache, no 28GB download),
            # then load the adapter weights on top. Passing the adapter dir directly to
            # from_pretrained causes Unsloth to resolve the base model to full-precision
            # Qwen/Qwen2.5-Coder-14B-Instruct and download 28GB.
            unsloth_model_name = "unsloth/Qwen2.5-Coder-14B-Instruct-bnb-4bit"
            logger.info(f"  WARM START: loading 4-bit base first, then adapter from {warm_start}")
        elif os.path.isdir(model_path) and os.path.exists(os.path.join(model_path, "config.json")):
            # Continual learning: load merged HF checkpoint as base (quantized on-the-fly)
            # This path is used when --base-model-hf points to a merged checkpoint
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
            # Try cached Unsloth pre-quantized model first (already 4-bit, no CPU quantization needed)
            bnb4_cache = os.path.expanduser("~/.cache/huggingface/hub/models--unsloth--Qwen2.5-Coder-14B-Instruct-bnb-4bit/snapshots")
            if os.path.isdir(bnb4_cache):
                snapshots = os.listdir(bnb4_cache)
                if snapshots:
                    load_path = os.path.join(bnb4_cache, snapshots[0])
                    logger.info(f"  Using cached pre-quantized model: {load_path}")
            if load_path == model_path:
                # Final fallback: try HF hub name (will download if online)
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
    try:
        from trl import DataCollatorForCompletionOnlyLM  # TRL <0.24
    except ImportError:
        # TRL 0.24+ removed DataCollatorForCompletionOnlyLM — use inline implementation
        from dataclasses import dataclass
        from transformers import DataCollatorForLanguageModeling

        @dataclass
        class DataCollatorForCompletionOnlyLM(DataCollatorForLanguageModeling):
            """Masks loss on everything before the response_template tokens."""
            response_template: str = "<|im_start|>assistant\n"
            mlm: bool = False

            def __init__(self, response_template, tokenizer, **kwargs):
                super().__init__(tokenizer=tokenizer, mlm=False, **kwargs)
                self.response_template_ids = tokenizer.encode(
                    response_template, add_special_tokens=False
                )

            def torch_call(self, examples):
                import torch
                batch = super().torch_call(examples)
                for i, labels in enumerate(batch["labels"]):
                    # Find response template position
                    template_len = len(self.response_template_ids)
                    found = False
                    for idx in range(len(labels) - template_len + 1):
                        if labels[idx:idx + template_len].tolist() == self.response_template_ids:
                            # Mask everything before the response (set to -100)
                            batch["labels"][i, :idx + template_len] = -100
                            found = True
                            break
                    if not found:
                        # If template not found, mask nothing (train on full sequence)
                        pass
                return batch
        logger.info("Using inline DataCollatorForCompletionOnlyLM (TRL 0.24+ compat)")

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

    # ── Semantic <think> token initialization (§32 LLM4SVG) ──
    if args.init_think_tokens:
        _THINK_SEEDS = ["reason", "analyze", "consider", "evaluate", "think", "step"]
        think_tokens = ["<think>", "</think>"]
        found_tokens = [t for t in think_tokens if t in tokenizer.get_vocab()]
        if found_tokens:
            embed_layer = model.get_input_embeddings()
            seed_ids = []
            for word in _THINK_SEEDS:
                ids = tokenizer.encode(word, add_special_tokens=False)
                seed_ids.extend(ids)
            if seed_ids:
                with torch.no_grad():
                    seed_embeds = embed_layer.weight[seed_ids].mean(dim=0)
                    for tok in found_tokens:
                        tok_id = tokenizer.convert_tokens_to_ids(tok)
                        if tok_id != tokenizer.unk_token_id:
                            embed_layer.weight[tok_id] = seed_embeds
                            logger.info(f"  Initialized '{tok}' (id={tok_id}) with semantic average of {_THINK_SEEDS}")
            else:
                logger.warning("Could not encode seed words for <think> token init")
        else:
            logger.info("No <think>/</think> tokens found in tokenizer -- skipping init")

    # Count quantized modules
    n_quantized = sum(1 for _, m in model.named_modules()
                      if hasattr(m, "weight") and hasattr(m.weight, "quant_state"))
    logger.info(f"Quantized modules: {n_quantized} Linear4bit")

    # ── Apply LoRA + Freeze base + gradient checkpointing ──
    if use_unsloth and warm_start:
        # Warm start: apply fresh LoRA via Unsloth (for optimized training), then
        # copy v7 adapter weights into the new LoRA layers
        model = FastLanguageModel.get_peft_model(
            model,
            r=LORA_CONFIG["r"],
            lora_alpha=LORA_CONFIG["lora_alpha"],
            target_modules=LORA_CONFIG["target_modules"],
            lora_dropout=LORA_CONFIG["lora_dropout"],
            bias=LORA_CONFIG["bias"],
            use_gradient_checkpointing="unsloth",
            use_rslora=LORA_CONFIG.get("use_rslora", True),
            use_dora=LORA_CONFIG["use_dora"],
        )
        # Load v7 weights into the LoRA layers
        import safetensors.torch
        adapter_file = os.path.join(warm_start, "adapter_model.safetensors")
        if not os.path.exists(adapter_file):
            adapter_file = os.path.join(warm_start, "adapter_model.bin")
            v7_state = torch.load(adapter_file, map_location="cpu", weights_only=True)
        else:
            v7_state = safetensors.torch.load_file(adapter_file)
        # Load matching keys (ignoring mismatches from different LoRA configs)
        model_state = model.state_dict()
        loaded, skipped = 0, 0
        for key, val in v7_state.items():
            if key in model_state and model_state[key].shape == val.shape:
                model_state[key].copy_(val)
                loaded += 1
            else:
                skipped += 1
        logger.info(f"WARM START: loaded {loaded} adapter weights from {warm_start} "
                    f"(skipped {skipped} mismatched)")
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

    # ── Orthogonal LoRA Initialization ("Merge before Forget") ──
    # Initialize new LoRA in the null space of previous LoRA's subspace.
    # This ensures new learning cannot interfere with previous directions.
    if prev_lora_path and os.path.exists(prev_lora_path):
        try:
            import safetensors.torch as st
            logger.info(f"Orthogonal LoRA init: loading previous adapter from {prev_lora_path}")

            # Load previous adapter weights
            prev_adapter_file = os.path.join(prev_lora_path, "adapter_model.safetensors")
            if not os.path.exists(prev_adapter_file):
                prev_adapter_file = os.path.join(prev_lora_path, "adapter_model.bin")
                prev_state = torch.load(prev_adapter_file, map_location="cpu", weights_only=True)
            else:
                prev_state = st.load_file(prev_adapter_file)

            # Build lookup of previous A/B matrices by layer
            prev_lora = {}
            for k, v in prev_state.items():
                if 'lora_A' in k or 'lora_B' in k:
                    prev_lora[k] = v

            ortho_count = 0
            for name, param in model.named_parameters():
                if 'lora_A' not in name or not param.requires_grad:
                    continue

                # Find matching previous A and B matrices
                # Name pattern: base_model.model.model.layers.N.self_attn.q_proj.lora_A.default.weight
                b_name = name.replace('lora_A', 'lora_B')
                prev_a_key = None
                prev_b_key = None
                for k in prev_lora:
                    if 'lora_A' in k and name.split('lora_A')[0] in k:
                        prev_a_key = k
                    if 'lora_B' in k and name.split('lora_A')[0].replace('lora_A', 'lora_B') in k:
                        prev_b_key = k

                # Try exact match first
                if prev_a_key is None:
                    # Try matching by the layer path portion
                    for k in prev_lora:
                        # Extract just the module path (e.g., layers.0.self_attn.q_proj)
                        curr_parts = name.replace('base_model.model.', '').split('.lora_A')[0]
                        prev_parts = k.replace('base_model.model.', '').split('.lora_A')[0]
                        if curr_parts == prev_parts and 'lora_A' in k:
                            prev_a_key = k
                        if curr_parts == prev_parts.replace('lora_B', 'lora_A').replace('lora_A', 'lora_B') and 'lora_B' in k:
                            prev_b_key = k

                if prev_a_key is None or prev_b_key is None:
                    continue

                prev_A = prev_lora[prev_a_key].float()  # [r, in]
                prev_B = prev_lora[prev_b_key].float()  # [out, r]

                # Compute effective delta and its SVD
                prev_delta = prev_B @ prev_A  # [out, in]
                try:
                    _, _, Vh = torch.linalg.svd(prev_delta, full_matrices=False)
                    # Vh shape: [min(out,in), in] — these are the input directions used

                    # Project current A init to be orthogonal to previous directions
                    new_A = param.data.float()
                    # Only use top-r singular vectors (the rank of previous LoRA)
                    r_prev = min(prev_A.shape[0], Vh.shape[0])
                    Vh_top = Vh[:r_prev, :]  # [r_prev, in]

                    # Remove previous subspace: A_ortho = A - A @ Vh^T @ Vh
                    projection = Vh_top.T @ Vh_top  # [in, in]
                    orthogonal = new_A - new_A @ projection

                    # Re-normalize to maintain initialization scale
                    orig_norm = new_A.norm()
                    ortho_norm = orthogonal.norm().clamp(min=1e-8)
                    param.data = (orthogonal * (orig_norm / ortho_norm)).to(param.dtype)
                    ortho_count += 1
                except Exception:
                    continue  # Skip layers where SVD fails

            logger.info(f"  Orthogonal init applied to {ortho_count} lora_A matrices "
                        f"(orthogonal to previous LoRA subspace)")
        except Exception as e:
            logger.warning(f"Orthogonal init failed: {e} — using default init (non-fatal)")
    elif prev_lora_path:
        logger.warning(f"Previous LoRA path not found: {prev_lora_path} — using default init")

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
    # Strip all columns except instruction/input/output — mixed types break pyarrow/tokenizer
    keep_cols = {"instruction", "input", "output"}
    drop_cols = [c for c in dataset.column_names if c not in keep_cols]
    if drop_cols:
        dataset = dataset.remove_columns(drop_cols)
        logger.info(f"Dropped columns: {drop_cols}")
    logger.info(f"EOS token: '{tokenizer.eos_token}' (id={tokenizer.eos_token_id})")

    def format_to_text(examples):
        """Convert instruction/output pairs to pre-formatted text via chat template.

        Returns a 'text' column with fully formatted strings. This bypasses Unsloth's
        internal _tokenize which can fail with messages-format datasets due to Arrow
        serialization issues.

        NOTE: Using 'text' column with DataCollatorForCompletionOnlyLM to mask
        prompt tokens from the loss. The response_template marks where assistant
        output begins in the formatted text.
        """
        all_texts = []
        n_truncated = 0
        for inst, inp, out in zip(
            examples["instruction"], examples["input"], examples["output"]
        ):
            user_content = str(inst)
            if inp:
                user_content += "\n" + str(inp)

            messages = [
                {"role": "system", "content": CODING_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": str(out)},
            ]

            # Apply chat template to get final text
            try:
                text = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=False
                )
            except Exception:
                text = f"system\n{CODING_SYSTEM_PROMPT}\nuser\n{user_content}\nassistant\n{out}"

            # Truncate long responses to fit seq_length
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
                    overhead_tokens = n_tokens - len(tokenizer.encode(str(out)))

                budget = seq_length - overhead_tokens - 1
                out_tokens = tokenizer.encode(str(out), add_special_tokens=False)[:budget]
                truncated_out = tokenizer.decode(out_tokens, skip_special_tokens=False)
                messages[-1]["content"] = truncated_out
                try:
                    text = tokenizer.apply_chat_template(
                        messages, tokenize=False, add_generation_prompt=False
                    )
                except Exception:
                    text = f"system\n{CODING_SYSTEM_PROMPT}\nuser\n{user_content}\nassistant\n{truncated_out}"
                n_truncated += 1

            all_texts.append(text)

        if n_truncated > 0:
            logger.info(f"  format_to_text: truncated {n_truncated}/{len(all_texts)} "
                        f"to fit {seq_length} tokens")
        return {"text": all_texts}

    dataset = dataset.map(format_to_text, batched=True,
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

    sample_text = dataset[0]["text"]
    sample_len = len(tokenizer.encode(sample_text))
    ends_with_eos = sample_text.rstrip().endswith("<|im_end|>")
    logger.info(f"Sample: {sample_len} tokens, ends_with_EOS={ends_with_eos}")
    logger.info(f"  First 200 chars: {sample_text[:200]}...")
    logger.info(f"  Last 200 chars: ...{sample_text[-200:]}")

    # ── EWC-LoRA Setup ──
    # Elastic Weight Consolidation: penalizes changes to important LoRA parameters
    ewc_state = {"fisher": None, "old_params": None, "enabled": False}

    if use_ewc and EWC_CONFIG["enabled"]:
        fisher_path = ewc_fisher_path
        if fisher_path and os.path.exists(fisher_path):
            logger.info(f"Loading EWC Fisher matrix from {fisher_path}")
            try:
                fisher_data = torch.load(fisher_path, map_location="cpu", weights_only=True)
                ewc_state["fisher"] = fisher_data["fisher"]
                ewc_state["old_params"] = fisher_data["old_params"]
                ewc_state["enabled"] = True
                logger.info(f"  EWC active: {len(ewc_state['fisher'])} parameter groups, "
                            f"lambda={EWC_CONFIG['lambda']}")
            except Exception as e:
                logger.warning(f"Failed to load Fisher matrix: {e} — EWC disabled")
        else:
            logger.info("No Fisher matrix found — EWC disabled (first cycle or no --fisher-path)")
    else:
        logger.info("EWC disabled" + (" (--no-ewc)" if not use_ewc else ""))

    def compute_ewc_loss(model_arg):
        """Compute EWC quadratic penalty: lambda * sum(F_i * (theta_i - theta_i_old)^2)"""
        if not ewc_state["enabled"]:
            return 0.0

        ewc_loss = torch.tensor(0.0, device=next(model_arg.parameters()).device)
        fisher = ewc_state["fisher"]
        old_params = ewc_state["old_params"]

        for name, param in model_arg.named_parameters():
            if name in fisher and param.requires_grad:
                fisher_val = fisher[name].to(param.device)
                old_val = old_params[name].to(param.device)
                ewc_loss = ewc_loss + (fisher_val * (param - old_val) ** 2).sum()

        return EWC_CONFIG["lambda"] * ewc_loss

    # ── KL-Anchored Loss Setup ──
    # Chunked approach: backbone(full seq) → lm_head(kl_slice positions only)
    # Peak logit VRAM = kl_slice × 248K × 2 bytes = ~240MB (not 970MB for full seq).
    # Compatible with CCE: we never rely on outputs.logits from the SFT pass.
    # k3 estimator: (r-1) - log(r), same as GRPO. O(seq_len) not O(seq×vocab).
    kl_state = {"disabled": False, "last_kl": 0.0, "last_sft": 0.0, "last_ewc": 0.0}
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

        # Phase 4: EWC penalty (additive, independent of KL)
        ewc_loss_val = 0.0
        if ewc_state["enabled"]:
            try:
                ewc_penalty = compute_ewc_loss(model_arg)
                if isinstance(ewc_penalty, torch.Tensor):
                    ewc_loss_val = ewc_penalty.item()
                    sft_loss = sft_loss + ewc_penalty
            except Exception as e:
                if ewc_state["enabled"]:
                    logger.warning(f"EWC loss error ({type(e).__name__}: {e}) — disabling")
                    ewc_state["enabled"] = False

        kl_state["last_kl"] = kl_loss_val
        kl_state["last_sft"] = (sft_loss.item() - KL_CONFIG["lambda"] * kl_loss_val
                                 - ewc_loss_val if kl_loss_val or ewc_loss_val
                                 else sft_loss.item())
        kl_state["last_ewc"] = ewc_loss_val

        if return_outputs:
            return sft_loss, outputs
        return sft_loss

    if use_kl or use_ewc:
        SFTTrainer.compute_loss = compute_loss_with_kl

    # ── Callbacks ──
    class V5LoggingCallback(TrainerCallback):
        def __init__(self):
            self._start_time = time.time()
            self._step_start = time.time()
            self._step_timeout = step_timeout
            self._loss_history = []  # Track all losses for regression detection
            self._diverge_warnings = 0  # Count consecutive divergence signals

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
                self._loss_history.append(loss)
                self._check_loss_health(step, total, loss, control)
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

        def _check_loss_health(self, step, total, loss, control):
            """Auto-abort if training is clearly failing."""
            # 1. Bad init: loss > 2.0 after 20 steps means something is very wrong
            if step >= 20 and step <= 30 and loss > 2.0:
                logger.error(f"QUALITY ALARM: Loss {loss:.4f} > 2.0 at step {step} — "
                             f"bad initialization, aborting to save time")
                control.should_training_stop = True
                return

            # 2. Not converging: loss > 1.0 after 25% of training
            if step > total * 0.25 and loss > 1.0:
                logger.error(f"QUALITY ALARM: Loss {loss:.4f} > 1.0 at step {step} "
                             f"({step/total*100:.0f}% through) — not converging, aborting")
                control.should_training_stop = True
                return

            # 3. Diverging: loss trending up over last 20 logged values
            if len(self._loss_history) >= 20:
                recent = self._loss_history[-20:]
                first_half = sum(recent[:10]) / 10
                second_half = sum(recent[10:]) / 10
                if second_half > first_half * 1.10:  # 10% increase
                    self._diverge_warnings += 1
                    logger.warning(f"QUALITY WARNING: Loss trending UP "
                                   f"({first_half:.4f} → {second_half:.4f}) "
                                   f"[warning {self._diverge_warnings}/3]")
                    if self._diverge_warnings >= 3:
                        logger.error(f"QUALITY ALARM: 3 consecutive divergence warnings — "
                                     f"training is getting worse, aborting")
                        control.should_training_stop = True
                else:
                    self._diverge_warnings = 0  # Reset on recovery

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

    # ── Two-Stage Training Configuration ──
    # Based on LLM4SVG paper: Stage 1 aligns output format (low LR, 1 epoch),
    # Stage 2 trains knowledge (normal LR, 2 epochs). LoRA weights persist across stages.
    TWO_STAGE_CONFIG = {
        "stage1": {"learning_rate": 1e-5, "num_train_epochs": 1, "label": "Format Alignment"},
        "stage2": {"learning_rate": 2e-5, "num_train_epochs": 2, "label": "Knowledge Training"},
    }

    if two_stage:
        stages = [
            ("stage1", TWO_STAGE_CONFIG["stage1"]),
            ("stage2", TWO_STAGE_CONFIG["stage2"]),
        ]
        logger.info("Two-stage training ENABLED (LLM4SVG-inspired)")
        logger.info(f"  Stage 1: {TWO_STAGE_CONFIG['stage1']['label']} — "
                     f"lr={TWO_STAGE_CONFIG['stage1']['learning_rate']}, "
                     f"epochs={TWO_STAGE_CONFIG['stage1']['num_train_epochs']}")
        logger.info(f"  Stage 2: {TWO_STAGE_CONFIG['stage2']['label']} — "
                     f"lr={TWO_STAGE_CONFIG['stage2']['learning_rate']}, "
                     f"epochs={TWO_STAGE_CONFIG['stage2']['num_train_epochs']}")
    else:
        stages = [("single", None)]  # Single-stage: use existing config

    # ── Build SFTConfig ──
    # Adjust batch size: Unsloth saves ~4GB VRAM, so we can go bigger
    batch_size = TRAINING_CONFIG["per_device_train_batch_size"]
    grad_accum = TRAINING_CONFIG["gradient_accumulation_steps"]
    if use_unsloth:
        batch_size = 1    # batch=1 for 14B on 16GB (fused CE loss needs VRAM headroom)
        grad_accum = 16   # Keep effective batch = 16
        logger.info(f"Unsloth QLoRA mode: batch_size={batch_size}, grad_accum={grad_accum} "
                     f"(effective={batch_size * grad_accum})")

    # Pre-formatted text column — bypasses Unsloth's _tokenize which crashes on messages format
    logger.info("Dataset format: pre-formatted text (chat template applied in format_to_text)")
    logger.info("Sequence packing: OFF")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    overall_start_time = time.time()
    final_loss = "N/A"

    from torch.utils.data import SequentialSampler

    for stage_name, stage_cfg in stages:
        # Determine LR and epochs for this stage
        if stage_cfg is not None:
            stage_lr = stage_cfg["learning_rate"]
            stage_epochs = stage_cfg["num_train_epochs"]
            stage_label = stage_cfg["label"]
            logger.info("")
            logger.info("=" * 60)
            logger.info(f"  === Stage {stage_name[-1]}: {stage_label} ===")
            logger.info(f"  lr={stage_lr}, epochs={stage_epochs}")
            logger.info("=" * 60)
        else:
            # Single-stage: use original logic
            stage_epochs = epochs_override if epochs_override > 0 else (1 if warm_start else TRAINING_CONFIG["num_train_epochs"])
            stage_lr = TRAINING_CONFIG["learning_rate"] / 2 if warm_start else TRAINING_CONFIG["learning_rate"]

        sft_kwargs = dict(
            output_dir=OUTPUT_DIR,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=grad_accum,
            num_train_epochs=stage_epochs,
            learning_rate=stage_lr,
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
            packing=False,
            dataset_text_field="text",        # Pre-formatted text (chat template already applied)
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
            if stage_cfg is None:
                logger.info("Early stopping enabled: eval every 50 steps, patience ~150 steps")

        if max_steps > 0:
            sft_kwargs["max_steps"] = max_steps
            sft_kwargs["save_steps"] = max_steps + 1
            if stage_cfg is None:
                logger.info(f"Test mode: max_steps={max_steps}")

        sft_config = SFTConfig(**sft_kwargs)

        # Early stopping callback
        callbacks = [V5LoggingCallback()]
        if eval_dataset is not None:
            from transformers import EarlyStoppingCallback
            callbacks.append(EarlyStoppingCallback(early_stopping_patience=3))  # 3 evals = 150 steps
            if stage_cfg is None:
                logger.info("EarlyStoppingCallback added (patience=3 evals)")

        # Domain probe callback: mid-training regression detection (--probe-guard)
        if probe_guard and max_steps > probe_interval:
            try:
                from domain_probe_callback import DomainProbeCallback
                probe_cb = DomainProbeCallback(
                    probe_interval=probe_interval,
                    server_url=probe_server_url,
                )
                # Set baseline from score_ledger if available
                ledger_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "score_ledger.json")
                if os.path.exists(ledger_path):
                    with open(ledger_path, "r") as f:
                        ledger = json.load(f)
                    versions = [k for k in ledger if not k.startswith("failed/")]
                    if versions:
                        latest = ledger[versions[-1]]
                        baseline = {d: s for d, s in latest.items()
                                    if isinstance(s, (int, float)) and d in ('python', 'rust', 'go', 'cpp', 'js', 'hive')}
                        if baseline:
                            probe_cb.set_baseline(baseline)
                            callbacks.append(probe_cb)
                            logger.info(f"DomainProbeCallback enabled: every {probe_interval} steps, "
                                        f"baseline from {versions[-1]}")
                        else:
                            logger.warning("Probe guard: no numeric domain scores in ledger, skipping")
                    else:
                        logger.warning("Probe guard: empty score_ledger, skipping")
                else:
                    logger.warning("Probe guard: score_ledger.json not found, skipping")
            except ImportError as e:
                logger.warning(f"Probe guard: could not import DomainProbeCallback: {e}")

        # LoRA+ optimizer: B matrix gets 16x higher LR (arXiv 2602.04998)
        lora_plus_optimizers = None
        if lora_plus:
            import torch
            a_params = [p for n, p in model.named_parameters() if "lora_A" in n and p.requires_grad]
            b_params = [p for n, p in model.named_parameters() if "lora_B" in n and p.requires_grad]
            other_params = [p for n, p in model.named_parameters()
                           if "lora_A" not in n and "lora_B" not in n and p.requires_grad]
            lora_plus_lr = stage_lr
            param_groups = [
                {"params": a_params, "lr": lora_plus_lr},
                {"params": b_params, "lr": lora_plus_lr * 16},
            ]
            if other_params:
                param_groups.append({"params": other_params, "lr": lora_plus_lr})
            lora_plus_optimizer = torch.optim.AdamW(param_groups, weight_decay=0.01)
            lora_plus_optimizers = (lora_plus_optimizer, None)  # (optimizer, scheduler=None → default)
            logger.info(f"LoRA+ enabled: A_lr={lora_plus_lr:.2e}, B_lr={lora_plus_lr * 16:.2e} (16x)")

        # Response-only loss masking: only compute loss on assistant tokens.
        # The template marks where the assistant response starts in ChatML format.
        response_template = "<|im_start|>assistant\n"
        response_collator = DataCollatorForCompletionOnlyLM(
            response_template=response_template,
            tokenizer=tokenizer,
        )

        trainer = SFTTrainer(
            model=model,
            processing_class=tokenizer,
            train_dataset=dataset,
            eval_dataset=eval_dataset,
            args=sft_config,
            callbacks=callbacks,
            data_collator=response_collator,
            optimizers=lora_plus_optimizers if lora_plus else (None, None),
        )

        # Preserve curriculum ordering
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

        # Check for existing checkpoints (only for first stage or single-stage)
        resume_checkpoint = None
        if stage_name in ("single", "stage1") and os.path.exists(OUTPUT_DIR):
            checkpoints = sorted(
                [d for d in os.listdir(OUTPUT_DIR) if d.startswith("checkpoint-")],
                key=lambda x: int(x.split("-")[-1]) if x.split("-")[-1].isdigit() else 0,
            )
            if checkpoints:
                resume_checkpoint = os.path.join(OUTPUT_DIR, checkpoints[-1])
                logger.info(f"Resuming from checkpoint: {resume_checkpoint}")

        # Final VRAM cleanup before training — free all cached allocations
        gc.collect()
        torch.cuda.empty_cache()
        pre_train_alloc = torch.cuda.memory_allocated() / 1e9
        pre_train_reserved = torch.cuda.memory_reserved() / 1e9
        pre_train_total = torch.cuda.get_device_properties(0).total_memory / 1e9
        logger.info(f"Pre-train VRAM: {pre_train_alloc:.2f}GB alloc, "
                    f"{pre_train_reserved:.2f}GB reserved, "
                    f"{pre_train_total - pre_train_reserved:.2f}GB truly free")

        if stage_cfg is not None:
            logger.info(f"Starting {stage_label} (Stage {stage_name[-1]})...")
        else:
            logger.info("Starting training...")
        sys.stderr.flush()
        stage_start_time = time.time()

        try:
            stats = trainer.train(resume_from_checkpoint=resume_checkpoint)
        except Exception as e:
            logger.error(f"Training FAILED: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            _heartbeat_stop.set()
            raise

        stage_elapsed = time.time() - stage_start_time
        stage_loss = stats.metrics.get("train_loss", "N/A")
        if stage_cfg is not None:
            logger.info(f"Stage {stage_name[-1]} ({stage_label}) complete: "
                        f"loss={stage_loss}, time={stage_elapsed:.0f}s ({stage_elapsed/3600:.1f}h)")
        else:
            logger.info(f"Training complete: loss={stage_loss}, time={stage_elapsed:.0f}s ({stage_elapsed/3600:.1f}h)")
        final_loss = stage_loss

    _heartbeat_stop.set()

    elapsed = time.time() - overall_start_time
    loss = final_loss
    if two_stage:
        logger.info(f"Two-stage training complete: final_loss={loss}, "
                    f"total_time={elapsed:.0f}s ({elapsed/3600:.1f}h)")

    # ── Save adapter ──
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    logger.info(f"Adapter saved to {OUTPUT_DIR}")

    # ── Normalize adapter config (fix absolute cache paths) ──
    adapter_config_path = os.path.join(OUTPUT_DIR, "adapter_config.json")
    if os.path.exists(adapter_config_path):
        try:
            with open(adapter_config_path, "r", encoding="utf-8") as f:
                adapter_cfg = json.load(f)
            base_path = adapter_cfg.get("base_model_name_or_path", "")
            if "/snapshots/" in base_path or "/.cache/" in base_path:
                adapter_cfg["base_model_name_or_path"] = "Qwen/Qwen2.5-Coder-14B-Instruct"
                with open(adapter_config_path, "w", encoding="utf-8") as f:
                    json.dump(adapter_cfg, f, indent=2)
                logger.info("  Normalized adapter_config.json base_model_name_or_path")
        except Exception as e:
            logger.warning(f"  Could not normalize adapter config: {e}")

    # ── Compute & save Fisher matrix for next EWC cycle ──
    if use_ewc or EWC_CONFIG["enabled"]:
        try:
            logger.info("Computing Fisher Information Matrix for EWC (next cycle)...")
            fisher = {}
            old_params = {}
            model.eval()

            # Collect LoRA parameter names
            for name, param in model.named_parameters():
                if 'lora_' in name and param.requires_grad:
                    fisher[name] = torch.zeros_like(param, device="cpu")
                    old_params[name] = param.data.clone().cpu()

            if fisher:
                # Use training dataset for Fisher computation (up to N samples)
                fisher_samples = min(EWC_CONFIG["fisher_samples"], len(dataset))
                import itertools
                fisher_loader = torch.utils.data.DataLoader(
                    dataset.select(range(fisher_samples)),
                    batch_size=1,
                    collate_fn=trainer.data_collator,
                )
                for batch in itertools.islice(fisher_loader, fisher_samples):
                    batch = {k: v.to(model.device) if hasattr(v, 'to') else v
                             for k, v in batch.items()}
                    model.zero_grad()
                    outputs = model(**batch)
                    outputs.loss.backward()
                    for name, param in model.named_parameters():
                        if name in fisher and param.grad is not None:
                            fisher[name] += (param.grad.data ** 2).cpu() / fisher_samples
                    model.zero_grad()

                fisher_save_path = os.path.join(OUTPUT_DIR, "fisher.pt")
                torch.save({"fisher": fisher, "old_params": old_params}, fisher_save_path)
                size_mb = os.path.getsize(fisher_save_path) / (1024 * 1024)
                logger.info(f"  Fisher matrix saved: {fisher_save_path} ({size_mb:.1f} MB, "
                            f"{len(fisher)} params, {fisher_samples} samples)")
            else:
                logger.warning("  No LoRA parameters found — skipping Fisher computation")
        except Exception as e:
            logger.warning(f"  Fisher computation failed: {e} — skipping (non-fatal)")

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
        "ewc_config": EWC_CONFIG if use_ewc else None,
        "ewc_enabled_during_training": ewc_state["enabled"],
        "max_seq_length": seq_length,
        "system_prompt": "CODING_SYSTEM_PROMPT (hiveai.llm.prompts)",
        "format": "ChatML via tokenizer.apply_chat_template",
        "eos_token": tokenizer.eos_token,
        "eos_token_id": tokenizer.eos_token_id,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "two_stage": two_stage,
        "two_stage_config": TWO_STAGE_CONFIG if two_stage else None,
    }
    with open(os.path.join(OUTPUT_DIR, "training_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    # ── Auto-convert LoRA to GGUF ──
    auto_convert_gguf(OUTPUT_DIR)
    adapter_gguf_path = os.path.join(OUTPUT_DIR, "adapter.gguf")

    # ── Print next steps ──
    print("\n" + "=" * 60)
    print("  Training Complete — Next Steps")
    print("=" * 60)
    if os.path.exists(adapter_gguf_path):
        print(f"""
  adapter.gguf ready at: {adapter_gguf_path}

  1. Run full cycle (merge + eval + promote):
     bash scripts/run_full_cycle.sh <domain> <data.jsonl> <version>

  2. Or quick eval:
     python scripts/quick_eval.py
""")
    else:
        print(f"""
  1. Convert LoRA to GGUF:
     python convert_lora_to_gguf.py {OUTPUT_DIR} --outfile {adapter_gguf_path} --outtype f16

  2. Quick eval:
     python scripts/quick_eval.py
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
    parser.add_argument("--epochs", type=int, default=0,
                        help="Override number of training epochs (default: 2, or 1 for warm-start)")
    parser.add_argument("--data", type=str, default=None,
                        help="Override training data JSONL path (default: v7.jsonl)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Override output directory (default: loras/v7)")
    parser.add_argument("--two-stage", action="store_true",
                        help="Enable two-stage training (LLM4SVG-inspired): "
                             "Stage 1 aligns output format (1 epoch, lr=1e-5), "
                             "Stage 2 trains knowledge (2 epochs, lr=2e-5)")
    parser.add_argument("--attn-only", action="store_true",
                        help="Train attention layers only (freeze MLP). "
                             "QAD research shows 3.2dB improvement from reduced gradient noise.")
    parser.add_argument("--init-think-tokens", action="store_true",
                        help="Initialize <think>/</think> token embeddings semantically "
                             "(LLM4SVG-inspired). Averages embeddings of related words "
                             "for faster convergence.")
    # === Continual Learning Pipeline v1.0 flags ===
    parser.add_argument("--rank", type=int, default=0,
                        help="Override LoRA rank (default: 16, use 4-8 for continual learning)")
    parser.add_argument("--lr", type=float, default=0.0,
                        help="Override learning rate directly (default: 2e-4, or 1e-4 for warm-start)")
    parser.add_argument("--lora-plus", action="store_true",
                        help="LoRA+: B matrix gets 16x higher LR than A matrix "
                             "(40-60%% faster convergence, arXiv 2602.04998)")
    parser.add_argument("--replay-dir", type=str, default=None,
                        help="Path to replay/ directory with per-domain JSONL files")
    parser.add_argument("--replay-ratio", type=float, default=0.25,
                        help="Fraction of replay data in training mix (default: 0.25)")
    parser.add_argument("--consolidation-only", action="store_true",
                        help="Consolidation mode: 1 epoch, LR/10, 100%% replay data")
    parser.add_argument("--base-model-hf", type=str, default=None,
                        help="Path to full-precision HF base model (for training on merged checkpoint)")
    parser.add_argument("--neftune-alpha", type=float, default=-1.0,
                        help="Override NEFTune noise alpha (default: 5.0, set 0 to disable)")
    # === Lossless Continual Learning flags ===
    parser.add_argument("--ewc-lambda", type=float, default=-1.0,
                        help="EWC penalty weight (default: 0.5, set 0 to disable)")
    parser.add_argument("--no-ewc", action="store_true",
                        help="Disable EWC-LoRA regularization")
    parser.add_argument("--fisher-path", type=str, default=None,
                        help="Path to Fisher matrix .pt file from previous cycle")
    parser.add_argument("--prev-lora", type=str, default=None,
                        help="Path to previous cycle's LoRA adapter for orthogonal init")
    parser.add_argument("--probe-guard", action="store_true",
                        help="Enable mid-training domain probe callback (for runs >50 steps)")
    parser.add_argument("--probe-interval", type=int, default=50,
                        help="Steps between domain probe checks (default: 50)")
    parser.add_argument("--probe-server", type=str, default="http://localhost:11435",
                        help="llama-server URL for probe checks (default: http://localhost:11435)")
    args = parser.parse_args()

    # In --test mode, auto-skip Unsloth unless --force-unsloth.
    # Unsloth's Triton JIT compilation takes 15+ minutes — the standard
    # transformers+PEFT path catches the exact same shape/VRAM/config errors.
    if args.test and not args.force_unsloth:
        args.no_unsloth = True
        logger.info("Test mode: auto-skipping Unsloth (use --force-unsloth to override)")

    model_path = args.model or BASE_MODEL

    # QAD §4: attention-only training (freeze MLP layers)
    if args.attn_only:
        LORA_CONFIG["target_modules"] = ["q_proj", "k_proj", "v_proj", "o_proj"]
        logger.info("Attention-only mode: training q/k/v/o_proj only (MLP frozen)")

    # Continual Learning: rank override
    if args.rank > 0:
        LORA_CONFIG["r"] = args.rank
        LORA_CONFIG["lora_alpha"] = args.rank * 2  # maintain 2x ratio
        logger.info(f"LoRA rank override: r={args.rank}, alpha={args.rank * 2}")

    # Consolidation mode: override LR and epochs
    if args.consolidation_only:
        base_lr = args.lr if args.lr > 0 else TRAINING_CONFIG["learning_rate"]
        args.lr = base_lr / 10  # LR/10 for consolidation
        args.epochs = args.epochs if args.epochs > 0 else 1  # 1 epoch
        logger.info(f"Consolidation mode: lr={args.lr}, epochs={args.epochs}, 100% replay")

    # NEFTune alpha override
    if args.neftune_alpha >= 0:
        TRAINING_CONFIG["neftune_noise_alpha"] = args.neftune_alpha if args.neftune_alpha > 0 else None
        logger.info(f"NEFTune alpha override: {args.neftune_alpha}" if args.neftune_alpha > 0
                    else "NEFTune disabled")

    # EWC-LoRA configuration
    use_ewc = not args.no_ewc
    if args.ewc_lambda >= 0:
        EWC_CONFIG["lambda"] = args.ewc_lambda
        if args.ewc_lambda == 0:
            use_ewc = False
        logger.info(f"EWC lambda override: {args.ewc_lambda}")
    ewc_fisher_path = args.fisher_path

    if args.data:
        TRAINING_JSONL = os.path.abspath(args.data)

    if args.output_dir:
        OUTPUT_DIR = os.path.abspath(args.output_dir)

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

    # LR override (applied after consolidation_only adjustments)
    if args.lr > 0:
        TRAINING_CONFIG["learning_rate"] = args.lr
        logger.info(f"Learning rate override: {args.lr}")

    # Base model HF override for continual learning (train on merged checkpoint)
    if args.base_model_hf:
        model_path = args.base_model_hf
        logger.info(f"Base model HF override: {model_path}")

    # Adaptive replay ratio: check score_ledger for domains that dropped last cycle
    effective_replay_ratio = args.replay_ratio
    boosted_domains = []
    ledger_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "score_ledger.json")
    if os.path.exists(ledger_path) and not args.consolidation_only:
        try:
            with open(ledger_path, "r") as f:
                ledger = json.load(f)
            versions = [k for k in ledger if not k.startswith("failed/")]
            if len(versions) >= 2:
                latest = ledger[versions[-1]]
                prev = ledger[versions[-2]]
                for domain in ['python', 'rust', 'go', 'cpp', 'js', 'hive']:
                    curr_score = latest.get(domain, 0)
                    prev_score = prev.get(domain, 0)
                    if isinstance(curr_score, (int, float)) and isinstance(prev_score, (int, float)):
                        if curr_score < prev_score - 0.01:
                            boosted_domains.append(domain)
                if boosted_domains:
                    effective_replay_ratio = min(0.40, args.replay_ratio + 0.15)
                    logger.info(f"ADAPTIVE REPLAY: domains {boosted_domains} dropped last cycle — "
                                f"boosting replay ratio {args.replay_ratio:.0%} -> {effective_replay_ratio:.0%}")
        except Exception as e:
            logger.warning(f"Could not read score_ledger for adaptive replay: {e}")

    # Replay data mixing
    if args.replay_dir and os.path.isdir(args.replay_dir):
        from pathlib import Path
        replay_files = list(Path(args.replay_dir).glob("*.jsonl"))
        if replay_files:
            import random
            random.seed(42)
            replay_samples = []
            for rf in replay_files:
                with open(rf, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            replay_samples.append(json.loads(line))
            if replay_samples and args.data:
                # Mix replay into training data at the specified ratio
                with open(args.data, "r", encoding="utf-8") as f:
                    domain_samples = [json.loads(l) for l in f if l.strip()]
                # Calculate mix: domain_count / (1 - replay_ratio) = total
                # replay_count = total * replay_ratio
                target_replay = int(len(domain_samples) * effective_replay_ratio / (1 - effective_replay_ratio))
                target_replay = min(target_replay, len(replay_samples))
                selected_replay = random.sample(replay_samples, target_replay)
                mixed = domain_samples + selected_replay
                random.shuffle(mixed)
                # Write mixed data to temp file
                mixed_path = os.path.join(os.path.dirname(args.data), f"_mixed_replay_{os.getpid()}.jsonl")
                with open(mixed_path, "w", encoding="utf-8") as f:
                    for sample in mixed:
                        # Strip metadata — mixed types crash pyarrow
                        clean = {k: v for k, v in sample.items() if k != "metadata"}
                        f.write(json.dumps(clean, ensure_ascii=False) + "\n")
                TRAINING_JSONL = mixed_path
                logger.info(f"Replay mix: {len(domain_samples)} domain + {target_replay} replay "
                            f"= {len(mixed)} total ({effective_replay_ratio:.0%} replay)")
            elif args.consolidation_only and replay_samples:
                # Consolidation mode: 100% replay
                mixed_path = os.path.join(os.path.dirname(TRAINING_JSONL), f"_consolidation_{os.getpid()}.jsonl")
                with open(mixed_path, "w", encoding="utf-8") as f:
                    for sample in replay_samples:
                        clean = {k: v for k, v in sample.items() if k != "metadata"}
                        f.write(json.dumps(clean, ensure_ascii=False) + "\n")
                TRAINING_JSONL = mixed_path
                logger.info(f"Consolidation: using {len(replay_samples)} replay samples (100%)")

    optimize_system_pre_load()
    train_v5(model_path, max_steps=args.test, use_kl=not args.no_kl,
             skip_unsloth=args.no_unsloth, step_timeout=args.step_timeout,
             seq_length_override=args.seq_length, warm_start=args.warm_start,
             epochs_override=args.epochs, two_stage=args.two_stage,
             lora_plus=args.lora_plus, use_ewc=use_ewc,
             ewc_fisher_path=ewc_fisher_path, prev_lora_path=args.prev_lora,
             probe_guard=args.probe_guard, probe_interval=args.probe_interval,
             probe_server_url=args.probe_server)
