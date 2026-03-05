"""
Batch P12 — DevSecOps: SAST/DAST integration, container security, secret management,
supply chain security, and runtime application security.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. SAST and DAST Integration ---
    (
        "devsecops/sast-dast-integration",
        r"""Explain how to integrate static application security testing with Semgrep custom rules and dynamic testing with OWASP ZAP into a CI/CD pipeline, including triage workflows and false-positive management strategies.""",
        r"""# SAST and DAST Integration in CI/CD Pipelines

## Why Shift-Left Security Requires Both SAST and DAST

Security testing is most effective when it operates at **multiple layers**. Static Application Security Testing (SAST) analyzes source code without executing it, catching vulnerabilities like SQL injection patterns, hardcoded credentials, and insecure deserialization early in the development cycle. Dynamic Application Security Testing (DAST), however, tests the running application from the outside, discovering issues that only manifest at runtime such as authentication bypasses, CORS misconfigurations, and server-side request forgery. Because each approach has blind spots the other covers, combining them is a **best practice** that dramatically reduces the chance of vulnerabilities reaching production.

A common mistake is treating security scans as a gate-only mechanism. Therefore, the most effective strategy integrates findings into developer workflows with proper triage, deduplication, and false-positive suppression. The trade-off is between scan thoroughness and pipeline speed -- you want comprehensive coverage without blocking every pull request for twenty minutes.

## SAST with Semgrep: Custom Rules and CI Integration

Semgrep is a lightweight, open-source static analysis tool that supports custom rules written in YAML. Unlike traditional SAST tools that rely on complex AST transformations, Semgrep uses a pattern-matching approach that developers can understand and extend.

### Writing Custom Semgrep Rules

```yaml
# .semgrep/custom-rules/sql-injection.yaml
# Custom Semgrep rules for detecting SQL injection patterns
rules:
  - id: python-sql-injection-format-string
    patterns:
      - pattern: |
          $CURSOR.execute(f"...{$VAR}...")
      - pattern-not-inside: |
          $VAR = sanitize(...)
    message: >
      SQL injection via f-string interpolation in execute().
      Use parameterized queries instead: cursor.execute("SELECT ... WHERE id = %s", (var,))
    languages: [python]
    severity: ERROR
    metadata:
      cwe: ["CWE-89"]
      owasp: ["A03:2021"]
      confidence: HIGH
      impact: HIGH

  - id: python-sql-injection-concatenation
    patterns:
      - pattern: |
          $CURSOR.execute("..." + $VAR + "...")
    message: >
      SQL injection via string concatenation. Use parameterized queries.
    languages: [python]
    severity: ERROR
    metadata:
      cwe: ["CWE-89"]
      confidence: HIGH

  - id: python-yaml-unsafe-load
    pattern: yaml.load($DATA)
    fix: yaml.safe_load($DATA)
    message: >
      yaml.load() without Loader argument allows arbitrary code execution.
      Use yaml.safe_load() instead.
    languages: [python]
    severity: WARNING
    metadata:
      cwe: ["CWE-502"]
```

### Semgrep Triage and Suppression Manager

```python
import json
import hashlib
import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import logging

logger = logging.getLogger(__name__)


@dataclass
class SastFinding:
    # Represents a single SAST finding from Semgrep
    rule_id: str
    file_path: str
    line_start: int
    line_end: int
    severity: str
    message: str
    cwe: List[str] = field(default_factory=list)
    fingerprint: str = ""

    def compute_fingerprint(self) -> str:
        # Stable fingerprint based on rule + location context
        content = f"{self.rule_id}:{self.file_path}:{self.line_start}"
        self.fingerprint = hashlib.sha256(content.encode()).hexdigest()[:16]
        return self.fingerprint


class SastTriageManager:
    # Manages triage state for SAST findings across pipeline runs
    def __init__(self, db_path: str = ".semgrep/triage.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self) -> None:
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS triage_decisions ("
            "  fingerprint TEXT PRIMARY KEY,"
            "  rule_id TEXT NOT NULL,"
            "  status TEXT NOT NULL DEFAULT 'open',"
            "  reason TEXT,"
            "  reviewer TEXT,"
            "  created_at TEXT NOT NULL,"
            "  updated_at TEXT NOT NULL"
            ")"
        )
        self.conn.commit()

    def is_suppressed(self, finding: SastFinding) -> bool:
        # Check if a finding has been triaged as false positive
        cursor = self.conn.execute(
            "SELECT status FROM triage_decisions WHERE fingerprint = ?",
            (finding.fingerprint,)
        )
        row = cursor.fetchone()
        return row is not None and row[0] in ("false_positive", "accepted_risk")

    def suppress_finding(
        self,
        finding: SastFinding,
        status: str,
        reason: str,
        reviewer: str
    ) -> None:
        # Record a triage decision for a finding
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT OR REPLACE INTO triage_decisions"
            " (fingerprint, rule_id, status, reason, reviewer, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (finding.fingerprint, finding.rule_id, status, reason, reviewer, now, now)
        )
        self.conn.commit()
        logger.info(f"Triaged {finding.fingerprint} as {status}: {reason}")

    def filter_findings(
        self, findings: List[SastFinding]
    ) -> Tuple[List[SastFinding], List[SastFinding]]:
        # Separate actionable findings from suppressed ones
        actionable: List[SastFinding] = []
        suppressed: List[SastFinding] = []
        for f in findings:
            f.compute_fingerprint()
            if self.is_suppressed(f):
                suppressed.append(f)
            else:
                actionable.append(f)
        logger.info(
            f"Filtered {len(findings)} findings: "
            f"{len(actionable)} actionable, {len(suppressed)} suppressed"
        )
        return actionable, suppressed


def run_semgrep_scan(
    target_dir: str,
    config_paths: List[str],
    output_format: str = "json"
) -> List[SastFinding]:
    # Execute Semgrep scan and parse results into structured findings
    cmd = [
        "semgrep", "scan",
        "--config", ",".join(config_paths),
        "--json",
        "--no-git-ignore",
        target_dir
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Semgrep failed: {result.stderr}")

    data = json.loads(result.stdout)
    findings: List[SastFinding] = []
    for r in data.get("results", []):
        finding = SastFinding(
            rule_id=r["check_id"],
            file_path=r["path"],
            line_start=r["start"]["line"],
            line_end=r["end"]["line"],
            severity=r["extra"].get("severity", "INFO"),
            message=r["extra"].get("message", ""),
            cwe=r["extra"].get("metadata", {}).get("cwe", [])
        )
        findings.append(finding)
    return findings
```

## DAST with OWASP ZAP: Automated Dynamic Scanning

OWASP ZAP provides a powerful API for automated dynamic scanning. The **pitfall** many teams fall into is running full active scans on every PR, which takes far too long. A better approach uses baseline (passive) scans for PRs and full active scans on a nightly schedule.

```python
import requests
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ZapScanType(Enum):
    BASELINE = "baseline"   # Passive only -- fast, safe for PRs
    FULL = "full"           # Active + passive -- thorough, nightly
    API = "api"             # OpenAPI/GraphQL targeted scan


@dataclass
class ZapConfig:
    # Configuration for OWASP ZAP scan execution
    zap_base_url: str = "http://localhost:8080"
    api_key: str = ""
    target_url: str = ""
    scan_type: ZapScanType = ZapScanType.BASELINE
    max_duration_minutes: int = 30
    ajax_spider: bool = False
    openapi_spec_url: Optional[str] = None


@dataclass
class DastAlert:
    # A single DAST finding from ZAP
    alert_id: int
    name: str
    risk: str
    confidence: str
    url: str
    description: str
    solution: str
    cwe_id: int
    wasc_id: int


class ZapScanner:
    # Wrapper around OWASP ZAP API for automated DAST scanning
    def __init__(self, config: ZapConfig):
        self.config = config
        self.session = requests.Session()
        self.session.params = {"apikey": config.api_key}

    def _api_get(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        url = f"{self.config.zap_base_url}{endpoint}"
        resp = self.session.get(url, params=params or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def start_spider(self) -> int:
        # Spider the target to discover endpoints
        result = self._api_get("/JSON/spider/action/scan/", {
            "url": self.config.target_url,
            "maxChildren": "10",
            "recurse": "true"
        })
        scan_id = int(result["scan"])
        logger.info(f"Started spider scan {scan_id} against {self.config.target_url}")
        return scan_id

    def wait_for_spider(self, scan_id: int) -> None:
        # Poll spider progress until completion
        while True:
            status = self._api_get("/JSON/spider/view/status/", {"scanId": str(scan_id)})
            progress = int(status["status"])
            if progress >= 100:
                break
            logger.info(f"Spider progress: {progress}%")
            time.sleep(5)

    def start_active_scan(self) -> int:
        # Launch active scan -- only for full scan type
        result = self._api_get("/JSON/ascan/action/scan/", {
            "url": self.config.target_url,
            "recurse": "true",
            "scanPolicyName": "Default Policy"
        })
        return int(result["scan"])

    def wait_for_active_scan(self, scan_id: int) -> None:
        start = time.time()
        timeout = self.config.max_duration_minutes * 60
        while True:
            if time.time() - start > timeout:
                logger.warning("Active scan timeout -- stopping")
                self._api_get("/JSON/ascan/action/stop/", {"scanId": str(scan_id)})
                break
            status = self._api_get("/JSON/ascan/view/status/", {"scanId": str(scan_id)})
            if int(status["status"]) >= 100:
                break
            time.sleep(10)

    def get_alerts(self, min_risk: str = "Low") -> List[DastAlert]:
        # Retrieve all alerts above minimum risk threshold
        risk_levels = {"Informational": 0, "Low": 1, "Medium": 2, "High": 3}
        min_level = risk_levels.get(min_risk, 1)
        data = self._api_get("/JSON/alert/view/alerts/", {
            "baseurl": self.config.target_url,
            "start": "0",
            "count": "500"
        })
        alerts: List[DastAlert] = []
        for a in data.get("alerts", []):
            if risk_levels.get(a["risk"], 0) >= min_level:
                alerts.append(DastAlert(
                    alert_id=int(a["id"]),
                    name=a["name"],
                    risk=a["risk"],
                    confidence=a["confidence"],
                    url=a["url"],
                    description=a["description"],
                    solution=a["solution"],
                    cwe_id=int(a.get("cweid", 0)),
                    wasc_id=int(a.get("wascid", 0))
                ))
        return alerts

    def run_scan(self) -> List[DastAlert]:
        # Orchestrate the complete scan workflow
        spider_id = self.start_spider()
        self.wait_for_spider(spider_id)
        if self.config.scan_type == ZapScanType.FULL:
            active_id = self.start_active_scan()
            self.wait_for_active_scan(active_id)
        return self.get_alerts()
```

## CI Pipeline Integration Strategy

The key trade-off in pipeline integration is **speed versus thoroughness**. Best practice is a tiered approach:

- **PR checks**: Semgrep (incremental, diff-only) + ZAP baseline scan -- completes in 2-5 minutes
- **Merge to main**: Full Semgrep scan + ZAP API scan -- completes in 10-15 minutes
- **Nightly**: Full Semgrep + ZAP active scan + dependency audit -- 30-60 minutes

### Triage Workflow Best Practices

1. **Centralize findings** in a security dashboard (DefectDojo, OWASP Dependency-Track)
2. **Deduplicate** across SAST and DAST -- a SQL injection found by both should be one ticket
3. **Auto-close** findings that no longer appear in subsequent scans
4. **SLA by severity**: Critical = 24h, High = 7 days, Medium = 30 days, Low = next sprint

## Summary and Key Takeaways

- **SAST catches code-level patterns** before runtime; Semgrep's custom rules let teams encode institutional knowledge about dangerous patterns specific to their codebase.
- **DAST validates runtime behavior** and catches issues SAST cannot see, such as misconfigured headers, broken authentication flows, and server misconfigurations.
- **Triage management is essential** because raw scan output generates too many false positives; therefore a suppression database with audit trails prevents alert fatigue.
- **Tiered scanning** balances the trade-off between developer velocity and security coverage -- use fast passive scans on PRs and thorough active scans on schedules.
- **A common pitfall** is treating security scans as purely blocking gates; however, the best teams treat findings as prioritized work items with clear SLAs and ownership.
""",
    ),

    # --- 2. Container Security Scanning ---
    (
        "devsecops/container-security-scanning",
        r"""Describe comprehensive container security scanning strategies using Trivy and Grype for vulnerability detection, best practices for base image selection and distroless containers, and runtime security monitoring with Falco rules.""",
        r"""# Container Security Scanning: From Build to Runtime

## The Container Security Landscape

Containers introduce a unique security challenge because they bundle application code with an operating system layer, libraries, and configuration -- all of which can contain vulnerabilities. A **common mistake** is scanning only at build time and assuming containers remain secure throughout their lifecycle. However, new CVEs are published daily, and a container that was clean last week may have critical vulnerabilities today. Therefore, a comprehensive strategy must cover the entire lifecycle: **build, registry, deploy, and runtime**.

## Vulnerability Scanning with Trivy and Grype

Trivy and Grype are the two leading open-source container vulnerability scanners. The trade-off between them is that Trivy provides broader coverage (OS packages, language dependencies, IaC misconfigurations, secrets) while Grype focuses specifically on vulnerability matching with excellent SBOM integration via Syft.

### Multi-Scanner Pipeline Implementation

```python
import subprocess
import json
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from enum import Enum
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class Severity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NEGLIGIBLE = "NEGLIGIBLE"


@dataclass
class Vulnerability:
    # A single vulnerability finding from any scanner
    vuln_id: str          # CVE-2024-XXXXX
    package_name: str
    installed_version: str
    fixed_version: Optional[str]
    severity: Severity
    scanner: str          # trivy or grype
    title: str = ""
    description: str = ""
    data_source: str = ""

    @property
    def is_fixable(self) -> bool:
        return self.fixed_version is not None and self.fixed_version != ""


@dataclass
class ScanResult:
    # Aggregated results from one or more scanners
    image: str
    vulnerabilities: List[Vulnerability] = field(default_factory=list)
    scanners_used: List[str] = field(default_factory=list)

    def by_severity(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for v in self.vulnerabilities:
            counts[v.severity.value] = counts.get(v.severity.value, 0) + 1
        return counts

    def fixable_criticals(self) -> List[Vulnerability]:
        return [
            v for v in self.vulnerabilities
            if v.severity == Severity.CRITICAL and v.is_fixable
        ]

    def deduplicated(self) -> List[Vulnerability]:
        # Merge findings from multiple scanners by CVE ID
        seen: Dict[str, Vulnerability] = {}
        for v in self.vulnerabilities:
            key = f"{v.vuln_id}:{v.package_name}"
            if key not in seen:
                seen[key] = v
        return list(seen.values())


class TrivyScanner:
    # Wrapper for Trivy container vulnerability scanner
    def __init__(self, severity_filter: str = "CRITICAL,HIGH"):
        self.severity_filter = severity_filter

    def scan_image(self, image_ref: str) -> List[Vulnerability]:
        cmd = [
            "trivy", "image",
            "--format", "json",
            "--severity", self.severity_filter,
            "--ignore-unfixed",
            image_ref
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode not in (0, 1):
            raise RuntimeError(f"Trivy scan failed: {result.stderr[:500]}")

        data = json.loads(result.stdout)
        vulns: List[Vulnerability] = []
        for target in data.get("Results", []):
            for v in target.get("Vulnerabilities", []):
                vulns.append(Vulnerability(
                    vuln_id=v["VulnerabilityID"],
                    package_name=v["PkgName"],
                    installed_version=v["InstalledVersion"],
                    fixed_version=v.get("FixedVersion"),
                    severity=Severity(v["Severity"]),
                    scanner="trivy",
                    title=v.get("Title", ""),
                    description=v.get("Description", "")[:200]
                ))
        logger.info(f"Trivy found {len(vulns)} vulnerabilities in {image_ref}")
        return vulns

    def scan_filesystem(self, path: str) -> List[Vulnerability]:
        # Scan a filesystem path for language-specific dependencies
        cmd = [
            "trivy", "fs",
            "--format", "json",
            "--severity", self.severity_filter,
            path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        data = json.loads(result.stdout)
        vulns: List[Vulnerability] = []
        for target in data.get("Results", []):
            for v in target.get("Vulnerabilities", []):
                vulns.append(Vulnerability(
                    vuln_id=v["VulnerabilityID"],
                    package_name=v["PkgName"],
                    installed_version=v["InstalledVersion"],
                    fixed_version=v.get("FixedVersion"),
                    severity=Severity(v["Severity"]),
                    scanner="trivy-fs",
                    title=v.get("Title", "")
                ))
        return vulns


class GrypeScanner:
    # Wrapper for Grype vulnerability scanner with SBOM support
    def scan_image(self, image_ref: str) -> List[Vulnerability]:
        cmd = ["grype", image_ref, "-o", "json", "--only-fixed"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        data = json.loads(result.stdout)
        vulns: List[Vulnerability] = []
        for match in data.get("matches", []):
            vuln_data = match["vulnerability"]
            artifact = match["artifact"]
            vulns.append(Vulnerability(
                vuln_id=vuln_data["id"],
                package_name=artifact["name"],
                installed_version=artifact["version"],
                fixed_version=vuln_data.get("fix", {}).get("versions", [None])[0],
                severity=Severity(vuln_data["severity"].upper()),
                scanner="grype",
                data_source=vuln_data.get("dataSource", "")
            ))
        logger.info(f"Grype found {len(vulns)} vulnerabilities in {image_ref}")
        return vulns


def run_multi_scanner_pipeline(
    image_ref: str,
    fail_on_critical: bool = True
) -> ScanResult:
    # Run both scanners and merge results for comprehensive coverage
    scan_result = ScanResult(image=image_ref)

    trivy = TrivyScanner()
    grype = GrypeScanner()

    trivy_vulns = trivy.scan_image(image_ref)
    scan_result.vulnerabilities.extend(trivy_vulns)
    scan_result.scanners_used.append("trivy")

    grype_vulns = grype.scan_image(image_ref)
    scan_result.vulnerabilities.extend(grype_vulns)
    scan_result.scanners_used.append("grype")

    deduped = scan_result.deduplicated()
    logger.info(
        f"Combined scan: {len(scan_result.vulnerabilities)} raw, "
        f"{len(deduped)} unique vulnerabilities"
    )

    if fail_on_critical and scan_result.fixable_criticals():
        crits = scan_result.fixable_criticals()
        logger.error(f"BLOCKING: {len(crits)} fixable critical vulnerabilities found")
        for c in crits:
            logger.error(f"  {c.vuln_id} in {c.package_name} -- fix: {c.fixed_version}")

    return scan_result
```

## Base Image Selection and Distroless Containers

Choosing the right base image is the **single most impactful decision** for container security. The best practice hierarchy from most secure to least:

1. **Distroless** (gcr.io/distroless) -- no shell, no package manager, minimal attack surface
2. **Alpine-based** -- small footprint (~5MB), musl libc, apk for builds only
3. **Slim variants** (python:3.12-slim) -- reduced Debian, still has apt
4. **Full OS images** (ubuntu:24.04) -- largest attack surface, most CVEs

### Distroless Multi-Stage Build Pattern

```dockerfile
# Stage 1: Build with full toolchain
FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir poetry
COPY pyproject.toml poetry.lock ./
RUN poetry export -f requirements.txt --output requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
COPY src/ ./src/

# Stage 2: Runtime with distroless -- no shell, no pkg manager
FROM gcr.io/distroless/python3-debian12:nonroot
WORKDIR /app
COPY --from=builder /install /usr/local
COPY --from=builder /app/src ./src
USER nonroot:nonroot
EXPOSE 8080
ENTRYPOINT ["python", "-m", "src.main"]
```

## Runtime Security with Falco

Falco monitors system calls in real-time, detecting anomalous container behavior. This catches threats that static scanning cannot: compromised containers, lateral movement, and privilege escalation attempts.

```yaml
# falco-custom-rules.yaml
# Runtime detection rules for container security
- rule: Shell Spawned in Container
  desc: >
    Detect shell processes spawned inside containers.
    Because distroless containers have no shell,
    any shell activity indicates compromise.
  condition: >
    spawned_process and container and
    (proc.name in (bash, sh, zsh, dash, csh, ksh)) and
    not proc.pname in (cron, supervisord)
  output: >
    Shell spawned in container
    (user=%user.name container=%container.name
     shell=%proc.name parent=%proc.pname
     cmdline=%proc.cmdline image=%container.image.repository)
  priority: WARNING
  tags: [container, shell, mitre_execution]

- rule: Sensitive File Read in Container
  desc: Detect reads of sensitive files like /etc/shadow or private keys
  condition: >
    open_read and container and
    (fd.name startswith /etc/shadow or
     fd.name startswith /root/.ssh or
     fd.name contains id_rsa)
  output: >
    Sensitive file read (file=%fd.name user=%user.name
     container=%container.name image=%container.image.repository)
  priority: ERROR
  tags: [container, filesystem, mitre_credential_access]

- rule: Outbound Connection to Unusual Port
  desc: >
    Containers should only connect to well-known ports.
    Connections to unusual ports may indicate C2 communication.
  condition: >
    outbound and container and
    not fd.sport in (53, 80, 443, 8080, 8443, 5432, 3306, 6379) and
    not k8s.ns.name = "kube-system"
  output: >
    Unexpected outbound connection (port=%fd.sport ip=%fd.sip
     container=%container.name command=%proc.cmdline)
  priority: NOTICE
  tags: [container, network, mitre_command_and_control]
```

## Registry Scanning and Admission Control

A mature container security program does not stop at build-time scanning. **Best practice** demands continuous registry scanning -- rescanning all stored images against updated vulnerability databases on a daily cadence. When a new critical CVE is published, images that were clean yesterday may suddenly be affected. Therefore, organizations should integrate registry scanning with Kubernetes admission controllers (such as Kyverno or OPA Gatekeeper) that **block deployment of images** with unresolved critical vulnerabilities. This creates a policy enforcement point that prevents vulnerable containers from ever reaching production, regardless of when the vulnerability was discovered. The trade-off is that overly strict admission policies can block legitimate deployments during zero-day events, so teams should define exception workflows for emergency rollouts with time-boxed waivers.

## Summary and Key Takeaways

- **Multi-scanner approaches** using both Trivy and Grype catch more vulnerabilities because each tool has different data sources; therefore, deduplicating across scanners gives the most complete picture.
- **Distroless containers** are the **best practice** for production because they eliminate entire vulnerability classes -- no shell means no shell injection, no package manager means no post-exploitation package installation.
- **Runtime monitoring with Falco** is essential because static scanning cannot detect compromised containers or novel attack patterns; however, rules must be tuned to avoid alert fatigue.
- **The key pitfall** is scanning only at build time. Continuous scanning of running containers against updated CVE databases is critical because new vulnerabilities are disclosed daily.
- **Base image selection** is the highest-leverage security decision -- switching from ubuntu:24.04 to distroless can eliminate 90%+ of OS-level CVEs.
- **Admission controllers** provide the final enforcement gate, ensuring that policy violations caught by registry scanners actually prevent deployment rather than merely generating alerts.
""",
    ),

    # --- 3. Secret Management ---
    (
        "devsecops/secret-management-vault",
        r"""Explain HashiCorp Vault patterns for secret management in production environments, including dynamic secret generation, automated secret rotation, transit encryption engine usage, and Vault agent injection in Kubernetes pods.""",
        r"""# Secret Management with HashiCorp Vault: Production Patterns

## Why Static Secrets Are a Liability

The traditional approach of storing secrets in environment variables, config files, or even encrypted at-rest stores creates a fundamental problem: **static secrets have unlimited blast radius and indefinite validity**. When a database password is committed to a `.env` file, it remains valid until someone manually rotates it -- which, in practice, means it stays valid forever. A common mistake is believing that encryption at rest solves the problem; however, encryption only protects against one threat (disk theft) while leaving the secret vulnerable to process inspection, log leakage, and lateral movement.

HashiCorp Vault addresses this by introducing **dynamic secrets** (generated on demand with automatic TTL-based revocation), **leasing** (all secrets have an expiration), and **audit logging** (every secret access is recorded). The trade-off is operational complexity -- Vault requires careful deployment, unsealing, and high availability configuration -- but the security benefits are substantial.

## Vault Secret Engines and Dynamic Secrets

### Database Dynamic Secrets

```python
import hvac
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Tuple
from contextlib import contextmanager
from datetime import datetime, timezone
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class DynamicCredential:
    # A Vault-issued dynamic credential with lease management
    username: str
    password: str
    lease_id: str
    lease_duration: int   # seconds
    renewable: bool
    issued_at: float = field(default_factory=time.time)

    @property
    def expires_at(self) -> float:
        return self.issued_at + self.lease_duration

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    @property
    def ttl_remaining(self) -> int:
        return max(0, int(self.expires_at - time.time()))


class VaultSecretManager:
    # Production-grade Vault client with dynamic secret lifecycle management
    def __init__(
        self,
        vault_addr: str,
        auth_method: str = "kubernetes",
        role: str = "",
        namespace: str = "",
        mount_point: str = "database"
    ):
        self.client = hvac.Client(url=vault_addr, namespace=namespace)
        self.mount_point = mount_point
        self.role = role
        self._current_cred: Optional[DynamicCredential] = None
        self._renewal_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._authenticate(auth_method, role)

    def _authenticate(self, method: str, role: str) -> None:
        # Authenticate to Vault using the appropriate method
        if method == "kubernetes":
            # Read the SA token mounted by Kubernetes
            with open("/var/run/secrets/kubernetes.io/serviceaccount/token") as f:
                jwt = f.read()
            self.client.auth.kubernetes.login(role=role, jwt=jwt)
            logger.info(f"Authenticated to Vault via Kubernetes auth, role={role}")
        elif method == "approle":
            # AppRole for CI/CD and non-Kubernetes workloads
            role_id = self._read_file("/vault/role-id")
            secret_id = self._read_file("/vault/secret-id")
            self.client.auth.approle.login(
                role_id=role_id,
                secret_id=secret_id
            )
            logger.info("Authenticated to Vault via AppRole")
        else:
            raise ValueError(f"Unsupported auth method: {method}")

    def _read_file(self, path: str) -> str:
        with open(path) as f:
            return f.read().strip()

    def get_database_credentials(self, db_role: str) -> DynamicCredential:
        # Request dynamic database credentials from Vault
        # Vault generates a unique user/pass with automatic expiration
        response = self.client.secrets.database.generate_credentials(
            name=db_role,
            mount_point=self.mount_point
        )
        cred = DynamicCredential(
            username=response["data"]["username"],
            password=response["data"]["password"],
            lease_id=response["lease_id"],
            lease_duration=response["lease_duration"],
            renewable=response["renewable"]
        )
        logger.info(
            f"Obtained dynamic credentials for {db_role}: "
            f"user={cred.username}, ttl={cred.lease_duration}s"
        )
        self._current_cred = cred
        return cred

    def renew_lease(self, cred: DynamicCredential) -> DynamicCredential:
        # Renew a dynamic credential's lease before expiration
        if not cred.renewable:
            logger.warning("Credential is not renewable, requesting new one")
            return self.get_database_credentials(self.role)

        response = self.client.sys.renew_lease(
            lease_id=cred.lease_id,
            increment=cred.lease_duration
        )
        cred.lease_duration = response["lease_duration"]
        cred.issued_at = time.time()
        logger.info(f"Renewed lease {cred.lease_id}, new TTL={cred.lease_duration}s")
        return cred

    def revoke_lease(self, cred: DynamicCredential) -> None:
        # Explicitly revoke credentials when no longer needed
        self.client.sys.revoke_lease(cred.lease_id)
        logger.info(f"Revoked lease {cred.lease_id} for user {cred.username}")

    def start_renewal_loop(self, cred: DynamicCredential) -> None:
        # Background thread that renews credentials before expiration
        def _renew_loop() -> None:
            while not self._stop_event.is_set():
                # Renew at 2/3 of TTL -- best practice for safety margin
                sleep_time = max(cred.ttl_remaining * 2 // 3, 10)
                self._stop_event.wait(timeout=sleep_time)
                if self._stop_event.is_set():
                    break
                try:
                    self.renew_lease(cred)
                except Exception as e:
                    logger.error(f"Lease renewal failed: {e}")
                    # Attempt to get fresh credentials
                    try:
                        new_cred = self.get_database_credentials(self.role)
                        cred.username = new_cred.username
                        cred.password = new_cred.password
                        cred.lease_id = new_cred.lease_id
                    except Exception as inner:
                        logger.critical(f"Cannot obtain new credentials: {inner}")

        self._renewal_thread = threading.Thread(
            target=_renew_loop, daemon=True, name="vault-renewal"
        )
        self._renewal_thread.start()

    def stop_renewal(self) -> None:
        self._stop_event.set()
        if self._renewal_thread:
            self._renewal_thread.join(timeout=5)


@contextmanager
def managed_db_credentials(
    vault_addr: str,
    db_role: str,
    vault_role: str,
    auth_method: str = "kubernetes"
):
    # Context manager that handles the full credential lifecycle
    manager = VaultSecretManager(
        vault_addr=vault_addr,
        auth_method=auth_method,
        role=vault_role
    )
    cred = manager.get_database_credentials(db_role)
    manager.start_renewal_loop(cred)
    try:
        yield cred
    finally:
        manager.stop_renewal()
        manager.revoke_lease(cred)
        logger.info("Database credentials revoked on context exit")
```

## Transit Encryption Engine

Vault's Transit engine provides **encryption as a service** -- applications send plaintext to Vault and receive ciphertext, without ever handling encryption keys directly. This is a best practice because it separates the concerns of key management from application logic.

```python
import base64
from typing import List, Optional
import hvac


class TransitEncryptor:
    # Vault Transit engine wrapper for application-layer encryption
    def __init__(self, client: hvac.Client, key_name: str, mount_point: str = "transit"):
        self.client = client
        self.key_name = key_name
        self.mount_point = mount_point

    def encrypt(self, plaintext: str) -> str:
        # Encrypt data through Vault Transit -- key never leaves Vault
        encoded = base64.b64encode(plaintext.encode()).decode()
        result = self.client.secrets.transit.encrypt_data(
            name=self.key_name,
            plaintext=encoded,
            mount_point=self.mount_point
        )
        return result["data"]["ciphertext"]  # vault:v1:base64...

    def decrypt(self, ciphertext: str) -> str:
        # Decrypt Vault Transit ciphertext back to plaintext
        result = self.client.secrets.transit.decrypt_data(
            name=self.key_name,
            ciphertext=ciphertext,
            mount_point=self.mount_point
        )
        decoded = base64.b64decode(result["data"]["plaintext"]).decode()
        return decoded

    def encrypt_batch(self, items: List[str]) -> List[str]:
        # Batch encrypt for efficiency -- reduces round trips
        batch_input = [
            {"plaintext": base64.b64encode(item.encode()).decode()}
            for item in items
        ]
        result = self.client.secrets.transit.encrypt_data(
            name=self.key_name,
            batch_input=batch_input,
            mount_point=self.mount_point
        )
        return [r["ciphertext"] for r in result["data"]["batch_results"]]

    def rotate_key(self) -> None:
        # Rotate the encryption key -- old ciphertext still decryptable
        self.client.secrets.transit.rotate_key(
            name=self.key_name,
            mount_point=self.mount_point
        )

    def rewrap(self, ciphertext: str) -> str:
        # Re-encrypt with latest key version without exposing plaintext
        result = self.client.secrets.transit.rewrap_data(
            name=self.key_name,
            ciphertext=ciphertext,
            mount_point=self.mount_point
        )
        return result["data"]["ciphertext"]
```

## Vault Agent Injection in Kubernetes

Vault Agent Injector uses a mutating webhook to automatically inject secrets into Kubernetes pods via sidecar containers. This is the **best practice** for Kubernetes-native Vault integration because applications read secrets from a file path and require no Vault SDK dependency.

```yaml
# kubernetes/deployment-with-vault-injection.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api-server
  template:
    metadata:
      labels:
        app: api-server
      annotations:
        # Vault Agent Injector annotations
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "api-server"
        vault.hashicorp.com/agent-inject-secret-db-creds: "database/creds/api-server-role"
        vault.hashicorp.com/agent-inject-template-db-creds: |
          {{- with secret "database/creds/api-server-role" -}}
          DB_HOST=postgres.production.svc.cluster.local
          DB_PORT=5432
          DB_USERNAME={{ .Data.username }}
          DB_PASSWORD={{ .Data.password }}
          DB_NAME=api_production
          {{- end -}}
        vault.hashicorp.com/agent-inject-secret-api-key: "secret/data/api-server/api-key"
        vault.hashicorp.com/agent-revoke-on-shutdown: "true"
        vault.hashicorp.com/agent-pre-populate-only: "false"
    spec:
      serviceAccountName: api-server
      containers:
        - name: api-server
          image: gcr.io/myproject/api-server:v1.2.3
          ports:
            - containerPort: 8080
          env:
            - name: DB_CREDS_PATH
              value: /vault/secrets/db-creds
          volumeMounts:
            - name: vault-secrets
              mountPath: /vault/secrets
              readOnly: true
```

## Secret Rotation Strategy and Emergency Procedures

Automated secret rotation should be implemented at multiple levels. For database credentials, Vault's dynamic secret engine inherently handles rotation because each credential issuance creates a fresh username and password pair. For API keys and certificates, Vault's PKI engine can issue short-lived TLS certificates (e.g., 24-hour TTL) that eliminate the need for manual rotation entirely. The **best practice** is to set maximum TTLs on all secret mounts so that even if an application fails to renew, the credential is automatically invalidated by Vault. In emergency scenarios -- such as a suspected credential compromise -- teams should have runbooks that invoke Vault's lease revocation API to immediately invalidate all credentials issued by a specific engine or role. This capability is why Vault is fundamentally superior to static secret stores: it provides a **single control plane** for instant, organization-wide credential revocation.

## Summary and Key Takeaways

- **Dynamic secrets** eliminate the static secret problem because credentials are generated on demand with automatic expiration; therefore, a leaked credential has a limited blast radius.
- **Lease renewal** is critical for long-running services; the **pitfall** is not handling renewal failures gracefully, which causes credential expiration and service outages.
- **Transit encryption** separates key management from application logic, which is a **best practice** because developers never handle raw encryption keys and key rotation is transparent.
- **Vault Agent Injection** in Kubernetes is the preferred pattern because it requires zero application changes -- secrets appear as files, and the sidecar handles authentication and renewal automatically.
- **The common mistake** is treating Vault as a simple key-value store; however, its real power lies in dynamic secret engines, policy-based access control, and comprehensive audit logging.
- **Emergency revocation** is a critical capability that static secret stores lack entirely; Vault can invalidate every credential issued from a compromised path in seconds.
""",
    ),

    # --- 4. Supply Chain Security ---
    (
        "devsecops/supply-chain-security",
        r"""Explain software supply chain security practices including SBOM generation with CycloneDX, artifact signing with Sigstore and cosign, the SLSA framework for build provenance, dependency review automation, and provenance attestation verification.""",
        r"""# Software Supply Chain Security: SBOM, Sigstore, SLSA, and Provenance

## Why Supply Chain Security Matters Now

Software supply chain attacks have escalated dramatically. The SolarWinds compromise, Log4Shell, the Codecov breach, and the xz-utils backdoor demonstrated that attackers increasingly target the **build and distribution pipeline** rather than the application itself. Because modern applications depend on hundreds of transitive dependencies, a single compromised package can affect millions of downstream consumers. Therefore, supply chain security is no longer optional -- it is a **best practice** mandated by executive orders, regulatory frameworks, and industry standards.

The core challenge is establishing **trust** across four dimensions: What is in my software (SBOM)? Who built it (signing)? How was it built (provenance)? Are the dependencies safe (review)?

## SBOM Generation with CycloneDX

A Software Bill of Materials is a machine-readable inventory of every component in your software. CycloneDX is the OWASP standard that provides richer security metadata than SPDX for vulnerability management use cases.

### Automated SBOM Pipeline

```python
import json
import subprocess
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set
from pathlib import Path
from datetime import datetime, timezone
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ComponentType(Enum):
    LIBRARY = "library"
    FRAMEWORK = "framework"
    APPLICATION = "application"
    CONTAINER = "container"
    OPERATING_SYSTEM = "operating-system"


@dataclass
class SBOMComponent:
    # Represents a software component in CycloneDX format
    name: str
    version: str
    purl: str                                  # Package URL identifier
    component_type: ComponentType = ComponentType.LIBRARY
    licenses: List[str] = field(default_factory=list)
    hashes: Dict[str, str] = field(default_factory=dict)
    supplier: str = ""
    is_direct: bool = True
    scope: str = "required"                    # required, optional, excluded

    def to_cyclonedx(self) -> Dict[str, Any]:
        component: Dict[str, Any] = {
            "type": self.component_type.value,
            "name": self.name,
            "version": self.version,
            "purl": self.purl,
            "scope": self.scope,
        }
        if self.hashes:
            component["hashes"] = [
                {"alg": alg, "content": val}
                for alg, val in self.hashes.items()
            ]
        if self.licenses:
            component["licenses"] = [
                {"license": {"id": lic}} for lic in self.licenses
            ]
        return component


@dataclass
class SBOMDocument:
    # Full CycloneDX 1.5 SBOM document
    project_name: str
    project_version: str
    components: List[SBOMComponent] = field(default_factory=list)
    serial_number: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_cyclonedx_json(self) -> Dict[str, Any]:
        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "serialNumber": self.serial_number or f"urn:uuid:{hashlib.md5(self.project_name.encode()).hexdigest()}",
            "version": 1,
            "metadata": {
                "timestamp": self.created_at,
                "component": {
                    "type": "application",
                    "name": self.project_name,
                    "version": self.project_version,
                },
                "tools": [{"name": "sbom-generator", "version": "1.0.0"}]
            },
            "components": [c.to_cyclonedx() for c in self.components],
        }

    def save(self, output_path: str) -> None:
        with open(output_path, "w") as f:
            json.dump(self.to_cyclonedx_json(), f, indent=2)
        logger.info(f"SBOM saved to {output_path} with {len(self.components)} components")


class SBOMGenerator:
    # Multi-ecosystem SBOM generator using Syft and native tools
    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)

    def generate_with_syft(self, image_or_dir: str) -> SBOMDocument:
        # Use Syft for comprehensive SBOM generation
        cmd = [
            "syft", image_or_dir,
            "-o", "cyclonedx-json",
            "--name", self.project_dir.name
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"Syft SBOM generation failed: {result.stderr[:500]}")

        data = json.loads(result.stdout)
        doc = SBOMDocument(
            project_name=self.project_dir.name,
            project_version="0.0.0"
        )
        for comp in data.get("components", []):
            doc.components.append(SBOMComponent(
                name=comp["name"],
                version=comp.get("version", "unknown"),
                purl=comp.get("purl", ""),
                component_type=ComponentType(comp.get("type", "library")),
                licenses=[
                    lic.get("license", {}).get("id", "NOASSERTION")
                    for lic in comp.get("licenses", [])
                ]
            ))
        return doc

    def generate_from_lockfiles(self) -> SBOMDocument:
        # Parse lockfiles directly for language-specific accuracy
        doc = SBOMDocument(
            project_name=self.project_dir.name,
            project_version="0.0.0"
        )
        # Python: poetry.lock
        poetry_lock = self.project_dir / "poetry.lock"
        if poetry_lock.exists():
            doc.components.extend(self._parse_poetry_lock(poetry_lock))
        # Node: package-lock.json
        pkg_lock = self.project_dir / "package-lock.json"
        if pkg_lock.exists():
            doc.components.extend(self._parse_npm_lock(pkg_lock))
        return doc

    def _parse_poetry_lock(self, lock_path: Path) -> List[SBOMComponent]:
        # Best effort parsing of poetry.lock for Python dependencies
        components: List[SBOMComponent] = []
        try:
            import tomllib
            with open(lock_path, "rb") as f:
                data = tomllib.load(f)
            for pkg in data.get("package", []):
                components.append(SBOMComponent(
                    name=pkg["name"],
                    version=pkg["version"],
                    purl=f"pkg:pypi/{pkg['name']}@{pkg['version']}",
                    is_direct=(pkg.get("category", "main") == "main")
                ))
        except Exception as e:
            logger.warning(f"Failed to parse poetry.lock: {e}")
        return components

    def _parse_npm_lock(self, lock_path: Path) -> List[SBOMComponent]:
        components: List[SBOMComponent] = []
        with open(lock_path) as f:
            data = json.load(f)
        for name, info in data.get("packages", {}).items():
            if name == "":
                continue
            pkg_name = name.replace("node_modules/", "")
            components.append(SBOMComponent(
                name=pkg_name,
                version=info.get("version", "unknown"),
                purl=f"pkg:npm/{pkg_name}@{info.get('version', 'unknown')}",
                is_direct=not info.get("dev", False)
            ))
        return components
```

## Artifact Signing with Sigstore and Cosign

Sigstore provides **keyless signing** -- instead of managing long-lived signing keys (which are themselves a supply chain risk), Sigstore uses short-lived certificates tied to identity providers (GitHub Actions OIDC, Google, etc.). This is a significant improvement because it eliminates the key management burden while providing stronger identity guarantees.

### Signing and Verification Pipeline

```python
import subprocess
import json
from dataclasses import dataclass
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


@dataclass
class SignatureVerification:
    # Result of a cosign signature verification
    verified: bool
    signer_identity: str
    issuer: str
    transparency_log_index: Optional[int] = None
    certificate_expiry: str = ""
    error: str = ""


class CosignManager:
    # Wrapper for cosign container image signing and verification
    def sign_image_keyless(
        self,
        image_digest: str,
        fulcio_url: str = "https://fulcio.sigstore.dev",
        rekor_url: str = "https://rekor.sigstore.dev"
    ) -> bool:
        # Keyless signing -- uses OIDC identity from CI environment
        cmd = [
            "cosign", "sign",
            "--fulcio-url", fulcio_url,
            "--rekor-url", rekor_url,
            "--yes",
            image_digest
        ]
        env = {"COSIGN_EXPERIMENTAL": "1"}
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=120, env={**__import__("os").environ, **env}
        )
        if result.returncode == 0:
            logger.info(f"Successfully signed {image_digest}")
            return True
        logger.error(f"Signing failed: {result.stderr}")
        return False

    def verify_image(
        self,
        image_ref: str,
        expected_identity: str,
        expected_issuer: str = "https://token.actions.githubusercontent.com"
    ) -> SignatureVerification:
        # Verify image signature with identity constraints
        cmd = [
            "cosign", "verify",
            "--certificate-identity", expected_identity,
            "--certificate-oidc-issuer", expected_issuer,
            "--output", "json",
            image_ref
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return SignatureVerification(
                verified=False,
                signer_identity="",
                issuer="",
                error=result.stderr[:500]
            )

        data = json.loads(result.stdout)
        if data and len(data) > 0:
            cert_info = data[0].get("optional", {})
            return SignatureVerification(
                verified=True,
                signer_identity=cert_info.get("Subject", expected_identity),
                issuer=cert_info.get("Issuer", expected_issuer),
                transparency_log_index=cert_info.get("LogIndex")
            )
        return SignatureVerification(
            verified=False, signer_identity="", issuer="",
            error="No verification payloads returned"
        )

    def attach_sbom(self, image_digest: str, sbom_path: str) -> bool:
        # Attach SBOM as a cosign attestation to the image
        cmd = [
            "cosign", "attach", "sbom",
            "--sbom", sbom_path,
            "--type", "cyclonedx",
            image_digest
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            logger.info(f"Attached SBOM to {image_digest}")
            return True
        logger.error(f"SBOM attachment failed: {result.stderr}")
        return False

    def attest_provenance(
        self,
        image_digest: str,
        provenance_path: str,
        predicate_type: str = "slsaprovenance"
    ) -> bool:
        # Create SLSA provenance attestation for build provenance
        cmd = [
            "cosign", "attest",
            "--predicate", provenance_path,
            "--type", predicate_type,
            "--yes",
            image_digest
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.returncode == 0
```

## SLSA Framework and Build Provenance

The SLSA (Supply-chain Levels for Software Artifacts) framework defines four levels of increasing supply chain integrity. Each level adds protections against different attack vectors:

- **SLSA Level 1**: Provenance exists (build process is documented)
- **SLSA Level 2**: Hosted build service (builds run on a managed platform, not a developer laptop)
- **SLSA Level 3**: Hardened builds (build environment is ephemeral and tamper-resistant)
- **SLSA Level 4**: Two-person review + hermetic builds (highest assurance)

### Provenance Attestation Structure

```json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {
      "name": "ghcr.io/myorg/api-server",
      "digest": {"sha256": "abc123def456..."}
    }
  ],
  "predicateType": "https://slsa.dev/provenance/v1",
  "predicate": {
    "buildDefinition": {
      "buildType": "https://github.com/slsa-framework/slsa-github-generator",
      "externalParameters": {
        "source": {
          "uri": "git+https://github.com/myorg/api-server@refs/heads/main",
          "digest": {"sha1": "abc123..."}
        }
      },
      "resolvedDependencies": [
        {
          "uri": "pkg:pypi/fastapi@0.109.0",
          "digest": {"sha256": "..."}
        }
      ]
    },
    "runDetails": {
      "builder": {
        "id": "https://github.com/slsa-framework/slsa-github-generator/.github/workflows/generator_container_slsa3.yml@refs/tags/v1.9.0"
      },
      "metadata": {
        "invocationId": "https://github.com/myorg/api-server/actions/runs/12345",
        "startedOn": "2025-01-15T10:30:00Z",
        "finishedOn": "2025-01-15T10:35:00Z"
      }
    }
  }
}
```

## Dependency Review Automation

Automated dependency review prevents malicious or vulnerable packages from entering the codebase. The **pitfall** is reviewing only direct dependencies while ignoring transitive ones, which account for 80%+ of the dependency tree.

## Summary and Key Takeaways

- **SBOMs are the foundation** of supply chain security because you cannot protect what you cannot see; therefore, generating CycloneDX SBOMs in CI and attaching them to artifacts should be the first step in any supply chain security program.
- **Keyless signing with Sigstore** eliminates the trade-off between signing security and key management complexity; however, you must verify signatures with identity constraints (expected signer + issuer) to prevent unauthorized signers.
- **SLSA provenance** establishes a verifiable chain from source code to artifact. The **best practice** is to use SLSA Level 3 generators provided by GitHub or Google, which run in hardened, ephemeral build environments.
- **A common mistake** is treating dependency review as a one-time gate rather than continuous monitoring. New CVEs against existing dependencies require ongoing scanning of SBOMs against vulnerability databases.
- **The key trade-off** in supply chain security is between strictness and developer velocity. Start with SBOM generation and signing (low friction), then progressively add provenance verification and dependency review policies.
""",
    ),

    # --- 5. Runtime Application Security ---
    (
        "devsecops/runtime-application-security",
        r"""Describe runtime application security strategies including RASP instrumentation, WAF rule configuration with ModSecurity and cloud WAFs, intelligent rate limiting algorithms, anomaly detection for API traffic, and security event correlation across distributed services.""",
        r"""# Runtime Application Security: RASP, WAF, Rate Limiting, and Anomaly Detection

## Why Runtime Security Is the Last Line of Defense

No matter how thorough your SAST, DAST, and supply chain controls are, vulnerabilities will reach production. Zero-day exploits, business logic flaws, and novel attack techniques bypass static analysis because they target behaviors that only manifest at runtime. Runtime Application Self-Protection (RASP), Web Application Firewalls (WAF), rate limiting, and anomaly detection form the **defense-in-depth** layers that protect running applications. The trade-off is that runtime controls add latency and operational complexity; however, the alternative -- relying solely on pre-deployment scanning -- is a **common mistake** that leaves applications defenseless against unknown threats.

## RASP: Runtime Application Self-Protection

RASP instruments the application from within, monitoring function calls, database queries, and file system operations in real-time. Because RASP operates inside the application context, it has significantly better accuracy than external WAFs -- it can see the actual SQL query being constructed, not just the HTTP request that triggered it. Therefore, RASP has much lower false positive rates for attacks like SQL injection and path traversal.

### RASP Middleware Implementation

```python
import re
import time
import hashlib
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any, Set, Tuple
from enum import Enum
from functools import wraps
from datetime import datetime, timezone
import threading

logger = logging.getLogger(__name__)


class ThreatCategory(Enum):
    SQL_INJECTION = "sql_injection"
    XSS = "cross_site_scripting"
    PATH_TRAVERSAL = "path_traversal"
    COMMAND_INJECTION = "command_injection"
    SSRF = "server_side_request_forgery"
    DESERIALIZATION = "insecure_deserialization"


class RASPAction(Enum):
    MONITOR = "monitor"    # Log only
    BLOCK = "block"        # Block and return 403
    SANITIZE = "sanitize"  # Clean the input and continue


@dataclass
class SecurityEvent:
    # A detected security event with full context
    timestamp: str
    threat_category: ThreatCategory
    action_taken: RASPAction
    source_ip: str
    request_path: str
    request_method: str
    matched_pattern: str
    payload_snippet: str
    confidence: float
    user_id: Optional[str] = None
    trace_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "threat": self.threat_category.value,
            "action": self.action_taken.value,
            "source_ip": self.source_ip,
            "path": self.request_path,
            "method": self.request_method,
            "pattern": self.matched_pattern,
            "payload": self.payload_snippet[:200],
            "confidence": self.confidence,
            "user_id": self.user_id,
            "trace_id": self.trace_id,
        }


@dataclass
class DetectionRule:
    # A single RASP detection rule with pattern and action
    name: str
    category: ThreatCategory
    patterns: List[str]
    action: RASPAction = RASPAction.BLOCK
    confidence: float = 0.9
    enabled: bool = True
    compiled_patterns: List[re.Pattern] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.patterns
        ]


class RASPEngine:
    # Core RASP detection engine that inspects request payloads
    def __init__(self, mode: RASPAction = RASPAction.BLOCK):
        self.mode = mode
        self.rules: List[DetectionRule] = []
        self.event_buffer: List[SecurityEvent] = []
        self._lock = threading.Lock()
        self._load_default_rules()

    def _load_default_rules(self) -> None:
        self.rules = [
            DetectionRule(
                name="sql_injection_union",
                category=ThreatCategory.SQL_INJECTION,
                patterns=[
                    r"(?:union\s+(?:all\s+)?select)",
                    r"(?:;\s*(?:drop|alter|create|truncate)\s+table)",
                    r"(?:'\s*(?:or|and)\s+[\d'\"]+\s*[=<>])",
                    r"(?:(?:benchmark|sleep|waitfor)\s*\()",
                ],
                confidence=0.95,
            ),
            DetectionRule(
                name="xss_script_injection",
                category=ThreatCategory.XSS,
                patterns=[
                    r"<script[^>]*>",
                    r"javascript\s*:",
                    r"on(?:error|load|click|mouseover)\s*=",
                    r"(?:eval|setTimeout|setInterval)\s*\(",
                ],
                confidence=0.90,
            ),
            DetectionRule(
                name="path_traversal",
                category=ThreatCategory.PATH_TRAVERSAL,
                patterns=[
                    r"(?:\.\./){2,}",
                    r"(?:%2e%2e[/\\%]){2,}",
                    r"(?:/etc/(?:passwd|shadow|hosts))",
                    r"(?:\\\\[a-zA-Z]+\\[a-zA-Z$]+)",
                ],
                confidence=0.92,
            ),
            DetectionRule(
                name="command_injection",
                category=ThreatCategory.COMMAND_INJECTION,
                patterns=[
                    r"(?:;\s*(?:cat|ls|whoami|id|uname|curl|wget)\b)",
                    r"(?:\|\s*(?:bash|sh|cmd|powershell))",
                    r"(?:\$\(.*\))",
                    r"(?:`[^`]+`)",
                ],
                confidence=0.88,
            ),
        ]

    def inspect_request(
        self,
        source_ip: str,
        method: str,
        path: str,
        headers: Dict[str, str],
        query_params: Dict[str, str],
        body: Optional[str] = None,
        user_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[SecurityEvent]]:
        # Inspect all request components for malicious patterns
        # Returns (is_blocked, event_if_detected)
        payloads_to_check: List[Tuple[str, str]] = []

        # Check query parameters
        for key, value in query_params.items():
            payloads_to_check.append((f"query:{key}", value))

        # Check headers (common injection vectors)
        for header in ("user-agent", "referer", "x-forwarded-for", "cookie"):
            if header in headers:
                payloads_to_check.append((f"header:{header}", headers[header]))

        # Check request body
        if body:
            payloads_to_check.append(("body", body))

        # Check the path itself
        payloads_to_check.append(("path", path))

        for location, payload in payloads_to_check:
            for rule in self.rules:
                if not rule.enabled:
                    continue
                for pattern in rule.compiled_patterns:
                    match = pattern.search(payload)
                    if match:
                        event = SecurityEvent(
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            threat_category=rule.category,
                            action_taken=rule.action if self.mode != RASPAction.MONITOR else RASPAction.MONITOR,
                            source_ip=source_ip,
                            request_path=path,
                            request_method=method,
                            matched_pattern=rule.name,
                            payload_snippet=payload[:200],
                            confidence=rule.confidence,
                            user_id=user_id,
                            trace_id=trace_id,
                        )
                        with self._lock:
                            self.event_buffer.append(event)
                        logger.warning(
                            f"RASP detection: {rule.category.value} from {source_ip} "
                            f"on {path} (rule={rule.name}, action={event.action_taken.value})"
                        )
                        should_block = (
                            rule.action == RASPAction.BLOCK
                            and self.mode != RASPAction.MONITOR
                        )
                        return should_block, event

        return False, None

    def get_recent_events(self, limit: int = 100) -> List[SecurityEvent]:
        with self._lock:
            return list(self.event_buffer[-limit:])
```

## WAF Configuration: ModSecurity Core Rule Set

WAFs operate at the network edge, inspecting HTTP traffic before it reaches the application. The **best practice** is layering a WAF in front of RASP -- the WAF catches broad attack classes with generic rules, while RASP catches application-specific attacks with contextual awareness.

```python
# WAF rule management and cloud WAF integration
from dataclasses import dataclass
from typing import List, Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class WAFRule:
    # Represents a WAF rule for ModSecurity or cloud WAF
    rule_id: int
    description: str
    action: str             # deny, log, pass, redirect
    phase: int              # 1=request headers, 2=request body, 3=response headers, 4=response body
    severity: str
    pattern: str
    targets: List[str]      # ARGS, REQUEST_BODY, REQUEST_HEADERS, etc.
    paranoia_level: int = 1 # CRS paranoia level (1-4)
    enabled: bool = True

    def to_modsecurity(self) -> str:
        # Generate ModSecurity rule syntax
        targets_str = "|".join(self.targets)
        return (
            f'SecRule {targets_str} "{self.pattern}" '
            f'"id:{self.rule_id},'
            f'phase:{self.phase},'
            f'{self.action},'
            f'severity:{self.severity},'
            f'msg:\'{self.description}\','
            f'tag:\'paranoia-level/{self.paranoia_level}\'"'
        )


class WAFRuleManager:
    # Manages WAF rules across ModSecurity and cloud WAF providers
    def __init__(self) -> None:
        self.rules: List[WAFRule] = []
        self._load_baseline_rules()

    def _load_baseline_rules(self) -> None:
        # Core rules that should always be active
        self.rules.extend([
            WAFRule(
                rule_id=100001,
                description="SQL injection via UNION SELECT",
                action="deny",
                phase=2,
                severity="CRITICAL",
                pattern=r"(?i:union\s+(?:all\s+)?select)",
                targets=["ARGS", "REQUEST_BODY"],
            ),
            WAFRule(
                rule_id=100002,
                description="XSS via script tag injection",
                action="deny",
                phase=2,
                severity="CRITICAL",
                pattern=r"(?i:<script[^>]*>)",
                targets=["ARGS", "REQUEST_BODY", "REQUEST_HEADERS"],
            ),
            WAFRule(
                rule_id=100003,
                description="Path traversal attempt",
                action="deny",
                phase=1,
                severity="HIGH",
                pattern=r"(?:\.\./){2,}",
                targets=["REQUEST_URI", "ARGS"],
            ),
        ])

    def generate_modsecurity_config(self) -> str:
        lines = [
            "# Auto-generated ModSecurity rules",
            "SecRuleEngine On",
            "SecRequestBodyAccess On",
            "SecResponseBodyAccess Off",
            ""
        ]
        for rule in self.rules:
            if rule.enabled:
                lines.append(rule.to_modsecurity())
        return "\n".join(lines)
```

## Intelligent Rate Limiting

Simple rate limiting (e.g., 100 requests per minute per IP) is trivially bypassed with distributed attacks. **Best practice** is adaptive rate limiting that considers multiple signals: IP reputation, endpoint sensitivity, user authentication state, and request patterns.

```python
import time
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class TokenBucket:
    # Token bucket rate limiter with configurable burst
    capacity: float
    refill_rate: float      # tokens per second
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.time)

    def consume(self, tokens: int = 1) -> bool:
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


@dataclass
class ClientProfile:
    # Behavioral profile for a client used in adaptive rate limiting
    ip_address: str
    request_count: int = 0
    error_count: int = 0       # 4xx/5xx responses
    unique_endpoints: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    is_authenticated: bool = False
    reputation_score: float = 1.0  # 0.0 (malicious) to 1.0 (trusted)

    @property
    def error_rate(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.error_count / self.request_count

    @property
    def request_velocity(self) -> float:
        # Requests per second over the client's lifetime
        duration = max(self.last_seen - self.first_seen, 1.0)
        return self.request_count / duration


class AdaptiveRateLimiter:
    # Multi-dimensional rate limiter with behavioral analysis
    def __init__(
        self,
        base_rate: float = 10.0,     # requests/sec for normal clients
        burst_capacity: float = 50.0,
        penalty_multiplier: float = 0.5,
    ):
        self.base_rate = base_rate
        self.burst_capacity = burst_capacity
        self.penalty_multiplier = penalty_multiplier
        self.buckets: Dict[str, TokenBucket] = {}
        self.profiles: Dict[str, ClientProfile] = defaultdict(
            lambda: ClientProfile(ip_address="unknown")
        )
        self._lock = threading.Lock()

    def _get_effective_rate(self, profile: ClientProfile) -> float:
        # Calculate rate limit based on client behavior
        rate = self.base_rate

        # Authenticated users get higher limits
        if profile.is_authenticated:
            rate *= 2.0

        # High error rate suggests scanning or fuzzing
        if profile.error_rate > 0.5:
            rate *= self.penalty_multiplier
            logger.info(
                f"Reduced rate for {profile.ip_address}: "
                f"error_rate={profile.error_rate:.2f}"
            )

        # Adjust by reputation score
        rate *= max(profile.reputation_score, 0.1)

        # Extremely high velocity is suspicious regardless
        if profile.request_velocity > self.base_rate * 5:
            rate *= 0.25

        return rate

    def check_rate_limit(
        self,
        client_id: str,
        ip_address: str,
        endpoint: str,
        is_authenticated: bool = False,
    ) -> Tuple[bool, Dict[str, Any]]:
        # Check if request should be allowed, returns (allowed, metadata)
        with self._lock:
            profile = self.profiles[client_id]
            profile.ip_address = ip_address
            profile.request_count += 1
            profile.last_seen = time.time()
            profile.is_authenticated = is_authenticated

            effective_rate = self._get_effective_rate(profile)

            if client_id not in self.buckets:
                self.buckets[client_id] = TokenBucket(
                    capacity=self.burst_capacity,
                    refill_rate=effective_rate,
                    tokens=self.burst_capacity,
                )
            else:
                # Update rate dynamically
                self.buckets[client_id].refill_rate = effective_rate

            bucket = self.buckets[client_id]
            allowed = bucket.consume()

            metadata = {
                "allowed": allowed,
                "effective_rate": effective_rate,
                "tokens_remaining": bucket.tokens,
                "client_error_rate": profile.error_rate,
                "reputation": profile.reputation_score,
            }

            if not allowed:
                logger.warning(
                    f"Rate limited {client_id} ({ip_address}) on {endpoint}: "
                    f"rate={effective_rate:.1f}/s, reputation={profile.reputation_score:.2f}"
                )

            return allowed, metadata

    def record_response(self, client_id: str, status_code: int) -> None:
        # Update client profile with response information
        with self._lock:
            profile = self.profiles[client_id]
            if status_code >= 400:
                profile.error_count += 1
            # Degrade reputation for repeated errors
            if profile.error_rate > 0.7 and profile.request_count > 20:
                profile.reputation_score = max(0.1, profile.reputation_score - 0.05)
```

## Security Event Correlation

In distributed systems, a single attack may generate events across multiple services. Correlating these events by trace ID, source IP, and time window is essential for detecting coordinated attacks. The **pitfall** is alerting on individual events rather than correlated patterns, which generates excessive noise.

## Summary and Key Takeaways

- **RASP and WAF serve complementary roles**: WAFs filter broad attack classes at the network edge, while RASP detects application-specific attacks with context-aware accuracy. Using both is a **best practice** for defense in depth.
- **Adaptive rate limiting** is far superior to static limits because it considers behavioral signals like error rates, authentication state, and request velocity; therefore, legitimate traffic is rarely impacted while attacks are throttled aggressively.
- **Anomaly detection** on API traffic catches zero-day attacks and business logic abuse that signature-based tools miss. However, the trade-off is that ML-based detection requires a training period and generates false positives during that phase.
- **Security event correlation** across distributed services is essential because modern attacks span multiple services; a **common mistake** is analyzing each service's logs in isolation, missing the coordinated nature of the attack.
- **The key pitfall** in runtime security is deploying in blocking mode without sufficient tuning. Best practice is to start in monitor/log-only mode, tune rules and thresholds using production traffic, and then gradually enable blocking for high-confidence detections.
""",
    ),
]
