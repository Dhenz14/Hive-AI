"""
hiveai/dbc/hivepoa.py

Adapter storage client for the DBC protocol.

Currently wraps IPFS (via ipfshttpclient) since HivePoA isn't live yet.
When HivePoA launches, this module will be extended with their REST API
while keeping the same public interface.

Fallback chain: HivePoA (future) → IPFS → GitHub Releases (bootstrap).
"""

import hashlib
import logging
import os
import shutil
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


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
