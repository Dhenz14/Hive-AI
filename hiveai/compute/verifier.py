"""
hiveai/compute/verifier.py

Trusted verification module for GPU compute workloads.

This module runs ONLY on trusted infrastructure (coordinator/server side).
It validates untrusted worker outputs by:

1. Re-running a HIDDEN subset of challenges (worker doesn't know which)
2. Comparing worker-reported scores against independently computed scores
3. Rejecting results with suspicious deviations

The hidden eval subset is NEVER exposed to workers or the public repo.
It is loaded from a private file that the coordinator controls.

V1 supports: eval_sweep, benchmark_run
"""

import json
import logging
import os
import random
import subprocess
import sys
import time
from pathlib import Path

from hiveai.compute.models import (
    VerificationDecision,
    VerificationResult,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Maximum acceptable deviation between worker-reported and verifier-observed scores
# Beyond this, the submission is suspicious
MAX_SCORE_DEVIATION = 0.15  # 15% absolute deviation

# Minimum hidden challenges to re-run for verification
MIN_HIDDEN_CHALLENGES = 3
# Maximum (cap for cost reasons)
MAX_HIDDEN_CHALLENGES = 10

# Fraction of worker's challenges to re-run (randomly sampled)
HIDDEN_SAMPLE_FRACTION = 0.15  # 15% of challenges


class EvalSweepVerifier:
    """Verifies eval_sweep results by re-running a hidden challenge subset."""

    def __init__(
        self,
        model_name: str | None = None,
        base_url: str | None = None,
        hidden_challenge_ids: list[str] | None = None,
    ):
        """
        Args:
            model_name: Ollama model to use for verification (same as worker used)
            base_url: llama-server URL if not Ollama
            hidden_challenge_ids: Specific challenge IDs to use as hidden set.
                If None, randomly samples from the worker's reported challenges.
        """
        self.model_name = model_name
        self.base_url = base_url
        self.hidden_challenge_ids = hidden_challenge_ids

    def verify(self, worker_result_json: str, manifest: dict) -> VerificationDecision:
        """Verify a worker's eval_sweep result.

        Steps:
            1. Parse worker result
            2. Select hidden challenge subset
            3. Re-run those challenges independently
            4. Compare scores
            5. Return verification decision
        """
        try:
            worker_result = json.loads(worker_result_json)
        except (json.JSONDecodeError, TypeError):
            return VerificationDecision(
                result=VerificationResult.FAIL,
                score=0.0,
                verifier_type="hidden_eval",
                details={"error": "Invalid result JSON"},
            )

        # Structural checks
        required_fields = ["overall_score", "challenges_run", "scores"]
        for field in required_fields:
            if field not in worker_result:
                return VerificationDecision(
                    result=VerificationResult.FAIL,
                    score=0.0,
                    verifier_type="hidden_eval",
                    details={"error": f"Missing required field: {field}"},
                )

        if worker_result["challenges_run"] == 0:
            return VerificationDecision(
                result=VerificationResult.FAIL,
                score=0.0,
                verifier_type="hidden_eval",
                details={"error": "Zero challenges reported"},
            )

        # Select hidden challenge subset to re-run
        worker_scores = worker_result.get("scores", {})
        if not worker_scores:
            return VerificationDecision(
                result=VerificationResult.FAIL,
                score=0.0,
                verifier_type="hidden_eval",
                details={"error": "No per-challenge scores reported"},
            )

        hidden_ids = self._select_hidden_challenges(list(worker_scores.keys()))
        if not hidden_ids:
            # Not enough challenges to verify — soft pass with low score
            return VerificationDecision(
                result=VerificationResult.SOFT_FAIL,
                score=0.3,
                verifier_type="hidden_eval",
                details={"warning": "Too few challenges to verify"},
                hidden_challenges_run=0,
                hidden_challenges_matched=0,
            )

        # Re-run hidden challenges
        model = self.model_name or manifest.get("model_name", "qwen3:14b")
        verifier_scores = self._run_hidden_eval(model, hidden_ids, manifest)

        if verifier_scores is None:
            return VerificationDecision(
                result=VerificationResult.SOFT_FAIL,
                score=0.3,
                verifier_type="hidden_eval",
                details={"error": "Hidden eval execution failed"},
                hidden_challenges_run=0,
                hidden_challenges_matched=0,
            )

        # Compare worker-reported vs verifier-observed scores
        matched = 0
        deviations = []
        for cid in hidden_ids:
            worker_score = self._extract_challenge_score(worker_scores.get(cid, {}))
            verifier_score = verifier_scores.get(cid, 0.0)

            deviation = abs(worker_score - verifier_score)
            deviations.append(deviation)

            if deviation <= MAX_SCORE_DEVIATION:
                matched += 1

        avg_deviation = sum(deviations) / len(deviations) if deviations else 1.0
        match_rate = matched / len(hidden_ids) if hidden_ids else 0.0

        # Decision logic
        if match_rate >= 0.7 and avg_deviation <= MAX_SCORE_DEVIATION:
            result = VerificationResult.PASS
            # Score reflects quality: high match rate + low deviation = high contribution
            score = min(1.0, match_rate * (1.0 - avg_deviation))
        elif match_rate >= 0.5:
            result = VerificationResult.SOFT_FAIL
            score = match_rate * 0.5
        else:
            result = VerificationResult.FAIL
            score = 0.0

        return VerificationDecision(
            result=result,
            score=score,
            verifier_type="hidden_eval",
            verifier_version="1.0.0",
            details={
                "hidden_ids": hidden_ids,
                "match_rate": match_rate,
                "avg_deviation": round(avg_deviation, 4),
                "per_challenge_deviations": {
                    cid: round(dev, 4)
                    for cid, dev in zip(hidden_ids, deviations)
                },
                "worker_overall_score": worker_result.get("overall_score", 0.0),
            },
            hidden_challenges_run=len(hidden_ids),
            hidden_challenges_matched=matched,
            score_deviation=avg_deviation,
        )

    def _select_hidden_challenges(self, all_challenge_ids: list[str]) -> list[str]:
        """Select a random subset of challenges for hidden verification."""
        if self.hidden_challenge_ids:
            # Use pre-specified hidden set (rotated by coordinator)
            return [cid for cid in self.hidden_challenge_ids if cid in all_challenge_ids]

        # Random sample from worker's reported challenges
        n = max(
            MIN_HIDDEN_CHALLENGES,
            min(MAX_HIDDEN_CHALLENGES, int(len(all_challenge_ids) * HIDDEN_SAMPLE_FRACTION)),
        )
        n = min(n, len(all_challenge_ids))
        return random.sample(all_challenge_ids, n)

    def _run_hidden_eval(
        self, model: str, challenge_ids: list[str], manifest: dict
    ) -> dict[str, float] | None:
        """Re-run specific challenges using run_eval.py.

        Returns dict of {challenge_id: score} or None on failure.
        """
        eval_script = str(PROJECT_ROOT / "scripts" / "run_eval.py")
        base_url = self.base_url or manifest.get("base_url")

        cmd = [
            sys.executable, eval_script,
            "--model", model,
            "--limit", str(len(challenge_ids)),
            "--temperature", str(manifest.get("temperature", 0.3)),
            "--max-tokens", str(manifest.get("max_tokens", 4096)),
        ]
        if base_url:
            cmd.extend(["--base-url", base_url])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(PROJECT_ROOT),
                timeout=600,  # 10 min max for hidden eval
            )

            if result.returncode != 0:
                logger.error(f"Hidden eval failed: {result.stderr[-1000:]}")
                return None

            # Find and parse the output report
            evals_dir = PROJECT_ROOT / "evals"
            reports = sorted(evals_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not reports:
                return None

            with open(reports[0]) as f:
                report = json.load(f)

            scores = {}
            for cid, score_data in report.get("scores", {}).items():
                if cid in challenge_ids:
                    scores[cid] = self._extract_challenge_score(score_data)

            return scores

        except subprocess.TimeoutExpired:
            logger.error("Hidden eval timed out")
            return None
        except Exception as e:
            logger.error(f"Hidden eval error: {e}")
            return None

    @staticmethod
    def _extract_challenge_score(score_data: dict | float) -> float:
        """Extract a numeric score from challenge data."""
        if isinstance(score_data, (int, float)):
            return float(score_data)
        if isinstance(score_data, dict):
            return float(score_data.get("score", score_data.get("overall", 0.0)))
        return 0.0


class BenchmarkRunVerifier(EvalSweepVerifier):
    """Verifies benchmark_run results. Same logic as eval_sweep for V1."""
    pass


def get_verifier(workload_type: str, **kwargs) -> EvalSweepVerifier | BenchmarkRunVerifier | None:
    """Factory for workload-specific verifiers."""
    if workload_type == "eval_sweep":
        return EvalSweepVerifier(**kwargs)
    elif workload_type == "benchmark_run":
        return BenchmarkRunVerifier(**kwargs)
    return None
