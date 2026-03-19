"""
hiveai/compute/expert_sharding.py

Expert Weight Sharding via IPFS — splits MoE model weights into
per-expert files, pins them on IPFS, and lets community nodes
download only the experts they're assigned to host.

Workflow:
  1. Operator shards model offline: shard_model() → per-expert .safetensors
  2. Operator uploads shards: upload_shards_to_ipfs() → pins on IPFS, registers CIDs on HivePoA
  3. Community node downloads assigned experts: download_experts() → fetches from IPFS, verifies SHA-256
  4. Node loads experts into vLLM/inference engine

MoE expert naming conventions:
  - DeepSeek-V3: model.layers.{L}.mlp.experts.{E}.*
  - Qwen3-MoE: model.layers.{L}.mlp.experts.{E}.*
  - Mixtral: model.layers.{L}.block_sparse_moe.experts.{E}.*
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore


@dataclass
class ShardInfo:
    """Info about a single expert weight shard."""
    expert_index: int
    filename: str
    path: str
    size_bytes: int
    sha256_hash: str
    ipfs_cid: Optional[str] = None


class ExpertSharder:
    """
    Splits MoE model weights into per-expert files.

    Identifies expert parameters by naming convention, groups them,
    and writes each expert's weights to a separate file.
    """

    # Known expert parameter patterns for popular MoE architectures
    EXPERT_PATTERNS = {
        "deepseek": "model.layers.{layer}.mlp.experts.{expert}",
        "qwen": "model.layers.{layer}.mlp.experts.{expert}",
        "mixtral": "model.layers.{layer}.block_sparse_moe.experts.{expert}",
    }

    def shard_model(
        self,
        model_path: str,
        output_dir: str,
        model_type: str = "qwen",
        num_experts: int = 64,
    ) -> list[ShardInfo]:
        """
        Shard a MoE model into per-expert weight files.

        Args:
            model_path: Path to model directory (HuggingFace format with safetensors)
            output_dir: Directory to write per-expert shard files
            model_type: One of "deepseek", "qwen", "mixtral"
            num_experts: Total number of experts in the model

        Returns:
            List of ShardInfo for each expert shard created.
        """
        try:
            from safetensors import safe_open
            from safetensors.torch import save_file
        except ImportError:
            raise ImportError("safetensors required: pip install safetensors")

        model_dir = Path(model_path)
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        pattern_template = self.EXPERT_PATTERNS.get(model_type, self.EXPERT_PATTERNS["qwen"])

        # Collect all safetensors files
        st_files = sorted(model_dir.glob("*.safetensors"))
        if not st_files:
            raise FileNotFoundError(f"No safetensors files in {model_path}")

        # Group parameters by expert index
        expert_params: dict[int, dict[str, object]] = {i: {} for i in range(num_experts)}
        shared_params: dict[str, object] = {}

        for st_file in st_files:
            with safe_open(str(st_file), framework="pt") as f:
                for key in f.keys():
                    expert_idx = self._extract_expert_index(key, model_type)
                    if expert_idx is not None and 0 <= expert_idx < num_experts:
                        expert_params[expert_idx][key] = f.get_tensor(key)
                    else:
                        # Shared parameters (embedding, attention, router, etc.)
                        shared_params[key] = f.get_tensor(key)

        # Write per-expert shard files
        shards = []
        for expert_idx in range(num_experts):
            params = expert_params[expert_idx]
            if not params:
                logger.warning(f"Expert {expert_idx}: no parameters found, skipping")
                continue

            filename = f"expert_{expert_idx:03d}.safetensors"
            filepath = out_dir / filename
            save_file(params, str(filepath))

            # Compute SHA-256
            sha256 = self._file_sha256(str(filepath))
            size = filepath.stat().st_size

            shard = ShardInfo(
                expert_index=expert_idx,
                filename=filename,
                path=str(filepath),
                size_bytes=size,
                sha256_hash=sha256,
            )
            shards.append(shard)
            logger.info(
                f"Expert {expert_idx}: {len(params)} params, "
                f"{size / 1024 / 1024:.1f}MB, sha256={sha256[:16]}..."
            )

        # Also write shared params
        if shared_params:
            shared_file = out_dir / "shared_weights.safetensors"
            save_file(shared_params, str(shared_file))
            logger.info(f"Shared weights: {len(shared_params)} params, {shared_file.stat().st_size / 1024 / 1024:.1f}MB")

        logger.info(f"Sharding complete: {len(shards)} expert shards in {output_dir}")
        return shards

    def _extract_expert_index(self, param_name: str, model_type: str) -> Optional[int]:
        """Extract expert index from a parameter name."""
        # Pattern: ...experts.{N}...
        parts = param_name.split(".")
        for i, part in enumerate(parts):
            if part == "experts" and i + 1 < len(parts):
                try:
                    return int(parts[i + 1])
                except ValueError:
                    pass
        return None

    def _file_sha256(self, filepath: str) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()


class IPFSShardManager:
    """
    Manages upload/download of expert weight shards via IPFS.
    """

    def __init__(
        self,
        ipfs_api_url: str = "http://localhost:5001",
        hivepoa_url: str = "http://localhost:5000",
        api_key: str = "",
    ):
        self.ipfs_api_url = ipfs_api_url.rstrip("/")
        self.hivepoa_url = hivepoa_url.rstrip("/")
        self.api_key = api_key

    async def upload_shards(
        self,
        shards: list[ShardInfo],
        model_name: str,
        quantization: str = "fp16",
    ) -> list[ShardInfo]:
        """Upload shards to IPFS and register CIDs on HivePoA."""
        if aiohttp is None:
            raise ImportError("aiohttp required")

        uploaded = []
        async with aiohttp.ClientSession() as session:
            for shard in shards:
                # Upload to IPFS
                cid = await self._ipfs_add(session, shard.path)
                if not cid:
                    logger.error(f"IPFS upload failed for expert {shard.expert_index}")
                    continue
                shard.ipfs_cid = cid

                # Register on HivePoA
                await self._register_shard(session, shard, model_name, quantization)
                uploaded.append(shard)
                logger.info(f"Expert {shard.expert_index}: uploaded to IPFS as {cid}")

        return uploaded

    async def download_experts(
        self,
        model_name: str,
        expert_indices: list[int],
        output_dir: str,
        quantization: str = "fp16",
    ) -> list[str]:
        """Download specific expert shards from IPFS, verify integrity."""
        if aiohttp is None:
            raise ImportError("aiohttp required")

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        downloaded = []

        async with aiohttp.ClientSession() as session:
            # Get CIDs from HivePoA
            experts_param = ",".join(str(i) for i in expert_indices)
            headers = self._auth_headers()
            async with session.get(
                f"{self.hivepoa_url}/api/community/expert-shards",
                headers=headers,
                params={"model": model_name, "experts": experts_param},
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to query expert shards: HTTP {resp.status}")
                    return []
                data = await resp.json()
                shards = data.get("shards", [])

            for shard_info in shards:
                cid = shard_info.get("ipfsCid")
                expected_hash = shard_info.get("sha256Hash")
                expert_idx = shard_info.get("expertIndex")
                filename = f"expert_{expert_idx:03d}.safetensors"
                filepath = out_dir / filename

                # Download from IPFS
                content = await self._ipfs_cat(session, cid)
                if not content:
                    logger.error(f"IPFS download failed for expert {expert_idx} (CID: {cid})")
                    continue

                # Verify SHA-256
                actual_hash = hashlib.sha256(content).hexdigest()
                if expected_hash and actual_hash != expected_hash:
                    logger.error(
                        f"Expert {expert_idx}: SHA-256 mismatch! "
                        f"expected={expected_hash[:16]}... actual={actual_hash[:16]}..."
                    )
                    continue

                filepath.write_bytes(content)
                downloaded.append(str(filepath))
                logger.info(f"Expert {expert_idx}: downloaded ({len(content) / 1024 / 1024:.1f}MB), verified OK")

        return downloaded

    async def _ipfs_add(self, session: aiohttp.ClientSession, filepath: str) -> Optional[str]:
        """Add a file to IPFS and return its CID."""
        try:
            with open(filepath, "rb") as f:
                data = aiohttp.FormData()
                data.add_field("file", f, filename=os.path.basename(filepath))
                async with session.post(
                    f"{self.ipfs_api_url}/api/v0/add",
                    data=data,
                    params={"pin": "true"},
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result.get("Hash")
        except Exception as e:
            logger.error(f"IPFS add failed: {e}")
        return None

    async def _ipfs_cat(self, session: aiohttp.ClientSession, cid: str) -> Optional[bytes]:
        """Fetch content from IPFS by CID."""
        try:
            async with session.post(
                f"{self.ipfs_api_url}/api/v0/cat",
                params={"arg": cid},
                timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            logger.error(f"IPFS cat failed for {cid}: {e}")
        return None

    async def _register_shard(
        self,
        session: aiohttp.ClientSession,
        shard: ShardInfo,
        model_name: str,
        quantization: str,
    ) -> None:
        """Register shard metadata on HivePoA."""
        headers = self._auth_headers()
        payload = {
            "modelName": model_name,
            "expertIndex": shard.expert_index,
            "shardFilename": shard.filename,
            "ipfsCid": shard.ipfs_cid,
            "sha256Hash": shard.sha256_hash,
            "sizeBytes": shard.size_bytes,
            "quantization": quantization,
        }
        try:
            async with session.post(
                f"{self.hivepoa_url}/api/community/expert-shards",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    logger.warning(f"Shard registration failed: HTTP {resp.status}: {body[:200]}")
        except Exception as e:
            logger.error(f"Shard registration error: {e}")

    def _auth_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"ApiKey {self.api_key}"
        return headers
