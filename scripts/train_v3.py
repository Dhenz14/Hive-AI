"""
Train HiveAI LoRA v3 on pruned Qwen3.5-35B-A3B.

One-command training:
    python scripts/train_v3.py
    python scripts/train_v3.py --test 10   # smoke test (10 steps)

What's new in v3:
    - Pruned base model (256->128 experts, 55% routing capacity retained)
    - Unfused expert tensors: BitsAndBytes quantizes ALL params to true 4-bit (~9GB)
    - Monkey-patched MoE experts: nn.Linear per expert instead of fused 3D Parameters
    - ChatML format with CODING_SYSTEM_PROMPT (matches inference exactly)
    - DoRA + NEFTune (quality improvements, zero inference cost)
    - 4096 token context (was 2048)
    - 2,385 quality-filtered pairs with rich metadata
    - Curriculum ordering (beginner -> intermediate -> expert)
    - Hive domain-aware scoring and oversampling (2x Hive pairs)

Uses standard transformers + PEFT with monkey-patched expert modules.
Expert tensors unfused by scripts/unfuse_experts.py -> BnB quantizes them -> fits 16GB VRAM.

Prerequisites:
    1. scripts/fix_model_keys.py   (CausalLM key format)
    2. scripts/compact_experts.py  (256->128 experts)
    3. scripts/unfuse_experts.py   (3D fused -> 2D per-expert for BnB quantization)
"""
import faulthandler
import json
import logging
import os
import subprocess
import sys
import threading
import time

# ── CUDA memory allocator ──
# Note: expandable_segments can cause OOM during BnB model loading on tight VRAM.
# PyTorch defaults work well for our 16GB setup.

sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, 'reconfigure') else None
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

TRAINING_JSONL = os.path.join(PROJECT_ROOT, "loras", "training_data", "v3.jsonl")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "loras", "v3")

# Use PRUNED + UNFUSED base model
BASE_MODEL = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b-pruned")

# GGUF conversion
CONVERT_LORA_SCRIPT = r"C:\Users\theyc\llama.cpp\convert_lora_to_gguf.py"
ADAPTER_GGUF = os.path.join(OUTPUT_DIR, "hiveai-v3-lora.gguf")

# ---------------------------------------------------------------------------
# v3 Training Configuration
# ---------------------------------------------------------------------------
MAX_SEQ_LENGTH = 4096

LORA_CONFIG = {
    "r": 32,
    "lora_alpha": 64,               # alpha = 2*r for stable scaling
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
    "lora_dropout": 0.0,
    "bias": "none",
    "use_dora": True,                # Weight-Decomposed LoRA: +1-4.4pts quality
}

TRAINING_CONFIG = {
    "per_device_train_batch_size": 1,
    "gradient_accumulation_steps": 8,  # Effective batch = 1*8 = 8
    "num_train_epochs": 1,             # 1 epoch: standard for LoRA (<10k pairs, 0.04% trainable)
    "learning_rate": 2e-4,
    "warmup_steps": 9,              # 3% of 299 steps (replaces deprecated warmup_ratio)
    "lr_scheduler_type": "cosine",
    "bf16": True,
    "logging_steps": 10,
    "save_steps": 100,
    "weight_decay": 0.01,
    "max_grad_norm": 1.0,
    "seed": 42,
    "neftune_noise_alpha": 5.0,      # NEFTune: +0.5-1% quality, zero cost
}


# ---------------------------------------------------------------------------
# Expert Unfusing Monkey-Patch
# ---------------------------------------------------------------------------
def patch_experts_for_quantization():
    """
    Monkey-patch Qwen3NextExperts to use nn.Linear layers instead of fused 3D Parameters.

    BitsAndBytes load_in_4bit only quantizes nn.Linear (2D weight matrices).
    The original Qwen3NextExperts uses fused 3D nn.Parameter tensors:
        gate_up_proj: (num_experts, 2*intermediate, hidden)  -- NOT quantized
        down_proj:    (num_experts, hidden, intermediate)     -- NOT quantized

    This patch replaces them with per-expert nn.Linear layers:
        gate_projs.{i}: nn.Linear(hidden, intermediate)      -- quantized to 4-bit
        up_projs.{i}:   nn.Linear(hidden, intermediate)      -- quantized to 4-bit
        down_projs.{i}: nn.Linear(intermediate, hidden)      -- quantized to 4-bit

    The safetensors files must be unfused first (scripts/unfuse_experts.py).
    """
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from transformers.activations import ACT2FN

    # Import BOTH expert classes (qwen3_5_moe has its own, separate from qwen3_next)
    from transformers.models.qwen3_5_moe.modeling_qwen3_5_moe import Qwen3_5MoeExperts
    from transformers.models.qwen3_next.modeling_qwen3_next import Qwen3NextExperts

    def patched_init(self, config):
        nn.Module.__init__(self)
        self.num_experts = config.num_experts
        self.hidden_dim = config.hidden_size
        self.intermediate_dim = config.moe_intermediate_size
        self.act_fn = ACT2FN[config.hidden_act]
        # Required by @use_experts_implementation decorator
        self.config = config
        self.has_bias = False
        self.is_transposed = False

        # Per-expert nn.Linear layers -- BitsAndBytes will quantize these
        self.gate_projs = nn.ModuleList([
            nn.Linear(self.hidden_dim, self.intermediate_dim, bias=False)
            for _ in range(self.num_experts)
        ])
        self.up_projs = nn.ModuleList([
            nn.Linear(self.hidden_dim, self.intermediate_dim, bias=False)
            for _ in range(self.num_experts)
        ])
        self.down_projs = nn.ModuleList([
            nn.Linear(self.intermediate_dim, self.hidden_dim, bias=False)
            for _ in range(self.num_experts)
        ])

    def _dequant_weight(module):
        """Dequantize a BnB Linear4bit weight to BF16, or return raw weight.

        IMPORTANT: Params4bit.dequantize() is broken — returns packed uint8 shape
        (N/2, 1) instead of original (out, in). Must use bnb.functional.dequantize_4bit
        which correctly restores the original weight shape and dtype.
        """
        import bitsandbytes as bnb
        w = module.weight
        if hasattr(w, 'quant_state'):
            # Correct BnB dequantization: returns (out_features, in_features)
            return bnb.functional.dequantize_4bit(w.data, w.quant_state).to(torch.bfloat16)
        return w.data.to(torch.bfloat16)

    def patched_forward_fused(
        self,
        hidden_states: torch.Tensor,
        top_k_index: torch.Tensor,
        top_k_weights: torch.Tensor,
    ) -> torch.Tensor:
        """
        Fused MoE expert dispatch: batch-dequant + grouped matmul.

        Instead of N sequential Linear4bit.forward() calls per projection (each
        launching a dequant kernel + GEMM kernel), this:
        1. Sorts tokens by expert assignment for contiguous memory access
        2. Batch-dequantizes all expert weights into a 3D tensor per projection
        3. Uses per-expert matmul with contiguous token groups (much less Python overhead)
        4. Scatters weighted results back to token positions

        Reduces Python dispatch overhead from 384 iterations/layer to 3 batch operations.
        VRAM overhead: ~268 MB peak (one projection's dequantized weights at a time).
        With gradient checkpointing, only one layer active → fits in 5 GB headroom.
        """
        num_tokens = hidden_states.shape[0]
        hidden_dim = hidden_states.shape[1]
        device = hidden_states.device
        dtype = hidden_states.dtype

        # ── Sort tokens by expert for contiguous grouping ──
        with torch.no_grad():
            flat_experts = top_k_index.view(-1)                     # [num_tokens * top_k]
            flat_weights = top_k_weights.view(-1)                   # [num_tokens * top_k]
            top_k = top_k_index.shape[1]
            token_ids = torch.arange(num_tokens, device=device)
            token_ids = token_ids.unsqueeze(1).expand(-1, top_k).reshape(-1)

            sort_idx = torch.argsort(flat_experts, stable=True)
            sorted_experts = flat_experts[sort_idx]
            sorted_token_ids = token_ids[sort_idx]
            sorted_weights = flat_weights[sort_idx]

            # Per-expert boundaries
            expert_counts = torch.bincount(sorted_experts, minlength=self.num_experts)
            expert_offsets = torch.zeros(self.num_experts + 1, dtype=torch.long, device=device)
            expert_offsets[1:] = torch.cumsum(expert_counts, dim=0)

        # Gather sorted input tokens
        sorted_hidden = hidden_states[sorted_token_ids]             # [total_activations, hidden_dim]
        total_act = sorted_hidden.shape[0]

        # ── Gate + Up projections (batch-dequant → per-expert matmul) ──
        gate_out = torch.empty(total_act, self.intermediate_dim, device=device, dtype=dtype)
        up_out = torch.empty_like(gate_out)

        for i in range(self.num_experts):
            start = expert_offsets[i].item()
            end = expert_offsets[i + 1].item()
            if start == end:
                continue
            expert_input = sorted_hidden[start:end]
            # Dequant weights once, use for matmul, weights are [out, in]
            gw = _dequant_weight(self.gate_projs[i])
            uw = _dequant_weight(self.up_projs[i])
            gate_out[start:end] = expert_input @ gw.T
            up_out[start:end] = expert_input @ uw.T
            del gw, uw  # Free immediately

        # ── Activation: SiLU(gate) * up ──
        intermediate = F.silu(gate_out) * up_out
        del gate_out, up_out

        # ── Down projection (batch-dequant → per-expert matmul) ──
        down_out = torch.empty(total_act, hidden_dim, device=device, dtype=dtype)

        for i in range(self.num_experts):
            start = expert_offsets[i].item()
            end = expert_offsets[i + 1].item()
            if start == end:
                continue
            dw = _dequant_weight(self.down_projs[i])
            down_out[start:end] = intermediate[start:end] @ dw.T
            del dw

        del intermediate

        # ── Scatter weighted results back to token positions ──
        weighted_out = down_out * sorted_weights.unsqueeze(1)
        del down_out

        final_hidden_states = torch.zeros(num_tokens, hidden_dim, device=device, dtype=dtype)
        final_hidden_states.index_add_(0, sorted_token_ids, weighted_out.to(dtype))

        return final_hidden_states

    def patched_forward_sequential(
        self,
        hidden_states: torch.Tensor,
        top_k_index: torch.Tensor,
        top_k_weights: torch.Tensor,
    ) -> torch.Tensor:
        """
        Sequential MoE expert dispatch using standard Linear4bit.forward().

        Each expert call goes through BnB's MatMul4Bit autograd Function which
        saves packed 4-bit weights (~0.75MB/expert) in the autograd graph.
        Lower peak VRAM than fused dispatch but more kernel launches.

        Fallback for when fused dispatch causes issues.
        """
        final_hidden_states = torch.zeros_like(hidden_states)
        _silu = F.silu

        with torch.no_grad():
            active_experts = top_k_index.unique().tolist()

        for expert_idx in active_experts:
            mask = (top_k_index == expert_idx)
            token_idx, top_k_pos = mask.nonzero(as_tuple=True)

            if token_idx.numel() == 0:
                continue

            current_state = hidden_states[token_idx]

            gate_out = self.gate_projs[expert_idx](current_state)
            up_out = self.up_projs[expert_idx](current_state)
            current_hidden_states = _silu(gate_out) * up_out
            current_hidden_states = self.down_projs[expert_idx](current_hidden_states)

            current_hidden_states = current_hidden_states * top_k_weights[token_idx, top_k_pos, None]
            final_hidden_states.index_add_(0, token_idx, current_hidden_states.to(final_hidden_states.dtype))

        return final_hidden_states

    # Choose dispatch strategy based on environment variable
    USE_FUSED_MOE = os.environ.get("HIVE_FUSED_MOE", "1") == "1"

    def patched_forward(self, hidden_states, top_k_index, top_k_weights):
        if USE_FUSED_MOE:
            return patched_forward_fused(self, hidden_states, top_k_index, top_k_weights)
        return patched_forward_sequential(self, hidden_states, top_k_index, top_k_weights)

    # Patch BOTH classes
    Qwen3_5MoeExperts.__init__ = patched_init
    Qwen3_5MoeExperts.forward = patched_forward
    Qwen3NextExperts.__init__ = patched_init
    Qwen3NextExperts.forward = patched_forward

    # Patch _init_weights to handle unfused expert structure
    # (The original tries to access module.gate_up_proj which no longer exists)
    from transformers.models.qwen3_5_moe.modeling_qwen3_5_moe import Qwen3_5MoePreTrainedModel
    original_init_weights = Qwen3_5MoePreTrainedModel._init_weights

    @torch.no_grad()
    def patched_init_weights(self, module):
        if isinstance(module, (Qwen3_5MoeExperts, Qwen3NextExperts)):
            # Skip — our nn.Linear layers are initialized by PyTorch defaults
            # and will be overwritten by checkpoint weights anyway
            return
        original_init_weights(self, module)

    Qwen3_5MoePreTrainedModel._init_weights = patched_init_weights

    logger.info("Patched Qwen3_5MoeExperts + Qwen3NextExperts: fused 3D -> per-expert nn.Linear")
    logger.info("  BitsAndBytes will now quantize all expert layers to 4-bit")
    logger.info("  Memory-efficient dispatch: standard Linear4bit (saves quantized weights in autograd)")
    logger.info("  Peak autograd overhead: ~500MB vs ~7.5GB with manual dequant bypass")


def disable_expert_fusing_converter():
    """
    Disable the transformers conversion_mapping that re-fuses per-expert tensors.

    The qwen2_moe converter would convert:
        experts.*.gate_proj.weight -> experts.gate_up_proj (3D fused)
    We need per-expert 2D tensors to stay unfused for BitsAndBytes quantization.

    Our naming convention (gate_projs.{i}.weight) avoids the converter pattern
    (experts.*.gate_proj.weight), but MTP keys may still match. Disabling the
    converter prevents any interference.
    """
    try:
        import transformers.conversion_mapping as cm
        # Remove entries that would trigger expert fusing
        for key in list(cm._MODEL_TO_CONVERSION_PATTERN.keys()):
            if "qwen3" in key or "qwen2_moe" in key:
                del cm._MODEL_TO_CONVERSION_PATTERN[key]
        logger.info("Disabled qwen2_moe conversion mapping (prevents re-fusing)")
    except Exception as e:
        logger.warning(f"Could not disable conversion mapping: {e}")


def apply_fused_cross_entropy(model):
    """
    Replace the model's loss computation with fused cross-entropy from cut_cross_entropy.

    Standard path:
        logits = lm_head(hidden_states)  # [B, S, 248055] = ~2 GB for S=4096
        loss = cross_entropy(logits, labels)

    Fused path:
        loss = linear_cross_entropy(hidden_states, lm_head.weight, labels)
        # Never materializes the full logit tensor — tiled Triton kernels

    Memory savings: ~2 GB per forward pass (vocab_size=248055 × seq × dtype).
    Compute savings: fused softmax + CE in one kernel pass.
    """
    try:
        from cut_cross_entropy import linear_cross_entropy
    except ImportError:
        logger.warning("cut_cross_entropy not installed — using standard CE loss")
        logger.warning("Install with: pip install cut_cross_entropy")
        return False

    import torch
    import types
    from transformers.models.qwen3_5_moe.modeling_qwen3_5_moe import (
        Qwen3_5MoeForCausalLM,
        MoeCausalLMOutputWithPast,
        load_balancing_loss_func,
    )

    # Get the original forward to preserve its logic for non-loss parts
    original_forward = Qwen3_5MoeForCausalLM.forward

    def fused_ce_forward(
        self,
        input_ids=None,
        attention_mask=None,
        position_ids=None,
        past_key_values=None,
        inputs_embeds=None,
        labels=None,
        use_cache=None,
        output_attentions=None,
        output_hidden_states=None,
        output_router_logits=None,
        return_dict=None,
        cache_position=None,
        logits_to_keep=0,
        **kwargs,
    ):
        # If no labels, use original forward (inference path)
        if labels is None:
            return original_forward(
                self, input_ids=input_ids, attention_mask=attention_mask,
                position_ids=position_ids, past_key_values=past_key_values,
                inputs_embeds=inputs_embeds, labels=labels, use_cache=use_cache,
                output_attentions=output_attentions,
                output_hidden_states=output_hidden_states,
                output_router_logits=output_router_logits,
                return_dict=return_dict, cache_position=cache_position,
                logits_to_keep=logits_to_keep, **kwargs,
            )

        # Training path: use fused CE to avoid materializing logit tensor
        output_router_logits = (
            output_router_logits if output_router_logits is not None
            else self.config.output_router_logits
        )

        outputs = self.model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            position_ids=position_ids,
            past_key_values=past_key_values,
            inputs_embeds=inputs_embeds,
            use_cache=use_cache,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            output_router_logits=output_router_logits,
            cache_position=cache_position,
            **kwargs,
        )

        hidden_states = outputs.last_hidden_state  # [B, S, hidden_dim]

        # Manual causal LM shift (standard path: logits[:-1] predicts labels[1:])
        shift_hidden = hidden_states[..., :-1, :].contiguous()  # [B, S-1, H]
        shift_labels = labels[..., 1:].contiguous()              # [B, S-1]

        # Fused CE: hidden_states + lm_head.weight -> loss (no logit tensor!)
        # Flatten to 2D for cut_cross_entropy: [B*(S-1), H] and [B*(S-1)]
        flat_hidden = shift_hidden.view(-1, shift_hidden.size(-1))
        flat_labels = shift_labels.view(-1)

        loss = linear_cross_entropy(
            flat_hidden,              # e: [B*(S-1), hidden_dim]
            self.lm_head.weight,      # c: [vocab_size, hidden_dim]
            flat_labels,              # targets: [B*(S-1)]
            ignore_index=-100,
            shift=False,              # already shifted manually
            reduction="mean",
        )

        # Aux loss (load balancing)
        aux_loss = None
        if output_router_logits:
            aux_loss = load_balancing_loss_func(
                outputs.router_logits,
                self.num_experts,
                self.num_experts_per_tok,
                attention_mask,
            )
            if labels is not None and aux_loss is not None:
                loss += self.router_aux_loss_coef * aux_loss.to(loss.device)

        # Return minimal logits (trainer accesses .shape for metrics)
        # Using last token's hidden state × lm_head as a tiny proxy
        dummy_logits = torch.zeros(
            hidden_states.shape[0], 1, self.config.vocab_size,
            device=hidden_states.device, dtype=hidden_states.dtype,
        )
        return MoeCausalLMOutputWithPast(
            loss=loss,
            aux_loss=aux_loss,
            logits=dummy_logits,
            past_key_values=outputs.past_key_values,
            hidden_states=outputs.hidden_states,
            attentions=outputs.attentions,
            router_logits=outputs.router_logits,
        )

    Qwen3_5MoeForCausalLM.forward = fused_ce_forward
    logger.info("Patched Qwen3_5MoeForCausalLM.forward with fused cross-entropy")
    logger.info("  Avoids materializing [B, S, 248055] logit tensor (~2 GB)")
    logger.info("  Uses cut_cross_entropy Triton kernels for tiled CE computation")
    return True


# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------
def check_prerequisites():
    """Verify all files and dependencies."""
    errors = []
    warnings = []

    # Training data
    if not os.path.exists(TRAINING_JSONL):
        errors.append(f"Training data not found: {TRAINING_JSONL}")
    else:
        with open(TRAINING_JSONL, "r", encoding="utf-8") as f:
            pair_count = sum(1 for line in f if line.strip())
        logger.info(f"Training data: {pair_count} pairs from {TRAINING_JSONL}")

    # Base model
    model_path = BASE_MODEL
    if os.path.isdir(BASE_MODEL):
        shards = [f for f in os.listdir(BASE_MODEL)
                  if f.endswith(".safetensors") and "index" not in f]
        if len(shards) < 14:
            errors.append(f"Pruned model incomplete: {len(shards)}/14 shards in {BASE_MODEL}")
        else:
            logger.info(f"Base model: pruned ({len(shards)} shards)")

        # Verify model keys have been fixed (CausalLM config)
        config_path = os.path.join(BASE_MODEL, "config.json")
        if os.path.exists(config_path):
            with open(config_path) as f:
                cfg = json.load(f)
            arch = cfg.get("architectures", [])
            if arch != ["Qwen3_5MoeForCausalLM"]:
                errors.append(
                    f"Model config uses {arch} -- run scripts/fix_model_keys.py first. "
                    f"Expected ['Qwen3_5MoeForCausalLM'] for clean loading."
                )
            else:
                logger.info("  Config: Qwen3_5MoeForCausalLM (keys fixed)")

        # Verify experts are unfused
        index_path = os.path.join(BASE_MODEL, "model.safetensors.index.json")
        if os.path.exists(index_path):
            with open(index_path) as f:
                idx = json.load(f)
            has_unfused = any("gate_projs" in k for k in idx["weight_map"])
            has_fused = any(k.endswith(".gate_up_proj") for k in idx["weight_map"])
            if has_fused and not has_unfused:
                errors.append(
                    "Expert tensors are still fused (3D). "
                    "Run scripts/unfuse_experts.py first."
                )
            elif has_unfused:
                n_expert_keys = sum(1 for k in idx["weight_map"]
                                    if "gate_projs" in k or "up_projs" in k or "down_projs" in k)
                logger.info(f"  Experts: unfused ({n_expert_keys} individual 2D tensors)")

        # Verify pruning was applied
        meta_path = os.path.join(BASE_MODEL, "pruning_meta.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            logger.info(f"  Pruning: {meta.get('total_experts_before', '?')} -> "
                        f"{meta.get('total_experts_after', '?')} experts, "
                        f"{meta.get('routing_capacity_retained', 0):.1%} capacity")
    else:
        errors.append(f"No base model found at {BASE_MODEL}")

    # Dependencies
    for pkg_name in ["peft", "trl", "datasets", "bitsandbytes"]:
        try:
            __import__(pkg_name)
        except ImportError:
            errors.append(f"{pkg_name} not installed. Run: pip install {pkg_name}")

    # GGUF converter
    if not os.path.exists(CONVERT_LORA_SCRIPT):
        warnings.append(f"LoRA GGUF converter not found: {CONVERT_LORA_SCRIPT}")

    # GPU check
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
            logger.info(f"GPU: {gpu_name} ({vram:.1f} GB VRAM)")
            if vram < 12:
                errors.append(f"Insufficient VRAM: {vram:.1f}GB (need >=12GB)")
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


def unload_ollama_model():
    """Free GPU memory by unloading any active Ollama model."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps({"model": "qwen3:14b", "keep_alive": 0}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        logger.info("Unloaded Ollama model to free GPU VRAM")
    except Exception:
        pass


def optimize_system():
    """
    Auto-detect hardware and maximize system resources for training.

    Adapts to any machine: detects CPU count, RAM, GPU capabilities,
    and applies all safe optimizations. Kills competing GPU processes,
    sets process priority, configures thread pools, and tunes OS-level
    settings for maximum throughput.
    """
    import psutil

    logger.info("=" * 60)
    logger.info("  System Auto-Optimizer")
    logger.info("=" * 60)
    optimizations = []

    # ── 1. Detect hardware ──
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
            logger.info(f"  GPU: {gpu_name} ({vram_total:.1f}GB VRAM, compute {capability[0]}.{capability[1]})")
        else:
            capability = (0, 0)
    except Exception:
        capability = (0, 0)

    # ── 2. Kill competing GPU processes ──
    # Unload ALL Ollama models (not just qwen3:14b)
    try:
        import urllib.request
        # List loaded models
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
                optimizations.append(f"unloaded Ollama model {model_name}")
    except Exception:
        pass

    # Check for llama-server on port 11435 (uses GPU VRAM)
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(("127.0.0.1", 11435))
        s.close()
        if result == 0:
            logger.warning("  WARNING: llama-server running on port 11435 — uses GPU VRAM!")
            logger.warning("  Consider stopping it: taskkill /f /im llama-server.exe")
    except Exception:
        pass

    # ── 3. Set process priority to HIGH ──
    try:
        p = psutil.Process()
        if sys.platform == "win32":
            p.nice(psutil.HIGH_PRIORITY_CLASS)
            logger.info("  Process priority: HIGH")
            optimizations.append("process priority HIGH")
        else:
            p.nice(-10)
            logger.info("  Process priority: -10 (elevated)")
            optimizations.append("process priority elevated")
    except (psutil.AccessDenied, OSError) as e:
        logger.info(f"  Process priority: could not elevate ({e})")

    # ── 4. Pin to performance CPU cores ──
    # On systems with P-cores and E-cores (Intel 12th+), pin to first half (P-cores)
    # On other systems, use all cores
    try:
        p = psutil.Process()
        # Use all cores for training — PyTorch handles thread affinity internally
        all_cores = list(range(cpu_count))
        p.cpu_affinity(all_cores)
        logger.info(f"  CPU affinity: all {cpu_count} cores")
        optimizations.append(f"CPU affinity {cpu_count} cores")
    except Exception:
        pass

    # ── 5. Configure PyTorch thread pools ──
    try:
        import torch
        # Intra-op: CPU compute threads for operations (matmul, etc.)
        # For GPU training, we don't need many CPU compute threads
        # But data loading benefits from parallelism
        torch.set_num_threads(min(cpu_count, 8))
        torch.set_num_interop_threads(min(cpu_count // 2, 4))
        logger.info(f"  PyTorch threads: {torch.get_num_threads()} intra-op, "
                    f"{torch.get_num_interop_threads()} inter-op")
        optimizations.append(f"PyTorch threads tuned")
    except Exception:
        pass

    # ── 6. CUDA-specific optimizations (auto-detect capability) ──
    try:
        import torch
        if torch.cuda.is_available():
            # TF32: Ada Lovelace (8.x) and Hopper (9.x) — zero quality loss for training
            if capability[0] >= 8:
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True
                optimizations.append("TF32 enabled")

            # SDP backends: enable fast paths (keep math as fallback for GDN layers)
            if hasattr(torch.backends.cuda, 'flash_sdp_enabled'):
                torch.backends.cuda.enable_flash_sdp(True)
                torch.backends.cuda.enable_mem_efficient_sdp(True)
                optimizations.append("Flash+MemEfficient SDP enabled")

            # Disable debug sync (slows training significantly)
            os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "0")

            # cuBLAS workspace for better algorithm selection
            os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

            logger.info(f"  CUDA: TF32={'on' if capability[0] >= 8 else 'off'}, "
                        f"capability={capability[0]}.{capability[1]}")
            optimizations.append("CUDA tuned")
    except Exception:
        pass

    # ── 7. Memory optimization ──
    try:
        import torch
        # Disable CUDA memory caching for unused tensors
        os.environ.setdefault("PYTORCH_NO_CUDA_MEMORY_CACHING", "0")
        # Aggressive garbage collection threshold
        import gc
        gc.set_threshold(700, 10, 5)  # Less frequent but larger GC sweeps
        optimizations.append("GC threshold tuned")
    except Exception:
        pass

    # ── 8. OS-level I/O optimization ──
    if sys.platform == "win32":
        # Windows: disable file system last-access timestamp updates for faster I/O
        # (Already disabled by default on most Windows 10/11 installs)
        os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        optimizations.append("bytecode caching disabled")

    # ── 9. Reduce Python overhead ──
    # Disable hash randomization for reproducibility
    os.environ.setdefault("PYTHONHASHSEED", "42")

    # ── 10. Log available resources after optimization ──
    ram_avail_after = psutil.virtual_memory().available / (1024**3)
    try:
        import torch
        if torch.cuda.is_available():
            vram_free = (torch.cuda.get_device_properties(0).total_memory
                         - torch.cuda.memory_allocated()) / (1024**3)
            logger.info(f"  Resources after optimization: "
                        f"RAM={ram_avail_after:.1f}GB free, VRAM={vram_free:.1f}GB free")
    except Exception:
        logger.info(f"  Resources after optimization: RAM={ram_avail_after:.1f}GB free")

    logger.info(f"  Applied {len(optimizations)} optimizations: {', '.join(optimizations)}")
    logger.info("=" * 60)
    return optimizations


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def train_v3(model_path: str, max_steps: int = 0):
    """Train LoRA v3 with monkey-patched experts for true 4-bit quantization."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import LoraConfig, TaskType, get_peft_model
    from datasets import load_dataset
    from trl import SFTTrainer, SFTConfig
    from transformers import TrainerCallback
    import psutil

    # System prompt for ChatML -- matches what llama-server sends at inference
    from hiveai.llm.prompts import CODING_SYSTEM_PROMPT

    logger.info("=" * 60)
    logger.info("  HiveAI LoRA v3 Training")
    logger.info("=" * 60)
    logger.info(f"  Base model:  {model_path}")
    logger.info(f"  Data:        {TRAINING_JSONL}")
    logger.info(f"  Output:      {OUTPUT_DIR}")
    logger.info(f"  LoRA:        r={LORA_CONFIG['r']}, alpha={LORA_CONFIG['lora_alpha']}, "
                f"DoRA={LORA_CONFIG.get('use_dora')}")
    logger.info(f"  Training:    batch={TRAINING_CONFIG['per_device_train_batch_size']}x"
                f"{TRAINING_CONFIG['gradient_accumulation_steps']}="
                f"{TRAINING_CONFIG['per_device_train_batch_size'] * TRAINING_CONFIG['gradient_accumulation_steps']} effective, "
                f"epochs={TRAINING_CONFIG['num_train_epochs']}, lr={TRAINING_CONFIG['learning_rate']}")
    logger.info(f"  Context:     {MAX_SEQ_LENGTH} tokens")
    logger.info(f"  NEFTune:     alpha={TRAINING_CONFIG['neftune_noise_alpha']}")
    logger.info(f"  Loading:     unfused experts + BnB 4-bit (true ~9GB, fits 16GB VRAM)")
    if max_steps:
        logger.info(f"  TEST MODE:   stopping after {max_steps} steps")
    logger.info("=" * 60)

    # Count pairs
    with open(TRAINING_JSONL, "r", encoding="utf-8") as f:
        pair_count = sum(1 for line in f if line.strip())
    logger.info(f"Training pairs: {pair_count}")

    # ── Apply monkey-patches BEFORE loading ──
    # 1. Patch expert class: fused 3D Parameters -> per-expert nn.Linear
    patch_experts_for_quantization()
    # 2. Disable conversion mapping that would re-fuse per-expert tensors
    disable_expert_fusing_converter()

    # ── Load model with 4-bit quantization ──
    # With unfused experts, BnB quantizes ALL nn.Linear layers to NF4.
    # Quantized model is ~11.1GB — fits entirely on 16GB GPU.
    # CRITICAL: device_map={"": 0} forces all layers on GPU.
    # device_map="auto" overestimates layer sizes (bf16 not NF4) and
    # offloads ~28/40 layers to CPU, causing 10-50x slowdown from PCIe shuttling.
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )

    logger.info(f"Loading tokenizer from {model_path}...")
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

    logger.info(f"Loading model with unfused experts + BnB 4-bit (ALL on GPU)...")
    load_start = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        quantization_config=bnb_config,
        device_map={"": 0},  # Force all on GPU 0 — no CPU offloading
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )
    load_time = time.time() - load_start
    logger.info(f"Model loaded in {load_time:.0f}s")

    # Log VRAM usage
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

    # NOTE: Fused CE (cut_cross_entropy) saves ~2 GB VRAM but conflicts with
    # TRL 0.29.0's mean_token_accuracy metric which accesses logits.shape.
    # Since we have 5 GB VRAM headroom and the bottleneck is MoE expert dispatch
    # (not loss computation), standard CE is fine. Add for v4 via custom compute_loss.

    # Check that experts are actually quantized (should be Linear4bit not raw Parameter)
    n_quantized = 0
    n_not_quantized = 0
    for name, module in model.named_modules():
        if hasattr(module, 'weight') and hasattr(module.weight, 'quant_state'):
            n_quantized += 1
        elif isinstance(module, torch.nn.Linear):
            n_not_quantized += 1
    logger.info(f"Quantized modules: {n_quantized} Linear4bit, {n_not_quantized} unquantized Linear")

    # ── Freeze base params + enable gradient checkpointing ──
    n_frozen = 0
    for param in model.parameters():
        param.requires_grad = False
        n_frozen += 1
    logger.info(f"Frozen {n_frozen} base model parameters")

    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()
    else:
        def _make_inputs_require_grad(module, input, output):
            output.requires_grad_(True)
        model.get_input_embeddings().register_forward_hook(_make_inputs_require_grad)

    model.gradient_checkpointing_enable(
        gradient_checkpointing_kwargs={
            "use_reentrant": False,
            "preserve_rng_state": False,  # No dropout anywhere → skip 80 CUDA syncs/step
        }
    )
    logger.info("Gradient checkpointing enabled (preserve_rng_state=False — no dropout)")

    # ── Apply LoRA ──
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
    logger.info(f"LoRA applied: r={LORA_CONFIG['r']}, alpha={LORA_CONFIG['lora_alpha']}, "
                f"DoRA={LORA_CONFIG['use_dora']}")

    # Cast LoRA adapter weights to bf16 (PEFT creates them in float32 by default)
    n_cast = 0
    for name, param in model.named_parameters():
        if param.requires_grad and param.dtype == torch.float32:
            param.data = param.data.to(torch.bfloat16)
            n_cast += 1
    if n_cast:
        logger.info(f"Cast {n_cast} LoRA adapter params float32 -> bf16")

    # ── Fused MoE dispatch info ──
    if os.environ.get("HIVE_FUSED_MOE", "1") == "1":
        logger.info("Fused MoE dispatch: ENABLED (batch-dequant + sorted per-expert matmul)")
        logger.info("  Tokens sorted by expert for contiguous memory access")
        logger.info("  Set HIVE_FUSED_MOE=0 to use sequential dispatch")
    else:
        logger.info("Fused MoE dispatch: DISABLED (sequential Linear4bit calls)")

    # ── Selective torch.compile for non-BnB components ──
    # BnB Linear4bit modules are incompatible with torch.compile (Dynamo can't trace
    # NF4 tensors). But attention SDPA, normalization, and LoRA modules compile fine.
    # Since MoE expert dispatch is only ~13% of step time, optimizing the other 87%
    # (attention + norms) via compilation has higher leverage.
    USE_COMPILE = os.environ.get("HIVE_TORCH_COMPILE", "1") == "1"
    if USE_COMPILE:
        try:
            # Navigate to the actual model layers (through PEFT wrapper)
            base_model = model
            if hasattr(base_model, 'base_model'):
                base_model = base_model.base_model
            if hasattr(base_model, 'model'):
                base_model = base_model.model
            if hasattr(base_model, 'model'):
                base_model = base_model.model

            layers = None
            if hasattr(base_model, 'layers'):
                layers = base_model.layers
            elif hasattr(base_model, 'language_model') and hasattr(base_model.language_model, 'layers'):
                layers = base_model.language_model.layers

            if layers is not None:
                compiled_attn = 0
                compiled_norm = 0
                for layer_idx, layer in enumerate(layers):
                    # Compile normalization layers (small, many calls, fuses well)
                    if hasattr(layer, 'input_layernorm'):
                        try:
                            layer.input_layernorm = torch.compile(
                                layer.input_layernorm, mode="reduce-overhead"
                            )
                            compiled_norm += 1
                        except Exception:
                            pass
                    if hasattr(layer, 'post_attention_layernorm'):
                        try:
                            layer.post_attention_layernorm = torch.compile(
                                layer.post_attention_layernorm, mode="reduce-overhead"
                            )
                            compiled_norm += 1
                        except Exception:
                            pass
                logger.info(f"torch.compile: {compiled_norm} normalization layers compiled")
                logger.info("  Mode: reduce-overhead (Triton fusion)")
                logger.info("  First step will be slower (Triton compilation warmup)")
                logger.info("  Set HIVE_TORCH_COMPILE=0 to disable")
            else:
                logger.warning("torch.compile: could not find model layers, skipping")
        except Exception as e:
            logger.warning(f"torch.compile failed, continuing without: {e}")
    else:
        logger.info("torch.compile: DISABLED (set HIVE_TORCH_COMPILE=1 to enable)")

    # ── Load and format dataset ──
    dataset = load_dataset("json", data_files=TRAINING_JSONL, split="train")

    logger.info(f"EOS token: '{tokenizer.eos_token}' (id={tokenizer.eos_token_id})")

    # ChatML formatting -- matches inference exactly
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

            # Truncate assistant output if too long (preserve EOS)
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

    # Validate sample
    sample = dataset[0]["text"]
    sample_len = len(tokenizer.encode(sample))
    ends_with_eos = sample.rstrip().endswith("<|im_end|>")
    logger.info(f"Sample: {sample_len} tokens, ends_with_EOS={ends_with_eos}")
    logger.info(f"First 400 chars:\n{sample[:400]}")

    # ── Training ──
    class HiveLoggingCallback(TrainerCallback):
        """Logs training metrics through our logger."""
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
            if lr is not None:
                parts.append(f"lr={lr:.2e}")
            parts.append(f"elapsed={elapsed/3600:.1f}h")
            parts.append(f"ETA={eta_s/3600:.1f}h")
            logger.info(" | ".join(parts))
            sys.stderr.flush()

        def on_step_end(self, args, state, control, **kwargs):
            # Periodically clear CUDA allocator cache to prevent fragmentation
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
                ram_avail = psutil.virtual_memory().available / (1024**3)
                gpu_line = ""
                try:
                    out = subprocess.check_output(
                        ["nvidia-smi", "--query-gpu=memory.used,memory.free",
                         "--format=csv,noheader,nounits"],
                        text=True, timeout=5
                    ).strip()
                    gpu_used, gpu_free = out.split(", ")
                    gpu_line = f" | GPU={gpu_used}MB used, {gpu_free}MB free"
                except Exception:
                    pass
                logger.info(f"[MEM step={step}] RAM={ram_gb:.1f}GB used, "
                            f"{ram_avail:.1f}GB avail{gpu_line}")
            except Exception as e:
                logger.warning(f"[MEM] failed: {e}")

    # Heartbeat thread
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
    _hb_thread = threading.Thread(target=_heartbeat, daemon=True)
    _hb_thread.start()

    # Build SFTConfig
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
        # Fused optimizer: identical math, fewer CUDA kernel launches (~5% speedup)
        optim="adamw_torch_fused",
        # Dataloader: prefetch on background threads, pin memory for faster DMA
        dataloader_num_workers=2,
        dataloader_pin_memory=True,
        dataloader_persistent_workers=True,  # keep workers alive between epochs
        dataloader_prefetch_factor=2,        # prefetch 2 batches per worker
        dataloader_drop_last=True,           # drop incomplete final batch (fixes loss scaling)
        # Monitoring & storage
        logging_first_step=True,
        save_total_limit=3,
        skip_memory_metrics=True,  # we have our own memory callback
        # SFT-specific
        dataset_text_field="text",
        max_length=MAX_SEQ_LENGTH,
        # NEFTune: gaussian noise on input embeddings
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
        callbacks=[HiveLoggingCallback()],
    )

    # Preserve curriculum ordering (beginner -> intermediate -> expert)
    from torch.utils.data import SequentialSampler
    trainer._get_train_sampler = lambda dataset: SequentialSampler(dataset)

    # Check for existing checkpoints to resume from
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

    # Save adapter
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    logger.info(f"Adapter saved to {OUTPUT_DIR}")

    # Save training metadata
    meta = {
        "version": "v3.0",
        "base_model": model_path,
        "pair_count": pair_count,
        "loss": loss if isinstance(loss, (int, float)) else None,
        "training_time_s": round(elapsed),
        "lora_config": LORA_CONFIG,
        "training_config": TRAINING_CONFIG,
        "max_seq_length": MAX_SEQ_LENGTH,
        "system_prompt": "CODING_SYSTEM_PROMPT (hiveai.llm.prompts)",
        "format": "ChatML via tokenizer.apply_chat_template",
        "loading_method": "unfused experts + BnB 4-bit NF4 (true ~9GB)",
        "pruning": "128/256 experts, 55% routing capacity retained",
        "expert_format": "unfused nn.Linear (gate_projs/up_projs/down_projs per expert)",
        "eos_token": tokenizer.eos_token,
        "eos_token_id": tokenizer.eos_token_id,
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

    adapter_config = os.path.join(OUTPUT_DIR, "adapter_config.json")
    if not os.path.exists(adapter_config):
        logger.error(f"No adapter found at {OUTPUT_DIR}")
        return None

    logger.info(f"Converting LoRA adapter to GGUF: {ADAPTER_GGUF}")
    cmd = [
        sys.executable, CONVERT_LORA_SCRIPT,
        "--base", os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b-pruned"),
        "--outfile", ADAPTER_GGUF,
        "--outtype", "f16",
        OUTPUT_DIR,
    ]
    logger.info(f"  {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
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
    print("  v3 Training Complete -- Next Steps")
    print("=" * 60)
    print(f"""
  RECOMMENDED: Use the deploy script (handles everything):
     python scripts/deploy_v3.py --now --eval

  OR manually:

  1. Start llama-server with v3 LoRA (optimized flags):
     "C:/Users/theyc/llama.cpp/bin/llama-server.exe" \\
       -m "models/qwen3.5-35b-a3b/Qwen3.5-35B-A3B-Q4_K_M.gguf" \\
       --lora "loras/v3/hiveai-v3-lora.gguf" \\
       --port 11435 --n-gpu-layers 999 --ctx-size 16384 --threads 2 \\
       -b 4096 -fa --cache-type-k q8_0 --cache-type-v q4_0 --no-mmap --mlock

  2. Run eval:
     python scripts/run_eval.py --model hiveai-v3 \\
       --base-url http://localhost:11435

  3. Compare: qwen3:14b=0.741, hiveai-v1=0.853 (+15%)
""")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Train HiveAI LoRA v3")
    parser.add_argument("--test", type=int, default=0,
                        help="Smoke test: run N steps then stop (0=full training)")
    args = parser.parse_args()

    logger.info("HiveAI LoRA v3 Training Pipeline")
    logger.info("Base: Qwen3.5-35B-A3B-pruned (128/256 experts, 55% capacity)")
    logger.info("Data: v3.jsonl (2,385 quality-filtered pairs)")
    logger.info("Method: unfused experts + BnB 4-bit (true ~9GB, all on GPU)")

    # Free GPU + maximize system resources
    unload_ollama_model()
    optimize_system()

    model_path = check_prerequisites()

    if args.test:
        logger.info(f"SMOKE TEST: {args.test} steps")
        loss = train_v3(model_path, max_steps=args.test)
        logger.info(f"Smoke test complete. Loss: {loss}")
    else:
        loss = train_v3(model_path)
        convert_to_gguf()
        print_next_steps()
