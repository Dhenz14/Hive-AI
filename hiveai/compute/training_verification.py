"""
hiveai/compute/training_verification.py

TOPLOC-Style Training Verification — cryptographic proof of training contributions.

Inspired by INTELLECT-2's TOPLOC (Trusted Open Proof of Learning Contributions):
  - Nodes submit training proofs: (step, loss, param_checksum, gradient_norm)
  - Verifiers spot-check by re-running a few steps from a checkpoint
  - Mismatches → slashing/reputation penalty

Proof format:
  At each checkpoint step, the node computes:
  1. loss value (scalar)
  2. param_checksum: SHA-256 of sorted, flattened, rounded (4 decimal) parameters
  3. gradient_norm: L2 norm of gradients at that step
  4. Node signs the proof with its key

Verification protocol:
  1. Verifier selects ~5% of proofs randomly for spot-check
  2. For each selected proof: download the checkpoint, replay N steps (1-3)
  3. Compare: loss within tolerance (1e-2 for bf16), checksum match
  4. If mismatch: mark proof as FAILED, penalize node reputation

Key insight from INTELLECT-2:
  Full verification is expensive (re-run training step). But probabilistic
  spot-checking with slashing makes cheating unprofitable: if 5% of steps
  are verified and cheating is penalized 20x the reward, expected value
  of cheating is negative.
"""

import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ProofStatus(Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    CHALLENGED = "challenged"


@dataclass
class TrainingProof:
    """Cryptographic proof of a training step."""
    node_id: str
    task_id: str
    step: int
    loss: float
    param_checksum: str  # SHA-256 of canonical parameter representation
    gradient_norm: float
    learning_rate: float
    timestamp: str  # ISO 8601
    batch_size: int = 0
    tokens_processed: int = 0
    # Optional: checkpoint location for verification
    checkpoint_cid: Optional[str] = None  # IPFS CID of checkpoint
    # Signature (node signs proof with its key)
    signature: Optional[str] = None

    def to_signable_bytes(self) -> bytes:
        """Canonical byte representation for signing."""
        data = f"{self.node_id}:{self.task_id}:{self.step}:{self.loss:.6f}:{self.param_checksum}:{self.gradient_norm:.6f}:{self.learning_rate:.8f}:{self.timestamp}"
        return data.encode("utf-8")

    def compute_proof_hash(self) -> str:
        """Hash of the proof for deduplication."""
        return hashlib.sha256(self.to_signable_bytes()).hexdigest()


@dataclass
class VerificationChallenge:
    """A challenge to verify a specific training proof."""
    proof_id: str
    proof: TrainingProof
    num_steps_to_replay: int = 1  # replay 1-3 steps from checkpoint
    dataset_shard_id: Optional[str] = None
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class VerificationResult:
    """Result of verifying a training proof."""
    proof_id: str
    verified: bool
    loss_match: bool
    checksum_match: bool
    claimed_loss: float
    replayed_loss: float
    loss_delta: float
    claimed_checksum: str
    replayed_checksum: str
    tolerance_used: float
    verified_at: str = ""
    error: Optional[str] = None

    def __post_init__(self):
        if not self.verified_at:
            self.verified_at = datetime.now(timezone.utc).isoformat()


# Verification tolerances
LOSS_TOLERANCE_FP32 = 1e-4
LOSS_TOLERANCE_BF16 = 1e-2
CHECKSUM_ROUNDING_DECIMALS = 4  # round params to 4 decimals before hashing
DEFAULT_SAMPLE_RATE = 0.05  # verify 5% of proofs
SLASHING_MULTIPLIER = 20  # penalty = 20x the reward for that step


class TOPLOCVerifier:
    """
    TOPLOC-style training contribution verifier.

    Implements probabilistic spot-checking:
    - Select ~5% of submitted proofs for verification
    - Re-run the training step from a checkpoint
    - Compare loss and parameter checksums
    - Flag mismatches for reputation penalty
    """

    def __init__(
        self,
        loss_tolerance: float = LOSS_TOLERANCE_BF16,
        sample_rate: float = DEFAULT_SAMPLE_RATE,
    ):
        self.loss_tolerance = loss_tolerance
        self.sample_rate = sample_rate
        self._proofs: dict[str, TrainingProof] = {}

    def create_proof(
        self,
        node_id: str,
        task_id: str,
        step: int,
        loss: float,
        param_checksum: str,
        gradient_norm: float,
        learning_rate: float,
        checkpoint_cid: Optional[str] = None,
        batch_size: int = 0,
        tokens_processed: int = 0,
    ) -> TrainingProof:
        """Create a training proof for a completed step."""
        proof = TrainingProof(
            node_id=node_id,
            task_id=task_id,
            step=step,
            loss=loss,
            param_checksum=param_checksum,
            gradient_norm=gradient_norm,
            learning_rate=learning_rate,
            timestamp=datetime.now(timezone.utc).isoformat(),
            checkpoint_cid=checkpoint_cid,
            batch_size=batch_size,
            tokens_processed=tokens_processed,
        )

        proof_id = proof.compute_proof_hash()
        self._proofs[proof_id] = proof
        return proof

    def verify_proof(
        self,
        proof: TrainingProof,
        replayed_loss: float,
        replayed_checksum: str,
    ) -> VerificationResult:
        """
        Verify a training proof by comparing against replayed values.

        Args:
            proof: The original proof submitted by the node
            replayed_loss: Loss value from re-running the training step
            replayed_checksum: Parameter checksum from re-running

        Returns:
            VerificationResult with match/mismatch details
        """
        loss_delta = abs(proof.loss - replayed_loss)
        loss_match = loss_delta <= self.loss_tolerance
        checksum_match = proof.param_checksum == replayed_checksum

        verified = loss_match and checksum_match

        result = VerificationResult(
            proof_id=proof.compute_proof_hash(),
            verified=verified,
            loss_match=loss_match,
            checksum_match=checksum_match,
            claimed_loss=proof.loss,
            replayed_loss=replayed_loss,
            loss_delta=loss_delta,
            claimed_checksum=proof.param_checksum,
            replayed_checksum=replayed_checksum,
            tolerance_used=self.loss_tolerance,
        )

        if not verified:
            reasons = []
            if not loss_match:
                reasons.append(f"loss delta {loss_delta:.6f} > tolerance {self.loss_tolerance}")
            if not checksum_match:
                reasons.append("param checksum mismatch")
            result.error = "; ".join(reasons)
            logger.warning(
                f"TOPLOC verification FAILED for {proof.node_id} step {proof.step}: {result.error}"
            )
        else:
            logger.info(f"TOPLOC verification PASSED for {proof.node_id} step {proof.step}")

        return result

    def select_challenges(
        self,
        proofs: list[TrainingProof],
        sample_rate: Optional[float] = None,
    ) -> list[VerificationChallenge]:
        """
        Randomly select proofs for spot-check verification.

        Uses the configured sample rate (default 5%).
        Selection is deterministic for a given proof set (seeded by task_id).
        """
        rate = sample_rate or self.sample_rate
        if not proofs:
            return []

        # Seed random with task_id for deterministic selection
        task_ids = set(p.task_id for p in proofs)
        seed = hashlib.sha256(",".join(sorted(task_ids)).encode()).hexdigest()
        rng = random.Random(seed)

        # Select proofs
        num_to_check = max(1, int(len(proofs) * rate))
        selected = rng.sample(proofs, min(num_to_check, len(proofs)))

        challenges = []
        for proof in selected:
            challenge = VerificationChallenge(
                proof_id=proof.compute_proof_hash(),
                proof=proof,
                num_steps_to_replay=rng.choice([1, 1, 1, 2, 3]),  # mostly 1 step
            )
            challenges.append(challenge)

        logger.info(
            f"TOPLOC: selected {len(challenges)}/{len(proofs)} proofs for verification "
            f"(rate={rate:.1%})"
        )
        return challenges

    @staticmethod
    def compute_param_checksum(params: dict) -> str:
        """
        Compute canonical parameter checksum.

        The checksum is deterministic across hardware:
        1. Sort parameter names
        2. For each parameter, flatten to 1D, round to 4 decimals
        3. SHA-256 of the concatenated rounded values

        This handles fp16/bf16 non-determinism by rounding.
        """
        h = hashlib.sha256()
        for name in sorted(params.keys()):
            tensor = params[name]
            # Handle both numpy arrays and torch tensors
            if hasattr(tensor, "detach"):
                values = tensor.detach().float().cpu().numpy().flatten()
            elif hasattr(tensor, "flatten"):
                values = tensor.flatten()
            else:
                values = [float(tensor)]

            rounded = [round(float(v), CHECKSUM_ROUNDING_DECIMALS) for v in values]
            h.update(json.dumps(rounded, separators=(",", ":")).encode())

        return h.hexdigest()

    def estimate_verification_cost(
        self,
        total_proofs: int,
        step_replay_cost_seconds: float = 10.0,
    ) -> dict:
        """Estimate the cost of verification for a training run."""
        challenges = max(1, int(total_proofs * self.sample_rate))
        avg_replay_steps = 1.4  # weighted average of [1,1,1,2,3]
        total_replay_seconds = challenges * avg_replay_steps * step_replay_cost_seconds

        return {
            "total_proofs": total_proofs,
            "challenges_to_verify": challenges,
            "sample_rate": self.sample_rate,
            "estimated_replay_seconds": round(total_replay_seconds, 1),
            "estimated_replay_hours": round(total_replay_seconds / 3600, 2),
            "slashing_multiplier": SLASHING_MULTIPLIER,
            "expected_cheating_ev": "negative (verification cost < slashing penalty)",
        }
