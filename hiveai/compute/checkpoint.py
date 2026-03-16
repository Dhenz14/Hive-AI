"""
hiveai/compute/checkpoint.py

Durable worker checkpoint state machine for crash recovery.

Checkpoint stages (advisory for recovery, not authoritative for protocol):
  claimed         — job claimed, nonce received
  started         — start_job called on server
  executing       — workload subprocess running
  output_ready    — output file written, hash computed
  submit_prepared — submit payload assembled
  submit_sent     — submit_result called (server may or may not have received)
  acknowledged    — server confirmed receipt (200 from submit)
  terminal        — job complete (success or reported failure), checkpoint can be cleaned up

Each transition writes the full checkpoint to disk atomically (write-then-rename).
On restart, the worker reads the checkpoint and decides:
  - If stage < submit_sent: fail the job (output may be incomplete)
  - If stage == submit_sent: retry submit with same nonce (server handles idempotency)
  - If stage == acknowledged: clean up, nothing to do
  - If stage == terminal: clean up

The checkpoint file is per-attempt, keyed by attempt_id.
"""

import json
import logging
import os
import platform
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Ordered stages — higher index = further along
STAGES = [
    "claimed",
    "started",
    "executing",
    "output_ready",
    "submit_prepared",
    "submit_sent",
    "acknowledged",
    "terminal",
]

STAGE_INDEX = {s: i for i, s in enumerate(STAGES)}


@dataclass
class WorkerCheckpoint:
    """Durable checkpoint state for a single job attempt."""
    attempt_id: str
    job_id: str
    nonce: str
    lease_token: str
    workload_type: str
    stage: str = "claimed"

    # Populated as work progresses
    output_path: str | None = None
    output_sha256: str | None = None
    output_size_bytes: int | None = None
    result_json: str | None = None
    metrics_json: str | None = None
    provenance_json: str | None = None

    # Metadata
    node_instance_id: str = ""
    created_at: str = ""  # ISO timestamp
    updated_at: str = ""  # ISO timestamp

    def advance_to(self, stage: str) -> None:
        """Advance checkpoint to a new stage. Only forward transitions allowed."""
        if stage not in STAGE_INDEX:
            raise ValueError(f"Unknown checkpoint stage: {stage}")
        if STAGE_INDEX[stage] <= STAGE_INDEX.get(self.stage, -1):
            logger.warning(
                f"Checkpoint advance ignored: {self.stage} -> {stage} "
                f"(not forward) for attempt {self.attempt_id}"
            )
            return
        self.stage = stage
        from datetime import datetime, timezone
        self.updated_at = datetime.now(timezone.utc).isoformat()


class CheckpointStore:
    """Manages durable checkpoint files on disk.

    Checkpoints are stored as JSON files in a dedicated directory.
    Each file is named by attempt_id for easy lookup.

    Write protocol: write to temp file, then atomic rename.
    This prevents partial/corrupt checkpoints from crashes during write.
    """

    def __init__(self, checkpoint_dir: str | Path | None = None):
        if checkpoint_dir is None:
            checkpoint_dir = Path.home() / ".hiveai" / "checkpoints"
        self.dir = Path(checkpoint_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, attempt_id: str) -> Path:
        # Sanitize attempt_id for filesystem safety
        safe_id = attempt_id.replace("/", "_").replace("\\", "_")
        return self.dir / f"{safe_id}.json"

    def save(self, checkpoint: WorkerCheckpoint) -> None:
        """Atomically persist checkpoint to disk."""
        target = self._path(checkpoint.attempt_id)
        data = json.dumps(asdict(checkpoint), indent=2)

        # Write-then-rename for atomicity
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.dir), suffix=".tmp", prefix="ckpt_"
        )
        try:
            os.write(fd, data.encode("utf-8"))
            os.close(fd)
            # On Windows, target must not exist for rename
            if os.path.exists(target):
                os.replace(tmp_path, str(target))
            else:
                os.rename(tmp_path, str(target))
        except Exception:
            os.close(fd) if not os.path.exists(tmp_path) else None
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        logger.debug(f"Checkpoint saved: {checkpoint.attempt_id} stage={checkpoint.stage}")

    def load(self, attempt_id: str) -> WorkerCheckpoint | None:
        """Load checkpoint from disk. Returns None if not found or corrupt."""
        path = self._path(attempt_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text("utf-8"))
            return WorkerCheckpoint(**data)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning(f"Corrupt checkpoint for {attempt_id}: {e}")
            return None

    def remove(self, attempt_id: str) -> None:
        """Remove checkpoint file after job is terminal."""
        path = self._path(attempt_id)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def list_active(self) -> list[WorkerCheckpoint]:
        """List all non-terminal checkpoints (for crash recovery on restart)."""
        active = []
        for path in self.dir.glob("*.json"):
            try:
                data = json.loads(path.read_text("utf-8"))
                cp = WorkerCheckpoint(**data)
                if cp.stage != "terminal":
                    active.append(cp)
            except (json.JSONDecodeError, TypeError, KeyError):
                logger.warning(f"Skipping corrupt checkpoint: {path}")
        return active


def collect_provenance(
    nonce: str,
    worker_version: str = "1.0.0",
    output_sha256: str | None = None,
    output_cid: str | None = None,
    output_size_bytes: int | None = None,
) -> str:
    """Collect structured provenance metadata for submission.

    Returns JSON string with identity + environment + derivation categories.
    """
    import sys

    provenance = {
        "schema_version": 1,
        "identity": {
            "nonce": nonce,
            "worker_version": worker_version,
        },
        "environment": {
            "platform": f"{platform.system()}-{platform.machine()}",
            "python_version": platform.python_version(),
        },
        "derivation": {
            "output_artifact_ref": None,
        },
    }

    # Add optional environment fields
    try:
        import torch
        provenance["environment"]["torch_version"] = torch.__version__
        if torch.cuda.is_available():
            provenance["environment"]["cuda_version"] = torch.version.cuda or ""
    except ImportError:
        pass

    # Add output artifact ref if available
    if output_sha256:
        provenance["derivation"]["output_artifact_ref"] = {
            "cid": output_cid or f"sha256:{output_sha256}",
            "sha256": output_sha256,
            "size_bytes": output_size_bytes or 0,
        }

    return json.dumps(provenance)
