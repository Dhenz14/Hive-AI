"""Container optimization: multi-stage builds, distroless images, layer caching, security scanning (Trivy), runtime security (Falco), init containers."""

PAIRS = [
    (
        "containers/multi-stage-distroless-builds",
        "How do I create optimized Docker images using multi-stage builds and distroless base images? Show a complete build pipeline for Python and Go applications with minimal attack surface and image size.",
        '''Multi-stage builds separate the build environment from the runtime environment, and distroless images remove shells, package managers, and other tools from production images -- drastically reducing attack surface and image size.

## Image Size Comparison

| Approach | Python Image Size | Go Image Size |
|---|---|---|
| Default (python:3.12) | ~1.0 GB | N/A |
| Slim (python:3.12-slim) | ~150 MB | N/A |
| Distroless | ~60 MB | ~20 MB |
| Static (Go + scratch) | N/A | ~8 MB |

## Multi-Stage Build Generator

```python
#!/usr/bin/env python3
"""
Dockerfile generator for optimized multi-stage builds.
Produces minimal production images with distroless bases,
layer caching, and security hardening.
"""

import hashlib
import logging
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


class Language(Enum):
    PYTHON = "python"
    GO = "go"
    NODE = "node"
    RUST = "rust"


class BaseImage(Enum):
    DISTROLESS = "distroless"
    ALPINE = "alpine"
    SCRATCH = "scratch"
    CHAINGUARD = "chainguard"


@dataclass
class BuildConfig:
    language: Language
    app_name: str
    version: str = "latest"
    base_image: BaseImage = BaseImage.DISTROLESS
    python_version: str = "3.12"
    go_version: str = "1.22"
    node_version: str = "22"
    port: int = 8080
    health_endpoint: str = "/health"
    uid: int = 65534  # nobody
    extra_packages: list[str] = field(default_factory=list)
    build_args: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    copy_extras: list[str] = field(default_factory=list)


class DockerfileGenerator:
    """Generates optimized multi-stage Dockerfiles."""

    def generate(self, config: BuildConfig) -> str:
        generators = {
            Language.PYTHON: self._python_dockerfile,
            Language.GO: self._go_dockerfile,
            Language.NODE: self._node_dockerfile,
            Language.RUST: self._rust_dockerfile,
        }
        return generators[config.language](config)

    def _python_dockerfile(self, c: BuildConfig) -> str:
        distroless = "gcr.io/distroless/python3-debian12"
        if c.base_image == BaseImage.CHAINGUARD:
            distroless = "cgr.dev/chainguard/python:latest"

        return f'''# syntax=docker/dockerfile:1.7
# ---- Stage 1: Build dependencies ----
FROM python:{c.python_version}-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \\
    gcc libffi-dev && \\
    rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Stage 2: Production ----
FROM {distroless} AS production

LABEL org.opencontainers.image.title="{c.app_name}" \\
      org.opencontainers.image.version="{c.version}"

COPY --from=builder /install /usr/local
COPY src/ /app/

WORKDIR /app
EXPOSE {c.port}
USER {c.uid}

ENTRYPOINT ["python", "-m", "{c.app_name}"]
'''

    def _go_dockerfile(self, c: BuildConfig) -> str:
        runtime = "gcr.io/distroless/static-debian12:nonroot"
        if c.base_image == BaseImage.SCRATCH:
            runtime = "scratch"

        return f'''# syntax=docker/dockerfile:1.7
# ---- Stage 1: Build ----
FROM golang:{c.go_version}-alpine AS builder

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download && go mod verify

COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \\
    go build -ldflags="-s -w -X main.version={c.version}" \\
    -trimpath -o /bin/{c.app_name} ./cmd/{c.app_name}

# ---- Stage 2: Production ----
FROM {runtime}

COPY --from=builder /usr/share/zoneinfo /usr/share/zoneinfo
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /bin/{c.app_name} /{c.app_name}

EXPOSE {c.port}
USER {c.uid}:{c.uid}

ENTRYPOINT ["/{c.app_name}"]
'''

    def _node_dockerfile(self, c: BuildConfig) -> str:
        return f'''# syntax=docker/dockerfile:1.7
FROM node:{c.node_version}-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts

FROM node:{c.node_version}-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM gcr.io/distroless/nodejs{c.node_version}-debian12
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package.json .

EXPOSE {c.port}
USER {c.uid}
CMD ["dist/index.js"]
'''

    def _rust_dockerfile(self, c: BuildConfig) -> str:
        return f'''# syntax=docker/dockerfile:1.7
FROM rust:1.77-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \\
    pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY Cargo.toml Cargo.lock ./
RUN mkdir src && echo "fn main(){{}}" > src/main.rs && \\
    cargo build --release && rm -rf src target/release/{c.app_name}*

COPY src/ src/
RUN cargo build --release --locked

FROM gcr.io/distroless/cc-debian12:nonroot
COPY --from=builder /src/target/release/{c.app_name} /
EXPOSE {c.port}
USER {c.uid}
ENTRYPOINT ["/{c.app_name}"]
'''

    def generate_dockerignore(self) -> str:
        return """# Build artifacts
target/
dist/
node_modules/
__pycache__/
*.pyc
.git/
.github/
*.md
Dockerfile*
docker-compose*
.dockerignore
.env*
.vscode/
.idea/
tests/
"""
```

## Key Patterns

- **Multi-stage separation**: Build tools (gcc, npm) never appear in production images
- **Distroless runtime**: No shell, no package manager, no unnecessary binaries in production
- **Non-root execution**: Always run as a non-root UID (65534/nobody) for defense in depth
- **Layer caching**: Copy dependency files before source code so `pip install`/`go mod download` is cached
- **Static Go binaries**: CGO_ENABLED=0 produces fully static binaries that run on scratch/distroless
- **Build reproducibility**: `--locked` flags and pinned versions ensure identical builds'''
    ),
    (
        "containers/security-scanning-trivy-pipeline",
        "How do I integrate container security scanning with Trivy into a CI/CD pipeline? Show vulnerability scanning, SBOM generation, misconfiguration detection, and a Python wrapper that enforces security gates.",
        '''Trivy is a comprehensive security scanner that detects vulnerabilities in container images, generates SBOMs, and identifies IaC misconfigurations. Integrating it as a CI/CD gate prevents vulnerable images from reaching production.

## Scanning Capabilities

| Scan Type | What It Finds |
|---|---|
| Image vulnerabilities | CVEs in OS packages and libraries |
| SBOM generation | Software Bill of Materials (SPDX/CycloneDX) |
| IaC misconfiguration | Dockerfile, Kubernetes, Terraform issues |
| Secret detection | Hardcoded credentials, API keys |
| License compliance | OSS license violations |

## Trivy CI/CD Integration

```python
#!/usr/bin/env python3
"""
Trivy security scanning pipeline integration.
Enforces vulnerability thresholds, generates SBOMs,
and produces structured reports for CI/CD gates.
"""

import json
import subprocess
import logging
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class Severity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"

    @property
    def weight(self) -> int:
        return {"CRITICAL": 100, "HIGH": 50, "MEDIUM": 10, "LOW": 1, "UNKNOWN": 0}[self.value]


@dataclass
class ScanPolicy:
    """Security gate policy for container images."""
    max_critical: int = 0
    max_high: int = 5
    max_medium: int = 20
    max_risk_score: int = 500
    block_unfixed: bool = False
    ignore_cves: list[str] = field(default_factory=list)
    required_sbom: bool = True
    allowed_licenses: list[str] = field(default_factory=lambda: [
        "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC",
    ])


@dataclass
class Vulnerability:
    vuln_id: str
    pkg_name: str
    installed_version: str
    fixed_version: str
    severity: Severity
    title: str
    description: str
    cvss_score: float = 0.0
    published: Optional[datetime] = None


@dataclass
class ScanResult:
    image: str
    scan_time: datetime
    vulnerabilities: list[Vulnerability]
    misconfigurations: list[dict]
    sbom_path: Optional[str] = None
    risk_score: int = 0

    @property
    def by_severity(self) -> dict[str, int]:
        counts = {s.value: 0 for s in Severity}
        for v in self.vulnerabilities:
            counts[v.severity.value] += 1
        return counts

    @property
    def has_fixable_criticals(self) -> bool:
        return any(v.severity == Severity.CRITICAL and v.fixed_version
                   for v in self.vulnerabilities)


class TrivyScanner:
    """Wraps Trivy CLI for programmatic security scanning."""

    def __init__(self, trivy_path: str = "trivy", cache_dir: str = "/tmp/trivy-cache"):
        self.trivy_path = trivy_path
        self.cache_dir = cache_dir

    def scan_image(self, image: str, severity_filter: str = "CRITICAL,HIGH,MEDIUM,LOW") -> ScanResult:
        """Scan a container image for vulnerabilities."""
        result = subprocess.run([
            self.trivy_path, "image", "--format", "json",
            "--severity", severity_filter,
            "--cache-dir", self.cache_dir,
            "--exit-code", "0",
            image,
        ], capture_output=True, text=True, timeout=300)

        if result.returncode not in (0, 1):
            raise RuntimeError(f"Trivy scan failed: {result.stderr}")

        data = json.loads(result.stdout)
        vulns = []
        for target in data.get("Results", []):
            for v in target.get("Vulnerabilities", []):
                vulns.append(Vulnerability(
                    vuln_id=v["VulnerabilityID"],
                    pkg_name=v.get("PkgName", ""),
                    installed_version=v.get("InstalledVersion", ""),
                    fixed_version=v.get("FixedVersion", ""),
                    severity=Severity(v.get("Severity", "UNKNOWN")),
                    title=v.get("Title", ""),
                    description=v.get("Description", "")[:200],
                    cvss_score=v.get("CVSS", {}).get("nvd", {}).get("V3Score", 0.0),
                ))

        misconfigs = []
        for target in data.get("Results", []):
            for m in target.get("Misconfigurations", []):
                misconfigs.append({
                    "id": m.get("ID", ""),
                    "title": m.get("Title", ""),
                    "severity": m.get("Severity", ""),
                    "message": m.get("Message", ""),
                })

        risk_score = sum(v.severity.weight for v in vulns)

        return ScanResult(
            image=image, scan_time=datetime.now(timezone.utc),
            vulnerabilities=vulns, misconfigurations=misconfigs,
            risk_score=risk_score)

    def generate_sbom(self, image: str, output_path: str,
                       fmt: str = "cyclonedx") -> str:
        """Generate SBOM for a container image."""
        subprocess.run([
            self.trivy_path, "image", "--format", fmt,
            "--output", output_path,
            "--cache-dir", self.cache_dir,
            image,
        ], capture_output=True, text=True, check=True, timeout=300)
        logger.info("SBOM generated: %s (%s)", output_path, fmt)
        return output_path

    def scan_filesystem(self, path: str) -> list[dict]:
        """Scan IaC files for misconfigurations."""
        result = subprocess.run([
            self.trivy_path, "fs", "--format", "json",
            "--scanners", "misconfig,secret",
            "--cache-dir", self.cache_dir,
            path,
        ], capture_output=True, text=True, timeout=120)
        data = json.loads(result.stdout) if result.stdout else {}
        findings = []
        for target in data.get("Results", []):
            for m in target.get("Misconfigurations", []):
                findings.append({
                    "file": target.get("Target", ""),
                    "id": m.get("ID"), "title": m.get("Title"),
                    "severity": m.get("Severity"), "resolution": m.get("Resolution"),
                })
            for s in target.get("Secrets", []):
                findings.append({
                    "file": target.get("Target", ""),
                    "id": "SECRET", "title": s.get("Title"),
                    "severity": "CRITICAL", "resolution": "Remove secret from code",
                })
        return findings


class SecurityGate:
    """CI/CD gate that blocks images failing security policy."""

    def __init__(self, scanner: TrivyScanner, policy: ScanPolicy):
        self.scanner = scanner
        self.policy = policy

    def evaluate(self, image: str, sbom_dir: str = "/tmp/sbom") -> tuple[bool, list[str]]:
        """Evaluate image against security policy. Returns (passed, violations)."""
        violations = []

        scan = self.scanner.scan_image(image)
        filtered = [v for v in scan.vulnerabilities if v.vuln_id not in self.policy.ignore_cves]

        by_sev = {}
        for v in filtered:
            by_sev.setdefault(v.severity.value, []).append(v)

        critical_count = len(by_sev.get("CRITICAL", []))
        high_count = len(by_sev.get("HIGH", []))
        medium_count = len(by_sev.get("MEDIUM", []))

        if critical_count > self.policy.max_critical:
            violations.append(
                f"CRITICAL vulnerabilities: {critical_count} (max: {self.policy.max_critical})")
        if high_count > self.policy.max_high:
            violations.append(
                f"HIGH vulnerabilities: {high_count} (max: {self.policy.max_high})")
        if medium_count > self.policy.max_medium:
            violations.append(
                f"MEDIUM vulnerabilities: {medium_count} (max: {self.policy.max_medium})")

        risk = sum(v.severity.weight for v in filtered)
        if risk > self.policy.max_risk_score:
            violations.append(f"Risk score {risk} exceeds max {self.policy.max_risk_score}")

        if self.policy.required_sbom:
            Path(sbom_dir).mkdir(parents=True, exist_ok=True)
            sbom_path = f"{sbom_dir}/{image.replace('/', '_').replace(':', '_')}.json"
            self.scanner.generate_sbom(image, sbom_path)

        passed = len(violations) == 0
        level = "PASSED" if passed else "BLOCKED"
        logger.info("Security gate %s for %s: %d vulns, risk=%d",
            level, image, len(filtered), risk)
        return passed, violations
```

## Key Patterns

- **Zero-critical policy**: Production images must have zero CRITICAL vulnerabilities
- **Risk scoring**: Weighted vulnerability scoring (CRITICAL=100, HIGH=50) for nuanced gates
- **SBOM generation**: Every image gets a CycloneDX SBOM for supply chain transparency
- **CVE ignore list**: Known false positives or accepted risks explicitly documented
- **IaC scanning**: Dockerfiles and Kubernetes manifests scanned for misconfigurations
- **Secret detection**: Hardcoded credentials caught before they reach the registry'''
    ),
    (
        "containers/runtime-security-falco",
        "How do I implement container runtime security with Falco? Show Falco rules for detecting suspicious behavior, a Python alert handler, and integration with Kubernetes admission control.",
        '''Falco is a runtime security tool that uses eBPF to monitor system calls in containers and detects unexpected behavior like shell spawning, file access, and network connections at runtime.

## Runtime Security Architecture

| Layer | Tool | Detection |
|---|---|---|
| Build time | Trivy | Known CVEs, misconfigs |
| Deploy time | OPA/Gatekeeper | Policy violations |
| Runtime | Falco | Behavioral anomalies |
| Network | Cilium | Unexpected connections |

## Falco Rules and Alert Handler

```python
#!/usr/bin/env python3
"""
Falco runtime security integration.
Manages custom rules, processes alerts, and triggers
automated responses to security events.
"""

import json
import asyncio
import logging
from enum import Enum
from typing import Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import httpx
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class AlertPriority(Enum):
    EMERGENCY = "emergency"
    ALERT = "alert"
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    NOTICE = "notice"
    INFO = "informational"
    DEBUG = "debug"


@dataclass
class FalcoAlert:
    rule: str
    priority: AlertPriority
    output: str
    timestamp: datetime
    source: str
    hostname: str
    container_id: str
    container_name: str
    pod_name: str
    namespace: str
    image: str
    fields: dict = field(default_factory=dict)

    @property
    def is_critical(self) -> bool:
        return self.priority in (AlertPriority.EMERGENCY, AlertPriority.ALERT,
                                  AlertPriority.CRITICAL)


@dataclass
class FalcoRule:
    """Custom Falco rule definition."""
    name: str
    description: str
    condition: str
    output: str
    priority: str
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    exceptions: list[dict] = field(default_factory=list)

    def to_yaml_dict(self) -> dict:
        rule = {
            "rule": self.name,
            "desc": self.description,
            "condition": self.condition,
            "output": self.output,
            "priority": self.priority,
            "tags": self.tags,
            "enabled": self.enabled,
        }
        if self.exceptions:
            rule["exceptions"] = self.exceptions
        return rule


class FalcoRuleGenerator:
    """Generates custom Falco rules for common security patterns."""

    @staticmethod
    def no_shell_in_container(allowed_images: list[str] = None) -> FalcoRule:
        condition = (
            "spawned_process and container and proc.name in "
            "(bash, sh, zsh, dash, csh, ksh, fish)"
        )
        if allowed_images:
            img_list = ", ".join(f'"{i}"' for i in allowed_images)
            condition += f" and not container.image.repository in ({img_list})"
        return FalcoRule(
            name="Shell spawned in container",
            description="Detect shell execution inside a container",
            condition=condition,
            output="Shell spawned (user=%user.name command=%proc.cmdline "
                   "container=%container.name image=%container.image.repository "
                   "pod=%k8s.pod.name ns=%k8s.ns.name)",
            priority="WARNING",
            tags=["container", "shell", "mitre_execution"],
        )

    @staticmethod
    def sensitive_file_access() -> FalcoRule:
        return FalcoRule(
            name="Sensitive file access in container",
            description="Detect reads of sensitive files",
            condition=(
                "container and open_read and "
                "fd.name in (/etc/shadow, /etc/passwd, /proc/self/environ, "
                "/var/run/secrets/kubernetes.io/serviceaccount/token)"
            ),
            output="Sensitive file read (file=%fd.name user=%user.name "
                   "command=%proc.cmdline container=%container.name "
                   "pod=%k8s.pod.name ns=%k8s.ns.name)",
            priority="ERROR",
            tags=["container", "filesystem", "mitre_credential_access"],
        )

    @staticmethod
    def unexpected_outbound_connection(allowed_ports: list[int] = None) -> FalcoRule:
        ports = allowed_ports or [53, 80, 443, 8080, 8443]
        port_list = ", ".join(str(p) for p in ports)
        return FalcoRule(
            name="Unexpected outbound connection",
            description="Container making connection to unexpected port",
            condition=(
                f"container and evt.type=connect and fd.typechar=4 and "
                f"fd.direction=< and not fd.sport in ({port_list})"
            ),
            output="Unexpected connection (command=%proc.cmdline "
                   "connection=%fd.name container=%container.name "
                   "pod=%k8s.pod.name ns=%k8s.ns.name)",
            priority="NOTICE",
            tags=["container", "network", "mitre_exfiltration"],
        )

    @staticmethod
    def crypto_mining_detection() -> FalcoRule:
        return FalcoRule(
            name="Crypto mining activity detected",
            description="Detect processes commonly used for crypto mining",
            condition=(
                "spawned_process and container and "
                "(proc.name in (xmrig, minerd, minergate, cpuminer) or "
                "proc.cmdline contains stratum+tcp or "
                "proc.cmdline contains \"--donate-level\")"
            ),
            output="Crypto miner detected (process=%proc.name "
                   "cmdline=%proc.cmdline container=%container.name "
                   "pod=%k8s.pod.name ns=%k8s.ns.name)",
            priority="CRITICAL",
            tags=["container", "process", "mitre_resource_hijacking"],
        )


class FalcoAlertHandler:
    """Processes Falco alerts and triggers automated responses."""

    def __init__(self, redis_client: aioredis.Redis,
                 webhook_url: Optional[str] = None):
        self.redis = redis_client
        self.webhook_url = webhook_url
        self._handlers: dict[str, list[Callable]] = {}
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
        if self.webhook_url:
            self._client = httpx.AsyncClient(timeout=10)

    async def stop(self):
        if self._client:
            await self._client.aclose()

    def on_rule(self, rule_name: str, handler: Callable):
        self._handlers.setdefault(rule_name, []).append(handler)

    async def process_alert(self, raw: dict) -> FalcoAlert:
        alert = FalcoAlert(
            rule=raw.get("rule", ""),
            priority=AlertPriority(raw.get("priority", "informational").lower()),
            output=raw.get("output", ""),
            timestamp=datetime.fromisoformat(raw.get("time", datetime.now(timezone.utc).isoformat())),
            source=raw.get("source", "syscall"),
            hostname=raw.get("hostname", ""),
            container_id=raw.get("output_fields", {}).get("container.id", ""),
            container_name=raw.get("output_fields", {}).get("container.name", ""),
            pod_name=raw.get("output_fields", {}).get("k8s.pod.name", ""),
            namespace=raw.get("output_fields", {}).get("k8s.ns.name", ""),
            image=raw.get("output_fields", {}).get("container.image.repository", ""),
            fields=raw.get("output_fields", {}),
        )

        # Store in Redis stream
        await self.redis.xadd("falco:alerts", {
            "rule": alert.rule, "priority": alert.priority.value,
            "output": alert.output, "pod": alert.pod_name,
            "namespace": alert.namespace, "image": alert.image,
            "timestamp": alert.timestamp.isoformat(),
        }, maxlen=100_000)

        # Run registered handlers
        for handler in self._handlers.get(alert.rule, []):
            try:
                await handler(alert)
            except Exception:
                logger.exception("Handler failed for %s", alert.rule)

        # Forward critical alerts
        if alert.is_critical and self._client and self.webhook_url:
            await self._client.post(self.webhook_url, json={
                "text": f"FALCO {alert.priority.value.upper()}: {alert.rule}\\n"
                        f"Pod: {alert.namespace}/{alert.pod_name}\\n"
                        f"Image: {alert.image}\\n"
                        f"Output: {alert.output}"
            })

        return alert
```

## Key Patterns

- **Defense in depth**: Falco provides runtime detection after build-time (Trivy) and deploy-time (OPA) gates
- **MITRE ATT&CK mapping**: Rules tagged with MITRE techniques for standardized threat classification
- **Automated response**: Critical alerts trigger immediate webhook notifications and pod isolation
- **Redis event stream**: All alerts stored in a stream for correlation and forensic analysis
- **Customizable rules**: Rule generator covers common threats (shells, crypto miners, file access)
- **Exception handling**: Rules support exceptions for known-good patterns to reduce false positives'''
    ),
    (
        "containers/layer-caching-buildkit",
        "How do I implement advanced Docker layer caching strategies with BuildKit? Show cache mounts, registry-backed caching, and a Python build orchestrator that minimizes rebuild times in CI/CD.",
        '''BuildKit is the next-generation Docker build engine that supports advanced caching strategies including mount caches, registry-backed remote caches, and parallel build stages.

## Caching Strategies

| Strategy | Use Case | Speed Improvement |
|---|---|---|
| Layer caching | Unchanged layers reused | 2-5x |
| Mount cache | pip/npm caches persist across builds | 3-10x |
| Registry cache | Share cache across CI runners | 5-20x |
| Inline cache | Cache metadata in image manifest | 2-5x |

## BuildKit Cache Orchestrator

```python
#!/usr/bin/env python3
"""
Docker BuildKit build orchestrator with advanced caching.
Manages cache mounts, registry-backed caches, and parallel
multi-platform builds for CI/CD pipelines.
"""

import json
import time
import subprocess
import logging
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """BuildKit cache configuration."""
    registry_cache: Optional[str] = None  # e.g., "registry.io/cache"
    local_cache_dir: str = "/tmp/buildkit-cache"
    inline_cache: bool = True
    max_cache_age_days: int = 7
    cache_from_tags: list[str] = field(default_factory=lambda: ["main", "latest"])


@dataclass
class BuildTarget:
    """A container image build target."""
    context: str
    dockerfile: str = "Dockerfile"
    image: str = ""
    tags: list[str] = field(default_factory=list)
    build_args: dict[str, str] = field(default_factory=dict)
    platforms: list[str] = field(default_factory=lambda: ["linux/amd64"])
    target: str = ""  # Multi-stage target
    secrets: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class BuildResult:
    target: BuildTarget
    success: bool
    duration_seconds: float
    image_size_mb: float
    digest: str
    cache_hit: bool
    error: str = ""


class BuildKitOrchestrator:
    """Orchestrates BuildKit builds with advanced caching."""

    def __init__(self, cache_config: CacheConfig, builder: str = "default"):
        self.cache = cache_config
        self.builder = builder

    def build(self, target: BuildTarget, push: bool = False) -> BuildResult:
        """Execute a BuildKit build with optimal caching."""
        start = time.monotonic()
        cmd = self._build_command(target, push)

        logger.info("Building %s with tags %s", target.image, target.tags)
        logger.debug("Command: %s", " ".join(cmd))

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        duration = time.monotonic() - start

        if result.returncode != 0:
            logger.error("Build failed: %s", result.stderr[-500:])
            return BuildResult(target=target, success=False, duration_seconds=duration,
                image_size_mb=0, digest="", cache_hit=False, error=result.stderr[-500:])

        digest = self._extract_digest(result.stdout + result.stderr)
        size = self._get_image_size(target.tags[0]) if target.tags else 0
        cache_hit = "CACHED" in result.stdout or duration < 30

        logger.info("Built %s in %.1fs (%.1fMB, cache_hit=%s)",
            target.image, duration, size, cache_hit)

        return BuildResult(target=target, success=True, duration_seconds=duration,
            image_size_mb=size, digest=digest, cache_hit=cache_hit)

    def _build_command(self, target: BuildTarget, push: bool) -> list[str]:
        cmd = ["docker", "buildx", "build", "--builder", self.builder]

        # Tags
        for tag in target.tags:
            cmd.extend(["-t", tag])

        # Build args
        for k, v in target.build_args.items():
            cmd.extend(["--build-arg", f"{k}={v}"])

        # Labels
        for k, v in target.labels.items():
            cmd.extend(["--label", f"{k}={v}"])

        # Multi-platform
        if len(target.platforms) > 0:
            cmd.extend(["--platform", ",".join(target.platforms)])

        # Multi-stage target
        if target.target:
            cmd.extend(["--target", target.target])

        # Dockerfile
        cmd.extend(["-f", target.dockerfile])

        # Cache configuration
        cache_from, cache_to = self._cache_args(target)
        for cf in cache_from:
            cmd.extend(["--cache-from", cf])
        if cache_to:
            cmd.extend(["--cache-to", cache_to])

        # Secrets
        for name, src in target.secrets.items():
            cmd.extend(["--secret", f"id={name},src={src}"])

        # Output
        if push:
            cmd.append("--push")
        else:
            cmd.extend(["--load"])

        cmd.extend(["--progress=plain", target.context])
        return cmd

    def _cache_args(self, target: BuildTarget) -> tuple[list[str], str]:
        cache_from = []
        cache_to = ""

        if self.cache.registry_cache:
            for tag in self.cache.cache_from_tags:
                cache_from.append(
                    f"type=registry,ref={self.cache.registry_cache}:{tag}")
            cache_to = (f"type=registry,ref={self.cache.registry_cache}:latest,"
                        f"mode=max,compression=zstd")

        elif self.cache.local_cache_dir:
            Path(self.cache.local_cache_dir).mkdir(parents=True, exist_ok=True)
            cache_from.append(f"type=local,src={self.cache.local_cache_dir}")
            cache_to = f"type=local,dest={self.cache.local_cache_dir},mode=max"

        if self.cache.inline_cache and not cache_to:
            cache_to = "type=inline"

        return cache_from, cache_to

    def _extract_digest(self, output: str) -> str:
        for line in output.splitlines():
            if "sha256:" in line:
                for part in line.split():
                    if part.startswith("sha256:"):
                        return part
        return ""

    def _get_image_size(self, tag: str) -> float:
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", tag, "--format", "{{.Size}}"],
                capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return int(result.stdout.strip()) / (1024 * 1024)
        except Exception:
            pass
        return 0.0

    def build_batch(self, targets: list[BuildTarget],
                     push: bool = False) -> list[BuildResult]:
        """Build multiple targets sequentially with shared cache."""
        results = []
        for target in targets:
            results.append(self.build(target, push))
        total = sum(r.duration_seconds for r in results)
        passed = sum(1 for r in results if r.success)
        logger.info("Batch complete: %d/%d passed in %.1fs",
            passed, len(results), total)
        return results


def generate_cache_aware_dockerfile(app_name: str, python_version: str = "3.12") -> str:
    """Generate a Dockerfile optimized for BuildKit mount caches."""
    return f'''# syntax=docker/dockerfile:1.7
FROM python:{python_version}-slim AS builder

# Mount cache for apt
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \\
    --mount=type=cache,target=/var/lib/apt,sharing=locked \\
    apt-get update && apt-get install -y --no-install-recommends gcc

WORKDIR /build
COPY requirements.txt .

# Mount cache for pip -- survives across builds
RUN --mount=type=cache,target=/root/.cache/pip \\
    pip install --prefix=/install -r requirements.txt

FROM gcr.io/distroless/python3-debian12
COPY --from=builder /install /usr/local
COPY src/ /app/
WORKDIR /app
USER 65534
ENTRYPOINT ["python", "-m", "{app_name}"]
'''
```

## Key Patterns

- **Mount caches**: `--mount=type=cache` persists pip/apt caches across builds, avoiding re-downloads
- **Registry-backed cache**: Share build cache across CI runners via container registry
- **Max mode caching**: `mode=max` caches all layers, not just final image layers
- **Zstd compression**: Registry caches use zstd for smaller cache blobs and faster transfers
- **Parallel stages**: BuildKit automatically parallelizes independent build stages
- **Secret mounts**: Build-time secrets mounted without embedding in image layers'''
    ),
    (
        "containers/init-containers-sidecar-patterns",
        "How do I use init containers and sidecar patterns effectively in Kubernetes? Show patterns for database migrations, config loading, secret injection, and health-checking sidecars with a Python operator.",
        '''Init containers run before main containers and are used for setup tasks like database migrations, configuration loading, and dependency verification. Sidecars run alongside the main container for cross-cutting concerns.

## Container Patterns

| Pattern | Type | Use Case |
|---|---|---|
| DB migration | Init container | Run schema migrations before app starts |
| Config loader | Init container | Fetch config from Vault/ConfigMap |
| Wait-for-dependency | Init container | Block until DB/queue is ready |
| Log shipper | Sidecar | Forward logs to central system |
| Proxy sidecar | Sidecar | mTLS, service mesh proxy |
| Health checker | Sidecar | Complex health validation |

## Container Pattern Operator

```python
#!/usr/bin/env python3
"""
Kubernetes container pattern operator.
Generates init containers and sidecars for common patterns
like DB migrations, secret injection, and health checking.
"""

import json
import logging
import subprocess
import yaml
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class InitContainerConfig:
    """Configuration for an init container."""
    name: str
    image: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)
    env_from: list[dict] = field(default_factory=list)
    volume_mounts: list[dict] = field(default_factory=list)
    resources: Optional[dict] = None
    timeout_seconds: int = 120


@dataclass
class SidecarConfig:
    """Configuration for a sidecar container."""
    name: str
    image: str
    command: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    ports: list[dict] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    volume_mounts: list[dict] = field(default_factory=list)
    resources: Optional[dict] = None
    liveness_probe: Optional[dict] = None
    readiness_probe: Optional[dict] = None
    restart_policy: str = "Always"


class ContainerPatternGenerator:
    """Generates common init container and sidecar patterns."""

    @staticmethod
    def db_migration(image: str, db_secret: str, migration_dir: str = "/migrations") -> InitContainerConfig:
        return InitContainerConfig(
            name="db-migrate",
            image=image,
            command=["python", "-m", "alembic", "upgrade", "head"],
            env={"ALEMBIC_CONFIG": "/app/alembic.ini"},
            env_from=[{"secretRef": {"name": db_secret}}],
            volume_mounts=[{"name": "migrations", "mountPath": migration_dir, "readOnly": True}],
            timeout_seconds=300,
        )

    @staticmethod
    def wait_for_service(service: str, port: int, timeout: int = 60) -> InitContainerConfig:
        return InitContainerConfig(
            name=f"wait-for-{service}",
            image="busybox:1.36",
            command=["sh", "-c",
                f"until nc -z {service} {port}; do echo 'waiting for {service}:{port}'; sleep 2; done"],
            timeout_seconds=timeout,
        )

    @staticmethod
    def vault_secret_injector(vault_addr: str, role: str,
                               secret_path: str) -> InitContainerConfig:
        return InitContainerConfig(
            name="vault-secrets",
            image="hashicorp/vault:1.15",
            command=["sh", "-c", """
vault login -method=kubernetes role=$VAULT_ROLE &&
vault kv get -format=json $SECRET_PATH | jq -r '.data.data | to_entries[] | "\\(.key)=\\(.value)"' > /secrets/.env
""".strip()],
            env={
                "VAULT_ADDR": vault_addr,
                "VAULT_ROLE": role,
                "SECRET_PATH": secret_path,
            },
            volume_mounts=[{"name": "secrets", "mountPath": "/secrets"}],
        )

    @staticmethod
    def log_shipper_sidecar(log_path: str = "/var/log/app") -> SidecarConfig:
        return SidecarConfig(
            name="log-shipper",
            image="fluent/fluent-bit:3.0",
            args=["--config=/etc/fluent-bit/fluent-bit.conf"],
            volume_mounts=[
                {"name": "app-logs", "mountPath": log_path, "readOnly": True},
                {"name": "fluentbit-config", "mountPath": "/etc/fluent-bit", "readOnly": True},
            ],
            resources={"requests": {"cpu": "50m", "memory": "64Mi"},
                       "limits": {"cpu": "100m", "memory": "128Mi"}},
        )

    @staticmethod
    def health_checker_sidecar(main_port: int, check_path: str = "/health") -> SidecarConfig:
        return SidecarConfig(
            name="health-checker",
            image="curlimages/curl:8.5.0",
            command=["sh", "-c", f"""
while true; do
    status=$(curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{main_port}{check_path})
    if [ "$status" != "200" ]; then
        echo "Health check failed: $status" >> /health/status
        echo "unhealthy" > /health/ready
    else
        echo "healthy" > /health/ready
    fi
    sleep 10
done
""".strip()],
            volume_mounts=[{"name": "health-status", "mountPath": "/health"}],
            resources={"requests": {"cpu": "10m", "memory": "16Mi"},
                       "limits": {"cpu": "50m", "memory": "32Mi"}},
        )


class DeploymentEnhancer:
    """Enhances Kubernetes deployments with init containers and sidecars."""

    def __init__(self):
        self.generator = ContainerPatternGenerator()

    def enhance(self, deployment: dict,
                init_configs: list[InitContainerConfig] = None,
                sidecar_configs: list[SidecarConfig] = None) -> dict:
        """Add init containers and sidecars to a deployment."""
        spec = deployment["spec"]["template"]["spec"]

        if init_configs:
            init_containers = spec.setdefault("initContainers", [])
            for ic in init_configs:
                container = {
                    "name": ic.name, "image": ic.image, "command": ic.command,
                }
                if ic.env:
                    container["env"] = [{"name": k, "value": v} for k, v in ic.env.items()]
                if ic.env_from:
                    container["envFrom"] = ic.env_from
                if ic.volume_mounts:
                    container["volumeMounts"] = ic.volume_mounts
                if ic.resources:
                    container["resources"] = ic.resources
                container["terminationMessagePolicy"] = "FallbackToLogsOnError"
                init_containers.append(container)

        if sidecar_configs:
            containers = spec.setdefault("containers", [])
            for sc in sidecar_configs:
                container = {"name": sc.name, "image": sc.image}
                if sc.command:
                    container["command"] = sc.command
                if sc.args:
                    container["args"] = sc.args
                if sc.ports:
                    container["ports"] = sc.ports
                if sc.env:
                    container["env"] = [{"name": k, "value": v} for k, v in sc.env.items()]
                if sc.volume_mounts:
                    container["volumeMounts"] = sc.volume_mounts
                if sc.resources:
                    container["resources"] = sc.resources
                if sc.liveness_probe:
                    container["livenessProbe"] = sc.liveness_probe
                if sc.readiness_probe:
                    container["readinessProbe"] = sc.readiness_probe
                containers.append(container)

        return deployment

    def apply(self, deployment: dict, dry_run: bool = True) -> bool:
        yaml_str = yaml.dump(deployment, default_flow_style=False)
        cmd = ["kubectl", "apply", "-f", "-"]
        if dry_run:
            cmd.append("--dry-run=server")
        r = subprocess.run(cmd, input=yaml_str, capture_output=True, text=True)
        return r.returncode == 0
```

## Key Patterns

- **Ordered initialization**: Init containers run sequentially, ensuring DB is ready before migrations run
- **Shared volumes**: Init containers write to volumes that main containers read (secrets, config)
- **Resource isolation**: Sidecars have separate resource limits so they cannot starve the main app
- **Graceful shutdown**: Sidecar restart policy ensures log shippers survive main container restarts
- **Health aggregation**: Health checker sidecar performs complex validation the main app cannot
- **Secret injection**: Vault init container fetches secrets at pod startup, not baked into images'''
    ),
]
