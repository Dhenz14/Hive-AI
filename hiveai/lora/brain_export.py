"""
hiveai/lora/brain_export.py

Export trained adapter brains to IPFS and publish metadata to Hive blockchain.

Flow:
  1. Locate the adapter GGUF file for a given LoraVersion
  2. Pin GGUF to local IPFS daemon
  3. Store CID + metadata in LoraVersion
  4. Publish metadata as custom_json to Hive blockchain
  5. Other nodes: fetch CID from Hive -> download from IPFS -> apply adapter

Dependencies:
  - ipfshttpclient (optional: pip install ipfshttpclient)
  - IPFS daemon running locally (ipfs daemon) on port 5001
"""
import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)


def compute_file_hash(file_path: str) -> str:
    """SHA-256 hash of a file for integrity verification."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def pin_to_ipfs(file_path: str) -> str:
    """
    Pin a file to the local IPFS daemon and return its CID.

    Requires: IPFS daemon running on localhost:5001
    Raises ImportError if ipfshttpclient not installed.
    Raises ConnectionError if daemon not reachable.
    """
    import ipfshttpclient

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Adapter file not found: {file_path}")

    client = ipfshttpclient.connect("/ip4/127.0.0.1/tcp/5001")
    result = client.add(file_path)
    cid = result["Hash"]
    file_size = os.path.getsize(file_path)
    logger.info(f"Pinned to IPFS: {cid} ({file_size / 1024 / 1024:.1f} MB)")
    return cid


def export_brain(lora_version_id: int, db) -> dict:
    """
    Full brain export pipeline for a trained LoRA version.

    1. Locate the adapter GGUF file
    2. Compute SHA-256 for integrity
    3. Pin to IPFS
    4. Update LoraVersion with CID and metadata

    Returns dict with version, ipfs_cid, file_size_mb, sha256, metadata.
    """
    from hiveai.models import LoraVersion

    lv = db.query(LoraVersion).filter(LoraVersion.id == lora_version_id).first()
    if not lv:
        raise ValueError(f"LoraVersion {lora_version_id} not found")
    if lv.status != "ready":
        raise ValueError(f"LoraVersion {lora_version_id} is not ready (status={lv.status})")

    # Find the GGUF file in the adapter directory
    adapter_dir = lv.adapter_path
    if not adapter_dir or not os.path.isdir(adapter_dir):
        raise FileNotFoundError(f"Adapter directory not found: {adapter_dir}")

    gguf_files = [f for f in os.listdir(adapter_dir) if f.endswith(".gguf")]
    if not gguf_files:
        raise FileNotFoundError(f"No .gguf file found in {adapter_dir}")

    gguf_path = os.path.join(adapter_dir, gguf_files[0])
    file_hash = compute_file_hash(gguf_path)
    file_size = os.path.getsize(gguf_path)

    # Pin to IPFS
    cid = pin_to_ipfs(gguf_path)

    # Update DB
    metadata = {
        "file_name": gguf_files[0],
        "file_size": file_size,
        "sha256": file_hash,
        "base_model": lv.base_model,
        "pair_count": lv.pair_count,
        "benchmark_score": lv.benchmark_score,
        "version": lv.version,
    }
    lv.ipfs_cid = cid
    lv.export_metadata = metadata
    db.commit()

    logger.info(f"Brain exported: version={lv.version}, CID={cid}")

    return {
        "version": lv.version,
        "ipfs_cid": cid,
        "file_size_mb": round(file_size / 1024 / 1024, 1),
        "sha256": file_hash,
        "metadata": metadata,
    }


def publish_brain_to_hive(lora_version_id: int, author: str, db) -> dict:
    """
    Publish brain export metadata to Hive blockchain as a custom_json operation.

    The custom_json contains the IPFS CID, version info, and benchmark scores
    so other nodes can discover and download the adapter.

    Returns the operation payload ready for Keychain signing.
    """
    from hiveai.models import LoraVersion

    lv = db.query(LoraVersion).filter(LoraVersion.id == lora_version_id).first()
    if not lv or not lv.ipfs_cid:
        raise ValueError("Must export to IPFS before publishing to Hive")

    custom_json = {
        "app": "hiveai-refinery/1.0",
        "type": "brain_export",
        "version": lv.version,
        "ipfs_cid": lv.ipfs_cid,
        "base_model": lv.base_model,
        "pair_count": lv.pair_count,
        "benchmark_score": lv.benchmark_score,
        "metadata": lv.export_metadata,
    }

    operation = [
        "custom_json",
        {
            "required_auths": [],
            "required_posting_auths": [author],
            "id": "hiveai_brain_export",
            "json": json.dumps(custom_json),
        },
    ]

    return {
        "status": "ready_to_sign",
        "author": author,
        "operation": operation,
        "ipfs_cid": lv.ipfs_cid,
        "message": "Sign with Hive Keychain to broadcast brain export.",
    }


def import_brain(ipfs_cid: str, output_dir: str) -> str:
    """
    Download an adapter from IPFS by CID and save locally.

    Returns path to the downloaded file.
    """
    import ipfshttpclient

    os.makedirs(output_dir, exist_ok=True)

    client = ipfshttpclient.connect("/ip4/127.0.0.1/tcp/5001")
    client.get(ipfs_cid, target=output_dir)

    downloaded = os.path.join(output_dir, ipfs_cid)
    logger.info(f"Downloaded brain from IPFS: {ipfs_cid} -> {downloaded}")
    return downloaded
