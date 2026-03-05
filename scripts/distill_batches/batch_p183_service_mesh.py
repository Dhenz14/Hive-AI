"""Service mesh: Istio/Linkerd patterns, traffic management, mutual TLS, observability, canary deployments, circuit breaking."""

PAIRS = [
    (
        "infrastructure/service-mesh-istio-traffic-management",
        "How do I implement advanced traffic management with Istio? Show VirtualService and DestinationRule configurations for canary deployments, traffic mirroring, fault injection, and a Python deployment orchestrator.",
        '''Istio traffic management uses VirtualService for routing rules and DestinationRule for load balancing and connection pool policies. Together they enable fine-grained traffic control without application changes.

## Traffic Management Architecture

| Resource | Purpose |
|---|---|
| VirtualService | Route matching, traffic splitting, retries, timeouts |
| DestinationRule | Subsets, load balancing, connection pools, outlier detection |
| Gateway | Ingress traffic configuration |
| ServiceEntry | External service registration |

## Istio Canary Orchestrator

```python
#!/usr/bin/env python3
"""
Istio traffic management orchestrator for canary deployments,
traffic mirroring, and progressive rollouts with automated analysis.
"""

import asyncio
import logging
from typing import Optional
from dataclasses import dataclass, field
import httpx
import yaml

logger = logging.getLogger(__name__)


@dataclass
class CanaryConfig:
    service_name: str
    namespace: str
    stable_version: str
    canary_version: str
    steps: list[int] = field(default_factory=lambda: [5, 10, 25, 50, 75, 100])
    step_interval_seconds: int = 300
    error_rate_threshold: float = 0.01
    latency_p99_threshold_ms: float = 500.0
    min_request_count: int = 100
    rollback_on_failure: bool = True


@dataclass
class MeshMetrics:
    success_rate: float
    request_count: int
    latency_p50_ms: float
    latency_p99_ms: float
    error_count: int


class IstioTrafficManager:
    """Manages Istio VirtualService and DestinationRule resources."""

    def __init__(self, kube_api_url: str = "http://localhost:8001"):
        self.kube_api = kube_api_url
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
        self._client = httpx.AsyncClient(base_url=self.kube_api, timeout=30)

    async def stop(self):
        if self._client:
            await self._client.aclose()

    def build_virtual_service(self, name: str, namespace: str, host: str,
                               splits: list[dict], retries: Optional[dict] = None,
                               timeout: str = "30s", mirror: Optional[dict] = None,
                               header_routes: Optional[list[dict]] = None) -> dict:
        http_routes = []
        if header_routes:
            for hr in header_routes:
                http_routes.append({
                    "match": [{"headers": {hr["header"]: {"exact": hr["value"]}}}],
                    "route": [{"destination": {"host": host, "subset": hr["subset"]}}],
                })

        main_route = {
            "route": [{"destination": {"host": host, "subset": s["subset"]},
                        "weight": s["weight"]} for s in splits],
            "timeout": timeout,
        }
        if retries:
            main_route["retries"] = retries
        if mirror:
            main_route["mirror"] = {"host": host, "subset": mirror["subset"]}
            main_route["mirrorPercentage"] = {"value": mirror.get("percentage", 100)}
        http_routes.append(main_route)

        return {
            "apiVersion": "networking.istio.io/v1",
            "kind": "VirtualService",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {"hosts": [host], "http": http_routes},
        }

    def build_destination_rule(self, name: str, namespace: str, host: str,
                                subsets: list[dict],
                                outlier_detection: Optional[dict] = None) -> dict:
        spec = {
            "host": host,
            "trafficPolicy": {
                "tls": {"mode": "ISTIO_MUTUAL"},
                "connectionPool": {
                    "tcp": {"maxConnections": 100, "connectTimeout": "5s"},
                    "http": {"h2UpgradePolicy": "DEFAULT",
                             "http1MaxPendingRequests": 100,
                             "maxRequestsPerConnection": 10},
                },
            },
            "subsets": [{"name": s["name"], "labels": s["labels"]} for s in subsets],
        }
        if outlier_detection:
            spec["trafficPolicy"]["outlierDetection"] = outlier_detection
        return {
            "apiVersion": "networking.istio.io/v1",
            "kind": "DestinationRule",
            "metadata": {"name": name, "namespace": namespace},
            "spec": spec,
        }

    async def apply_resource(self, resource: dict) -> bool:
        kind = resource["kind"]
        ns = resource["metadata"]["namespace"]
        name = resource["metadata"]["name"]
        group, version = resource["apiVersion"].rsplit("/", 1)
        plural = f"{kind.lower()}s"
        url = f"/apis/{group}/{version}/namespaces/{ns}/{plural}/{name}"
        resp = await self._client.put(url, json=resource)
        if resp.status_code == 404:
            url = f"/apis/{group}/{version}/namespaces/{ns}/{plural}"
            resp = await self._client.post(url, json=resource)
        if resp.status_code in (200, 201):
            logger.info("Applied %s/%s", kind, name)
            return True
        logger.error("Failed %s/%s: %s", kind, name, resp.text)
        return False


class CanaryOrchestrator:
    """Progressive canary rollout with automated Prometheus analysis."""

    def __init__(self, traffic_mgr: IstioTrafficManager,
                 prometheus_url: str = "http://prometheus:9090"):
        self.traffic_mgr = traffic_mgr
        self.prometheus_url = prometheus_url
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
        self._client = httpx.AsyncClient(timeout=10)

    async def stop(self):
        if self._client:
            await self._client.aclose()

    async def execute_canary(self, config: CanaryConfig) -> bool:
        logger.info("Canary start: %s %s -> %s",
            config.service_name, config.stable_version, config.canary_version)

        host = f"{config.service_name}.{config.namespace}.svc.cluster.local"
        dr = self.traffic_mgr.build_destination_rule(
            name=config.service_name, namespace=config.namespace, host=host,
            subsets=[
                {"name": "stable", "labels": {"version": config.stable_version}},
                {"name": "canary", "labels": {"version": config.canary_version}},
            ],
            outlier_detection={
                "consecutive5xxErrors": 3, "interval": "10s",
                "baseEjectionTime": "30s", "maxEjectionPercent": 50,
            })
        await self.traffic_mgr.apply_resource(dr)

        for weight in config.steps:
            logger.info("Canary step: %d%% to %s", weight, config.canary_version)
            vs = self.traffic_mgr.build_virtual_service(
                name=config.service_name, namespace=config.namespace, host=host,
                splits=[{"subset": "stable", "weight": 100 - weight},
                        {"subset": "canary", "weight": weight}],
                retries={"attempts": 3, "perTryTimeout": "2s",
                         "retryOn": "5xx,reset,connect-failure"})
            await self.traffic_mgr.apply_resource(vs)
            await asyncio.sleep(config.step_interval_seconds)

            metrics = await self._collect_metrics(config)
            if not self._is_healthy(metrics, config):
                logger.warning("Canary unhealthy at %d%%", weight)
                if config.rollback_on_failure:
                    await self._rollback(config, host)
                    return False
            logger.info("Healthy at %d%%: sr=%.3f p99=%.1fms",
                weight, metrics.success_rate, metrics.latency_p99_ms)

        logger.info("Canary promoted: %s %s", config.service_name, config.canary_version)
        return True

    async def _collect_metrics(self, config: CanaryConfig) -> MeshMetrics:
        svc, ver = config.service_name, config.canary_version
        queries = {
            "sr": (f'sum(rate(istio_requests_total{{destination_service_name="{svc}",'
                   f'destination_version="{ver}",response_code=~"2.."}}[5m])) / '
                   f'sum(rate(istio_requests_total{{destination_service_name="{svc}",'
                   f'destination_version="{ver}"}}[5m]))'),
            "count": (f'sum(increase(istio_requests_total{{destination_service_name="{svc}",'
                      f'destination_version="{ver}"}}[5m]))'),
            "p99": (f'histogram_quantile(0.99,sum(rate(istio_request_duration_milliseconds_bucket'
                    f'{{destination_service_name="{svc}",destination_version="{ver}"}}[5m]))by(le))'),
        }
        results = {}
        for key, q in queries.items():
            resp = await self._client.get(f"{self.prometheus_url}/api/v1/query",
                                           params={"query": q})
            data = resp.json()
            r = data.get("data", {}).get("result", [])
            results[key] = float(r[0]["value"][1]) if r else 0.0
        return MeshMetrics(success_rate=results.get("sr", 0), request_count=int(results.get("count", 0)),
                           latency_p50_ms=0, latency_p99_ms=results.get("p99", 0), error_count=0)

    def _is_healthy(self, m: MeshMetrics, c: CanaryConfig) -> bool:
        if m.request_count < c.min_request_count:
            return True
        return (1.0 - m.success_rate) <= c.error_rate_threshold and m.latency_p99_ms <= c.latency_p99_threshold_ms

    async def _rollback(self, config: CanaryConfig, host: str):
        logger.warning("Rolling back %s", config.service_name)
        vs = self.traffic_mgr.build_virtual_service(
            name=config.service_name, namespace=config.namespace, host=host,
            splits=[{"subset": "stable", "weight": 100}, {"subset": "canary", "weight": 0}])
        await self.traffic_mgr.apply_resource(vs)
```

## Key Patterns

- **Progressive rollout**: Traffic incrementally shifted (5% -> 10% -> 25% -> 50% -> 100%) with health checks
- **Automated analysis**: Prometheus metrics evaluated against thresholds at each step
- **Automatic rollback**: If canary degrades, traffic instantly reverts to stable
- **Outlier detection**: Unhealthy pods ejected from the load balancer pool
- **Header-based routing**: Testers route to canary via headers before public exposure
- **Traffic mirroring**: Shadow traffic to new version for comparison without user impact'''
    ),
    (
        "infrastructure/service-mesh-circuit-breaking",
        "How do I implement circuit breaking and resilience patterns at the service mesh level? Show Istio DestinationRule circuit breakers, outlier detection, and a Python monitoring system that tracks circuit states across the mesh.",
        '''Circuit breaking at the mesh level protects services from cascading failures without requiring application code changes. Istio implements this through DestinationRule connection pools and outlier detection.

## Circuit Breaking Architecture

| Mechanism | Istio Resource | Purpose |
|---|---|---|
| Connection limits | connectionPool.tcp | Cap max connections |
| Request limits | connectionPool.http | Cap concurrent requests |
| Outlier detection | outlierDetection | Eject unhealthy endpoints |
| Retries | VirtualService retries | Retry on transient errors |
| Timeouts | VirtualService timeout | Bound request duration |

## Mesh Circuit Breaker Monitor

```python
#!/usr/bin/env python3
"""
Service mesh circuit breaker monitoring and management.
Monitors Istio circuit breaker states via Envoy metrics
and Prometheus, with automated cascade detection.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import httpx

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    service_name: str
    namespace: str
    max_connections: int = 100
    max_pending_requests: int = 100
    max_requests_per_connection: int = 10
    max_retries: int = 3
    consecutive_errors_to_eject: int = 5
    eject_interval: str = "10s"
    base_ejection_time: str = "30s"
    max_ejection_percent: int = 50

    def to_destination_rule(self) -> dict:
        host = f"{self.service_name}.{self.namespace}.svc.cluster.local"
        return {
            "apiVersion": "networking.istio.io/v1",
            "kind": "DestinationRule",
            "metadata": {"name": f"{self.service_name}-cb", "namespace": self.namespace},
            "spec": {
                "host": host,
                "trafficPolicy": {
                    "connectionPool": {
                        "tcp": {"maxConnections": self.max_connections, "connectTimeout": "5s"},
                        "http": {
                            "http1MaxPendingRequests": self.max_pending_requests,
                            "http2MaxRequests": self.max_connections * 2,
                            "maxRequestsPerConnection": self.max_requests_per_connection,
                            "maxRetries": self.max_retries,
                        },
                    },
                    "outlierDetection": {
                        "consecutive5xxErrors": self.consecutive_errors_to_eject,
                        "interval": self.eject_interval,
                        "baseEjectionTime": self.base_ejection_time,
                        "maxEjectionPercent": self.max_ejection_percent,
                        "minHealthPercent": 50,
                    },
                    "tls": {"mode": "ISTIO_MUTUAL"},
                },
            },
        }


@dataclass
class ServiceHealth:
    service_name: str
    namespace: str
    circuit_state: CircuitState
    ejected_hosts: int
    total_hosts: int
    success_rate_1m: float
    success_rate_5m: float
    overflow_count: int

    @property
    def healthy_host_percent(self) -> float:
        if self.total_hosts == 0:
            return 0.0
        return ((self.total_hosts - self.ejected_hosts) / self.total_hosts) * 100

    @property
    def is_degraded(self) -> bool:
        return self.success_rate_1m < 0.95 or self.ejected_hosts > 0 or self.overflow_count > 0


class MeshCircuitMonitor:
    """Monitors circuit breaker states across the service mesh."""

    def __init__(self, prometheus_url: str = "http://prometheus:9090",
                 poll_interval: float = 15.0):
        self.prometheus_url = prometheus_url
        self.poll_interval = poll_interval
        self._client: Optional[httpx.AsyncClient] = None
        self._services: dict[str, CircuitBreakerConfig] = {}
        self._health: dict[str, ServiceHealth] = {}
        self._poll_task: Optional[asyncio.Task] = None
        self._callbacks: dict[str, list[Callable]] = {
            "circuit_opened": [], "circuit_closed": [],
            "service_degraded": [], "cascade_risk": [],
        }

    def on(self, event: str, callback: Callable):
        self._callbacks.setdefault(event, []).append(callback)

    async def start(self):
        self._client = httpx.AsyncClient(timeout=10)
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        if self._poll_task:
            self._poll_task.cancel()
        if self._client:
            await self._client.aclose()

    def register_service(self, config: CircuitBreakerConfig):
        self._services[f"{config.namespace}/{config.service_name}"] = config

    async def _poll_loop(self):
        while True:
            try:
                await asyncio.sleep(self.poll_interval)
                for key, config in self._services.items():
                    health = await self._collect_health(config.service_name, config.namespace)
                    old = self._health.get(key)
                    self._health[key] = health
                    await self._check_transitions(old, health)

                degraded = [h for h in self._health.values() if h.is_degraded]
                if len(degraded) >= 3:
                    for cb in self._callbacks.get("cascade_risk", []):
                        await cb(degraded)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Monitor poll error")
                await asyncio.sleep(5)

    async def _collect_health(self, svc: str, ns: str) -> ServiceHealth:
        queries = {
            "sr1m": (f'sum(rate(istio_requests_total{{destination_service_name="{svc}",'
                     f'response_code=~"2.."}}[1m]))/sum(rate(istio_requests_total'
                     f'{{destination_service_name="{svc}"}}[1m]))'),
            "sr5m": (f'sum(rate(istio_requests_total{{destination_service_name="{svc}",'
                     f'response_code=~"2.."}}[5m]))/sum(rate(istio_requests_total'
                     f'{{destination_service_name="{svc}"}}[5m]))'),
            "overflow": (f'sum(increase(envoy_cluster_upstream_rq_pending_overflow'
                         f'{{cluster_name=~".*{svc}.*"}}[5m]))'),
            "ejected": (f'sum(envoy_cluster_outlier_detection_ejections_active'
                        f'{{cluster_name=~".*{svc}.*"}})'),
        }
        results = {}
        for k, q in queries.items():
            try:
                resp = await self._client.get(f"{self.prometheus_url}/api/v1/query",
                                               params={"query": q})
                data = resp.json()
                r = data.get("data", {}).get("result", [])
                v = float(r[0]["value"][1]) if r else 0.0
                results[k] = 0.0 if str(v) == "nan" else v
            except Exception:
                results[k] = 0.0

        sr1, sr5 = results.get("sr1m", 1.0), results.get("sr5m", 1.0)
        ejected = int(results.get("ejected", 0))

        if sr1 < 0.5 or ejected > 2:
            state = CircuitState.OPEN
        elif sr1 < 0.95 or ejected > 0:
            state = CircuitState.HALF_OPEN
        else:
            state = CircuitState.CLOSED

        return ServiceHealth(
            service_name=svc, namespace=ns, circuit_state=state,
            ejected_hosts=ejected, total_hosts=3,
            success_rate_1m=sr1, success_rate_5m=sr5,
            overflow_count=int(results.get("overflow", 0)))

    async def _check_transitions(self, old: Optional[ServiceHealth], new: ServiceHealth):
        if old is None:
            return
        if old.circuit_state != CircuitState.OPEN and new.circuit_state == CircuitState.OPEN:
            logger.warning("Circuit OPENED: %s/%s", new.namespace, new.service_name)
            for cb in self._callbacks.get("circuit_opened", []):
                await cb(new)
        elif old.circuit_state == CircuitState.OPEN and new.circuit_state == CircuitState.CLOSED:
            logger.info("Circuit CLOSED: %s/%s", new.namespace, new.service_name)
            for cb in self._callbacks.get("circuit_closed", []):
                await cb(new)
```

## Key Patterns

- **Connection pool limits**: Cap TCP connections and pending requests to prevent exhaustion
- **Outlier detection**: Envoy ejects pods returning consecutive 5xx errors automatically
- **Retry budgets**: Limit retries to 20% to prevent retry storms during outages
- **Cascade detection**: When 3+ services are degraded simultaneously, trigger cascade alerts
- **State machine tracking**: Monitor circuit transitions (closed -> open -> half-open -> closed)
- **Mesh-level protection**: All enforcement in Envoy sidecars -- no app code changes'''
    ),
    (
        "infrastructure/service-mesh-observability",
        "How do I integrate comprehensive observability into a service mesh? Show how to collect traces, metrics, and access logs from Istio, and build a Python mesh health dashboard aggregator.",
        '''Service mesh observability leverages the Envoy sidecar to automatically collect traces, metrics, and logs for every service call without instrumenting application code.

## Observability Stack

| Signal | Source | Backend |
|---|---|---|
| Traces | Envoy + OTel | Tempo / Jaeger |
| Metrics | Envoy + Prometheus | Prometheus + Grafana |
| Access Logs | Envoy | Loki / Elasticsearch |
| Service Graph | Kiali | Kiali dashboard |

## Mesh Observability Aggregator

```python
#!/usr/bin/env python3
"""
Service mesh observability aggregator. Collects and correlates
traces, metrics, and service graph data from Istio telemetry.
"""

import asyncio
import logging
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import httpx

logger = logging.getLogger(__name__)


@dataclass
class ServiceMetrics:
    name: str
    namespace: str
    request_rate: float = 0.0
    error_rate: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p99_ms: float = 0.0
    success_rate: float = 1.0


@dataclass
class ServiceEdge:
    source: str
    destination: str
    request_rate: float = 0.0
    error_rate: float = 0.0
    protocol: str = "http"


@dataclass
class TraceSpan:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    operation_name: str
    service_name: str
    start_time: datetime
    duration_ms: float
    status_code: int
    tags: dict = field(default_factory=dict)


@dataclass
class MeshHealthSummary:
    timestamp: datetime
    total_services: int
    healthy_services: int
    degraded_services: int
    failing_services: int
    total_request_rate: float
    overall_success_rate: float
    p99_latency_ms: float
    service_metrics: dict[str, ServiceMetrics] = field(default_factory=dict)
    service_graph: list[ServiceEdge] = field(default_factory=list)


class MeshObservabilityAggregator:
    """Aggregates observability data from the service mesh."""

    def __init__(self, prometheus_url: str = "http://prometheus:9090",
                 tempo_url: str = "http://tempo:3200"):
        self.prometheus_url = prometheus_url
        self.tempo_url = tempo_url
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
        self._client = httpx.AsyncClient(timeout=30)

    async def stop(self):
        if self._client:
            await self._client.aclose()

    async def get_mesh_health(self, namespace: str = "") -> MeshHealthSummary:
        ns_filter = f'destination_service_namespace="{namespace}"' if namespace else ""
        services = await self._discover_services(ns_filter)

        tasks = [self._collect_svc_metrics(s, namespace) for s in services]
        graph_task = self._collect_graph(ns_filter)
        all_metrics = await asyncio.gather(*tasks, return_exceptions=True)
        graph = await graph_task

        svc_map = {}
        healthy = degraded = failing = 0
        total_rps = 0.0
        sr_list = []

        for m in all_metrics:
            if isinstance(m, Exception):
                continue
            svc_map[m.name] = m
            total_rps += m.request_rate
            sr_list.append(m.success_rate)
            if m.success_rate >= 0.99:
                healthy += 1
            elif m.success_rate >= 0.95:
                degraded += 1
            else:
                failing += 1

        return MeshHealthSummary(
            timestamp=datetime.now(timezone.utc),
            total_services=len(svc_map),
            healthy_services=healthy, degraded_services=degraded,
            failing_services=failing, total_request_rate=total_rps,
            overall_success_rate=sum(sr_list) / len(sr_list) if sr_list else 1.0,
            p99_latency_ms=max((m.latency_p99_ms for m in svc_map.values()), default=0),
            service_metrics=svc_map, service_graph=graph)

    async def find_slow_traces(self, service: str,
                                min_duration_ms: float = 1000,
                                limit: int = 20) -> list[TraceSpan]:
        resp = await self._client.get(f"{self.tempo_url}/api/search", params={
            "tags": f"service.name={service}",
            "minDuration": f"{int(min_duration_ms)}ms", "limit": limit})
        data = resp.json()
        spans = []
        for trace in data.get("traces", []):
            for span in trace.get("spans", []):
                spans.append(TraceSpan(
                    trace_id=trace["traceID"], span_id=span.get("spanID", ""),
                    parent_span_id=span.get("parentSpanID"),
                    operation_name=span.get("operationName", ""),
                    service_name=service,
                    start_time=datetime.fromtimestamp(
                        span.get("startTime", 0) / 1e6, tz=timezone.utc),
                    duration_ms=span.get("duration", 0) / 1000,
                    status_code=int(span.get("tags", {}).get("http.status_code", 0)),
                    tags=span.get("tags", {})))
        return sorted(spans, key=lambda s: s.duration_ms, reverse=True)

    async def _discover_services(self, ns_filter: str) -> list[str]:
        q = f'count by (destination_service_name)(istio_requests_total{{{ns_filter}}}) > 0'
        resp = await self._client.get(f"{self.prometheus_url}/api/v1/query",
                                       params={"query": q})
        data = resp.json()
        return [r["metric"]["destination_service_name"]
                for r in data.get("data", {}).get("result", [])]

    async def _collect_svc_metrics(self, svc: str, ns: str) -> ServiceMetrics:
        queries = {
            "rps": f'sum(rate(istio_requests_total{{destination_service_name="{svc}"}}[5m]))',
            "sr": (f'sum(rate(istio_requests_total{{destination_service_name="{svc}",'
                   f'response_code=~"2.."}}[5m]))/sum(rate(istio_requests_total'
                   f'{{destination_service_name="{svc}"}}[5m]))'),
            "p50": (f'histogram_quantile(0.50,sum(rate(istio_request_duration_milliseconds_bucket'
                    f'{{destination_service_name="{svc}"}}[5m]))by(le))'),
            "p99": (f'histogram_quantile(0.99,sum(rate(istio_request_duration_milliseconds_bucket'
                    f'{{destination_service_name="{svc}"}}[5m]))by(le))'),
        }
        results = {}
        for k, q in queries.items():
            try:
                resp = await self._client.get(f"{self.prometheus_url}/api/v1/query",
                                               params={"query": q})
                data = resp.json()
                r = data.get("data", {}).get("result", [])
                v = float(r[0]["value"][1]) if r else 0.0
                results[k] = 0.0 if str(v) == "nan" else v
            except Exception:
                results[k] = 0.0

        return ServiceMetrics(name=svc, namespace=ns, request_rate=results.get("rps", 0),
            success_rate=results.get("sr", 1.0), latency_p50_ms=results.get("p50", 0),
            latency_p99_ms=results.get("p99", 0))

    async def _collect_graph(self, ns_filter: str) -> list[ServiceEdge]:
        q = (f'sum by(source_workload,destination_service_name)'
             f'(rate(istio_requests_total{{{ns_filter},source_workload!="unknown"}}[5m]))')
        resp = await self._client.get(f"{self.prometheus_url}/api/v1/query",
                                       params={"query": q})
        data = resp.json()
        edges = []
        for r in data.get("data", {}).get("result", []):
            rate_val = float(r["value"][1])
            if rate_val > 0:
                edges.append(ServiceEdge(
                    source=r["metric"].get("source_workload", "unknown"),
                    destination=r["metric"].get("destination_service_name", "unknown"),
                    request_rate=rate_val))
        return edges
```

## Key Patterns

- **Automatic instrumentation**: Envoy sidecars capture 100% of telemetry without SDK changes
- **Parallel collection**: All service metrics collected concurrently for responsiveness
- **Service graph discovery**: Dynamic topology built from actual traffic, not static config
- **Slow trace correlation**: Tempo integration finds specific slow requests for root cause
- **Health classification**: Services categorized healthy/degraded/failing by success rate
- **Top error aggregation**: Most frequent error codes surfaced for rapid incident response'''
    ),
    (
        "infrastructure/service-mesh-linkerd-lightweight",
        "Compare Linkerd vs Istio and show how to implement Linkerd service mesh with traffic splitting, automatic mTLS, and service profiles for per-route retries and timeouts.",
        '''Linkerd is a lightweight service mesh using Rust-based micro-proxies. It prioritizes simplicity and low overhead compared to Istio.

## Linkerd vs Istio

| Feature | Linkerd | Istio |
|---|---|---|
| Proxy | linkerd2-proxy (Rust) | Envoy (C++) |
| Memory per pod | ~10MB | ~50-100MB |
| Latency overhead | <1ms p99 | ~3-5ms p99 |
| mTLS | Auto, always on | Configurable |
| Traffic splitting | SMI TrafficSplit | VirtualService |
| Complexity | Low | High |

## Linkerd Service Profile and Traffic Split Manager

```python
#!/usr/bin/env python3
"""
Linkerd service mesh management for lightweight zero-trust networking.
Handles service profiles, SMI traffic splits, and authorization policies.
"""

import logging
import subprocess
import yaml
from typing import Optional
from dataclasses import dataclass, field
import httpx

logger = logging.getLogger(__name__)


@dataclass
class LinkerdServiceProfile:
    """Per-route behavior for a Linkerd-meshed service."""
    service_name: str
    namespace: str
    routes: list[dict] = field(default_factory=list)

    def add_route(self, name: str, method: str, path_regex: str,
                  is_retryable: bool = False, timeout: str = ""):
        route = {"name": name, "condition": {"method": method, "pathRegex": path_regex}}
        if is_retryable:
            route["isRetryable"] = True
        if timeout:
            route["timeout"] = timeout
        self.routes.append(route)

    def to_resource(self) -> dict:
        host = f"{self.service_name}.{self.namespace}.svc.cluster.local"
        return {
            "apiVersion": "linkerd.io/v1alpha2",
            "kind": "ServiceProfile",
            "metadata": {"name": host, "namespace": self.namespace},
            "spec": {
                "routes": self.routes,
                "retryBudget": {"retryRatio": 0.2, "minRetriesPerSecond": 10, "ttl": "10s"},
            },
        }


@dataclass
class LinkerdTrafficSplit:
    name: str
    namespace: str
    root_service: str
    backends: list[dict] = field(default_factory=list)

    def add_backend(self, service: str, weight: int):
        self.backends.append({"service": service, "weight": weight})

    def to_resource(self) -> dict:
        return {
            "apiVersion": "split.smi-spec.io/v1alpha2",
            "kind": "TrafficSplit",
            "metadata": {"name": self.name, "namespace": self.namespace},
            "spec": {
                "service": self.root_service,
                "backends": [{"service": b["service"], "weight": b["weight"]}
                             for b in self.backends],
            },
        }


@dataclass
class LinkerdAuthPolicy:
    name: str
    namespace: str
    server_name: str
    allowed_service_accounts: list[str] = field(default_factory=list)

    def to_resources(self) -> list[dict]:
        resources = []
        resources.append({
            "apiVersion": "policy.linkerd.io/v1beta3",
            "kind": "Server",
            "metadata": {"name": self.server_name, "namespace": self.namespace},
            "spec": {
                "podSelector": {"matchLabels": {"app": self.server_name}},
                "port": "http", "proxyProtocol": "HTTP/2",
            },
        })
        if self.allowed_service_accounts:
            mtls_name = f"{self.name}-mtls"
            resources.append({
                "apiVersion": "policy.linkerd.io/v1alpha1",
                "kind": "MeshTLSAuthentication",
                "metadata": {"name": mtls_name, "namespace": self.namespace},
                "spec": {
                    "identities": [
                        f"{sa}.{self.namespace}.serviceaccount.identity.linkerd.cluster.local"
                        for sa in self.allowed_service_accounts],
                },
            })
            resources.append({
                "apiVersion": "policy.linkerd.io/v1alpha1",
                "kind": "AuthorizationPolicy",
                "metadata": {"name": self.name, "namespace": self.namespace},
                "spec": {
                    "targetRef": {"group": "policy.linkerd.io", "kind": "Server",
                                  "name": self.server_name},
                    "requiredAuthenticationRefs": [{"kind": "MeshTLSAuthentication",
                                                     "name": mtls_name}],
                },
            })
        return resources


class LinkerdManager:
    def __init__(self, kubeconfig: Optional[str] = None):
        self.kubeconfig = kubeconfig

    def inject_deployment(self, deployment_yaml: str) -> str:
        cmd = ["linkerd", "inject", "-"]
        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        return subprocess.run(cmd, input=deployment_yaml, capture_output=True,
                              text=True, check=True).stdout

    def apply_resource(self, resource: dict, dry_run: bool = False) -> bool:
        cmd = ["kubectl", "apply", "-f", "-"]
        if dry_run:
            cmd.append("--dry-run=server")
        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        r = subprocess.run(cmd, input=yaml.dump(resource), capture_output=True, text=True)
        if r.returncode != 0:
            logger.error("Apply failed: %s", r.stderr)
            return False
        return True

    def setup_canary(self, service: str, namespace: str,
                     stable: str, canary: str, canary_weight: int = 0) -> list[dict]:
        profile = LinkerdServiceProfile(service, namespace)
        profile.add_route("GET /api", "GET", "/api/.*", is_retryable=True, timeout="10s")
        profile.add_route("POST /api", "POST", "/api/.*", is_retryable=False, timeout="30s")

        split = LinkerdTrafficSplit(f"{service}-canary", namespace, service)
        split.add_backend(stable, 100 - canary_weight)
        split.add_backend(canary, canary_weight)

        return [profile.to_resource(), split.to_resource()]

    async def get_route_stats(self, service: str, namespace: str,
                               viz_url: str = "http://localhost:8084") -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{viz_url}/api/routes",
                params={"namespace": namespace, "resource": f"deploy/{service}"})
            return resp.json()
```

## Key Patterns

- **Automatic mTLS**: Linkerd enables mutual TLS by default -- all meshed traffic encrypted
- **Lightweight proxies**: Rust linkerd2-proxy uses ~10MB vs Envoy ~50-100MB
- **Service profiles**: Per-route retry/timeout policies (GET retryable, POST not)
- **Retry budgets**: 20% global retry budget prevents retry storms
- **SMI compatibility**: Standard TrafficSplit API works with Flagger and other tools
- **Identity-based auth**: Policies reference service account identities, not IPs'''
    ),
    (
        "infrastructure/service-mesh-multi-cluster",
        "How do I set up multi-cluster service mesh connectivity? Show cross-cluster service discovery, shared trust domains, locality-aware failover, and a Python federation manager.",
        '''Multi-cluster service mesh enables services across Kubernetes clusters to communicate securely with shared identity, discovery, and traffic management.

## Multi-Cluster Patterns

| Pattern | Use Case | Complexity |
|---|---|---|
| Flat network | VPC peering | Low |
| Gateway-based | Separate networks via gateways | Medium |
| DNS federation | External DNS resolution | Medium |
| Full mesh | Every cluster peers | High |

## Multi-Cluster Federation Manager

```python
#!/usr/bin/env python3
"""
Multi-cluster service mesh federation manager.
Cross-cluster service discovery, trust domain sharing,
and locality-aware failover between Kubernetes clusters.
"""

import asyncio
import json
import logging
import subprocess
import yaml
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import httpx

logger = logging.getLogger(__name__)


class ClusterTopology(Enum):
    FLAT_NETWORK = "flat_network"
    GATEWAY_BASED = "gateway_based"


@dataclass
class ClusterConfig:
    name: str
    region: str
    zone: str
    kubeconfig_path: str
    context: str
    network: str = "default"
    is_primary: bool = False
    priority: int = 0


@dataclass
class FederatedService:
    name: str
    namespace: str
    clusters: list[str]
    failover_priority: list[str] = field(default_factory=list)
    locality_lb: bool = True


@dataclass
class ClusterHealth:
    name: str
    region: str
    healthy: bool
    latency_ms: float
    service_count: int
    last_check: datetime


class MultiClusterManager:
    def __init__(self, trust_domain: str = "hiveai.prod",
                 topology: ClusterTopology = ClusterTopology.GATEWAY_BASED):
        self.trust_domain = trust_domain
        self.topology = topology
        self._clusters: dict[str, ClusterConfig] = {}
        self._services: dict[str, FederatedService] = {}
        self._health: dict[str, ClusterHealth] = {}
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
        self._client = httpx.AsyncClient(timeout=30)

    async def stop(self):
        if self._client:
            await self._client.aclose()

    def add_cluster(self, config: ClusterConfig):
        self._clusters[config.name] = config

    def register_service(self, service: FederatedService):
        self._services[f"{service.namespace}/{service.name}"] = service

    def generate_east_west_gateway(self, cluster: ClusterConfig) -> dict:
        return {
            "apiVersion": "install.istio.io/v1alpha1",
            "kind": "IstioOperator",
            "metadata": {"name": "eastwest-gateway"},
            "spec": {
                "profile": "empty",
                "components": {
                    "ingressGateways": [{
                        "name": "istio-eastwestgateway",
                        "label": {"istio": "eastwestgateway",
                                  "topology.istio.io/network": cluster.network},
                        "enabled": True,
                        "k8s": {
                            "env": [{"name": "ISTIO_META_REQUESTED_NETWORK_VIEW",
                                     "value": cluster.network}],
                            "service": {"ports": [
                                {"name": "tls", "port": 15443, "targetPort": 15443},
                                {"name": "status-port", "port": 15021, "targetPort": 15021},
                            ]},
                        },
                    }],
                },
                "values": {
                    "global": {
                        "network": cluster.network, "meshID": "hiveai-mesh",
                        "multiCluster": {"clusterName": cluster.name},
                    },
                },
            },
        }

    def generate_failover_rules(self, service: FederatedService) -> list[dict]:
        host = f"{service.name}.{service.namespace}.svc.cluster.local"
        dr = {
            "apiVersion": "networking.istio.io/v1",
            "kind": "DestinationRule",
            "metadata": {"name": f"{service.name}-federation", "namespace": service.namespace},
            "spec": {
                "host": host,
                "trafficPolicy": {
                    "tls": {"mode": "ISTIO_MUTUAL"},
                    "connectionPool": {
                        "tcp": {"maxConnections": 100},
                        "http": {"h2UpgradePolicy": "DEFAULT", "http1MaxPendingRequests": 100},
                    },
                    "outlierDetection": {
                        "consecutive5xxErrors": 3, "interval": "10s", "baseEjectionTime": "30s",
                    },
                },
            },
        }
        if service.locality_lb and service.failover_priority:
            failover_entries = []
            for i, c in enumerate(service.failover_priority):
                if c in self._clusters:
                    next_c = service.failover_priority[(i + 1) % len(service.failover_priority)]
                    if next_c in self._clusters:
                        failover_entries.append({
                            "from": self._clusters[c].region,
                            "to": self._clusters[next_c].region})
            dr["spec"]["trafficPolicy"]["loadBalancer"] = {
                "localityLbSetting": {"enabled": True, "failover": failover_entries},
                "simple": "ROUND_ROBIN",
            }
        return [dr]

    async def check_cluster_health(self) -> dict[str, ClusterHealth]:
        tasks = [self._check_cluster(n, c) for n, c in self._clusters.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, ClusterHealth):
                self._health[r.name] = r
        return dict(self._health)

    async def _check_cluster(self, name: str, config: ClusterConfig) -> ClusterHealth:
        start = asyncio.get_event_loop().time()
        try:
            r = subprocess.run(
                ["kubectl", "--context", config.context, "get", "pods",
                 "-n", "istio-system", "--field-selector=status.phase=Running",
                 "-o", "json"],
                capture_output=True, text=True, timeout=10)
            elapsed = (asyncio.get_event_loop().time() - start) * 1000
            data = json.loads(r.stdout) if r.returncode == 0 else {}
            return ClusterHealth(name=name, region=config.region,
                healthy=r.returncode == 0, latency_ms=elapsed,
                service_count=len(data.get("items", [])),
                last_check=datetime.now(timezone.utc))
        except Exception:
            elapsed = (asyncio.get_event_loop().time() - start) * 1000
            return ClusterHealth(name=name, region=config.region, healthy=False,
                latency_ms=elapsed, service_count=0, last_check=datetime.now(timezone.utc))

    def apply_federation(self, output_dir: str = "/tmp/federation"):
        from pathlib import Path
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        for key, svc in self._services.items():
            for rule in self.generate_failover_rules(svc):
                path = out / f"{rule['metadata']['name']}.yaml"
                with open(path, "w") as f:
                    yaml.dump(rule, f, default_flow_style=False)
                for cn in svc.clusters:
                    if cn in self._clusters:
                        subprocess.run(["kubectl", "--context", self._clusters[cn].context,
                            "apply", "-f", str(path)], capture_output=True, text=True)
                        logger.info("Applied %s to %s", path.name, cn)
```

## Key Patterns

- **Shared trust domain**: All clusters use same root CA for seamless cross-cluster mTLS
- **East-west gateways**: Dedicated gateways handle cross-cluster traffic on port 15443
- **Locality-aware routing**: Traffic prefers local cluster, auto-fails over to nearest region
- **Health-based failover**: Unhealthy clusters detected and traffic rerouted automatically
- **Federated service registry**: Services explicitly declared multi-cluster with failover priorities
- **Network separation**: Gateway topology handles routing across different networks'''
    ),
]
