"""Software supply chain security -- SBOM, dependency scanning, image signing, SLSA provenance."""

PAIRS = [
    (
        "security/sbom-generation",
        "Show how to generate Software Bill of Materials (SBOM) in CycloneDX and SPDX formats for Python projects, containers, and CI/CD pipelines.",
        '''# --- Generate CycloneDX SBOM programmatically ---

from typing import Optional
from datetime import datetime, timezone
from pathlib import Path
import json
import uuid

from cyclonedx.model.bom import Bom
from cyclonedx.model.component import Component, ComponentType
from cyclonedx.model import (
    ExternalReference, ExternalReferenceType,
    HashAlgorithm, HashType,
    License, LicenseChoice,
    OrganizationalEntity,
    Property,
    Tool,'''
    ),
    (
        "permissive",
        "} for comp in components: for lic in comp.licenses: if lic in COPYLEFT_LICENSES: issues['copyleft'].append(f'{comp.name}@{comp.version} ({lic})') elif lic in UNKNOWN_RISK: issues['unknown'].append(f'{comp.name}@{comp.version}') else: issues['permissive'].append(f'{comp.name}@{comp.version} ({lic})') return issues",
        '''| SBOM Format | Standard | Ecosystem | Primary Use |
|---|---|---|---|
| CycloneDX | OWASP | Security-focused | Vulnerability management, compliance |
| SPDX | Linux Foundation | License-focused | License compliance, legal review |
| SWID | ISO/IEC 19770-2 | Enterprise | Asset management |

| Generation Tool | Input Sources | Output Formats | Best For |
|---|---|---|---|
| cyclonedx-bom | pip, Poetry, Pipenv | CycloneDX JSON/XML | Python projects |
| Syft (Anchore) | Images, dirs, archives | CycloneDX, SPDX | Container images |
| Trivy | Images, filesystems, repos | CycloneDX, SPDX | Combined SBOM + vuln scan |
| spdx-tools | Multiple | SPDX JSON/RDF/TV | SPDX-specific workflows |

Key patterns:

1. **Generate at build time** -- produce SBOM during CI/CD, not retroactively
2. **Include PURLs** -- Package URLs enable cross-tool vulnerability correlation
3. **CycloneDX 1.5+** -- latest spec supports formulation, licensing, and services
4. **Attest SBOMs** -- sign SBOMs with Sigstore for tamper-proof provenance
5. **License audit** -- scan SBOM for copyleft and unknown licenses before release
6. **Container + source** -- generate separate SBOMs for source dependencies and container contents
7. **Schema validation** -- always validate SBOM format before publishing'''
    ),
    (
        "security/dependency-scanning",
        "Show dependency scanning and vulnerability detection with Dependabot, Trivy, pip-audit, and Safety with CI/CD integration and remediation workflows.",
        '''# --- Dependabot configuration (.github/dependabot.yml) ---

version: 2
updates:
  # Python pip dependencies
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "06:00"
      timezone: "America/New_York"
    open-pull-requests-limit: 10
    reviewers:
      - "security-team"
    labels:
      - "dependencies"
      - "security"
    # Group minor/patch updates to reduce PR noise
    groups:
      production-deps:
        patterns:
          - "fastapi*"
          - "uvicorn*"
          - "sqlalchemy*"
        update-types:
          - "minor"
          - "patch"
      dev-deps:
        patterns:
          - "pytest*"
          - "mypy*"
          - "ruff*"
    # Ignore known-safe major version locks
    ignore:
      - dependency-name: "boto3"
        update-types: ["version-update:semver-major"]
    # Security updates have higher priority
    security-updates:
      enabled: true

  # Docker base images
  - package-ecosystem: "docker"
    directory: "/"
    schedule:
      interval: "weekly"
    labels:
      - "docker"
      - "dependencies"

  # GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    labels:
      - "ci"
      - "dependencies"
```

```python
# --- Automated vulnerability scanning with pip-audit and Safety ---

import subprocess
import json
import sys
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import logging

logger = logging.getLogger("security.deps")


@dataclass
class Vulnerability:
    package: str
    installed_version: str
    fixed_version: Optional[str]
    vuln_id: str  # CVE or advisory ID
    severity: str  # critical, high, medium, low
    description: str
    source: str    # pip-audit, safety, trivy


class DependencyScanner:
    """Unified dependency vulnerability scanner."""

    def __init__(self, project_dir: Path = Path(".")) -> None:
        self.project_dir = project_dir
        self.vulnerabilities: list[Vulnerability] = []

    def scan_pip_audit(self) -> list[Vulnerability]:
        """Scan with pip-audit (uses OSV and PyPI advisory DB)."""
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m", "pip_audit",'''
    ),
    (
        "--exit-code",
        "str(self.project_dir) ] capture_output=True text=True ) except FileNotFoundError: logger.warning('trivy not installed; skipping') return [] vulns = [] if result.stdout: data = json.loads(result.stdout) for res in data.get('Results', []): for vuln_data in res.get('Vulnerabilities', []): v = Vulnerability( package=vuln_data.get('PkgName', '') installed_version=vuln_data.get('InstalledVersion', '') fixed_version=vuln_data.get('FixedVersion') vuln_id=vuln_data.get('VulnerabilityID', '') severity=vuln_data.get('Severity', 'UNKNOWN').lower() description=vuln_data.get('Title', '')[:200] source='trivy' ) vulns.append(v) self.vulnerabilities.extend(vulns) return vulns def generate_report(self) -> dict:",
        '''seen = set()
        unique_vulns = []
        for v in self.vulnerabilities:
            key = (v.package, v.vuln_id)
            if key not in seen:
                seen.add(key)
                unique_vulns.append(v)

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        unique_vulns.sort(key=lambda v: severity_order.get(v.severity, 4))

        report = {'''
    ),
    (
        "source",
        "}) return report @staticmethod def _map_severity(vuln_id: str) -> str:",
        '''return "high"  # Default to high for safety


# Usage
from datetime import datetime, timezone

scanner = DependencyScanner(Path("."))
scanner.scan_pip_audit()
scanner.scan_trivy_filesystem()
report = scanner.generate_report()
print(json.dumps(report, indent=2))
```

```yaml
# --- CI/CD: multi-scanner pipeline ---
# GitHub Actions

name: Dependency Security Scan
on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: "0 6 * * 1"  # Weekly Monday 6am

jobs:
  scan:
    runs-on: ubuntu-latest
    permissions:
      security-events: write  # For SARIF upload

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r requirements.txt

      # pip-audit scan
      - name: pip-audit scan
        run: |
          pip install pip-audit
          pip-audit --format json --output pip-audit-results.json || true
          pip-audit --format cyclonedx-json --output pip-audit-sbom.cdx.json || true

      # Trivy filesystem scan
      - name: Trivy filesystem scan
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: "fs"
          scan-ref: "."
          format: "sarif"
          output: "trivy-fs-results.sarif"
          severity: "CRITICAL,HIGH"

      # Trivy container scan (if Dockerfile exists)
      - name: Build image for scanning
        if: hashFiles('Dockerfile') != ''
        run: docker build -t scan-target:latest .

      - name: Trivy image scan
        if: hashFiles('Dockerfile') != ''
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: "scan-target:latest"
          format: "sarif"
          output: "trivy-image-results.sarif"
          severity: "CRITICAL,HIGH"

      # Upload results to GitHub Security tab
      - name: Upload Trivy SARIF
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: "trivy-fs-results.sarif"
          category: "trivy-filesystem"

      # Fail on critical vulnerabilities
      - name: Check for critical vulnerabilities
        run: |
          python -c "
          import json, sys
          with open('pip-audit-results.json') as f:
              data = json.load(f)
          vulns = [d for d in data.get('dependencies', []) if d.get('vulns')]
          critical = [v for d in vulns for v in d['vulns']
                      if 'CRITICAL' in str(v).upper()]
          if critical:
              print(f'CRITICAL vulnerabilities found: {len(critical)}')
              for c in critical:
                  print(f'  - {c}')
              sys.exit(1)
          print('No critical vulnerabilities found')
          "
```

| Scanner | Database | Formats | Languages | Speed |
|---|---|---|---|---|
| pip-audit | OSV + PyPI | JSON, CycloneDX | Python only | Fast |
| Safety | Safety DB | JSON, text | Python only | Fast |
| Trivy | NVD, OSV, GHSA | JSON, SARIF, CycloneDX | Multi-language | Medium |
| Dependabot | GHSA | Pull requests | Multi-language | Background |
| Grype (Anchore) | NVD, GHSA | JSON, SARIF, CycloneDX | Multi-language | Medium |
| Snyk | Snyk DB | JSON, SARIF | Multi-language | Medium |

Key patterns:

1. **Multi-scanner approach** -- use pip-audit + Trivy for defense in depth across different vuln databases
2. **SARIF output** -- upload to GitHub Security tab for centralized vulnerability tracking
3. **Fail on critical** -- block PRs with critical vulns, allow merge with medium/low as tracked issues
4. **Weekly schedule** -- run scans on a schedule even without code changes (new CVEs appear daily)
5. **Dependabot groups** -- group minor/patch updates to reduce PR noise while staying current
6. **Pin GitHub Actions** -- use commit SHAs instead of tags to prevent supply chain attacks on CI
7. **Auto-remediation** -- Dependabot creates PRs with version bumps for known fixes'''
    ),
    (
        "security/container-image-signing",
        "Show container image signing and verification with cosign (Sigstore) including keyless signing, SBOM attestation, and admission control in Kubernetes.",
        '''# --- cosign: sign container images ---

# Install cosign
# go install github.com/sigstore/cosign/v2/cmd/cosign@latest
# or: brew install cosign

# 1. Keyless signing (recommended) - uses OIDC identity via Fulcio
#    Works with GitHub Actions, GitLab CI, and local OIDC providers
cosign sign ghcr.io/myorg/api-service:v2.1.0

# This triggers an OIDC flow:
# - Opens browser for identity verification
# - Fulcio issues a short-lived certificate
# - Rekor records the signature in a transparency log
# - No long-lived keys to manage!

# 2. Key-based signing (for air-gapped environments)
cosign generate-key-pair
# Creates cosign.key (private, password-protected) and cosign.pub (public)

cosign sign --key cosign.key ghcr.io/myorg/api-service:v2.1.0
# Stores signature as an OCI artifact alongside the image

# 3. Sign with annotations (add metadata to signatures)
cosign sign \
  --key cosign.key \
  -a "git.sha=$(git rev-parse HEAD)" \
  -a "ci.build=$(echo $GITHUB_RUN_ID)" \
  -a "sbom=true" \
  ghcr.io/myorg/api-service:v2.1.0

# 4. Verify signatures
cosign verify \
  --key cosign.pub \
  ghcr.io/myorg/api-service:v2.1.0

# Keyless verification (checks Fulcio certificate + Rekor log)
cosign verify \
  --certificate-identity "https://github.com/myorg/api-service/.github/workflows/build.yml@refs/heads/main" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  ghcr.io/myorg/api-service:v2.1.0

# 5. Attach and sign SBOM
cosign attach sbom --sbom sbom.cdx.json ghcr.io/myorg/api-service:v2.1.0
cosign sign --key cosign.key --attachment sbom ghcr.io/myorg/api-service:v2.1.0

# 6. Attest (in-toto attestation with SBOM as predicate)
cosign attest \
  --key cosign.key \
  --predicate sbom.cdx.json \
  --type cyclonedx \
  ghcr.io/myorg/api-service:v2.1.0

# Verify attestation
cosign verify-attestation \
  --key cosign.pub \
  --type cyclonedx \
  ghcr.io/myorg/api-service:v2.1.0
```

```yaml
# --- GitHub Actions: build, sign, and attest container images ---

name: Build, Sign, and Attest
on:
  push:
    tags: ["v*"]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-sign:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write   # Required for keyless signing

    steps:
      - uses: actions/checkout@v4

      - name: Install cosign
        uses: sigstore/cosign-installer@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=semver,pattern={{version}}
            type=sha

      - name: Build and push
        id: build
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}

      - name: Generate SBOM
        uses: anchore/sbom-action@v0
        with:
          image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}
          format: cyclonedx-json
          output-file: sbom.cdx.json

      # Keyless signing with GitHub OIDC
      - name: Sign image
        env:
          DIGEST: ${{ steps.build.outputs.digest }}
        run: |
          cosign sign --yes \
            -a "git.sha=${{ github.sha }}" \
            -a "git.ref=${{ github.ref }}" \
            -a "ci.run=${{ github.run_id }}" \
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${DIGEST}

      # Attest SBOM
      - name: Attest SBOM
        env:
          DIGEST: ${{ steps.build.outputs.digest }}
        run: |
          cosign attest --yes \
            --predicate sbom.cdx.json \
            --type cyclonedx \
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${DIGEST}

      # Attest SLSA provenance
      - name: Generate provenance
        uses: slsa-framework/slsa-github-generator/.github/workflows/generator_container_slsa3.yml@v2.0.0
        with:
          image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          digest: ${{ steps.build.outputs.digest }}
```

```yaml
# --- Kubernetes admission control with Kyverno ---
# Enforce image signatures before pods can be created

apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-image-signatures
  annotations:
    policies.kyverno.io/title: Verify Image Signatures
    policies.kyverno.io/description: >
      Require all container images to be signed with cosign
      and have a valid SBOM attestation.
spec:
  validationFailureAction: Enforce  # Block unsigned images
  background: false
  rules:
    # Rule 1: Verify image signature
    - name: verify-signature
      match:
        any:
          - resources:
              kinds: ["Pod"]
              namespaces: ["production", "staging"]
      verifyImages:
        - imageReferences:
            - "ghcr.io/myorg/*"
          attestors:
            - entries:
                - keyless:
                    subject: "https://github.com/myorg/*"
                    issuer: "https://token.actions.githubusercontent.com"
                    rekor:
                      url: "https://rekor.sigstore.dev"
          # Also verify required annotations
          mutateDigest: true    # Replace tags with digests
          verifyDigest: true    # Ensure digest matches

    # Rule 2: Require SBOM attestation
    - name: require-sbom
      match:
        any:
          - resources:
              kinds: ["Pod"]
              namespaces: ["production"]
      verifyImages:
        - imageReferences:
            - "ghcr.io/myorg/*"
          attestations:
            - type: "https://cyclonedx.org/bom"
              attestors:
                - entries:
                    - keyless:
                        subject: "https://github.com/myorg/*"
                        issuer: "https://token.actions.githubusercontent.com"
              conditions:
                - all:
                    # Ensure SBOM has components (not empty)
                    - key: "{{ components | length(@) }}"
                      operator: GreaterThan
                      value: "0"

---
# --- Alternative: Sigstore Policy Controller ---

apiVersion: policy.sigstore.dev/v1beta1
kind: ClusterImagePolicy
metadata:
  name: require-signed-images
spec:
  images:
    - glob: "ghcr.io/myorg/**"
  authorities:
    - keyless:
        identities:
          - issuer: "https://token.actions.githubusercontent.com"
            subjectRegExp: "https://github.com/myorg/.*"
        ctlog:
          url: "https://rekor.sigstore.dev"
```

```python
# --- Programmatic signature verification with cosign/sigstore ---

import subprocess
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class SignatureVerification:
    verified: bool
    signer_identity: Optional[str]
    issuer: Optional[str]
    annotations: dict[str, str]
    transparency_log_index: Optional[int]


def verify_image_signature(
    image_ref: str,
    expected_identity: str | None = None,
    expected_issuer: str | None = None,
    public_key: str | None = None,
) -> SignatureVerification:
    """Verify container image signature using cosign."""
    cmd = ["cosign", "verify", "--output-text"]

    if public_key:
        cmd.extend(["--key", public_key])
    else:
        # Keyless verification
        if expected_identity:
            cmd.extend(["--certificate-identity-regexp", expected_identity])
        if expected_issuer:
            cmd.extend(["--certificate-oidc-issuer", expected_issuer])

    cmd.append(image_ref)

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        return SignatureVerification(
            verified=False,
            signer_identity=None,
            issuer=None,
            annotations={},
            transparency_log_index=None,'''
    ),
    (
        "LogIndex",
        ") ) except (json.JSONDecodeError, IndexError): return SignatureVerification( verified=True signer_identity=None issuer=None annotations={} transparency_log_index=None )",
        '''| Signing Method | Key Management | Identity Proof | Transparency | Best For |
|---|---|---|---|---|
| Keyless (Sigstore) | None (ephemeral) | OIDC (GitHub, Google) | Rekor log | CI/CD pipelines |
| Key-based (cosign) | Manual (cosign.key) | Key possession | Optional Rekor | Air-gapped environments |
| Notation (CNCF) | Key vault (Azure, AWS) | Key + trust policy | Optional | Cloud-native environments |

Key patterns:

1. **Keyless preferred** -- Sigstore keyless signing eliminates key management via OIDC + Fulcio + Rekor
2. **Sign by digest** -- always reference images by digest (`@sha256:...`), never by mutable tags
3. **SBOM attestation** -- attach SBOM as in-toto attestation alongside the image signature
4. **Admission control** -- enforce signatures with Kyverno or Sigstore Policy Controller in K8s
5. **Mutate to digest** -- Kyverno's `mutateDigest: true` replaces tags with verified digests
6. **CI identity** -- use GitHub Actions OIDC as the signing identity for full provenance
7. **Defense in depth** -- sign images, attest SBOMs, verify at admission, and audit in runtime'''
    ),
    (
        "security/reproducible-builds-slsa",
        "Explain reproducible builds and SLSA (Supply-chain Levels for Software Artifacts) provenance with practical implementation using GitHub Actions and SLSA framework.",
        '''┌──────────────────────────────────────────────────────────┐
│                    SLSA Levels                            │
│                                                           │
│  Level 0: No guarantees                                   │
│  Level 1: Build process documented                        │
│           + Provenance generated                          │
│                                                           │
│  Level 2: Hosted build service                            │
│           + Signed provenance                             │
│           + Build service generates provenance            │
│                                                           │
│  Level 3: Hardened build platform                         │
│           + Non-forgeable provenance                      │
│           + Isolated, ephemeral build environments        │
│           + Prevents insider threats                      │
│                                                           │
│  Level 4: Hermetic, reproducible builds (aspirational)    │
│           + Two-party review of all changes               │
│           + Reproducible build process                    │
└──────────────────────────────────────────────────────────┘
```

```yaml
# --- SLSA Level 3 provenance with GitHub Actions ---

name: SLSA Build and Provenance
on:
  push:
    tags: ["v*"]

jobs:
  # Step 1: Build the artifact
  build:
    runs-on: ubuntu-latest
    outputs:
      digest: ${{ steps.hash.outputs.digest }}
      artifact-name: ${{ steps.build.outputs.name }}

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Build wheel
        id: build
        run: |
          pip install build
          python -m build --wheel --outdir dist/
          WHEEL=$(ls dist/*.whl)
          echo "name=$(basename $WHEEL)" >> $GITHUB_OUTPUT

      - name: Compute digest
        id: hash
        run: |
          WHEEL=$(ls dist/*.whl)
          DIGEST=$(sha256sum "$WHEEL" | cut -d' ' -f1)
          echo "digest=sha256:$DIGEST" >> $GITHUB_OUTPUT

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: python-wheel
          path: dist/*.whl

  # Step 2: Generate SLSA provenance
  provenance:
    needs: build
    permissions:
      actions: read      # For reading workflow info
      id-token: write    # For signing provenance
      contents: write    # For uploading to release
    uses: slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@v2.0.0
    with:
      base64-subjects: |
        ${{ needs.build.outputs.digest }} ${{ needs.build.outputs.artifact-name }}

  # Step 3: Verify provenance (optional verification step)
  verify:
    needs: [build, provenance]
    runs-on: ubuntu-latest
    steps:
      - name: Download artifact
        uses: actions/download-artifact@v4
        with:
          name: python-wheel

      - name: Download provenance
        uses: actions/download-artifact@v4
        with:
          name: ${{ needs.provenance.outputs.provenance-name }}

      - name: Install slsa-verifier
        uses: slsa-framework/slsa-verifier/actions/installer@v2.5.1

      - name: Verify provenance
        run: |
          slsa-verifier verify-artifact \
            *.whl \
            --provenance-path ${{ needs.provenance.outputs.provenance-name }} \
            --source-uri "github.com/${{ github.repository }}" \
            --source-tag "${{ github.ref_name }}"
```

```python
# --- Reproducible Python builds with locked dependencies ---

# pyproject.toml configuration for reproducible builds
"""
[build-system]
requires = ["hatchling>=1.21.0"]
build-backend = "hatchling.build"

[project]
name = "my-api-service"
version = "2.1.0"
requires-python = ">=3.11"

dependencies = [
    "fastapi==0.109.2",
    "uvicorn[standard]==0.27.1",
    "sqlalchemy==2.0.27",
    "pydantic==2.6.1",
]

[tool.hatch.build.targets.wheel]
# Reproducible builds: exclude variable metadata
reproducible = true
"""
```

```python
# --- Build reproducibility checker ---

import hashlib
import subprocess
import json
import tempfile
from pathlib import Path
from dataclasses import dataclass


@dataclass
class BuildResult:
    artifact_path: Path
    sha256_digest: str
    build_metadata: dict


def reproducible_build(
    source_dir: Path,
    build_count: int = 2,
) -> tuple[bool, list[BuildResult]]:
    """
    Verify build reproducibility by building multiple times
    and comparing artifact digests.
    """
    results: list[BuildResult] = []

    for i in range(build_count):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set deterministic environment variables
            env = {'''
    ),
    (
        "source_date_epoch",
        "} ))",
        '''digests = {r.sha256_digest for r in results}
    is_reproducible = len(digests) == 1

    if not is_reproducible:
        import logging
        logging.warning(
            f"Non-reproducible build! Got {len(digests)} different digests: "
            f"{[r.sha256_digest[:16] for r in results]}"'''
    ),
    (
        "errors",
        "}",
        '''REPRODUCIBLE_DOCKERFILE = """
# syntax=docker/dockerfile:1

# Pin base image by digest (not tag)
FROM python:3.12-slim@sha256:abc123... AS builder

# Set reproducibility environment
ENV SOURCE_DATE_EPOCH=1709510400 \\
    PYTHONDONTWRITEBYTECODE=1 \\
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy only dependency files first (cache layer)
COPY requirements.txt .
RUN pip install --no-compile -r requirements.txt

# Copy source
COPY . .

# Build wheel
RUN python -m build --wheel --outdir /dist

# Runtime stage
FROM python:3.12-slim@sha256:abc123...

ENV PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Non-root user
RUN useradd -r -s /bin/false appuser
USER appuser

ENTRYPOINT ["python", "-m", "my_api_service"]
"""
```

| SLSA Level | Requirements | Protection Against |
|---|---|---|
| Level 0 | None | Nothing |
| Level 1 | Provenance exists | Mistakes, after-the-fact analysis |
| Level 2 | Hosted build + signed provenance | Tampering after build |
| Level 3 | Hardened platform + non-forgeable provenance | Insider threats, build compromise |
| Level 4 | Hermetic + reproducible | All supply chain attacks |

| Reproducibility Factor | Problem | Solution |
|---|---|---|
| Timestamps | File modification times vary | SOURCE_DATE_EPOCH |
| Filesystem order | Directory listing non-deterministic | Sort entries in build scripts |
| Hash randomization | Python dict ordering varies | PYTHONHASHSEED=0 |
| Base images | Mutable tags change | Pin by digest (@sha256:...) |
| Dependencies | Version ranges resolve differently | Lock files (pip-compile, poetry.lock) |
| Build tools | Tool versions differ | Pin build-system in pyproject.toml |

Key patterns:

1. **SLSA Level 3** -- use slsa-github-generator for non-forgeable provenance in GitHub Actions
2. **Pin by digest** -- reference base images and dependencies by hash, never mutable tags
3. **SOURCE_DATE_EPOCH** -- set a fixed timestamp for reproducible file metadata in archives
4. **Lock dependencies** -- use pip-compile or poetry.lock for fully resolved dependency versions
5. **Verify provenance** -- use slsa-verifier to check artifact provenance before deployment
6. **Multi-build check** -- build the same source twice and compare digests to verify reproducibility
7. **Ephemeral builders** -- use fresh, isolated build environments to prevent cross-build contamination'''
    ),
]
