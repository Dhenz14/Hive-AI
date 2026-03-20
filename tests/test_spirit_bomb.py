"""
tests/test_spirit_bomb.py

Tests for Spirit Bomb community cloud components:
  - TierAutoscaler: tier transitions, hysteresis, EMA smoothing
  - ClusterManager: cluster formation, placement scoring
  - ElasticMoEManager: expert activation, routing, placement plans
  - IncentiveCalculator: reward calculations
  - HelixPlacementOptimizer: layer placement, throughput estimation
  - EagleSpeculativeEngine: speculative decoding stats
"""

import time
import pytest

from hiveai.compute.tier_autoscaler import (
    TierAutoscaler,
    Tier,
    UPGRADE_THRESHOLDS,
    DOWNGRADE_THRESHOLDS,
    MIN_TRANSITION_INTERVAL_SECONDS,
)
from hiveai.compute.cluster_manager import (
    ClusterManager,
    ClusterNode,
    PeerLatency,
    GpuClusterState,
)
from hiveai.compute.elastic_moe import (
    ElasticMoEManager,
    ExpertReplica,
)
from hiveai.compute.incentives import (
    IncentiveCalculator,
    ContributionPeriod,
    TIER_MULTIPLIERS,
    MAX_PAYOUT_PER_PERIOD_HBD,
)
from hiveai.compute.helix_placement import (
    HelixPlacementOptimizer,
    GpuSpec,
    GPU_SPECS_DB,
)
from hiveai.compute.speculative_decoding import (
    EagleSpeculativeEngine,
    SpeculativeConfig,
    select_draft_model,
)
from datetime import datetime, timezone


# ── TierAutoscaler Tests ────────────────────────────────────────

class TestTierAutoscaler:
    def test_initial_tier_is_solo(self):
        scaler = TierAutoscaler()
        assert scaler.state.current_tier == Tier.SOLO

    def test_upgrade_to_pool(self):
        scaler = TierAutoscaler()
        # Need to bypass min interval
        scaler.state.last_transition_time = time.time() - MIN_TRANSITION_INTERVAL_SECONDS - 1
        result = scaler.evaluate(5)  # 2+ GPUs = Pool
        assert result == Tier.POOL

    def test_upgrade_to_cluster(self):
        scaler = TierAutoscaler()
        scaler.state.last_transition_time = time.time() - MIN_TRANSITION_INTERVAL_SECONDS - 1
        scaler.evaluate(5)  # → Pool
        scaler.state.last_transition_time = time.time() - MIN_TRANSITION_INTERVAL_SECONDS - 1
        scaler.state.smoothed_gpu_count = 5.0
        # Pool → Cluster requires cluster_qualified=True
        result = scaler.evaluate(5, cluster_qualified=True)
        assert result == Tier.CLUSTER

    def test_hysteresis_prevents_flapping(self):
        scaler = TierAutoscaler()
        scaler.state.last_transition_time = time.time() - MIN_TRANSITION_INTERVAL_SECONDS - 1
        scaler.evaluate(5)  # → Pool
        assert scaler.state.current_tier == Tier.POOL

        # 1.5 GPUs (smoothed) is above downgrade threshold (1) — stays Pool
        scaler.state.last_transition_time = time.time() - MIN_TRANSITION_INTERVAL_SECONDS - 1
        scaler.state.smoothed_gpu_count = 1.5
        result = scaler.evaluate(2)
        assert result == Tier.POOL  # stays at Pool (smoothed > 1)

    def test_downgrade_below_hysteresis(self):
        scaler = TierAutoscaler()
        scaler.state.last_transition_time = time.time() - MIN_TRANSITION_INTERVAL_SECONDS - 1
        scaler.evaluate(5)  # → Pool
        scaler.state.last_transition_time = time.time() - MIN_TRANSITION_INTERVAL_SECONDS - 1
        scaler.state.smoothed_gpu_count = 0.8  # below 1 = downgrade
        # Downgrade is deferred (drain period)
        result = scaler.evaluate(0)
        assert result == Tier.POOL  # still Pool during drain
        assert scaler.state.pending_transition is not None

    def test_min_interval_respected(self):
        scaler = TierAutoscaler()
        scaler.state.last_transition_time = time.time()  # just transitioned
        result = scaler.evaluate(50)
        assert result == Tier.SOLO  # no transition due to min interval

    def test_force_tier(self):
        scaler = TierAutoscaler()
        scaler.force_tier(3, "admin override")
        assert scaler.state.current_tier == Tier.CLUSTER

    def test_callback_fired(self):
        scaler = TierAutoscaler()
        called = []
        scaler.on_tier_change(lambda old, new, gpus: called.append((old, new, gpus)))
        scaler.state.last_transition_time = time.time() - MIN_TRANSITION_INTERVAL_SECONDS - 1
        scaler.evaluate(20)
        assert len(called) == 1
        assert called[0] == (1, 2, 20)

    def test_status_report(self):
        scaler = TierAutoscaler()
        status = scaler.get_status()
        assert status["current_tier"] == 1
        assert "thresholds" in status


# ── ClusterManager Tests ────────────────────────────────────────

class TestClusterManager:
    def test_form_clusters_by_region(self):
        mgr = ClusterManager()
        nodes = [
            ClusterNode("n1", "RTX 4090", 24, region="us-east"),
            ClusterNode("n2", "RTX 4080", 16, region="us-east"),
            ClusterNode("n3", "RTX 3060", 12, region="eu-west"),
        ]
        clusters = mgr.form_clusters(nodes)
        assert len(clusters) >= 2  # at least 2 regions

    def test_cluster_vram_calculation(self):
        mgr = ClusterManager()
        nodes = [
            ClusterNode("n1", "RTX 4090", 24, region="us-east"),
            ClusterNode("n2", "RTX 4080", 16, region="us-east"),
        ]
        clusters = mgr.form_clusters(nodes)
        us_clusters = [c for c in clusters if c.region == "us-east"]
        assert us_clusters[0].total_vram_gb == 40

    def test_select_best_cluster(self):
        mgr = ClusterManager()
        nodes = [
            ClusterNode("n1", "RTX 4090", 24, region="us-east"),
            ClusterNode("n2", "RTX 4090", 24, region="us-east"),
            ClusterNode("n3", "RTX 3060", 12, region="eu-west"),
        ]
        mgr.form_clusters(nodes)
        best = mgr.select_best_cluster(14.0)
        assert best is not None
        assert best.total_vram_gb >= 24

    def test_optimal_parallelism_small_model(self):
        mgr = ClusterManager()
        state = GpuClusterState(
            cluster_id="test",
            region="us-east",
            nodes=[
                ClusterNode("n1", "RTX 4090", 24),
                ClusterNode("n2", "RTX 4090", 24),
            ],
        )
        result = mgr.get_optimal_parallelism(state, 7.0)  # 7B fits on single 24GB GPU
        assert result["strategy"] == "expert_parallel"  # fits on single GPU

    def test_optimal_parallelism_large_model(self):
        mgr = ClusterManager()
        state = GpuClusterState(
            cluster_id="test",
            region="us-east",
            nodes=[
                ClusterNode("n1", "RTX 4070", 12),
                ClusterNode("n2", "RTX 4070", 12),
                ClusterNode("n3", "RTX 4070", 12),
            ],
        )
        state.latency_matrix[("n1", "n2")] = PeerLatency("n1", "n2", 20.0, measured_at=time.time())
        result = mgr.get_optimal_parallelism(state, 32.0)
        assert result["strategy"] in ("pipeline_parallel", "tensor_parallel")


# ── ElasticMoE Tests ────────────────────────────────────────────

class TestElasticMoE:
    def test_initial_tier_base(self):
        moe = ElasticMoEManager("Qwen3-Coder-80B-MoE")
        config = moe.set_tier(1)
        assert config["num_active_experts"] == 2
        assert config["tier_name"] == "BASE"

    def test_scale_up_experts(self):
        moe = ElasticMoEManager("Qwen3-Coder-80B-MoE")
        moe.set_tier(1)
        config = moe.set_tier(3)
        assert config["num_active_experts"] == 8
        assert config["tier_changed"]

    def test_scale_down_experts(self):
        moe = ElasticMoEManager("Qwen3-Coder-80B-MoE")
        moe.set_tier(3)  # 8 experts
        config = moe.set_tier(1)  # back to 2
        assert config["num_active_experts"] == 2

    def test_register_expert_replica(self):
        moe = ElasticMoEManager("Qwen3-Coder-80B-MoE")
        moe.set_tier(1)
        replica = moe.register_expert_replica(0, "node-1", "RTX 4090", 24)
        assert replica.expert_id == 0
        assert replica.status == "ready"

    def test_expert_distribution(self):
        moe = ElasticMoEManager("Qwen3-Coder-80B-MoE")
        moe.set_tier(1)
        moe.register_expert_replica(0, "node-1", "RTX 4090", 24)
        dist = moe.get_expert_distribution()
        assert dist["active_experts"] == 2
        assert dist["total_replicas"] >= 1

    def test_vllm_config_generation(self):
        moe = ElasticMoEManager("Qwen3-Coder-80B-MoE")
        moe.set_tier(2)
        config = moe.generate_vllm_config([{"vram_gb": 16}, {"vram_gb": 16}])
        assert "tensor_parallel_size" in config
        assert "max_model_len" in config


# ── Incentive Calculator Tests ──────────────────────────────────

class TestIncentives:
    def test_basic_inference_reward(self):
        calc = IncentiveCalculator(current_tier=1)
        contrib = ContributionPeriod(
            node_id="test-node",
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            tokens_generated=10000,
            requests_served=50,
            tier=1,
        )
        result = calc.calculate_reward(contrib)
        assert result.total_hbd > 0
        assert result.inference_reward_hbd > 0

    def test_tier_multiplier(self):
        calc = IncentiveCalculator()
        base_contrib = ContributionPeriod(
            node_id="test",
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            tokens_generated=10000,
            tier=1,
        )
        tier3_contrib = ContributionPeriod(
            node_id="test",
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            tokens_generated=10000,
            tier=3,
        )
        r1 = calc.calculate_reward(base_contrib)
        r3 = calc.calculate_reward(tier3_contrib)
        assert r3.total_hbd == r1.total_hbd * 2.0  # Tier 3 = 2x

    def test_payout_cap(self):
        calc = IncentiveCalculator()
        contrib = ContributionPeriod(
            node_id="test",
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            tokens_generated=100_000_000,  # massive
            tier=3,
        )
        result = calc.calculate_reward(contrib)
        assert result.total_hbd <= MAX_PAYOUT_PER_PERIOD_HBD
        assert result.capped

    def test_earnings_estimate(self):
        calc = IncentiveCalculator()
        estimate = calc.estimate_earnings(gpu_vram_gb=16, hours_per_day=8, tier=2)
        assert estimate["estimated_monthly_hbd"] > 0
        assert estimate["tier_multiplier"] == 1.5


# ── Helix Placement Tests ──────────────────────────────────────

class TestHelixPlacement:
    def test_add_gpu_from_db(self):
        opt = HelixPlacementOptimizer()
        opt.add_gpus_from_db([
            {"node_id": "n1", "gpu_model": "RTX 4090", "vram_gb": 24},
            {"node_id": "n2", "gpu_model": "RTX 4070 Ti SUPER", "vram_gb": 16},
        ])
        assert len(opt._gpu_profiles) == 2

    def test_placement_single_gpu(self):
        opt = HelixPlacementOptimizer()
        opt.add_gpu(GpuSpec("n1", "RTX 4090", 24, 165, 1008))
        plan = opt.optimize_placement("Qwen3-14B", "awq")
        assert plan is not None
        assert plan.pipeline_stages == 1

    def test_placement_multi_gpu(self):
        opt = HelixPlacementOptimizer()
        opt.add_gpu(GpuSpec("n1", "RTX 4090", 24, 165, 1008))
        opt.add_gpu(GpuSpec("n2", "RTX 4070", 12, 59, 504))
        plan = opt.optimize_placement("Qwen3-32B", "fp16")
        if plan:
            assert plan.pipeline_stages >= 1
            assert plan.estimated_throughput_tps > 0

    def test_helix_vs_naive_speedup(self):
        opt = HelixPlacementOptimizer()
        opt.add_gpu(GpuSpec("n1", "RTX 4090", 24, 165, 1008))
        opt.add_gpu(GpuSpec("n2", "RTX 3060", 12, 25, 360))
        result = opt.compare_placements("Qwen3-14B", "awq")
        if "speedup" in result:
            assert result["speedup"] >= 1.0  # Helix should be at least as good


# ── Speculative Decoding Tests ──────────────────────────────────

class TestSpeculativeDecoding:
    def test_initial_stats(self):
        engine = EagleSpeculativeEngine()
        stats = engine.get_stats()
        assert stats["total_tokens"] == 0
        assert stats["speedup"] == 1.0

    def test_record_step_updates_stats(self):
        engine = EagleSpeculativeEngine()
        engine.record_step(draft_tokens=5, accepted_tokens=4, draft_time_ms=2, verify_time_ms=20)
        stats = engine.get_stats()
        assert stats["total_tokens"] == 5  # 4 accepted + 1 verify
        assert stats["acceptance_rate"] == 0.8

    def test_adaptive_draft_length(self):
        engine = EagleSpeculativeEngine(SpeculativeConfig(num_speculative_tokens=5))
        # High acceptance → should increase draft length
        for _ in range(20):
            engine.record_step(5, 5, 2, 20)
        assert engine._adaptive_draft_length >= 5

    def test_speedup_estimation(self):
        engine = EagleSpeculativeEngine()
        estimate = engine.estimate_speedup(target_model_tps=40.0, acceptance_rate=0.75)
        assert estimate["estimated_speedup"] > 1.0
        assert estimate["effective_tps"] > 40.0

    def test_draft_model_selection(self):
        result = select_draft_model("Qwen3-32B", gpu_vram_gb=16)
        assert "draft_model" in result
        assert result["expected_acceptance_rate"] > 0

    def test_vllm_config_generation(self):
        engine = EagleSpeculativeEngine(SpeculativeConfig(draft_model_name="Qwen3-0.6B"))
        config = engine.get_vllm_speculative_config()
        assert config["speculative_model"] == "Qwen3-0.6B"
        assert config["num_speculative_tokens"] > 0


# ── KV-Cache Router Tests ──────────────────────────────────────

from hiveai.compute.kv_cache_router import KVCacheIndex, KVCacheAwareRouter

class TestKVCacheRouter:
    def test_register_and_lookup(self):
        index = KVCacheIndex()
        prefix_hash = index.register_cache("node-1", "Hello world how are you", 5)
        assert prefix_hash
        results = index.lookup("Hello world how are you", min_tokens=1)
        assert len(results) >= 1
        assert results[0].node_id == "node-1"

    def test_cache_miss(self):
        index = KVCacheIndex()
        results = index.lookup("Completely new prompt", min_tokens=1)
        assert len(results) == 0

    def test_evict_node(self):
        index = KVCacheIndex()
        index.register_cache("node-1", "Some prompt", 10)
        removed = index.evict_node("node-1")
        assert removed >= 1
        results = index.lookup("Some prompt", min_tokens=1)
        assert len(results) == 0

    def test_router_cache_hit(self):
        router = KVCacheAwareRouter()
        router.update_node_load("node-1", 0.3)
        router.update_node_load("node-2", 0.1)
        # Register a cache entry — the prompt needs 3+ words for the lookup to match
        prompt = "Hello world how are you doing today in this fine weather"
        router.register_completion("node-1", prompt, len(prompt.split()))

        decision = router.route(prompt, ["node-1", "node-2"])
        assert decision.node_id == "node-1"
        assert decision.reason == "cache_hit"

    def test_router_load_balance(self):
        router = KVCacheAwareRouter()
        router.update_node_load("node-1", 0.9)
        router.update_node_load("node-2", 0.1)

        decision = router.route("New prompt no cache", ["node-1", "node-2"])
        assert decision.node_id == "node-2"
        assert decision.reason == "load_balance"

    def test_router_overloaded_cache_node(self):
        router = KVCacheAwareRouter()
        router.update_node_load("node-1", 0.95)  # overloaded
        router.update_node_load("node-2", 0.2)
        router.register_completion("node-1", "Cached prompt", 20)

        # Should skip overloaded node-1 despite cache hit
        decision = router.route("Cached prompt", ["node-1", "node-2"])
        assert decision.node_id == "node-2"
        assert decision.reason == "load_balance"

    def test_cache_stats(self):
        index = KVCacheIndex()
        index.register_cache("node-1", "Prompt A", 10)
        index.register_cache("node-2", "Prompt B", 20)
        stats = index.get_stats()
        assert stats["total_entries"] == 2
        assert stats["nodes_with_cache"] == 2


# ── Latency Prober Tests ──────────────────────────────────────

from hiveai.compute.latency_prober import LatencyProber, ProbeResult

class TestLatencyProber:
    def test_add_peer(self):
        prober = LatencyProber("my-node")
        prober.add_peer("peer-1", "http://10.0.0.2:8100")
        assert "peer-1" in prober._peers

    def test_remove_peer(self):
        prober = LatencyProber("my-node")
        prober.add_peer("peer-1", "http://10.0.0.2:8100")
        prober.remove_peer("peer-1")
        assert "peer-1" not in prober._peers

    def test_probe_result_parallelism(self):
        result = ProbeResult("peer-1", "http://x", rtt_median_ms=5.0, probes_sent=5, probes_succeeded=5, measured_at=time.time())
        assert result.parallelism_capability == "tensor_parallel"

        result2 = ProbeResult("peer-2", "http://x", rtt_median_ms=30.0, probes_sent=5, probes_succeeded=5, measured_at=time.time())
        assert result2.parallelism_capability == "pipeline_parallel"

        result3 = ProbeResult("peer-3", "http://x", rtt_median_ms=100.0, probes_sent=5, probes_succeeded=5, measured_at=time.time())
        assert result3.parallelism_capability == "expert_parallel"

    def test_probe_result_reachable(self):
        r1 = ProbeResult("p1", "http://x", probes_sent=5, probes_succeeded=4, measured_at=time.time())
        assert r1.is_reachable  # 80% success

        r2 = ProbeResult("p2", "http://x", probes_sent=5, probes_succeeded=1, measured_at=time.time())
        assert not r2.is_reachable  # 20% success

    def test_network_summary_empty(self):
        prober = LatencyProber("my-node")
        summary = prober.get_network_summary()
        assert summary["peers"] == 0


# ── Distributed Training Tests ──────────────────────────────────

from hiveai.compute.distributed_training import (
    TrainingOrchestrator,
    FederatedLoRACoordinator,
    TrainingTask,
    TrainingMode,
    TrainingContribution,
    DisTrOPretrainingCoordinator,
)

class TestDistributedTraining:
    def test_recommend_federated_lora(self):
        orch = TrainingOrchestrator()
        rec = orch.recommend_training_mode(14.0, "finetune", 2, 100.0)
        assert rec["mode"] == TrainingMode.FEDERATED_LORA.value
        assert rec["feasible"]

    def test_recommend_distro_for_pretrain(self):
        orch = TrainingOrchestrator()
        rec = orch.recommend_training_mode(14.0, "pretrain", 20, 100.0)
        assert rec["mode"] == TrainingMode.DISTRO_PRETRAIN.value

    def test_federated_lora_task_lifecycle(self):
        coord = FederatedLoRACoordinator()
        task = TrainingTask(
            task_id="test-task",
            mode=TrainingMode.FEDERATED_LORA,
            base_model="Qwen3-14B",
            dataset_id="test-dataset",
        )
        coord.create_task(task)
        assert "test-task" in coord.active_tasks

        # Submit contribution
        contrib = TrainingContribution(
            node_id="node-1",
            task_id="test-task",
            steps_completed=100,
            adapter_cid="QmTest123",
            loss_history=[2.0, 1.5, 1.2],
        )
        coord.submit_contribution(contrib)

        status = coord.get_task_status("test-task")
        assert status["contributors"] == 1
        assert status["total_steps"] == 100

    def test_merge_config_generation(self):
        coord = FederatedLoRACoordinator()
        task = TrainingTask(task_id="t1", mode=TrainingMode.FEDERATED_LORA, base_model="Qwen3-14B", dataset_id="ds1")
        coord.create_task(task)
        coord.submit_contribution(TrainingContribution("n1", "t1", 100, adapter_cid="cid1", loss_history=[1.0]))
        coord.submit_contribution(TrainingContribution("n2", "t1", 200, adapter_cid="cid2", loss_history=[0.8]))

        config = coord.generate_merge_config("t1")
        assert config["merge_method"] == "dare_ties"
        assert len(config["models"]) == 2

    def test_distro_training_time_estimate(self):
        coord = DisTrOPretrainingCoordinator()
        estimate = coord.estimate_training_time(
            model_params_b=14.0,
            dataset_tokens_b=1.0,
            total_gpus=50,
            avg_gpu_tflops=40.0,
        )
        assert estimate["estimated_hours"] > 0
        assert "99" in estimate["scaling_efficiency"]  # near-linear scaling
