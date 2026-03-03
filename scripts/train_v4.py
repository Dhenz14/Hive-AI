#!/usr/bin/env python3
"""
scripts/train_v4.py

HiveAI LoRA v4 — MoE-Aware Training with ESFT + KL-Anchored SFT

Building on v3's proven foundation (monkey-patched unfused experts + BnB 4-bit):
  - ESFT (Expert-Specialized Fine-Tuning): selectively LoRA-train top coding
    experts per layer (attention r=32 + expert MLP r=16)
  - KL-Anchored SFT: L = L_sft + λ·KL(π_ref ∥ π_tuned) prevents catastrophic
    forgetting while fine-tuning more parameters
  - Expert Health Monitoring: tracks routing entropy, expert usage, collapse risk
  - Foundation for eventual MoELoRA/MixLoRA in v5+

Key differences from v3:
  - v3: attention-only LoRA (q_proj, k_proj, v_proj, o_proj)
  - v4: attention LoRA (r=32) + ESFT-selected expert MLP LoRA (r=16)
  - v4: KL regularization against frozen reference model (via PEFT adapter toggle)
  - v4: per-step expert health monitoring (routing entropy, dead experts)

Usage:
    python scripts/train_v4.py                                       # full training
    python scripts/train_v4.py --test 3                              # smoke test
    python scripts/train_v4.py --esft-config scripts/esft_config.json
    python scripts/train_v4.py --generate-esft                       # generate config & exit
    python scripts/train_v4.py --no-kl                               # disable KL anchoring
    python scripts/train_v4.py --kl-lambda 0.05                     # tune KL strength
    python scripts/train_v4.py --attention-only                      # v3-style (no expert LoRA)

Requirements:
    torch, transformers>=5.2.0, peft>=0.10.0, trl>=0.24.0, datasets, bitsandbytes, psutil
    Optional: safetensors (for --generate-esft)
"""

import argparse
import gc
import json
import logging
import math
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("train_v4")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
TRAINING_JSONL = str(PROJECT_ROOT / "loras" / "training_data" / "v4.jsonl")
OUTPUT_DIR = str(PROJECT_ROOT / "loras" / "v4")
ADAPTER_GGUF = str(PROJECT_ROOT / "loras" / "v4" / "hiveai-v4-lora.gguf")
PRUNED_MODEL_DIR = str(PROJECT_ROOT / "models" / "qwen3.5-35b-a3b-pruned")
DEFAULT_ESFT_CONFIG = str(PROJECT_ROOT / "scripts" / "esft_config.json")
CONVERT_LORA_SCRIPT = str(PROJECT_ROOT / "llama.cpp" / "convert_lora_to_gguf.py")
LOG_DIR = str(PROJECT_ROOT / "logs")

# Also check common llama.cpp locations
if not os.path.exists(CONVERT_LORA_SCRIPT):
    alt = os.path.expanduser("~/llama.cpp/convert_lora_to_gguf.py")
    if os.path.exists(alt):
        CONVERT_LORA_SCRIPT = alt

# Architecture
NUM_LAYERS = 40
NUM_ACTIVE_EXPERTS = 8
MAX_SEQ_LENGTH = 4096

# ---------------------------------------------------------------------------
# LoRA Config
# ---------------------------------------------------------------------------
LORA_CONFIG = {
    "r": 32,               # attention rank
    "lora_alpha": 64,       # attention alpha (2x rank)
    "expert_r": 16,         # expert MLP rank (more modules → lower rank)
    "expert_alpha": 32,     # expert MLP alpha (2x rank)
    "lora_dropout": 0.0,
    "bias": "none",
    "use_dora": True,
    "base_targets": ["q_proj", "k_proj", "v_proj", "o_proj"],
}

# KL-Anchored SFT
KL_DEFAULTS = {
    "lambda": 0.1,         # KL weight in total loss
    "temperature": 1.0,    # softmax temperature for KL
    "seq_limit": 512,      # max tokens for KL computation (VRAM savings)
}

# Expert health monitoring
HEALTH_CONFIG = {
    "log_interval": 10,            # steps between health logs
    "dead_threshold": 0.01,        # fraction below which expert is "dead"
    "collapse_entropy_ratio": 0.3, # warn if entropy < 30% of max
}

# Training hyperparameters (same base as v3)
TRAINING_CONFIG = {
    "per_device_train_batch_size": 1,
    "gradient_accumulation_steps": 8,
    "num_train_epochs": 1,
    "learning_rate": 2e-4,
    "warmup_steps": 10,
    "lr_scheduler_type": "cosine",
    "bf16": True,
    "logging_steps": 1,
    "save_steps": 50,
    "weight_decay": 0.01,
    "max_grad_norm": 1.0,
    "seed": 42,
    "neftune_noise_alpha": 5.0,
}


# ---------------------------------------------------------------------------
# ESFT Config Generator (weight norm proxy — no GPU needed)
# ---------------------------------------------------------------------------
def generate_esft_config(model_dir, select_ratio=0.15, output_path=None):
    """
    Generate ESFT config from gate weight norms (no GPU, no model loading).

    Uses L2 norm of each expert's gate weight row as a proxy for specialization.
    Higher norm → more specialized routing → more likely a coding expert.
    This is approximate — for activation-based selection, run select_experts_esft.py.
    """
    import numpy as np

    output_path = output_path or DEFAULT_ESFT_CONFIG
    gate_re = re.compile(r"layers\.(\d+)\.mlp\.gate\.weight$")
    norms_by_layer = {}

    import glob as glob_mod
    shard_files = sorted(glob_mod.glob(os.path.join(model_dir, "model*.safetensors")))
    if not shard_files:
        logger.error(f"No safetensors shards in {model_dir}")
        return None

    logger.info(f"Scanning {len(shard_files)} shards for gate weights...")

    import torch
    from safetensors import safe_open

    for shard in shard_files:
        with safe_open(shard, framework="pt", device="cpu") as f:
            for name in f.keys():
                m = gate_re.search(name)
                if m:
                    layer_idx = int(m.group(1))
                    weights = f.get_tensor(name).float()  # (num_experts, hidden_dim)
                    norms = torch.norm(weights, dim=1).numpy()
                    norms_by_layer[layer_idx] = norms

    if not norms_by_layer:
        logger.error("No gate weights found in model shards")
        return None

    logger.info(f"Found gate weights for {len(norms_by_layer)} layers")

    # Select top experts per layer by gate weight norm
    selected = {}
    for layer_idx in sorted(norms_by_layer.keys()):
        norms = norms_by_layer[layer_idx]
        num_experts = len(norms)
        k = max(int(num_experts * select_ratio), NUM_ACTIVE_EXPERTS)
        top_indices = np.argsort(norms)[::-1][:k].tolist()
        selected[str(layer_idx)] = sorted(top_indices)

    total_selected = sum(len(v) for v in selected.values())
    total_experts = sum(len(norms_by_layer[k]) for k in norms_by_layer)

    config = {
        "method": "ESFT (gate weight norm proxy)",
        "select_ratio": select_ratio,
        "model_dir": model_dir,
        "total_selected": total_selected,
        "total_experts": total_experts,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "selected_experts": selected,
        "note": (
            "Approximate selection via gate weight norms. "
            "For activation-based selection, run select_experts_esft.py."
        ),
    }

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)

    logger.info(f"ESFT config saved: {output_path}")
    logger.info(
        f"  {total_selected}/{total_experts} experts selected "
        f"({total_selected / total_experts:.1%})"
    )

    for layer_idx in sorted(norms_by_layer.keys()):
        n = norms_by_layer[layer_idx]
        sel = selected[str(layer_idx)]
        top_norm = n[sel[0]] if sel else 0
        bar = "#" * int(len(sel) / len(n) * 30)
        print(
            f"  Layer {layer_idx:2d}: {len(sel):3d}/{len(n):3d} experts "
            f"[{bar:<30s}] top_norm={top_norm:.4f}"
        )

    return config


# ---------------------------------------------------------------------------
# ESFT Target Module Builder
# ---------------------------------------------------------------------------
def build_target_modules(esft_config=None):
    """
    Build LoRA target_modules list from ESFT config.

    Returns:
        targets: list of target module patterns (strings + regex)
        esft: parsed ESFT config dict or None
    """
    targets = list(LORA_CONFIG["base_targets"])  # always include attention

    if esft_config is None:
        logger.info("No ESFT config — attention-only LoRA (same as v3)")
        return targets

    selected = esft_config["selected_experts"]
    total_expert_modules = 0

    # Build one regex pattern per layer matching all selected experts' MLPs
    for layer_str, expert_indices in selected.items():
        if not expert_indices:
            continue
        expert_alts = "|".join(str(e) for e in expert_indices)
        proj_alts = "gate_projs|up_projs|down_projs"
        # Regex: exactly match this layer's selected expert projections
        pattern = (
            f".*layers\\.{layer_str}\\.mlp\\.experts"
            f"\\.({proj_alts})\\.({expert_alts})$"
        )
        targets.append(pattern)
        total_expert_modules += len(expert_indices) * 3

    total_experts = sum(len(v) for v in selected.values())
    logger.info(
        f"ESFT targets: {total_expert_modules} expert MLP modules "
        f"({total_experts} experts across {len(selected)} layers) + "
        f"{len(LORA_CONFIG['base_targets'])} attention modules"
    )
    return targets


# ---------------------------------------------------------------------------
# Monkey-Patch: Unfuse MoE Experts for BnB Quantization (from v3)
# ---------------------------------------------------------------------------
def patch_experts_for_quantization():
    """
    Monkey-patch Qwen3_5MoeExperts to unfuse 3D Parameter tensors into
    per-expert nn.Linear modules, enabling BitsAndBytes 4-bit quantization.

    Without this patch, BnB can't handle the fused 3D Parameters
    (experts.gate_up_proj shape [256, 1024, 2048]) — they're not nn.Linear.
    After patching, each expert gets its own nn.Linear that BnB quantizes
    to Linear4bit (~0.75MB vs 12MB per expert in bf16).
    """
    import torch
    import torch.nn as nn

    try:
        from transformers.models.qwen3_5_moe.modeling_qwen3_5_moe import (
            Qwen3_5MoeExperts,
        )
    except ImportError:
        logger.error("Cannot import Qwen3_5MoeExperts — check transformers version")
        sys.exit(1)

    _original_init = Qwen3_5MoeExperts.__init__

    def _patched_init(self, config, is_sparse=True):
        nn.Module.__init__(self)
        self.config = config
        self.is_sparse = is_sparse

        num_experts = config.num_experts if is_sparse else config.num_shared_experts
        self.num_experts = num_experts

        ffn_dim = config.intermediate_size if is_sparse else config.shared_intermediate_size
        hidden_dim = config.hidden_size

        self.gate_projs = nn.ModuleList(
            [nn.Linear(hidden_dim, ffn_dim, bias=False) for _ in range(num_experts)]
        )
        self.up_projs = nn.ModuleList(
            [nn.Linear(hidden_dim, ffn_dim, bias=False) for _ in range(num_experts)]
        )
        self.down_projs = nn.ModuleList(
            [nn.Linear(ffn_dim, hidden_dim, bias=False) for _ in range(num_experts)]
        )

    Qwen3_5MoeExperts.__init__ = _patched_init

    def _patched_forward(self, x, expert_mask=None):
        if expert_mask is not None:
            return self._forward_with_mask(x, expert_mask)
        return self._forward_single(x)

    def _forward_single(self, x):
        gate_out = self.gate_projs[0](x)
        up_out = self.up_projs[0](x)
        output = torch.nn.functional.silu(gate_out) * up_out
        return self.down_projs[0](output)

    def _forward_with_mask(self, x, expert_mask):
        batch_size, seq_len, hidden_dim = x.shape
        final_output = torch.zeros_like(x)

        for i in range(self.num_experts):
            mask_i = expert_mask[i]
            if mask_i.any():
                token_indices, = mask_i.nonzero(as_tuple=True)
                if len(token_indices) == 0:
                    continue
                expert_input = x.view(-1, hidden_dim)[token_indices]
                gate_out = self.gate_projs[i](expert_input)
                up_out = self.up_projs[i](expert_input)
                expert_out = torch.nn.functional.silu(gate_out) * up_out
                expert_out = self.down_projs[i](expert_out)
                final_output.view(-1, hidden_dim)[token_indices] += expert_out

        return final_output

    Qwen3_5MoeExperts.forward = _patched_forward
    Qwen3_5MoeExperts._forward_single = _forward_single
    Qwen3_5MoeExperts._forward_with_mask = _forward_with_mask

    logger.info("Monkey-patched Qwen3_5MoeExperts: fused 3D -> per-expert nn.Linear")


def disable_expert_fusing_converter():
    """
    Prevent transformers from re-fusing per-expert tensors during loading.

    The default weight conversion mapping merges gate_projs/up_projs into
    a single gate_up_proj Parameter. We disable this so our unfused
    nn.Linear modules load correctly from the original sharded safetensors.
    """
    try:
        from transformers.models.qwen3_5_moe import modeling_qwen3_5_moe

        if hasattr(modeling_qwen3_5_moe, "Qwen3_5MoeConverter"):
            orig = modeling_qwen3_5_moe.Qwen3_5MoeConverter

            class NoopConverter(orig):
                @classmethod
                def _get_weight_mapping(cls, config, prefix=""):
                    return {}

            modeling_qwen3_5_moe.Qwen3_5MoeConverter = NoopConverter
            logger.info("Disabled expert fusing converter")
        else:
            logger.info("No Qwen3_5MoeConverter found (safe to proceed)")
    except Exception as e:
        logger.warning(f"Could not disable converter: {e}")


# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------
def check_prerequisites(training_data, esft_config_path=None):
    """Verify all prerequisites before training."""
    errors = []
    warnings = []

    # Model
    model_path = PRUNED_MODEL_DIR
    if not os.path.isdir(model_path):
        errors.append(f"Pruned model not found: {model_path}")
    else:
        safetensors = list(Path(model_path).glob("*.safetensors"))
        if not safetensors:
            errors.append(f"No safetensors in {model_path}")
        else:
            logger.info(f"Model: {model_path} ({len(safetensors)} shards)")

    # Training data
    if not os.path.exists(training_data):
        errors.append(f"Training data not found: {training_data}")
    else:
        with open(training_data, "r", encoding="utf-8") as f:
            pair_count = sum(1 for line in f if line.strip())
        logger.info(f"Training data: {training_data} ({pair_count} pairs)")

    # ESFT config
    if esft_config_path:
        if not os.path.exists(esft_config_path):
            warnings.append(f"ESFT config not found: {esft_config_path} — will use attention-only")
        else:
            with open(esft_config_path) as f:
                esft = json.load(f)
            total = esft.get("total_selected", "?")
            logger.info(f"ESFT config: {esft_config_path} ({total} experts)")

    # Dependencies
    for pkg in ["peft", "trl", "datasets", "bitsandbytes"]:
        try:
            __import__(pkg)
        except ImportError:
            errors.append(f"{pkg} not installed. Run: pip install {pkg}")

    # GGUF converter
    if not os.path.exists(CONVERT_LORA_SCRIPT):
        warnings.append(f"LoRA GGUF converter not found: {CONVERT_LORA_SCRIPT}")

    # GPU
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
            logger.info(f"GPU: {gpu_name} ({vram:.1f} GB VRAM)")
            if vram < 14:
                warnings.append(
                    f"VRAM {vram:.1f}GB may be tight for v4 with KL anchoring. "
                    "Consider --no-kl if OOM occurs."
                )
        else:
            errors.append("No CUDA GPU detected")
    except ImportError:
        errors.append("PyTorch not installed")

    for w in warnings:
        logger.warning(f"WARNING: {w}")
    if errors:
        for e in errors:
            logger.error(f"BLOCKER: {e}")
        sys.exit(1)

    return model_path


# ---------------------------------------------------------------------------
# System Optimization (from v3)
# ---------------------------------------------------------------------------
def unload_ollama_models():
    """Free GPU memory by unloading all active Ollama models."""
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
                logger.info(f"Unloaded Ollama model: {model_name}")
    except Exception:
        pass


def optimize_system():
    """Auto-detect hardware and maximize resources for training."""
    import psutil

    logger.info("=" * 60)
    logger.info("  System Auto-Optimizer")
    logger.info("=" * 60)
    optimizations = []

    cpu_count = os.cpu_count() or 4
    ram_total = psutil.virtual_memory().total / (1024**3)
    ram_avail = psutil.virtual_memory().available / (1024**3)
    logger.info(f"  CPU: {cpu_count} cores | RAM: {ram_total:.1f}GB total, {ram_avail:.1f}GB avail")

    capability = (0, 0)
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            capability = torch.cuda.get_device_capability(0)
            logger.info(f"  GPU: {gpu_name} ({vram:.1f}GB, compute {capability[0]}.{capability[1]})")
    except Exception:
        pass

    # Kill competing GPU processes
    unload_ollama_models()

    # Check for llama-server
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        if s.connect_ex(("127.0.0.1", 11435)) == 0:
            logger.warning("  llama-server on port 11435 uses GPU VRAM!")
            logger.warning("  Consider: taskkill /f /im llama-server.exe")
        s.close()
    except Exception:
        pass

    # Process priority
    try:
        p = psutil.Process()
        if sys.platform == "win32":
            p.nice(psutil.HIGH_PRIORITY_CLASS)
        else:
            p.nice(-10)
        optimizations.append("process priority elevated")
    except (psutil.AccessDenied, OSError):
        pass

    # PyTorch threads
    try:
        import torch
        torch.set_num_threads(min(cpu_count, 8))
        torch.set_num_interop_threads(min(cpu_count // 2, 4))
        optimizations.append("PyTorch threads tuned")
    except Exception:
        pass

    # CUDA optimizations
    try:
        import torch
        if torch.cuda.is_available():
            if capability[0] >= 8:
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True
                optimizations.append("TF32 enabled")
            if hasattr(torch.backends.cuda, 'flash_sdp_enabled'):
                torch.backends.cuda.enable_flash_sdp(True)
                torch.backends.cuda.enable_mem_efficient_sdp(True)
                optimizations.append("Flash+MemEfficient SDP")
            os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "0")
            os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    except Exception:
        pass

    # GC tuning
    gc.set_threshold(700, 10, 5)
    optimizations.append("GC threshold tuned")

    logger.info(f"  Applied: {', '.join(optimizations)}")
    logger.info("=" * 60)
    return optimizations


# ---------------------------------------------------------------------------
# MoELoRATrainer — Custom SFTTrainer with KL-Anchored Loss
# ---------------------------------------------------------------------------
class MoELoRATrainer:
    """
    Wrapper that creates an SFTTrainer with KL-anchored loss and
    expert health monitoring via gate hooks.

    The KL loss prevents catastrophic forgetting by regularizing the tuned
    model's output distribution toward the frozen reference (base model).
    Reference logits are computed efficiently by toggling PEFT adapters.
    """

    @staticmethod
    def create(model, tokenizer, dataset, sft_config, callbacks,
               kl_lambda=0.1, kl_temperature=1.0, kl_seq_limit=512):
        """
        Build the trainer with custom loss function.

        Returns (trainer, gate_hooks) — caller should remove hooks after training.
        """
        import torch
        import torch.nn.functional as F
        from trl import SFTTrainer

        # Gate hook infrastructure for expert health monitoring
        gate_cache = []
        collecting_gates = [False]  # mutable container for closure
        hooks = []

        def gate_hook(module, input_tensor, output):
            if collecting_gates[0]:
                gate_cache.append(output.detach())

        # Register hooks on all MoE gate modules
        for name, module in model.named_modules():
            if re.search(r"\.mlp\.gate$", name):
                h = module.register_forward_hook(gate_hook)
                hooks.append(h)
        logger.info(f"Gate hooks: {len(hooks)} registered for health monitoring")

        # Shared state for callbacks to read
        step_state = {
            "losses": {},
            "gate_snapshot": [],
            "kl_disabled": False,
        }

        # Custom loss function with KL anchoring
        _original_compute_loss = SFTTrainer.compute_loss

        def compute_loss_with_kl(self, model, inputs, return_outputs=False,
                                 num_items_in_batch=None, **kwargs):
            # Phase 1: tuned forward (collect gate logits)
            gate_cache.clear()
            collecting_gates[0] = True

            # Build kwargs for parent compute_loss
            parent_kwargs = {}
            if num_items_in_batch is not None:
                parent_kwargs["num_items_in_batch"] = num_items_in_batch

            result = _original_compute_loss(
                self, model, inputs,
                return_outputs=True,
                **parent_kwargs,
                **kwargs,
            )

            if isinstance(result, tuple):
                sft_loss, outputs = result
            else:
                sft_loss = result
                outputs = None

            collecting_gates[0] = False
            step_state["gate_snapshot"] = list(gate_cache)

            # Phase 2: KL anchoring
            kl_loss_val = 0.0
            if kl_lambda > 0 and not step_state["kl_disabled"] and outputs is not None:
                tuned_logits = outputs.logits
                kl_slice = min(tuned_logits.shape[1], kl_seq_limit)

                try:
                    with torch.no_grad():
                        model.disable_adapter_layers()
                        ref_outputs = model(**inputs)
                        ref_logits = ref_outputs.logits[:, -kl_slice:, :].detach()
                        model.enable_adapter_layers()

                    kl_loss = F.kl_div(
                        F.log_softmax(
                            tuned_logits[:, -kl_slice:, :] / kl_temperature, dim=-1
                        ),
                        F.log_softmax(ref_logits / kl_temperature, dim=-1),
                        reduction="batchmean",
                        log_target=True,
                    ) * (kl_temperature ** 2)

                    kl_loss_val = kl_loss.item()
                    sft_loss = sft_loss + kl_lambda * kl_loss

                except torch.cuda.OutOfMemoryError:
                    model.enable_adapter_layers()
                    torch.cuda.empty_cache()
                    if not step_state["kl_disabled"]:
                        logger.warning(
                            "KL anchoring OOM — disabling for rest of training. "
                            "Use --no-kl or --kl-seq-limit to prevent."
                        )
                        step_state["kl_disabled"] = True

            step_state["losses"] = {
                "sft": (sft_loss.item() - kl_lambda * kl_loss_val)
                       if kl_loss_val else sft_loss.item(),
                "kl": kl_loss_val,
                "total": sft_loss.item(),
            }

            if return_outputs:
                return sft_loss, outputs
            return sft_loss

        # Monkey-patch the trainer class for this instance
        SFTTrainer.compute_loss = compute_loss_with_kl

        trainer = SFTTrainer(
            model=model,
            processing_class=tokenizer,
            train_dataset=dataset,
            args=sft_config,
            callbacks=callbacks,
        )

        # Attach shared state to trainer for callbacks
        trainer._v4_state = step_state
        trainer._v4_hooks = hooks

        # Preserve curriculum ordering
        from torch.utils.data import SequentialSampler
        trainer._get_train_sampler = lambda ds: SequentialSampler(ds)

        return trainer


# ---------------------------------------------------------------------------
# V4 Training Callback (logging + expert health + memory)
# ---------------------------------------------------------------------------
class V4TrainingCallback:
    """Combined callback for v4: loss logging, expert health, memory monitoring."""

    def __init__(self, health_config=None):
        from transformers import TrainerCallback
        self._health = health_config or HEALTH_CONFIG
        self._start_time = None
        self._trainer = None  # set after trainer creation

    def get_callback(self):
        """Return a TrainerCallback instance that closes over self."""
        parent = self

        from transformers import TrainerCallback
        import psutil

        class _Callback(TrainerCallback):
            def on_train_begin(self, args, state, control, **kwargs):
                parent._start_time = time.time()
                parent._log_memory(0)
                logger.info(f"Training started: {state.max_steps} total steps")

            def on_log(self, args, state, control, logs=None, **kwargs):
                if logs is None:
                    return
                step = state.global_step
                total = state.max_steps
                loss = logs.get("loss", logs.get("train_loss"))
                lr = logs.get("learning_rate")
                elapsed = time.time() - (parent._start_time or time.time())
                eta_s = (elapsed / max(step, 1)) * (total - step) if step > 0 else 0

                parts = [f"Step {step}/{total}"]
                if loss is not None:
                    parts.append(f"loss={loss:.4f}")
                if lr is not None:
                    parts.append(f"lr={lr:.2e}")

                # v4: show KL component
                if parent._trainer:
                    v4 = getattr(parent._trainer, '_v4_state', {})
                    losses = v4.get("losses", {})
                    if losses.get("kl", 0) > 0:
                        parts.append(f"kl={losses['kl']:.4f}")

                parts.append(f"elapsed={elapsed / 3600:.1f}h")
                parts.append(f"ETA={eta_s / 3600:.1f}h")
                logger.info(" | ".join(parts))
                sys.stderr.flush()

            def on_step_end(self, args, state, control, **kwargs):
                import torch

                # VRAM cleanup
                if state.global_step % 10 == 0:
                    torch.cuda.empty_cache()

                # Memory logging
                if state.global_step % 50 == 0 and state.global_step > 0:
                    parent._log_memory(state.global_step)

                # Expert health monitoring
                if (state.global_step % parent._health["log_interval"] == 0
                        and parent._trainer):
                    v4 = getattr(parent._trainer, '_v4_state', {})
                    snapshot = v4.get("gate_snapshot", [])
                    if snapshot:
                        parent._log_expert_health(state.global_step, snapshot)

        return _Callback()

    def _log_memory(self, step):
        try:
            import psutil
            proc = psutil.Process()
            ram_gb = proc.memory_info().rss / (1024**3)
            ram_avail = psutil.virtual_memory().available / (1024**3)
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
            logger.info(
                f"[MEM step={step}] RAM={ram_gb:.1f}GB used, "
                f"{ram_avail:.1f}GB avail{gpu_line}"
            )
        except Exception as e:
            logger.warning(f"[MEM] failed: {e}")

    def _log_expert_health(self, step, gate_logits_list):
        """Compute and log routing health metrics from gate logits."""
        import torch
        import numpy as np

        entropies = []
        dead_counts = []
        max_loads = []

        for gate_logits in gate_logits_list:
            if gate_logits.dim() == 3:
                gate_logits = gate_logits.reshape(-1, gate_logits.shape[-1])

            num_experts = gate_logits.shape[-1]
            num_tokens = gate_logits.shape[0]
            if num_tokens == 0:
                continue

            # Top-k routing decisions
            _, top_indices = gate_logits.topk(
                min(NUM_ACTIVE_EXPERTS, num_experts), dim=-1
            )

            # Expert usage: fraction of tokens routed to each expert
            usage = torch.zeros(num_experts, device=gate_logits.device)
            for k in range(top_indices.shape[1]):
                usage.scatter_add_(
                    0, top_indices[:, k],
                    torch.ones(num_tokens, device=gate_logits.device),
                )
            usage = usage / num_tokens

            # Routing entropy (normalized to [0, 1])
            p = usage / usage.sum().clamp(min=1e-10)
            p = p.clamp(min=1e-10)
            entropy = -(p * p.log()).sum().item()
            max_entropy = math.log(num_experts)
            entropies.append(entropy / max_entropy if max_entropy > 0 else 0)

            # Dead experts (< threshold of expected usage)
            expected = NUM_ACTIVE_EXPERTS / num_experts
            dead = (usage < expected * self._health["dead_threshold"]).sum().item()
            dead_counts.append(dead)

            # Max load (highest single expert usage)
            max_loads.append(usage.max().item())

        if not entropies:
            return

        mean_entropy = np.mean(entropies)
        mean_dead = np.mean(dead_counts)
        mean_max_load = np.mean(max_loads)

        logger.info(
            f"[HEALTH step={step}] "
            f"routing_entropy={mean_entropy:.3f} "
            f"dead_experts={mean_dead:.0f} "
            f"max_load={mean_max_load:.3f}"
        )

        if mean_entropy < self._health["collapse_entropy_ratio"]:
            logger.warning(
                f"  ROUTING COLLAPSE RISK: entropy {mean_entropy:.3f} "
                f"< threshold {self._health['collapse_entropy_ratio']}"
            )


# ---------------------------------------------------------------------------
# Main Training Function
# ---------------------------------------------------------------------------
def train_v4(model_path, training_data, esft_config=None,
             kl_lambda=0.1, kl_temperature=1.0, kl_seq_limit=512,
             max_steps=0):
    """Train LoRA v4 with ESFT expert selection and KL-anchored loss."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import LoraConfig, TaskType, get_peft_model
    from datasets import load_dataset
    from trl import SFTConfig
    import psutil

    from hiveai.llm.prompts import CODING_SYSTEM_PROMPT

    # --- Header ---
    esft_mode = "ESFT" if esft_config else "attention-only"
    kl_mode = f"λ={kl_lambda}" if kl_lambda > 0 else "disabled"
    logger.info("=" * 60)
    logger.info("  HiveAI LoRA v4 Training — MoE-Aware")
    logger.info("=" * 60)
    logger.info(f"  Base model:  {model_path}")
    logger.info(f"  Data:        {training_data}")
    logger.info(f"  Output:      {OUTPUT_DIR}")
    logger.info(f"  Mode:        {esft_mode}")
    logger.info(f"  KL anchor:   {kl_mode}")
    logger.info(
        f"  LoRA:        attention r={LORA_CONFIG['r']}, "
        f"expert r={LORA_CONFIG['expert_r']}, DoRA={LORA_CONFIG['use_dora']}"
    )
    logger.info(
        f"  Training:    batch={TRAINING_CONFIG['per_device_train_batch_size']}x"
        f"{TRAINING_CONFIG['gradient_accumulation_steps']}="
        f"{TRAINING_CONFIG['per_device_train_batch_size'] * TRAINING_CONFIG['gradient_accumulation_steps']}"
        f" effective, lr={TRAINING_CONFIG['learning_rate']}"
    )
    if max_steps:
        logger.info(f"  TEST MODE:   {max_steps} steps")
    logger.info("=" * 60)

    # Count pairs
    with open(training_data, "r", encoding="utf-8") as f:
        pair_count = sum(1 for line in f if line.strip())
    logger.info(f"Training pairs: {pair_count}")

    # --- Monkey-patches (BEFORE loading) ---
    patch_experts_for_quantization()
    disable_expert_fusing_converter()

    # --- Load model ---
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )

    logger.info("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

    logger.info("Loading model with unfused experts + BnB 4-bit...")
    load_start = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        quantization_config=bnb_config,
        device_map={"": 0},
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )
    logger.info(f"Model loaded in {time.time() - load_start:.0f}s")

    vram_alloc = torch.cuda.memory_allocated() / 1e9
    logger.info(f"VRAM after load: {vram_alloc:.1f}GB")

    # Verify no meta-device params
    meta_params = [(n, p) for n, p in model.named_parameters() if p.device.type == "meta"]
    if meta_params:
        logger.error(f"BLOCKER: {len(meta_params)} params on meta device!")
        for n, p in meta_params[:5]:
            logger.error(f"  meta: {n}")
        sys.exit(1)

    # --- Freeze + gradient checkpointing ---
    for param in model.parameters():
        param.requires_grad = False

    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()
    else:
        def _hook(module, input, output):
            output.requires_grad_(True)
        model.get_input_embeddings().register_forward_hook(_hook)

    model.gradient_checkpointing_enable(
        gradient_checkpointing_kwargs={
            "use_reentrant": False,
            "preserve_rng_state": False,
        }
    )
    logger.info("Gradient checkpointing enabled")

    # --- Build target modules ---
    target_modules = build_target_modules(esft_config)

    # --- Apply LoRA ---
    lora_kwargs = dict(
        r=LORA_CONFIG["r"],
        lora_alpha=LORA_CONFIG["lora_alpha"],
        target_modules=target_modules,
        lora_dropout=LORA_CONFIG["lora_dropout"],
        bias=LORA_CONFIG["bias"],
        task_type=TaskType.CAUSAL_LM,
        use_dora=LORA_CONFIG["use_dora"],
    )

    # Use rank_pattern for expert MLP modules (lower rank than attention)
    if esft_config:
        lora_kwargs["rank_pattern"] = {
            "gate_projs": LORA_CONFIG["expert_r"],
            "up_projs": LORA_CONFIG["expert_r"],
            "down_projs": LORA_CONFIG["expert_r"],
        }
        lora_kwargs["alpha_pattern"] = {
            "gate_projs": LORA_CONFIG["expert_alpha"],
            "up_projs": LORA_CONFIG["expert_alpha"],
            "down_projs": LORA_CONFIG["expert_alpha"],
        }

    lora_config = LoraConfig(**lora_kwargs)
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Cast LoRA params to bf16
    n_cast = 0
    for name, param in model.named_parameters():
        if param.requires_grad and param.dtype == torch.float32:
            param.data = param.data.to(torch.bfloat16)
            n_cast += 1
    if n_cast:
        logger.info(f"Cast {n_cast} LoRA params float32 -> bf16")

    vram_after_lora = torch.cuda.memory_allocated() / 1e9
    logger.info(f"VRAM after LoRA: {vram_after_lora:.1f}GB (+{vram_after_lora - vram_alloc:.1f}GB)")

    # --- Load and format dataset ---
    dataset = load_dataset("json", data_files=training_data, split="train")

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

            # Truncate if too long
            n_tokens = len(tokenizer.encode(text))
            if n_tokens > MAX_SEQ_LENGTH:
                overhead_msgs = [
                    {"role": "system", "content": CODING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": ""},
                ]
                try:
                    overhead = tokenizer.apply_chat_template(
                        overhead_msgs, tokenize=False, add_generation_prompt=False
                    )
                    overhead_tokens = len(tokenizer.encode(overhead))
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

        if n_truncated:
            logger.info(f"  Truncated {n_truncated}/{len(texts)} to {MAX_SEQ_LENGTH} tokens")
        return {"text": texts}

    dataset = dataset.map(format_prompt, batched=True)
    logger.info(f"Dataset ready: {len(dataset)} examples")

    # Validate sample
    sample = dataset[0]["text"]
    sample_len = len(tokenizer.encode(sample))
    logger.info(f"Sample: {sample_len} tokens, EOS={'<|im_end|>' in sample[-20:]}")
    logger.info(f"First 300 chars:\n{sample[:300]}")

    # --- Callback ---
    v4_cb = V4TrainingCallback(health_config=HEALTH_CONFIG)
    callback = v4_cb.get_callback()

    # --- Heartbeat ---
    _heartbeat_stop = threading.Event()

    def _heartbeat():
        n = 0
        while not _heartbeat_stop.wait(300):
            n += 1
            try:
                proc = psutil.Process()
                ram_gb = proc.memory_info().rss / (1024**3)
                logger.info(f"[HEARTBEAT #{n}] alive, RAM={ram_gb:.1f}GB")
                sys.stderr.flush()
            except Exception:
                pass

    hb_thread = threading.Thread(target=_heartbeat, daemon=True)
    hb_thread.start()

    # --- Build SFTConfig ---
    sft_kwargs = dict(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=TRAINING_CONFIG["per_device_train_batch_size"],
        gradient_accumulation_steps=TRAINING_CONFIG["gradient_accumulation_steps"],
        num_train_epochs=TRAINING_CONFIG["num_train_epochs"],
        learning_rate=TRAINING_CONFIG["learning_rate"],
        warmup_steps=TRAINING_CONFIG["warmup_steps"],
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
        optim="adamw_torch_fused",
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
        neftune_noise_alpha=TRAINING_CONFIG["neftune_noise_alpha"],
    )
    if max_steps > 0:
        sft_kwargs["max_steps"] = max_steps
        sft_kwargs["save_steps"] = max_steps + 1

    sft_config = SFTConfig(**sft_kwargs)

    # --- Create trainer ---
    trainer = MoELoRATrainer.create(
        model=model,
        tokenizer=tokenizer,
        dataset=dataset,
        sft_config=sft_config,
        callbacks=[callback],
        kl_lambda=kl_lambda,
        kl_temperature=kl_temperature,
        kl_seq_limit=kl_seq_limit,
    )

    # Link callback to trainer
    v4_cb._trainer = trainer

    # Check for resume checkpoint
    resume_checkpoint = None
    if os.path.exists(OUTPUT_DIR):
        checkpoints = sorted(
            [d for d in os.listdir(OUTPUT_DIR) if d.startswith("checkpoint-")],
            key=lambda x: int(x.split("-")[-1]) if x.split("-")[-1].isdigit() else 0,
        )
        if checkpoints:
            resume_checkpoint = os.path.join(OUTPUT_DIR, checkpoints[-1])
            logger.info(f"Resuming from: {resume_checkpoint}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- Train ---
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
        # Clean up gate hooks
        for h in getattr(trainer, '_v4_hooks', []):
            h.remove()

    elapsed = time.time() - start_time
    loss = stats.metrics.get("train_loss", "N/A")
    logger.info(f"Training complete: loss={loss}, time={elapsed:.0f}s ({elapsed / 3600:.1f}h)")

    # Save
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    logger.info(f"Adapter saved to {OUTPUT_DIR}")

    # Metadata
    meta = {
        "version": "v4.0",
        "base_model": model_path,
        "pair_count": pair_count,
        "loss": loss if isinstance(loss, (int, float)) else None,
        "training_time_s": round(elapsed),
        "lora_config": LORA_CONFIG,
        "training_config": TRAINING_CONFIG,
        "kl_config": {
            "lambda": kl_lambda,
            "temperature": kl_temperature,
            "seq_limit": kl_seq_limit,
        },
        "esft_config": esft_config.get("method", "none") if esft_config else "attention-only",
        "esft_total_experts": esft_config.get("total_selected", 0) if esft_config else 0,
        "max_seq_length": MAX_SEQ_LENGTH,
        "system_prompt": "CODING_SYSTEM_PROMPT (hiveai.llm.prompts)",
        "format": "ChatML via tokenizer.apply_chat_template",
        "pruning": "128/256 experts, 55% routing capacity retained",
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(os.path.join(OUTPUT_DIR, "training_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    return loss


# ---------------------------------------------------------------------------
# GGUF Conversion
# ---------------------------------------------------------------------------
def convert_to_gguf():
    """Convert LoRA adapter to GGUF for llama-server."""
    if not os.path.exists(CONVERT_LORA_SCRIPT):
        logger.warning("Skipping GGUF conversion (converter not found)")
        return None

    if not os.path.exists(os.path.join(OUTPUT_DIR, "adapter_config.json")):
        logger.error(f"No adapter found at {OUTPUT_DIR}")
        return None

    logger.info(f"Converting LoRA adapter to GGUF: {ADAPTER_GGUF}")
    cmd = [
        sys.executable, CONVERT_LORA_SCRIPT,
        "--base", PRUNED_MODEL_DIR,
        "--outfile", ADAPTER_GGUF,
        "--outtype", "f16",
        OUTPUT_DIR,
    ]
    logger.info(f"  {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        logger.error(f"GGUF conversion failed:\n{result.stderr[:1000]}")
        return None

    if os.path.exists(ADAPTER_GGUF):
        size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
        logger.info(f"LoRA GGUF created: {ADAPTER_GGUF} ({size_mb:.0f} MB)")
        return ADAPTER_GGUF

    logger.error("GGUF conversion produced no output file")
    return None


def print_next_steps():
    """Print deployment instructions."""
    print("\n" + "=" * 60)
    print("  v4 Training Complete — Next Steps")
    print("=" * 60)
    print(f"""
  RECOMMENDED: Use the deploy script:
     python scripts/deploy_v4.py --now --eval

  OR manually:

  1. Start llama-server with v4 LoRA:
     "C:/Users/theyc/llama.cpp/bin/llama-server.exe" \\
       -m "models/qwen3.5-35b-a3b/Qwen3.5-35B-A3B-Q4_K_M.gguf" \\
       --lora "loras/v4/hiveai-v4-lora.gguf" \\
       --port 11435 --n-gpu-layers 999 --ctx-size 16384 --threads 2 \\
       -b 4096 -fa --cache-type-k q8_0 --cache-type-v q4_0 --no-mmap --mlock

  2. Run eval:
     python scripts/run_eval.py --model hiveai-v4 \\
       --base-url http://localhost:11435

  3. Compare: qwen3:14b=0.741, hiveai-v1=0.853 (+15%%)
""")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train HiveAI LoRA v4 (MoE-Aware)")
    parser.add_argument("--test", type=int, default=0,
                        help="Smoke test: run N steps then stop")
    parser.add_argument("--esft-config", default=None,
                        help="Path to ESFT config JSON (expert selection)")
    parser.add_argument("--generate-esft", action="store_true",
                        help="Generate ESFT config from gate weights and exit")
    parser.add_argument("--esft-ratio", type=float, default=0.15,
                        help="ESFT select ratio (default: 0.15 = top 15%%)")
    parser.add_argument("--attention-only", action="store_true",
                        help="v3-style attention-only LoRA (no expert training)")
    parser.add_argument("--no-kl", action="store_true",
                        help="Disable KL anchoring")
    parser.add_argument("--kl-lambda", type=float, default=KL_DEFAULTS["lambda"],
                        help=f"KL loss weight (default: {KL_DEFAULTS['lambda']})")
    parser.add_argument("--kl-temperature", type=float, default=KL_DEFAULTS["temperature"],
                        help=f"KL softmax temperature (default: {KL_DEFAULTS['temperature']})")
    parser.add_argument("--kl-seq-limit", type=int, default=KL_DEFAULTS["seq_limit"],
                        help=f"Max tokens for KL computation (default: {KL_DEFAULTS['seq_limit']})")
    parser.add_argument("--data", default=TRAINING_JSONL,
                        help=f"Training data path (default: {TRAINING_JSONL})")
    args = parser.parse_args()

    # --- ESFT config generation mode ---
    if args.generate_esft:
        logger.info("ESFT Config Generator (gate weight norm proxy)")
        if not os.path.isdir(PRUNED_MODEL_DIR):
            logger.error(f"Model not found: {PRUNED_MODEL_DIR}")
            sys.exit(1)
        config = generate_esft_config(
            PRUNED_MODEL_DIR,
            select_ratio=args.esft_ratio,
            output_path=DEFAULT_ESFT_CONFIG,
        )
        if config:
            print(f"\n  Next: python scripts/train_v4.py --esft-config {DEFAULT_ESFT_CONFIG}")
        sys.exit(0)

    # --- Training mode ---
    # Set up file logging
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, "train_v4_full.log")
    file_handler = logging.FileHandler(log_file, mode="a")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(file_handler)

    logger.info("HiveAI LoRA v4 Training Pipeline — MoE-Aware")
    logger.info("Base: Qwen3.5-35B-A3B-pruned (128/256 experts, 55% capacity)")

    # ESFT config
    esft_config = None
    if not args.attention_only:
        esft_path = args.esft_config or DEFAULT_ESFT_CONFIG
        if os.path.exists(esft_path):
            with open(esft_path) as f:
                esft_config = json.load(f)
            logger.info(f"ESFT config loaded: {esft_path}")
        elif args.esft_config:
            logger.error(f"ESFT config not found: {args.esft_config}")
            sys.exit(1)
        else:
            logger.info("No ESFT config found — run --generate-esft first, or use --attention-only")
            logger.info("Falling back to attention-only LoRA")

    # KL config
    kl_lambda = 0 if args.no_kl else args.kl_lambda

    # System prep
    unload_ollama_models()
    optimize_system()
    check_prerequisites(args.data, args.esft_config)

    if args.test:
        logger.info(f"SMOKE TEST: {args.test} steps")
        loss = train_v4(
            PRUNED_MODEL_DIR, args.data, esft_config,
            kl_lambda=kl_lambda,
            kl_temperature=args.kl_temperature,
            kl_seq_limit=args.kl_seq_limit,
            max_steps=args.test,
        )
        logger.info(f"Smoke test complete. Loss: {loss}")
    else:
        loss = train_v4(
            PRUNED_MODEL_DIR, args.data, esft_config,
            kl_lambda=kl_lambda,
            kl_temperature=args.kl_temperature,
            kl_seq_limit=args.kl_seq_limit,
        )
        convert_to_gguf()
        print_next_steps()
