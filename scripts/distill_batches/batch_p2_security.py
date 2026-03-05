"""
Batch P2 — Security: SBOM, supply chain, runtime security, post-quantum crypto.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Software Supply Chain Security ---
    (
        "supply_chain_sbom_sigstore",
        "Explain software supply chain security — SBOM generation, Sigstore for artifact signing, "
        "SLSA framework levels, and dependency confusion attacks. Show how to build a secure CI/CD "
        "pipeline that generates SBOMs, signs artifacts with Sigstore, and achieves SLSA Level 3. "
        "Include GitHub Actions workflow and Python/Go code with proper error handling.",
        """\
# Software Supply Chain Security: SBOM, Sigstore, and SLSA

## The Problem

Software supply chain attacks have caused billions in damage:
- **SolarWinds (2020)**: Build system compromised, malicious code injected into signed updates
- **Log4Shell (2021)**: Vulnerability in ubiquitous dependency, unknown to most consumers
- **Codecov (2021)**: CI/CD tool compromised, secrets exfiltrated from thousands of repos
- **xz Utils (2024)**: Backdoor planted by a long-term social engineering campaign

The root cause is that modern software depends on hundreds of external packages,
and most organizations have no visibility into what's in their dependency tree,
whether artifacts have been tampered with, or how they were built.

## SBOM (Software Bill of Materials)

An SBOM is a **complete inventory of every component** in your software — like a nutrition
label for code. It enables vulnerability scanning, license compliance, and incident response.

### Generating SBOMs

```python
\"\"\"SBOM generation and vulnerability scanning pipeline.\"\"\"
import json
import subprocess
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from pathlib import Path
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


@dataclass
class Component:
    \"\"\"A single software component in the SBOM.\"\"\"
    name: str
    version: str
    purl: str  # Package URL — universal identifier
    licenses: List[str] = field(default_factory=list)
    hashes: Dict[str, str] = field(default_factory=dict)
    supplier: str = ""
    is_direct: bool = True  # Direct dependency vs transitive


@dataclass
class SBOM:
    \"\"\"CycloneDX-format Software Bill of Materials.\"\"\"
    project_name: str
    project_version: str
    components: List[Component] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_cyclonedx(self) -> Dict[str, Any]:
        \"\"\"Export as CycloneDX 1.5 JSON format — the industry standard.\"\"\"
        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "version": 1,
            "metadata": {
                "timestamp": self.created_at,
                "component": {
                    "type": "application",
                    "name": self.project_name,
                    "version": self.project_version,
                },
                "tools": [{"name": "hiveai-sbom-gen", "version": "1.0.0"}],
            },
            "components": [
                {
                    "type": "library",
                    "name": comp.name,
                    "version": comp.version,
                    "purl": comp.purl,
                    "licenses": [{"license": {"id": lic}} for lic in comp.licenses],
                    "hashes": [
                        {"alg": alg, "content": digest}
                        for alg, digest in comp.hashes.items()
                    ],
                    "scope": "required" if comp.is_direct else "optional",
                }
                for comp in self.components
            ],
        }


def generate_python_sbom(project_dir: Path) -> SBOM:
    \"\"\"
    Generate SBOM from Python project using pip inspect.

    The reason we use `pip inspect` instead of parsing requirements.txt is that
    requirements.txt doesn't include transitive dependencies or their hashes.
    pip inspect gives us the complete resolved dependency graph.
    \"\"\"
    try:
        result = subprocess.run(
            ["pip", "inspect", "--format=json"],
            capture_output=True, text=True, check=True,
            cwd=str(project_dir),
        )
        installed = json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"pip inspect failed: {e.stderr}")
        raise RuntimeError(f"Failed to inspect Python packages: {e}") from e

    # Parse pyproject.toml for direct dependencies
    direct_deps = set()
    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        import tomllib
        with open(pyproject, "rb") as f:
            config = tomllib.load(f)
            for dep in config.get("project", {}).get("dependencies", []):
                # Extract package name from dependency specifier
                name = dep.split(">=")[0].split("==")[0].split("[")[0].strip().lower()
                direct_deps.add(name)

    sbom = SBOM(
        project_name=project_dir.name,
        project_version="0.0.0",  # From pyproject.toml
    )

    for pkg in installed.get("installed", []):
        meta = pkg.get("metadata", {})
        name = meta.get("name", "unknown")
        version = meta.get("version", "0.0.0")

        component = Component(
            name=name,
            version=version,
            purl=f"pkg:pypi/{name}@{version}",
            licenses=[meta.get("license", "UNKNOWN")],
            is_direct=name.lower() in direct_deps,
        )

        # Add hash if available
        dist_info = pkg.get("dist_info_path", "")
        if dist_info:
            record_file = Path(dist_info) / "RECORD"
            if record_file.exists():
                component.hashes["SHA-256"] = _hash_file(record_file)

        sbom.components.append(component)

    logger.info(
        f"Generated SBOM: {len(sbom.components)} components "
        f"({sum(1 for c in sbom.components if c.is_direct)} direct)"
    )
    return sbom


def _hash_file(path: Path) -> str:
    \"\"\"SHA-256 hash of a file.\"\"\"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_vulnerabilities(sbom: SBOM) -> List[Dict[str, Any]]:
    \"\"\"
    Scan SBOM components against vulnerability databases (OSV, NVD).

    Uses the OSV API because it's free, covers multiple ecosystems,
    and is maintained by Google. The alternative (NVD) requires API keys
    and has rate limits.
    \"\"\"
    import httpx

    vulnerabilities = []
    # Batch query for efficiency — OSV supports batch
    queries = [
        {"package": {"name": c.name, "ecosystem": "PyPI"}, "version": c.version}
        for c in sbom.components
    ]

    try:
        response = httpx.post(
            "https://api.osv.dev/v1/querybatch",
            json={"queries": queries},
            timeout=30,
        )
        response.raise_for_status()
        results = response.json().get("results", [])

        for i, result in enumerate(results):
            for vuln in result.get("vulns", []):
                vulnerabilities.append({
                    "component": sbom.components[i].name,
                    "version": sbom.components[i].version,
                    "vuln_id": vuln["id"],
                    "summary": vuln.get("summary", "No summary"),
                    "severity": _extract_severity(vuln),
                })

    except httpx.HTTPError as e:
        logger.error(f"OSV API query failed: {e}")
        raise

    return vulnerabilities


def _extract_severity(vuln: Dict) -> str:
    \"\"\"Extract CVSS severity from OSV vulnerability data.\"\"\"
    for severity in vuln.get("severity", []):
        if severity.get("type") == "CVSS_V3":
            score = float(severity.get("score", "0"))
            if score >= 9.0: return "CRITICAL"
            if score >= 7.0: return "HIGH"
            if score >= 4.0: return "MEDIUM"
            return "LOW"
    return "UNKNOWN"
```

## Sigstore Artifact Signing

```yaml
# .github/workflows/secure-release.yaml
# SLSA Level 3 pipeline: provenance, signing, SBOM

name: Secure Release
on:
  push:
    tags: ["v*"]

permissions:
  contents: write
  id-token: write    # Required for Sigstore OIDC signing
  attestations: write
  packages: write

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      digest: ${{ steps.build.outputs.digest }}

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Build package
        id: build
        run: |
          pip install build
          python -m build
          # Record the SHA-256 digest of the built artifact
          DIGEST=$(sha256sum dist/*.whl | head -1 | awk '{print "sha256:"$1}')
          echo "digest=${DIGEST}" >> $GITHUB_OUTPUT

      - name: Generate SBOM
        run: |
          pip install cyclonedx-bom
          cyclonedx-py environment \
            --output-format json \
            --output sbom.cdx.json

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: release-artifacts
          path: |
            dist/*.whl
            dist/*.tar.gz
            sbom.cdx.json

  sign:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: release-artifacts

      # Sigstore signing — keyless using GitHub OIDC identity
      # No private keys to manage! Identity comes from the CI workflow.
      - name: Sign with Sigstore
        uses: sigstore/gh-action-sigstore-python@v3
        with:
          inputs: |
            dist/*.whl
            dist/*.tar.gz

      # GitHub Attestation — SLSA provenance
      - name: Generate SLSA provenance
        uses: actions/attest-build-provenance@v1
        with:
          subject-name: myorg/mypackage
          subject-digest: ${{ needs.build.outputs.digest }}

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            dist/*
            *.sigstore.json
            sbom.cdx.json
```

## Sigstore Verification in Go

```go
package verify

import (
    "context"
    "crypto/sha256"
    "encoding/hex"
    "fmt"
    "io"
    "os"

    "github.com/sigstore/sigstore-go/pkg/verify"
    "github.com/sigstore/sigstore-go/pkg/root"
    "github.com/sigstore/sigstore-go/pkg/bundle"
)

// VerifyArtifact verifies a Sigstore-signed artifact.
//
// Sigstore's keyless signing works because the signer's identity (from OIDC)
// is embedded in the transparency log. Verification checks:
// 1. Signature is valid for the artifact
// 2. Certificate was issued by Fulcio (Sigstore's CA)
// 3. Entry exists in Rekor transparency log (tamper-evident)
// 4. Signer identity matches expected issuer/subject
func VerifyArtifact(
    ctx context.Context,
    artifactPath string,
    bundlePath string,
    expectedIssuer string,
    expectedIdentity string,
) error {
    // Load the Sigstore trusted root (Fulcio CA + Rekor log)
    trustedRoot, err := root.FetchTrustedRoot()
    if err != nil {
        return fmt.Errorf("fetching trusted root: %w", err)
    }

    // Load the signature bundle
    bundleBytes, err := os.ReadFile(bundlePath)
    if err != nil {
        return fmt.Errorf("reading bundle: %w", err)
    }

    sigBundle, err := bundle.LoadJSONFromBytes(bundleBytes)
    if err != nil {
        return fmt.Errorf("parsing bundle: %w", err)
    }

    // Compute artifact digest
    artifactFile, err := os.Open(artifactPath)
    if err != nil {
        return fmt.Errorf("opening artifact: %w", err)
    }
    defer artifactFile.Close()

    hasher := sha256.New()
    if _, err := io.Copy(hasher, artifactFile); err != nil {
        return fmt.Errorf("hashing artifact: %w", err)
    }
    digest := hex.EncodeToString(hasher.Sum(nil))

    // Build verification policy
    verifierConfig := []verify.PolicyOption{
        verify.WithCertificateIdentity(
            verify.CertificateIdentity{
                Issuer:  expectedIssuer,  // e.g., "https://token.actions.githubusercontent.com"
                Subject: expectedIdentity, // e.g., "https://github.com/myorg/myrepo/.github/workflows/release.yml@refs/tags/v1.0.0"
            },
        ),
    }

    policy, err := verify.NewPolicy(verifierConfig...)
    if err != nil {
        return fmt.Errorf("creating policy: %w", err)
    }

    // Verify!
    sev, err := verify.NewSignedEntityVerifier(trustedRoot)
    if err != nil {
        return fmt.Errorf("creating verifier: %w", err)
    }

    result, err := sev.Verify(sigBundle, policy)
    if err != nil {
        return fmt.Errorf("verification failed: %w", err)
    }

    fmt.Printf("Verified! Signer: %s, Issuer: %s\\n",
        result.Statement.Subject, result.Statement.Issuer)
    return nil
}
```

## SLSA Framework Levels

```
SLSA (Supply-chain Levels for Software Artifacts) — graduated security guarantees:

Level 0: No guarantees
  - Anyone can modify the build process
  - No provenance information

Level 1: Build provenance exists
  - Automated build process
  - Provenance document generated (who built it, how)
  - No integrity guarantees on provenance itself

Level 2: Signed provenance from hosted build
  - Build runs on a hosted service (GitHub Actions, Cloud Build)
  - Provenance is signed and tamper-evident
  - Prevents most build tampering after-the-fact

Level 3: Hardened build platform (production target)
  - Build environment is ephemeral (fresh VM per build)
  - Build definition comes from version-controlled source
  - Provenance cannot be forged by build service admins
  - Prevents insider threats and compromised build services

Level 4 (proposed): Hermetic, reproducible builds
  - Build is fully reproducible from source
  - All dependencies pinned by hash
  - Two independent builds produce identical artifacts
```

## Dependency Confusion Defense

```python
def check_dependency_confusion(
    requirements_file: Path,
    internal_registry: str = "https://pypi.internal.corp/simple/",
) -> List[Dict[str, str]]:
    \"\"\"
    Detect potential dependency confusion attacks.

    The attack: if your org uses internal packages (e.g., 'corp-utils'),
    an attacker can publish 'corp-utils' on public PyPI with a higher version.
    pip defaults to choosing the highest version, pulling the malicious package.

    Prevention strategies:
    1. Pin all dependencies to exact versions with hashes
    2. Use --index-url (not --extra-index-url) to prevent fallback to PyPI
    3. Claim your internal package names on public PyPI (namespace squatting defense)
    4. Use pip's --require-hashes to verify integrity
    \"\"\"
    import httpx

    risks = []
    with open(requirements_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue

            pkg_name = line.split("==")[0].split(">=")[0].split("[")[0].strip()

            # Check if package exists on public PyPI
            try:
                resp = httpx.get(
                    f"https://pypi.org/pypi/{pkg_name}/json",
                    timeout=10,
                )
                if resp.status_code == 200:
                    pypi_data = resp.json()
                    public_version = pypi_data["info"]["version"]
                    risks.append({
                        "package": pkg_name,
                        "risk": "exists_on_public_pypi",
                        "public_version": public_version,
                        "recommendation": "Pin with hash or use --index-url",
                    })
                elif resp.status_code == 404:
                    # Package doesn't exist on public PyPI — potential target
                    risks.append({
                        "package": pkg_name,
                        "risk": "internal_only_not_claimed",
                        "recommendation": "Register placeholder on public PyPI",
                    })
            except httpx.HTTPError:
                continue

    return risks
```

## Key Takeaways

Supply chain security is a defense-in-depth problem — no single tool solves it. The
recommended production stack is: **SBOM generation** (CycloneDX) for visibility, **Sigstore**
for artifact signing without key management, **SLSA provenance** for build integrity, and
**dependency pinning with hashes** for reproducibility. The trade-off is developer experience
versus security — strict pinning slows down dependency updates, but the alternative is
trusting that every package in your tree hasn't been compromised. For production systems,
the security overhead is worth it.

The most common mistake is focusing only on vulnerability scanning while ignoring build
integrity. Scanning tells you about known vulnerabilities; SLSA provenance tells you
whether the artifact was built from the source code you reviewed. Both are essential
because a compromised build system can inject malicious code that no scanner will detect.
"""
    ),

    # --- 2. Container Runtime Security ---
    (
        "container_runtime_security",
        "Explain container runtime security using seccomp profiles, AppArmor, and OPA Gatekeeper. "
        "Show how to build a defense-in-depth container security strategy with proper pod security "
        "standards, network policies, and runtime threat detection. Include Kubernetes YAML manifests "
        "and Go policy code with error handling and testing.",
        """\
# Container Runtime Security: Defense in Depth

## The Threat Model

Containers share the host kernel. A container escape (exploiting a kernel vulnerability from
within a container) gives the attacker root access to the host and all other containers.
Defense in depth means: even if one layer fails, other layers prevent full compromise.

```
                    Defense Layers
┌─────────────────────────────────────────────┐
│ Layer 5: Runtime Detection (Falco, Tetragon)│ ← Detect anomalies
│ Layer 4: Network Policies                    │ ← Limit blast radius
│ Layer 3: OPA/Gatekeeper (admission control)  │ ← Prevent misconfig
│ Layer 2: Seccomp + AppArmor (syscall filter) │ ← Limit capabilities
│ Layer 1: Pod Security Standards              │ ← Baseline hardening
│ Layer 0: Image Scanning (Trivy, Grype)       │ ← Prevent known vulns
└─────────────────────────────────────────────┘
```

## Layer 1: Pod Security Standards

```yaml
# Kubernetes Pod Security Standards (PSS) — enforce at namespace level
# Three profiles: Privileged (no restrictions), Baseline, Restricted

# Enforce restricted profile on production namespace
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    # Pod Security Admission controller enforces these
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted

---
# A properly hardened pod that passes "restricted" PSS
apiVersion: v1
kind: Pod
metadata:
  name: secure-api
  namespace: production
spec:
  # Don't use the default service account (has API access)
  automountServiceAccountToken: false
  serviceAccountName: api-minimal

  securityContext:
    runAsNonRoot: true           # Never run as root
    runAsUser: 10001             # Specific non-root UID
    runAsGroup: 10001
    fsGroup: 10001
    seccompProfile:
      type: RuntimeDefault       # Enable default seccomp profile

  containers:
    - name: api
      image: myorg/api:v2.1.0@sha256:abc123...  # Pin by digest, not tag
      securityContext:
        allowPrivilegeEscalation: false  # Prevent setuid/setgid
        readOnlyRootFilesystem: true     # Prevent file writes
        capabilities:
          drop: ["ALL"]                  # Drop ALL Linux capabilities
          # add: ["NET_BIND_SERVICE"]    # Only if needed for port < 1024
        runAsNonRoot: true
      resources:
        limits:
          cpu: "500m"
          memory: "512Mi"
          ephemeral-storage: "100Mi"     # Prevent disk filling
        requests:
          cpu: "250m"
          memory: "256Mi"
      # Writable dirs via emptyDir volumes (since rootfs is read-only)
      volumeMounts:
        - name: tmp
          mountPath: /tmp
        - name: cache
          mountPath: /app/cache

  volumes:
    - name: tmp
      emptyDir:
        medium: Memory     # tmpfs — no disk writes, auto-cleaned
        sizeLimit: 64Mi
    - name: cache
      emptyDir:
        sizeLimit: 128Mi
```

## Layer 2: Custom Seccomp Profile

```json
{
    "defaultAction": "SCMP_ACT_ERRNO",
    "architectures": ["SCMP_ARCH_X86_64"],
    "syscalls": [
        {
            "names": [
                "read", "write", "close", "fstat", "lseek", "mmap",
                "mprotect", "munmap", "brk", "pread64", "pwrite64",
                "readv", "writev", "access", "pipe", "select", "poll",
                "dup", "dup2", "clone", "execve", "exit", "exit_group",
                "wait4", "kill", "fcntl", "flock", "fsync",
                "getpid", "getuid", "geteuid", "getgid", "getegid",
                "socket", "connect", "accept", "sendto", "recvfrom",
                "bind", "listen", "setsockopt", "getsockopt",
                "epoll_create1", "epoll_ctl", "epoll_wait",
                "openat", "newfstatat", "futex", "nanosleep",
                "clock_gettime", "getrandom", "sigaltstack",
                "set_robust_list", "rt_sigaction", "rt_sigprocmask"
            ],
            "action": "SCMP_ACT_ALLOW"
        },
        {
            "names": ["ptrace", "personality", "mount", "umount2",
                      "pivot_root", "chroot", "reboot", "sethostname",
                      "init_module", "delete_module", "kexec_load"],
            "action": "SCMP_ACT_KILL"
        }
    ]
}
```

**Why a custom profile?** The default seccomp profile blocks ~44 of ~300+ syscalls.
A custom allow-list profile blocks everything except what your app needs. This means
if an attacker gets code execution inside the container, they can't use dangerous syscalls
like `ptrace` (process injection), `mount` (filesystem escape), or `kexec_load` (kernel
replacement). The trade-off is maintenance — you must update the allow-list when your
application's syscall usage changes.

## Layer 3: OPA Gatekeeper Policies

```yaml
# OPA Gatekeeper — Kubernetes admission controller using Rego policies
# Prevents non-compliant resources from being created

# ConstraintTemplate defines the POLICY LOGIC
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8scontainerlimits
spec:
  crd:
    spec:
      names:
        kind: K8sContainerLimits
      validation:
        openAPIV3Schema:
          type: object
          properties:
            maxCpu:
              type: string
            maxMemory:
              type: string
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8scontainerlimits

        # Deny if container has no resource limits
        violation[{"msg": msg}] {
            container := input.review.object.spec.containers[_]
            not container.resources.limits
            msg := sprintf("Container %s must have resource limits", [container.name])
        }

        # Deny if CPU limit exceeds maximum
        violation[{"msg": msg}] {
            container := input.review.object.spec.containers[_]
            cpu_limit := container.resources.limits.cpu
            max_cpu := input.parameters.maxCpu
            # Convert to millicores for comparison
            cpu_cores := to_number(trim_suffix(cpu_limit, "m"))
            max_cores := to_number(trim_suffix(max_cpu, "m"))
            cpu_cores > max_cores
            msg := sprintf(
                "Container %s CPU limit %s exceeds max %s",
                [container.name, cpu_limit, max_cpu]
            )
        }

---
# Constraint APPLIES the template with specific parameters
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sContainerLimits
metadata:
  name: production-limits
spec:
  enforcementAction: deny
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Pod"]
      - apiGroups: ["apps"]
        kinds: ["Deployment", "StatefulSet", "DaemonSet"]
    namespaces: ["production"]
  parameters:
    maxCpu: "2000m"
    maxMemory: "4Gi"
```

## Layer 4: Network Policies

```yaml
# Default deny — no pod can talk to any other pod unless explicitly allowed
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: production
spec:
  podSelector: {}  # Applies to ALL pods in namespace
  policyTypes:
    - Ingress
    - Egress

---
# Allow API pods to receive traffic from ingress controller only
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-ingress
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-system
        - podSelector:
            matchLabels:
              app: nginx-ingress
      ports:
        - port: 8080
          protocol: TCP
  egress:
    # Allow DNS
    - to:
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - port: 53
          protocol: UDP
    # Allow database access
    - to:
        - podSelector:
            matchLabels:
              app: postgresql
      ports:
        - port: 5432
          protocol: TCP
    # Allow external HTTPS (APIs, package registries)
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 10.0.0.0/8      # Block internal network access
              - 172.16.0.0/12
              - 192.168.0.0/16
      ports:
        - port: 443
          protocol: TCP
```

## Layer 5: Runtime Threat Detection with Go

```go
package security

import (
    "context"
    "fmt"
    "log/slog"
    "strings"
    "time"
)

// ThreatEvent represents a detected security anomaly
type ThreatEvent struct {
    Timestamp   time.Time
    Severity    string // "critical", "high", "medium", "low"
    Container   string
    Namespace   string
    Description string
    Syscall     string // If syscall-related
    Process     string
    Action      string // "alert", "kill", "block"
}

// ThreatRule defines a detection rule
type ThreatRule struct {
    Name        string
    Description string
    Severity    string
    Match       func(event *ThreatEvent) bool
    Action      string
}

// SecurityMonitor watches for runtime threats
type SecurityMonitor struct {
    rules    []ThreatRule
    alertCh  chan ThreatEvent
    logger   *slog.Logger
}

// NewSecurityMonitor creates a monitor with default detection rules
func NewSecurityMonitor(logger *slog.Logger) *SecurityMonitor {
    m := &SecurityMonitor{
        alertCh: make(chan ThreatEvent, 100),
        logger:  logger,
    }
    m.registerDefaultRules()
    return m
}

func (m *SecurityMonitor) registerDefaultRules() {
    m.rules = []ThreatRule{
        {
            Name:        "container_shell_exec",
            Description: "Interactive shell opened in container",
            Severity:    "high",
            Match: func(e *ThreatEvent) bool {
                shells := []string{"/bin/sh", "/bin/bash", "/bin/zsh"}
                for _, shell := range shells {
                    if strings.Contains(e.Process, shell) {
                        return true
                    }
                }
                return false
            },
            Action: "alert",
        },
        {
            Name:        "sensitive_file_access",
            Description: "Access to sensitive files (secrets, keys, shadow)",
            Severity:    "critical",
            Match: func(e *ThreatEvent) bool {
                sensitivePatterns := []string{
                    "/etc/shadow", "/etc/passwd", "/.ssh/",
                    "/var/run/secrets/", ".env", "credentials",
                }
                for _, pattern := range sensitivePatterns {
                    if strings.Contains(e.Description, pattern) {
                        return true
                    }
                }
                return false
            },
            Action: "alert",
        },
        {
            Name:        "crypto_mining_detection",
            Description: "Potential cryptocurrency mining activity",
            Severity:    "critical",
            Match: func(e *ThreatEvent) bool {
                minerPatterns := []string{
                    "stratum+tcp", "xmrig", "minerd", "cpuminer",
                    "cryptonight", "monero",
                }
                lower := strings.ToLower(e.Description + " " + e.Process)
                for _, pattern := range minerPatterns {
                    if strings.Contains(lower, pattern) {
                        return true
                    }
                }
                return false
            },
            Action: "kill",
        },
        {
            Name:        "privilege_escalation",
            Description: "Privilege escalation attempt detected",
            Severity:    "critical",
            Match: func(e *ThreatEvent) bool {
                privEscSyscalls := []string{
                    "setuid", "setgid", "setns", "unshare",
                    "ptrace", "mount",
                }
                for _, syscall := range privEscSyscalls {
                    if e.Syscall == syscall {
                        return true
                    }
                }
                return false
            },
            Action: "block",
        },
    }
}

// Evaluate checks an event against all rules
func (m *SecurityMonitor) Evaluate(ctx context.Context, event *ThreatEvent) []ThreatRule {
    var matched []ThreatRule
    for _, rule := range m.rules {
        if rule.Match(event) {
            event.Severity = rule.Severity
            event.Action = rule.Action
            matched = append(matched, rule)

            m.logger.WarnContext(ctx, "threat detected",
                "rule", rule.Name,
                "severity", rule.Severity,
                "container", event.Container,
                "namespace", event.Namespace,
                "action", rule.Action,
            )

            select {
            case m.alertCh <- *event:
            default:
                m.logger.Error("alert channel full, dropping event")
            }
        }
    }
    return matched
}
```

## Testing Security Rules

```go
func TestCryptoMiningDetection(t *testing.T) {
    monitor := NewSecurityMonitor(slog.Default())

    tests := []struct {
        name    string
        event   ThreatEvent
        matched bool
    }{
        {
            name: "xmrig process",
            event: ThreatEvent{
                Process:     "/tmp/xmrig",
                Description: "new process started",
                Container:   "api-pod",
            },
            matched: true,
        },
        {
            name: "stratum connection",
            event: ThreatEvent{
                Process:     "curl",
                Description: "outbound connection to stratum+tcp://pool.mining.com",
                Container:   "worker-pod",
            },
            matched: true,
        },
        {
            name: "normal process",
            event: ThreatEvent{
                Process:     "/usr/bin/python3",
                Description: "serving HTTP on port 8080",
                Container:   "api-pod",
            },
            matched: false,
        },
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            rules := monitor.Evaluate(context.Background(), &tt.event)
            if (len(rules) > 0) != tt.matched {
                t.Errorf("expected matched=%v, got %d rules", tt.matched, len(rules))
            }
            if tt.matched && rules[0].Severity != "critical" {
                t.Errorf("crypto mining should be critical severity")
            }
        })
    }
}
```

## Key Takeaways

Container security is defense in depth — no single layer is sufficient. The most common
mistake is relying solely on image scanning (Layer 0), which only catches known vulnerabilities
in known packages. Production systems need all five layers because each addresses a different
threat: image scanning prevents known CVEs, pod security prevents misconfigurations, seccomp
limits exploit capabilities, network policies limit blast radius, and runtime detection
catches zero-day attacks. The trade-off is operational complexity versus security posture,
but for production workloads handling sensitive data, the complexity is justified.
"""
    ),

    # --- 3. Post-Quantum Cryptography ---
    (
        "post_quantum_cryptography_migration",
        "Explain post-quantum cryptography — why RSA and ECC are threatened by quantum computers, "
        "how lattice-based cryptography works, the NIST PQC standards (ML-KEM, ML-DSA, SLH-DSA), "
        "and build a hybrid key exchange implementation in Python. Cover the migration strategy "
        "for existing systems with backward compatibility.",
        """\
# Post-Quantum Cryptography: Preparing for the Quantum Threat

## Why Current Cryptography is at Risk

RSA and ECC security relies on mathematical problems that classical computers can't solve
efficiently (factoring large numbers, computing discrete logarithms). However, Shor's
algorithm on a sufficiently powerful quantum computer solves these in polynomial time.

```
Algorithm          Classical Security    Quantum Security    Status
RSA-2048           112 bits              0 bits (broken)     MIGRATE
ECDSA P-256        128 bits              0 bits (broken)     MIGRATE
AES-256            256 bits              128 bits (halved)   OK (double key)
SHA-256            256 bits              128 bits (halved)   OK
ChaCha20-Poly1305  256 bits              128 bits (halved)   OK

Timeline concern: "Harvest now, decrypt later" attacks
  - Adversaries record encrypted traffic TODAY
  - Decrypt it when quantum computers become available (2030-2040?)
  - Sensitive data with long secrecy requirements is at risk NOW
```

**Key insight**: Symmetric cryptography (AES, ChaCha20) and hash functions (SHA-256) are
only weakened, not broken, by quantum computers (Grover's algorithm halves the security
level). The urgent migration is for **asymmetric cryptography** — key exchange (RSA, ECDH)
and digital signatures (RSA, ECDSA, EdDSA).

## NIST Post-Quantum Standards

NIST finalized three PQC standards in 2024 after an 8-year competition:

### ML-KEM (Module-Lattice Key Encapsulation Mechanism)
- **Replaces**: RSA key exchange, ECDH
- **Based on**: Module Learning With Errors (MLWE) lattice problem
- **Sizes**: ML-KEM-512 (128-bit), ML-KEM-768 (192-bit), ML-KEM-1024 (256-bit)
- **Performance**: Faster than RSA, slightly larger keys

### ML-DSA (Module-Lattice Digital Signature Algorithm)
- **Replaces**: RSA signatures, ECDSA, EdDSA
- **Based on**: Module Learning With Errors + Fiat-Shamir with Aborts
- **Sizes**: ML-DSA-44 (128-bit), ML-DSA-65 (192-bit), ML-DSA-87 (256-bit)
- **Performance**: Fast signing/verification, larger signatures than ECDSA

### SLH-DSA (Stateless Hash-Based Digital Signature Algorithm)
- **Replaces**: Same as ML-DSA (backup in case lattice assumptions break)
- **Based on**: Hash functions only — minimal mathematical assumptions
- **Sizes**: SLH-DSA-128s (small), SLH-DSA-128f (fast), etc.
- **Trade-off**: Very large signatures but based on well-understood hash security

## How Lattice-Based Cryptography Works

```
The Learning With Errors (LWE) problem:

Given: Matrix A (public), vector b = A*s + e (public)
  Where: s = secret key, e = small random "error" vector
Find:  s

This is HARD because the error vector e masks the relationship between A and s.
Without the error: b = A*s → just solve a linear system (easy)
With the error: b ≈ A*s → lattice reduction problem (hard for classical AND quantum)

Simplified analogy:
  Classic RSA: "factor 15" → 3 × 5 (quantum computer: easy with Shor's)
  LWE: "find x such that Ax ≈ b (with noise)" → lattice problem (quantum: still hard)

Key generation:
  1. Generate random matrix A (public parameter)
  2. Choose secret s and small error e
  3. Compute b = A*s + e
  4. Public key = (A, b), Secret key = s

Encryption (simplified):
  1. Choose random r and small errors e1, e2
  2. u = A^T * r + e1
  3. v = b^T * r + e2 + encode(message)
  4. Ciphertext = (u, v)

Decryption:
  1. Compute v - s^T * u = message + (noise terms)
  2. The noise terms are small enough that rounding recovers the message
```

## Hybrid Key Exchange Implementation

```python
\"\"\"
Hybrid PQC key exchange: combines classical ECDH with ML-KEM.

Why hybrid? If lattice-based crypto has an unknown weakness, ECDH provides
a safety net. If quantum computers break ECDH, ML-KEM provides protection.
The combined key is secure as long as EITHER algorithm is secure.
\"\"\"
import os
import hashlib
import hmac
from dataclasses import dataclass
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# Using oqs-python (Open Quantum Safe) for PQC algorithms
# pip install oqs
try:
    import oqs
    PQC_AVAILABLE = True
except ImportError:
    PQC_AVAILABLE = False
    logger.warning("oqs not available — PQC key exchange disabled")

# Using cryptography for classical ECDH
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


@dataclass
class HybridKeyPair:
    \"\"\"Combined classical + PQC key pair.\"\"\"
    ecdh_private: ec.EllipticCurvePrivateKey
    ecdh_public_bytes: bytes
    pqc_public_key: bytes
    pqc_secret_key: bytes  # Only available to key pair owner


@dataclass
class HybridSharedSecret:
    \"\"\"Combined shared secret from hybrid key exchange.\"\"\"
    combined_key: bytes  # 32 bytes — ready for symmetric encryption
    ecdh_component: bytes
    pqc_component: bytes


class HybridKeyExchange:
    \"\"\"
    Hybrid key exchange combining X25519 (ECDH) + ML-KEM-768.

    This follows the approach used by Chrome, Cloudflare, and Signal:
    run BOTH algorithms and combine the shared secrets. The result is
    secure against both classical and quantum adversaries.

    The combination uses HKDF to derive a single key from both secrets,
    ensuring that compromising one algorithm doesn't compromise the key.
    \"\"\"

    PQC_ALGORITHM = "ML-KEM-768"  # NIST Level 3 (192-bit security)

    def __init__(self):
        if not PQC_AVAILABLE:
            raise RuntimeError(
                "oqs library required for PQC. Install with: pip install oqs"
            )
        # Verify algorithm is available
        if self.PQC_ALGORITHM not in oqs.get_enabled_kem_mechanisms():
            available = oqs.get_enabled_kem_mechanisms()
            raise RuntimeError(
                f"{self.PQC_ALGORITHM} not available. "
                f"Available KEMs: {available[:5]}..."
            )

    def generate_keypair(self) -> HybridKeyPair:
        \"\"\"Generate a hybrid key pair (ECDH + ML-KEM).\"\"\"
        # Classical: X25519 (Curve25519 ECDH)
        ecdh_private = ec.generate_private_key(ec.SECP384R1())
        ecdh_public_bytes = ecdh_private.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.CompressedPoint,
        )

        # Post-quantum: ML-KEM-768
        kem = oqs.KeyEncapsulation(self.PQC_ALGORITHM)
        pqc_public_key = kem.generate_keypair()
        pqc_secret_key = kem.export_secret_key()

        logger.info(
            f"Generated hybrid keypair: ECDH={len(ecdh_public_bytes)}B, "
            f"PQC={len(pqc_public_key)}B"
        )

        return HybridKeyPair(
            ecdh_private=ecdh_private,
            ecdh_public_bytes=ecdh_public_bytes,
            pqc_public_key=pqc_public_key,
            pqc_secret_key=pqc_secret_key,
        )

    def encapsulate(
        self,
        recipient_keypair: HybridKeyPair,
        sender_ecdh_private: ec.EllipticCurvePrivateKey,
    ) -> Tuple[bytes, HybridSharedSecret]:
        \"\"\"
        Encapsulate a shared secret for the recipient.

        Returns (ciphertext, shared_secret) where:
        - ciphertext must be sent to the recipient
        - shared_secret is the agreed-upon symmetric key
        \"\"\"
        # Classical ECDH
        recipient_ecdh_public = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP384R1(), recipient_keypair.ecdh_public_bytes,
        )
        ecdh_shared = sender_ecdh_private.exchange(ec.ECDH(), recipient_ecdh_public)

        # PQC encapsulation
        kem = oqs.KeyEncapsulation(self.PQC_ALGORITHM)
        pqc_ciphertext, pqc_shared = kem.encap_secret(recipient_keypair.pqc_public_key)

        # Combine both shared secrets using HKDF
        combined_key = self._combine_secrets(ecdh_shared, pqc_shared)

        return pqc_ciphertext, HybridSharedSecret(
            combined_key=combined_key,
            ecdh_component=ecdh_shared,
            pqc_component=pqc_shared,
        )

    def decapsulate(
        self,
        my_keypair: HybridKeyPair,
        sender_ecdh_public_bytes: bytes,
        pqc_ciphertext: bytes,
    ) -> HybridSharedSecret:
        \"\"\"
        Decapsulate the shared secret using our private key.
        \"\"\"
        # Classical ECDH
        sender_ecdh_public = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP384R1(), sender_ecdh_public_bytes,
        )
        ecdh_shared = my_keypair.ecdh_private.exchange(ec.ECDH(), sender_ecdh_public)

        # PQC decapsulation
        kem = oqs.KeyEncapsulation(self.PQC_ALGORITHM, my_keypair.pqc_secret_key)
        pqc_shared = kem.decap_secret(pqc_ciphertext)

        # Combine
        combined_key = self._combine_secrets(ecdh_shared, pqc_shared)

        return HybridSharedSecret(
            combined_key=combined_key,
            ecdh_component=ecdh_shared,
            pqc_component=pqc_shared,
        )

    def _combine_secrets(
        self,
        ecdh_secret: bytes,
        pqc_secret: bytes,
    ) -> bytes:
        \"\"\"
        Combine classical and PQC shared secrets using HKDF.

        HKDF (HMAC-based Key Derivation Function) ensures that the combined
        key is uniformly random even if one of the input secrets is biased.
        The 'info' field binds the derivation to our specific protocol.
        \"\"\"
        combined_input = ecdh_secret + pqc_secret
        return HKDF(
            algorithm=hashes.SHA384(),
            length=32,  # 256-bit symmetric key
            salt=None,  # Random salt would be better but complicates protocol
            info=b"hybrid-kem-v1",
        ).derive(combined_input)
```

## Testing the Hybrid Key Exchange

```python
import pytest
from hybrid_kem import HybridKeyExchange, HybridSharedSecret


@pytest.fixture
def kem():
    \"\"\"Create hybrid KEM instance.\"\"\"
    return HybridKeyExchange()


def test_key_exchange_produces_matching_secrets(kem):
    \"\"\"Both parties should derive the same shared secret.\"\"\"
    # Alice generates her keypair
    alice = kem.generate_keypair()

    # Bob generates his keypair
    bob = kem.generate_keypair()

    # Alice encapsulates a secret for Bob
    ciphertext, alice_secret = kem.encapsulate(bob, alice.ecdh_private)

    # Bob decapsulates using his private key
    bob_secret = kem.decapsulate(bob, alice.ecdh_public_bytes, ciphertext)

    # Both should have the same combined key
    assert alice_secret.combined_key == bob_secret.combined_key
    assert len(alice_secret.combined_key) == 32  # 256-bit key


def test_different_recipients_get_different_secrets(kem):
    \"\"\"Each recipient should get a unique shared secret.\"\"\"
    sender = kem.generate_keypair()
    recipient1 = kem.generate_keypair()
    recipient2 = kem.generate_keypair()

    _, secret1 = kem.encapsulate(recipient1, sender.ecdh_private)
    _, secret2 = kem.encapsulate(recipient2, sender.ecdh_private)

    assert secret1.combined_key != secret2.combined_key


def test_wrong_private_key_fails(kem):
    \"\"\"Decapsulation with wrong private key should produce different secret.\"\"\"
    alice = kem.generate_keypair()
    bob = kem.generate_keypair()
    eve = kem.generate_keypair()  # Attacker

    ciphertext, alice_secret = kem.encapsulate(bob, alice.ecdh_private)

    # Eve tries to decapsulate with her own key — should get different result
    eve_secret = kem.decapsulate(eve, alice.ecdh_public_bytes, ciphertext)

    assert alice_secret.combined_key != eve_secret.combined_key
```

## Migration Strategy

```
Phase 1: Inventory (NOW)
  - Catalog all cryptographic usage: TLS certificates, API keys, stored encrypted data
  - Identify data with long-term secrecy requirements (>10 years)
  - Priority: data in transit first (harvest-now-decrypt-later threat)

Phase 2: Hybrid deployment (2025-2027)
  - Enable hybrid key exchange in TLS (X25519 + ML-KEM-768)
  - Chrome, Firefox, Cloudflare already support this
  - Backward compatible: clients that don't support PQC fall back to classical

Phase 3: PQC-preferred (2027-2030)
  - Default to PQC algorithms, classical as fallback
  - Re-encrypt stored data with PQC-protected keys
  - Rotate all long-term signing keys to ML-DSA

Phase 4: Classical deprecation (2030+)
  - Remove classical-only cipher suites
  - Depends on quantum computer development timeline
```

## Key Takeaways

The migration to post-quantum cryptography is urgent for **data in transit** because of
harvest-now-decrypt-later attacks, but the timeline for **data at rest** is less critical
because you control when decryption happens. The hybrid approach is recommended because
it provides security against both classical and quantum adversaries — if lattice-based
crypto turns out to have a weakness, ECDH still protects you, and vice versa.

The trade-off is increased key and ciphertext sizes: ML-KEM-768 public keys are ~1184 bytes
versus 32 bytes for X25519. For TLS handshakes this adds ~1-2KB per connection — negligible
for most applications but significant for IoT devices with constrained bandwidth.
"""
    ),
]
