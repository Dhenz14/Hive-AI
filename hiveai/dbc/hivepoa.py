"""
hiveai/dbc/hivepoa.py

Adapter storage client + trust integration for the DBC protocol.

Storage: IPFS (via ipfshttpclient) with GitHub Releases fallback.
Trust:   Reads witness-rooted WoT eligibility from HivePoA trust registry.

Fallback chain: HivePoA (future) → IPFS → GitHub Releases (bootstrap).
Trust chain:    HivePoA trust registry → local cache → fail-closed.
"""

import hashlib
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Feature flag: set HIVEPOA_TRUST_ENABLED=true to activate trust checks
TRUST_ENABLED = os.environ.get("HIVEPOA_TRUST_ENABLED", "false").lower() == "true"
HIVEPOA_BASE_URL = os.environ.get("HIVEPOA_URL", "http://localhost:3000")
TRUST_CHECK_TIMEOUT = 5  # seconds
TRUST_CACHE_TTL = 300    # 5 minute cache


@dataclass
class TrustCheckResult:
    """Result of a trust eligibility check from HivePoA."""
    eligible: bool
    eligibility_type: str  # "witness", "vouched", "none"
    witness_rank: int | None
    vouchers: list[str]
    opted_in: bool
    status: str
    role: str
    cached: bool = False
    error: str | None = None


def compute_file_hash(file_path: str) -> str:
    """SHA-256 hash of a file for integrity verification."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


class HivePoAClient:
    """Adapter storage and retrieval.

    Currently uses IPFS as the storage layer. When HivePoA launches,
    this class will add HivePoA as the primary backend with IPFS and
    GitHub Releases as fallbacks.

    Usage:
        client = HivePoAClient()
        result = client.upload_adapter("/path/to/adapter.gguf")
        # result = {"cid": "Qm...", "size_bytes": 300000000, "sha256": "abc..."}

        path = client.download_adapter("Qm...", output_dir="adapters/")
    """

    def __init__(
        self,
        ipfs_addr: str = "/ip4/127.0.0.1/tcp/5001",
        github_repo: str | None = None,
        adapter_dir: str = "adapters",
    ):
        """
        Args:
            ipfs_addr: IPFS daemon multiaddr (default: local daemon on 5001).
            github_repo: GitHub repo for fallback downloads (e.g. "theyc/HiveAI").
            adapter_dir: Default directory for downloaded adapters.
        """
        self._ipfs_addr = ipfs_addr
        self._github_repo = github_repo
        self._adapter_dir = adapter_dir

    def _get_ipfs_client(self):
        """Lazy-connect to IPFS daemon."""
        try:
            import ipfshttpclient

            return ipfshttpclient.connect(self._ipfs_addr)
        except ImportError:
            raise ImportError(
                "ipfshttpclient is required for IPFS storage. "
                "Install with: pip install ipfshttpclient"
            )
        except Exception as e:
            raise ConnectionError(
                f"Cannot connect to IPFS daemon at {self._ipfs_addr}: {e}. "
                "Ensure IPFS daemon is running: ipfs daemon"
            )

    def upload_adapter(self, file_path: str) -> dict:
        """Pin adapter file to IPFS.

        Returns:
            {"cid": "Qm...", "size_bytes": int, "sha256": str}
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Adapter file not found: {file_path}")

        file_hash = compute_file_hash(file_path)
        file_size = os.path.getsize(file_path)

        client = self._get_ipfs_client()
        result = client.add(file_path)
        cid = result["Hash"]

        logger.info(
            f"Adapter pinned to IPFS: {cid} "
            f"({file_size / 1024 / 1024:.1f} MB, sha256={file_hash[:12]}...)"
        )

        return {
            "cid": cid,
            "size_bytes": file_size,
            "sha256": file_hash,
        }

    def download_adapter(
        self,
        cid: str,
        output_dir: str | None = None,
        github_tag: str | None = None,
    ) -> str:
        """Download adapter by CID. Tries IPFS first, falls back to GitHub.

        Args:
            cid: IPFS Content ID of the adapter.
            output_dir: Directory to save the adapter. Defaults to self._adapter_dir.
            github_tag: Optional GitHub release tag for fallback download.

        Returns:
            Path to the downloaded adapter file.
        """
        out_dir = output_dir or self._adapter_dir
        os.makedirs(out_dir, exist_ok=True)

        # Try IPFS first
        try:
            return self._download_from_ipfs(cid, out_dir)
        except Exception as e:
            logger.warning(f"IPFS download failed for {cid}: {e}")

        # Fallback: GitHub Releases
        if github_tag and self._github_repo:
            try:
                return self._download_from_github(github_tag, out_dir)
            except Exception as e:
                logger.warning(
                    f"GitHub download failed for {github_tag}: {e}"
                )

        raise ConnectionError(
            f"Failed to download adapter {cid}. "
            "Neither IPFS nor GitHub fallback succeeded."
        )

    def _download_from_ipfs(self, cid: str, output_dir: str) -> str:
        """Download from IPFS daemon."""
        client = self._get_ipfs_client()
        client.get(cid, target=output_dir)
        downloaded = os.path.join(output_dir, cid)

        # Rename to a friendlier name if the CID file exists
        if os.path.exists(downloaded):
            final_path = os.path.join(output_dir, f"{cid}.gguf")
            shutil.move(downloaded, final_path)
            logger.info(f"Downloaded adapter from IPFS: {cid} → {final_path}")
            return final_path

        logger.info(f"Downloaded adapter from IPFS: {cid}")
        return downloaded

    def _download_from_github(self, tag: str, output_dir: str) -> str:
        """Download adapter from GitHub Releases with resume support."""
        if not self._github_repo:
            raise ValueError("No github_repo configured for fallback")

        # GitHub Releases API URL
        url = (
            f"https://github.com/{self._github_repo}"
            f"/releases/download/{tag}/adapter.gguf"
        )

        output_path = os.path.join(output_dir, f"{tag}.gguf")
        temp_path = output_path + ".partial"

        # Resume support via Range header
        downloaded = 0
        if os.path.exists(temp_path):
            downloaded = os.path.getsize(temp_path)
            logger.info(
                f"Resuming GitHub download from {downloaded} bytes"
            )

        headers = {}
        if downloaded > 0:
            headers["Range"] = f"bytes={downloaded}-"

        resp = requests.get(url, headers=headers, stream=True, timeout=30)
        resp.raise_for_status()

        mode = "ab" if downloaded > 0 else "wb"
        total = int(resp.headers.get("content-length", 0)) + downloaded

        with open(temp_path, mode) as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded / total * 100
                    if downloaded % (10 * 1024 * 1024) < 1024 * 1024:  # Log every ~10MB
                        logger.info(
                            f"GitHub download: {downloaded / 1024 / 1024:.0f} / "
                            f"{total / 1024 / 1024:.0f} MB ({pct:.1f}%)"
                        )

        # Atomic rename
        shutil.move(temp_path, output_path)
        logger.info(
            f"Downloaded adapter from GitHub: {tag} → {output_path} "
            f"({os.path.getsize(output_path) / 1024 / 1024:.1f} MB)"
        )
        return output_path

    def check_availability(self, cid: str) -> bool:
        """Check if a CID is available on the IPFS network."""
        try:
            client = self._get_ipfs_client()
            # Use object stat instead of full download — faster
            stat = client.object.stat(cid)
            return stat is not None
        except Exception:
            return False

    def verify_integrity(self, file_path: str, expected_sha256: str) -> bool:
        """Verify a downloaded file matches expected hash."""
        actual = compute_file_hash(file_path)
        if actual != expected_sha256:
            logger.error(
                f"Integrity check failed: expected {expected_sha256[:12]}..., "
                f"got {actual[:12]}..."
            )
            return False
        return True

    # ================================================================
    # Trust Registry Integration
    # ================================================================

    # In-memory cache: (username, role) -> (TrustCheckResult, expiry_time)
    _trust_cache: dict[tuple[str, str], tuple["TrustCheckResult", float]] = {}

    def check_trust(self, username: str, role: str) -> TrustCheckResult:
        """Check if a Hive account is trusted for a specific role.

        Calls HivePoA's GET /api/trust/check/:username/:role.

        Behavior:
        - If HIVEPOA_TRUST_ENABLED=false: returns NOT eligible (fail-closed for privileged path)
        - If HivePoA is unreachable: returns NOT eligible (fail-closed)
        - Results cached for TRUST_CACHE_TTL seconds

        This method is read-only. Hive-AI never writes trust state.
        HivePoA decides who is trusted; Hive-AI consumes the yes/no.
        """
        if not TRUST_ENABLED:
            return TrustCheckResult(
                eligible=False, eligibility_type="none", witness_rank=None,
                vouchers=[], opted_in=False, status="trust_disabled", role=role,
                error="HIVEPOA_TRUST_ENABLED is false",
            )

        # Check cache
        cache_key = (username, role)
        if cache_key in self._trust_cache:
            result, expiry = self._trust_cache[cache_key]
            if time.time() < expiry:
                result.cached = True
                return result

        # Call HivePoA
        try:
            url = f"{HIVEPOA_BASE_URL}/api/trust/check/{username}/{role}"
            resp = requests.get(url, timeout=TRUST_CHECK_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            result = TrustCheckResult(
                eligible=data.get("eligible", False),
                eligibility_type=data.get("eligibilityType", "none"),
                witness_rank=data.get("witnessRank"),
                vouchers=data.get("vouchers", []),
                opted_in=data.get("optedIn", False),
                status=data.get("status", "unknown"),
                role=role,
            )

            # Cache the result
            self._trust_cache[cache_key] = (result, time.time() + TRUST_CACHE_TTL)
            return result

        except requests.Timeout:
            logger.warning(f"Trust check timed out for {username}/{role}")
            return TrustCheckResult(
                eligible=False, eligibility_type="none", witness_rank=None,
                vouchers=[], opted_in=False, status="timeout", role=role,
                error="HivePoA trust check timed out",
            )
        except requests.ConnectionError:
            logger.warning(f"Trust check failed — HivePoA unreachable for {username}/{role}")
            return TrustCheckResult(
                eligible=False, eligibility_type="none", witness_rank=None,
                vouchers=[], opted_in=False, status="unreachable", role=role,
                error="HivePoA unreachable",
            )
        except Exception as e:
            logger.error(f"Trust check error for {username}/{role}: {e}")
            return TrustCheckResult(
                eligible=False, eligibility_type="none", witness_rank=None,
                vouchers=[], opted_in=False, status="error", role=role,
                error=str(e),
            )

    def get_trusted_accounts(self, role: str) -> set[str]:
        """Get the set of trusted usernames for a role.

        Calls HivePoA's GET /api/trust/roles/:role/members.
        Used to populate NodeConfig.wot_accounts for consensus evaluation.

        Returns empty set if trust is disabled or HivePoA is unreachable.
        """
        if not TRUST_ENABLED:
            return set()

        try:
            url = f"{HIVEPOA_BASE_URL}/api/trust/roles/{role}/members"
            resp = requests.get(url, timeout=TRUST_CHECK_TIMEOUT)
            resp.raise_for_status()
            members = resp.json()
            return {m["username"] for m in members if m.get("status") == "active"}
        except Exception as e:
            logger.warning(f"Failed to fetch trusted accounts for {role}: {e}")
            return set()
