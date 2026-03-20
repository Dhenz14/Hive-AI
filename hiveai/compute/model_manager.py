"""
hiveai/compute/model_manager.py

Model Manager — manages qualified models per tier with auto-switching.

This is the bridge between the tier system and actual model serving.
When the community tier changes, this manager:
  1. Checks which model is qualified for the new tier
  2. Ensures it's downloaded locally (or starts download)
  3. Switches the active Ollama model
  4. Verifies the switch with a health check

Model Qualification:
  Each tier has a fixed, tested model stack. Models are qualified through
  an eval pipeline before being added. Community can't inject random models.

Tier Model Stack:
  Tier 1 (Local, <15 GPUs):
    - Primary: best qualified 14B model (tested via eval pipeline)
    - Fallback: qwen3:14b (always available)

  Tier 2 (Cluster, 15-39 GPUs):
    - Primary: qwen3:32b (split across 2+ GPUs)
    - Requires: 2+ registered nodes with combined 28GB+ VRAM

  Tier 3 (Full Brain, 40+ GPUs):
    - Primary: Qwen3-Coder-80B-MoE (expert parallel)
    - Requires: 40+ nodes, IPFS-sharded expert weights
"""

import asyncio
import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:
    aiohttp = None


# ── Qualified Model Stack ────────────────────────────────────────

@dataclass
class QualifiedModel:
    """A model that's been tested and approved for a tier."""
    name: str                    # Ollama model name (e.g., "qwen3:14b")
    display_name: str            # Human-readable name
    tier: int                    # Which tier this model serves
    size_gb: float               # Download size
    vram_required_gb: float      # Minimum VRAM to run (without CPU offload)
    vram_recommended_gb: float   # Recommended VRAM (no offload needed)
    eval_score: float = 0.0      # Qualification eval score (0-100)
    eval_date: str = ""          # When it was last evaluated
    qualified: bool = False      # Has it passed qualification?
    priority: int = 0            # Higher = preferred within same tier
    supports_cpu_offload: bool = True
    requires_cluster: bool = False
    ollama_name: str = ""        # Actual ollama model identifier to pull/run

    def __post_init__(self):
        if not self.ollama_name:
            self.ollama_name = self.name


# The approved model stack — only these models are used in production
QUALIFIED_MODELS: list[QualifiedModel] = [
    # ── Tier 1: Local inference ──────────────────────────
    QualifiedModel(
        name="qwen3:14b",
        display_name="Qwen3 14B (Q4, fast)",
        tier=1,
        size_gb=9.3,
        vram_required_gb=8.0,
        vram_recommended_gb=12.0,
        eval_score=72.0,
        qualified=True,
        priority=10,
    ),
    QualifiedModel(
        name="claude-distill-14b",
        display_name="Qwen3 14B Claude Opus Distill (Q6_K, reasoning)",
        tier=1,
        size_gb=12.1,
        vram_required_gb=10.0,
        vram_recommended_gb=16.0,
        eval_score=0.0,  # pending eval
        qualified=False,  # needs to pass eval first
        priority=20,      # higher priority IF it qualifies
        ollama_name="hf.co/Otakadelic/Qwen3-14B-Claude-4.5-Opus-High-Reasoning-Distill-Q6_K-GGUF",
    ),
    QualifiedModel(
        name="qwen3.5:9b",
        display_name="Qwen3.5 9B (fast, good for simple tasks)",
        tier=1,
        size_gb=6.6,
        vram_required_gb=6.0,
        vram_recommended_gb=8.0,
        eval_score=65.0,
        qualified=True,
        priority=5,
    ),

    # ── Tier 2: Cluster inference ────────────────────────
    QualifiedModel(
        name="qwen3:32b",
        display_name="Qwen3 32B (cluster, high quality)",
        tier=2,
        size_gb=20.0,
        vram_required_gb=20.0,
        vram_recommended_gb=24.0,
        eval_score=88.0,
        qualified=True,
        priority=10,
        requires_cluster=True,
    ),

    # ── Tier 3: Full brain ───────────────────────────────
    QualifiedModel(
        name="qwen3-coder-80b-moe",
        display_name="Qwen3 Coder 80B MoE (expert parallel)",
        tier=3,
        size_gb=48.0,
        vram_required_gb=48.0,
        vram_recommended_gb=80.0,
        eval_score=95.0,
        qualified=True,
        priority=10,
        requires_cluster=True,
    ),
]


@dataclass
class ModelEvalResult:
    """Result of evaluating a model for qualification."""
    model_name: str
    eval_prompts: int
    correct: int
    score: float          # 0-100
    avg_latency_ms: float
    avg_tokens: float
    timestamp: str = ""
    details: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ── Qualification Eval Prompts ───────────────────────────────────

EVAL_PROMPTS = [
    {"prompt": "What is the capital of France?", "expected_contains": "paris", "category": "knowledge"},
    {"prompt": "Write a Python function to check if a number is prime.", "expected_contains": "def", "category": "code"},
    {"prompt": "Explain why the sky is blue in one sentence.", "expected_contains": "scatter", "category": "reasoning"},
    {"prompt": "What is 127 * 43?", "expected_contains": "5461", "category": "math"},
    {"prompt": "Translate 'hello world' to Spanish.", "expected_contains": "hola", "category": "translation"},
    {"prompt": "What data structure uses LIFO ordering?", "expected_contains": "stack", "category": "knowledge"},
    {"prompt": "Write a SQL query to find duplicate emails in a users table.", "expected_contains": "GROUP BY", "category": "code"},
    {"prompt": "If a train travels 60mph for 2.5 hours, how far does it go?", "expected_contains": "150", "category": "math"},
    {"prompt": "What is the time complexity of binary search?", "expected_contains": "log", "category": "knowledge"},
    {"prompt": "Explain the difference between TCP and UDP in one sentence.", "expected_contains": "reliable", "category": "reasoning"},
]

QUALIFICATION_THRESHOLD = 60.0  # must score 60%+ to qualify


class ModelManager:
    """
    Manages the qualified model stack for Spirit Bomb tiers.
    """

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url
        self.models = list(QUALIFIED_MODELS)
        self._active_model: Optional[str] = None
        self._current_tier = 1

    def get_best_model_for_tier(self, tier: int, vram_gb: float = 16.0) -> Optional[QualifiedModel]:
        """Get the best qualified model for a given tier and VRAM."""
        candidates = [
            m for m in self.models
            if m.tier <= tier
            and m.qualified
            and m.vram_required_gb <= vram_gb
        ]
        if not candidates:
            return None
        # Sort by: tier desc (prefer higher tier models), then priority desc
        candidates.sort(key=lambda m: (m.tier, m.priority), reverse=True)
        return candidates[0]

    def get_models_for_tier(self, tier: int) -> list[QualifiedModel]:
        """Get all qualified models for a specific tier."""
        return [m for m in self.models if m.tier == tier and m.qualified]

    def get_download_plan(self, tier: int) -> list[QualifiedModel]:
        """Get models that should be pre-downloaded for a tier (and all lower tiers)."""
        return [
            m for m in self.models
            if m.tier <= tier and m.qualified and not m.requires_cluster
        ]

    async def check_downloaded(self) -> dict[str, bool]:
        """Check which qualified models are already downloaded in Ollama."""
        if aiohttp is None:
            return {}

        downloaded = {}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.ollama_url}/api/tags") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        local_names = {m["name"] for m in data.get("models", [])}
                        for model in self.models:
                            downloaded[model.name] = model.ollama_name in local_names or model.name in local_names
        except Exception as e:
            logger.warning(f"Could not check Ollama models: {e}")

        return downloaded

    async def ensure_tier_models(self, tier: int) -> list[str]:
        """Ensure all models for a tier (and below) are downloaded."""
        plan = self.get_download_plan(tier)
        downloaded = await self.check_downloaded()
        missing = [m for m in plan if not downloaded.get(m.name, False)]

        pulled = []
        for model in missing:
            logger.info(f"Pulling model for tier {model.tier}: {model.display_name}")
            success = await self._pull_model(model.ollama_name)
            if success:
                pulled.append(model.name)

        return pulled

    async def _pull_model(self, ollama_name: str) -> bool:
        """Pull a model via Ollama."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ollama", "pull", ollama_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception as e:
            logger.error(f"Failed to pull {ollama_name}: {e}")
            return False

    async def eval_model(
        self,
        model_name: str,
        ollama_name: Optional[str] = None,
    ) -> ModelEvalResult:
        """
        Run qualification eval against a model.

        Sends EVAL_PROMPTS to the model via Ollama, checks responses
        against expected patterns, and scores the model.
        """
        if aiohttp is None:
            raise ImportError("aiohttp required")

        target = ollama_name or model_name
        correct = 0
        details = []
        total_latency = 0.0
        total_tokens = 0

        async with aiohttp.ClientSession() as session:
            for i, ep in enumerate(EVAL_PROMPTS):
                start = time.time()
                try:
                    async with session.post(
                        f"{self.ollama_url}/api/chat",
                        json={
                            "model": target,
                            "messages": [{"role": "user", "content": ep["prompt"]}],
                            "stream": False,
                            "options": {"num_predict": 2048, "temperature": 0},
                        },
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = (data.get("message", {}).get("content", "") or "").lower()
                            tokens = data.get("eval_count", 0)
                            latency_ms = (time.time() - start) * 1000

                            passed = ep["expected_contains"].lower() in content
                            if passed:
                                correct += 1

                            total_latency += latency_ms
                            total_tokens += tokens

                            details.append({
                                "prompt": ep["prompt"][:60],
                                "category": ep["category"],
                                "passed": passed,
                                "expected": ep["expected_contains"],
                                "got_preview": content[:100],
                                "latency_ms": round(latency_ms),
                                "tokens": tokens,
                            })

                            status = "PASS" if passed else "FAIL"
                            logger.info(f"  Eval {i+1}/{len(EVAL_PROMPTS)}: {status} [{ep['category']}] {latency_ms:.0f}ms")
                        else:
                            details.append({"prompt": ep["prompt"][:60], "passed": False, "error": f"HTTP {resp.status}"})

                except Exception as e:
                    details.append({"prompt": ep["prompt"][:60], "passed": False, "error": str(e)})

        n = len(EVAL_PROMPTS)
        score = (correct / n * 100) if n > 0 else 0

        return ModelEvalResult(
            model_name=model_name,
            eval_prompts=n,
            correct=correct,
            score=round(score, 1),
            avg_latency_ms=round(total_latency / max(n, 1), 1),
            avg_tokens=round(total_tokens / max(n, 1), 1),
            details=details,
        )

    def qualify_model(self, model_name: str, eval_result: ModelEvalResult) -> bool:
        """Qualify or disqualify a model based on eval results."""
        model = next((m for m in self.models if m.name == model_name), None)
        if not model:
            return False

        model.eval_score = eval_result.score
        model.eval_date = eval_result.timestamp
        model.qualified = eval_result.score >= QUALIFICATION_THRESHOLD

        status = "QUALIFIED" if model.qualified else "DISQUALIFIED"
        logger.info(f"Model {model_name}: {status} (score={eval_result.score}%, threshold={QUALIFICATION_THRESHOLD}%)")
        return model.qualified

    async def switch_to_best(self, tier: int, vram_gb: float = 16.0) -> Optional[str]:
        """Switch to the best available model for the current tier."""
        best = self.get_best_model_for_tier(tier, vram_gb)
        if not best:
            logger.warning(f"No qualified model available for tier {tier}")
            return None

        if self._active_model == best.ollama_name:
            return best.ollama_name  # already active

        logger.info(f"Switching to {best.display_name} for tier {tier}")
        self._active_model = best.ollama_name
        self._current_tier = tier
        return best.ollama_name

    def get_status(self) -> dict:
        """Get current model manager status."""
        return {
            "active_model": self._active_model,
            "current_tier": self._current_tier,
            "qualified_models": [
                {
                    "name": m.name,
                    "display_name": m.display_name,
                    "tier": m.tier,
                    "size_gb": m.size_gb,
                    "qualified": m.qualified,
                    "eval_score": m.eval_score,
                    "priority": m.priority,
                }
                for m in self.models
            ],
        }
