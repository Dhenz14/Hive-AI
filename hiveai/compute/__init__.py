"""
hiveai/compute — GPU Compute Marketplace + Spirit Bomb Community Cloud

Core modules:
  models.py              — Shared manifest/result contract (workload types, schemas)
  worker.py              — Untrusted GPU worker runtime (claims jobs, executes, reports)
  verifier.py            — Trusted verification module (hidden eval, semantic checks)

Spirit Bomb modules:
  community_coordinator.py — Tier monitoring, manifest publishing, pool tracking
  cluster_manager.py       — Geo-aware GPU clustering, latency-based affinity
  elastic_moe.py           — Dynamic MoE expert activation (tier-aware scaling)
  inference_worker.py      — Community inference contribution mode
  distributed_inference.py — Distributed inference coordinator (vLLM PP/TP/EP)
  tier_autoscaler.py       — Automatic tier transitions with hysteresis
  distributed_training.py  — DisTrO/Hivemind/Federated LoRA training
  helix_placement.py       — Max-flow GPU placement optimizer
  incentives.py            — HBD reward calculations
  speculative_decoding.py  — EAGLE-3 integration
  latency_prober.py        — RTT measurement between community nodes
  kv_cache_router.py       — KV-cache aware request routing (llm-d inspired)
  model_registry.py        — Model selection + quantization per tier/task
"""
