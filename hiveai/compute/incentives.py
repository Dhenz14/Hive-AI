"""
hiveai/compute/incentives.py

HBD Incentive System for community GPU contributions.

Defines reward structures for nodes contributing to the Spirit Bomb:
  - Inference contributions: tokens generated, requests served
  - Training contributions: steps completed, adapter quality
  - Uptime bonuses: consistent availability
  - Tier bonuses: multipliers for higher-tier community participation

Reward calculation:
  Base rate: 0.001 HBD per 1000 tokens generated
  Tier multipliers: Tier 1 = 1x, Tier 2 = 1.5x, Tier 3 = 2x
  Uptime bonus: +10% for 99%+ uptime in period
  Quality bonus: +20% for top-10% throughput nodes

All rewards are tracked in HivePoA's inference_contributions table
and paid out via the existing compute payout system.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Base reward rates (HBD per unit)
BASE_RATE_PER_1K_TOKENS = 0.001  # 0.001 HBD per 1000 tokens
BASE_RATE_PER_REQUEST = 0.0001   # 0.0001 HBD per request served
BASE_RATE_PER_TRAINING_STEP = 0.0005  # 0.0005 HBD per training step

# Tier multipliers
TIER_MULTIPLIERS = {
    1: 1.0,
    2: 1.5,
    3: 2.0,
}

# Uptime thresholds
UPTIME_BONUS_THRESHOLD = 0.99  # 99% uptime
UPTIME_BONUS_MULTIPLIER = 1.10  # +10%

# Quality bonus (top performers)
QUALITY_BONUS_PERCENTILE = 0.10  # top 10%
QUALITY_BONUS_MULTIPLIER = 1.20  # +20%

# Maximum HBD payout per node per period
MAX_PAYOUT_PER_PERIOD_HBD = 10.0  # cap at 10 HBD per period


@dataclass
class ContributionPeriod:
    """A node's contribution during a reward period."""
    node_id: str
    period_start: datetime
    period_end: datetime
    # Inference metrics
    tokens_generated: int = 0
    requests_served: int = 0
    inference_ms: int = 0
    # Training metrics
    training_steps: int = 0
    training_tokens: int = 0
    adapters_submitted: int = 0
    # Availability
    uptime_ratio: float = 0.0  # 0.0 to 1.0
    heartbeats_expected: int = 0
    heartbeats_received: int = 0
    # Computed
    tier: int = 1
    throughput_tps: float = 0.0  # tokens per second


@dataclass
class RewardCalculation:
    """Calculated reward for a contribution period."""
    node_id: str
    period_start: datetime
    period_end: datetime
    # Breakdown
    inference_reward_hbd: float = 0.0
    training_reward_hbd: float = 0.0
    tier_multiplier: float = 1.0
    uptime_bonus: float = 0.0
    quality_bonus: float = 0.0
    # Total
    total_hbd: float = 0.0
    capped: bool = False


class IncentiveCalculator:
    """
    Calculates HBD rewards for community GPU contributions.

    The calculator is deterministic: same inputs always produce same outputs.
    This allows any node to verify the reward calculation independently.
    """

    def __init__(self, current_tier: int = 1):
        self._current_tier = current_tier

    def set_tier(self, tier: int) -> None:
        self._current_tier = tier

    def calculate_reward(
        self,
        contribution: ContributionPeriod,
        all_throughputs: Optional[list[float]] = None,
    ) -> RewardCalculation:
        """
        Calculate HBD reward for a contribution period.

        Args:
            contribution: The node's contribution metrics
            all_throughputs: All nodes' throughputs for quality bonus calculation

        Returns:
            RewardCalculation with breakdown
        """
        result = RewardCalculation(
            node_id=contribution.node_id,
            period_start=contribution.period_start,
            period_end=contribution.period_end,
        )

        # 1. Inference reward
        inference_tokens_k = contribution.tokens_generated / 1000.0
        result.inference_reward_hbd = (
            inference_tokens_k * BASE_RATE_PER_1K_TOKENS
            + contribution.requests_served * BASE_RATE_PER_REQUEST
        )

        # 2. Training reward
        result.training_reward_hbd = (
            contribution.training_steps * BASE_RATE_PER_TRAINING_STEP
        )

        # 3. Tier multiplier
        tier = contribution.tier or self._current_tier
        result.tier_multiplier = TIER_MULTIPLIERS.get(tier, 1.0)

        # 4. Uptime bonus
        if contribution.uptime_ratio >= UPTIME_BONUS_THRESHOLD:
            result.uptime_bonus = UPTIME_BONUS_MULTIPLIER - 1.0  # +10%

        # 5. Quality bonus (top 10% throughput)
        if all_throughputs and contribution.throughput_tps > 0:
            sorted_tps = sorted(all_throughputs, reverse=True)
            threshold_idx = max(1, int(len(sorted_tps) * QUALITY_BONUS_PERCENTILE))
            if contribution.throughput_tps >= sorted_tps[min(threshold_idx, len(sorted_tps) - 1)]:
                result.quality_bonus = QUALITY_BONUS_MULTIPLIER - 1.0  # +20%

        # Total = (inference + training) × tier × (1 + uptime + quality)
        base = result.inference_reward_hbd + result.training_reward_hbd
        multiplier = result.tier_multiplier * (1.0 + result.uptime_bonus + result.quality_bonus)
        result.total_hbd = round(base * multiplier, 6)

        # Cap
        if result.total_hbd > MAX_PAYOUT_PER_PERIOD_HBD:
            result.total_hbd = MAX_PAYOUT_PER_PERIOD_HBD
            result.capped = True

        return result

    def calculate_batch(
        self,
        contributions: list[ContributionPeriod],
    ) -> list[RewardCalculation]:
        """Calculate rewards for a batch of contributions (with quality bonus)."""
        throughputs = [c.throughput_tps for c in contributions if c.throughput_tps > 0]

        return [
            self.calculate_reward(c, throughputs)
            for c in contributions
        ]

    def estimate_earnings(
        self,
        gpu_vram_gb: int,
        hours_per_day: float = 8.0,
        tier: int = 1,
    ) -> dict:
        """
        Estimate potential earnings for a GPU contributing to the community.

        Gives potential contributors an idea of what they could earn.
        """
        # Estimate throughput based on VRAM (rough: more VRAM = bigger model = slower per token)
        if gpu_vram_gb >= 24:
            tps = 40.0  # running larger model
        elif gpu_vram_gb >= 16:
            tps = 60.0
        elif gpu_vram_gb >= 12:
            tps = 80.0
        else:
            tps = 100.0  # small model, fast

        tokens_per_day = tps * 3600 * hours_per_day * 0.3  # 30% utilization
        requests_per_day = tokens_per_day / 200  # avg 200 tokens per request

        daily_inference = (tokens_per_day / 1000) * BASE_RATE_PER_1K_TOKENS
        daily_requests = requests_per_day * BASE_RATE_PER_REQUEST
        daily_base = daily_inference + daily_requests
        daily_with_tier = daily_base * TIER_MULTIPLIERS.get(tier, 1.0)
        monthly = daily_with_tier * 30

        return {
            "gpu_vram_gb": gpu_vram_gb,
            "hours_per_day": hours_per_day,
            "tier": tier,
            "estimated_tokens_per_day": int(tokens_per_day),
            "estimated_requests_per_day": int(requests_per_day),
            "estimated_daily_hbd": round(daily_with_tier, 4),
            "estimated_monthly_hbd": round(monthly, 2),
            "tier_multiplier": TIER_MULTIPLIERS.get(tier, 1.0),
            "note": "Estimates assume 30% GPU utilization. Actual earnings depend on demand.",
        }
