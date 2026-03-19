"""
hiveai/compute/lmcache_config.py

LMCache Integration — hierarchical KV cache for vLLM.

LMCache is the de facto KV cache layer for production LLM serving (2025).
It provides GPU → CPU → disk → Redis hierarchical storage with automatic
eviction and cross-node cache sharing.

Replaces the custom KVCacheIndex/KVCacheAwareRouter (which is preserved
but deprecated) with production-grade cache infrastructure.

Integration points:
  - vLLM: --kv-transfer-config flag points to LMCache config
  - vLLM: --enable-prefix-caching works alongside LMCache
  - Docker: LMCache runs as a sidecar or in-process with vLLM
  - Cluster mode: Redis backend enables cross-node cache sharing

Benefits over custom router:
  - 3-10x latency reduction (LMCache benchmarks)
  - GPU memory KV cache offloading (run longer contexts)
  - Automatic eviction policies
  - Cross-node cache sharing for multi-turn conversations
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LMCacheConfig:
    """Configuration for LMCache hierarchical KV cache."""

    # Local cache tier (fastest)
    local_device: str = "cpu"  # "cpu" or "cuda" (GPU cache tier)
    max_local_cache_size_gb: float = 4.0

    # Disk cache tier (larger, slower)
    disk_cache_enabled: bool = True
    disk_cache_path: str = "/tmp/lmcache"
    max_disk_cache_size_gb: float = 20.0

    # Remote cache tier (cross-node sharing, cluster mode)
    remote_url: Optional[str] = None  # Redis URL, e.g., "redis://redis:6379"
    remote_serde: str = "cachegen"  # serialization: "cachegen" (compressed) or "safetensors"

    # Cache behavior
    chunk_size: int = 256  # tokens per KV chunk (LMCache default)
    eviction_policy: str = "lru"  # "lru" or "s3fifo"

    # Performance
    enable_prefix_caching: bool = True
    enable_blending: bool = True  # blend KV from cache with recomputed KV

    def to_lmcache_config(self) -> dict:
        """Generate LMCache YAML-compatible config dict."""
        config: dict = {
            "chunk_size": self.chunk_size,
            "local_device": self.local_device,
        }

        # Local tier
        if self.local_device == "cpu":
            config["local_cpu"] = {
                "max_size_gb": self.max_local_cache_size_gb,
                "eviction_policy": self.eviction_policy,
            }
        else:
            config["local_gpu"] = {
                "max_size_gb": self.max_local_cache_size_gb,
            }

        # Disk tier
        if self.disk_cache_enabled:
            config["local_disk"] = {
                "path": self.disk_cache_path,
                "max_size_gb": self.max_disk_cache_size_gb,
            }

        # Remote tier (Redis for cluster)
        if self.remote_url:
            config["remote"] = {
                "url": self.remote_url,
                "serde": self.remote_serde,
            }

        return config

    def to_yaml_string(self) -> str:
        """Generate LMCache YAML config string."""
        config = self.to_lmcache_config()
        # Simple YAML serialization (no pyyaml dependency needed)
        lines = []
        for key, value in config.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)


class LMCacheIntegration:
    """
    Manages LMCache configuration for vLLM integration.

    Usage:
        lmcache = LMCacheIntegration(LMCacheConfig(
            remote_url="redis://redis:6379"  # for cluster mode
        ))

        # Get vLLM CLI flags
        flags = lmcache.get_vllm_cli_flags()
        # → ["--kv-transfer-config", '{"kv_connector":"LMCacheConnector",...}']

        # Write config file for Docker volume mount
        lmcache.write_config("/config/lmcache.yaml")
    """

    def __init__(self, config: Optional[LMCacheConfig] = None):
        self.config = config or LMCacheConfig()

    def get_vllm_cli_flags(self) -> list[str]:
        """
        Generate vLLM CLI flags for LMCache integration.

        vLLM V1 supports LMCache via --kv-transfer-config with the
        LMCacheConnector backend.
        """
        flags = ["--enable-prefix-caching"]

        # LMCache KV connector config
        kv_config = {
            "kv_connector": "LMCacheConnector",
            "kv_role": "kv_both",  # both producer and consumer
            "config": self.config.to_lmcache_config(),
        }

        flags.extend(["--kv-transfer-config", json.dumps(kv_config)])

        return flags

    def get_vllm_env_vars(self) -> dict:
        """Get environment variables for LMCache configuration."""
        env = {
            "LMCACHE_CHUNK_SIZE": str(self.config.chunk_size),
            "LMCACHE_LOCAL_DEVICE": self.config.local_device,
        }
        if self.config.disk_cache_enabled:
            env["LMCACHE_DISK_PATH"] = self.config.disk_cache_path
        if self.config.remote_url:
            env["LMCACHE_REMOTE_URL"] = self.config.remote_url
            env["LMCACHE_REMOTE_SERDE"] = self.config.remote_serde
        return env

    def write_config(self, path: str) -> None:
        """Write LMCache config to a YAML file."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(self.config.to_yaml_string())
        logger.info(f"LMCache config written to {path}")

    def get_docker_compose_fragment(self) -> dict:
        """Generate docker-compose service fragment for LMCache sidecar."""
        if not self.config.remote_url:
            # No Redis needed for local-only caching
            return {}

        return {
            "redis": {
                "image": "redis:7-alpine",
                "ports": ["6379:6379"],
                "volumes": ["redis_data:/data"],
                "healthcheck": {
                    "test": ["CMD", "redis-cli", "ping"],
                    "interval": "10s",
                    "timeout": "5s",
                    "retries": 3,
                },
            }
        }

    def get_cache_stats_config(self) -> dict:
        """Configuration for cache statistics endpoint."""
        return {
            "endpoint": "/v1/cache/stats",
            "metrics": [
                "cache_hits",
                "cache_misses",
                "evictions",
                "memory_used_gb",
                "disk_used_gb",
                "remote_hits",
                "remote_misses",
                "avg_lookup_ms",
            ],
            "refresh_interval_seconds": 10,
        }

    @staticmethod
    def for_tier(tier: int, cluster_mode: bool = False) -> "LMCacheIntegration":
        """Create LMCache config optimized for a specific Spirit Bomb tier."""
        if tier == 1:
            # Tier 1: local only, small cache
            config = LMCacheConfig(
                local_device="cpu",
                max_local_cache_size_gb=2.0,
                disk_cache_enabled=True,
                max_disk_cache_size_gb=10.0,
                remote_url=None,
            )
        elif tier == 2:
            # Tier 2: larger local cache, optional cluster
            config = LMCacheConfig(
                local_device="cpu",
                max_local_cache_size_gb=4.0,
                disk_cache_enabled=True,
                max_disk_cache_size_gb=20.0,
                remote_url="redis://redis:6379" if cluster_mode else None,
            )
        else:
            # Tier 3: full cluster with GPU cache tier
            config = LMCacheConfig(
                local_device="cpu",
                max_local_cache_size_gb=8.0,
                disk_cache_enabled=True,
                max_disk_cache_size_gb=50.0,
                remote_url="redis://redis:6379" if cluster_mode else None,
                remote_serde="cachegen",
                enable_blending=True,
            )

        return LMCacheIntegration(config)
