"""
hiveai/compute/tier_autoscaler.py

Tier Autoscaler — automatic tier transitions with graceful degradation.

Tier definitions (additive, never removes what works):
  Solo (1):    0-1 GPUs — Hive-AI's own stack unchanged
  Pool (2):    2+ GPUs — each serves independent requests (throughput scaling)
  Cluster (3): 2+ GPUs with <50ms latency + 24GB+ VRAM (capability scaling via vLLM PP)

Transition logic:
  Solo → Pool: upgrade when 2+ GPUs come online
  Pool → Cluster: upgrade when a latency-qualified cluster forms
  Cluster → Pool: downgrade when cluster disqualifies (latency/VRAM)
  Pool → Solo: downgrade when only 1 GPU remains

Safety features:
  - Hysteresis: Pool→Solo at 1 GPU (not 2), prevents flapping
  - EMA smoothing: dampens transient GPU count spikes
  - Minimum interval: at least 15 min between transitions
  - Drain period: 60s grace period for in-flight requests on downgrade

IMPORTANT: These thresholds must stay in sync with community_coordinator.py
and spirit-bomb-service.ts (HivePoA).
"""

import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class Tier(IntEnum):
    SOLO = 1       # Local only — Hive-AI handles everything
    POOL = 2       # Multiple GPUs serve independent requests
    CLUSTER = 3    # GPUs combine via vLLM pipeline parallel


# Upgrade thresholds
UPGRADE_THRESHOLDS = {
    Tier.SOLO: 2,  # upgrade to Pool when 2+ GPUs available
    # Pool → Cluster is NOT count-based — requires cluster_qualified=True
}

# Downgrade thresholds (with hysteresis)
DOWNGRADE_THRESHOLDS = {
    Tier.POOL: 1,      # downgrade to Solo when only 1 GPU remains
    # Cluster → Pool when cluster disqualifies (not count-based)
}

# Minimum time between tier transitions (prevents flapping)
# Upgrades can happen faster (low risk), downgrades need more caution
MIN_TRANSITION_INTERVAL_SECONDS = 300  # 5 min

# Drain period before completing downgrade
DRAIN_PERIOD_SECONDS = 60  # give in-flight requests 60s to finish


@dataclass
class TierTransition:
    """Record of a tier transition."""
    from_tier: Tier
    to_tier: Tier
    gpu_count: int
    timestamp: float
    reason: str
    completed: bool = False


@dataclass
class AutoscalerState:
    """Current autoscaler state."""
    current_tier: Tier = Tier.SOLO
    last_transition_time: float = 0.0
    pending_transition: Optional[TierTransition] = None
    transition_history: list[TierTransition] = field(default_factory=list)
    # Smoothed GPU count (exponential moving average to dampen spikes)
    smoothed_gpu_count: float = 0.0
    ema_alpha: float = 0.15  # weight for new observation (lower = more stable)


class TierAutoscaler:
    """
    Manages automatic tier transitions with safety mechanisms.

    Usage:
        scaler = TierAutoscaler()
        scaler.on_tier_change(my_reconfigure_callback)

        # Called each poll cycle:
        new_tier = scaler.evaluate(total_gpus=5, cluster_qualified=False)
    """

    def __init__(self):
        self.state = AutoscalerState()
        self._callbacks: list[Callable] = []

    def on_tier_change(self, callback: Callable) -> None:
        """Register a callback for tier transitions.

        Callback signature: callback(old_tier: int, new_tier: int, gpu_count: int)
        """
        self._callbacks.append(callback)

    def evaluate(self, total_gpus: int, cluster_qualified: bool = False) -> Tier:
        """
        Evaluate whether a tier transition should occur.

        Args:
            total_gpus: Current number of online GPUs
            cluster_qualified: True if any cluster has <50ms latency + 24GB+ VRAM

        Returns the current (possibly new) tier.
        """
        now = time.time()

        # Update smoothed GPU count
        if self.state.smoothed_gpu_count == 0:
            self.state.smoothed_gpu_count = float(total_gpus)
        else:
            alpha = self.state.ema_alpha
            self.state.smoothed_gpu_count = (
                alpha * total_gpus + (1 - alpha) * self.state.smoothed_gpu_count
            )

        smoothed = self.state.smoothed_gpu_count
        current = self.state.current_tier

        # Check pending transition (drain period)
        if self.state.pending_transition and not self.state.pending_transition.completed:
            pending = self.state.pending_transition
            elapsed = now - pending.timestamp
            if elapsed >= DRAIN_PERIOD_SECONDS:
                # Drain complete — commit the transition
                self._commit_transition(pending)
                return self.state.current_tier
            else:
                # Still draining
                logger.debug(
                    f"Drain in progress: {DRAIN_PERIOD_SECONDS - elapsed:.0f}s remaining "
                    f"(pending {pending.from_tier.name} → {pending.to_tier.name})"
                )
                return current

        # Minimum interval between transitions
        if now - self.state.last_transition_time < MIN_TRANSITION_INTERVAL_SECONDS:
            return current

        # Check for upgrade
        target = self._check_upgrade(current, smoothed, cluster_qualified)
        if target and target != current:
            # Upgrades are instant (no drain needed)
            transition = TierTransition(
                from_tier=current,
                to_tier=target,
                gpu_count=total_gpus,
                timestamp=now,
                reason=f"Pool grew to {total_gpus} GPUs (smoothed: {smoothed:.1f})"
                       + (", cluster qualified" if cluster_qualified else ""),
                completed=True,
            )
            self._commit_transition(transition)
            return self.state.current_tier

        # Check for downgrade
        target = self._check_downgrade(current, smoothed, cluster_qualified)
        if target and target != current:
            # Downgrades require drain period
            transition = TierTransition(
                from_tier=current,
                to_tier=target,
                gpu_count=total_gpus,
                timestamp=now,
                reason=f"Pool at {total_gpus} GPUs (smoothed: {smoothed:.1f})"
                       + (", cluster disqualified" if not cluster_qualified else ""),
            )
            self.state.pending_transition = transition
            logger.info(
                f"Downgrade initiated: {current.name} → {target.name} "
                f"(drain period: {DRAIN_PERIOD_SECONDS}s)"
            )
            return current  # Stay on current tier during drain

        return current

    def _check_upgrade(self, current: Tier, smoothed_gpus: float,
                       cluster_qualified: bool = False) -> Optional[Tier]:
        """Check if we should upgrade to a higher tier."""
        if current == Tier.CLUSTER:
            return None  # Already at max

        if current == Tier.SOLO and smoothed_gpus >= UPGRADE_THRESHOLDS[Tier.SOLO]:
            return Tier.POOL

        if current == Tier.POOL and cluster_qualified:
            return Tier.CLUSTER

        return None

    def _check_downgrade(self, current: Tier, smoothed_gpus: float,
                         cluster_qualified: bool = False) -> Optional[Tier]:
        """Check if we should downgrade to a lower tier."""
        if current == Tier.SOLO:
            return None  # Already at min

        if current == Tier.CLUSTER and not cluster_qualified:
            return Tier.POOL

        if current == Tier.POOL and smoothed_gpus < DOWNGRADE_THRESHOLDS[Tier.POOL]:
            return Tier.SOLO

        return None

    def _commit_transition(self, transition: TierTransition) -> None:
        """Commit a tier transition and fire callbacks."""
        old_tier = self.state.current_tier
        self.state.current_tier = transition.to_tier
        self.state.last_transition_time = transition.timestamp
        transition.completed = True
        self.state.pending_transition = None
        self.state.transition_history.append(transition)

        direction = "UPGRADE" if transition.to_tier > old_tier else "DOWNGRADE"
        logger.info(
            f"Tier {direction}: {old_tier.name} → {transition.to_tier.name} "
            f"({transition.gpu_count} GPUs). Reason: {transition.reason}"
        )

        # Fire callbacks
        for cb in self._callbacks:
            try:
                cb(old_tier.value, transition.to_tier.value, transition.gpu_count)
            except Exception as e:
                logger.error(f"Tier change callback failed: {e}")

    def force_tier(self, tier: int, reason: str = "manual override") -> None:
        """Force a specific tier (admin override)."""
        target = Tier(tier)
        if target == self.state.current_tier:
            return

        transition = TierTransition(
            from_tier=self.state.current_tier,
            to_tier=target,
            gpu_count=0,
            timestamp=time.time(),
            reason=reason,
            completed=True,
        )
        self._commit_transition(transition)

    def get_status(self) -> dict:
        """Get current autoscaler status for monitoring."""
        pending = self.state.pending_transition
        return {
            "current_tier": self.state.current_tier.value,
            "tier_name": self.state.current_tier.name,
            "tier_mode": {Tier.SOLO: "solo", Tier.POOL: "pool", Tier.CLUSTER: "cluster"}[self.state.current_tier],
            "smoothed_gpu_count": round(self.state.smoothed_gpu_count, 1),
            "last_transition": self.state.last_transition_time,
            "pending_transition": {
                "from": pending.from_tier.name,
                "to": pending.to_tier.name,
                "initiated_at": pending.timestamp,
                "reason": pending.reason,
            } if pending and not pending.completed else None,
            "transition_count": len(self.state.transition_history),
            "thresholds": {
                "upgrade_to_pool": UPGRADE_THRESHOLDS[Tier.SOLO],
                "upgrade_to_cluster": "latency + VRAM qualified",
                "downgrade_to_solo": DOWNGRADE_THRESHOLDS[Tier.POOL],
                "downgrade_to_pool": "cluster disqualified",
            },
        }
