"""
hiveai/compute/worker.py

Untrusted GPU worker runtime.

Registers with HivePoA, claims typed jobs, executes them using
Hive-AI's existing eval/benchmark scripts, and reports results.

V1 supports only: eval_sweep, benchmark_run
The worker has ZERO freedom over hyperparameters, model choice,
or verification logic. It executes the manifest exactly.

Usage (via scripts/gpu_worker.py):
    python scripts/gpu_worker.py --hivepoa-url http://localhost:3000 --api-key <key>
"""

import hashlib
import json
import logging
import os
import platform
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class GPUWorker:
    """Untrusted GPU worker runtime."""

    def __init__(
        self,
        compute_client,  # HivePoAComputeClient instance
        node_instance_id: str,
        gpu_model: str = "unknown",
        gpu_vram_gb: int = 16,
        supported_workloads: str = "eval_sweep,benchmark_run",
        cached_models: str = "",
        cuda_version: str | None = None,
        poll_interval: int = 30,
        heartbeat_interval: int = 20,
    ):
        self.client = compute_client
        self.node_instance_id = node_instance_id
        self.gpu_model = gpu_model
        self.gpu_vram_gb = gpu_vram_gb
        self.supported_workloads = supported_workloads
        self.cached_models = cached_models
        self.cuda_version = cuda_version
        self.poll_interval = poll_interval
        self.heartbeat_interval = heartbeat_interval

        self._running = False
        self._current_job = None
        self._heartbeat_thread: threading.Thread | None = None

    def run(self) -> None:
        """Main worker loop. Blocks until interrupted."""
        self._running = True
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        # Register with HivePoA
        node = self.client.register_node(
            node_instance_id=self.node_instance_id,
            gpu_model=self.gpu_model,
            gpu_vram_gb=self.gpu_vram_gb,
            supported_workloads=self.supported_workloads,
            cached_models=self.cached_models,
            cuda_version=self.cuda_version,
            worker_version="1.0.0",
        )
        logger.info(f"Registered as node {node.id} (rep={node.reputation_score})")

        logger.info(f"Worker loop started — polling every {self.poll_interval}s")
        consecutive_errors = 0
        while self._running:
            try:
                self._poll_and_execute()
                consecutive_errors = 0
            except KeyboardInterrupt:
                break
            except Exception as e:
                consecutive_errors += 1
                backoff = min(self.poll_interval * (2 ** min(consecutive_errors, 5)), 300)
                logger.error(f"Worker loop error (backoff {backoff}s): {e}", exc_info=True)
                time.sleep(backoff)

        logger.info("Worker shutting down")
        try:
            self.client.drain_node(self.node_instance_id)
        except Exception:
            pass

    def _shutdown(self, signum, frame):
        logger.info("Shutdown signal received")
        self._running = False

    def _poll_and_execute(self) -> None:
        """Poll for a job, execute it, report result."""
        claimed = self.client.claim_next_job(self.node_instance_id)
        if not claimed:
            time.sleep(self.poll_interval)
            return

        self._current_job = claimed
        logger.info(f"Claimed job {claimed.job_id} ({claimed.workload_type})")

        # Start heartbeat thread
        self._start_heartbeat(claimed)

        try:
            # Signal job started
            self.client.start_job(claimed.job_id, claimed.attempt_id, claimed.lease_token)

            # Execute based on workload type
            if claimed.workload_type == "eval_sweep":
                result_json, metrics_json, output_path = self._execute_eval_sweep(claimed)
            elif claimed.workload_type == "benchmark_run":
                result_json, metrics_json, output_path = self._execute_benchmark_run(claimed)
            else:
                raise ValueError(f"Unsupported workload type: {claimed.workload_type}")

            # Compute artifact hash
            output_sha256 = self._file_sha256(output_path)
            output_size = os.path.getsize(output_path)

            # For V1, output_cid is the sha256 (no IPFS pinning yet — the coordinator
            # can fetch via transport URL or the result JSON contains the full data)
            output_cid = f"sha256:{output_sha256}"

            # Submit result
            self.client.submit_result(
                job_id=claimed.job_id,
                attempt_id=claimed.attempt_id,
                lease_token=claimed.lease_token,
                output_cid=output_cid,
                output_sha256=output_sha256,
                output_size_bytes=output_size,
                metrics_json=metrics_json,
                result_json=result_json,
            )
            logger.info(f"Job {claimed.job_id} submitted successfully")

        except Exception as e:
            logger.error(f"Job {claimed.job_id} failed: {e}", exc_info=True)
            try:
                self.client.fail_job(
                    job_id=claimed.job_id,
                    attempt_id=claimed.attempt_id,
                    lease_token=claimed.lease_token,
                    reason=str(e)[:1000],
                    stderr_tail=str(e)[:4000],
                )
            except Exception as report_err:
                logger.error(f"Failed to report failure: {report_err}")
        finally:
            self._stop_heartbeat()
            self._current_job = None

    # ================================================================
    # Workload Executors
    # ================================================================

    def _execute_eval_sweep(self, job) -> tuple[str, str, str]:
        """Execute eval_sweep using Hive-AI's regression_eval.py (60-probe domain eval).

        Manifest fields:
            model_name: str — version label (e.g. "v5-think")
            server_url: str — llama-server URL (default http://localhost:11435)
            quick: bool — use 18 probes instead of 60 (default false)
            threshold: float — max regression per domain (default 0.03)
        """
        manifest = job.manifest
        model_name = manifest.get("model_name", "v5-think")
        server_url = manifest.get("server_url", "http://localhost:11435")
        quick = manifest.get("quick", False)
        threshold = manifest.get("threshold", 0.03)

        self.client.report_progress(
            job.job_id, job.attempt_id, job.lease_token, 5, "preparing"
        )

        # Use explicit output file to avoid mtime-based discovery races
        output_file = tempfile.NamedTemporaryFile(
            prefix=f"eval_{job.job_id}_", suffix=".json", delete=False, dir=str(PROJECT_ROOT / "evals")
        )
        output_path = output_file.name
        output_file.close()

        eval_script = str(PROJECT_ROOT / "scripts" / "regression_eval.py")
        if not Path(eval_script).exists():
            raise RuntimeError(f"Eval script not found: {eval_script}")

        cmd = [sys.executable, eval_script,
               "--model-version", model_name,
               "--server-url", server_url,
               "--threshold", str(threshold)]
        if quick:
            cmd.append("--quick")

        self.client.report_progress(
            job.job_id, job.attempt_id, job.lease_token, 10, "running_eval"
        )

        start_time = time.time()
        timeout = min(job.lease_seconds - 60, 1800)  # cap at 30 min, leave 60s buffer
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(PROJECT_ROOT), timeout=timeout,
        )
        elapsed = time.time() - start_time

        # regression_eval.py writes to score_ledger.json and prints to stdout.
        # Parse stdout for domain scores (format: "domain: X.XX")
        scores = self._parse_regression_output(proc.stdout, model_name)

        if not scores:
            raise RuntimeError(
                f"regression_eval.py produced no parseable scores "
                f"(exit {proc.returncode}): {proc.stderr[-2000:]}"
            )

        overall = scores.get("overall", sum(scores.values()) / max(len(scores), 1))
        passed = proc.returncode == 0

        result_data = {
            "overall_score": overall,
            "challenges_run": 60 if not quick else 18,
            "challenges_passed": int(overall * (60 if not quick else 18)),
            "scores": scores,
            "category_scores": {k: v for k, v in scores.items() if k != "overall"},
            "total_time_sec": elapsed,
            "model_name": model_name,
            "eval_harness_version": "1.0.0",
            "regression_passed": passed,
        }

        # Write explicit output file
        with open(output_path, "w") as f:
            json.dump(result_data, f, indent=2)

        metrics_data = {
            "wall_time_sec": elapsed,
            "worker_version": "1.0.0",
            "python_version": platform.python_version(),
            "exit_code": proc.returncode,
        }

        self.client.report_progress(
            job.job_id, job.attempt_id, job.lease_token, 95, "submitting"
        )

        return json.dumps(result_data), json.dumps(metrics_data), output_path

    def _execute_benchmark_run(self, job) -> tuple[str, str, str]:
        """Execute benchmark_run using executable_eval.py (sandbox-verified code gen).

        Manifest fields:
            model_name: str — version label
            server_url: str — llama-server URL
            language: str — filter ("python", "cpp", "javascript", "" for all)
        """
        manifest = job.manifest
        model_name = manifest.get("model_name", "v5-think")
        server_url = manifest.get("server_url", "http://localhost:11435")
        language = manifest.get("language", "")

        self.client.report_progress(
            job.job_id, job.attempt_id, job.lease_token, 5, "preparing"
        )

        output_file = tempfile.NamedTemporaryFile(
            prefix=f"bench_{job.job_id}_", suffix=".json", delete=False, dir=str(PROJECT_ROOT / "evals")
        )
        output_path = output_file.name
        output_file.close()

        bench_script = str(PROJECT_ROOT / "scripts" / "executable_eval.py")
        if not Path(bench_script).exists():
            raise RuntimeError(f"Benchmark script not found: {bench_script}")

        cmd = [sys.executable, bench_script,
               "--server-url", server_url,
               "--output", output_path]
        if language:
            cmd.extend(["--language", language])

        self.client.report_progress(
            job.job_id, job.attempt_id, job.lease_token, 10, "running_benchmark"
        )

        start_time = time.time()
        timeout = min(job.lease_seconds - 60, 1800)
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(PROJECT_ROOT), timeout=timeout,
        )
        elapsed = time.time() - start_time

        if proc.returncode != 0:
            raise RuntimeError(
                f"executable_eval.py failed (exit {proc.returncode}): {proc.stderr[-2000:]}"
            )

        with open(output_path) as f:
            report = json.load(f)

        result_data = {
            "overall_score": report.get("pass_rate", 0.0),
            "challenges_run": report.get("total_prompts", 0),
            "challenges_passed": report.get("prompts_passing", 0),
            "scores": report.get("by_language", {}),
            "category_scores": report.get("by_language", {}),
            "total_time_sec": elapsed,
            "model_name": model_name,
            "eval_harness_version": "1.0.0",
            "blocks_total": report.get("total_blocks", 0),
            "blocks_passing": report.get("blocks_passing", 0),
        }

        # Overwrite with structured result
        with open(output_path, "w") as f:
            json.dump(result_data, f, indent=2)

        metrics_data = {
            "wall_time_sec": elapsed,
            "worker_version": "1.0.0",
            "python_version": platform.python_version(),
            "exit_code": proc.returncode,
        }

        self.client.report_progress(
            job.job_id, job.attempt_id, job.lease_token, 95, "submitting"
        )

        return json.dumps(result_data), json.dumps(metrics_data), output_path

    def _parse_regression_output(self, stdout: str, model_name: str) -> dict:
        """Parse regression_eval.py stdout or score_ledger.json for domain scores."""
        # Try score_ledger.json first (most reliable)
        ledger_path = PROJECT_ROOT / "score_ledger.json"
        if ledger_path.exists():
            try:
                with open(ledger_path) as f:
                    ledger = json.load(f)
                if model_name in ledger:
                    return ledger[model_name]
            except (json.JSONDecodeError, KeyError):
                pass

        # Fallback: parse stdout lines like "python: 0.9342"
        import re
        scores = {}
        for line in stdout.splitlines():
            m = re.match(r'\s*(\w+)\s*:\s*([\d.]+)', line)
            if m and m.group(1) in ("python", "rust", "go", "cpp", "js", "hive", "overall"):
                scores[m.group(1)] = float(m.group(2))
        return scores

    # ================================================================
    # Helpers
    # ================================================================

    def _file_sha256(self, path: str) -> str:
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()

    def _start_heartbeat(self, job) -> None:
        """Background thread that sends heartbeats during job execution."""
        job_id = job.job_id

        def _heartbeat_loop():
            while self._current_job and self._running:
                try:
                    in_progress = 1 if self._current_job else 0
                    self.client.heartbeat(self.node_instance_id, jobs_in_progress=in_progress)
                except Exception as e:
                    logger.warning(f"Heartbeat failed for job {job_id}: {e}")
                time.sleep(self.heartbeat_interval)

        self._heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        self._heartbeat_thread = None


def generate_instance_id() -> str:
    """Generate a stable node instance ID based on machine identity.
    Persisted to disk so it survives restarts.
    """
    id_file = PROJECT_ROOT / ".gpu_worker_id"
    if id_file.exists():
        return id_file.read_text().strip()

    instance_id = f"gpu-{platform.node()}-{uuid.uuid4().hex[:12]}"
    id_file.write_text(instance_id)
    logger.info(f"Generated new node instance ID: {instance_id}")
    return instance_id
