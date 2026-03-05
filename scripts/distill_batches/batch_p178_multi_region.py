"""Multi-region architecture — active-active setup, conflict resolution, geo-routing, data replication, failover patterns, latency-based routing."""

PAIRS = [
    (
        "multi-region/active-active",
        "Implement an active-active multi-region architecture in Python with request routing, region-aware data access, health-based failover, and cross-region replication coordination.",
        '''Active-active multi-region architecture with routing and failover:

```python
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

import httpx

logger = logging.getLogger("multiregion.active_active")


class RegionStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"      # graceful shutdown


@dataclass
class Region:
    name: str                    # e.g. "us-east-1", "eu-west-1"
    endpoint: str                # base URL for this region
    status: RegionStatus = RegionStatus.HEALTHY
    latency_ms: float = 0       # last measured latency
    error_rate: float = 0.0     # rolling error rate (0.0-1.0)
    weight: int = 100           # traffic weight (0-100)
    is_primary: bool = False    # primary for write operations
    capabilities: set[str] = field(default_factory=lambda: {"read", "write"})
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoutingDecision:
    region: Region
    fallback_regions: list[Region]
    reason: str


class RegionRegistry:
    """Manages region health, latency, and availability.

    Monitors each region with periodic health checks and
    maintains a real-time view of the multi-region topology.
    """

    def __init__(
        self,
        regions: list[Region],
        health_check_interval: float = 10.0,
        error_rate_window: int = 100,
    ) -> None:
        self._regions = {r.name: r for r in regions}
        self._health_interval = health_check_interval
        self._error_window = error_rate_window
        self._request_outcomes: dict[str, list[bool]] = {
            r.name: [] for r in regions
        }
        self._running = False

    @property
    def healthy_regions(self) -> list[Region]:
        return [
            r for r in self._regions.values()
            if r.status in (RegionStatus.HEALTHY, RegionStatus.DEGRADED)
        ]

    def get_region(self, name: str) -> Region | None:
        return self._regions.get(name)

    def record_outcome(self, region_name: str, success: bool, latency_ms: float) -> None:
        """Record a request outcome for error rate tracking."""
        region = self._regions.get(region_name)
        if not region:
            return

        outcomes = self._request_outcomes[region_name]
        outcomes.append(success)
        if len(outcomes) > self._error_window:
            outcomes.pop(0)

        # Update rolling error rate
        if outcomes:
            region.error_rate = 1.0 - (sum(outcomes) / len(outcomes))

        # Update latency (exponential moving average)
        alpha = 0.3
        region.latency_ms = alpha * latency_ms + (1 - alpha) * region.latency_ms

        # Auto-degrade if error rate is high
        if region.error_rate > 0.5:
            region.status = RegionStatus.UNHEALTHY
        elif region.error_rate > 0.1:
            region.status = RegionStatus.DEGRADED

    async def start_health_checks(self) -> None:
        self._running = True
        while self._running:
            await self._check_all_regions()
            await asyncio.sleep(self._health_interval)

    async def _check_all_regions(self) -> None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            tasks = [
                self._check_region(client, region)
                for region in self._regions.values()
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_region(self, client: httpx.AsyncClient, region: Region) -> None:
        start = time.monotonic()
        try:
            resp = await client.get(f"{region.endpoint}/health")
            latency = (time.monotonic() - start) * 1000

            if resp.status_code == 200:
                self.record_outcome(region.name, True, latency)
            else:
                self.record_outcome(region.name, False, latency)
        except Exception:
            latency = (time.monotonic() - start) * 1000
            self.record_outcome(region.name, False, latency)


class MultiRegionRouter:
    """Routes requests to the optimal region based on multiple factors.

    Routing strategies:
    - Latency-based: pick the region with lowest latency
    - Geo-proximity: route to the nearest region to the client
    - Weighted: distribute traffic by configured weights
    - Failover: fall back to healthy regions when primary fails
    """

    def __init__(self, registry: RegionRegistry) -> None:
        self._registry = registry

    def route_read(
        self,
        client_region: str | None = None,
        preferred_region: str | None = None,
    ) -> RoutingDecision:
        """Route a read request to the best region."""
        healthy = self._registry.healthy_regions
        if not healthy:
            raise RuntimeError("No healthy regions available")

        # Prefer client\'s local region
        if client_region:
            local = [r for r in healthy if r.name == client_region]
            if local:
                fallbacks = [r for r in healthy if r.name != client_region]
                return RoutingDecision(
                    region=local[0],
                    fallback_regions=sorted(fallbacks, key=lambda r: r.latency_ms),
                    reason="client_local_region",
                )

        # Fall back to lowest latency
        by_latency = sorted(healthy, key=lambda r: r.latency_ms)
        return RoutingDecision(
            region=by_latency[0],
            fallback_regions=by_latency[1:],
            reason="lowest_latency",
        )

    def route_write(
        self,
        client_region: str | None = None,
    ) -> RoutingDecision:
        """Route a write request — prefers primary region.

        In active-active, writes can go to any region but
        may need conflict resolution for concurrent writes.
        """
        healthy = self._registry.healthy_regions
        writable = [r for r in healthy if "write" in r.capabilities]

        if not writable:
            raise RuntimeError("No writable regions available")

        # Prefer primary region for writes (reduces conflicts)
        primary = [r for r in writable if r.is_primary]
        if primary:
            fallbacks = [r for r in writable if not r.is_primary]
            return RoutingDecision(
                region=primary[0],
                fallback_regions=fallbacks,
                reason="primary_region",
            )

        # Prefer local region for lower latency
        if client_region:
            local = [r for r in writable if r.name == client_region]
            if local:
                fallbacks = [r for r in writable if r.name != client_region]
                return RoutingDecision(
                    region=local[0],
                    fallback_regions=fallbacks,
                    reason="local_write",
                )

        # Weighted random selection
        return self._weighted_pick(writable)

    def _weighted_pick(self, regions: list[Region]) -> RoutingDecision:
        total = sum(r.weight for r in regions)
        pick = random.uniform(0, total)
        cumulative = 0
        for region in regions:
            cumulative += region.weight
            if pick <= cumulative:
                fallbacks = [r for r in regions if r.name != region.name]
                return RoutingDecision(
                    region=region,
                    fallback_regions=fallbacks,
                    reason="weighted_random",
                )
        return RoutingDecision(
            region=regions[0],
            fallback_regions=regions[1:],
            reason="weighted_fallback",
        )


class MultiRegionClient:
    """HTTP client with automatic region routing and failover.

    Tries the primary region first, then falls back to
    secondary regions on failure.
    """

    def __init__(
        self,
        registry: RegionRegistry,
        router: MultiRegionRouter,
        max_retries: int = 2,
    ) -> None:
        self._registry = registry
        self._router = router
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(timeout=10.0)

    async def read(
        self,
        path: str,
        client_region: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        decision = self._router.route_read(client_region=client_region)
        return await self._execute_with_failover(
            decision, "GET", path, **kwargs,
        )

    async def write(
        self,
        path: str,
        data: Any = None,
        client_region: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        decision = self._router.route_write(client_region=client_region)
        return await self._execute_with_failover(
            decision, "POST", path, json=data, **kwargs,
        )

    async def _execute_with_failover(
        self,
        decision: RoutingDecision,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        all_regions = [decision.region] + decision.fallback_regions

        for i, region in enumerate(all_regions[:self._max_retries + 1]):
            start = time.monotonic()
            try:
                url = f"{region.endpoint}{path}"
                response = await self._client.request(method, url, **kwargs)
                latency = (time.monotonic() - start) * 1000
                self._registry.record_outcome(region.name, True, latency)

                if response.status_code < 500:
                    return response

                # 5xx — try next region
                self._registry.record_outcome(region.name, False, latency)
                logger.warning(f"Region {region.name} returned {response.status_code}, trying next")

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                latency = (time.monotonic() - start) * 1000
                self._registry.record_outcome(region.name, False, latency)
                logger.warning(f"Region {region.name} failed: {e}")

        raise RuntimeError(f"All regions failed for {method} {path}")

    async def close(self) -> None:
        await self._client.aclose()


# ── Usage ─────────────────────────────────────────────────────────

async def main() -> None:
    regions = [
        Region(name="us-east-1", endpoint="https://api-east.example.com", is_primary=True, weight=40),
        Region(name="us-west-2", endpoint="https://api-west.example.com", weight=30),
        Region(name="eu-west-1", endpoint="https://api-eu.example.com", weight=30),
    ]

    registry = RegionRegistry(regions)
    router = MultiRegionRouter(registry)
    client = MultiRegionClient(registry, router)

    # Start health monitoring
    asyncio.create_task(registry.start_health_checks())

    # Read routes to nearest healthy region
    response = await client.read("/api/v1/products/123", client_region="us-east-1")

    # Write routes to primary, falls back on failure
    response = await client.write(
        "/api/v1/orders",
        data={"item": "widget", "qty": 5},
        client_region="eu-west-1",
    )

    await client.close()
```

Multi-region routing strategies:

| Strategy | Reads | Writes | Conflict risk |
|---|---|---|---|
| Primary-secondary | Any region | Primary only | None (single writer) |
| Active-active | Any region | Any region | High (needs resolution) |
| Leader-follower | Follower preferred | Leader only | None |
| Geo-partitioned | Local region | Local region | None (data is partitioned) |

Key patterns:
- **Latency-aware routing**: EMA tracks per-region latency for optimal picks
- **Automatic failover**: Tries fallback regions on failure or 5xx
- **Health-based degradation**: High error rates auto-mark regions unhealthy
- **Weighted distribution**: Control traffic split across regions
- **Read/write separation**: Reads go anywhere, writes prefer primary
'''
    ),
    (
        "multi-region/conflict-resolution",
        "Implement conflict resolution strategies for multi-region active-active databases including last-writer-wins, vector clocks, and custom merge functions with Python.",
        '''Conflict resolution for multi-region active-active databases:

```python
from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ConflictType(str, Enum):
    NO_CONFLICT = "no_conflict"
    UPDATE_UPDATE = "update_update"    # both regions updated same record
    UPDATE_DELETE = "update_delete"    # one updated, one deleted
    INSERT_INSERT = "insert_insert"    # both inserted same key


@dataclass
class VersionedRecord:
    """A database record with multi-region versioning metadata."""
    key: str
    value: dict[str, Any]
    region: str
    version: int
    timestamp: float            # wall clock (for LWW)
    vector_clock: dict[str, int] = field(default_factory=dict)
    checksum: str = ""
    is_deleted: bool = False
    merge_history: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.checksum:
            self.checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        content = json.dumps(self.value, sort_keys=True, default=str)
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def increment_clock(self, region: str) -> None:
        self.vector_clock[region] = self.vector_clock.get(region, 0) + 1

    def merge_clocks(self, other_clock: dict[str, int]) -> None:
        all_regions = set(self.vector_clock) | set(other_clock)
        self.vector_clock = {
            r: max(self.vector_clock.get(r, 0), other_clock.get(r, 0))
            for r in all_regions
        }


def detect_conflict(local: VersionedRecord, remote: VersionedRecord) -> ConflictType:
    """Detect the type of conflict between two versions of a record."""
    if local.is_deleted and not remote.is_deleted:
        return ConflictType.UPDATE_DELETE
    if not local.is_deleted and remote.is_deleted:
        return ConflictType.UPDATE_DELETE

    # Check vector clocks for causality
    local_dominates = all(
        local.vector_clock.get(r, 0) >= remote.vector_clock.get(r, 0)
        for r in set(local.vector_clock) | set(remote.vector_clock)
    )
    remote_dominates = all(
        remote.vector_clock.get(r, 0) >= local.vector_clock.get(r, 0)
        for r in set(local.vector_clock) | set(remote.vector_clock)
    )

    if local_dominates and not remote_dominates:
        return ConflictType.NO_CONFLICT  # local is newer
    if remote_dominates and not local_dominates:
        return ConflictType.NO_CONFLICT  # remote is newer

    # Concurrent updates — true conflict
    return ConflictType.UPDATE_UPDATE


# ── Resolution strategies ─────────────────────────────────────────

class ConflictResolver(ABC):
    @abstractmethod
    def resolve(
        self, local: VersionedRecord, remote: VersionedRecord,
    ) -> VersionedRecord:
        ...


class LastWriterWinsResolver(ConflictResolver):
    """Resolve conflicts by picking the record with the latest timestamp.

    Simple and deterministic but can lose data. Best for
    non-critical data where latest value is acceptable.
    """

    def __init__(self, tiebreaker: str = "region_name") -> None:
        self._tiebreaker = tiebreaker

    def resolve(
        self, local: VersionedRecord, remote: VersionedRecord,
    ) -> VersionedRecord:
        if remote.timestamp > local.timestamp:
            winner = remote
        elif local.timestamp > remote.timestamp:
            winner = local
        else:
            # Tiebreak by region name (deterministic)
            winner = remote if remote.region > local.region else local

        winner.merge_clocks(
            local.vector_clock if winner is remote else remote.vector_clock
        )
        winner.merge_history.append(
            f"lww:{local.region}={local.version},"
            f"{remote.region}={remote.version}"
        )
        return winner


class FieldLevelMergeResolver(ConflictResolver):
    """Merge conflicts at the field level.

    For each field, pick the value from the record that
    most recently modified that field. Requires per-field
    timestamps.
    """

    def __init__(self, field_timestamps_key: str = "_field_timestamps") -> None:
        self._ts_key = field_timestamps_key

    def resolve(
        self, local: VersionedRecord, remote: VersionedRecord,
    ) -> VersionedRecord:
        local_ts = local.value.get(self._ts_key, {})
        remote_ts = remote.value.get(self._ts_key, {})

        merged_value: dict[str, Any] = {}
        merged_ts: dict[str, float] = {}
        all_fields = set(local.value) | set(remote.value)
        all_fields.discard(self._ts_key)

        for field_name in all_fields:
            lt = local_ts.get(field_name, 0)
            rt = remote_ts.get(field_name, 0)

            if rt > lt:
                merged_value[field_name] = remote.value.get(field_name)
                merged_ts[field_name] = rt
            elif lt > rt:
                merged_value[field_name] = local.value.get(field_name)
                merged_ts[field_name] = lt
            else:
                # Same timestamp — prefer the one with higher region name
                if remote.region > local.region:
                    merged_value[field_name] = remote.value.get(field_name)
                else:
                    merged_value[field_name] = local.value.get(field_name)
                merged_ts[field_name] = max(lt, rt)

        merged_value[self._ts_key] = merged_ts

        result = VersionedRecord(
            key=local.key,
            value=merged_value,
            region=local.region,
            version=max(local.version, remote.version) + 1,
            timestamp=time.time(),
            vector_clock={},
        )
        result.merge_clocks(local.vector_clock)
        result.merge_clocks(remote.vector_clock)
        result.increment_clock(local.region)
        result.merge_history = [
            *local.merge_history,
            f"field_merge:{local.region}={local.version},{remote.region}={remote.version}",
        ]
        return result


class CustomMergeResolver(ConflictResolver):
    """Applies domain-specific merge logic per record type.

    Register merge functions for different entity types.
    Falls back to LWW for unregistered types.
    """

    def __init__(self) -> None:
        self._merge_fns: dict[str, Callable] = {}
        self._fallback = LastWriterWinsResolver()

    def register(
        self,
        entity_type: str,
        merge_fn: Callable[[dict, dict], dict],
    ) -> None:
        self._merge_fns[entity_type] = merge_fn

    def resolve(
        self, local: VersionedRecord, remote: VersionedRecord,
    ) -> VersionedRecord:
        entity_type = local.value.get("_type", "")
        merge_fn = self._merge_fns.get(entity_type)

        if merge_fn is None:
            return self._fallback.resolve(local, remote)

        merged_value = merge_fn(local.value, remote.value)

        result = VersionedRecord(
            key=local.key,
            value=merged_value,
            region=local.region,
            version=max(local.version, remote.version) + 1,
            timestamp=time.time(),
        )
        result.merge_clocks(local.vector_clock)
        result.merge_clocks(remote.vector_clock)
        result.increment_clock(local.region)
        return result


# ── Replication coordinator ───────────────────────────────────────

class ReplicationCoordinator:
    """Coordinates data replication between regions with conflict resolution.

    Processes incoming replication events, detects conflicts,
    applies resolution strategy, and tracks replication lag.
    """

    def __init__(
        self,
        local_region: str,
        resolver: ConflictResolver,
    ) -> None:
        self.local_region = local_region
        self._resolver = resolver
        self._store: dict[str, VersionedRecord] = {}
        self._replication_lag: dict[str, float] = {}
        self._conflict_count: int = 0
        self._resolved_count: int = 0

    def local_write(self, key: str, value: dict[str, Any]) -> VersionedRecord:
        """Write a record locally (will be replicated to other regions)."""
        existing = self._store.get(key)
        version = (existing.version + 1) if existing else 1
        clock = dict(existing.vector_clock) if existing else {}

        record = VersionedRecord(
            key=key,
            value=value,
            region=self.local_region,
            version=version,
            timestamp=time.time(),
            vector_clock=clock,
        )
        record.increment_clock(self.local_region)
        self._store[key] = record
        return record

    def receive_replication(self, remote_record: VersionedRecord) -> VersionedRecord:
        """Process an incoming replicated record from another region."""
        local_record = self._store.get(remote_record.key)

        if local_record is None:
            # No local version — accept remote
            self._store[remote_record.key] = remote_record
            return remote_record

        conflict = detect_conflict(local_record, remote_record)

        if conflict == ConflictType.NO_CONFLICT:
            # Check if remote is strictly newer
            remote_newer = all(
                remote_record.vector_clock.get(r, 0) >= local_record.vector_clock.get(r, 0)
                for r in set(remote_record.vector_clock) | set(local_record.vector_clock)
            )
            if remote_newer:
                self._store[remote_record.key] = remote_record
                return remote_record
            return local_record

        # Real conflict — resolve
        self._conflict_count += 1
        resolved = self._resolver.resolve(local_record, remote_record)
        self._store[resolved.key] = resolved
        self._resolved_count += 1

        logger.info(
            f"Resolved {conflict.value} conflict on key '{resolved.key}' "
            f"between {local_record.region}(v{local_record.version}) "
            f"and {remote_record.region}(v{remote_record.version})"
        )

        return resolved

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_records": len(self._store),
            "conflicts_detected": self._conflict_count,
            "conflicts_resolved": self._resolved_count,
            "replication_lag": dict(self._replication_lag),
        }


# ── Domain-specific merge example ─────────────────────────────────

def merge_shopping_cart(local: dict, remote: dict) -> dict:
    """Custom merge for shopping cart: union of items, max quantities."""
    local_items = {item["sku"]: item for item in local.get("items", [])}
    remote_items = {item["sku"]: item for item in remote.get("items", [])}

    merged_items = {}
    for sku in set(local_items) | set(remote_items):
        l_item = local_items.get(sku, {"sku": sku, "qty": 0})
        r_item = remote_items.get(sku, {"sku": sku, "qty": 0})
        merged_items[sku] = {
            "sku": sku,
            "qty": max(l_item["qty"], r_item["qty"]),
            "name": l_item.get("name") or r_item.get("name", ""),
        }

    return {
        "_type": "shopping_cart",
        "items": list(merged_items.values()),
        "updated_at": max(local.get("updated_at", 0), remote.get("updated_at", 0)),
    }
```

Conflict resolution strategies comparison:

| Strategy | Data loss risk | Complexity | Best for |
|---|---|---|---|
| Last Writer Wins (LWW) | High | Low | Session data, caches |
| Field-level merge | Low | Medium | User profiles, settings |
| Custom merge | None | High | Shopping carts, counters |
| CRDTs | None | Medium | Counters, sets, registers |
| Manual resolution | None | Very high | Financial transactions |

Key design decisions:
- **Vector clocks** detect true concurrency vs causal ordering
- **Field-level merge** minimizes data loss by merging per-field
- **Domain-specific merge** applies business rules (e.g., max quantity for carts)
- **Merge history** provides audit trail of conflict resolutions
- **Checksums** detect silent data corruption during replication
'''
    ),
    (
        "multi-region/geo-routing",
        "Implement geo-routing for multi-region APIs with DNS-based routing, latency probing, client IP geolocation, and automatic failover using Python.",
        '''Geo-routing with DNS, latency probing, IP geolocation, and failover:

```python
from __future__ import annotations

import asyncio
import ipaddress
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("multiregion.georouting")


@dataclass
class GeoLocation:
    latitude: float
    longitude: float
    country_code: str = ""
    region: str = ""
    city: str = ""
    continent: str = ""


@dataclass
class RegionEndpoint:
    name: str
    endpoint: str
    location: GeoLocation
    healthy: bool = True
    latency_ms: float = 0
    weight: int = 100
    active_connections: int = 0
    max_connections: int = 10_000


# ── IP geolocation ────────────────────────────────────────────────

class GeoIPResolver:
    """Resolve client IP addresses to geographic locations.

    In production, use MaxMind GeoIP2 or a cloud provider\'s
    geolocation service. This implementation shows the interface
    with a simplified in-memory database.
    """

    # Simplified CIDR -> region mapping (production: use GeoIP2)
    CIDR_MAP: list[tuple[str, GeoLocation]] = [
        ("0.0.0.0/0", GeoLocation(37.7749, -122.4194, "US", "us-west", "San Francisco", "NA")),
    ]

    def __init__(self) -> None:
        self._cache: dict[str, GeoLocation] = {}

    def resolve(self, ip: str) -> GeoLocation:
        """Resolve an IP address to a geographic location."""
        if ip in self._cache:
            return self._cache[ip]

        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return GeoLocation(0, 0)

        # Check CIDR ranges
        for cidr, location in self.CIDR_MAP:
            network = ipaddress.ip_network(cidr, strict=False)
            if addr in network:
                self._cache[ip] = location
                return location

        return GeoLocation(0, 0)

    async def resolve_via_api(self, ip: str) -> GeoLocation:
        """Resolve using an external geolocation API."""
        if ip in self._cache:
            return self._cache[ip]

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                # Example: ipinfo.io, ip-api.com, or MaxMind web service
                resp = await client.get(f"https://ipinfo.io/{ip}/json")
                data = resp.json()
                loc = data.get("loc", "0,0").split(",")
                location = GeoLocation(
                    latitude=float(loc[0]),
                    longitude=float(loc[1]),
                    country_code=data.get("country", ""),
                    region=data.get("region", ""),
                    city=data.get("city", ""),
                )
                self._cache[ip] = location
                return location
        except Exception:
            return GeoLocation(0, 0)


# ── Geographic distance calculation ───────────────────────────────

def haversine_distance(loc1: GeoLocation, loc2: GeoLocation) -> float:
    """Calculate distance between two points on Earth in kilometers."""
    R = 6371  # Earth radius in km

    lat1 = math.radians(loc1.latitude)
    lat2 = math.radians(loc2.latitude)
    dlat = math.radians(loc2.latitude - loc1.latitude)
    dlon = math.radians(loc2.longitude - loc1.longitude)

    a = (math.sin(dlat / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# ── Geo-aware router ──────────────────────────────────────────────

class GeoRouter:
    """Routes requests to the geographically optimal region.

    Combines geographic proximity with health status, latency
    measurements, and capacity constraints.
    """

    def __init__(
        self,
        endpoints: list[RegionEndpoint],
        geo_resolver: GeoIPResolver,
        latency_weight: float = 0.4,
        distance_weight: float = 0.4,
        load_weight: float = 0.2,
    ) -> None:
        self._endpoints = {e.name: e for e in endpoints}
        self._geo = geo_resolver
        self._w_latency = latency_weight
        self._w_distance = distance_weight
        self._w_load = load_weight

    def route(
        self,
        client_ip: str,
        prefer_region: str | None = None,
    ) -> list[RegionEndpoint]:
        """Return endpoints sorted by routing score (best first).

        Score = weighted combination of:
        - Geographic distance (lower is better)
        - Measured latency (lower is better)
        - Current load (lower is better)
        """
        client_location = self._geo.resolve(client_ip)
        healthy = [e for e in self._endpoints.values() if e.healthy]

        if not healthy:
            raise RuntimeError("No healthy endpoints available")

        # If preferred region is available and healthy, put it first
        if prefer_region:
            preferred = [e for e in healthy if e.name == prefer_region]
            others = [e for e in healthy if e.name != prefer_region]
            if preferred:
                return preferred + self._score_and_sort(others, client_location)

        return self._score_and_sort(healthy, client_location)

    def _score_and_sort(
        self,
        endpoints: list[RegionEndpoint],
        client_location: GeoLocation,
    ) -> list[RegionEndpoint]:
        """Score each endpoint and sort by ascending score (lower = better)."""
        if not endpoints:
            return []

        # Calculate raw values
        distances = [haversine_distance(client_location, e.location) for e in endpoints]
        latencies = [e.latency_ms for e in endpoints]
        loads = [e.active_connections / max(e.max_connections, 1) for e in endpoints]

        # Normalize to 0-1 range
        max_dist = max(distances) or 1
        max_lat = max(latencies) or 1

        scored = []
        for i, endpoint in enumerate(endpoints):
            score = (
                self._w_distance * (distances[i] / max_dist) +
                self._w_latency * (latencies[i] / max_lat) +
                self._w_load * loads[i]
            )
            scored.append((score, endpoint))

        scored.sort(key=lambda x: x[0])
        return [endpoint for _, endpoint in scored]

    async def update_latencies(self) -> None:
        """Probe all endpoints to measure current latency."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            for endpoint in self._endpoints.values():
                start = time.monotonic()
                try:
                    await client.get(f"{endpoint.endpoint}/ping")
                    endpoint.latency_ms = (time.monotonic() - start) * 1000
                    endpoint.healthy = True
                except Exception:
                    endpoint.latency_ms = 99999
                    endpoint.healthy = False


# ── DNS-based geo routing configuration ───────────────────────────

@dataclass
class DNSRecord:
    name: str
    record_type: str      # A, AAAA, CNAME
    value: str
    ttl: int = 60
    weight: int = 100
    health_check_id: str = ""
    region: str = ""
    failover: str = ""     # "PRIMARY" or "SECONDARY"
    geolocation: dict[str, str] = field(default_factory=dict)


def generate_route53_config(
    domain: str,
    endpoints: list[RegionEndpoint],
) -> list[DNSRecord]:
    """Generate AWS Route53-style DNS configuration for geo routing.

    This produces the configuration that would be applied via
    AWS SDK or Terraform to set up geographic DNS routing.
    """
    records: list[DNSRecord] = []

    # Continent-level routing
    continent_map = {
        "NA": "us-east-1",
        "EU": "eu-west-1",
        "AS": "ap-northeast-1",
        "SA": "us-east-1",       # fallback
        "AF": "eu-west-1",       # fallback
        "OC": "ap-southeast-2",
    }

    for endpoint in endpoints:
        # Geolocation-based record
        records.append(DNSRecord(
            name=f"api.{domain}",
            record_type="A",
            value=endpoint.endpoint.replace("https://", ""),
            ttl=60,
            weight=endpoint.weight,
            health_check_id=f"hc-{endpoint.name}",
            region=endpoint.name,
            geolocation={
                "continent": endpoint.location.continent,
            },
        ))

    # Default fallback (catches unmatched geolocations)
    primary = next((e for e in endpoints if e.name.startswith("us-")), endpoints[0])
    records.append(DNSRecord(
        name=f"api.{domain}",
        record_type="A",
        value=primary.endpoint.replace("https://", ""),
        ttl=60,
        health_check_id=f"hc-{primary.name}",
        geolocation={"country": "*"},
    ))

    return records


# ── FastAPI middleware for geo routing ─────────────────────────────

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class GeoRoutingMiddleware(BaseHTTPMiddleware):
    """Middleware that adds geo-routing headers to responses."""

    def __init__(self, app: Any, geo_resolver: GeoIPResolver, local_region: str) -> None:
        super().__init__(app)
        self._geo = geo_resolver
        self._local_region = local_region

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        # Get client IP
        client_ip = request.headers.get(
            "x-forwarded-for",
            request.client.host if request.client else "0.0.0.0",
        ).split(",")[0].strip()

        # Resolve location
        location = self._geo.resolve(client_ip)

        # Add geo info to request state
        request.state.client_location = location
        request.state.client_ip = client_ip

        response = await call_next(request)

        # Add routing headers
        response.headers["X-Served-By-Region"] = self._local_region
        response.headers["X-Client-Country"] = location.country_code
        response.headers["X-Client-Continent"] = location.continent

        return response
```

Geo-routing decision factors:

| Factor | Weight | Source | Update frequency |
|---|---|---|---|
| Geographic distance | 40% | Client IP geolocation | Per request |
| Measured latency | 40% | Active probing | Every 10-30s |
| Current load | 20% | Connection counter | Real-time |
| Health status | Binary | Health check | Every 5-10s |

Key patterns:
- **Haversine formula**: Calculate great-circle distance between coordinates
- **Multi-factor scoring**: Combine distance, latency, and load with weights
- **DNS-level routing**: Route53/CloudFlare for initial request routing
- **Application-level routing**: Fine-grained control per request
- **IP geolocation caching**: Avoid repeated lookups for the same IP
- **Failover ordering**: Score-sorted fallback list for automatic recovery
'''
    ),
    (
        "multi-region/data-replication",
        "Implement data replication strategies for multi-region deployments including async replication with change data capture (CDC), conflict-free replication using CRDTs, and replication lag monitoring.",
        '''Multi-region data replication with CDC, CRDTs, and lag monitoring:

```python
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncIterator, Callable, Coroutine

logger = logging.getLogger("multiregion.replication")


class ChangeType(str, Enum):
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"


@dataclass
class ChangeEvent:
    """A single change data capture event."""
    event_id: str
    table: str
    key: str
    change_type: ChangeType
    before: dict[str, Any] | None     # previous state (for updates/deletes)
    after: dict[str, Any] | None      # new state (for inserts/updates)
    timestamp: float                   # source region wall clock
    source_region: str
    sequence_number: int               # monotonically increasing per source
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReplicationPosition:
    """Tracks the replication position for a source region."""
    source_region: str
    last_sequence: int = 0
    last_event_id: str = ""
    last_timestamp: float = 0
    lag_ms: float = 0


class ChangeDataCapture:
    """Change data capture producer for a local database.

    Captures INSERT/UPDATE/DELETE operations and produces
    ChangeEvents for cross-region replication.

    In production, use Debezium or database-native CDC
    (PostgreSQL logical replication, MySQL binlog).
    """

    def __init__(self, region: str) -> None:
        self.region = region
        self._sequence: int = 0
        self._subscribers: list[asyncio.Queue[ChangeEvent]] = []
        self._buffer: deque[ChangeEvent] = deque(maxlen=10_000)

    def subscribe(self) -> asyncio.Queue[ChangeEvent]:
        queue: asyncio.Queue[ChangeEvent] = asyncio.Queue(maxsize=1000)
        self._subscribers.append(queue)
        return queue

    async def capture_insert(self, table: str, key: str, data: dict[str, Any]) -> ChangeEvent:
        return await self._emit(ChangeType.INSERT, table, key, None, data)

    async def capture_update(
        self, table: str, key: str,
        before: dict[str, Any], after: dict[str, Any],
    ) -> ChangeEvent:
        return await self._emit(ChangeType.UPDATE, table, key, before, after)

    async def capture_delete(self, table: str, key: str, before: dict[str, Any]) -> ChangeEvent:
        return await self._emit(ChangeType.DELETE, table, key, before, None)

    async def _emit(
        self,
        change_type: ChangeType,
        table: str,
        key: str,
        before: dict | None,
        after: dict | None,
    ) -> ChangeEvent:
        self._sequence += 1
        event = ChangeEvent(
            event_id=f"cdc_{uuid.uuid4().hex[:12]}",
            table=table,
            key=key,
            change_type=change_type,
            before=before,
            after=after,
            timestamp=time.time(),
            source_region=self.region,
            sequence_number=self._sequence,
        )
        self._buffer.append(event)

        for subscriber in self._subscribers:
            try:
                subscriber.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"CDC subscriber queue full, dropping event {event.event_id}")

        return event

    def get_events_since(self, sequence: int) -> list[ChangeEvent]:
        """Get buffered events since a sequence number (for catch-up)."""
        return [e for e in self._buffer if e.sequence_number > sequence]


# ── Replication consumer ──────────────────────────────────────────

class ReplicationConsumer:
    """Consumes change events from remote regions and applies them locally.

    Handles:
    - Ordered application of changes per source
    - Idempotency (skip already-applied events)
    - Lag tracking
    - Error handling with retry
    """

    def __init__(
        self,
        local_region: str,
        apply_fn: Callable[[ChangeEvent], Coroutine[Any, Any, bool]],
    ) -> None:
        self.local_region = local_region
        self._apply_fn = apply_fn
        self._positions: dict[str, ReplicationPosition] = {}
        self._running = False
        self._error_count: int = 0

    def get_position(self, source_region: str) -> ReplicationPosition:
        if source_region not in self._positions:
            self._positions[source_region] = ReplicationPosition(
                source_region=source_region,
            )
        return self._positions[source_region]

    async def consume(self, event_source: asyncio.Queue[ChangeEvent]) -> None:
        """Main consumption loop."""
        self._running = True
        while self._running:
            try:
                event = await asyncio.wait_for(event_source.get(), timeout=5.0)
                await self._process_event(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self._error_count += 1
                logger.error(f"Replication consumer error: {e}")
                await asyncio.sleep(1)

    async def _process_event(self, event: ChangeEvent) -> None:
        # Skip events from our own region
        if event.source_region == self.local_region:
            return

        position = self.get_position(event.source_region)

        # Idempotency: skip if already processed
        if event.sequence_number <= position.last_sequence:
            return

        # Detect gaps (missed events)
        expected_seq = position.last_sequence + 1
        if event.sequence_number > expected_seq:
            logger.warning(
                f"Gap detected from {event.source_region}: "
                f"expected seq {expected_seq}, got {event.sequence_number}"
            )

        # Apply the change
        success = await self._apply_fn(event)
        if success:
            position.last_sequence = event.sequence_number
            position.last_event_id = event.event_id
            position.last_timestamp = event.timestamp
            position.lag_ms = (time.time() - event.timestamp) * 1000
        else:
            logger.error(f"Failed to apply event {event.event_id}")

    def get_lag_report(self) -> dict[str, float]:
        """Get replication lag per source region in milliseconds."""
        return {
            name: pos.lag_ms
            for name, pos in self._positions.items()
        }


# ── Replication lag monitor ───────────────────────────────────────

@dataclass
class LagAlert:
    source_region: str
    current_lag_ms: float
    threshold_ms: float
    message: str
    timestamp: str


class ReplicationLagMonitor:
    """Monitors replication lag and triggers alerts.

    Tracks lag per source region with configurable thresholds.
    Can trigger alerts or automatic failover actions.
    """

    def __init__(
        self,
        consumer: ReplicationConsumer,
        warning_threshold_ms: float = 5_000,     # 5 seconds
        critical_threshold_ms: float = 30_000,    # 30 seconds
        check_interval: float = 10.0,
    ) -> None:
        self._consumer = consumer
        self._warning_ms = warning_threshold_ms
        self._critical_ms = critical_threshold_ms
        self._interval = check_interval
        self._alert_handlers: list[Callable[[LagAlert], Coroutine]] = []
        self._lag_history: dict[str, deque[tuple[float, float]]] = {}

    def on_alert(self, handler: Callable[[LagAlert], Coroutine]) -> None:
        self._alert_handlers.append(handler)

    async def start_monitoring(self) -> None:
        while True:
            lag_report = self._consumer.get_lag_report()

            for source, lag_ms in lag_report.items():
                # Track history for trending
                if source not in self._lag_history:
                    self._lag_history[source] = deque(maxlen=100)
                self._lag_history[source].append((time.time(), lag_ms))

                if lag_ms > self._critical_ms:
                    await self._fire_alert(LagAlert(
                        source_region=source,
                        current_lag_ms=lag_ms,
                        threshold_ms=self._critical_ms,
                        message=f"CRITICAL: Replication lag from {source} is {lag_ms:.0f}ms",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ))
                elif lag_ms > self._warning_ms:
                    await self._fire_alert(LagAlert(
                        source_region=source,
                        current_lag_ms=lag_ms,
                        threshold_ms=self._warning_ms,
                        message=f"WARNING: Replication lag from {source} is {lag_ms:.0f}ms",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ))

            await asyncio.sleep(self._interval)

    async def _fire_alert(self, alert: LagAlert) -> None:
        for handler in self._alert_handlers:
            try:
                await handler(alert)
            except Exception as e:
                logger.error(f"Alert handler error: {e}")

    def get_lag_stats(self) -> dict[str, dict[str, float]]:
        """Get lag statistics per source region."""
        stats = {}
        for source, history in self._lag_history.items():
            lags = [lag for _, lag in history]
            if lags:
                stats[source] = {
                    "current_ms": lags[-1],
                    "avg_ms": sum(lags) / len(lags),
                    "max_ms": max(lags),
                    "min_ms": min(lags),
                    "p99_ms": sorted(lags)[int(len(lags) * 0.99)] if len(lags) > 1 else lags[0],
                }
        return stats


# ── Cross-region replication setup ────────────────────────────────

async def setup_replication() -> None:
    """Set up bidirectional replication between regions."""

    # Each region has its own CDC producer
    us_east_cdc = ChangeDataCapture("us-east-1")
    eu_west_cdc = ChangeDataCapture("eu-west-1")

    # Apply function for local database
    async def apply_change(event: ChangeEvent) -> bool:
        logger.info(
            f"Applying {event.change_type.value} on {event.table}:{event.key} "
            f"from {event.source_region}"
        )
        # In production: apply to local DB with conflict resolution
        return True

    # Each region consumes from the other
    us_consumer = ReplicationConsumer("us-east-1", apply_change)
    eu_consumer = ReplicationConsumer("eu-west-1", apply_change)

    # Wire up: EU produces -> US consumes, and vice versa
    eu_to_us_queue = eu_west_cdc.subscribe()
    us_to_eu_queue = us_east_cdc.subscribe()

    # Start lag monitoring
    us_monitor = ReplicationLagMonitor(us_consumer)
    eu_monitor = ReplicationLagMonitor(eu_consumer)

    async def alert_handler(alert: LagAlert) -> None:
        logger.warning(alert.message)

    us_monitor.on_alert(alert_handler)
    eu_monitor.on_alert(alert_handler)

    # Start all consumers and monitors
    await asyncio.gather(
        us_consumer.consume(eu_to_us_queue),
        eu_consumer.consume(us_to_eu_queue),
        us_monitor.start_monitoring(),
        eu_monitor.start_monitoring(),
    )
```

Replication strategies comparison:

| Strategy | Consistency | Latency | Complexity |
|---|---|---|---|
| Synchronous replication | Strong | High (cross-region RTT) | Medium |
| Async CDC (this example) | Eventual | Low (local writes fast) | Medium |
| CRDT-based | Strong eventual | Low | High |
| Consensus (Raft/Paxos) | Strong | High (majority quorum) | Very high |
| Log shipping | Eventual | Medium (batch delay) | Low |

Key patterns:
- **CDC events** capture all changes with before/after state
- **Sequence numbers** detect gaps and ensure ordered application
- **Idempotent application** makes replay safe (skip already-seen events)
- **Lag monitoring** with percentile tracking and alerting thresholds
- **Bidirectional replication** for active-active setup
- **Change buffering** enables catch-up after consumer restarts
'''
    ),
    (
        "multi-region/failover-patterns",
        "Implement automated failover patterns for multi-region deployments including health-based failover, DNS failover, traffic draining, and split-brain prevention.",
        '''Automated multi-region failover with health monitoring and split-brain prevention:

```python
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger("multiregion.failover")


class RegionRole(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    DRAINING = "draining"
    FAILED = "failed"
    RECOVERING = "recovering"


class FailoverTrigger(str, Enum):
    HEALTH_CHECK = "health_check"
    MANUAL = "manual"
    LAG_EXCEEDED = "lag_exceeded"
    SPLIT_BRAIN = "split_brain"
    SCHEDULED = "scheduled"         # planned maintenance


@dataclass
class RegionState:
    name: str
    role: RegionRole
    endpoint: str
    healthy: bool = True
    consecutive_failures: int = 0
    last_healthy_at: float = 0
    replication_lag_ms: float = 0
    active_connections: int = 0
    dns_weight: int = 0


@dataclass
class FailoverEvent:
    timestamp: str
    trigger: FailoverTrigger
    from_primary: str
    to_primary: str
    reason: str
    duration_ms: float = 0
    success: bool = True


class FailoverConfig:
    """Configuration for automated failover behavior."""

    def __init__(
        self,
        health_check_interval: float = 5.0,
        failure_threshold: int = 3,        # consecutive failures before failover
        recovery_threshold: int = 5,       # consecutive successes before recovery
        drain_timeout: float = 30.0,       # seconds to drain traffic
        max_replication_lag_ms: float = 10_000,
        cooldown_period: float = 300.0,    # minimum time between failovers
        require_manual_failback: bool = True,  # prevent automatic failback
    ) -> None:
        self.health_check_interval = health_check_interval
        self.failure_threshold = failure_threshold
        self.recovery_threshold = recovery_threshold
        self.drain_timeout = drain_timeout
        self.max_replication_lag_ms = max_replication_lag_ms
        self.cooldown_period = cooldown_period
        self.require_manual_failback = require_manual_failback


class FailoverOrchestrator:
    """Orchestrates failover between regions.

    Monitors health, triggers failover when thresholds are exceeded,
    and coordinates the traffic shift with proper draining.
    """

    def __init__(
        self,
        regions: list[RegionState],
        config: FailoverConfig | None = None,
        health_check_fn: Callable[[str], Coroutine[Any, Any, bool]] | None = None,
        dns_update_fn: Callable[[str, int], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self._regions = {r.name: r for r in regions}
        self._config = config or FailoverConfig()
        self._health_check = health_check_fn or self._default_health_check
        self._dns_update = dns_update_fn or self._default_dns_update
        self._failover_history: list[FailoverEvent] = []
        self._last_failover_time: float = 0
        self._running = False
        self._callbacks: list[Callable[[FailoverEvent], Coroutine]] = []

    def on_failover(self, callback: Callable[[FailoverEvent], Coroutine]) -> None:
        self._callbacks.append(callback)

    @property
    def primary(self) -> RegionState | None:
        for r in self._regions.values():
            if r.role == RegionRole.PRIMARY:
                return r
        return None

    @property
    def secondaries(self) -> list[RegionState]:
        return [r for r in self._regions.values() if r.role == RegionRole.SECONDARY]

    # ── Health monitoring ─────────────────────────────────────────

    async def start_monitoring(self) -> None:
        self._running = True
        while self._running:
            await self._check_all_regions()
            await self._evaluate_failover()
            await asyncio.sleep(self._config.health_check_interval)

    async def _check_all_regions(self) -> None:
        for region in self._regions.values():
            if region.role == RegionRole.FAILED:
                # Check if a failed region has recovered
                healthy = await self._health_check(region.endpoint)
                if healthy:
                    region.consecutive_failures = 0
                    region.healthy = True
                continue

            healthy = await self._health_check(region.endpoint)
            if healthy:
                region.healthy = True
                region.consecutive_failures = 0
                region.last_healthy_at = time.monotonic()
            else:
                region.healthy = False
                region.consecutive_failures += 1

    async def _evaluate_failover(self) -> None:
        primary = self.primary
        if not primary:
            return

        # Check cooldown
        if time.monotonic() - self._last_failover_time < self._config.cooldown_period:
            return

        # Check if primary needs failover
        should_failover = False
        reason = ""

        if primary.consecutive_failures >= self._config.failure_threshold:
            should_failover = True
            reason = f"Primary {primary.name} failed {primary.consecutive_failures} consecutive health checks"

        elif primary.replication_lag_ms > self._config.max_replication_lag_ms:
            should_failover = True
            reason = f"Primary {primary.name} replication lag {primary.replication_lag_ms:.0f}ms exceeds threshold"

        if should_failover:
            # Pick the best secondary
            candidates = [
                r for r in self.secondaries
                if r.healthy and r.consecutive_failures == 0
            ]
            if not candidates:
                logger.error("No healthy secondaries available for failover!")
                return

            # Pick secondary with lowest replication lag
            best = min(candidates, key=lambda r: r.replication_lag_ms)
            await self.execute_failover(primary, best, FailoverTrigger.HEALTH_CHECK, reason)

    # ── Failover execution ────────────────────────────────────────

    async def execute_failover(
        self,
        old_primary: RegionState,
        new_primary: RegionState,
        trigger: FailoverTrigger,
        reason: str,
    ) -> FailoverEvent:
        """Execute a failover from old primary to new primary.

        Steps:
        1. Mark old primary as DRAINING
        2. Shift DNS weight away from old primary
        3. Wait for connections to drain
        4. Promote new primary
        5. Update DNS to point to new primary
        6. Mark old primary as FAILED or SECONDARY
        """
        start = time.monotonic()
        logger.warning(
            f"FAILOVER: {old_primary.name} -> {new_primary.name} "
            f"(trigger: {trigger.value}, reason: {reason})"
        )

        # Step 1: Start draining old primary
        old_primary.role = RegionRole.DRAINING
        await self._dns_update(old_primary.name, weight=0)

        # Step 2: Wait for traffic to drain
        drain_start = time.monotonic()
        while (time.monotonic() - drain_start) < self._config.drain_timeout:
            if old_primary.active_connections == 0:
                break
            await asyncio.sleep(1)

        # Step 3: Promote new primary
        new_primary.role = RegionRole.PRIMARY
        new_primary.dns_weight = 100
        await self._dns_update(new_primary.name, weight=100)

        # Step 4: Mark old primary appropriately
        if old_primary.healthy:
            old_primary.role = RegionRole.SECONDARY
            old_primary.dns_weight = 0
        else:
            old_primary.role = RegionRole.FAILED
            old_primary.dns_weight = 0

        # Record the event
        duration_ms = (time.monotonic() - start) * 1000
        event = FailoverEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            trigger=trigger,
            from_primary=old_primary.name,
            to_primary=new_primary.name,
            reason=reason,
            duration_ms=duration_ms,
        )
        self._failover_history.append(event)
        self._last_failover_time = time.monotonic()

        # Notify listeners
        for callback in self._callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Failover callback error: {e}")

        logger.info(f"Failover completed in {duration_ms:.0f}ms")
        return event

    async def manual_failback(self, region_name: str) -> FailoverEvent | None:
        """Manually fail back to a recovered region.

        Only allowed if the region is healthy and in SECONDARY or FAILED state.
        """
        region = self._regions.get(region_name)
        if not region:
            raise ValueError(f"Unknown region: {region_name}")

        if not region.healthy:
            raise ValueError(f"Region {region_name} is not healthy")

        current_primary = self.primary
        if not current_primary:
            raise ValueError("No current primary")

        if region.name == current_primary.name:
            raise ValueError(f"Region {region_name} is already primary")

        return await self.execute_failover(
            current_primary, region, FailoverTrigger.MANUAL,
            f"Manual failback to {region_name}",
        )

    # ── Split-brain detection ─────────────────────────────────────

    async def detect_split_brain(self) -> bool:
        """Detect if multiple regions think they are primary.

        Uses a shared coordination key (e.g., in a global database
        or distributed lock) to verify single-primary invariant.
        """
        primaries = [
            r for r in self._regions.values()
            if r.role == RegionRole.PRIMARY
        ]

        if len(primaries) > 1:
            logger.critical(
                f"SPLIT BRAIN DETECTED: Multiple primaries: "
                f"{[r.name for r in primaries]}"
            )
            # Resolution: keep the one with the highest last_healthy_at
            latest = max(primaries, key=lambda r: r.last_healthy_at)
            for p in primaries:
                if p.name != latest.name:
                    p.role = RegionRole.SECONDARY
                    await self._dns_update(p.name, weight=0)
                    logger.warning(f"Demoted {p.name} to secondary (split-brain resolution)")
            return True

        return False

    # ── Stubs ─────────────────────────────────────────────────────

    async def _default_health_check(self, endpoint: str) -> bool:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{endpoint}/health")
                return resp.status_code == 200
        except Exception:
            return False

    async def _default_dns_update(self, region: str, weight: int) -> None:
        logger.info(f"DNS update: {region} weight={weight}")

    def get_status(self) -> dict[str, Any]:
        return {
            "regions": {
                name: {
                    "role": r.role.value,
                    "healthy": r.healthy,
                    "dns_weight": r.dns_weight,
                    "consecutive_failures": r.consecutive_failures,
                    "replication_lag_ms": r.replication_lag_ms,
                }
                for name, r in self._regions.items()
            },
            "failover_history": [
                {
                    "timestamp": e.timestamp,
                    "trigger": e.trigger.value,
                    "from": e.from_primary,
                    "to": e.to_primary,
                    "reason": e.reason,
                    "duration_ms": e.duration_ms,
                }
                for e in self._failover_history[-10:]
            ],
        }
```

Failover execution timeline:

| Step | Action | Duration |
|---|---|---|
| 1. Detection | Health check fails N times | N * interval |
| 2. Decision | Evaluate secondaries, pick best | ~instant |
| 3. Drain | Shift DNS weight to 0, wait for connections | 10-30s |
| 4. Promote | Set new primary, update DNS | ~instant |
| 5. Verify | Confirm new primary is serving | 5-10s |
| 6. Notify | Fire callbacks, log event | ~instant |

Key patterns:
- **Consecutive failure threshold**: Prevents flapping on transient errors
- **Cooldown period**: Prevents rapid failover oscillation
- **Drain timeout**: Gracefully shifts traffic before cutting over
- **Split-brain detection**: Ensures single-primary invariant
- **Manual failback**: Prevents automatic failback to a potentially unstable region
- **Replication lag check**: Only fail over to secondaries with acceptable lag
'''
    ),
    (
        "multi-region/latency-routing",
        "Implement latency-based routing for a multi-region API with real-time latency measurement, adaptive routing weights, and client-side region affinity tracking.",
        '''Latency-based routing with real-time measurement and adaptive weights:

```python
from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("multiregion.latency_routing")


@dataclass
class LatencyStats:
    """Latency statistics for a region endpoint."""
    samples: deque[float] = field(default_factory=lambda: deque(maxlen=100))
    ema: float = 0                   # exponential moving average
    p50: float = 0
    p95: float = 0
    p99: float = 0
    jitter: float = 0               # standard deviation of recent samples
    last_probe_at: float = 0

    def add_sample(self, latency_ms: float) -> None:
        self.samples.append(latency_ms)
        alpha = 0.2
        self.ema = alpha * latency_ms + (1 - alpha) * self.ema if self.ema else latency_ms
        self._update_percentiles()
        self.last_probe_at = time.monotonic()

    def _update_percentiles(self) -> None:
        if not self.samples:
            return
        sorted_samples = sorted(self.samples)
        n = len(sorted_samples)
        self.p50 = sorted_samples[int(n * 0.5)]
        self.p95 = sorted_samples[min(int(n * 0.95), n - 1)]
        self.p99 = sorted_samples[min(int(n * 0.99), n - 1)]

        if n >= 2:
            mean = sum(sorted_samples) / n
            variance = sum((x - mean) ** 2 for x in sorted_samples) / n
            self.jitter = math.sqrt(variance)


@dataclass
class RegionEndpointConfig:
    name: str
    endpoint: str
    probe_path: str = "/ping"
    min_weight: int = 5             # minimum traffic share
    max_weight: int = 100           # maximum traffic share
    healthy: bool = True
    latency: LatencyStats = field(default_factory=LatencyStats)
    adaptive_weight: float = 50.0   # dynamically adjusted


class LatencyProber:
    """Continuously probes region endpoints to measure latency.

    Uses lightweight HTTP requests (GET /ping or HEAD /)
    with timing to build a latency profile for each region.
    """

    def __init__(
        self,
        endpoints: list[RegionEndpointConfig],
        probe_interval: float = 5.0,
        probe_timeout: float = 3.0,
    ) -> None:
        self._endpoints = {e.name: e for e in endpoints}
        self._interval = probe_interval
        self._timeout = probe_timeout
        self._running = False

    async def start(self) -> None:
        self._running = True
        while self._running:
            await self._probe_all()
            await asyncio.sleep(self._interval)

    async def _probe_all(self) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            tasks = [
                self._probe_one(client, ep)
                for ep in self._endpoints.values()
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _probe_one(
        self, client: httpx.AsyncClient, endpoint: RegionEndpointConfig,
    ) -> None:
        start = time.monotonic()
        try:
            await client.get(f"{endpoint.endpoint}{endpoint.probe_path}")
            latency_ms = (time.monotonic() - start) * 1000
            endpoint.latency.add_sample(latency_ms)
            endpoint.healthy = True
        except Exception:
            latency_ms = (time.monotonic() - start) * 1000
            endpoint.latency.add_sample(latency_ms + 10000)  # penalty
            endpoint.healthy = False

    def get_endpoint(self, name: str) -> RegionEndpointConfig | None:
        return self._endpoints.get(name)


class AdaptiveWeightCalculator:
    """Dynamically adjusts routing weights based on latency measurements.

    Uses inverse-latency weighting: lower latency = higher weight.
    Includes jitter penalty and health-based adjustments.
    """

    def __init__(
        self,
        jitter_penalty: float = 0.5,   # penalize high jitter
        smoothing_factor: float = 0.3,  # weight change speed (0-1)
    ) -> None:
        self._jitter_penalty = jitter_penalty
        self._smoothing = smoothing_factor

    def calculate_weights(
        self, endpoints: list[RegionEndpointConfig],
    ) -> dict[str, float]:
        """Calculate optimal traffic weights based on current latency."""
        healthy = [e for e in endpoints if e.healthy]
        if not healthy:
            # All unhealthy — equal weights
            return {e.name: 100 / len(endpoints) for e in endpoints}

        # Calculate score for each endpoint (lower latency = higher score)
        scores: dict[str, float] = {}
        for ep in healthy:
            base_latency = ep.latency.ema or 100
            jitter = ep.latency.jitter or 0

            # Effective latency = base + jitter penalty
            effective = base_latency + jitter * self._jitter_penalty

            # Inverse score (lower latency = higher score)
            scores[ep.name] = 1.0 / max(effective, 1.0)

        # Normalize to percentages
        total_score = sum(scores.values())
        weights: dict[str, float] = {}

        for ep in endpoints:
            if ep.name in scores:
                raw_weight = (scores[ep.name] / total_score) * 100
                # Clamp to min/max bounds
                clamped = max(ep.min_weight, min(ep.max_weight, raw_weight))
                # Smooth the transition
                new_weight = (
                    self._smoothing * clamped +
                    (1 - self._smoothing) * ep.adaptive_weight
                )
                weights[ep.name] = new_weight
                ep.adaptive_weight = new_weight
            else:
                weights[ep.name] = 0
                ep.adaptive_weight = 0

        return weights


class LatencyBasedRouter:
    """Routes requests based on real-time latency measurements.

    Combines latency probing, adaptive weight calculation,
    and weighted random selection for traffic distribution.
    """

    def __init__(
        self,
        endpoints: list[RegionEndpointConfig],
        probe_interval: float = 5.0,
        weight_update_interval: float = 10.0,
    ) -> None:
        self._endpoints = endpoints
        self._prober = LatencyProber(endpoints, probe_interval)
        self._calculator = AdaptiveWeightCalculator()
        self._weights: dict[str, float] = {e.name: e.adaptive_weight for e in endpoints}
        self._weight_interval = weight_update_interval

    async def start(self) -> None:
        """Start latency probing and weight calculation."""
        await asyncio.gather(
            self._prober.start(),
            self._weight_updater(),
        )

    async def _weight_updater(self) -> None:
        while True:
            self._weights = self._calculator.calculate_weights(self._endpoints)
            logger.debug(f"Updated weights: {self._weights}")
            await asyncio.sleep(self._weight_interval)

    def select_endpoint(
        self,
        client_affinity: str | None = None,
    ) -> RegionEndpointConfig:
        """Select the best endpoint using weighted random selection.

        If client has a region affinity and that region is healthy,
        prefer it to maintain session locality.
        """
        # Client affinity: prefer the affinity region if healthy
        if client_affinity:
            for ep in self._endpoints:
                if ep.name == client_affinity and ep.healthy:
                    # 80% chance to use affinity region
                    if random.random() < 0.8:
                        return ep

        # Weighted random selection
        healthy = [e for e in self._endpoints if e.healthy]
        if not healthy:
            return random.choice(self._endpoints)

        weights = [self._weights.get(e.name, 0) for e in healthy]
        total = sum(weights) or 1

        pick = random.uniform(0, total)
        cumulative = 0
        for ep, w in zip(healthy, weights):
            cumulative += w
            if pick <= cumulative:
                return ep

        return healthy[-1]

    def get_routing_table(self) -> list[dict[str, Any]]:
        """Get current routing table for monitoring."""
        return [
            {
                "region": ep.name,
                "healthy": ep.healthy,
                "weight": round(self._weights.get(ep.name, 0), 1),
                "latency_ema_ms": round(ep.latency.ema, 1),
                "latency_p50_ms": round(ep.latency.p50, 1),
                "latency_p95_ms": round(ep.latency.p95, 1),
                "jitter_ms": round(ep.latency.jitter, 1),
                "samples": len(ep.latency.samples),
            }
            for ep in self._endpoints
        ]


# ── Client-side region affinity ───────────────────────────────────

class RegionAffinityTracker:
    """Tracks client-to-region affinity for session locality.

    Stores a cookie or header indicating which region served
    the client previously, enabling sticky routing.
    """

    COOKIE_NAME = "X-Region-Affinity"
    HEADER_NAME = "x-region-affinity"

    def get_affinity(self, request_headers: dict[str, str]) -> str | None:
        """Extract region affinity from request."""
        return request_headers.get(self.HEADER_NAME)

    def set_affinity(
        self, response_headers: dict[str, str], region: str,
    ) -> None:
        """Set region affinity in response for next request."""
        response_headers[self.HEADER_NAME] = region
        response_headers["Set-Cookie"] = (
            f"{self.COOKIE_NAME}={region}; "
            f"Path=/; Max-Age=3600; SameSite=Lax"
        )


# ── Usage example ─────────────────────────────────────────────────

async def main() -> None:
    endpoints = [
        RegionEndpointConfig(
            name="us-east-1",
            endpoint="https://api-east.example.com",
            min_weight=10,
        ),
        RegionEndpointConfig(
            name="eu-west-1",
            endpoint="https://api-eu.example.com",
            min_weight=10,
        ),
        RegionEndpointConfig(
            name="ap-southeast-1",
            endpoint="https://api-ap.example.com",
            min_weight=5,
        ),
    ]

    router = LatencyBasedRouter(endpoints, probe_interval=5.0)

    # Start in background
    asyncio.create_task(router.start())

    # Wait for initial measurements
    await asyncio.sleep(10)

    # Route requests
    for _ in range(100):
        ep = router.select_endpoint(client_affinity="us-east-1")
        print(f"Routed to: {ep.name} (weight: {router._weights.get(ep.name, 0):.1f})")

    # Check routing table
    for entry in router.get_routing_table():
        print(
            f"  {entry['region']}: weight={entry['weight']}%, "
            f"p50={entry['latency_p50_ms']}ms, "
            f"p95={entry['latency_p95_ms']}ms"
        )
```

Latency-based routing components:

| Component | Role | Update frequency |
|---|---|---|
| Latency prober | Measure RTT to each region | Every 5-10 seconds |
| Weight calculator | Convert latency to traffic weights | Every 10-30 seconds |
| Router | Select endpoint per request | Per request |
| Affinity tracker | Maintain session stickiness | Per response |

Key patterns:
- **EMA smoothing**: Prevents routing oscillation from latency spikes
- **Jitter penalty**: Penalizes unstable endpoints even if average is good
- **Min/max weight bounds**: Ensures every healthy region gets some traffic
- **Gradual weight transitions**: Smoothing factor prevents sudden shifts
- **Client affinity**: 80/20 split between affinity and optimal routing
- **Percentile tracking**: P50/P95/P99 for latency SLA monitoring
'''
    ),
]
