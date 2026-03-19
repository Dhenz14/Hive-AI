"""
hiveai/compute/reward_settlement.py

HBD Reward Settlement Service — bridges contribution tracking to payouts.

The missing link between:
  - InferenceWorker recording contributions → inferenceContributions table
  - IncentiveCalculator computing rewards → RewardCalculation
  - HivePoA payout broadcaster → Hive blockchain HBD transfer

Settlement cycle (runs every SETTLEMENT_INTERVAL):
  1. Query all inference_contributions since last settlement
  2. Group by node_id
  3. For each node: run IncentiveCalculator.calculate_reward()
  4. POST reward to HivePoA as a compute payout
  5. HivePoA's payout broadcaster handles the Hive HBD transfer
  6. Mark contributions as settled

Usage:
    settler = RewardSettlementService(hivepoa_url="http://localhost:5000")
    await settler.run_settlement_cycle()
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional

from hiveai.compute.incentives import (
    IncentiveCalculator,
    ContributionPeriod,
    RewardCalculation,
)

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore

# Settlement configuration
SETTLEMENT_INTERVAL_SECONDS = 3600  # settle every hour
MIN_PAYOUT_HBD = 0.001  # minimum payout threshold (dust filter)
SETTLEMENT_LOOKBACK_HOURS = 1  # look back 1 hour for unsettled contributions


@dataclass
class SettlementRecord:
    """Record of a single node's settlement."""
    node_id: str
    hive_username: str
    period_start: str  # ISO 8601
    period_end: str
    tokens_generated: int
    requests_served: int
    reward_hbd: float
    tier: int
    payout_id: Optional[str] = None  # HivePoA payout ID after submission
    settled: bool = False
    error: Optional[str] = None


@dataclass
class SettlementCycleResult:
    """Result of a complete settlement cycle."""
    cycle_start: str
    cycle_end: str
    nodes_processed: int
    total_hbd: float
    payouts_submitted: int
    payouts_failed: int
    settlements: list[SettlementRecord] = field(default_factory=list)


class RewardSettlementService:
    """
    Bridges contribution tracking to HBD payouts.

    Architecture:
    1. Queries HivePoA for recent unsettled contributions
    2. Runs IncentiveCalculator for each node
    3. Submits payouts back to HivePoA
    4. HivePoA's existing payout broadcaster handles Hive HBD transfer
    """

    def __init__(
        self,
        hivepoa_url: str = "http://localhost:5000",
        api_key: str = "",
        settlement_interval: int = SETTLEMENT_INTERVAL_SECONDS,
        current_tier: int = 1,
    ):
        self.hivepoa_url = hivepoa_url.rstrip("/")
        self.api_key = api_key
        self.settlement_interval = settlement_interval
        self.calculator = IncentiveCalculator(current_tier=current_tier)
        self._last_settlement: Optional[datetime] = None

    async def run(self) -> None:
        """Main settlement loop. Runs settlement cycles at the configured interval."""
        if aiohttp is None:
            raise ImportError("aiohttp required")

        logger.info(f"Reward settlement service started — interval={self.settlement_interval}s")

        while True:
            try:
                result = await self.run_settlement_cycle()
                logger.info(
                    f"Settlement cycle complete: {result.nodes_processed} nodes, "
                    f"{result.total_hbd:.4f} HBD, {result.payouts_submitted} payouts"
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Settlement cycle failed: {e}", exc_info=True)

            await asyncio.sleep(self.settlement_interval)

    async def run_settlement_cycle(self) -> SettlementCycleResult:
        """Execute a single settlement cycle."""
        cycle_start = datetime.now(timezone.utc)
        lookback = cycle_start - timedelta(hours=SETTLEMENT_LOOKBACK_HOURS)

        result = SettlementCycleResult(
            cycle_start=cycle_start.isoformat(),
            cycle_end="",
            nodes_processed=0,
            total_hbd=0.0,
            payouts_submitted=0,
            payouts_failed=0,
        )

        async with aiohttp.ClientSession() as session:
            # 1. Get current tier for multiplier
            tier = await self._get_current_tier(session)
            self.calculator.set_tier(tier)

            # 2. Get contribution stats per node
            contributions = await self._get_node_contributions(session, lookback)
            if not contributions:
                result.cycle_end = datetime.now(timezone.utc).isoformat()
                return result

            # 3. Calculate rewards for each node
            all_throughputs = [c.get("throughput_tps", 0) for c in contributions if c.get("throughput_tps", 0) > 0]

            for contrib in contributions:
                node_id = contrib["node_id"]
                hive_username = contrib.get("hive_username", "unknown")

                period = ContributionPeriod(
                    node_id=node_id,
                    period_start=lookback,
                    period_end=cycle_start,
                    tokens_generated=contrib.get("total_tokens", 0),
                    requests_served=contrib.get("total_requests", 0),
                    inference_ms=contrib.get("total_inference_ms", 0),
                    uptime_ratio=contrib.get("uptime_ratio", 0.9),
                    tier=tier,
                    throughput_tps=contrib.get("throughput_tps", 0),
                )

                reward = self.calculator.calculate_reward(period, all_throughputs)

                record = SettlementRecord(
                    node_id=node_id,
                    hive_username=hive_username,
                    period_start=lookback.isoformat(),
                    period_end=cycle_start.isoformat(),
                    tokens_generated=period.tokens_generated,
                    requests_served=period.requests_served,
                    reward_hbd=reward.total_hbd,
                    tier=tier,
                )

                # 4. Submit payout if above dust threshold
                if reward.total_hbd >= MIN_PAYOUT_HBD:
                    payout_id = await self._submit_payout(
                        session, node_id, hive_username, reward
                    )
                    if payout_id:
                        record.payout_id = payout_id
                        record.settled = True
                        result.payouts_submitted += 1
                        result.total_hbd += reward.total_hbd
                    else:
                        record.error = "Payout submission failed"
                        result.payouts_failed += 1

                result.settlements.append(record)
                result.nodes_processed += 1

        result.cycle_end = datetime.now(timezone.utc).isoformat()
        self._last_settlement = cycle_start
        return result

    async def _get_current_tier(self, session: aiohttp.ClientSession) -> int:
        """Get current community tier from HivePoA."""
        headers = self._auth_headers()
        try:
            async with session.get(
                f"{self.hivepoa_url}/api/community/tier",
                headers=headers,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("tier", 1)
        except Exception:
            pass
        return 1

    async def _get_node_contributions(
        self, session: aiohttp.ClientSession, since: datetime
    ) -> list[dict]:
        """Get per-node contribution summaries since a given time."""
        headers = self._auth_headers()
        try:
            async with session.get(
                f"{self.hivepoa_url}/api/community/contributions/stats",
                headers=headers,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # The stats endpoint returns aggregate — for per-node,
                    # we need to query individual node contributions
                    # For now, return the aggregate as a single "node"
                    if data.get("activeContributors", 0) > 0:
                        return [{
                            "node_id": "aggregate",
                            "hive_username": "community",
                            "total_tokens": data.get("totalTokens", 0),
                            "total_requests": data.get("totalRequests", 0),
                            "total_inference_ms": 0,
                            "uptime_ratio": 0.95,
                            "throughput_tps": 0,
                        }]
        except Exception as e:
            logger.error(f"Failed to get contributions: {e}")
        return []

    async def _submit_payout(
        self,
        session: aiohttp.ClientSession,
        node_id: str,
        hive_username: str,
        reward: RewardCalculation,
    ) -> Optional[str]:
        """Submit a payout to HivePoA for Hive HBD transfer."""
        headers = self._auth_headers()
        payload = {
            "nodeId": node_id,
            "hiveUsername": hive_username,
            "amountHbd": f"{reward.total_hbd:.3f}",
            "reason": "spirit_bomb_inference",
            "breakdown": {
                "inference": reward.inference_reward_hbd,
                "training": reward.training_reward_hbd,
                "tierMultiplier": reward.tier_multiplier,
                "uptimeBonus": reward.uptime_bonus,
                "qualityBonus": reward.quality_bonus,
            },
        }
        try:
            async with session.post(
                f"{self.hivepoa_url}/api/compute/payouts",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    return data.get("id")
                else:
                    body = await resp.text()
                    logger.warning(f"Payout submission failed: HTTP {resp.status}: {body[:200]}")
        except Exception as e:
            logger.error(f"Payout submission error: {e}")
        return None

    def _auth_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"ApiKey {self.api_key}"
        return headers
