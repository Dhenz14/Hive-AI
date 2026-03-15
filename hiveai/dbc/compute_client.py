"""
hiveai/dbc/compute_client.py

Client for HivePoA's GPU Compute Marketplace API (/api/compute/*).

Used by:
  - gpu_worker.py: registers as a node, claims jobs, reports results
  - coordinator scripts: creates jobs, monitors completion, triggers settlement

Requires a HivePoA session token (Bearer auth) or agent API key.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30  # HTTP timeout seconds


@dataclass
class ComputeNodeInfo:
    id: str
    node_instance_id: str
    hive_username: str
    status: str
    gpu_model: str
    gpu_vram_gb: int
    reputation_score: int = 0
    jobs_in_progress: int = 0
    max_concurrent_jobs: int = 1


@dataclass
class ClaimedJob:
    job_id: str
    attempt_id: str
    lease_token: str
    workload_type: str
    manifest: dict
    manifest_sha256: str
    budget_hbd: str
    lease_seconds: int


class HivePoAComputeClient:
    """REST client for HivePoA /api/compute/* endpoints."""

    def __init__(
        self,
        base_url: str,
        auth_token: str | None = None,
        api_key: str | None = None,
    ):
        """
        Args:
            base_url: HivePoA server URL (e.g. "http://localhost:3000")
            auth_token: Bearer session token (for job creators)
            api_key: Agent API key (for GPU workers)
        """
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers["Content-Type"] = "application/json"

        if api_key:
            self._session.headers["Authorization"] = f"ApiKey {api_key}"
        elif auth_token:
            self._session.headers["Authorization"] = f"Bearer {auth_token}"

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _check(self, resp: requests.Response) -> dict:
        if not resp.ok:
            try:
                err = resp.json().get("error", resp.text)
            except Exception:
                err = resp.text
            raise RuntimeError(f"HivePoA API error ({resp.status_code}): {err}")
        return resp.json()

    # ================================================================
    # Node Operations
    # ================================================================

    def register_node(
        self,
        node_instance_id: str,
        gpu_model: str,
        gpu_vram_gb: int,
        supported_workloads: str,
        cached_models: str = "",
        cuda_version: str | None = None,
        cpu_cores: int | None = None,
        ram_gb: int | None = None,
        worker_version: str = "1.0.0",
        price_per_hour_hbd: str = "0.50",
        max_concurrent_jobs: int = 1,
    ) -> ComputeNodeInfo:
        """Register (or re-register) this GPU node with HivePoA."""
        payload: dict[str, Any] = {
            "nodeInstanceId": node_instance_id,
            "gpuModel": gpu_model,
            "gpuVramGb": gpu_vram_gb,
            "supportedWorkloads": supported_workloads,
            "cachedModels": cached_models,
            "workerVersion": worker_version,
            "pricePerHourHbd": price_per_hour_hbd,
            "maxConcurrentJobs": max_concurrent_jobs,
        }
        if cuda_version:
            payload["cudaVersion"] = cuda_version
        if cpu_cores:
            payload["cpuCores"] = cpu_cores
        if ram_gb:
            payload["ramGb"] = ram_gb

        data = self._check(
            self._session.post(self._url("/api/compute/nodes/register"), json=payload, timeout=DEFAULT_TIMEOUT)
        )
        logger.info(f"Node registered: {data.get('id')} ({gpu_model}, {gpu_vram_gb}GB)")
        return ComputeNodeInfo(
            id=data["id"],
            node_instance_id=data["nodeInstanceId"],
            hive_username=data["hiveUsername"],
            status=data["status"],
            gpu_model=data["gpuModel"],
            gpu_vram_gb=data["gpuVramGb"],
            reputation_score=data.get("reputationScore", 0),
            jobs_in_progress=data.get("jobsInProgress", 0),
            max_concurrent_jobs=data.get("maxConcurrentJobs", 1),
        )

    def heartbeat(self, node_instance_id: str, jobs_in_progress: int = 0) -> None:
        """Send heartbeat to keep node alive and lease valid."""
        self._check(
            self._session.post(
                self._url("/api/compute/nodes/heartbeat"),
                json={"nodeInstanceId": node_instance_id, "jobsInProgress": jobs_in_progress},
                timeout=DEFAULT_TIMEOUT,
            )
        )

    def drain_node(self, node_instance_id: str) -> None:
        """Mark node as draining — no new jobs will be assigned."""
        self._check(
            self._session.post(
                self._url("/api/compute/nodes/drain"),
                json={"nodeInstanceId": node_instance_id},
                timeout=DEFAULT_TIMEOUT,
            )
        )

    # ================================================================
    # Job Operations (Worker Side)
    # ================================================================

    def claim_next_job(self, node_instance_id: str) -> ClaimedJob | None:
        """Atomically claim the next eligible job. Returns None if no jobs available."""
        data = self._check(
            self._session.post(
                self._url("/api/compute/jobs/claim-next"),
                json={"nodeInstanceId": node_instance_id},
                timeout=DEFAULT_TIMEOUT,
            )
        )
        if not data.get("job"):
            return None

        job = data["job"]
        attempt = data["attempt"]
        return ClaimedJob(
            job_id=job["id"],
            attempt_id=attempt["id"],
            lease_token=attempt["leaseToken"],
            workload_type=job["workloadType"],
            manifest=json.loads(job["manifestJson"]) if isinstance(job["manifestJson"], str) else job["manifestJson"],
            manifest_sha256=job["manifestSha256"],
            budget_hbd=job["budgetHbd"],
            lease_seconds=job["leaseSeconds"],
        )

    def start_job(self, job_id: str, attempt_id: str, lease_token: str) -> None:
        """Signal that job execution has started."""
        self._check(
            self._session.post(
                self._url(f"/api/compute/jobs/{job_id}/start"),
                json={"attemptId": attempt_id, "leaseToken": lease_token},
                timeout=DEFAULT_TIMEOUT,
            )
        )

    def report_progress(
        self, job_id: str, attempt_id: str, lease_token: str,
        progress_pct: int, current_stage: str | None = None,
    ) -> None:
        """Report execution progress (also serves as heartbeat)."""
        payload: dict[str, Any] = {
            "attemptId": attempt_id,
            "leaseToken": lease_token,
            "progressPct": progress_pct,
        }
        if current_stage:
            payload["currentStage"] = current_stage
        self._check(
            self._session.post(
                self._url(f"/api/compute/jobs/{job_id}/progress"),
                json=payload,
                timeout=DEFAULT_TIMEOUT,
            )
        )

    def submit_result(
        self, job_id: str, attempt_id: str, lease_token: str,
        output_cid: str, output_sha256: str,
        output_size_bytes: int | None = None,
        output_transport_url: str | None = None,
        metrics_json: str | None = None,
        result_json: str | None = None,
    ) -> dict:
        """Submit completed job result for verification."""
        payload: dict[str, Any] = {
            "attemptId": attempt_id,
            "leaseToken": lease_token,
            "outputCid": output_cid,
            "outputSha256": output_sha256,
        }
        if output_size_bytes is not None:
            payload["outputSizeBytes"] = output_size_bytes
        if output_transport_url:
            payload["outputTransportUrl"] = output_transport_url
        if metrics_json:
            payload["metricsJson"] = metrics_json
        if result_json:
            payload["resultJson"] = result_json

        return self._check(
            self._session.post(
                self._url(f"/api/compute/jobs/{job_id}/submit"),
                json=payload,
                timeout=DEFAULT_TIMEOUT,
            )
        )

    def fail_job(
        self, job_id: str, attempt_id: str, lease_token: str,
        reason: str, stderr_tail: str | None = None,
    ) -> None:
        """Report job failure."""
        payload: dict[str, Any] = {
            "attemptId": attempt_id,
            "leaseToken": lease_token,
            "reason": reason,
        }
        if stderr_tail:
            payload["stderrTail"] = stderr_tail[:4000]
        self._check(
            self._session.post(
                self._url(f"/api/compute/jobs/{job_id}/fail"),
                json=payload,
                timeout=DEFAULT_TIMEOUT,
            )
        )

    # ================================================================
    # Job Operations (Coordinator Side)
    # ================================================================

    def create_job(
        self,
        workload_type: str,
        manifest: dict,
        budget_hbd: str,
        priority: int = 0,
        min_vram_gb: int = 16,
        required_models: str = "",
        lease_seconds: int = 3600,
        max_attempts: int = 3,
    ) -> dict:
        """Create a compute job on HivePoA."""
        return self._check(
            self._session.post(
                self._url("/api/compute/jobs"),
                json={
                    "workloadType": workload_type,
                    "manifest": manifest,
                    "budgetHbd": budget_hbd,
                    "priority": priority,
                    "minVramGb": min_vram_gb,
                    "requiredModels": required_models,
                    "leaseSeconds": lease_seconds,
                    "maxAttempts": max_attempts,
                },
                timeout=DEFAULT_TIMEOUT,
            )
        )

    def get_job(self, job_id: str) -> dict:
        """Get job details including attempts, verifications, and payouts."""
        return self._check(
            self._session.get(self._url(f"/api/compute/jobs/{job_id}"), timeout=DEFAULT_TIMEOUT)
        )

    def get_my_jobs(self, limit: int = 50) -> list[dict]:
        """List jobs created by the authenticated user."""
        return self._check(
            self._session.get(self._url(f"/api/compute/jobs?limit={limit}"), timeout=DEFAULT_TIMEOUT)
        )

    def settle_payouts(self, job_id: str) -> dict:
        """Trigger payout settlement for a completed job."""
        return self._check(
            self._session.post(self._url(f"/api/compute/jobs/{job_id}/settle"), timeout=DEFAULT_TIMEOUT)
        )

    def get_stats(self) -> dict:
        """Get network-wide compute stats."""
        return self._check(
            self._session.get(self._url("/api/compute/stats"), timeout=DEFAULT_TIMEOUT)
        )

    def estimate_cost(self, workload_type: str, min_vram_gb: int = 16) -> dict:
        """Estimate cost for a workload."""
        return self._check(
            self._session.get(
                self._url(f"/api/compute/estimate?workloadType={workload_type}&minVramGb={min_vram_gb}"),
                timeout=DEFAULT_TIMEOUT,
            )
        )


def compute_file_sha256(file_path: str) -> str:
    """SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()
