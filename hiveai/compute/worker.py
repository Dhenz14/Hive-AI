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
        while self._running:
            try:
                self._poll_and_execute()
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}", exc_info=True)
                time.sleep(self.poll_interval)

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
        """Execute eval_sweep by running Hive-AI's run_eval.py."""
        manifest = job.manifest
        model_name = manifest.get("model_name", "qwen3:14b")
        base_url = manifest.get("base_url")
        category = manifest.get("category")
        limit = manifest.get("limit", 0)
        temperature = manifest.get("temperature", 0.3)
        max_tokens = manifest.get("max_tokens", 4096)
        workers = manifest.get("workers", 1)

        self.client.report_progress(
            job.job_id, job.attempt_id, job.lease_token, 5, "preparing"
        )

        # Build run_eval.py command
        eval_script = str(PROJECT_ROOT / "scripts" / "run_eval.py")
        cmd = [sys.executable, eval_script, "--model", model_name]

        if base_url:
            cmd.extend(["--base-url", base_url])
        if category:
            cmd.extend(["--category", category])
        if limit > 0:
            cmd.extend(["--limit", str(limit)])
        cmd.extend(["--temperature", str(temperature)])
        cmd.extend(["--max-tokens", str(max_tokens)])
        cmd.extend(["--workers", str(workers)])

        self.client.report_progress(
            job.job_id, job.attempt_id, job.lease_token, 10, "running_eval"
        )

        # Run eval — capture output
        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=job.lease_seconds - 60,  # leave 60s buffer for upload
        )
        elapsed = time.time() - start_time

        if result.returncode != 0:
            raise RuntimeError(f"run_eval.py failed (exit {result.returncode}): {result.stderr[-2000:]}")

        self.client.report_progress(
            job.job_id, job.attempt_id, job.lease_token, 90, "collecting_results"
        )

        # Find the most recent eval report
        evals_dir = PROJECT_ROOT / "evals"
        report_path = self._find_latest_eval_report(evals_dir, model_name)

        if not report_path:
            raise RuntimeError("Eval completed but no report file found in evals/")

        # Read and parse the report
        with open(report_path) as f:
            report = json.load(f)

        # Build structured result
        result_data = {
            "overall_score": report.get("overall_score", 0.0),
            "challenges_run": report.get("challenges_run", 0),
            "challenges_passed": report.get("challenges_passed", 0),
            "scores": report.get("scores", {}),
            "category_scores": report.get("category_scores", {}),
            "total_time_sec": elapsed,
            "model_name": model_name,
            "eval_harness_version": "1.0.0",
        }

        metrics_data = {
            "wall_time_sec": elapsed,
            "worker_version": "1.0.0",
            "python_version": platform.python_version(),
        }

        return json.dumps(result_data), json.dumps(metrics_data), str(report_path)

    def _execute_benchmark_run(self, job) -> tuple[str, str, str]:
        """Execute benchmark_run — same as eval_sweep but framed as benchmark."""
        # For V1, benchmark_run uses the same eval harness
        # The distinction is semantic: benchmarks are for comparison, evals are for gating
        return self._execute_eval_sweep(job)

    # ================================================================
    # Helpers
    # ================================================================

    def _find_latest_eval_report(self, evals_dir: Path, model_name: str) -> Path | None:
        """Find the most recently created eval report JSON."""
        if not evals_dir.exists():
            return None
        reports = sorted(evals_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        # Prefer reports matching the model name
        for r in reports:
            if model_name.replace(":", "-") in r.name or model_name.replace(":", "_") in r.name:
                return r
        return reports[0] if reports else None

    def _file_sha256(self, path: str) -> str:
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()

    def _start_heartbeat(self, job) -> None:
        """Background thread that sends heartbeats during job execution."""
        def _heartbeat_loop():
            while self._current_job and self._running:
                try:
                    self.client.heartbeat(self.node_instance_id, jobs_in_progress=1)
                except Exception as e:
                    logger.warning(f"Heartbeat failed: {e}")
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
