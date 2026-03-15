"""
Tests for compute canary loop: contracts, worker, verifier.

Run: python -m pytest tests/test_compute.py -v
"""
import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hiveai.compute.models import (
    WorkloadType, CANARY_WORKLOADS,
    EvalSweepManifest, BenchmarkRunManifest,
    EvalSweepResult, BenchmarkResult,
    ChallengeScore, WorkerMetrics,
    VerificationResult, VerificationDecision,
    manifest_to_dict, result_to_json,
)
from hiveai.compute.worker import GPUWorker, generate_instance_id
from hiveai.compute.verifier import EvalSweepVerifier, BenchmarkRunVerifier, get_verifier


# ================================================================
# Contract / Model Tests
# ================================================================

class TestContracts:
    def test_canary_workloads_only_eval_and_benchmark(self):
        assert WorkloadType.EVAL_SWEEP in CANARY_WORKLOADS
        assert WorkloadType.BENCHMARK_RUN in CANARY_WORKLOADS
        assert len(CANARY_WORKLOADS) == 2

    def test_eval_sweep_manifest_roundtrip(self):
        m = EvalSweepManifest(
            model_name="v5-think",
            challenge_ids=["py-1", "py-2"],
            temperature=0.0,
            max_tokens=2048,
        )
        d = manifest_to_dict(m)
        assert d["model_name"] == "v5-think"
        assert d["challenge_ids"] == ["py-1", "py-2"]
        assert isinstance(json.dumps(d), str)

    def test_benchmark_manifest_roundtrip(self):
        m = BenchmarkRunManifest(
            model_name="gpt-oss-20b",
            challenge_ids=[],
            temperature=0.1,
            max_tokens=4096,
        )
        d = manifest_to_dict(m)
        assert d["model_name"] == "gpt-oss-20b"

    def test_eval_result_serialization(self):
        r = EvalSweepResult(
            overall_score=0.945,
            challenges_run=60,
            challenges_passed=57,
            per_challenge=[],
            category_scores={"python": 0.93, "rust": 0.96},
        )
        j = result_to_json(r)
        parsed = json.loads(j)
        assert parsed["overall_score"] == 0.945
        assert parsed["challenges_run"] == 60

    def test_verification_decision_states(self):
        assert VerificationResult.PASS.value == "pass"
        assert VerificationResult.FAIL.value == "fail"
        assert VerificationResult.SOFT_FAIL.value == "soft_fail"

    def test_challenge_score_fields(self):
        cs = ChallengeScore(
            challenge_id="py-fibonacci",
            score=0.95,
            code_validity=1.0,
            test_passing=0.9,
            concept_coverage=1.0,
        )
        assert cs.score == 0.95
        assert cs.code_validity == 1.0

    def test_worker_metrics_untrusted(self):
        wm = WorkerMetrics(
            gpu_utilization_pct=85.0,
            gpu_memory_used_mb=14000,
            wall_time_sec=120.5,
        )
        assert wm.gpu_utilization_pct == 85.0


# ================================================================
# Worker Tests (Mocked HivePoA)
# ================================================================

class MockClaimedJob:
    def __init__(self, workload_type="eval_sweep", manifest=None):
        self.job_id = "test-job-1"
        self.attempt_id = "test-att-1"
        self.lease_token = "test-tok-1"
        self.workload_type = workload_type
        self.manifest = manifest or {
            "model_name": "v5-think",
            "server_url": "http://localhost:11435",
            "quick": True,
            "threshold": 0.03,
        }
        self.manifest_sha256 = "abc123"
        self.budget_hbd = "0.010"
        self.lease_seconds = 1800


class TestWorker:
    def _make_mock_client(self, job=None):
        client = MagicMock()
        client.register_node.return_value = MagicMock(id="node-1", reputation_score=50)
        client.claim_next_job.return_value = job
        client.start_job.return_value = None
        client.report_progress.return_value = None
        client.submit_result.return_value = {"status": "submitted"}
        client.fail_job.return_value = None
        client.heartbeat.return_value = None
        client.drain_node.return_value = None
        return client

    def test_worker_no_jobs_sleeps(self):
        client = self._make_mock_client(job=None)
        worker = GPUWorker(client, "test-node", poll_interval=1)
        worker._poll_and_execute()
        client.claim_next_job.assert_called_once()

    def test_worker_rejects_unsupported_workload(self):
        job = MockClaimedJob(workload_type="domain_lora_train")
        client = self._make_mock_client(job=job)
        worker = GPUWorker(client, "test-node")
        worker._poll_and_execute()
        # Should have called fail_job because workload is unsupported
        client.fail_job.assert_called_once()
        args = client.fail_job.call_args
        assert "Unsupported workload" in args.kwargs.get("reason", args[1] if len(args) > 1 else "")

    @patch("hiveai.compute.worker.subprocess.run")
    def test_worker_eval_sweep_happy_path(self, mock_run):
        """Worker executes eval_sweep and submits result."""
        # Mock subprocess to simulate regression_eval.py completing
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="python: 0.93\nrust: 0.95\ngo: 0.96\ncpp: 0.92\njs: 0.95\nhive: 0.98\noverall: 0.948\n",
            stderr="",
        )

        # Create a mock score_ledger.json
        ledger_path = Path(__file__).resolve().parent.parent / "score_ledger.json"
        ledger_existed = ledger_path.exists()
        if not ledger_existed:
            ledger_path.write_text(json.dumps({"v5-think": {"python": 0.93, "overall": 0.948}}))

        try:
            job = MockClaimedJob(workload_type="eval_sweep")
            client = self._make_mock_client(job=job)
            worker = GPUWorker(client, "test-node")
            worker._poll_and_execute()

            # Should have submitted
            client.submit_result.assert_called_once()
            call_kwargs = client.submit_result.call_args.kwargs
            result_json = json.loads(call_kwargs["result_json"])
            assert result_json["model_name"] == "v5-think"
            assert "overall_score" in result_json
        finally:
            if not ledger_existed and ledger_path.exists():
                ledger_path.unlink()

    def test_generate_instance_id_stable(self, tmp_path):
        """Instance ID should persist across calls."""
        id_file = tmp_path / ".gpu_worker_id"
        with patch("hiveai.compute.worker.PROJECT_ROOT", tmp_path):
            id1 = generate_instance_id()
            id2 = generate_instance_id()
            assert id1 == id2
            assert id1.startswith("gpu-")


# ================================================================
# Verifier Tests
# ================================================================

class TestVerifier:
    def test_get_verifier_eval(self):
        v = get_verifier("eval_sweep", "v5-think", "http://localhost:11435")
        assert isinstance(v, EvalSweepVerifier)

    def test_get_verifier_benchmark(self):
        v = get_verifier("benchmark_run", "v5-think", "http://localhost:11435")
        assert isinstance(v, BenchmarkRunVerifier)

    def test_verifier_rejects_empty_result(self):
        v = EvalSweepVerifier("v5-think", "http://localhost:11435")
        decision = v.verify("{}")
        assert decision.result == VerificationResult.FAIL

    def test_verifier_rejects_malformed_json(self):
        v = EvalSweepVerifier("v5-think", "http://localhost:11435")
        decision = v.verify("not json at all")
        assert decision.result == VerificationResult.FAIL

    def test_verifier_rejects_zero_challenges(self):
        v = EvalSweepVerifier("v5-think", "http://localhost:11435")
        result = json.dumps({
            "overall_score": 0.95,
            "challenges_run": 0,
            "challenges_passed": 0,
            "scores": {},
        })
        decision = v.verify(result)
        assert decision.result == VerificationResult.FAIL

    def test_verifier_structural_validation(self):
        """Verifier should catch missing required fields."""
        v = EvalSweepVerifier("v5-think", "http://localhost:11435")
        # Missing overall_score
        result = json.dumps({
            "challenges_run": 60,
            "challenges_passed": 55,
            "scores": {"python": 0.93},
        })
        decision = v.verify(result)
        assert decision.result == VerificationResult.FAIL


# ================================================================
# Compute Client Contract Tests
# ================================================================

class TestComputeClientContract:
    """Tests that compute_client.py field names match HivePoA API contract."""

    def test_register_payload_uses_camel_case(self):
        """HivePoA expects camelCase field names."""
        from hiveai.dbc.compute_client import HivePoAComputeClient

        client = HivePoAComputeClient("http://fake:3000", api_key="test")

        # Intercept the request
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(
                ok=True,
                json=lambda: {
                    "id": "1", "nodeInstanceId": "n", "hiveUsername": "u",
                    "status": "online", "gpuModel": "RTX", "gpuVramGb": 16,
                },
            )
            client.register_node(
                node_instance_id="test-node",
                gpu_model="RTX 4070",
                gpu_vram_gb=16,
                supported_workloads="eval_sweep",
            )
            call_kwargs = mock_post.call_args
            payload = call_kwargs.kwargs.get("json", call_kwargs[1].get("json", {}))
            # Verify camelCase
            assert "nodeInstanceId" in payload
            assert "gpuModel" in payload
            assert "gpuVramGb" in payload
            assert "supportedWorkloads" in payload

    def test_submit_result_sha256_field(self):
        """outputSha256 must be exactly 64 hex chars per contract."""
        from hiveai.dbc.compute_client import HivePoAComputeClient

        client = HivePoAComputeClient("http://fake:3000", api_key="test")
        sha = "a" * 64

        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(ok=True, json=lambda: {"status": "submitted"})
            client.submit_result(
                job_id="j1", attempt_id="a1", lease_token="t1",
                output_cid=f"sha256:{sha}", output_sha256=sha,
                result_json='{"test": true}',
            )
            call_kwargs = mock_post.call_args
            payload = call_kwargs.kwargs.get("json", call_kwargs[1].get("json", {}))
            assert payload["outputSha256"] == sha
            assert len(payload["outputSha256"]) == 64


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
