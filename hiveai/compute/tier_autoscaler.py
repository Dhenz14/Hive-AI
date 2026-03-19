"""
hiveai/compute/tier_autoscaler.py

Tier Autoscaler — automatic tier transitions with graceful degradation.

Handles the dynamic scaling behavior:
  - Pool grows → upgrade tier (more experts, better model)
  - Pool shrinks → downgrade tier (fewer experts, lighter model)
  - Hysteresis: prevents tier flapping on edge of threshold
  - Drain period: when downgrading, gives in-flight requests time to finish
  - Model warmup: pre-loads next tier's model before activating

The autoscaler is invoked by the CommunityCoordinator after each poll cycle.
It encapsulates all tier transition logic including:
  - MoE expert reconfiguration
  - Inference route updates
  - Model swap orchestration
  - Contribution reward adjustment

Tier thresholds with hysteresis:
  Tier 1 → 2: upgrade at 15 GPUs, downgrade at 12 (3-GPU buffer)
  Tier 2 → 3: upgrade at 40 GPUs, downgrade at 35 (5-GPU buffer)
"""

import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class Tier(IntEnum):
    BASE = 1
    ENHANCED = 2
    FULL = 3


# Thresholds with hysteresis to prevent flapping
UPGRADE_THRESHOLDS = {
    Tier.BASE: 15,      # upgrade to Tier 2 at 15 GPUs
    Tier.ENHANCED: 40,  # upgrade to Tier 3 at 40 GPUs
}

DOWNGRADE_THRESHOLDS = {
    Tier.ENHANCED: 12,  # downgrade to Tier 1 at 12 GPUs
    Tier.FULL: 35,      # downgrade to Tier 2 at 35 GPUs
}

# Minimum time between tier transitions (prevents flapping)
MIN_TRANSITION_INTERVAL_SECONDS = 900  # 15 min

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
    current_tier: Tier = Tier.BASE
    last_transition_time: float = 0.0
    pending_transition: Optional[TierTransition] = None
    transition_history: list[TierTransition] = field(default_factory=list)
    # Smoothed GPU count (exponential moving average to dampen spikes)
    smoothed_gpu_count: float = 0.0
    ema_alpha: float = 0.3  # weight for new observation


class TierAutoscaler:
    """
    Manages automatic tier transitions with safety mechanisms.

    Safety features:
    - Hysteresis: different thresholds for up/down (prevents flapping)
    - EMA smoothing: dampens transient GPU count spikes
    - Minimum interval: at least 15 min between transitions
    - Drain period: 60s grace period for in-flight requests on downgrade
    - Callbacks: hooks for MoE reconfiguration, model swap, route updates

    Usage:
        scaler = TierAutoscaler()
        scaler.on_tier_change(my_reconfigure_callback)

        # Called each poll cycle:
        new_tier = scaler.evaluate(total_gpus=25)
    """

    def __init__(self):
        self.state = AutoscalerState()
        self._callbacks: list[Callable] = []

    def on_tier_change(self, callback: Callable) -> None:
        """Register a callback for tier transitions.

        Callback signature: callback(old_tier: int, new_tier: int, gpu_count: int)
        """
        self._callbacks.append(callback)

    def evaluate(self, total_gpus: int) -> Tier:
        """
        Evaluate whether a tier transition should occur.

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
        target = self._check_upgrade(current, smoothed)
        if target and target != current:
            # Upgrades are instant (no drain needed)
            transition = TierTransition(
                from_tier=current,
                to_tier=target,
                gpu_count=total_gpus,
                timestamp=now,
                reason=f"Pool grew to {total_gpus} GPUs (smoothed: {smoothed:.1f})",
                completed=True,
            )
            self._commit_transition(transition)
            return self.state.current_tier

        # Check for downgrade
        target = self._check_downgrade(current, smoothed)
        if target and target != current:
            # Downgrades require drain period
            transition = TierTransition(
                from_tier=current,
                to_tier=target,
                gpu_count=total_gpus,
                timestamp=now,
                reason=f"Pool shrank to {total_gpus} GPUs (smoothed: {smoothed:.1f})",
            )
            self.state.pending_transition = transition
            logger.info(
                f"Downgrade initiated: {current.name} → {target.name} "
                f"(drain period: {DRAIN_PERIOD_SECONDS}s)"
            )
            return current  # Stay on current tier during drain

        return current

    def _check_upgrade(self, current: Tier, smoothed_gpus: float) -> Optional[Tier]:
        """Check if we should upgrade to a higher tier."""
        if current == Tier.FULL:
            return None  # Already at max

        threshold = UPGRADE_THRESHOLDS.get(current)
        if threshold and smoothed_gpus >= threshold:
            return Tier(current + 1)
        return None

    def _check_downgrade(self, current: Tier, smoothed_gpus: float) -> Optional[Tier]:
        """Check if we should downgrade to a lower tier."""
        if current == Tier.BASE:
            return None  # Already at min

        threshold = DOWNGRADE_THRESHOLDS.get(current)
        if threshold and smoothed_gpus < threshold:
            return Tier(current - 1)
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
                "upgrade_to_tier2": UPGRADE_THRESHOLDS[Tier.BASE],
                "upgrade_to_tier3": UPGRADE_THRESHOLDS[Tier.ENHANCED],
                "downgrade_to_tier1": DOWNGRADE_THRESHOLDS[Tier.ENHANCED],
                "downgrade_to_tier2": DOWNGRADE_THRESHOLDS[Tier.FULL],
            },
        }
