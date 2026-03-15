#!/usr/bin/env python3
"""
Canary compute loop — end-to-end proof of:
  claim -> start -> heartbeat -> submit -> verify -> payout

Runs a small eval_sweep and benchmark_run against a live (or mock) HivePoA
instance to prove the full loop works.

Usage:
    # Against live HivePoA:
    python scripts/canary_compute.py --hivepoa-url http://localhost:3000 --api-key <key>

    # Mock mode (no HivePoA needed — tests worker+verifier locally):
    python scripts/canary_compute.py --mock
"""
import argparse
import json
import logging
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from hiveai.compute.models import WorkloadType, CANARY_WORKLOADS
from hiveai.compute.verifier import get_verifier
from hiveai.compute.worker import GPUWorker, generate_instance_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("canary")


# ================================================================
# Mock HivePoA client (for local testing without a real server)
# ================================================================

@dataclass
class MockJob:
    job_id: str
    attempt_id: str
    lease_token: str
    workload_type: str
    manifest: dict
    manifest_sha256: str
    budget_hbd: float
    lease_seconds: int


@dataclass
class MockNode:
    id: str
    reputation_score: float


class MockHivePoAClient:
    """Simulates HivePoA compute API for local canary testing."""

    def __init__(self):
        self._jobs: list[MockJob] = []
        self._results: dict[str, dict] = {}
        self._claimed: set[str] = set()
        self._progress: dict[str, list] = {}

    def create_job(self, workload_type: str, manifest: dict, budget_hbd: float = 1.0,
                   lease_seconds: int = 1800, **kwargs) -> dict:
        job_id = f"canary-{uuid.uuid4().hex[:8]}"
        job = MockJob(
            job_id=job_id,
            attempt_id=f"att-{uuid.uuid4().hex[:8]}",
            lease_token=f"tok-{uuid.uuid4().hex[:12]}",
            workload_type=workload_type,
            manifest=manifest,
            manifest_sha256="mock",
            budget_hbd=budget_hbd,
            lease_seconds=lease_seconds,
        )
        self._jobs.append(job)
        logger.info(f"[MOCK] Created job {job_id} ({workload_type})")
        return {"job_id": job_id, "status": "pending"}

    def register_node(self, **kwargs) -> MockNode:
        logger.info(f"[MOCK] Registered node {kwargs.get('node_instance_id', '?')}")
        return MockNode(id="mock-node-1", reputation_score=1.0)

    def heartbeat(self, node_instance_id: str, jobs_in_progress: int = 0) -> dict:
        return {"status": "ok"}

    def drain_node(self, node_instance_id: str) -> dict:
        return {"status": "drained"}

    def claim_next_job(self, node_instance_id: str) -> MockJob | None:
        for job in self._jobs:
            if job.job_id not in self._claimed:
                self._claimed.add(job.job_id)
                logger.info(f"[MOCK] Node claimed job {job.job_id}")
                return job
        return None

    def start_job(self, job_id: str, attempt_id: str, lease_token: str) -> dict:
        logger.info(f"[MOCK] Job {job_id} started")
        return {"status": "running"}

    def report_progress(self, job_id: str, attempt_id: str, lease_token: str,
                        progress_pct: int, stage: str) -> dict:
        self._progress.setdefault(job_id, []).append({"pct": progress_pct, "stage": stage})
        return {"status": "ok"}

    def submit_result(self, job_id: str, attempt_id: str, lease_token: str,
                      output_cid: str, output_sha256: str, output_size_bytes: int,
                      metrics_json: str, result_json: str) -> dict:
        self._results[job_id] = {
            "output_cid": output_cid,
            "output_sha256": output_sha256,
            "output_size_bytes": output_size_bytes,
            "metrics_json": json.loads(metrics_json),
            "result_json": json.loads(result_json),
        }
        logger.info(f"[MOCK] Job {job_id} result submitted (score={json.loads(result_json).get('overall_score', '?')})")
        return {"status": "submitted"}

    def fail_job(self, job_id: str, attempt_id: str, lease_token: str,
                 reason: str, stderr_tail: str = "") -> dict:
        self._results[job_id] = {"status": "failed", "reason": reason}
        logger.error(f"[MOCK] Job {job_id} FAILED: {reason}")
        return {"status": "failed"}


# ================================================================
# Canary orchestrator
# ================================================================

def run_canary(client, server_url: str = "http://localhost:11435", quick: bool = True):
    """Submit canary jobs, run worker, verify results."""
    results = {}

    # Step 1: Create eval_sweep job
    logger.info("=" * 60)
    logger.info("STEP 1: Creating eval_sweep canary job")
    logger.info("=" * 60)
    eval_job = client.create_job(
        workload_type="eval_sweep",
        manifest={
            "model_name": "v5-think",
            "server_url": server_url,
            "quick": quick,
            "threshold": 0.03,
        },
        budget_hbd=0.01,
        lease_seconds=1800,
    )

    # Step 2: Create benchmark_run job
    logger.info("STEP 2: Creating benchmark_run canary job")
    bench_job = client.create_job(
        workload_type="benchmark_run",
        manifest={
            "model_name": "v5-think",
            "server_url": server_url,
            "language": "python",
        },
        budget_hbd=0.01,
        lease_seconds=1800,
    )

    # Step 3: Run worker (processes both jobs sequentially)
    logger.info("=" * 60)
    logger.info("STEP 3: Starting GPU worker")
    logger.info("=" * 60)
    instance_id = generate_instance_id()
    worker = GPUWorker(
        compute_client=client,
        node_instance_id=instance_id,
        gpu_model="RTX 4070 Ti SUPER",
        gpu_vram_gb=16,
        poll_interval=2,
        heartbeat_interval=10,
    )

    # Execute jobs (don't use worker.run() — it loops forever)
    # Instead, manually poll and execute each job
    for job_label in ["eval_sweep", "benchmark_run"]:
        logger.info(f"\n--- Executing {job_label} ---")
        worker._poll_and_execute()

    # Step 4: Verify results
    logger.info("=" * 60)
    logger.info("STEP 4: Verifying results")
    logger.info("=" * 60)

    for job_id, result_data in client._results.items():
        if result_data.get("status") == "failed":
            logger.error(f"Job {job_id}: FAILED — {result_data.get('reason', '?')}")
            results[job_id] = {"verdict": "WORKER_FAILED", "reason": result_data.get("reason")}
            continue

        result_json = result_data.get("result_json", {})
        model_name = result_json.get("model_name", "v5-think")

        # Determine workload type from job
        wtype = None
        for j in client._jobs:
            if j.job_id == job_id:
                wtype = j.workload_type
                break

        verifier = get_verifier(wtype or "eval_sweep", model_name, server_url)
        decision = verifier.verify(json.dumps(result_json))

        logger.info(
            f"Job {job_id} ({wtype}): "
            f"verdict={decision.result.value}, score={decision.score:.3f}, "
            f"hidden_matched={decision.hidden_challenges_matched}/{decision.hidden_challenges_run}"
        )
        results[job_id] = {
            "verdict": decision.result.value,
            "score": decision.score,
            "worker_overall": result_json.get("overall_score"),
            "deviation": decision.score_deviation,
        }

    # Step 5: Summary
    logger.info("=" * 60)
    logger.info("CANARY RESULTS")
    logger.info("=" * 60)
    all_pass = True
    for job_id, r in results.items():
        status = "PASS" if r["verdict"] == "pass" else "FAIL"
        if r["verdict"] != "pass":
            all_pass = False
        logger.info(f"  {job_id}: {status} (worker={r.get('worker_overall', '?')}, verifier={r.get('score', '?'):.3f})")

    if all_pass:
        logger.info("\nCANARY VERDICT: ALL PASS")
    else:
        logger.warning("\nCANARY VERDICT: SOME FAILURES — investigate above")

    return results


def main():
    parser = argparse.ArgumentParser(description="Canary compute loop")
    parser.add_argument("--hivepoa-url", type=str, default="http://localhost:3000",
                        help="HivePoA API URL")
    parser.add_argument("--api-key", type=str, default="",
                        help="HivePoA API key")
    parser.add_argument("--server-url", type=str, default="http://localhost:11435",
                        help="llama-server URL for eval/benchmark execution")
    parser.add_argument("--mock", action="store_true",
                        help="Use mock HivePoA client (no real server needed)")
    parser.add_argument("--quick", action="store_true", default=True,
                        help="Use quick eval (18 probes instead of 60)")
    args = parser.parse_args()

    if args.mock:
        client = MockHivePoAClient()
    else:
        from hiveai.dbc.compute_client import HivePoAComputeClient
        client = HivePoAComputeClient(
            base_url=args.hivepoa_url,
            api_key=args.api_key,
        )

    results = run_canary(client, server_url=args.server_url, quick=args.quick)

    # Exit with failure if any job failed verification
    if any(r.get("verdict") != "pass" for r in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
