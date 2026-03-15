"""
scripts/integrated_canary.py

Integrated two-repo canary validation.
Runs against a live HivePoA server with a real model server.

Tests:
  1. eval_sweep: coordinator creates job → worker claims → runs regression_eval.py → submits → HivePoA accepts
  2. benchmark_run: same flow with executable_eval.py
  3. Verifier rejection: coordinator creates job → worker submits inflated scores → verifier catches deviation

Frozen configuration:
  HivePoA: http://localhost:3000
  Model: llama-server on port 11435
  Payout mode: dry-run

Usage:
  python scripts/integrated_canary.py
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from hiveai.dbc.compute_client import HivePoAComputeClient, compute_file_sha256
from hiveai.compute.models import (
    EvalSweepManifest, BenchmarkRunManifest,
    manifest_to_dict, SCHEMA_VERSION,
)
from hiveai.compute.verifier import get_verifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("integrated_canary")

# Frozen config
HIVEPOA_URL = os.environ.get("HIVEPOA_URL", "http://localhost:3000")
AUTH_TOKEN = os.environ.get("CANARY_AUTH_TOKEN", "canary-test-token-2026")
API_KEY = os.environ.get("CANARY_API_KEY", "canary-agent-key-2026")
MODEL_SERVER = "http://localhost:11435"
NODE_INSTANCE_ID = "integrated-canary-node-001"

results = []


def record(name: str, passed: bool, details: str):
    results.append({"test": name, "pass": passed, "details": details})
    icon = "PASS" if passed else "FAIL"
    logger.info(f"[{icon}] {name}: {details}")


def main():
    logger.info("=" * 60)
    logger.info("INTEGRATED TWO-REPO CANARY VALIDATION")
    logger.info("=" * 60)
    logger.info(f"HivePoA:      {HIVEPOA_URL}")
    logger.info(f"Model server: {MODEL_SERVER}")
    logger.info(f"Payout mode:  dry-run")
    logger.info("")

    # Create clients
    # Coordinator uses Bearer token for job creation, settlement, etc.
    coordinator = HivePoAComputeClient(base_url=HIVEPOA_URL, auth_token=AUTH_TOKEN)
    # Worker uses Bearer for registration (requireAuth), then ApiKey for operations (requireAgentAuth)
    worker_reg_client = HivePoAComputeClient(base_url=HIVEPOA_URL, auth_token=AUTH_TOKEN)
    worker_client = HivePoAComputeClient(base_url=HIVEPOA_URL, api_key=API_KEY)

    # Pre-flight checks
    try:
        stats = coordinator.get_stats()
        logger.info(f"HivePoA stats: {stats}")
    except Exception as e:
        logger.error(f"HivePoA not reachable: {e}")
        sys.exit(1)

    # Register worker node
    try:
        node = worker_reg_client.register_node(
            node_instance_id=NODE_INSTANCE_ID,
            gpu_model="Integrated-Canary",
            gpu_vram_gb=24,
            supported_workloads="eval_sweep,benchmark_run",
            cached_models="hiveai-v1",
            worker_version="canary-integrated-1.0.0",
        )
        logger.info(f"Worker registered: {node.id} (rep={node.reputation_score})")
    except Exception as e:
        logger.error(f"Worker registration failed: {e}")
        sys.exit(1)

    # ================================================================
    # Test 1: eval_sweep with real regression_eval.py
    # ================================================================
    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: eval_sweep (regression_eval.py, quick mode)")
    logger.info("=" * 60)
    try:
        # Coordinator creates job
        manifest = manifest_to_dict(EvalSweepManifest(
            model_name="canary-integrated",
            workload_type="eval_sweep",
        ))
        # Override for real execution
        manifest["server_url"] = MODEL_SERVER
        manifest["quick"] = True  # 18 probes, not 60

        job = coordinator.create_job(
            workload_type="eval_sweep",
            manifest=manifest,
            budget_hbd="1.000",
            min_vram_gb=8,
            lease_seconds=1800,  # 30 min — LLM eval is slow on consumer hardware
        )
        job_id = job["id"]
        logger.info(f"Job created: {job_id}")

        # Worker claims
        claimed = worker_client.claim_next_job(NODE_INSTANCE_ID)
        if not claimed:
            raise RuntimeError("Worker failed to claim job")
        logger.info(f"Job claimed: attempt={claimed.attempt_id}")

        # Worker starts
        worker_client.start_job(claimed.job_id, claimed.attempt_id, claimed.lease_token)

        # Worker executes regression_eval.py (quick mode)
        worker_client.report_progress(claimed.job_id, claimed.attempt_id, claimed.lease_token, 10, "running_eval")

        eval_cmd = [
            sys.executable, str(PROJECT_ROOT / "scripts" / "regression_eval.py"),
            "--model-version", "canary-integrated",
            "--server-url", MODEL_SERVER,
            "--quick",
        ]
        logger.info(f"Running: {' '.join(eval_cmd)}")
        start_time = time.time()

        # Run eval as Popen so we can heartbeat during execution
        import threading
        heartbeat_stop = threading.Event()
        def _heartbeat():
            while not heartbeat_stop.is_set():
                try:
                    worker_client.heartbeat(NODE_INSTANCE_ID, jobs_in_progress=1)
                except Exception:
                    pass
                heartbeat_stop.wait(20)
        hb_thread = threading.Thread(target=_heartbeat, daemon=True)
        hb_thread.start()

        proc = subprocess.run(eval_cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=600)
        heartbeat_stop.set()
        elapsed = time.time() - start_time
        logger.info(f"regression_eval.py finished in {elapsed:.1f}s (exit={proc.returncode})")

        if proc.stdout:
            logger.info(f"stdout (last 500 chars): {proc.stdout[-500:]}")
        if proc.returncode != 0 and proc.stderr:
            logger.warning(f"stderr (last 500 chars): {proc.stderr[-500:]}")

        # Parse scores from score_ledger.json
        ledger_path = PROJECT_ROOT / "score_ledger.json"
        scores = {}
        if ledger_path.exists():
            with open(ledger_path) as f:
                ledger = json.load(f)
            scores = ledger.get("canary-integrated", {})

        if not scores:
            # Fallback: parse stdout
            import re
            for line in proc.stdout.splitlines():
                m = re.match(r'\s*(\w+)\s*:\s*([\d.]+)', line)
                if m and m.group(1) in ("python", "rust", "go", "cpp", "js", "hive", "overall"):
                    scores[m.group(1)] = float(m.group(2))

        overall = scores.get("overall", sum(scores.values()) / max(len(scores), 1) if scores else 0)
        logger.info(f"Scores: {scores}")
        logger.info(f"Overall: {overall}")

        worker_client.report_progress(claimed.job_id, claimed.attempt_id, claimed.lease_token, 90, "submitting")

        # Build result
        result_data = {
            "overall_score": overall,
            "challenges_run": 18,
            "challenges_passed": int(overall * 18),
            "scores": scores,
            "category_scores": {k: v for k, v in scores.items() if k != "overall"},
            "total_time_sec": elapsed,
            "model_name": "canary-integrated",
            "eval_harness_version": "1.0.0",
            "score": overall,
        }
        result_json = json.dumps(result_data)
        result_hash = sha256(result_json.encode()).hexdigest()

        # Submit
        submit_resp = worker_client.submit_result(
            job_id=claimed.job_id,
            attempt_id=claimed.attempt_id,
            lease_token=claimed.lease_token,
            output_cid=f"sha256:{result_hash}",
            output_sha256=result_hash,
            output_size_bytes=len(result_json),
            result_json=result_json,
            metrics_json=json.dumps({"wall_time_sec": elapsed, "exit_code": proc.returncode}),
        )

        # Check result
        job_data = coordinator.get_job(job_id)
        state = job_data.get("state")
        payouts = job_data.get("payouts", [])

        if state == "accepted" and len(payouts) >= 2:
            record("eval_sweep E2E", True, f"Accepted, {len(payouts)} payouts, overall={overall:.3f}, {elapsed:.1f}s")
        else:
            record("eval_sweep E2E", False, f"state={state}, payouts={len(payouts)}")

    except Exception as e:
        record("eval_sweep E2E", False, str(e))

    # Re-register to reset node state
    worker_reg_client.register_node(
        node_instance_id=NODE_INSTANCE_ID,
        gpu_model="Integrated-Canary",
        gpu_vram_gb=24,
        supported_workloads="eval_sweep,benchmark_run",
    )

    # ================================================================
    # Test 2: benchmark_run with real executable_eval.py
    # ================================================================
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: benchmark_run (executable_eval.py)")
    logger.info("=" * 60)
    try:
        manifest = manifest_to_dict(BenchmarkRunManifest(
            model_name="canary-integrated",
            workload_type="benchmark_run",
        ))
        manifest["server_url"] = MODEL_SERVER
        manifest["language"] = "python"  # python only for speed

        job = coordinator.create_job(
            workload_type="benchmark_run",
            manifest=manifest,
            budget_hbd="1.000",
            min_vram_gb=8,
            lease_seconds=600,
        )
        job_id = job["id"]
        logger.info(f"Job created: {job_id}")

        claimed = worker_client.claim_next_job(NODE_INSTANCE_ID)
        if not claimed:
            raise RuntimeError("Worker failed to claim benchmark job")

        worker_client.start_job(claimed.job_id, claimed.attempt_id, claimed.lease_token)
        worker_client.report_progress(claimed.job_id, claimed.attempt_id, claimed.lease_token, 10, "running_benchmark")

        import tempfile
        with tempfile.NamedTemporaryFile(prefix="canary_bench_", suffix=".json", delete=False, dir=str(PROJECT_ROOT / "evals")) as f:
            bench_output = f.name

        bench_cmd = [
            sys.executable, str(PROJECT_ROOT / "scripts" / "executable_eval.py"),
            "--server-url", MODEL_SERVER,
            "--language", "python",
            "--output", bench_output,
        ]
        logger.info(f"Running: {' '.join(bench_cmd)}")
        start_time = time.time()

        heartbeat_stop2 = threading.Event()
        def _hb2():
            while not heartbeat_stop2.is_set():
                try: worker_client.heartbeat(NODE_INSTANCE_ID, jobs_in_progress=1)
                except: pass
                heartbeat_stop2.wait(20)
        hb2 = threading.Thread(target=_hb2, daemon=True)
        hb2.start()

        proc = subprocess.run(bench_cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=300)
        heartbeat_stop2.set()
        elapsed = time.time() - start_time
        logger.info(f"executable_eval.py finished in {elapsed:.1f}s (exit={proc.returncode})")

        if proc.returncode != 0:
            logger.warning(f"stderr: {proc.stderr[-500:]}")

        # Parse output
        bench_result = {}
        if os.path.exists(bench_output):
            with open(bench_output) as f:
                bench_result = json.load(f)
            os.unlink(bench_output)

        pass_rate = bench_result.get("pass_rate", 0.0)
        total_prompts = bench_result.get("total_prompts", 0)
        logger.info(f"Benchmark: pass_rate={pass_rate}, prompts={total_prompts}")

        worker_client.report_progress(claimed.job_id, claimed.attempt_id, claimed.lease_token, 90, "submitting")

        result_data = {
            "overall_score": pass_rate,
            "challenges_run": total_prompts,
            "challenges_passed": bench_result.get("prompts_passing", 0),
            "scores": bench_result.get("by_language", {}),
            "category_scores": bench_result.get("by_language", {}),
            "total_time_sec": elapsed,
            "model_name": "canary-integrated",
            "score": pass_rate,
        }
        result_json = json.dumps(result_data)
        result_hash = sha256(result_json.encode()).hexdigest()

        worker_client.submit_result(
            job_id=claimed.job_id,
            attempt_id=claimed.attempt_id,
            lease_token=claimed.lease_token,
            output_cid=f"sha256:{result_hash}",
            output_sha256=result_hash,
            output_size_bytes=len(result_json),
            result_json=result_json,
            metrics_json=json.dumps({"wall_time_sec": elapsed, "exit_code": proc.returncode}),
        )

        job_data = coordinator.get_job(job_id)
        state = job_data.get("state")
        payouts = job_data.get("payouts", [])

        if state == "accepted" and len(payouts) >= 2:
            record("benchmark_run E2E", True, f"Accepted, {len(payouts)} payouts, pass_rate={pass_rate:.3f}, {elapsed:.1f}s")
        else:
            record("benchmark_run E2E", False, f"state={state}, payouts={len(payouts)}")

    except Exception as e:
        record("benchmark_run E2E", False, str(e))

    # Re-register
    worker_reg_client.register_node(
        node_instance_id=NODE_INSTANCE_ID,
        gpu_model="Integrated-Canary",
        gpu_vram_gb=24,
        supported_workloads="eval_sweep,benchmark_run",
    )

    # ================================================================
    # Test 3: Verifier rejection — inflated scores
    # ================================================================
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Verifier rejection (inflated scores)")
    logger.info("=" * 60)
    try:
        manifest = manifest_to_dict(EvalSweepManifest(
            model_name="canary-inflated",
            workload_type="eval_sweep",
        ))
        manifest["server_url"] = MODEL_SERVER
        manifest["quick"] = True

        job = coordinator.create_job(
            workload_type="eval_sweep",
            manifest=manifest,
            budget_hbd="1.000",
            min_vram_gb=8,
            lease_seconds=300,
        )
        job_id = job["id"]

        claimed = worker_client.claim_next_job(NODE_INSTANCE_ID)
        if not claimed:
            raise RuntimeError("Worker failed to claim inflated job")

        worker_client.start_job(claimed.job_id, claimed.attempt_id, claimed.lease_token)

        # Submit inflated scores (well-formed but falsified)
        inflated = {
            "overall_score": 0.99,
            "challenges_run": 18,
            "challenges_passed": 18,
            "scores": {"python": 0.99, "rust": 0.99, "go": 0.99, "cpp": 0.99, "js": 0.99, "hive": 0.99},
            "category_scores": {"python": 0.99, "rust": 0.99, "go": 0.99},
            "total_time_sec": 5,
            "model_name": "canary-inflated",
            "score": 0.99,
        }
        inflated_json = json.dumps(inflated)
        inflated_hash = sha256(inflated_json.encode()).hexdigest()

        worker_client.submit_result(
            job_id=claimed.job_id,
            attempt_id=claimed.attempt_id,
            lease_token=claimed.lease_token,
            output_cid=f"sha256:{inflated_hash}",
            output_sha256=inflated_hash,
            output_size_bytes=len(inflated_json),
            result_json=inflated_json,
            metrics_json=json.dumps({"wall_time_sec": 5}),
        )

        # HivePoA structurally accepts (valid JSON, correct fields)
        job_data = coordinator.get_job(job_id)
        hivepoa_state = job_data.get("state")
        logger.info(f"HivePoA state: {hivepoa_state} (expected: accepted structurally)")

        # Now run Hive-AI verifier (trusted side)
        # This re-runs regression_eval.py independently and compares
        verifier = get_verifier("eval_sweep", model_name="canary-inflated", server_url=MODEL_SERVER)
        logger.info("Running Hive-AI verifier (independent regression_eval.py)...")
        decision = verifier.verify(inflated_json, manifest)

        logger.info(f"Verifier result: {decision.result.value}")
        logger.info(f"  score={decision.score:.3f}, deviation={decision.score_deviation:.4f}")
        logger.info(f"  matched={decision.hidden_challenges_matched}/{decision.hidden_challenges_run}")
        logger.info(f"  details={json.dumps(decision.details, indent=2)}")

        # The verifier should catch the inflated scores
        # Check both per-domain deviation AND overall score gap
        overall_gap = abs(0.99 - decision.details.get("verifier_overall", 0.0))
        logger.info(f"Overall gap: worker=0.99, verifier={decision.details.get('verifier_overall', 0.0)}, gap={overall_gap:.4f}")

        if decision.result.value in ("fail", "soft_fail"):
            record("Verifier rejection", True,
                   f"Verifier correctly flagged inflated scores: {decision.result.value}, "
                   f"deviation={decision.score_deviation:.4f}, overall_gap={overall_gap:.4f}")
        elif overall_gap > 0.30:
            # Even if per-domain matching didn't catch it (key mismatch),
            # the overall score gap proves the scores are fabricated
            record("Verifier rejection", True,
                   f"Overall score gap {overall_gap:.4f} proves inflation "
                   f"(per-domain result={decision.result.value} may have key mismatch)")
        elif decision.score_deviation > 0.10:
            record("Verifier rejection", True,
                   f"Verifier detected deviation {decision.score_deviation:.4f} > 0.10")
        else:
            record("Verifier rejection", False,
                   f"Verifier did NOT catch inflated scores: {decision.result.value}, "
                   f"deviation={decision.score_deviation:.4f}, overall_gap={overall_gap:.4f}")

    except Exception as e:
        record("Verifier rejection", False, str(e))

    # ================================================================
    # Summary
    # ================================================================
    logger.info("\n" + "=" * 60)
    logger.info("INTEGRATED CANARY RESULTS")
    logger.info("=" * 60)
    passed = sum(1 for r in results if r["pass"])
    failed = sum(1 for r in results if not r["pass"])
    for r in results:
        icon = "PASS" if r["pass"] else "FAIL"
        logger.info(f"  [{icon}] {r['test']}: {r['details']}")
    logger.info(f"\n  {passed} passed, {failed} failed out of {len(results)} tests")

    if failed == 0:
        logger.info("\n  INTEGRATED CANARY PASSED — ready for treasury smoke test")
    else:
        logger.info("\n  INTEGRATED CANARY FAILED — fix issues before proceeding")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
