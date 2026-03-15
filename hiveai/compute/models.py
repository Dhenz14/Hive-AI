"""
hiveai/compute/models.py

Shared manifest/result contract for GPU compute workloads.

This module defines the FROZEN schemas that both the untrusted worker
and the trusted verifier must agree on. Changes here require bumping
SCHEMA_VERSION and coordinating both sides.

V1 canary workloads: eval_sweep, benchmark_run
V1 deferred: domain_lora_train, weakness_targeted_generation, adapter_validation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

SCHEMA_VERSION = 1


# ================================================================
# Workload Types
# ================================================================

class WorkloadType(str, Enum):
    """Supported workload types. Worker only executes types it declares."""
    EVAL_SWEEP = "eval_sweep"
    BENCHMARK_RUN = "benchmark_run"
    ADAPTER_VALIDATION = "adapter_validation"
    # Deferred to V1.1:
    DOMAIN_LORA_TRAIN = "domain_lora_train"
    WEAKNESS_TARGETED_GENERATION = "weakness_targeted_generation"


# Canary workloads: safe to run on untrusted nodes in the first pass
CANARY_WORKLOADS = frozenset({
    WorkloadType.EVAL_SWEEP,
    WorkloadType.BENCHMARK_RUN,
})


# ================================================================
# Manifest Schema (immutable job definition)
# ================================================================

@dataclass
class EvalSweepManifest:
    """Manifest for eval_sweep workload.

    Worker runs a subset of Hive-AI's eval harness against a model
    and returns structured scores per challenge.
    """
    schema_version: int = SCHEMA_VERSION
    workload_type: str = WorkloadType.EVAL_SWEEP

    # Model to evaluate
    model_name: str = ""           # Ollama model name (e.g. "qwen3:14b")
    base_url: str | None = None    # llama-server URL if not Ollama

    # Eval config
    challenge_ids: list[str] = field(default_factory=list)  # specific challenge IDs, empty = all
    category: str | None = None     # filter by category
    limit: int = 0                  # 0 = all matching challenges
    temperature: float = 0.3
    max_tokens: int = 4096
    workers: int = 1                # parallel eval workers

    # Executor metadata
    executor_type: str = "hiveai-eval"
    executor_version: str = "1.0.0"


@dataclass
class BenchmarkRunManifest:
    """Manifest for benchmark_run workload.

    Worker runs a benchmark suite and returns timing/quality metrics.
    """
    schema_version: int = SCHEMA_VERSION
    workload_type: str = WorkloadType.BENCHMARK_RUN

    # Model to benchmark
    model_name: str = ""
    base_url: str | None = None

    # Benchmark config
    benchmark_suite: str = "default"  # which benchmark set to run
    iterations: int = 1               # repeat count for statistical confidence
    challenge_ids: list[str] = field(default_factory=list)
    category: str | None = None
    temperature: float = 0.3
    max_tokens: int = 4096

    # Executor metadata
    executor_type: str = "hiveai-benchmark"
    executor_version: str = "1.0.0"


# ================================================================
# Result Schema (worker output)
# ================================================================

@dataclass
class EvalSweepResult:
    """Structured result from eval_sweep workload.

    The verifier will re-run a hidden subset of these challenges to verify.
    """
    # Summary scores
    overall_score: float = 0.0      # 0.0 - 1.0 weighted composite
    challenges_run: int = 0
    challenges_passed: int = 0

    # Per-challenge breakdown (challenge_id -> score dict)
    scores: dict[str, ChallengeScore] | dict[str, dict] = field(default_factory=dict)

    # Categories breakdown
    category_scores: dict[str, float] = field(default_factory=dict)

    # Timing
    total_time_sec: float = 0.0
    avg_time_per_challenge_sec: float = 0.0

    # Model info (for audit)
    model_name: str = ""
    eval_harness_version: str = ""


@dataclass
class ChallengeScore:
    """Score for a single eval challenge."""
    challenge_id: str = ""
    category: str = ""
    difficulty: int = 1
    score: float = 0.0               # 0.0 - 1.0
    code_validity: float = 0.0       # 0.0 - 1.0
    test_passing: float = 0.0        # 0.0 - 1.0
    concept_coverage: float = 0.0    # 0.0 - 1.0
    explanation_quality: float = 0.0  # 0.0 - 1.0
    time_sec: float = 0.0
    error: str | None = None


@dataclass
class BenchmarkResult:
    """Structured result from benchmark_run workload."""
    overall_score: float = 0.0
    challenges_run: int = 0
    iterations: int = 1
    scores: dict[str, dict] = field(default_factory=dict)
    category_scores: dict[str, float] = field(default_factory=dict)
    total_time_sec: float = 0.0
    model_name: str = ""


# ================================================================
# Metrics Schema (telemetry — untrusted, for debugging only)
# ================================================================

@dataclass
class WorkerMetrics:
    """Telemetry reported by worker. NOT used for verification decisions."""
    gpu_utilization_pct: float = 0.0
    gpu_memory_used_mb: float = 0.0
    gpu_memory_total_mb: float = 0.0
    wall_time_sec: float = 0.0
    cpu_time_sec: float = 0.0
    peak_memory_mb: float = 0.0
    worker_version: str = ""
    python_version: str = ""
    torch_version: str = ""
    cuda_version: str = ""


# ================================================================
# Verification Contract (verifier -> HivePoA)
# ================================================================

class VerificationResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SOFT_FAIL = "soft_fail"  # suspicious but not definitively bad


@dataclass
class VerificationDecision:
    """Output of the trusted verifier."""
    result: VerificationResult
    score: float = 0.0               # 0.0 - 1.0 contribution quality
    verifier_type: str = ""          # "hidden_eval", "structural", etc.
    verifier_version: str = "1.0.0"
    details: dict[str, Any] = field(default_factory=dict)
    # How many hidden challenges were re-run and matched
    hidden_challenges_run: int = 0
    hidden_challenges_matched: int = 0
    # Score deviation: abs(worker_reported_score - verifier_observed_score)
    score_deviation: float = 0.0


# ================================================================
# Helpers
# ================================================================

def manifest_to_dict(manifest: EvalSweepManifest | BenchmarkRunManifest) -> dict:
    """Convert a typed manifest to a plain dict for JSON serialization."""
    from dataclasses import asdict
    return asdict(manifest)


def result_to_json(result: EvalSweepResult | BenchmarkResult) -> str:
    """Serialize a result to JSON string."""
    import json
    from dataclasses import asdict
    return json.dumps(asdict(result))
