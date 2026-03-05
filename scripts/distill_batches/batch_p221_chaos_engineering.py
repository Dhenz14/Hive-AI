"""Chaos engineering — Chaos Monkey, Litmus, network chaos, stress testing, and experiment design."""

PAIRS = [
    (
        "reliability/chaos-monkey-litmus",
        "Show chaos engineering patterns using Chaos Monkey and LitmusChaos including pod kill, node drain, and experiment orchestration.",
        '''Chaos engineering with Chaos Monkey and LitmusChaos patterns:

```python
# --- chaos_runner.py --- Framework for chaos experiment execution ---

from __future__ import annotations

import random
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable
from datetime import datetime, timedelta

import requests
from kubernetes import client, config

logger = logging.getLogger(__name__)


class ExperimentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass
class SteadyStateHypothesis:
    """Define what 'normal' looks like before and after chaos."""
    name: str
    probes: list[Probe]
    tolerance: float = 0.95  # 95% of probes must pass

    def evaluate(self) -> bool:
        results = [probe.check() for probe in self.probes]
        pass_rate = sum(results) / len(results) if results else 0
        logger.info(f"Steady state '{self.name}': {pass_rate:.0%} pass rate")
        return pass_rate >= self.tolerance


@dataclass
class Probe:
    """Health check probe for steady state verification."""
    name: str
    url: str
    expected_status: int = 200
    timeout: float = 5.0

    def check(self) -> bool:
        try:
            resp = requests.get(self.url, timeout=self.timeout)
            passed = resp.status_code == self.expected_status
            if not passed:
                logger.warning(
                    f"Probe '{self.name}' failed: "
                    f"expected {self.expected_status}, got {resp.status_code}"
                )
            return passed
        except requests.RequestException as e:
            logger.error(f"Probe '{self.name}' error: {e}")
            return False


@dataclass
class ChaosExperiment:
    """Orchestrate a complete chaos experiment lifecycle."""
    name: str
    hypothesis: SteadyStateHypothesis
    actions: list[ChaosAction]
    rollback: list[Callable] = field(default_factory=list)
    duration: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    cooldown: timedelta = field(default_factory=lambda: timedelta(minutes=2))
    status: ExperimentStatus = ExperimentStatus.PENDING

    def run(self) -> ExperimentStatus:
        """Execute the full experiment lifecycle."""
        logger.info(f"=== Starting experiment: {self.name} ===")

        # Step 1: Verify steady state BEFORE chaos
        logger.info("Checking pre-experiment steady state...")
        if not self.hypothesis.evaluate():
            logger.error("Pre-experiment steady state check FAILED — aborting")
            self.status = ExperimentStatus.ABORTED
            return self.status

        # Step 2: Inject chaos
        self.status = ExperimentStatus.RUNNING
        try:
            for action in self.actions:
                logger.info(f"Injecting chaos: {action.name}")
                action.execute()

            # Step 3: Wait for system to react
            logger.info(f"Waiting {self.duration.seconds}s for chaos to take effect...")
            time.sleep(min(self.duration.total_seconds(), 300))

        except Exception as e:
            logger.error(f"Chaos injection failed: {e}")
            self._rollback()
            self.status = ExperimentStatus.ABORTED
            return self.status

        # Step 4: Verify steady state AFTER chaos
        logger.info("Checking post-experiment steady state...")
        if self.hypothesis.evaluate():
            logger.info("System SURVIVED chaos — experiment PASSED")
            self.status = ExperimentStatus.PASSED
        else:
            logger.warning("System DID NOT recover — experiment FAILED")
            self.status = ExperimentStatus.FAILED

        # Step 5: Rollback
        self._rollback()

        # Step 6: Cooldown
        logger.info(f"Cooldown: {self.cooldown.seconds}s")
        time.sleep(min(self.cooldown.total_seconds(), 120))

        return self.status

    def _rollback(self) -> None:
        for fn in self.rollback:
            try:
                fn()
            except Exception as e:
                logger.error(f"Rollback failed: {e}")


@dataclass
class ChaosAction:
    name: str
    execute: Callable
```

```python
# --- k8s_chaos.py --- Kubernetes chaos actions ---

from kubernetes import client, config
from typing import Optional
import random
import logging

logger = logging.getLogger(__name__)


class KubernetesChaos:
    """Chaos actions targeting Kubernetes resources."""

    def __init__(self, kubeconfig: Optional[str] = None):
        if kubeconfig:
            config.load_kube_config(config_file=kubeconfig)
        else:
            config.load_incluster_config()
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()

    def kill_random_pod(
        self,
        namespace: str = "default",
        label_selector: str = "app=myapp",
    ) -> str:
        """Kill a random pod matching the selector (Chaos Monkey pattern)."""
        pods = self.core_v1.list_namespaced_pod(
            namespace=namespace,
            label_selector=label_selector,
            field_selector="status.phase=Running",
        )
        if not pods.items:
            logger.warning(f"No running pods found for {label_selector}")
            return ""

        victim = random.choice(pods.items)
        pod_name = victim.metadata.name
        logger.info(f"Killing pod: {pod_name}")

        self.core_v1.delete_namespaced_pod(
            name=pod_name,
            namespace=namespace,
            grace_period_seconds=0,  # force kill
        )
        return pod_name

    def kill_percentage_of_pods(
        self,
        namespace: str,
        label_selector: str,
        percentage: int = 50,
    ) -> list[str]:
        """Kill a percentage of pods (blast radius control)."""
        pods = self.core_v1.list_namespaced_pod(
            namespace=namespace,
            label_selector=label_selector,
            field_selector="status.phase=Running",
        )
        count = max(1, len(pods.items) * percentage // 100)
        victims = random.sample(pods.items, min(count, len(pods.items)))
        killed = []

        for pod in victims:
            name = pod.metadata.name
            self.core_v1.delete_namespaced_pod(
                name=name, namespace=namespace, grace_period_seconds=0
            )
            killed.append(name)
            logger.info(f"Killed pod: {name}")

        return killed

    def drain_node(self, node_name: str) -> None:
        """Cordon and drain a node (simulates node failure)."""
        # Cordon: mark node unschedulable
        body = {"spec": {"unschedulable": True}}
        self.core_v1.patch_node(node_name, body)
        logger.info(f"Cordoned node: {node_name}")

        # Evict pods from the node
        pods = self.core_v1.list_pod_for_all_namespaces(
            field_selector=f"spec.nodeName={node_name}"
        )
        for pod in pods.items:
            if pod.metadata.namespace in ("kube-system",):
                continue
            try:
                eviction = client.V1Eviction(
                    metadata=client.V1ObjectMeta(
                        name=pod.metadata.name,
                        namespace=pod.metadata.namespace,
                    )
                )
                self.core_v1.create_namespaced_pod_eviction(
                    name=pod.metadata.name,
                    namespace=pod.metadata.namespace,
                    body=eviction,
                )
                logger.info(f"Evicted: {pod.metadata.namespace}/{pod.metadata.name}")
            except client.ApiException as e:
                logger.warning(f"Eviction failed: {e.reason}")

    def uncordon_node(self, node_name: str) -> None:
        """Reverse a node drain — make node schedulable again."""
        body = {"spec": {"unschedulable": False}}
        self.core_v1.patch_node(node_name, body)
        logger.info(f"Uncordoned node: {node_name}")
```

```yaml
# --- litmus-pod-kill.yaml --- LitmusChaos ChaosEngine ---
# Install Litmus: kubectl apply -f https://litmuschaos.github.io/litmus/litmus-operator-v3.0.0.yaml

apiVersion: litmuschaos.io/v1alpha1
kind: ChaosEngine
metadata:
  name: pod-kill-chaos
  namespace: default
spec:
  appinfo:
    appns: default
    applabel: "app=myapp"
    appkind: deployment
  engineState: active
  chaosServiceAccount: litmus-admin
  experiments:
    - name: pod-delete
      spec:
        components:
          env:
            - name: TOTAL_CHAOS_DURATION
              value: "60"           # seconds
            - name: CHAOS_INTERVAL
              value: "10"           # kill every 10s
            - name: FORCE
              value: "true"
            - name: PODS_AFFECTED_PERC
              value: "50"           # kill 50% of pods
        probe:
          - name: "check-app-health"
            type: httpProbe
            mode: Continuous
            httpProbe/inputs:
              url: "http://myapp.default.svc:8080/health"
              expectedResponseCode: "200"
            runProperties:
              probeTimeout: 5
              interval: 5
              retry: 3

---
# LitmusChaos experiment for node drain
apiVersion: litmuschaos.io/v1alpha1
kind: ChaosEngine
metadata:
  name: node-drain-chaos
  namespace: default
spec:
  appinfo:
    appns: default
    applabel: "app=myapp"
    appkind: deployment
  engineState: active
  chaosServiceAccount: litmus-admin
  experiments:
    - name: node-drain
      spec:
        components:
          env:
            - name: TOTAL_CHAOS_DURATION
              value: "120"
            - name: APP_NODE
              value: "worker-node-2"
        probe:
          - name: "steady-state-check"
            type: httpProbe
            mode: Edge           # check at start and end
            httpProbe/inputs:
              url: "http://myapp.default.svc:8080/health"
              expectedResponseCode: "200"
            runProperties:
              probeTimeout: 10
              interval: 10
              retry: 5
```

| Chaos Tool | Scope | Strengths | Best for |
|-----------|-------|-----------|----------|
| Chaos Monkey | Pod kill | Simple, battle-tested | Random failure injection |
| LitmusChaos | K8s-native | CRD-based, probes, GitOps-ready | Declarative experiments |
| Chaos Mesh | K8s-native | Time chaos, JVM chaos, IO chaos | Fine-grained fault injection |
| Gremlin | SaaS + agent | Enterprise, team features | Managed chaos platform |
| Toxiproxy | Network proxy | Programmable, language-agnostic | Network-level chaos |

Key patterns:
1. Always verify steady state BEFORE injecting chaos to establish a baseline
2. Control blast radius — start with one pod, then increase to a percentage
3. Include rollback procedures for every chaos action (uncordon nodes, restart pods)
4. Run chaos in staging first; graduate to production only with game days
5. Use probes (HTTP, command, Prometheus) to continuously monitor during chaos'''
    ),
    (
        "reliability/network-chaos",
        "Show how to simulate network chaos including latency injection, partition, and packet loss using tc, Toxiproxy, and Chaos Mesh.",
        '''Network chaos simulation with tc, Toxiproxy, and Chaos Mesh:

```python
# --- network_chaos.py --- Programmatic network fault injection ---

from __future__ import annotations

import subprocess
import logging
from dataclasses import dataclass
from typing import Optional
from contextlib import contextmanager

import requests

logger = logging.getLogger(__name__)


# === Linux tc (traffic control) based chaos ===

@dataclass
class TcNetem:
    """Network emulation using Linux tc/netem.

    Requires root/CAP_NET_ADMIN. Works on the interface level.
    """
    interface: str = "eth0"

    def add_latency(
        self,
        delay_ms: int = 200,
        jitter_ms: int = 50,
        correlation: int = 25,
    ) -> None:
        """Add latency with jitter to outgoing packets."""
        cmd = (
            f"tc qdisc add dev {self.interface} root netem "
            f"delay {delay_ms}ms {jitter_ms}ms {correlation}%"
        )
        self._run(cmd)
        logger.info(
            f"Added {delay_ms}ms latency (+/-{jitter_ms}ms) on {self.interface}"
        )

    def add_packet_loss(
        self,
        loss_percent: float = 5.0,
        correlation: int = 25,
    ) -> None:
        """Drop a percentage of outgoing packets."""
        cmd = (
            f"tc qdisc add dev {self.interface} root netem "
            f"loss {loss_percent}% {correlation}%"
        )
        self._run(cmd)
        logger.info(f"Added {loss_percent}% packet loss on {self.interface}")

    def add_bandwidth_limit(self, rate: str = "1mbit", burst: str = "32kbit") -> None:
        """Limit outgoing bandwidth."""
        cmd = (
            f"tc qdisc add dev {self.interface} root tbf "
            f"rate {rate} burst {burst} latency 400ms"
        )
        self._run(cmd)
        logger.info(f"Limited bandwidth to {rate} on {self.interface}")

    def add_packet_corruption(self, percent: float = 1.0) -> None:
        """Corrupt a percentage of packets (bit errors)."""
        cmd = (
            f"tc qdisc add dev {self.interface} root netem "
            f"corrupt {percent}%"
        )
        self._run(cmd)

    def add_packet_reorder(
        self, percent: float = 25.0, correlation: int = 50, delay_ms: int = 10
    ) -> None:
        """Reorder packets."""
        cmd = (
            f"tc qdisc add dev {self.interface} root netem "
            f"delay {delay_ms}ms reorder {percent}% {correlation}%"
        )
        self._run(cmd)

    def clear(self) -> None:
        """Remove all tc rules from the interface."""
        cmd = f"tc qdisc del dev {self.interface} root"
        self._run(cmd, check=False)
        logger.info(f"Cleared all netem rules on {self.interface}")

    @contextmanager
    def inject(self, fault_type: str, **kwargs):
        """Context manager for temporary fault injection."""
        fault_methods = {
            "latency": self.add_latency,
            "loss": self.add_packet_loss,
            "bandwidth": self.add_bandwidth_limit,
            "corruption": self.add_packet_corruption,
            "reorder": self.add_packet_reorder,
        }
        method = fault_methods.get(fault_type)
        if not method:
            raise ValueError(f"Unknown fault type: {fault_type}")
        method(**kwargs)
        try:
            yield
        finally:
            self.clear()

    def _run(self, cmd: str, check: bool = True) -> None:
        result = subprocess.run(
            cmd.split(), capture_output=True, text=True
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"tc command failed: {result.stderr}")
```

```python
# --- toxiproxy_chaos.py --- Toxiproxy for application-layer chaos ---

from __future__ import annotations

import requests
from dataclasses import dataclass, field
from typing import Optional
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToxiproxyClient:
    """Client for Toxiproxy API — network chaos at the TCP proxy level.

    Toxiproxy sits between your app and upstream services:
        app -> toxiproxy:6379 -> redis:6379
    """
    api_url: str = "http://localhost:8474"

    def create_proxy(
        self,
        name: str,
        listen: str,
        upstream: str,
        enabled: bool = True,
    ) -> dict:
        """Create a proxy between client and upstream."""
        resp = requests.post(
            f"{self.api_url}/proxies",
            json={
                "name": name,
                "listen": listen,
                "upstream": upstream,
                "enabled": enabled,
            },
        )
        resp.raise_for_status()
        logger.info(f"Created proxy: {name} ({listen} -> {upstream})")
        return resp.json()

    def add_toxic(
        self,
        proxy_name: str,
        toxic_type: str,
        stream: str = "downstream",
        toxicity: float = 1.0,
        attributes: Optional[dict] = None,
    ) -> dict:
        """Add a toxic (fault) to a proxy.

        Toxic types: latency, bandwidth, slow_close, timeout,
                     slicer, limit_data, reset_peer
        """
        resp = requests.post(
            f"{self.api_url}/proxies/{proxy_name}/toxics",
            json={
                "type": toxic_type,
                "stream": stream,
                "toxicity": toxicity,
                "attributes": attributes or {},
            },
        )
        resp.raise_for_status()
        logger.info(f"Added {toxic_type} toxic to {proxy_name}")
        return resp.json()

    def remove_toxic(self, proxy_name: str, toxic_name: str) -> None:
        """Remove a specific toxic from a proxy."""
        resp = requests.delete(
            f"{self.api_url}/proxies/{proxy_name}/toxics/{toxic_name}"
        )
        resp.raise_for_status()

    def disable_proxy(self, proxy_name: str) -> None:
        """Disable proxy completely — simulates full network partition."""
        resp = requests.post(
            f"{self.api_url}/proxies/{proxy_name}",
            json={"enabled": False},
        )
        resp.raise_for_status()
        logger.info(f"Disabled proxy: {proxy_name} (partition)")

    def enable_proxy(self, proxy_name: str) -> None:
        """Re-enable proxy — end network partition."""
        resp = requests.post(
            f"{self.api_url}/proxies/{proxy_name}",
            json={"enabled": True},
        )
        resp.raise_for_status()

    @contextmanager
    def latency(
        self, proxy_name: str, latency_ms: int = 500, jitter_ms: int = 100
    ):
        """Temporarily inject latency into a proxy."""
        toxic = self.add_toxic(
            proxy_name,
            "latency",
            attributes={"latency": latency_ms, "jitter": jitter_ms},
        )
        try:
            yield
        finally:
            self.remove_toxic(proxy_name, toxic["name"])

    @contextmanager
    def partition(self, proxy_name: str):
        """Temporarily partition (disable) a proxy."""
        self.disable_proxy(proxy_name)
        try:
            yield
        finally:
            self.enable_proxy(proxy_name)


# --- Usage ---
def run_redis_chaos_test():
    """Test application resilience to Redis latency."""
    toxy = ToxiproxyClient()

    # Create proxy: app connects to localhost:16379 instead of redis:6379
    toxy.create_proxy("redis", listen="0.0.0.0:16379", upstream="redis:6379")

    # Test 1: Latency spike
    with toxy.latency("redis", latency_ms=2000, jitter_ms=500):
        # Exercise the app — it should timeout gracefully
        resp = requests.get("http://app:8000/api/cached-data", timeout=10)
        assert resp.status_code in (200, 503)  # either cache hit or graceful degradation

    # Test 2: Full partition
    with toxy.partition("redis"):
        resp = requests.get("http://app:8000/api/cached-data", timeout=10)
        assert resp.status_code == 503  # should degrade, not 500
```

```yaml
# --- chaos-mesh-network.yaml --- Chaos Mesh network fault CRDs ---

# Network latency injection
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: network-latency
  namespace: default
spec:
  action: delay
  mode: all
  selector:
    namespaces: [default]
    labelSelectors:
      app: myapp
  delay:
    latency: "200ms"
    jitter: "50ms"
    correlation: "25"
  direction: to
  target:
    selector:
      namespaces: [default]
      labelSelectors:
        app: postgres
    mode: all
  duration: "5m"

---
# Network partition between services
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: network-partition
  namespace: default
spec:
  action: partition
  mode: all
  selector:
    namespaces: [default]
    labelSelectors:
      app: order-service
  direction: both
  target:
    selector:
      namespaces: [default]
      labelSelectors:
        app: payment-service
    mode: all
  duration: "2m"

---
# Packet loss simulation
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: network-packet-loss
  namespace: default
spec:
  action: loss
  mode: all
  selector:
    namespaces: [default]
    labelSelectors:
      app: myapp
  loss:
    loss: "30"
    correlation: "25"
  duration: "3m"

---
# Bandwidth throttling
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: network-bandwidth
  namespace: default
spec:
  action: bandwidth
  mode: all
  selector:
    namespaces: [default]
    labelSelectors:
      app: myapp
  bandwidth:
    rate: "1mbps"
    limit: 20971520     # 20MB queue
    buffer: 10000
  duration: "5m"
```

| Tool | Layer | Features | Deployment |
|------|-------|----------|------------|
| tc/netem | Kernel (L3/L4) | Latency, loss, reorder, bandwidth | Linux host/container |
| Toxiproxy | TCP proxy (L4) | Latency, timeout, bandwidth, partition | Sidecar or standalone |
| Chaos Mesh | K8s CRD (L3-L7) | All network faults + DNS chaos | K8s operator |
| Istio fault | Service mesh (L7) | HTTP abort, delay | Istio sidecar |
| iptables | Kernel (L3) | Drop, reject, rate-limit | Linux host/container |

Key patterns:
1. Use tc/netem for raw kernel-level chaos in containers; Toxiproxy for app-layer testing
2. Always use context managers to ensure cleanup — leftover tc rules will persist across runs
3. Test both latency (degradation) and partition (total failure) — they surface different bugs
4. Chaos Mesh CRDs integrate with GitOps — version-control your experiments
5. Direct chaos at specific service-to-service links (e.g., app-to-database), not entire nodes'''
    ),
    (
        "reliability/stress-testing",
        "Show how to perform CPU, memory, and disk stress testing including programmatic control and Kubernetes stress experiments.",
        '''CPU, memory, and disk stress testing for reliability validation:

```python
# --- stress_test.py --- Programmatic resource stress ---

from __future__ import annotations

import os
import time
import signal
import tempfile
import threading
import logging
import multiprocessing
from dataclasses import dataclass
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@dataclass
class StressResult:
    target: str
    duration_seconds: float
    peak_usage: Optional[float] = None
    error: Optional[str] = None


class CPUStress:
    """Generate CPU load on specific cores."""

    @staticmethod
    def burn_cpu(duration: float = 30, cores: Optional[int] = None) -> StressResult:
        """Pin CPU at 100% for the given duration.

        Args:
            duration: How long to stress in seconds.
            cores: Number of cores to stress (default: all).
        """
        num_cores = cores or multiprocessing.cpu_count()
        stop_event = threading.Event()

        def _burn():
            while not stop_event.is_set():
                # Tight loop = 100% CPU on this thread
                _ = sum(i * i for i in range(10000))

        threads = []
        for _ in range(num_cores):
            t = threading.Thread(target=_burn, daemon=True)
            t.start()
            threads.append(t)

        logger.info(f"CPU stress: {num_cores} cores for {duration}s")
        time.sleep(duration)
        stop_event.set()

        for t in threads:
            t.join(timeout=5)

        return StressResult(target="cpu", duration_seconds=duration)

    @staticmethod
    @contextmanager
    def stress(cores: Optional[int] = None):
        """Context manager for CPU stress."""
        stop_event = threading.Event()
        num_cores = cores or multiprocessing.cpu_count()

        def _burn():
            while not stop_event.is_set():
                _ = sum(i * i for i in range(10000))

        threads = []
        for _ in range(num_cores):
            t = threading.Thread(target=_burn, daemon=True)
            t.start()
            threads.append(t)

        logger.info(f"CPU stress started on {num_cores} cores")
        try:
            yield
        finally:
            stop_event.set()
            for t in threads:
                t.join(timeout=5)
            logger.info("CPU stress stopped")


class MemoryStress:
    """Allocate and hold memory to simulate memory pressure."""

    @staticmethod
    def allocate(
        size_mb: int = 512,
        duration: float = 30,
        step_mb: int = 64,
        step_interval: float = 1.0,
    ) -> StressResult:
        """Gradually allocate memory and hold it.

        Args:
            size_mb: Total memory to allocate.
            duration: How long to hold after full allocation.
            step_mb: Allocate this much per step.
            step_interval: Seconds between allocation steps.
        """
        blocks: list[bytearray] = []
        allocated = 0

        try:
            while allocated < size_mb:
                chunk = min(step_mb, size_mb - allocated)
                blocks.append(bytearray(chunk * 1024 * 1024))
                allocated += chunk
                logger.info(f"Memory allocated: {allocated}/{size_mb} MB")
                time.sleep(step_interval)

            logger.info(f"Holding {size_mb} MB for {duration}s")
            time.sleep(duration)

        except MemoryError:
            logger.error(f"OOM at {allocated} MB")
            return StressResult(
                target="memory",
                duration_seconds=0,
                peak_usage=allocated,
                error="MemoryError",
            )
        finally:
            del blocks  # release

        return StressResult(
            target="memory", duration_seconds=duration, peak_usage=size_mb
        )


class DiskStress:
    """Fill disk space or generate I/O pressure."""

    @staticmethod
    def fill_disk(
        size_mb: int = 1024,
        path: Optional[str] = None,
        block_size_mb: int = 64,
    ) -> StressResult:
        """Write data to fill disk space."""
        target_dir = path or tempfile.gettempdir()
        filepath = os.path.join(target_dir, "chaos_disk_fill.tmp")
        written = 0

        try:
            with open(filepath, "wb") as f:
                while written < size_mb:
                    chunk = min(block_size_mb, size_mb - written)
                    f.write(os.urandom(chunk * 1024 * 1024))
                    f.flush()
                    written += chunk
                    logger.info(f"Disk filled: {written}/{size_mb} MB")

            return StressResult(
                target="disk", duration_seconds=0, peak_usage=written
            )

        except OSError as e:
            logger.error(f"Disk fill failed at {written} MB: {e}")
            return StressResult(
                target="disk", duration_seconds=0, peak_usage=written, error=str(e)
            )
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

    @staticmethod
    def io_pressure(
        duration: float = 30,
        path: Optional[str] = None,
        block_size_kb: int = 4,
    ) -> StressResult:
        """Generate random read/write I/O to stress the disk subsystem."""
        target_dir = path or tempfile.gettempdir()
        filepath = os.path.join(target_dir, "chaos_io_stress.tmp")
        start = time.monotonic()

        try:
            with open(filepath, "w+b") as f:
                while time.monotonic() - start < duration:
                    data = os.urandom(block_size_kb * 1024)
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                    f.seek(0)
                    f.read(block_size_kb * 1024)
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

        elapsed = time.monotonic() - start
        return StressResult(target="disk_io", duration_seconds=elapsed)
```

```yaml
# --- stress-chaos-mesh.yaml --- Kubernetes StressChaos CRDs ---

# CPU stress on selected pods
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: cpu-stress
  namespace: default
spec:
  mode: one               # affect one random pod
  selector:
    namespaces: [default]
    labelSelectors:
      app: myapp
  stressors:
    cpu:
      workers: 4           # 4 CPU burn threads
      load: 80             # 80% per worker
  duration: "5m"

---
# Memory stress on selected pods
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: memory-stress
  namespace: default
spec:
  mode: all
  selector:
    namespaces: [default]
    labelSelectors:
      app: myapp
  stressors:
    memory:
      workers: 2
      size: "512MB"        # each worker allocates 512MB
  duration: "3m"
  containerNames: ["app"]  # target specific container in the pod
```

```bash
# --- stress-ng command-line examples ---

# CPU stress: 4 workers, 80% load, 60 seconds
stress-ng --cpu 4 --cpu-load 80 --timeout 60s --metrics-brief

# Memory stress: 2 workers, 1GB each, 60 seconds
stress-ng --vm 2 --vm-bytes 1G --vm-method all --timeout 60s

# Disk I/O stress: 4 workers, 60 seconds
stress-ng --hdd 4 --hdd-bytes 1G --timeout 60s

# Network stress: TCP socket thrash
stress-ng --sock 4 --timeout 60s

# Combined: CPU + memory + I/O
stress-ng --cpu 2 --cpu-load 90 \
          --vm 1 --vm-bytes 512M \
          --hdd 2 --hdd-bytes 256M \
          --timeout 120s --metrics-brief

# Matrix of stress tests with monitoring
stress-ng --cpu 4 --cpu-load 80 --timeout 30s --metrics-brief && \
stress-ng --vm 2 --vm-bytes 1G --timeout 30s --metrics-brief && \
stress-ng --hdd 4 --timeout 30s --metrics-brief

# In a container (Dockerfile)
# FROM ubuntu:22.04
# RUN apt-get update && apt-get install -y stress-ng
# ENTRYPOINT ["stress-ng"]
```

| Stress Type | Tool | Target | Symptom tested |
|------------|------|--------|---------------|
| CPU saturation | stress-ng, Python threads | CPU cores | Throttling, latency spikes |
| Memory pressure | stress-ng --vm, bytearray | RAM | OOM kills, GC pressure |
| Disk fill | dd, Python write | Disk space | Write failures, log rotation |
| Disk I/O | stress-ng --hdd, fio | Disk I/O bandwidth | Slow reads/writes, timeouts |
| Network | stress-ng --sock, iperf3 | TCP stack | Connection exhaustion |
| Fork bomb | stress-ng --fork | Process table | PID exhaustion |

Key patterns:
1. Allocate memory gradually (step-wise) to observe system behavior under increasing pressure
2. Always clean up temporary files in `finally` blocks to avoid lingering disk fill
3. Use context managers for CPU stress to guarantee thread cleanup
4. In Kubernetes, use StressChaos CRDs with `containerNames` to target specific containers
5. Combine stress tests with steady-state probes to validate resilience under load'''
    ),
    (
        "reliability/chaos-experiment-design",
        "Explain how to design a chaos experiment with steady state hypothesis, blast radius control, observability, and game day planning.",
        '''Designing chaos experiments with structured methodology:

```python
# --- experiment_framework.py --- Complete chaos experiment framework ---

from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class Severity(Enum):
    LOW = "low"           # Single pod restart
    MEDIUM = "medium"     # Service degradation
    HIGH = "high"         # Multi-service impact
    CRITICAL = "critical" # Production game day


class ProbeType(Enum):
    HTTP = "http"
    PROMETHEUS = "prometheus"
    CUSTOM = "custom"


@dataclass
class SteadyStateProbe:
    """A measurable probe for steady state verification."""
    name: str
    probe_type: ProbeType
    target: str  # URL, PromQL, or custom
    expected: Any
    tolerance: float = 0.0  # acceptable deviation from expected
    timeout_seconds: float = 10.0

    def evaluate(self) -> tuple[bool, Any]:
        """Run probe and return (passed, actual_value)."""
        if self.probe_type == ProbeType.HTTP:
            return self._check_http()
        elif self.probe_type == ProbeType.PROMETHEUS:
            return self._check_prometheus()
        else:
            raise ValueError(f"Unsupported probe type: {self.probe_type}")

    def _check_http(self) -> tuple[bool, Any]:
        try:
            resp = requests.get(self.target, timeout=self.timeout_seconds)
            actual = resp.status_code
            passed = actual == self.expected
            return passed, actual
        except requests.RequestException as e:
            return False, str(e)

    def _check_prometheus(self) -> tuple[bool, Any]:
        """Query Prometheus and check against expected value."""
        try:
            resp = requests.get(
                "http://prometheus:9090/api/v1/query",
                params={"query": self.target},
                timeout=self.timeout_seconds,
            )
            data = resp.json()
            if data["status"] != "success":
                return False, "query failed"

            results = data["data"]["result"]
            if not results:
                return False, "no data"

            actual = float(results[0]["value"][1])
            deviation = abs(actual - self.expected) / max(self.expected, 1e-9)
            passed = deviation <= self.tolerance
            return passed, actual
        except Exception as e:
            return False, str(e)


@dataclass
class SteadyStateHypothesis:
    """Define what normal system behavior looks like."""
    description: str
    probes: list[SteadyStateProbe]
    min_pass_rate: float = 1.0  # all probes must pass by default

    def evaluate(self) -> tuple[bool, list[dict]]:
        results = []
        for probe in self.probes:
            passed, actual = probe.evaluate()
            results.append({
                "probe": probe.name,
                "passed": passed,
                "expected": probe.expected,
                "actual": actual,
            })
            logger.info(
                f"  Probe '{probe.name}': "
                f"{'PASS' if passed else 'FAIL'} "
                f"(expected={probe.expected}, actual={actual})"
            )

        pass_rate = sum(r["passed"] for r in results) / len(results) if results else 0
        overall = pass_rate >= self.min_pass_rate
        return overall, results


@dataclass
class BlastRadius:
    """Control the scope of chaos impact."""
    severity: Severity
    affected_services: list[str]
    affected_percentage: int = 100  # percentage of instances
    regions: list[str] = field(default_factory=lambda: ["us-east-1"])
    excluded_services: list[str] = field(default_factory=list)

    def validate(self) -> None:
        """Ensure blast radius is appropriate for severity level."""
        limits = {
            Severity.LOW: {"max_services": 1, "max_percentage": 50},
            Severity.MEDIUM: {"max_services": 3, "max_percentage": 50},
            Severity.HIGH: {"max_services": 5, "max_percentage": 75},
            Severity.CRITICAL: {"max_services": 10, "max_percentage": 100},
        }
        limit = limits[self.severity]
        if len(self.affected_services) > limit["max_services"]:
            raise ValueError(
                f"Too many services ({len(self.affected_services)}) "
                f"for severity {self.severity.value} "
                f"(max {limit['max_services']})"
            )
        if self.affected_percentage > limit["max_percentage"]:
            raise ValueError(
                f"Percentage {self.affected_percentage}% too high "
                f"for severity {self.severity.value}"
            )


@dataclass
class ChaosAction:
    """A single fault injection action."""
    name: str
    description: str
    execute: Callable[[], None]
    rollback: Callable[[], None]
    duration: timedelta = field(default_factory=lambda: timedelta(minutes=5))


@dataclass
class ExperimentPlan:
    """Complete chaos experiment plan."""
    name: str
    description: str
    hypothesis: SteadyStateHypothesis
    blast_radius: BlastRadius
    actions: list[ChaosAction]
    prerequisites: list[str] = field(default_factory=list)
    abort_conditions: list[SteadyStateProbe] = field(default_factory=list)
    owner: str = ""
    approved_by: str = ""
    scheduled_at: Optional[datetime] = None


@dataclass
class ExperimentResult:
    """Results of a completed experiment."""
    experiment_name: str
    status: str  # passed, failed, aborted
    started_at: datetime
    ended_at: datetime
    pre_check: list[dict]
    post_check: list[dict]
    actions_executed: list[str]
    findings: list[str] = field(default_factory=list)

    def to_report(self) -> str:
        duration = self.ended_at - self.started_at
        lines = [
            f"# Chaos Experiment Report: {self.experiment_name}",
            f"Status: {self.status.upper()}",
            f"Duration: {duration}",
            f"Started: {self.started_at.isoformat()}",
            f"Ended: {self.ended_at.isoformat()}",
            "",
            "## Actions Executed",
            *[f"- {a}" for a in self.actions_executed],
            "",
            "## Findings",
            *[f"- {f}" for f in self.findings] if self.findings else ["- No issues found"],
        ]
        return "\n".join(lines)
```

```python
# --- experiment_runner.py --- Execute and monitor experiments ---

from experiment_framework import (
    ExperimentPlan, ExperimentResult, SteadyStateProbe, ChaosAction
)
from datetime import datetime
import time
import logging

logger = logging.getLogger(__name__)


class ExperimentRunner:
    """Execute chaos experiments with safety controls."""

    def __init__(self, abort_check_interval: float = 10.0):
        self.abort_check_interval = abort_check_interval

    def run(self, plan: ExperimentPlan) -> ExperimentResult:
        """Execute the experiment with full lifecycle management."""
        started_at = datetime.utcnow()
        actions_executed: list[str] = []
        findings: list[str] = []

        logger.info(f"{'='*60}")
        logger.info(f"EXPERIMENT: {plan.name}")
        logger.info(f"{'='*60}")

        # Validate blast radius
        try:
            plan.blast_radius.validate()
        except ValueError as e:
            logger.error(f"Blast radius validation failed: {e}")
            return ExperimentResult(
                experiment_name=plan.name,
                status="aborted",
                started_at=started_at,
                ended_at=datetime.utcnow(),
                pre_check=[], post_check=[],
                actions_executed=[],
                findings=[f"Blast radius rejected: {e}"],
            )

        # Pre-check: verify steady state
        logger.info("--- Pre-experiment steady state check ---")
        pre_passed, pre_results = plan.hypothesis.evaluate()
        if not pre_passed:
            logger.error("Pre-check FAILED — system not in steady state, aborting")
            return ExperimentResult(
                experiment_name=plan.name,
                status="aborted",
                started_at=started_at,
                ended_at=datetime.utcnow(),
                pre_check=pre_results, post_check=[],
                actions_executed=[],
                findings=["System not in steady state before experiment"],
            )

        # Execute chaos actions
        logger.info("--- Injecting chaos ---")
        rollbacks: list = []
        try:
            for action in plan.actions:
                # Check abort conditions before each action
                if self._should_abort(plan.abort_conditions):
                    logger.warning("ABORT condition triggered — stopping")
                    findings.append(f"Aborted before: {action.name}")
                    break

                logger.info(f"Executing: {action.name}")
                action.execute()
                actions_executed.append(action.name)
                rollbacks.append(action.rollback)

                # Wait for action duration with periodic abort checks
                self._wait_with_abort_checks(
                    action.duration.total_seconds(),
                    plan.abort_conditions,
                )

        except Exception as e:
            logger.error(f"Chaos action failed: {e}")
            findings.append(f"Action error: {e}")

        # Post-check: verify steady state after chaos
        logger.info("--- Post-experiment steady state check ---")
        # Brief stabilization period
        time.sleep(30)
        post_passed, post_results = plan.hypothesis.evaluate()

        if post_passed:
            logger.info("System RECOVERED — experiment PASSED")
            status = "passed"
        else:
            logger.warning("System DID NOT RECOVER — experiment FAILED")
            status = "failed"
            findings.append("System failed to return to steady state")

        # Rollback all actions
        logger.info("--- Rolling back ---")
        for rollback_fn in reversed(rollbacks):
            try:
                rollback_fn()
            except Exception as e:
                logger.error(f"Rollback error: {e}")
                findings.append(f"Rollback error: {e}")

        return ExperimentResult(
            experiment_name=plan.name,
            status=status,
            started_at=started_at,
            ended_at=datetime.utcnow(),
            pre_check=pre_results,
            post_check=post_results,
            actions_executed=actions_executed,
            findings=findings,
        )

    def _should_abort(self, conditions: list[SteadyStateProbe]) -> bool:
        for probe in conditions:
            passed, actual = probe.evaluate()
            if not passed:
                logger.warning(f"Abort condition met: {probe.name} = {actual}")
                return True
        return False

    def _wait_with_abort_checks(
        self, total_seconds: float, abort_conditions: list[SteadyStateProbe]
    ) -> None:
        elapsed = 0
        while elapsed < total_seconds:
            wait = min(self.abort_check_interval, total_seconds - elapsed)
            time.sleep(wait)
            elapsed += wait
            if self._should_abort(abort_conditions):
                raise RuntimeError("Abort condition triggered during wait")
```

```python
# --- game_day.py --- Game day planning template ---

from experiment_framework import (
    ExperimentPlan, SteadyStateHypothesis, SteadyStateProbe,
    ProbeType, BlastRadius, Severity, ChaosAction,
)
from experiment_runner import ExperimentRunner
from datetime import timedelta


def build_game_day_plan() -> list[ExperimentPlan]:
    """Build a structured game day with multiple experiments."""

    # Shared steady state hypothesis
    hypothesis = SteadyStateHypothesis(
        description="API responds < 500ms at p99, error rate < 1%",
        probes=[
            SteadyStateProbe(
                name="api-health",
                probe_type=ProbeType.HTTP,
                target="http://api.internal/health",
                expected=200,
            ),
            SteadyStateProbe(
                name="error-rate",
                probe_type=ProbeType.PROMETHEUS,
                target='rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])',
                expected=0.01,
                tolerance=0.5,  # 50% deviation from 1% = up to 1.5%
            ),
            SteadyStateProbe(
                name="p99-latency",
                probe_type=ProbeType.PROMETHEUS,
                target='histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))',
                expected=0.5,    # 500ms
                tolerance=0.5,   # up to 750ms
            ),
        ],
    )

    # Abort if error rate exceeds 10%
    abort_conditions = [
        SteadyStateProbe(
            name="critical-error-rate",
            probe_type=ProbeType.PROMETHEUS,
            target='rate(http_requests_total{status=~"5.."}[1m]) / rate(http_requests_total[1m])',
            expected=0.10,
            tolerance=0.0,
        ),
    ]

    experiments = [
        # Experiment 1: Single pod failure
        ExperimentPlan(
            name="Single API Pod Kill",
            description="Kill one API pod to verify auto-recovery",
            hypothesis=hypothesis,
            blast_radius=BlastRadius(
                severity=Severity.LOW,
                affected_services=["api"],
                affected_percentage=33,  # 1 of 3 pods
            ),
            actions=[
                ChaosAction(
                    name="Kill one API pod",
                    description="Delete a random API pod",
                    execute=lambda: None,  # k8s_chaos.kill_random_pod(...)
                    rollback=lambda: None,  # pods auto-recover via ReplicaSet
                    duration=timedelta(minutes=5),
                ),
            ],
            abort_conditions=abort_conditions,
            owner="sre-team",
        ),

        # Experiment 2: Database latency
        ExperimentPlan(
            name="Database Latency Injection",
            description="Add 500ms latency to database calls",
            hypothesis=hypothesis,
            blast_radius=BlastRadius(
                severity=Severity.MEDIUM,
                affected_services=["api", "worker"],
                affected_percentage=100,
            ),
            actions=[
                ChaosAction(
                    name="Inject DB latency",
                    description="Add 500ms latency via Toxiproxy",
                    execute=lambda: None,  # toxiproxy.add_toxic("postgres", "latency", ...)
                    rollback=lambda: None,  # toxiproxy.remove_toxic(...)
                    duration=timedelta(minutes=10),
                ),
            ],
            abort_conditions=abort_conditions,
            owner="sre-team",
        ),

        # Experiment 3: Cache partition
        ExperimentPlan(
            name="Redis Cache Partition",
            description="Simulate Redis outage to verify cache fallback",
            hypothesis=hypothesis,
            blast_radius=BlastRadius(
                severity=Severity.MEDIUM,
                affected_services=["api"],
                affected_percentage=100,
            ),
            actions=[
                ChaosAction(
                    name="Partition Redis",
                    description="Block all traffic to Redis",
                    execute=lambda: None,
                    rollback=lambda: None,
                    duration=timedelta(minutes=5),
                ),
            ],
            abort_conditions=abort_conditions,
            owner="sre-team",
        ),
    ]

    return experiments


def run_game_day() -> None:
    """Execute a full game day with progressive severity."""
    runner = ExperimentRunner(abort_check_interval=15.0)
    plans = build_game_day_plan()

    results = []
    for plan in plans:
        result = runner.run(plan)
        results.append(result)

        print(result.to_report())
        print()

        # Stop game day if any experiment fails
        if result.status == "failed":
            print(f"GAME DAY HALTED: {plan.name} failed")
            break
```

| Phase | Activity | Duration |
|-------|----------|----------|
| Preparation | Define hypothesis, probes, blast radius | 1-2 days before |
| Pre-game | Verify monitoring, alert team, confirm rollback | 1 hour before |
| Warm-up | Run LOW severity experiments | 30 minutes |
| Main event | Run MEDIUM/HIGH severity experiments | 2-3 hours |
| Cooldown | Verify all rollbacks, check metrics | 30 minutes |
| Retrospective | Document findings, create action items | Same day |

Key patterns:
1. Define the steady state hypothesis FIRST — you cannot assess chaos without a measurable baseline
2. Validate blast radius programmatically before execution (reject over-scoped experiments)
3. Include abort conditions that halt the experiment if safety thresholds are breached
4. Progress severity gradually: LOW -> MEDIUM -> HIGH, halting if any experiment fails
5. Game days require pre-approval, team notification, and same-day retrospective with action items'''
    ),
]
