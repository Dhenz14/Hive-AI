"""
hiveai/compute/verifier.py

Trusted verification module for GPU compute workloads.

This module runs ONLY on trusted infrastructure (coordinator/server side).
It validates untrusted worker outputs by:

1. Re-running the SAME eval/benchmark independently (job-scoped output)
2. Comparing worker-reported per-domain scores against verifier-observed scores
3. Rejecting results with suspicious deviations

V1 supports: eval_sweep (regression_eval.py), benchmark_run (executable_eval.py)

IMPORTANT: Every verifier run writes to a unique, job-scoped output file.
No shared mutable state. No mtime-based file discovery.
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from hiveai.compute.models import (
    VerificationDecision,
    VerificationResult,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Maximum acceptable deviation between worker-reported and verifier-observed scores
MAX_SCORE_DEVIATION = 0.15  # 15% absolute deviation per domain

# Minimum domains that must match for a PASS
MIN_MATCH_RATE = 0.7  # 70% of domains must be within tolerance


class EvalSweepVerifier:
    """Verifies eval_sweep (regression_eval.py) results.

    Compares worker-reported per-domain scores against an independent
    regression eval run on the verifier side. Uses job-scoped output
    files to prevent cross-contamination between concurrent runs.
    """

    def __init__(
        self,
        model_name: str | None = None,
        server_url: str | None = None,
    ):
        self.model_name = model_name
        self.server_url = server_url

    def verify(self, worker_result_json: str, manifest: dict) -> VerificationDecision:
        """Verify a worker's eval_sweep result."""
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
        for field in ("overall_score", "challenges_run", "scores"):
            if field not in worker_result:
                return VerificationDecision(
                    result=VerificationResult.FAIL,
                    score=0.0,
                    verifier_type="hidden_eval",
                    details={"error": f"Missing required field: {field}"},
                )

        worker_scores = worker_result.get("scores", {})
        if not worker_scores:
            return VerificationDecision(
                result=VerificationResult.FAIL,
                score=0.0,
                verifier_type="hidden_eval",
                details={"error": "No per-domain scores reported"},
            )

        # Re-run regression eval independently
        model = self.model_name or manifest.get("model_name", "v5-think")
        url = self.server_url or manifest.get("server_url", "http://localhost:11435")
        quick = manifest.get("quick", False)

        verifier_scores = self._run_regression_eval(model, url, quick)
        if verifier_scores is None:
            return VerificationDecision(
                result=VerificationResult.SOFT_FAIL,
                score=0.3,
                verifier_type="hidden_eval",
                details={"error": "Verifier regression eval failed"},
                hidden_challenges_run=0,
                hidden_challenges_matched=0,
            )

        # Compare per-domain scores
        all_domains = set(worker_scores.keys()) | set(verifier_scores.keys())
        # Exclude meta keys
        compare_domains = [d for d in all_domains if d not in ("overall", "model_name", "eval_harness_version")]

        if not compare_domains:
            return VerificationDecision(
                result=VerificationResult.SOFT_FAIL,
                score=0.3,
                verifier_type="hidden_eval",
                details={"warning": "No comparable domains found"},
                hidden_challenges_run=0,
                hidden_challenges_matched=0,
            )

        matched = 0
        deviations = {}
        for domain in compare_domains:
            w_score = self._to_float(worker_scores.get(domain, 0.0))
            v_score = self._to_float(verifier_scores.get(domain, 0.0))
            dev = abs(w_score - v_score)
            deviations[domain] = round(dev, 4)
            if dev <= MAX_SCORE_DEVIATION:
                matched += 1

        match_rate = matched / len(compare_domains)
        avg_deviation = sum(deviations.values()) / len(deviations) if deviations else 1.0

        # Decision
        if match_rate >= MIN_MATCH_RATE and avg_deviation <= MAX_SCORE_DEVIATION:
            result = VerificationResult.PASS
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
                "domains_compared": compare_domains,
                "match_rate": round(match_rate, 4),
                "avg_deviation": round(avg_deviation, 4),
                "per_domain_deviations": deviations,
                "worker_overall": worker_result.get("overall_score", 0.0),
                "verifier_overall": verifier_scores.get("overall", 0.0),
            },
            hidden_challenges_run=len(compare_domains),
            hidden_challenges_matched=matched,
            score_deviation=avg_deviation,
        )

    def _run_regression_eval(self, model: str, server_url: str, quick: bool) -> dict | None:
        """Run regression_eval.py with a job-scoped output, return domain scores."""
        eval_script = str(PROJECT_ROOT / "scripts" / "regression_eval.py")
        if not Path(eval_script).exists():
            logger.error(f"regression_eval.py not found at {eval_script}")
            return None

        # Job-scoped ledger file — no shared mutable state
        with tempfile.NamedTemporaryFile(
            prefix="verifier_ledger_", suffix=".json", delete=False,
            dir=str(PROJECT_ROOT / "evals"),
        ) as f:
            ledger_path = f.name

        cmd = [
            sys.executable, eval_script,
            "--model-version", f"verifier-{model}",
            "--server-url", server_url,
            "--ledger", ledger_path,
        ]
        if quick:
            cmd.append("--quick")

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=str(PROJECT_ROOT), timeout=600,
            )

            # Parse from job-scoped ledger (not shared score_ledger.json)
            scores = self._parse_ledger(ledger_path, f"verifier-{model}")
            if scores:
                return scores

            # Fallback: parse stdout
            scores = self._parse_stdout(proc.stdout)
            return scores if scores else None

        except subprocess.TimeoutExpired:
            logger.error("Verifier regression eval timed out")
            return None
        except Exception as e:
            logger.error(f"Verifier regression eval error: {e}")
            return None
        finally:
            # Clean up job-scoped ledger
            try:
                os.unlink(ledger_path)
            except OSError:
                pass

    @staticmethod
    def _parse_ledger(path: str, model_key: str) -> dict | None:
        """Parse a job-scoped score_ledger.json."""
        try:
            with open(path) as f:
                ledger = json.load(f)
            return ledger.get(model_key)
        except (json.JSONDecodeError, FileNotFoundError, KeyError):
            return None

    @staticmethod
    def _parse_stdout(stdout: str) -> dict | None:
        """Parse regression_eval.py stdout for domain scores."""
        import re
        scores = {}
        for line in stdout.splitlines():
            m = re.match(r'\s*(\w+)\s*:\s*([\d.]+)', line)
            if m and m.group(1) in ("python", "rust", "go", "cpp", "js", "hive", "overall"):
                scores[m.group(1)] = float(m.group(2))
        return scores if scores else None

    @staticmethod
    def _to_float(val) -> float:
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, dict):
            return float(val.get("score", val.get("overall", 0.0)))
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0


class BenchmarkRunVerifier:
    """Verifies benchmark_run (executable_eval.py) results.

    Re-runs the benchmark independently and compares pass rates.
    """

    def __init__(
        self,
        model_name: str | None = None,
        server_url: str | None = None,
    ):
        self.model_name = model_name
        self.server_url = server_url

    def verify(self, worker_result_json: str, manifest: dict) -> VerificationDecision:
        """Verify a worker's benchmark_run result."""
        try:
            worker_result = json.loads(worker_result_json)
        except (json.JSONDecodeError, TypeError):
            return VerificationDecision(
                result=VerificationResult.FAIL,
                score=0.0,
                verifier_type="hidden_benchmark",
                details={"error": "Invalid result JSON"},
            )

        for field in ("overall_score", "challenges_run"):
            if field not in worker_result:
                return VerificationDecision(
                    result=VerificationResult.FAIL,
                    score=0.0,
                    verifier_type="hidden_benchmark",
                    details={"error": f"Missing required field: {field}"},
                )

        # Re-run benchmark independently
        url = self.server_url or manifest.get("server_url", "http://localhost:11435")
        language = manifest.get("language", "")

        verifier_result = self._run_benchmark(url, language)
        if verifier_result is None:
            return VerificationDecision(
                result=VerificationResult.SOFT_FAIL,
                score=0.3,
                verifier_type="hidden_benchmark",
                details={"error": "Verifier benchmark execution failed"},
                hidden_challenges_run=0,
                hidden_challenges_matched=0,
            )

        # Compare pass rates
        worker_pass_rate = float(worker_result.get("overall_score", 0.0))
        verifier_pass_rate = float(verifier_result.get("pass_rate", 0.0))
        deviation = abs(worker_pass_rate - verifier_pass_rate)

        # Compare per-language if available
        worker_by_lang = worker_result.get("scores", {})
        verifier_by_lang = verifier_result.get("by_language", {})
        lang_deviations = {}
        lang_matched = 0
        all_langs = set(worker_by_lang.keys()) | set(verifier_by_lang.keys())
        for lang in all_langs:
            w = self._extract_lang_score(worker_by_lang.get(lang, 0.0))
            v = self._extract_lang_score(verifier_by_lang.get(lang, 0.0))
            d = abs(w - v)
            lang_deviations[lang] = round(d, 4)
            if d <= MAX_SCORE_DEVIATION:
                lang_matched += 1

        match_rate = lang_matched / len(all_langs) if all_langs else (1.0 if deviation <= MAX_SCORE_DEVIATION else 0.0)

        if deviation <= MAX_SCORE_DEVIATION and match_rate >= MIN_MATCH_RATE:
            result = VerificationResult.PASS
            score = min(1.0, (1.0 - deviation) * match_rate)
        elif deviation <= MAX_SCORE_DEVIATION * 2:
            result = VerificationResult.SOFT_FAIL
            score = 0.4
        else:
            result = VerificationResult.FAIL
            score = 0.0

        return VerificationDecision(
            result=result,
            score=score,
            verifier_type="hidden_benchmark",
            verifier_version="1.0.0",
            details={
                "worker_pass_rate": worker_pass_rate,
                "verifier_pass_rate": verifier_pass_rate,
                "overall_deviation": round(deviation, 4),
                "per_language_deviations": lang_deviations,
                "match_rate": round(match_rate, 4),
            },
            hidden_challenges_run=len(all_langs) if all_langs else 1,
            hidden_challenges_matched=lang_matched if all_langs else (1 if deviation <= MAX_SCORE_DEVIATION else 0),
            score_deviation=deviation,
        )

    def _run_benchmark(self, server_url: str, language: str) -> dict | None:
        """Run executable_eval.py with a job-scoped output file."""
        bench_script = str(PROJECT_ROOT / "scripts" / "executable_eval.py")
        if not Path(bench_script).exists():
            logger.error(f"executable_eval.py not found at {bench_script}")
            return None

        # Job-scoped output file
        with tempfile.NamedTemporaryFile(
            prefix="verifier_bench_", suffix=".json", delete=False,
            dir=str(PROJECT_ROOT / "evals"),
        ) as f:
            output_path = f.name

        cmd = [
            sys.executable, bench_script,
            "--server-url", server_url,
            "--output", output_path,
        ]
        if language:
            cmd.extend(["--language", language])

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=str(PROJECT_ROOT), timeout=600,
            )

            if proc.returncode != 0:
                logger.error(f"Verifier benchmark failed: {proc.stderr[-1000:]}")
                return None

            with open(output_path) as f:
                return json.load(f)

        except subprocess.TimeoutExpired:
            logger.error("Verifier benchmark timed out")
            return None
        except Exception as e:
            logger.error(f"Verifier benchmark error: {e}")
            return None
        finally:
            try:
                os.unlink(output_path)
            except OSError:
                pass

    @staticmethod
    def _extract_lang_score(val) -> float:
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, dict):
            return float(val.get("pass_rate", val.get("score", 0.0)))
        return 0.0


def get_verifier(workload_type: str, **kwargs) -> EvalSweepVerifier | BenchmarkRunVerifier | None:
    """Factory for workload-specific verifiers."""
    if workload_type == "eval_sweep":
        return EvalSweepVerifier(**kwargs)
    elif workload_type == "benchmark_run":
        return BenchmarkRunVerifier(**kwargs)
    return None
