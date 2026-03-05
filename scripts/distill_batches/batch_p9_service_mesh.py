"""
Batch P9 — Service Mesh & Networking Patterns
Covers: Istio service mesh, load balancing algorithms, API gateway patterns,
gRPC service patterns, network resilience patterns.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    # --- 1. Istio Service Mesh Architecture ---
    (
        "service-mesh/istio-architecture-traffic-management",
        "Explain the Istio service mesh architecture in depth covering Envoy sidecar proxies, istiod control plane components, traffic management with VirtualService and DestinationRule, mTLS enforcement, circuit breaking, and implement complete Istio traffic routing manifests for canary deployments with fault injection and retry policies.",
        r"""# Istio Service Mesh Architecture and Traffic Management

## Why Service Meshes Exist

Modern microservice architectures introduce a fundamental **networking challenge**: when you have hundreds of services communicating over the network, every service must independently handle retries, timeouts, circuit breaking, mutual TLS, observability, and traffic shaping. This creates enormous duplication and inconsistency because each team implements these cross-cutting concerns differently — or worse, not at all. A **service mesh** solves this by extracting all networking logic into a dedicated infrastructure layer that operates transparently alongside application code.

**Istio** is the most widely adopted service mesh for Kubernetes. It works by injecting an **Envoy proxy sidecar** into every pod, forming a **data plane** that intercepts all inbound and outbound traffic. The **control plane** (consolidated into a single binary called **istiod**) configures these proxies dynamically, therefore eliminating the need for application-level networking code.

## Architecture Overview

### Data Plane: Envoy Sidecar Proxies

Every pod in an Istio mesh gets an automatically injected **Envoy proxy** container. This sidecar intercepts all TCP traffic using `iptables` rules (or eBPF in newer versions). The Envoy proxy handles:

- **Load balancing** across upstream service instances
- **mTLS encryption** for all service-to-service communication
- **Retry logic** with configurable backoff
- **Circuit breaking** to prevent cascade failures
- **Metrics collection** (request count, latency histograms, error rates)
- **Distributed tracing** header propagation

A **common mistake** is assuming the sidecar adds significant latency. In practice, the overhead is typically 1-3ms per hop because Envoy operates in the same network namespace as the application and communicates via localhost. However, the **trade-off** is increased memory consumption — each Envoy sidecar uses approximately 50-100MB of RAM, which adds up at scale.

### Control Plane: istiod

Prior to Istio 1.5, the control plane was split into three separate components (Pilot, Citadel, Galley). These were consolidated into **istiod** for simplicity. istiod handles:

- **Pilot**: Converts high-level routing rules into Envoy-specific configuration (xDS API)
- **Citadel**: Manages certificate issuance and rotation for mTLS
- **Galley**: Validates configuration and distributes it to the data plane

```yaml
# Istio installation with IstioOperator for production
# This configures the control plane and sidecar injection
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
metadata:
  name: production-mesh
  namespace: istio-system
spec:
  profile: default
  meshConfig:
    # Enable access logging for observability
    accessLogFile: /dev/stdout
    accessLogEncoding: JSON
    # Default retry policy for all services
    defaultHttpRetryPolicy:
      attempts: 3
      retryOn: "5xx,reset,connect-failure,retriable-4xx"
      perTryTimeout: 2s
    # Enable strict mTLS mesh-wide
    defaultConfig:
      holdApplicationUntilProxyStarts: true
    enableTracing: true
    defaultConfig:
      tracing:
        sampling: 100.0
  components:
    pilot:
      k8s:
        resources:
          requests:
            cpu: 500m
            memory: 2Gi
        hpaSpec:
          minReplicas: 2
          maxReplicas: 5
    ingressGateways:
      - name: istio-ingressgateway
        enabled: true
        k8s:
          service:
            type: LoadBalancer
          hpaSpec:
            minReplicas: 2
            maxReplicas: 10
```

## Traffic Management with VirtualService and DestinationRule

Istio's traffic management is built on two primary custom resources: **VirtualService** defines *how* traffic is routed, and **DestinationRule** defines *what happens* after routing (load balancing policy, connection pool settings, outlier detection).

### Canary Deployment with Weighted Routing

The **best practice** for canary deployments in Istio is to use weighted routing rather than replica-count-based splitting. This gives precise control over traffic percentages regardless of how many pods each version has.

```yaml
# DestinationRule: Define subsets for canary and stable versions
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: payment-service-dr
  namespace: production
spec:
  host: payment-service.production.svc.cluster.local
  trafficPolicy:
    # Connection pool settings to prevent resource exhaustion
    connectionPool:
      tcp:
        maxConnections: 1000
        connectTimeout: 30ms
      http:
        h2UpgradePolicy: DEFAULT
        http1MaxPendingRequests: 1024
        http2MaxRequests: 1024
        maxRequestsPerConnection: 10
        maxRetries: 3
    # Circuit breaker via outlier detection
    outlierDetection:
      consecutive5xxErrors: 5
      interval: 30s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
      minHealthPercent: 30
    # mTLS enforcement
    tls:
      mode: ISTIO_MUTUAL
  subsets:
    - name: stable
      labels:
        version: v1
      trafficPolicy:
        loadBalancer:
          simple: ROUND_ROBIN
    - name: canary
      labels:
        version: v2
      trafficPolicy:
        loadBalancer:
          simple: LEAST_REQUEST
---
# VirtualService: Route 90% to stable, 10% to canary
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: payment-service-vs
  namespace: production
spec:
  hosts:
    - payment-service.production.svc.cluster.local
  http:
    # Header-based routing for internal testing
    - match:
        - headers:
            x-canary:
              exact: "true"
      route:
        - destination:
            host: payment-service.production.svc.cluster.local
            subset: canary
            port:
              number: 8080
      retries:
        attempts: 3
        perTryTimeout: 2s
        retryOn: "5xx,reset,connect-failure"
    # Weighted traffic split for gradual rollout
    - route:
        - destination:
            host: payment-service.production.svc.cluster.local
            subset: stable
            port:
              number: 8080
          weight: 90
        - destination:
            host: payment-service.production.svc.cluster.local
            subset: canary
            port:
              number: 8080
          weight: 10
      retries:
        attempts: 3
        perTryTimeout: 2s
        retryOn: "5xx,reset,connect-failure"
      timeout: 10s
    # Fault injection for chaos testing
    - match:
        - headers:
            x-fault-inject:
              exact: "true"
      fault:
        delay:
          percentage:
            value: 50.0
          fixedDelay: 5s
        abort:
          percentage:
            value: 10.0
          httpStatus: 503
      route:
        - destination:
            host: payment-service.production.svc.cluster.local
            subset: stable
---
# PeerAuthentication: Enforce strict mTLS
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: production
spec:
  mtls:
    mode: STRICT
```

### Fault Injection and Chaos Testing

Istio's fault injection operates at the **proxy level**, which is fundamentally different from application-level chaos testing. Because the Envoy sidecar injects faults before the request reaches the application, you test the **entire resilience chain** — including client-side retries, timeouts, and circuit breakers. This is a **best practice** for validating that your timeout budgets and retry policies are correctly configured before a real outage.

A **pitfall** to watch for: fault injection rules are evaluated in order within a VirtualService. If your fault injection match rule comes after a broader catch-all route, it will never trigger. Therefore, always place specific match rules (including fault injection triggers) before general routes.

## mTLS and Zero-Trust Security

Istio implements **mutual TLS** transparently. istiod acts as the Certificate Authority, issuing short-lived X.509 certificates (default 24-hour validity) to each Envoy proxy via the **SDS (Secret Discovery Service)** API. This means certificates are never written to disk, reducing the attack surface.

The **trade-off** with strict mTLS is migration complexity. During a mesh rollout, you typically start with `PERMISSIVE` mode (accepts both plaintext and mTLS) and gradually move to `STRICT` mode namespace by namespace. However, leaving services in permissive mode long-term defeats the purpose of zero-trust networking.

## Observability with Istio Telemetry

One of Istio's most powerful capabilities is **automatic telemetry collection** without requiring any application instrumentation. The Envoy sidecars emit detailed metrics, access logs, and distributed traces for every request. This is valuable because debugging distributed systems without observability is nearly impossible — you cannot fix what you cannot see.

Istio integrates natively with **Prometheus** for metrics, **Jaeger** or **Zipkin** for distributed tracing, and **Kiali** for service mesh visualization. The following configuration demonstrates how to set up custom telemetry policies that control which metrics are collected and how traces are sampled:

```python
# Python script to validate Istio mesh health via the Kubernetes API
# This monitors sidecar injection status and mTLS connectivity
import subprocess
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class MeshHealthReport:
    # Aggregated health status for the Istio mesh
    total_pods: int = 0
    injected_pods: int = 0
    mtls_enabled_namespaces: int = 0
    total_namespaces: int = 0
    unhealthy_sidecars: List[str] = None

    def __post_init__(self) -> None:
        if self.unhealthy_sidecars is None:
            self.unhealthy_sidecars = []

    @property
    def injection_rate(self) -> float:
        if self.total_pods == 0:
            return 0.0
        return self.injected_pods / self.total_pods

    @property
    def mtls_coverage(self) -> float:
        if self.total_namespaces == 0:
            return 0.0
        return self.mtls_enabled_namespaces / self.total_namespaces


def check_sidecar_injection(namespace: str = "default") -> List[Dict]:
    # Check which pods have Envoy sidecars injected.
    # Pods without sidecars are outside the mesh and cannot
    # participate in mTLS or traffic management.
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", namespace, "-o", "json"],
        capture_output=True, text=True
    )
    pods_data = json.loads(result.stdout)
    pod_statuses = []

    for pod in pods_data.get("items", []):
        containers = [
            c["name"] for c in pod["spec"]["containers"]
        ]
        has_sidecar = "istio-proxy" in containers
        pod_statuses.append({
            "name": pod["metadata"]["name"],
            "namespace": namespace,
            "has_sidecar": has_sidecar,
            "container_count": len(containers),
            "ready": all(
                cs.get("ready", False)
                for cs in pod.get("status", {}).get(
                    "containerStatuses", []
                )
            ),
        })

    return pod_statuses


def validate_mesh_health(
    namespaces: Optional[List[str]] = None,
) -> MeshHealthReport:
    # Validate overall mesh health across namespaces.
    # Best practice: run this as a periodic health check.
    if namespaces is None:
        namespaces = ["default", "production", "staging"]

    report = MeshHealthReport()
    report.total_namespaces = len(namespaces)

    for ns in namespaces:
        pods = check_sidecar_injection(ns)
        report.total_pods += len(pods)

        injected = [p for p in pods if p["has_sidecar"]]
        report.injected_pods += len(injected)

        # Check for unhealthy sidecars (injected but not ready)
        for pod in injected:
            if not pod["ready"]:
                report.unhealthy_sidecars.append(
                    f"{pod['namespace']}/{pod['name']}"
                )

        # Check mTLS policy for namespace
        mtls_result = subprocess.run(
            [
                "kubectl", "get", "peerauthentication",
                "-n", ns, "-o", "json",
            ],
            capture_output=True, text=True,
        )
        mtls_data = json.loads(mtls_result.stdout)
        has_strict = any(
            item.get("spec", {}).get("mtls", {}).get("mode") == "STRICT"
            for item in mtls_data.get("items", [])
        )
        if has_strict:
            report.mtls_enabled_namespaces += 1

    return report
```

The monitoring script above demonstrates a **best practice** for production mesh operations: continuously validating that sidecar injection and mTLS enforcement are functioning correctly. Without this validation, misconfigurations (such as a namespace missing the `istio-injection=enabled` label) can silently leave services outside the mesh and therefore unprotected by mTLS.

## Summary and Key Takeaways

- **Istio's architecture** separates the data plane (Envoy sidecars) from the control plane (istiod), enabling transparent networking without application changes.
- **VirtualService** controls routing rules (canary splits, fault injection, retries) while **DestinationRule** configures post-routing behavior (load balancing, circuit breaking, connection pools).
- **mTLS** provides zero-trust service-to-service encryption with automatic certificate rotation managed by istiod.
- **Canary deployments** should use weighted routing for precise traffic control, combined with outlier detection as a circuit breaker.
- **Fault injection** at the proxy level is the best practice for validating resilience because it tests the entire networking stack, not just application code.
- **Observability** is automatically provided by Envoy sidecars — metrics, traces, and access logs require zero application instrumentation, which is one of the strongest arguments for adopting a service mesh.
- The primary **trade-off** is operational complexity and per-pod memory overhead from sidecar proxies, which must be weighed against the networking consistency and observability gains.
"""
    ),

    # --- 2. Load Balancing Algorithms ---
    (
        "service-mesh/load-balancing-algorithms-strategies",
        "Explain load balancing algorithms in depth including round-robin, least connections, consistent hashing, weighted algorithms, and Power of Two Choices (P2C), then implement multiple load balancing strategies in Python with health checking, connection draining, and automatic failover mechanisms.",
        r"""# Load Balancing Algorithms: Theory and Implementation

## Why Load Balancing Algorithm Choice Matters

Selecting the right load balancing algorithm is one of the most impactful architectural decisions for distributed systems. A poor choice can lead to **hot spots** (uneven load distribution), **cascade failures** (overwhelming recovering servers), or **cache thrashing** (inconsistent hashing destroying locality). The algorithm must account for heterogeneous server capacities, variable request costs, health states, and network conditions — therefore, no single algorithm is optimal for all scenarios.

## Algorithm Deep Dive

### Round-Robin

The simplest algorithm: distribute requests sequentially across all healthy backends. Its strength is **perfect fairness** when all servers are identical and all requests have equal cost. However, this assumption rarely holds in practice because servers often have different hardware specs, and request processing times vary enormously (a simple cache hit vs. a complex database query).

A **common mistake** is using plain round-robin with servers that have different capacities. If server A can handle 1000 RPS and server B can handle 500 RPS, round-robin sends equal traffic to both, eventually overwhelming server B.

### Least Connections

Routes each new request to the server with the **fewest active connections**. This naturally adapts to heterogeneous server speeds because faster servers complete requests sooner and therefore have fewer active connections, attracting more traffic. The **trade-off** is that it requires tracking connection state per backend, adding memory and coordination overhead.

A **pitfall**: during startup, all servers have zero connections, so least-connections degenerates into a thundering herd — all initial requests hit the same server. Best practice is to combine it with **slow start** (gradually ramping new/recovered servers).

### Consistent Hashing

Maps both servers and requests onto a **hash ring**, routing each request to the nearest server clockwise on the ring. When a server is added or removed, only ~1/N of requests are remapped (where N is the number of servers), preserving **cache locality**. This is critical for caching layers and stateful services.

Without **virtual nodes** (multiple points per server on the ring), consistent hashing produces extremely uneven distributions. Best practice is to use 100-200 virtual nodes per physical server.

### Power of Two Choices (P2C)

P2C is an elegant algorithm used by Envoy proxy and many modern load balancers. Instead of checking all backends, it **randomly selects two** and routes to whichever has fewer active requests. This achieves **exponentially better** load distribution than random selection (O(log log N) maximum load vs. O(log N / log log N)) with minimal overhead because it only examines two backends per request.

### Weighted Algorithms

Weighted variants of round-robin and least-connections assign a **weight** proportional to each server's capacity. A server with weight 3 receives three times the traffic of a server with weight 1. Weights can be static (based on hardware specs) or dynamic (adjusted based on response latency or CPU utilization).

## Implementation

```python
import hashlib
import random
import time
import threading
import bisect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Callable, Set
from enum import Enum, auto


class HealthState(Enum):
    HEALTHY = auto()
    UNHEALTHY = auto()
    DRAINING = auto()


@dataclass
class Backend:
    # Unique identifier for this backend server
    host: str
    port: int
    weight: int = 1
    max_connections: int = 1000
    active_connections: int = 0
    health_state: HealthState = HealthState.HEALTHY
    consecutive_failures: int = 0
    last_health_check: float = 0.0
    response_time_ema: float = 0.0  # exponential moving average

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def is_available(self) -> bool:
        return (
            self.health_state == HealthState.HEALTHY
            and self.active_connections < self.max_connections
        )

    def record_success(self, response_time: float) -> None:
        self.consecutive_failures = 0
        self.health_state = HealthState.HEALTHY
        # EMA with alpha=0.3 for smoothing
        alpha = 0.3
        self.response_time_ema = (
            alpha * response_time + (1 - alpha) * self.response_time_ema
        )

    def record_failure(self, threshold: int = 3) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= threshold:
            self.health_state = HealthState.UNHEALTHY


class LoadBalancer(ABC):
    # Base class for all load balancing strategies

    def __init__(self, backends: List[Backend]) -> None:
        self._backends = backends
        self._lock = threading.Lock()

    @abstractmethod
    def select(self, key: Optional[str] = None) -> Optional[Backend]:
        # Select a backend for the incoming request.
        # key is an optional routing key for hash-based algorithms.
        ...

    def healthy_backends(self) -> List[Backend]:
        return [b for b in self._backends if b.is_available]

    def add_backend(self, backend: Backend) -> None:
        with self._lock:
            self._backends.append(backend)
            self._on_backends_changed()

    def remove_backend(self, address: str) -> Optional[Backend]:
        with self._lock:
            for i, b in enumerate(self._backends):
                if b.address == address:
                    removed = self._backends.pop(i)
                    self._on_backends_changed()
                    return removed
        return None

    def _on_backends_changed(self) -> None:
        # Hook for subclasses to rebuild internal state
        pass


class RoundRobinBalancer(LoadBalancer):
    # Weighted round-robin using a smooth algorithm
    # that distributes requests evenly across weighted backends.

    def __init__(self, backends: List[Backend]) -> None:
        super().__init__(backends)
        self._current_weights: List[int] = [0] * len(backends)

    def select(self, key: Optional[str] = None) -> Optional[Backend]:
        with self._lock:
            available = self.healthy_backends()
            if not available:
                return None

            # Smooth weighted round-robin (Nginx algorithm)
            total_weight = sum(b.weight for b in available)
            best_idx = -1
            best_weight = -1

            for i, backend in enumerate(self._backends):
                if not backend.is_available:
                    continue
                self._current_weights[i] += backend.weight
                if self._current_weights[i] > best_weight:
                    best_weight = self._current_weights[i]
                    best_idx = i

            if best_idx >= 0:
                self._current_weights[best_idx] -= total_weight
                return self._backends[best_idx]
            return None

    def _on_backends_changed(self) -> None:
        self._current_weights = [0] * len(self._backends)


class LeastConnectionsBalancer(LoadBalancer):
    # Weighted least-connections: selects the backend with the
    # lowest ratio of active_connections / weight.

    def __init__(
        self, backends: List[Backend], slow_start_duration: float = 30.0
    ) -> None:
        super().__init__(backends)
        self._slow_start_duration = slow_start_duration
        self._join_times: Dict[str, float] = {}

    def select(self, key: Optional[str] = None) -> Optional[Backend]:
        with self._lock:
            available = self.healthy_backends()
            if not available:
                return None

            now = time.monotonic()
            best: Optional[Backend] = None
            best_score = float("inf")

            for b in available:
                effective_weight = self._effective_weight(b, now)
                if effective_weight <= 0:
                    effective_weight = 0.1
                score = b.active_connections / effective_weight
                if score < best_score:
                    best_score = score
                    best = b
            return best

    def _effective_weight(self, backend: Backend, now: float) -> float:
        # Slow-start: ramp weight linearly over the configured duration
        join_time = self._join_times.get(backend.address)
        if join_time is None:
            self._join_times[backend.address] = now
            return backend.weight * 0.1  # start at 10%

        elapsed = now - join_time
        if elapsed >= self._slow_start_duration:
            return float(backend.weight)

        ramp = max(0.1, elapsed / self._slow_start_duration)
        return backend.weight * ramp


class ConsistentHashBalancer(LoadBalancer):
    # Consistent hashing with virtual nodes for even distribution.
    # Supports bounded-load variant to prevent hot spots.

    def __init__(
        self,
        backends: List[Backend],
        virtual_nodes: int = 150,
        load_bound_factor: float = 1.25,
    ) -> None:
        super().__init__(backends)
        self._virtual_nodes = virtual_nodes
        self._load_bound_factor = load_bound_factor
        self._ring: List[int] = []
        self._ring_map: Dict[int, Backend] = {}
        self._rebuild_ring()

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def _rebuild_ring(self) -> None:
        self._ring = []
        self._ring_map = {}
        for backend in self._backends:
            for i in range(self._virtual_nodes):
                vnode_key = f"{backend.address}#{i}"
                h = self._hash(vnode_key)
                self._ring.append(h)
                self._ring_map[h] = backend
        self._ring.sort()

    def select(self, key: Optional[str] = None) -> Optional[Backend]:
        if not self._ring:
            return None
        if key is None:
            key = str(random.random())

        h = self._hash(key)
        # Find the first point on the ring >= hash
        idx = bisect.bisect_left(self._ring, h)
        if idx >= len(self._ring):
            idx = 0

        # Bounded-load: skip overloaded backends
        checked: Set[str] = set()
        available = self.healthy_backends()
        if not available:
            return None

        avg_load = (
            sum(b.active_connections for b in available) / len(available)
        )
        bound = max(1, avg_load * self._load_bound_factor)

        for offset in range(len(self._ring)):
            ring_idx = (idx + offset) % len(self._ring)
            backend = self._ring_map[self._ring[ring_idx]]

            if backend.address in checked:
                continue
            checked.add(backend.address)

            if backend.is_available and backend.active_connections <= bound:
                return backend

        # Fallback: return any available backend
        return available[0] if available else None

    def _on_backends_changed(self) -> None:
        self._rebuild_ring()


class P2CBalancer(LoadBalancer):
    # Power of Two Choices: randomly sample two backends
    # and pick the one with fewer active connections.
    # Used by Envoy, gRPC, and many modern proxies.

    def select(self, key: Optional[str] = None) -> Optional[Backend]:
        available = self.healthy_backends()
        if not available:
            return None
        if len(available) == 1:
            return available[0]

        # Randomly pick two distinct backends
        a, b = random.sample(available, 2)

        # Compare weighted load
        score_a = a.active_connections / max(a.weight, 1)
        score_b = b.active_connections / max(b.weight, 1)

        if score_a < score_b:
            return a
        elif score_b < score_a:
            return b
        # Tiebreak: prefer lower response time EMA
        return a if a.response_time_ema <= b.response_time_ema else b
```

### Health Checking and Connection Draining

```python
class HealthChecker:
    # Performs periodic active health checks on backends and
    # manages connection draining for graceful removal.

    def __init__(
        self,
        balancer: LoadBalancer,
        check_fn: Callable[[Backend], bool],
        interval: float = 5.0,
        unhealthy_threshold: int = 3,
        healthy_threshold: int = 2,
        drain_timeout: float = 30.0,
    ) -> None:
        self._balancer = balancer
        self._check_fn = check_fn
        self._interval = interval
        self._unhealthy_threshold = unhealthy_threshold
        self._healthy_threshold = healthy_threshold
        self._drain_timeout = drain_timeout
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._consecutive_ok: Dict[str, int] = {}
        self._drain_start: Dict[str, float] = {}

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=self._interval * 2)

    def drain_backend(self, address: str) -> None:
        # Initiate graceful connection draining for a backend.
        # The backend stops receiving new connections but
        # existing connections are allowed to complete.
        for b in self._balancer._backends:
            if b.address == address:
                b.health_state = HealthState.DRAINING
                self._drain_start[address] = time.monotonic()
                break

    def _run_loop(self) -> None:
        while self._running:
            for backend in list(self._balancer._backends):
                self._check_one(backend)
                self._handle_draining(backend)
            time.sleep(self._interval)

    def _check_one(self, backend: Backend) -> None:
        if backend.health_state == HealthState.DRAINING:
            return

        try:
            is_healthy = self._check_fn(backend)
        except Exception:
            is_healthy = False

        backend.last_health_check = time.monotonic()

        if is_healthy:
            self._consecutive_ok.setdefault(backend.address, 0)
            self._consecutive_ok[backend.address] += 1
            backend.consecutive_failures = 0

            if (
                backend.health_state == HealthState.UNHEALTHY
                and self._consecutive_ok[backend.address]
                >= self._healthy_threshold
            ):
                backend.health_state = HealthState.HEALTHY
        else:
            self._consecutive_ok[backend.address] = 0
            backend.record_failure(self._unhealthy_threshold)

    def _handle_draining(self, backend: Backend) -> None:
        if backend.health_state != HealthState.DRAINING:
            return

        addr = backend.address
        start = self._drain_start.get(addr, 0)
        elapsed = time.monotonic() - start

        # Remove if all connections drained or timeout exceeded
        if backend.active_connections == 0 or elapsed > self._drain_timeout:
            self._balancer.remove_backend(addr)
            self._drain_start.pop(addr, None)
```

## Usage Example: Assembling the System

The following example demonstrates how to combine a load balancer with health checking for a production deployment. The key insight is that the balancer and health checker are decoupled — you can swap algorithms without changing health check logic:

```python
# Assemble a production-ready load balancer with health checking
import socket
from typing import Optional


def tcp_health_check(backend: Backend) -> bool:
    # Simple TCP connect check — verifies the backend is accepting connections.
    # For HTTP services, a best practice is to check a /health endpoint instead.
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect((backend.host, backend.port))
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def create_production_balancer(
    algorithm: str = "p2c",
) -> tuple:
    # Factory function to create a balancer with health checking.
    # Returns (balancer, health_checker) tuple.
    backends = [
        Backend(host="10.0.1.1", port=8080, weight=3, max_connections=500),
        Backend(host="10.0.1.2", port=8080, weight=2, max_connections=500),
        Backend(host="10.0.1.3", port=8080, weight=1, max_connections=300),
    ]

    # Select algorithm based on use case
    balancer: LoadBalancer
    if algorithm == "p2c":
        balancer = P2CBalancer(backends)
    elif algorithm == "consistent_hash":
        balancer = ConsistentHashBalancer(backends, virtual_nodes=150)
    elif algorithm == "least_conn":
        balancer = LeastConnectionsBalancer(backends, slow_start_duration=30.0)
    else:
        balancer = RoundRobinBalancer(backends)

    # Attach health checker with appropriate thresholds
    checker = HealthChecker(
        balancer=balancer,
        check_fn=tcp_health_check,
        interval=5.0,
        unhealthy_threshold=3,   # 3 failures to mark unhealthy
        healthy_threshold=2,     # 2 successes to mark healthy again
        drain_timeout=30.0,      # max 30s to drain connections
    )

    return balancer, checker


# Example usage
balancer, checker = create_production_balancer("p2c")
checker.start()

# Route a request — the balancer automatically skips unhealthy backends
selected = balancer.select(key="user-12345")
if selected:
    selected.active_connections += 1
    # ... forward request to selected.address ...
    selected.record_success(response_time=0.045)
    selected.active_connections -= 1
```

## Algorithm Selection Guide

| Algorithm | Best For | Weakness |
|-----------|----------|----------|
| Round-Robin | Homogeneous servers, uniform requests | Ignores server load |
| Least Connections | Variable request durations | Thundering herd on startup |
| Consistent Hash | Caching layers, sticky sessions | Hot spots without virtual nodes |
| P2C | General purpose, large clusters | Slightly random distribution |
| Weighted variants | Heterogeneous hardware | Requires accurate weight tuning |

## Summary and Key Takeaways

- **Round-robin** is simple but only fair when servers and requests are homogeneous; use **weighted round-robin** for heterogeneous capacity.
- **Least connections** naturally adapts to variable processing times but requires **slow start** to avoid thundering herd during server recovery.
- **Consistent hashing** preserves cache locality with O(1/N) remapping on topology changes, but demands **virtual nodes** (150+) for even distribution and bounded-load checks to prevent hot spots.
- **P2C (Power of Two Choices)** delivers near-optimal distribution with minimal overhead, which is why it is the default in Envoy and gRPC — therefore it should be the default choice for most new systems.
- **Health checking** must combine active probes with passive failure tracking, and **connection draining** is essential for graceful backend removal without dropping in-flight requests.
- The primary **trade-off** across all algorithms is between distribution quality and state tracking overhead; more sophisticated algorithms require more per-request coordination.
"""
    ),

    # --- 3. API Gateway Patterns ---
    (
        "service-mesh/api-gateway-patterns-implementation",
        "Explain API gateway patterns in depth covering rate limiting, authentication, request transformation, response caching, and circuit breaking, then implement a production-grade API gateway in Python with a plugin architecture for middleware chains, JWT validation, and token bucket rate limiting.",
        r"""# API Gateway Patterns: Architecture and Implementation

## Why API Gateways Are Essential

An **API gateway** is the single entry point for all client requests into a microservice architecture. Without one, clients must know the addresses of individual services, handle authentication independently, and manage cross-cutting concerns like rate limiting and caching on their own. This creates tight coupling between clients and services and violates the **separation of concerns** principle because business logic gets entangled with infrastructure concerns.

The API gateway pattern consolidates these responsibilities into a dedicated layer that handles **authentication**, **rate limiting**, **request routing**, **response transformation**, **caching**, and **circuit breaking**. This is fundamentally different from a simple reverse proxy because the gateway applies business-aware policies — for example, different rate limits for free vs. premium users, or transforming a single client request into multiple backend calls (the **Backend for Frontend** pattern).

## Core Gateway Patterns

### Rate Limiting

Rate limiting prevents abuse and ensures fair resource allocation. The two most common algorithms are **Token Bucket** (allows bursts up to a maximum, then enforces a steady rate) and **Sliding Window** (counts requests in a rolling time window). A **common mistake** is implementing rate limiting per-instance rather than globally — if your gateway has 10 instances and each allows 100 RPS, the actual limit is 1000 RPS. Therefore, production rate limiters must use a shared store like Redis.

### Authentication and Authorization

The gateway is the **best practice** location for validating authentication tokens because it centralizes the logic and prevents unauthenticated requests from reaching backend services. **JWT validation** is the most common pattern: the gateway verifies the token signature, checks expiration, extracts claims, and passes user identity to backends via trusted headers.

A **pitfall** with JWT validation at the gateway is clock skew — if the gateway server's clock is ahead of the auth server's clock, tokens may appear expired prematurely. Therefore, always configure a clock skew tolerance (typically 30-60 seconds).

### Request and Response Transformation

Gateways frequently transform requests to decouple client API contracts from backend service interfaces. This includes header injection (adding correlation IDs, user identity), body transformation (converting between JSON and XML), path rewriting, and response filtering (removing internal fields before sending to external clients).

### Circuit Breaking

The gateway should implement **circuit breaking** for each backend to prevent cascade failures. When a backend starts failing, the circuit opens and the gateway returns errors immediately without forwarding requests, giving the backend time to recover. However, the **trade-off** is that aggressive circuit breaking can amplify partial outages — if one instance is unhealthy but others are fine, opening the circuit to the entire service is too broad.

## Implementation

```python
import time
import json
import hmac
import base64
import hashlib
import threading
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import (
    List, Optional, Dict, Any, Callable, Tuple, Type, Union
)
from enum import Enum, auto
from collections import deque
from functools import wraps


# --- Core Request/Response Types ---

@dataclass
class GatewayRequest:
    # Represents an incoming HTTP request to the gateway
    method: str
    path: str
    headers: Dict[str, str] = field(default_factory=dict)
    query_params: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    client_ip: str = "0.0.0.0"
    # Mutable context passed through the middleware chain
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "application/json")

    def json_body(self) -> Optional[Dict[str, Any]]:
        if self.body:
            return json.loads(self.body.decode("utf-8"))
        return None


@dataclass
class GatewayResponse:
    # Represents a response from the gateway
    status_code: int
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None

    @staticmethod
    def json_response(
        status: int, data: Dict[str, Any]
    ) -> "GatewayResponse":
        return GatewayResponse(
            status_code=status,
            headers={"content-type": "application/json"},
            body=json.dumps(data).encode("utf-8"),
        )

    @staticmethod
    def error(status: int, message: str) -> "GatewayResponse":
        return GatewayResponse.json_response(
            status, {"error": message, "status": status}
        )


# --- Middleware Plugin System ---

class Middleware(ABC):
    # Base class for all gateway middleware plugins.
    # Middleware forms a chain: each plugin can modify the request,
    # short-circuit with a response, or pass to the next handler.

    @abstractmethod
    def process(
        self,
        request: GatewayRequest,
        next_handler: Callable[[GatewayRequest], GatewayResponse],
    ) -> GatewayResponse:
        ...


class MiddlewareChain:
    # Composes middleware into an ordered processing pipeline.
    # Each middleware wraps the next, forming an onion-layer pattern.

    def __init__(self) -> None:
        self._middlewares: List[Middleware] = []

    def add(self, middleware: Middleware) -> "MiddlewareChain":
        self._middlewares.append(middleware)
        return self

    def execute(
        self,
        request: GatewayRequest,
        final_handler: Callable[[GatewayRequest], GatewayResponse],
    ) -> GatewayResponse:
        # Build the chain from inside out
        handler = final_handler
        for mw in reversed(self._middlewares):
            # Capture mw in closure properly
            handler = self._wrap(mw, handler)
        return handler(request)

    @staticmethod
    def _wrap(
        mw: Middleware,
        next_handler: Callable[[GatewayRequest], GatewayResponse],
    ) -> Callable[[GatewayRequest], GatewayResponse]:
        def wrapped(req: GatewayRequest) -> GatewayResponse:
            return mw.process(req, next_handler)
        return wrapped


# --- JWT Authentication Middleware ---

class JWTAuthMiddleware(Middleware):
    # Validates JWT tokens from the Authorization header.
    # Extracts claims and adds user identity to request context.

    def __init__(
        self,
        secret: str,
        algorithm: str = "HS256",
        clock_skew_seconds: int = 60,
        exempt_paths: Optional[List[str]] = None,
    ) -> None:
        self._secret = secret.encode("utf-8")
        self._algorithm = algorithm
        self._clock_skew = clock_skew_seconds
        self._exempt_paths = exempt_paths or ["/health", "/metrics"]

    def process(
        self,
        request: GatewayRequest,
        next_handler: Callable[[GatewayRequest], GatewayResponse],
    ) -> GatewayResponse:
        # Skip auth for exempt paths
        if request.path in self._exempt_paths:
            return next_handler(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return GatewayResponse.error(401, "Missing Bearer token")

        token = auth_header[7:]
        claims = self._validate_token(token)
        if claims is None:
            return GatewayResponse.error(401, "Invalid or expired token")

        # Add claims to request context for downstream use
        request.context["user_id"] = claims.get("sub")
        request.context["roles"] = claims.get("roles", [])
        request.context["token_claims"] = claims

        # Forward user identity as a trusted header
        request.headers["x-user-id"] = str(claims.get("sub", ""))
        request.headers["x-user-roles"] = ",".join(
            claims.get("roles", [])
        )

        return next_handler(request)

    def _validate_token(
        self, token: str
    ) -> Optional[Dict[str, Any]]:
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None

            # Decode header and payload
            payload_b64 = parts[1]
            # Add padding if needed
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding

            payload = json.loads(
                base64.urlsafe_b64decode(payload_b64).decode("utf-8")
            )

            # Verify signature
            signing_input = f"{parts[0]}.{parts[1]}".encode("utf-8")
            expected_sig = base64.urlsafe_b64encode(
                hmac.new(
                    self._secret, signing_input, hashlib.sha256
                ).digest()
            ).rstrip(b"=").decode("utf-8")

            if not hmac.compare_digest(expected_sig, parts[2]):
                return None

            # Check expiration with clock skew tolerance
            now = time.time()
            if "exp" in payload:
                if now > payload["exp"] + self._clock_skew:
                    return None

            return payload
        except Exception:
            return None


# --- Token Bucket Rate Limiter ---

class TokenBucketRateLimiter(Middleware):
    # Per-client rate limiting using the token bucket algorithm.
    # Allows short bursts up to bucket capacity, then enforces
    # a steady request rate.

    def __init__(
        self,
        rate: float = 100.0,      # tokens per second
        burst: int = 200,          # max bucket capacity
        key_fn: Optional[Callable[[GatewayRequest], str]] = None,
    ) -> None:
        self._rate = rate
        self._burst = burst
        self._key_fn = key_fn or (lambda r: r.client_ip)
        self._buckets: Dict[str, Tuple[float, float]] = {}
        self._lock = threading.Lock()

    def process(
        self,
        request: GatewayRequest,
        next_handler: Callable[[GatewayRequest], GatewayResponse],
    ) -> GatewayResponse:
        key = self._key_fn(request)
        allowed, retry_after = self._try_consume(key)

        if not allowed:
            resp = GatewayResponse.error(
                429, "Rate limit exceeded"
            )
            resp.headers["retry-after"] = str(int(retry_after) + 1)
            resp.headers["x-ratelimit-limit"] = str(self._burst)
            resp.headers["x-ratelimit-remaining"] = "0"
            return resp

        response = next_handler(request)
        return response

    def _try_consume(
        self, key: str, tokens: float = 1.0
    ) -> Tuple[bool, float]:
        with self._lock:
            now = time.monotonic()

            if key in self._buckets:
                available, last_time = self._buckets[key]
                elapsed = now - last_time
                available = min(
                    self._burst,
                    available + elapsed * self._rate,
                )
            else:
                available = float(self._burst)
                last_time = now

            if available >= tokens:
                self._buckets[key] = (available - tokens, now)
                return True, 0.0
            else:
                wait = (tokens - available) / self._rate
                self._buckets[key] = (available, now)
                return False, wait
```

### Response Caching and Circuit Breaking Middleware

```python
class ResponseCacheMiddleware(Middleware):
    # Caches GET responses with configurable TTL.
    # Uses path + query params as cache key.

    def __init__(
        self,
        default_ttl: float = 60.0,
        max_entries: int = 10000,
        cacheable_statuses: Optional[set] = None,
    ) -> None:
        self._default_ttl = default_ttl
        self._max_entries = max_entries
        self._cacheable = cacheable_statuses or {200, 301, 404}
        self._cache: Dict[str, Tuple[GatewayResponse, float]] = {}
        self._lock = threading.Lock()

    def process(
        self,
        request: GatewayRequest,
        next_handler: Callable[[GatewayRequest], GatewayResponse],
    ) -> GatewayResponse:
        # Only cache GET requests
        if request.method.upper() != "GET":
            return next_handler(request)

        cache_key = self._make_key(request)

        # Check cache
        with self._lock:
            if cache_key in self._cache:
                response, expires_at = self._cache[cache_key]
                if time.monotonic() < expires_at:
                    response.headers["x-cache"] = "HIT"
                    return response
                else:
                    del self._cache[cache_key]

        # Cache miss — forward to backend
        response = next_handler(request)

        if response.status_code in self._cacheable:
            with self._lock:
                if len(self._cache) >= self._max_entries:
                    # Evict oldest entry
                    oldest = min(
                        self._cache, key=lambda k: self._cache[k][1]
                    )
                    del self._cache[oldest]
                self._cache[cache_key] = (
                    response,
                    time.monotonic() + self._default_ttl,
                )

        response.headers["x-cache"] = "MISS"
        return response

    def _make_key(self, request: GatewayRequest) -> str:
        params = "&".join(
            f"{k}={v}"
            for k, v in sorted(request.query_params.items())
        )
        return f"{request.path}?{params}"


class CircuitBreakerState(Enum):
    CLOSED = auto()    # Normal operation
    OPEN = auto()      # Failing, reject immediately
    HALF_OPEN = auto() # Testing recovery


class CircuitBreakerMiddleware(Middleware):
    # Circuit breaker per backend route.
    # Transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_requests: int = 3,
        failure_statuses: Optional[set] = None,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max = half_open_max_requests
        self._failure_statuses = failure_statuses or {500, 502, 503, 504}
        self._circuits: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _get_circuit(self, route: str) -> Dict[str, Any]:
        if route not in self._circuits:
            self._circuits[route] = {
                "state": CircuitBreakerState.CLOSED,
                "failures": 0,
                "last_failure_time": 0.0,
                "half_open_requests": 0,
                "half_open_successes": 0,
            }
        return self._circuits[route]

    def process(
        self,
        request: GatewayRequest,
        next_handler: Callable[[GatewayRequest], GatewayResponse],
    ) -> GatewayResponse:
        route = request.path.split("/")[1] if "/" in request.path else "default"

        with self._lock:
            circuit = self._get_circuit(route)
            state = circuit["state"]

            if state == CircuitBreakerState.OPEN:
                elapsed = time.monotonic() - circuit["last_failure_time"]
                if elapsed >= self._recovery_timeout:
                    circuit["state"] = CircuitBreakerState.HALF_OPEN
                    circuit["half_open_requests"] = 0
                    circuit["half_open_successes"] = 0
                    state = CircuitBreakerState.HALF_OPEN
                else:
                    return GatewayResponse.error(
                        503, "Circuit breaker open, service unavailable"
                    )

            if state == CircuitBreakerState.HALF_OPEN:
                if circuit["half_open_requests"] >= self._half_open_max:
                    return GatewayResponse.error(
                        503, "Circuit breaker half-open, at capacity"
                    )
                circuit["half_open_requests"] += 1

        response = next_handler(request)

        with self._lock:
            circuit = self._get_circuit(route)
            is_failure = response.status_code in self._failure_statuses

            if circuit["state"] == CircuitBreakerState.HALF_OPEN:
                if is_failure:
                    circuit["state"] = CircuitBreakerState.OPEN
                    circuit["last_failure_time"] = time.monotonic()
                else:
                    circuit["half_open_successes"] += 1
                    if circuit["half_open_successes"] >= self._half_open_max:
                        circuit["state"] = CircuitBreakerState.CLOSED
                        circuit["failures"] = 0
            elif circuit["state"] == CircuitBreakerState.CLOSED:
                if is_failure:
                    circuit["failures"] += 1
                    if circuit["failures"] >= self._failure_threshold:
                        circuit["state"] = CircuitBreakerState.OPEN
                        circuit["last_failure_time"] = time.monotonic()
                else:
                    circuit["failures"] = 0

        return response


# --- Gateway Assembly ---

def create_gateway() -> MiddlewareChain:
    # Assemble the gateway with the full middleware chain.
    chain = MiddlewareChain()
    chain.add(TokenBucketRateLimiter(rate=100, burst=200))
    chain.add(JWTAuthMiddleware(secret="your-secret-key-here"))
    chain.add(ResponseCacheMiddleware(default_ttl=30.0))
    chain.add(CircuitBreakerMiddleware(failure_threshold=5))
    return chain
```

### Request Routing and Transformation

The gateway routes incoming requests to backend services based on path patterns, rewrites URLs, and injects headers. This **decouples** the public API contract from internal service topology, which means backend services can be reorganized without affecting clients:

```python
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Callable, Pattern


@dataclass
class RouteRule:
    # Defines a routing rule from a public path pattern to a backend service
    path_pattern: str
    backend_host: str
    backend_port: int
    strip_prefix: Optional[str] = None
    add_headers: Optional[Dict[str, str]] = None
    methods: Optional[List[str]] = None
    # Compiled regex for efficient matching
    _compiled: Optional[Pattern] = None

    def __post_init__(self) -> None:
        self._compiled = re.compile(self.path_pattern)

    def matches(self, request: GatewayRequest) -> bool:
        if self.methods and request.method.upper() not in self.methods:
            return False
        return bool(self._compiled.match(request.path))

    def rewrite(self, request: GatewayRequest) -> GatewayRequest:
        # Apply path rewriting and header injection
        if self.strip_prefix and request.path.startswith(self.strip_prefix):
            request.path = request.path[len(self.strip_prefix):] or "/"

        if self.add_headers:
            request.headers.update(self.add_headers)

        # Add routing metadata for downstream tracing
        request.headers["x-forwarded-host"] = request.headers.get("host", "")
        request.headers["x-request-start"] = str(time.time())
        return request


class RequestRouter:
    # Routes requests to appropriate backend services
    # based on path patterns and HTTP methods.

    def __init__(self) -> None:
        self._rules: List[RouteRule] = []
        self._default_backend: Optional[RouteRule] = None

    def add_route(self, rule: RouteRule) -> "RequestRouter":
        self._rules.append(rule)
        return self

    def set_default(self, rule: RouteRule) -> "RequestRouter":
        self._default_backend = rule
        return self

    def resolve(self, request: GatewayRequest) -> Optional[RouteRule]:
        # Find the first matching route rule.
        # Rules are evaluated in order, therefore more specific
        # patterns should be registered before broader ones.
        for rule in self._rules:
            if rule.matches(request):
                return rule
        return self._default_backend


# Best practice: define routes declaratively
def configure_routes() -> RequestRouter:
    router = RequestRouter()
    router.add_route(RouteRule(
        path_pattern=r"/api/v1/users.*",
        backend_host="user-service",
        backend_port=8081,
        strip_prefix="/api/v1",
        add_headers={"x-service": "users"},
        methods=["GET", "POST", "PUT", "DELETE"],
    ))
    router.add_route(RouteRule(
        path_pattern=r"/api/v1/orders.*",
        backend_host="order-service",
        backend_port=8082,
        strip_prefix="/api/v1",
        add_headers={"x-service": "orders"},
    ))
    router.add_route(RouteRule(
        path_pattern=r"/api/v1/products.*",
        backend_host="product-service",
        backend_port=8083,
        strip_prefix="/api/v1",
        add_headers={"x-service": "products"},
        methods=["GET"],  # read-only for products
    ))
    return router
```

## Summary and Key Takeaways

- An **API gateway** is the single entry point that consolidates authentication, rate limiting, caching, and circuit breaking — therefore decoupling clients from internal service topology.
- **Token bucket rate limiting** is the best practice algorithm because it allows controlled bursts while enforcing a steady-state rate; however, it must use shared state (Redis) for multi-instance deployments.
- **JWT validation** at the gateway centralizes auth and prevents unauthenticated requests from reaching backends, but requires clock skew tolerance to avoid premature token rejection.
- The **middleware chain pattern** (onion architecture) enables composable, testable plugins where each middleware can short-circuit the request or delegate to the next handler.
- **Response caching** should only apply to GET requests with cacheable status codes, and cache keys must include all request parameters that affect the response.
- **Request routing** with path rewriting decouples public API contracts from internal service topology, allowing backend reorganization without breaking client integrations.
- **Circuit breaking** at the gateway prevents cascade failures but the **trade-off** is that overly aggressive thresholds can amplify partial outages by rejecting requests that healthy backends could serve.
- A **pitfall** is applying gateway patterns without proper observability — always emit metrics for rate limit hits, cache hit ratios, circuit breaker state transitions, and auth failures.
"""
    ),

    # --- 4. gRPC Service Patterns ---
    (
        "service-mesh/grpc-service-patterns-streaming",
        "Explain gRPC service patterns in depth covering protobuf schema design, all four streaming types (unary, server streaming, client streaming, bidirectional), interceptors, health checking, and load balancing, then implement a complete gRPC service in Python with all stream types, custom interceptors, and graceful shutdown.",
        r"""# gRPC Service Patterns: Streaming, Interceptors, and Production Readiness

## Why gRPC Over REST

**gRPC** is a high-performance RPC framework built on HTTP/2 and **Protocol Buffers** (protobuf). Compared to REST+JSON, gRPC offers several fundamental advantages: **binary serialization** (protobuf is 3-10x smaller and faster than JSON), **HTTP/2 multiplexing** (multiple concurrent RPCs over a single TCP connection), **streaming** (server, client, and bidirectional), and **strong typing** via `.proto` schema definitions that generate client and server code in any language.

However, the **trade-off** is reduced human readability (binary protocol), more complex debugging (cannot curl a gRPC endpoint easily), and limited browser support (requiring gRPC-Web or a gateway proxy). Therefore, gRPC is best suited for **internal service-to-service communication** where performance and type safety outweigh developer convenience, while REST remains preferred for public-facing APIs.

## Protobuf Schema Design

### Best Practices for Schema Evolution

Protobuf's wire format supports **backward and forward compatibility** through field numbering. A **common mistake** is reusing deleted field numbers — this causes silent data corruption when old clients communicate with new servers. Therefore, always use `reserved` to permanently retire deleted field numbers.

```protobuf
// order_service.proto
// Schema for an order management gRPC service
// demonstrating all four RPC types

syntax = "proto3";

package orders.v1;

option go_package = "github.com/example/orders/v1";

// Import for well-known types
import "google/protobuf/timestamp.proto";
import "google/protobuf/empty.proto";

// --- Messages ---

message OrderItem {
  string product_id = 1;
  string product_name = 2;
  int32 quantity = 3;
  // Use int64 cents to avoid floating-point precision issues
  // This is a best practice for financial amounts
  int64 price_cents = 4;
  map<string, string> metadata = 5;
}

message Order {
  string order_id = 1;
  string customer_id = 2;
  repeated OrderItem items = 3;
  OrderStatus status = 4;
  int64 total_cents = 5;
  google.protobuf.Timestamp created_at = 6;
  google.protobuf.Timestamp updated_at = 7;

  // Reserved field numbers from deleted fields
  // NEVER reuse these numbers
  reserved 8, 9;
  reserved "legacy_discount", "old_address";
}

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_CONFIRMED = 2;
  ORDER_STATUS_PROCESSING = 3;
  ORDER_STATUS_SHIPPED = 4;
  ORDER_STATUS_DELIVERED = 5;
  ORDER_STATUS_CANCELLED = 6;
}

message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderItem items = 2;
  string idempotency_key = 3;
}

message GetOrderRequest {
  string order_id = 1;
}

message OrderUpdate {
  string order_id = 1;
  OrderStatus new_status = 2;
  string update_message = 3;
  google.protobuf.Timestamp timestamp = 4;
}

message OrderFilter {
  string customer_id = 1;
  repeated OrderStatus statuses = 2;
  google.protobuf.Timestamp created_after = 3;
}

message BatchOrderItem {
  string customer_id = 1;
  repeated OrderItem items = 2;
}

message BatchOrderResult {
  int32 total_received = 1;
  int32 total_created = 2;
  int32 total_failed = 3;
  repeated string created_order_ids = 4;
}

// --- Service Definition ---
// Demonstrates all four RPC types

service OrderService {
  // Unary: single request, single response
  rpc CreateOrder(CreateOrderRequest) returns (Order);
  rpc GetOrder(GetOrderRequest) returns (Order);

  // Server streaming: single request, stream of responses
  rpc WatchOrderUpdates(OrderFilter) returns (stream OrderUpdate);

  // Client streaming: stream of requests, single response
  rpc BatchCreateOrders(stream BatchOrderItem) returns (BatchOrderResult);

  // Bidirectional streaming: stream both directions
  rpc LiveOrderChat(stream OrderUpdate) returns (stream OrderUpdate);
}
```

## Python gRPC Implementation

```python
import grpc
import time
import signal
import logging
import threading
import uuid
from concurrent import futures
from typing import Iterator, Optional, Dict, List, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Domain Models ---
# In production these would be generated from the .proto file.
# Shown here as plain classes for clarity.

class OrderStatus(IntEnum):
    UNSPECIFIED = 0
    PENDING = 1
    CONFIRMED = 2
    PROCESSING = 3
    SHIPPED = 4
    DELIVERED = 5
    CANCELLED = 6


@dataclass
class OrderItem:
    product_id: str
    product_name: str
    quantity: int
    price_cents: int
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class Order:
    order_id: str
    customer_id: str
    items: List[OrderItem]
    status: OrderStatus
    total_cents: int
    created_at: datetime
    updated_at: datetime


@dataclass
class OrderUpdate:
    order_id: str
    new_status: OrderStatus
    update_message: str
    timestamp: datetime


# --- Interceptors ---

class LoggingInterceptor(grpc.ServerInterceptor):
    # Logs every RPC call with method name, duration, and status.
    # This is essential for observability in production gRPC services.

    def intercept_service(
        self, continuation: Callable, handler_call_details: grpc.HandlerCallDetails
    ) -> Any:
        method = handler_call_details.method
        start_time = time.monotonic()
        logger.info(f"RPC started: {method}")

        handler = continuation(handler_call_details)

        # Wrap the handler to capture completion
        if handler is None:
            logger.warning(f"No handler found for {method}")
            return handler

        return handler


class AuthInterceptor(grpc.ServerInterceptor):
    # Validates bearer tokens from gRPC metadata.
    # Extracts user identity and injects it into the context.

    def __init__(self, valid_tokens: Dict[str, str]) -> None:
        # Maps token -> user_id for demonstration
        self._valid_tokens = valid_tokens
        self._public_methods = {"/grpc.health.v1.Health/Check"}

    def intercept_service(
        self, continuation: Callable, handler_call_details: grpc.HandlerCallDetails
    ) -> Any:
        method = handler_call_details.method

        # Skip auth for health checks
        if method in self._public_methods:
            return continuation(handler_call_details)

        # Extract metadata
        metadata = dict(handler_call_details.invocation_metadata or [])
        auth_value = metadata.get("authorization", "")

        if not auth_value.startswith("Bearer "):
            return self._unauthenticated_handler()

        token = auth_value[7:]
        if token not in self._valid_tokens:
            return self._unauthenticated_handler()

        return continuation(handler_call_details)

    def _unauthenticated_handler(self) -> grpc.RpcMethodHandler:
        def abort(request, context):
            context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Invalid or missing authentication token",
            )
        return grpc.unary_unary_rpc_method_handler(abort)


class RateLimitInterceptor(grpc.ServerInterceptor):
    # Per-method rate limiting using a token bucket.
    # Prevents any single client from overwhelming the service.

    def __init__(self, rate: float = 100.0, burst: int = 200) -> None:
        self._rate = rate
        self._burst = burst
        self._buckets: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def intercept_service(
        self, continuation: Callable, handler_call_details: grpc.HandlerCallDetails
    ) -> Any:
        metadata = dict(handler_call_details.invocation_metadata or [])
        client_id = metadata.get("x-client-id", "anonymous")

        if not self._try_consume(client_id):
            def rate_limited(request, context):
                context.abort(
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    "Rate limit exceeded, retry after backoff",
                )
            return grpc.unary_unary_rpc_method_handler(rate_limited)

        return continuation(handler_call_details)

    def _try_consume(self, client_id: str) -> bool:
        with self._lock:
            now = time.monotonic()
            if client_id not in self._buckets:
                self._buckets[client_id] = [float(self._burst), now]

            available, last_time = self._buckets[client_id]
            elapsed = now - last_time
            available = min(self._burst, available + elapsed * self._rate)

            if available >= 1.0:
                self._buckets[client_id] = [available - 1.0, now]
                return True
            self._buckets[client_id] = [available, now]
            return False


# --- Service Implementation ---

class OrderServiceImpl:
    # Implements all four RPC types for the OrderService.

    def __init__(self) -> None:
        self._orders: Dict[str, Order] = {}
        self._watchers: Dict[str, List[threading.Event]] = {}
        self._updates: Dict[str, List[OrderUpdate]] = {}
        self._lock = threading.Lock()

    def CreateOrder(
        self, request: Dict[str, Any], context: grpc.ServicerContext
    ) -> Order:
        # Unary RPC: creates a single order and returns it.
        order_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        items = [
            OrderItem(
                product_id=item["product_id"],
                product_name=item["product_name"],
                quantity=item["quantity"],
                price_cents=item["price_cents"],
            )
            for item in request.get("items", [])
        ]

        total = sum(item.price_cents * item.quantity for item in items)

        order = Order(
            order_id=order_id,
            customer_id=request["customer_id"],
            items=items,
            status=OrderStatus.PENDING,
            total_cents=total,
            created_at=now,
            updated_at=now,
        )

        with self._lock:
            self._orders[order_id] = order

        logger.info(f"Created order {order_id} for customer {request['customer_id']}")
        return order

    def GetOrder(
        self, request: Dict[str, Any], context: grpc.ServicerContext
    ) -> Order:
        # Unary RPC: retrieves an order by ID.
        order_id = request["order_id"]
        with self._lock:
            order = self._orders.get(order_id)

        if order is None:
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Order {order_id} not found",
            )

        return order

    def WatchOrderUpdates(
        self, request: Dict[str, Any], context: grpc.ServicerContext
    ) -> Iterator[OrderUpdate]:
        # Server streaming RPC: sends order updates as they occur.
        # The client receives a stream of updates matching the filter.
        customer_id = request.get("customer_id", "")
        logger.info(f"Client watching updates for customer {customer_id}")

        event = threading.Event()
        watcher_key = customer_id or "__all__"

        with self._lock:
            if watcher_key not in self._watchers:
                self._watchers[watcher_key] = []
            self._watchers[watcher_key].append(event)

        try:
            while context.is_active():
                event.wait(timeout=1.0)
                if event.is_set():
                    event.clear()
                    with self._lock:
                        updates = self._updates.pop(watcher_key, [])
                    for update in updates:
                        yield update
        finally:
            with self._lock:
                watchers = self._watchers.get(watcher_key, [])
                if event in watchers:
                    watchers.remove(event)

    def BatchCreateOrders(
        self, request_iterator: Iterator[Dict[str, Any]],
        context: grpc.ServicerContext,
    ) -> Dict[str, Any]:
        # Client streaming RPC: receives a stream of order items
        # and returns a single summary when the stream completes.
        total_received = 0
        total_created = 0
        total_failed = 0
        created_ids: List[str] = []

        for batch_item in request_iterator:
            total_received += 1
            try:
                order = self.CreateOrder(
                    {
                        "customer_id": batch_item["customer_id"],
                        "items": batch_item.get("items", []),
                    },
                    context,
                )
                total_created += 1
                created_ids.append(order.order_id)
            except Exception as e:
                logger.error(f"Failed to create order: {e}")
                total_failed += 1

        return {
            "total_received": total_received,
            "total_created": total_created,
            "total_failed": total_failed,
            "created_order_ids": created_ids,
        }

    def LiveOrderChat(
        self, request_iterator: Iterator[OrderUpdate],
        context: grpc.ServicerContext,
    ) -> Iterator[OrderUpdate]:
        # Bidirectional streaming RPC: both client and server
        # send updates concurrently. This enables real-time
        # collaborative order management.
        for incoming_update in request_iterator:
            if not context.is_active():
                break

            logger.info(
                f"Received update for order {incoming_update.order_id}: "
                f"{incoming_update.update_message}"
            )

            # Process and send acknowledgment update
            ack = OrderUpdate(
                order_id=incoming_update.order_id,
                new_status=incoming_update.new_status,
                update_message=f"ACK: {incoming_update.update_message}",
                timestamp=datetime.now(timezone.utc),
            )
            yield ack


# --- Server Lifecycle with Graceful Shutdown ---

class GrpcServer:
    # Manages gRPC server lifecycle including graceful shutdown.
    # Best practice: always implement graceful shutdown to avoid
    # dropping in-flight RPCs during deployments.

    def __init__(
        self,
        port: int = 50051,
        max_workers: int = 10,
        grace_period: float = 10.0,
    ) -> None:
        self._port = port
        self._grace_period = grace_period
        self._server: Optional[grpc.Server] = None
        self._shutdown_event = threading.Event()

        # Build interceptor chain
        interceptors = [
            LoggingInterceptor(),
            RateLimitInterceptor(rate=100, burst=200),
            AuthInterceptor(valid_tokens={"test-token": "user-1"}),
        ]

        self._server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=max_workers),
            interceptors=interceptors,
            options=[
                ("grpc.max_send_message_length", 50 * 1024 * 1024),
                ("grpc.max_receive_message_length", 50 * 1024 * 1024),
                ("grpc.keepalive_time_ms", 30000),
                ("grpc.keepalive_timeout_ms", 10000),
                ("grpc.keepalive_permit_without_calls", True),
                ("grpc.http2.max_ping_strikes", 0),
            ],
        )

    def start(self) -> None:
        self._server.add_insecure_port(f"[::]:{self._port}")
        self._server.start()
        logger.info(f"gRPC server started on port {self._port}")

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def wait_for_termination(self) -> None:
        self._shutdown_event.wait()
        logger.info(
            f"Graceful shutdown initiated, "
            f"grace period: {self._grace_period}s"
        )
        # Stop accepting new RPCs, wait for in-flight to complete
        self._server.stop(self._grace_period)
        logger.info("Server stopped")

    def _signal_handler(self, signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}")
        self._shutdown_event.set()


if __name__ == "__main__":
    server = GrpcServer(port=50051, max_workers=10, grace_period=10.0)
    server.start()
    server.wait_for_termination()
```

## Health Checking and Load Balancing

gRPC has a **standard health checking protocol** (defined in `grpc.health.v1.Health`) that load balancers use to determine backend availability. The **best practice** is to implement both the health service and **readiness probes** — the health service reports whether the gRPC process is running, while readiness indicates whether it can accept traffic (database connected, caches warm, etc.).

For load balancing, gRPC over HTTP/2 presents a unique challenge: because HTTP/2 multiplexes all RPCs over a single TCP connection, **L4 load balancers** (which route per-connection) cannot distribute individual RPCs across backends. Therefore, gRPC requires either **L7 load balancing** (which inspects HTTP/2 frames) or **client-side load balancing** (where the client maintains connections to all backends and selects per-RPC). Envoy, Istio, and Linkerd all provide L7 gRPC load balancing, while the gRPC library itself supports client-side strategies like **pick-first** and **round-robin**.

### Client Implementation with Retry and Timeout

A production gRPC client must handle connection management, retries, and deadlines properly. However, a **common mistake** is setting deadlines only on the client side without propagating them through the call chain. The following client demonstrates **best practice** patterns for resilient gRPC communication:

```python
# Production gRPC client with retry policy, deadlines, and metadata
import grpc
import time
import logging
from typing import Optional, Dict, Any, Iterator, List
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass
class RetryPolicy:
    # gRPC retry configuration matching the service config spec
    max_attempts: int = 3
    initial_backoff_seconds: float = 0.1
    max_backoff_seconds: float = 5.0
    backoff_multiplier: float = 2.0
    retryable_status_codes: List[str] = None

    def __post_init__(self) -> None:
        if self.retryable_status_codes is None:
            self.retryable_status_codes = [
                "UNAVAILABLE", "DEADLINE_EXCEEDED", "RESOURCE_EXHAUSTED"
            ]


class OrderServiceClient:
    # Resilient gRPC client for the OrderService.
    # Handles connection pooling, retries, and deadline propagation.

    def __init__(
        self,
        target: str = "localhost:50051",
        timeout: float = 10.0,
        auth_token: Optional[str] = None,
    ) -> None:
        self._timeout = timeout
        self._auth_token = auth_token

        # Configure retry policy via service config
        service_config = {
            "methodConfig": [{
                "name": [{"service": "orders.v1.OrderService"}],
                "retryPolicy": {
                    "maxAttempts": 3,
                    "initialBackoff": "0.1s",
                    "maxBackoff": "5s",
                    "backoffMultiplier": 2,
                    "retryableStatusCodes": [
                        "UNAVAILABLE", "DEADLINE_EXCEEDED"
                    ],
                },
                "timeout": f"{timeout}s",
            }],
        }

        import json
        self._channel = grpc.insecure_channel(
            target,
            options=[
                ("grpc.service_config", json.dumps(service_config)),
                ("grpc.enable_retries", 1),
                ("grpc.keepalive_time_ms", 30000),
                ("grpc.keepalive_timeout_ms", 10000),
                ("grpc.max_send_message_length", 50 * 1024 * 1024),
                ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ],
        )

    def _metadata(self) -> List[tuple]:
        # Build request metadata including auth and tracing headers
        meta = [("x-client-id", "order-client-v1")]
        if self._auth_token:
            meta.append(("authorization", f"Bearer {self._auth_token}"))
        return meta

    def create_order(
        self,
        customer_id: str,
        items: List[Dict[str, Any]],
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        # Create a single order with deadline propagation.
        # The timeout parameter overrides the default for this call.
        effective_timeout = timeout or self._timeout
        try:
            # In production, this would use the generated stub
            logger.info(
                f"Creating order for customer {customer_id} "
                f"with timeout {effective_timeout}s"
            )
            return {"customer_id": customer_id, "items": items}
        except grpc.RpcError as e:
            status = e.code()
            logger.error(
                f"RPC failed: {status.name} - {e.details()}"
            )
            raise

    def watch_updates(
        self, customer_id: str
    ) -> Iterator[Dict[str, Any]]:
        # Server streaming: watch for order status updates.
        # This demonstrates proper cancellation handling.
        logger.info(f"Starting update watch for {customer_id}")
        try:
            # In production this would call the generated stub
            # and yield OrderUpdate messages from the stream
            yield {"customer_id": customer_id, "status": "watching"}
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.CANCELLED:
                logger.info("Watch cancelled by client")
            else:
                logger.error(f"Watch failed: {e.code().name}")
                raise

    def close(self) -> None:
        # Gracefully close the channel.
        # Best practice: always close channels to release resources.
        if self._channel:
            self._channel.close()
            logger.info("gRPC channel closed")

    def __enter__(self) -> "OrderServiceClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
```

## Summary and Key Takeaways

- **Protobuf schema design** must follow strict versioning rules: never reuse field numbers, always use `reserved` for deleted fields, and prefer wrapper types for optional fields.
- gRPC's **four streaming types** enable different communication patterns: unary for simple request-response, server streaming for push notifications, client streaming for batch uploads, and bidirectional for real-time collaboration.
- **Interceptors** are the gRPC equivalent of middleware — use them for logging, authentication, rate limiting, and distributed tracing to keep cross-cutting concerns out of business logic.
- **Graceful shutdown** is critical for production deployments: stop accepting new RPCs, wait for in-flight RPCs to complete (with a timeout), then terminate. A **pitfall** is forgetting the grace period, which drops active RPCs during rolling deployments.
- gRPC **load balancing** requires L7 awareness because HTTP/2 multiplexing defeats L4 balancers; therefore use Envoy, Istio, or client-side balancing.
- **Client-side resilience** requires configuring retry policies via service config, propagating deadlines through call chains, and implementing proper channel lifecycle management.
- The primary **trade-off** of gRPC vs REST is performance and type safety versus developer ergonomics and browser compatibility.
"""
    ),

    # --- 5. Network Resilience Patterns ---
    (
        "service-mesh/network-resilience-patterns-library",
        "Explain network resilience patterns in depth covering circuit breaker states and transitions, bulkhead isolation, retry with exponential backoff and jitter, timeout cascading, and fallback strategies, then implement a comprehensive resilience library in Python with circuit breaker, bulkhead, and retry decorators including full state machine transitions.",
        r"""# Network Resilience Patterns: A Comprehensive Library

## Why Resilience Patterns Are Non-Negotiable

In distributed systems, **partial failure is the norm, not the exception**. Networks drop packets, services crash, databases become overloaded, and cloud regions go offline. Without deliberate resilience engineering, a single unhealthy dependency can cascade into a system-wide outage. The fundamental insight behind resilience patterns is that **failing fast and gracefully** is better than failing slowly and catastrophically — therefore, every remote call must be wrapped in protective patterns that limit blast radius and enable recovery.

The five core resilience patterns are: **Circuit Breaker** (stop calling a failing service), **Bulkhead** (isolate failures so they don't consume all resources), **Retry** (automatically recover from transient errors), **Timeout** (prevent indefinite blocking), and **Fallback** (provide degraded functionality when the primary path fails). These patterns are complementary and should be composed together — a **common mistake** is implementing only retries without circuit breaking, which turns transient failures into amplified load that prevents recovery.

## Circuit Breaker: State Machine Deep Dive

The circuit breaker pattern is modeled after electrical circuit breakers: when failures exceed a threshold, the circuit **opens** and immediately rejects requests without calling the failing service. After a recovery timeout, it transitions to **half-open** and allows a limited number of probe requests through. If probes succeed, the circuit **closes** (back to normal); if they fail, it **opens** again.

### State Transitions

```
    +--------+   failure threshold exceeded   +------+
    | CLOSED | -----------------------------> | OPEN |
    +--------+                                +------+
        ^                                         |
        |                                         | recovery timeout
        |   probe successes >= threshold          v
        +-----------------------------------  +----------+
                                              | HALF_OPEN|
        +-----------------------------------  +----------+
        |   probe failure                         |
        |                                         |
        +-------> +------+  <--------------------+
                  | OPEN |
                  +------+
```

The **best practice** is to use a **sliding window** for failure counting rather than a simple counter. A simple counter can trip the circuit based on ancient failures that no longer reflect current health, while a sliding window only considers recent requests.

### Timeout Cascading

A **pitfall** in microservice architectures is **timeout cascading**: if Service A calls Service B with a 5-second timeout, and Service B calls Service C with a 5-second timeout, Service A could wait up to 10 seconds (5s for B + 5s for C's timeout within B's handler). Therefore, timeouts must **decrease** along the call chain. If your gateway has a 10-second timeout, the first-hop service should use 7 seconds, and the second-hop should use 4 seconds, leaving room for processing at each layer.

## Implementation

```python
import time
import random
import threading
import functools
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import (
    TypeVar, Callable, Optional, Any, Dict, List, Set,
    Tuple, Generic, Type, Union
)
from enum import Enum, auto
from collections import deque
from concurrent.futures import Semaphore, ThreadPoolExecutor, Future


logger = logging.getLogger(__name__)
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


# --- Circuit Breaker ---

class CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


@dataclass
class CircuitBreakerConfig:
    # Configuration for the circuit breaker
    failure_threshold: int = 5           # failures to open circuit
    recovery_timeout: float = 30.0       # seconds before half-open
    half_open_max_calls: int = 3         # probes allowed in half-open
    success_threshold: int = 3           # successes to close from half-open
    sliding_window_size: int = 10        # number of recent calls to track
    failure_rate_threshold: float = 0.5  # 50% failure rate opens circuit
    # Exception types considered as failures
    record_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    # Exception types to ignore (not counted as failures)
    ignore_exceptions: Tuple[Type[Exception], ...] = ()


class SlidingWindow:
    # Tracks success/failure of recent calls using a fixed-size window.

    def __init__(self, size: int) -> None:
        self._size = size
        self._results: deque = deque(maxlen=size)

    def record(self, success: bool) -> None:
        self._results.append(success)

    @property
    def failure_rate(self) -> float:
        if not self._results:
            return 0.0
        failures = sum(1 for r in self._results if not r)
        return failures / len(self._results)

    @property
    def total_calls(self) -> int:
        return len(self._results)

    def reset(self) -> None:
        self._results.clear()


class CircuitBreaker:
    # Production-grade circuit breaker with sliding window
    # failure detection and configurable state transitions.

    def __init__(self, config: Optional[CircuitBreakerConfig] = None) -> None:
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._lock = threading.Lock()
        self._window = SlidingWindow(self._config.sliding_window_size)
        self._last_failure_time: float = 0.0
        self._half_open_calls: int = 0
        self._half_open_successes: int = 0
        self._listeners: List[Callable[[CircuitState, CircuitState], None]] = []

    @property
    def state(self) -> CircuitState:
        with self._lock:
            # Check for automatic transition from OPEN -> HALF_OPEN
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self._config.recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    def add_listener(
        self, listener: Callable[[CircuitState, CircuitState], None]
    ) -> None:
        self._listeners.append(listener)

    def _transition_to(self, new_state: CircuitState) -> None:
        old_state = self._state
        if old_state == new_state:
            return

        self._state = new_state
        logger.info(
            f"Circuit breaker: {old_state.name} -> {new_state.name}"
        )

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._half_open_successes = 0
        elif new_state == CircuitState.CLOSED:
            self._window.reset()

        for listener in self._listeners:
            try:
                listener(old_state, new_state)
            except Exception:
                pass

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        # Execute a function through the circuit breaker.
        with self._lock:
            current_state = self.state

            if current_state == CircuitState.OPEN:
                raise CircuitOpenError(
                    f"Circuit is OPEN, call rejected. "
                    f"Recovery in "
                    f"{self._config.recovery_timeout - (time.monotonic() - self._last_failure_time):.1f}s"
                )

            if current_state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self._config.half_open_max_calls:
                    raise CircuitOpenError(
                        "Circuit is HALF_OPEN and at probe capacity"
                    )
                self._half_open_calls += 1

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self._config.ignore_exceptions:
            # Do not count ignored exceptions as failures
            raise
        except self._config.record_exceptions as e:
            self._on_failure()
            raise
        except Exception:
            # Unrecognized exceptions pass through without counting
            raise

    def _on_success(self) -> None:
        with self._lock:
            self._window.record(True)

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self._config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    def _on_failure(self) -> None:
        with self._lock:
            self._window.record(False)

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open reopens the circuit
                self._last_failure_time = time.monotonic()
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if (
                    self._window.total_calls >= self._config.sliding_window_size
                    and self._window.failure_rate
                    >= self._config.failure_rate_threshold
                ):
                    self._last_failure_time = time.monotonic()
                    self._transition_to(CircuitState.OPEN)


class CircuitOpenError(Exception):
    pass


# --- Bulkhead ---

class BulkheadConfig:
    # Configuration for bulkhead isolation
    def __init__(
        self,
        max_concurrent: int = 10,
        max_queue: int = 20,
        queue_timeout: float = 5.0,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.max_queue = max_queue
        self.queue_timeout = queue_timeout


class Bulkhead:
    # Limits concurrent access to a resource using semaphores.
    # Prevents a slow dependency from consuming all threads
    # in the application, therefore isolating failures.

    def __init__(self, config: Optional[BulkheadConfig] = None) -> None:
        self._config = config or BulkheadConfig()
        self._semaphore = threading.Semaphore(self._config.max_concurrent)
        self._queue_count = 0
        self._queue_lock = threading.Lock()
        self._active_count = 0

    @property
    def active_count(self) -> int:
        return self._active_count

    @property
    def queue_count(self) -> int:
        return self._queue_count

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        # Execute a function within the bulkhead.
        # Rejects immediately if both execution slots and queue are full.

        with self._queue_lock:
            if self._queue_count >= self._config.max_queue:
                raise BulkheadFullError(
                    f"Bulkhead full: {self._active_count} active, "
                    f"{self._queue_count} queued"
                )
            self._queue_count += 1

        try:
            acquired = self._semaphore.acquire(
                timeout=self._config.queue_timeout
            )
            if not acquired:
                raise BulkheadFullError(
                    f"Timed out waiting for bulkhead slot "
                    f"after {self._config.queue_timeout}s"
                )

            with self._queue_lock:
                self._queue_count -= 1
                self._active_count += 1

            try:
                return func(*args, **kwargs)
            finally:
                self._semaphore.release()
                with self._queue_lock:
                    self._active_count -= 1
        except BulkheadFullError:
            with self._queue_lock:
                self._queue_count -= 1
            raise


class BulkheadFullError(Exception):
    pass


# --- Retry with Exponential Backoff and Jitter ---

@dataclass
class RetryConfig:
    # Configuration for retry behavior
    max_attempts: int = 3
    base_delay: float = 0.5        # seconds
    max_delay: float = 30.0        # seconds cap
    exponential_base: float = 2.0
    jitter: str = "full"           # "full", "equal", "decorrelated"
    # Exception types that should trigger a retry
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    # Optional predicate for finer-grained control
    retry_predicate: Optional[Callable[[Exception], bool]] = None


class RetryPolicy:
    # Implements retry with configurable backoff and jitter.
    #
    # Jitter strategies (each solves a different problem):
    # - "full": uniform random [0, exponential_delay]
    #     Best general-purpose choice. Spreads retries evenly.
    # - "equal": exponential_delay/2 + random [0, exponential_delay/2]
    #     Guarantees minimum backoff while adding randomness.
    # - "decorrelated": random [base_delay, previous_delay * 3]
    #     AWS recommended. Good for correlated failures.

    def __init__(self, config: Optional[RetryConfig] = None) -> None:
        self._config = config or RetryConfig()
        self._prev_delay: float = self._config.base_delay

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        last_exception: Optional[Exception] = None
        self._prev_delay = self._config.base_delay

        for attempt in range(1, self._config.max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except self._config.retryable_exceptions as e:
                last_exception = e

                # Check custom predicate if provided
                if (
                    self._config.retry_predicate
                    and not self._config.retry_predicate(e)
                ):
                    raise

                if attempt >= self._config.max_attempts:
                    logger.warning(
                        f"All {self._config.max_attempts} retry attempts "
                        f"exhausted. Last error: {e}"
                    )
                    raise

                delay = self._calculate_delay(attempt)
                logger.info(
                    f"Attempt {attempt}/{self._config.max_attempts} failed: "
                    f"{e}. Retrying in {delay:.2f}s"
                )
                time.sleep(delay)

        # Should not reach here, but satisfy type checker
        raise last_exception  # type: ignore

    def _calculate_delay(self, attempt: int) -> float:
        base = self._config.base_delay
        exp_delay = min(
            self._config.max_delay,
            base * (self._config.exponential_base ** (attempt - 1)),
        )

        jitter = self._config.jitter
        if jitter == "full":
            delay = random.uniform(0, exp_delay)
        elif jitter == "equal":
            half = exp_delay / 2
            delay = half + random.uniform(0, half)
        elif jitter == "decorrelated":
            delay = random.uniform(base, self._prev_delay * 3)
            delay = min(delay, self._config.max_delay)
            self._prev_delay = delay
        else:
            delay = exp_delay

        return delay
```

### Composing Resilience Patterns with Decorators

```python
# --- Decorator Factories for Clean Composition ---

def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    failure_rate_threshold: float = 0.5,
) -> Callable[[F], F]:
    # Decorator that wraps a function with a circuit breaker.
    config = CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        failure_rate_threshold=failure_rate_threshold,
    )
    cb = CircuitBreaker(config)

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return cb.call(func, *args, **kwargs)
        wrapper._circuit_breaker = cb  # expose for testing
        return wrapper  # type: ignore
    return decorator


def bulkhead(
    max_concurrent: int = 10,
    max_queue: int = 20,
    queue_timeout: float = 5.0,
) -> Callable[[F], F]:
    # Decorator that wraps a function with bulkhead isolation.
    config = BulkheadConfig(
        max_concurrent=max_concurrent,
        max_queue=max_queue,
        queue_timeout=queue_timeout,
    )
    bh = Bulkhead(config)

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return bh.call(func, *args, **kwargs)
        wrapper._bulkhead = bh  # expose for testing
        return wrapper  # type: ignore
    return decorator


def retry(
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    jitter: str = "full",
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    # Decorator that wraps a function with retry logic.
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        jitter=jitter,
        retryable_exceptions=retryable_exceptions,
    )

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            policy = RetryPolicy(config)
            return policy.call(func, *args, **kwargs)
        return wrapper  # type: ignore
    return decorator


def fallback(
    fallback_fn: Callable[..., Any],
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    # Decorator that provides a fallback when the primary function fails.
    # The fallback receives the same arguments as the original function.

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                logger.warning(
                    f"{func.__name__} failed with {e}, "
                    f"using fallback {fallback_fn.__name__}"
                )
                return fallback_fn(*args, **kwargs)
        return wrapper  # type: ignore
    return decorator


# --- Composed Usage Example ---

def get_cached_price(product_id: str) -> float:
    # Fallback: return cached/default price
    return 9.99


@fallback(get_cached_price, exceptions=(CircuitOpenError, BulkheadFullError, TimeoutError))
@circuit_breaker(failure_threshold=5, recovery_timeout=30.0)
@bulkhead(max_concurrent=5, max_queue=10, queue_timeout=2.0)
@retry(max_attempts=3, base_delay=0.5, jitter="full", retryable_exceptions=(ConnectionError, TimeoutError))
def get_product_price(product_id: str) -> float:
    # The decorator chain executes outside-in:
    # 1. fallback catches any unrecoverable error
    # 2. circuit_breaker rejects if service is known-down
    # 3. bulkhead limits concurrent calls
    # 4. retry handles transient failures
    #
    # This ordering is a best practice because:
    # - Fallback is outermost to catch circuit-open errors
    # - Circuit breaker is before retry to avoid retrying
    #   when the service is known to be down
    # - Bulkhead is inside circuit breaker to only limit
    #   calls that actually proceed
    # - Retry is innermost, retrying only individual call failures

    import urllib.request
    response = urllib.request.urlopen(
        f"http://pricing-service/api/v1/price/{product_id}",
        timeout=2.0,
    )
    data = response.read()
    return float(data)
```

## Decorator Composition Order

The **order of resilience decorators matters enormously**. The correct outside-in order is:

1. **Fallback** (outermost) — catches everything including circuit-open rejections
2. **Circuit Breaker** — fast-fails before consuming resources
3. **Bulkhead** — limits concurrency for calls that pass the circuit breaker
4. **Timeout** — limits how long each attempt takes
5. **Retry** (innermost) — retries individual failed attempts

A **common mistake** is placing retry outside the circuit breaker. This causes retries against a known-failing service, which delays the circuit from opening and amplifies the load on the struggling service. Therefore, retry should always be inside the circuit breaker.

## Summary and Key Takeaways

- **Circuit breakers** prevent cascade failures by fast-failing when a dependency is unhealthy; use **sliding window** failure detection rather than simple counters for accurate health tracking.
- **Bulkhead isolation** limits concurrent access to each dependency, therefore preventing a slow service from consuming all application threads — this is critical because without bulkheads, one slow dependency can starve healthy ones.
- **Retry with jitter** recovers from transient failures automatically; however, the jitter strategy matters significantly: **decorrelated jitter** (AWS recommended) is the best practice for avoiding retry storms where many clients retry simultaneously.
- **Timeout cascading** requires deliberately shorter timeouts at each hop in the call chain; the **pitfall** of equal timeouts across layers causes multiplicative worst-case latency.
- **Fallback strategies** provide degraded but functional responses (cached data, default values, alternative services) when primary paths fail.
- The **trade-off** in resilience engineering is between complexity and robustness: every pattern adds code, configuration, and operational overhead, but the alternative — unprotected remote calls — produces fragile systems that fail catastrophically under stress.
- **Decorator composition order** is critical: fallback > circuit breaker > bulkhead > timeout > retry, from outermost to innermost. Getting this wrong negates the benefits of the patterns.
"""
    ),
]
