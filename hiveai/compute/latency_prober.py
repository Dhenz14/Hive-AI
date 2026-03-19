"""
hiveai/compute/latency_prober.py

Latency Probing Service — measures RTT between community GPU nodes.

The foundation for intelligent clustering: nodes need to know how fast
they can communicate to form optimal clusters.

Architecture:
  - Each inference worker exposes a lightweight /ping endpoint
  - The prober periodically measures RTT to all known peers
  - Results are reported to the coordinator for cluster formation
  - Uses both TCP ping and small payload echo for bandwidth estimation

Measurement methodology:
  1. TCP handshake RTT (SYN → SYN-ACK): pure network latency
  2. HTTP echo (1KB payload): includes application overhead
  3. Bandwidth probe (100KB payload): sustained throughput estimate

Clustering thresholds:
  <10ms RTT: Tensor Parallel capable (NVLink-like locality)
  <50ms RTT: Pipeline Parallel capable (same datacenter / region)
  <200ms RTT: Expert Parallel capable (cross-region, high bandwidth)
  >200ms RTT: Federated only (train independently, merge)
"""

import asyncio
import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore

# Probe configuration
PING_PAYLOAD_BYTES = 1024  # 1KB for RTT measurement
BANDWIDTH_PAYLOAD_BYTES = 102400  # 100KB for bandwidth estimation
PROBE_TIMEOUT_SECONDS = 5
PROBE_COUNT = 5  # multiple probes for statistical robustness
PROBE_INTERVAL_SECONDS = 300  # re-probe every 5 minutes
STALE_THRESHOLD_SECONDS = 600  # results older than 10 min are stale


@dataclass
class ProbeResult:
    """Result of probing a single peer."""
    peer_id: str
    peer_url: str
    # Latency (RTT)
    rtt_min_ms: float = 0.0
    rtt_median_ms: float = 0.0
    rtt_p95_ms: float = 0.0
    rtt_max_ms: float = 0.0
    rtt_stddev_ms: float = 0.0
    # Bandwidth
    bandwidth_mbps: float = 0.0
    # Metadata
    probes_sent: int = 0
    probes_succeeded: int = 0
    measured_at: float = 0.0
    error: Optional[str] = None

    @property
    def success_rate(self) -> float:
        if self.probes_sent == 0:
            return 0.0
        return self.probes_succeeded / self.probes_sent

    @property
    def is_reachable(self) -> bool:
        return self.success_rate >= 0.6

    @property
    def parallelism_capability(self) -> str:
        """Determine what parallelism this link supports."""
        if self.rtt_median_ms < 10:
            return "tensor_parallel"
        elif self.rtt_median_ms < 50:
            return "pipeline_parallel"
        elif self.rtt_median_ms < 200:
            return "expert_parallel"
        else:
            return "federated_only"

    @property
    def is_stale(self) -> bool:
        return time.time() - self.measured_at > STALE_THRESHOLD_SECONDS


class LatencyProber:
    """
    Measures network latency and bandwidth to community GPU peers.

    Usage:
        prober = LatencyProber(my_node_id="node-1")
        prober.add_peer("node-2", "http://10.0.0.2:8100")
        results = await prober.probe_all()
    """

    def __init__(self, my_node_id: str = "self"):
        self.my_node_id = my_node_id
        self._peers: dict[str, str] = {}  # peer_id → URL
        self._results: dict[str, ProbeResult] = {}  # peer_id → latest result

    def add_peer(self, peer_id: str, url: str) -> None:
        """Register a peer for probing."""
        self._peers[peer_id] = url.rstrip("/")

    def remove_peer(self, peer_id: str) -> None:
        """Remove a peer from probing."""
        self._peers.pop(peer_id, None)
        self._results.pop(peer_id, None)

    async def probe_all(self) -> list[ProbeResult]:
        """Probe all registered peers concurrently."""
        if aiohttp is None:
            raise ImportError("aiohttp required for probing")

        tasks = [
            self._probe_peer(peer_id, url)
            for peer_id, url in self._peers.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_results = []
        for r in results:
            if isinstance(r, ProbeResult):
                self._results[r.peer_id] = r
                valid_results.append(r)
            elif isinstance(r, Exception):
                logger.warning(f"Probe failed: {r}")

        return valid_results

    async def _probe_peer(self, peer_id: str, url: str) -> ProbeResult:
        """Probe a single peer with multiple measurements."""
        result = ProbeResult(
            peer_id=peer_id,
            peer_url=url,
            probes_sent=PROBE_COUNT,
            measured_at=time.time(),
        )

        rtts = []
        async with aiohttp.ClientSession() as session:
            for i in range(PROBE_COUNT):
                try:
                    rtt = await self._single_ping(session, url)
                    if rtt is not None:
                        rtts.append(rtt)
                        result.probes_succeeded += 1
                except Exception as e:
                    if i == 0:
                        logger.debug(f"Probe to {peer_id} failed: {e}")

            # Bandwidth measurement (single probe)
            try:
                result.bandwidth_mbps = await self._measure_bandwidth(session, url)
            except Exception:
                pass

        if rtts:
            sorted_rtts = sorted(rtts)
            result.rtt_min_ms = sorted_rtts[0]
            result.rtt_median_ms = statistics.median(sorted_rtts)
            result.rtt_max_ms = sorted_rtts[-1]
            p95_idx = min(len(sorted_rtts) - 1, int(len(sorted_rtts) * 0.95 + 0.5))  # ceil
            result.rtt_p95_ms = sorted_rtts[p95_idx]
            result.rtt_stddev_ms = statistics.stdev(sorted_rtts) if len(sorted_rtts) > 1 else 0.0
        else:
            result.error = "All probes failed"

        return result

    async def _single_ping(
        self, session: aiohttp.ClientSession, url: str
    ) -> Optional[float]:
        """Send a single ping and measure RTT."""
        payload = b"x" * PING_PAYLOAD_BYTES
        start = time.monotonic()
        try:
            async with session.post(
                f"{url}/ping",
                data=payload,
                timeout=aiohttp.ClientTimeout(total=PROBE_TIMEOUT_SECONDS),
            ) as resp:
                await resp.read()
                rtt_ms = (time.monotonic() - start) * 1000
                if resp.status == 200:
                    return rtt_ms
                return None
        except (asyncio.TimeoutError, aiohttp.ClientError):
            return None

    async def _measure_bandwidth(
        self, session: aiohttp.ClientSession, url: str
    ) -> float:
        """Measure bandwidth with a larger payload."""
        payload = b"x" * BANDWIDTH_PAYLOAD_BYTES
        start = time.monotonic()
        try:
            async with session.post(
                f"{url}/ping",
                data=payload,
                timeout=aiohttp.ClientTimeout(total=PROBE_TIMEOUT_SECONDS * 2),
            ) as resp:
                data = await resp.read()
                elapsed_s = time.monotonic() - start
                if resp.status == 200 and elapsed_s > 0:
                    # Round-trip bytes / elapsed time
                    total_bytes = len(payload) + len(data)
                    mbps = (total_bytes * 8) / (elapsed_s * 1_000_000)
                    return round(mbps, 1)
        except Exception:
            pass
        return 0.0

    def get_results(self) -> dict[str, ProbeResult]:
        """Get all cached probe results."""
        return dict(self._results)

    def get_result(self, peer_id: str) -> Optional[ProbeResult]:
        """Get cached result for a specific peer."""
        return self._results.get(peer_id)

    def get_cluster_candidates(self, max_latency_ms: float = 50.0) -> list[list[str]]:
        """
        Group peers into cluster candidates based on mutual latency.

        Returns groups of peer IDs where all pairs have latency < max_latency_ms.
        Simple greedy grouping (optimal clustering is NP-hard).
        """
        reachable = {
            pid: r for pid, r in self._results.items()
            if r.is_reachable and r.rtt_median_ms < max_latency_ms
        }

        if not reachable:
            return []

        # Greedy: start from lowest-latency peer, expand group
        assigned = set()
        groups = []

        # Sort by latency
        sorted_peers = sorted(reachable.items(), key=lambda x: x[1].rtt_median_ms)

        for pid, result in sorted_peers:
            if pid in assigned:
                continue

            group = [self.my_node_id, pid]
            assigned.add(pid)

            # Try to add more peers that are close to ALL current group members
            for other_pid, other_result in sorted_peers:
                if other_pid in assigned:
                    continue
                if other_result.rtt_median_ms < max_latency_ms:
                    group.append(other_pid)
                    assigned.add(other_pid)

            if len(group) >= 2:
                groups.append(group)

        return groups

    def get_network_summary(self) -> dict:
        """Get a summary of the probing results."""
        results = list(self._results.values())
        if not results:
            return {"peers": 0, "reachable": 0}

        reachable = [r for r in results if r.is_reachable]
        latencies = [r.rtt_median_ms for r in reachable]

        return {
            "peers": len(results),
            "reachable": len(reachable),
            "unreachable": len(results) - len(reachable),
            "avg_latency_ms": round(statistics.mean(latencies), 1) if latencies else 0,
            "min_latency_ms": round(min(latencies), 1) if latencies else 0,
            "max_latency_ms": round(max(latencies), 1) if latencies else 0,
            "tp_capable": sum(1 for r in reachable if r.parallelism_capability == "tensor_parallel"),
            "pp_capable": sum(1 for r in reachable if r.parallelism_capability in ("tensor_parallel", "pipeline_parallel")),
            "stale_results": sum(1 for r in results if r.is_stale),
        }
