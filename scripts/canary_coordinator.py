"""
scripts/canary_coordinator.py

Minimal coordinator for testing the full GPU compute canary loop.

Creates eval_sweep and benchmark_run jobs on HivePoA, monitors completion,
runs hidden verification on accepted results, and reports outcomes.

Usage:
    # Create an eval sweep job
    python scripts/canary_coordinator.py \\
        --hivepoa-url http://localhost:3000 \\
        --auth-token <session-token> \\
        create-eval --model qwen3:14b --budget 1.000

    # Create a benchmark job
    python scripts/canary_coordinator.py \\
        --hivepoa-url http://localhost:3000 \\
        --auth-token <session-token> \\
        create-benchmark --model qwen3:14b --budget 1.000

    # Monitor a job until completion
    python scripts/canary_coordinator.py \\
        --hivepoa-url http://localhost:3000 \\
        --auth-token <token> \\
        monitor --job-id <id>

    # Verify a completed job's result (run hidden eval)
    python scripts/canary_coordinator.py \\
        --hivepoa-url http://localhost:3000 \\
        --auth-token <token> \\
        verify --job-id <id>

    # Full canary loop: create → wait → verify → settle
    python scripts/canary_coordinator.py \\
        --hivepoa-url http://localhost:3000 \\
        --auth-token <token> \\
        canary --model qwen3:14b --budget 1.000
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from hiveai.dbc.compute_client import HivePoAComputeClient
from hiveai.compute.models import (
    EvalSweepManifest,
    BenchmarkRunManifest,
    manifest_to_dict,
    SCHEMA_VERSION,
)
from hiveai.compute.verifier import get_verifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("coordinator")


def create_eval_job(client: HivePoAComputeClient, model: str, budget: str, limit: int = 0, category: str | None = None) -> str:
    """Create an eval_sweep job on HivePoA. Returns job ID."""
    manifest = EvalSweepManifest(
        model_name=model,
        limit=limit,
        category=category,
    )
    job = client.create_job(
        workload_type="eval_sweep",
        manifest=manifest_to_dict(manifest),
        budget_hbd=budget,
        min_vram_gb=16,
        required_models=model,
        lease_seconds=3600,
    )
    logger.info(f"Created eval_sweep job: {job['id']} (budget={budget} HBD)")
    return job["id"]


def create_benchmark_job(client: HivePoAComputeClient, model: str, budget: str, limit: int = 0) -> str:
    """Create a benchmark_run job on HivePoA. Returns job ID."""
    manifest = BenchmarkRunManifest(
        model_name=model,
        limit=limit,
    )
    job = client.create_job(
        workload_type="benchmark_run",
        manifest=manifest_to_dict(manifest),
        budget_hbd=budget,
        min_vram_gb=16,
        required_models=model,
        lease_seconds=3600,
    )
    logger.info(f"Created benchmark_run job: {job['id']} (budget={budget} HBD)")
    return job["id"]


def monitor_job(client: HivePoAComputeClient, job_id: str, poll_interval: int = 15, timeout: int = 3600) -> dict:
    """Poll job until terminal state. Returns full job data."""
    terminal_states = {"accepted", "rejected", "expired", "cancelled"}
    start = time.time()

    while time.time() - start < timeout:
        data = client.get_job(job_id)
        state = data.get("state", "unknown")
        progress = 0
        if data.get("attempts"):
            latest = data["attempts"][0]
            progress = latest.get("progressPct", 0)

        logger.info(f"Job {job_id}: state={state}, progress={progress}%")

        if state in terminal_states:
            return data

        time.sleep(poll_interval)

    logger.warning(f"Job {job_id} timed out after {timeout}s")
    return client.get_job(job_id)


def verify_job(client: HivePoAComputeClient, job_id: str) -> dict:
    """Run hidden verification on a completed job's result."""
    data = client.get_job(job_id)
    state = data.get("state")
    workload_type = data.get("workloadType")

    if state != "accepted":
        logger.warning(f"Job {job_id} is in state '{state}', not 'accepted'. Verifying anyway.")

    # Get the accepted attempt's result
    attempts = data.get("attempts", [])
    accepted = next((a for a in attempts if a.get("state") == "accepted"), None)
    if not accepted:
        logger.error(f"No accepted attempt found for job {job_id}")
        return {"error": "No accepted attempt"}

    result_json = accepted.get("resultJson")
    if not result_json:
        logger.error("Accepted attempt has no result JSON")
        return {"error": "No result JSON"}

    manifest = json.loads(data.get("manifestJson", "{}"))

    # Create workload-specific verifier
    verifier = get_verifier(workload_type, model_name=manifest.get("model_name"))
    if not verifier:
        logger.error(f"No verifier for workload type: {workload_type}")
        return {"error": f"Unsupported workload type: {workload_type}"}

    # Run hidden verification
    logger.info(f"Running hidden verification for job {job_id} ({workload_type})")
    decision = verifier.verify(result_json, manifest)

    logger.info(
        f"Verification result: {decision.result.value} "
        f"(score={decision.score:.3f}, "
        f"hidden={decision.hidden_challenges_matched}/{decision.hidden_challenges_run}, "
        f"deviation={decision.score_deviation:.4f})"
    )

    return {
        "result": decision.result.value,
        "score": decision.score,
        "hidden_challenges_run": decision.hidden_challenges_run,
        "hidden_challenges_matched": decision.hidden_challenges_matched,
        "score_deviation": decision.score_deviation,
        "details": decision.details,
    }


def run_canary(client: HivePoAComputeClient, model: str, budget: str, limit: int = 10) -> None:
    """Full canary loop: create → wait → verify → settle."""
    logger.info("=" * 60)
    logger.info("CANARY LOOP: eval_sweep")
    logger.info("=" * 60)

    # 1. Create job
    job_id = create_eval_job(client, model, budget, limit=limit)

    # 2. Wait for completion
    logger.info("Waiting for worker to claim and complete job...")
    result = monitor_job(client, job_id)
    state = result.get("state")
    logger.info(f"Job finished with state: {state}")

    if state != "accepted":
        logger.error(f"Job not accepted (state={state}). Canary failed.")
        return

    # 3. Run hidden verification
    verification = verify_job(client, job_id)
    if verification.get("result") != "pass":
        logger.warning(f"Hidden verification: {verification.get('result')}")
    else:
        logger.info("Hidden verification PASSED")

    # 4. Settle payouts
    try:
        settled = client.settle_payouts(job_id)
        logger.info(f"Payouts settled: {settled.get('settled', 0)} items")
    except Exception as e:
        logger.warning(f"Payout settlement: {e}")

    logger.info("=" * 60)
    logger.info("CANARY LOOP COMPLETE")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="HivePoA GPU Compute Canary Coordinator")
    parser.add_argument("--hivepoa-url", type=str, required=True)
    parser.add_argument("--auth-token", type=str, default=None, help="Bearer session token")
    parser.add_argument("--api-key", type=str, default=None, help="Agent API key")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-eval
    p_eval = subparsers.add_parser("create-eval", help="Create an eval_sweep job")
    p_eval.add_argument("--model", type=str, required=True)
    p_eval.add_argument("--budget", type=str, required=True, help="HBD budget (e.g. 1.000)")
    p_eval.add_argument("--limit", type=int, default=0)
    p_eval.add_argument("--category", type=str, default=None)

    # create-benchmark
    p_bench = subparsers.add_parser("create-benchmark", help="Create a benchmark_run job")
    p_bench.add_argument("--model", type=str, required=True)
    p_bench.add_argument("--budget", type=str, required=True)
    p_bench.add_argument("--limit", type=int, default=0)

    # monitor
    p_mon = subparsers.add_parser("monitor", help="Monitor a job until completion")
    p_mon.add_argument("--job-id", type=str, required=True)

    # verify
    p_ver = subparsers.add_parser("verify", help="Run hidden verification on a completed job")
    p_ver.add_argument("--job-id", type=str, required=True)

    # canary (full loop)
    p_canary = subparsers.add_parser("canary", help="Full canary loop: create → wait → verify → settle")
    p_canary.add_argument("--model", type=str, required=True)
    p_canary.add_argument("--budget", type=str, required=True)
    p_canary.add_argument("--limit", type=int, default=10, help="Challenges to run (default 10)")

    args = parser.parse_args()

    # Create client
    client = HivePoAComputeClient(
        base_url=args.hivepoa_url,
        auth_token=args.auth_token,
        api_key=args.api_key,
    )

    if args.command == "create-eval":
        job_id = create_eval_job(client, args.model, args.budget, args.limit, getattr(args, "category", None))
        print(f"Job ID: {job_id}")

    elif args.command == "create-benchmark":
        job_id = create_benchmark_job(client, args.model, args.budget, args.limit)
        print(f"Job ID: {job_id}")

    elif args.command == "monitor":
        result = monitor_job(client, args.job_id)
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "verify":
        result = verify_job(client, args.job_id)
        print(json.dumps(result, indent=2))

    elif args.command == "canary":
        run_canary(client, args.model, args.budget, args.limit)


if __name__ == "__main__":
    main()
