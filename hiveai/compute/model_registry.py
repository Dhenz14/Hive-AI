"""
hiveai/compute/model_registry.py

Model Registry — tracks available models, optimal configurations,
and tier-specific model selection for the Spirit Bomb community cloud.

This is the intelligence layer that decides WHICH model to use
based on:
  - Current community tier (GPU count)
  - Available VRAM across cluster
  - Task type (code, chat, reasoning, creative)
  - User preference (speed vs quality)
  - Quantization support

Model Selection Strategy:
  Tier 1 (<15 GPUs): Qwen3-14B AWQ — fits on any GPU ≥8GB
  Tier 2 (15-40):    Qwen3-32B AWQ — needs 16GB or 2x8GB PP
  Tier 3 (40+):      Qwen3-Coder-80B-MoE — distributed MoE experts

Task-Specific Models:
  Code:      Qwen3-Coder variants (MoE for scale, dense for local)
  Chat:      Qwen3 base variants (best general quality)
  Reasoning: Qwen3-30B-A3B (MoE, excellent reasoning-per-FLOP)
  Creative:  Qwen3-32B (dense, highest creativity per token)

Quantization Selection:
  ≥24GB VRAM: FP16 (best quality)
  16-23GB: AWQ (4-bit, ~95% quality)
  8-15GB: GGUF Q4_K_M (balanced speed/quality)
  <8GB: GGUF Q3_K_S (speed priority)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class TaskType(Enum):
    CODE = "code"
    CHAT = "chat"
    REASONING = "reasoning"
    CREATIVE = "creative"
    GENERAL = "general"


class QuantFormat(Enum):
    FP16 = "fp16"
    FP8 = "fp8"
    AWQ = "awq"
    GPTQ = "gptq"
    GGUF_Q4_K_M = "gguf_q4_k_m"
    GGUF_Q3_K_S = "gguf_q3_k_s"
    HQQ = "hqq"  # newest, no calibration data needed


@dataclass
class ModelSpec:
    """Specification of a model available in the registry."""
    model_id: str  # HuggingFace ID or custom identifier
    display_name: str
    params_b: float  # parameters in billions
    architecture: str  # "dense", "moe"
    # Size requirements
    fp16_vram_gb: float  # VRAM needed at FP16
    awq_vram_gb: float  # VRAM needed at AWQ/GPTQ
    gguf_vram_gb: float  # VRAM needed at Q4_K_M GGUF
    # Capabilities
    max_context_length: int = 32768
    supports_tool_use: bool = False
    supports_code: bool = False
    supports_vision: bool = False
    # Performance (on RTX 4070 Ti SUPER, single GPU)
    benchmark_tps_awq: float = 0.0  # tokens/sec at AWQ
    benchmark_tps_fp16: float = 0.0  # tokens/sec at FP16
    # MoE specifics
    total_experts: int = 0
    active_experts_per_token: int = 0
    # Tier eligibility
    min_tier: int = 1  # minimum tier to serve this model
    recommended_tier: int = 1
    # Task suitability (0-10 score)
    code_score: int = 5
    chat_score: int = 5
    reasoning_score: int = 5
    creative_score: int = 5
    # Speculative decoding
    draft_model: str = ""  # recommended draft model for EAGLE-3
    expected_spec_speedup: float = 1.0


# ── Model Database ──────────────────────────────────────────────

MODELS: dict[str, ModelSpec] = {
    # ── Dense Models ────────────────────────────────────
    "qwen3-14b": ModelSpec(
        model_id="Qwen/Qwen3-14B",
        display_name="Qwen3 14B",
        params_b=14.0,
        architecture="dense",
        fp16_vram_gb=28.0,
        awq_vram_gb=9.5,
        gguf_vram_gb=8.5,
        max_context_length=131072,
        supports_tool_use=True,
        supports_code=True,
        benchmark_tps_awq=80.0,
        benchmark_tps_fp16=35.0,
        min_tier=1,
        recommended_tier=1,
        code_score=7,
        chat_score=7,
        reasoning_score=6,
        creative_score=6,
        draft_model="Qwen/Qwen3-0.6B",
        expected_spec_speedup=3.5,
    ),
    "qwen3-32b": ModelSpec(
        model_id="Qwen/Qwen3-32B",
        display_name="Qwen3 32B",
        params_b=32.0,
        architecture="dense",
        fp16_vram_gb=64.0,
        awq_vram_gb=20.0,
        gguf_vram_gb=18.0,
        max_context_length=131072,
        supports_tool_use=True,
        supports_code=True,
        benchmark_tps_awq=40.0,
        benchmark_tps_fp16=18.0,
        min_tier=2,
        recommended_tier=2,
        code_score=8,
        chat_score=9,
        reasoning_score=8,
        creative_score=9,
        draft_model="Qwen/Qwen3-0.6B",
        expected_spec_speedup=3.2,
    ),
    # ── MoE Models ──────────────────────────────────────
    "qwen3-30b-a3b": ModelSpec(
        model_id="Qwen/Qwen3-30B-A3B",
        display_name="Qwen3 30B MoE (3B active)",
        params_b=30.0,
        architecture="moe",
        fp16_vram_gb=60.0,
        awq_vram_gb=18.0,
        gguf_vram_gb=16.0,
        max_context_length=131072,
        supports_tool_use=True,
        supports_code=True,
        total_experts=128,
        active_experts_per_token=8,
        benchmark_tps_awq=90.0,
        benchmark_tps_fp16=40.0,
        min_tier=1,
        recommended_tier=2,
        code_score=7,
        chat_score=7,
        reasoning_score=9,
        creative_score=6,
        draft_model="Qwen/Qwen3-0.6B",
        expected_spec_speedup=4.0,
    ),
    "qwen3-coder-80b-moe": ModelSpec(
        model_id="Qwen/Qwen3-Coder-80B-MoE",
        display_name="Qwen3 Coder 80B MoE",
        params_b=80.0,
        architecture="moe",
        fp16_vram_gb=160.0,
        awq_vram_gb=48.0,
        gguf_vram_gb=42.0,
        max_context_length=131072,
        supports_tool_use=True,
        supports_code=True,
        total_experts=64,
        active_experts_per_token=8,
        benchmark_tps_awq=25.0,
        benchmark_tps_fp16=10.0,
        min_tier=3,
        recommended_tier=3,
        code_score=10,
        chat_score=8,
        reasoning_score=9,
        creative_score=8,
        draft_model="Qwen/Qwen3-0.6B",
        expected_spec_speedup=3.0,
    ),
    "deepseek-v3": ModelSpec(
        model_id="deepseek-ai/DeepSeek-V3",
        display_name="DeepSeek V3 (671B MoE)",
        params_b=671.0,
        architecture="moe",
        fp16_vram_gb=1342.0,
        awq_vram_gb=340.0,
        gguf_vram_gb=300.0,
        max_context_length=131072,
        supports_tool_use=True,
        supports_code=True,
        total_experts=256,
        active_experts_per_token=8,
        benchmark_tps_awq=8.0,
        min_tier=3,
        recommended_tier=3,
        code_score=10,
        chat_score=9,
        reasoning_score=10,
        creative_score=9,
        draft_model="",
        expected_spec_speedup=2.5,
    ),
    # ── Small Models (for speculative drafting / edge) ──
    "qwen3-0.6b": ModelSpec(
        model_id="Qwen/Qwen3-0.6B",
        display_name="Qwen3 0.6B (draft)",
        params_b=0.6,
        architecture="dense",
        fp16_vram_gb=1.2,
        awq_vram_gb=0.5,
        gguf_vram_gb=0.4,
        max_context_length=32768,
        benchmark_tps_awq=500.0,
        benchmark_tps_fp16=300.0,
        min_tier=1,
        code_score=2,
        chat_score=3,
        reasoning_score=2,
        creative_score=2,
    ),
}


class ModelRegistry:
    """
    Model registry for the Spirit Bomb community cloud.

    Selects the optimal model for a given request based on:
    - Current tier
    - Available VRAM
    - Task type
    - Quality vs speed preference
    """

    def __init__(self):
        self.models = dict(MODELS)

    def select_model(
        self,
        tier: int,
        task: TaskType = TaskType.GENERAL,
        max_vram_gb: float = 16.0,
        prefer_speed: bool = False,
    ) -> Optional[ModelSpec]:
        """
        Select the best model for given constraints.

        Args:
            tier: Current community tier (1-3)
            task: Type of task
            max_vram_gb: Maximum VRAM available (for quantization selection)
            prefer_speed: If True, prefer faster smaller models
        """
        # Filter eligible models
        eligible = [
            m for m in self.models.values()
            if m.min_tier <= tier and m.awq_vram_gb <= max_vram_gb * 1.1  # 10% headroom
        ]

        if not eligible:
            # Fallback: find anything that fits in GGUF
            eligible = [
                m for m in self.models.values()
                if m.gguf_vram_gb <= max_vram_gb
            ]

        if not eligible:
            return None

        # Score based on task
        task_scores = {
            TaskType.CODE: lambda m: m.code_score,
            TaskType.CHAT: lambda m: m.chat_score,
            TaskType.REASONING: lambda m: m.reasoning_score,
            TaskType.CREATIVE: lambda m: m.creative_score,
            TaskType.GENERAL: lambda m: (m.code_score + m.chat_score + m.reasoning_score) / 3,
        }
        score_fn = task_scores.get(task, task_scores[TaskType.GENERAL])

        if prefer_speed:
            # Weight speed heavily
            key = lambda m: score_fn(m) * 0.3 + (m.benchmark_tps_awq / 100) * 0.7
        else:
            # Weight quality heavily
            key = lambda m: score_fn(m) * 0.7 + (m.benchmark_tps_awq / 100) * 0.3

        return max(eligible, key=key)

    def select_quantization(
        self, model: ModelSpec, available_vram_gb: float
    ) -> QuantFormat:
        """Select optimal quantization for available VRAM."""
        if available_vram_gb >= model.fp16_vram_gb:
            return QuantFormat.FP16
        elif available_vram_gb >= model.awq_vram_gb:
            return QuantFormat.AWQ
        elif available_vram_gb >= model.gguf_vram_gb:
            return QuantFormat.GGUF_Q4_K_M
        else:
            return QuantFormat.GGUF_Q3_K_S

    def get_tier_models(self, tier: int) -> list[ModelSpec]:
        """Get all models available at a given tier."""
        return sorted(
            [m for m in self.models.values() if m.min_tier <= tier],
            key=lambda m: m.params_b,
            reverse=True,
        )

    def get_model_card(self, model_key: str) -> Optional[dict]:
        """Get a human-readable model card."""
        model = self.models.get(model_key)
        if not model:
            return None

        return {
            "id": model.model_id,
            "name": model.display_name,
            "params": f"{model.params_b}B",
            "architecture": model.architecture,
            "context": f"{model.max_context_length // 1024}K",
            "vram_fp16": f"{model.fp16_vram_gb}GB",
            "vram_awq": f"{model.awq_vram_gb}GB",
            "vram_gguf": f"{model.gguf_vram_gb}GB",
            "speed_awq": f"{model.benchmark_tps_awq} tok/s",
            "strengths": self._model_strengths(model),
            "min_tier": model.min_tier,
            "recommended_tier": model.recommended_tier,
            "speculative_decoding": {
                "draft_model": model.draft_model or "n-gram (built-in)",
                "expected_speedup": f"{model.expected_spec_speedup}x",
            },
        }

    def _model_strengths(self, model: ModelSpec) -> list[str]:
        strengths = []
        scores = {
            "code": model.code_score,
            "chat": model.chat_score,
            "reasoning": model.reasoning_score,
            "creative": model.creative_score,
        }
        for name, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            if score >= 8:
                strengths.append(f"Excellent at {name}")
            elif score >= 6:
                strengths.append(f"Good at {name}")
        return strengths[:3]
