"""Container security — scanning, runtime protection, supply chain security, and compliance."""

PAIRS = [
    (
        "security/supply-chain-security",
        "Show software supply chain security: dependency scanning, SBOM generation, signed artifacts, and SLSA framework.",
        '''Software supply chain security patterns:

```yaml
# --- GitHub Actions: Full supply chain pipeline ---
name: Secure Build Pipeline
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  security-events: write
  packages: write
  id-token: write  # For OIDC signing

jobs:
  # Step 1: Dependency scanning
  dependency-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Dependabot/Snyk vulnerability scan
        uses: snyk/actions/python@master
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
        with:
          args: --severity-threshold=high

      - name: Check for known vulnerabilities
        run: |
          pip install pip-audit
          pip-audit -r requirements.txt --strict --desc

      - name: License compliance check
        run: |
          pip install pip-licenses
          pip-licenses --fail-on="GPL-3.0;AGPL-3.0" --format=json > licenses.json

  # Step 2: Static analysis
  sast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Bandit (Python security linter)
        run: |
          pip install bandit
          bandit -r src/ -f json -o bandit-report.json || true

      - name: Run Semgrep
        uses: semgrep/semgrep-action@v1
        with:
          config: >-
            p/python
            p/owasp-top-ten
            p/security-audit

      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: semgrep.sarif

  # Step 3: Build with provenance
  build:
    needs: [dependency-scan, sast]
    runs-on: ubuntu-latest
    outputs:
      digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        id: build
        uses: docker/build-push-action@v5
        with:
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          provenance: true    # SLSA provenance
          sbom: true          # SBOM generation

      - name: Generate SBOM
        uses: anchore/sbom-action@v0
        with:
          image: ghcr.io/${{ github.repository }}:${{ github.sha }}
          format: spdx-json
          output-file: sbom.spdx.json

      - name: Sign image with Cosign
        uses: sigstore/cosign-installer@v3
      - run: |
          cosign sign --yes \
            ghcr.io/${{ github.repository }}@${{ steps.build.outputs.digest }}

  # Step 4: Image scanning
  scan:
    needs: [build]
    runs-on: ubuntu-latest
    steps:
      - name: Run Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ghcr.io/${{ github.repository }}:${{ github.sha }}
          format: sarif
          output: trivy.sarif
          severity: CRITICAL,HIGH
          exit-code: 1
```

```python
# --- SBOM verification in deployment ---

import subprocess
import json

def verify_deployment_artifact(image: str, expected_digest: str):
    """Verify image signature and SBOM before deployment."""

    # 1. Verify image signature
    result = subprocess.run(
        ["cosign", "verify", "--certificate-identity-regexp", ".*",
         "--certificate-oidc-issuer", "https://token.actions.githubusercontent.com",
         image],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SecurityError(f"Image signature verification failed: {result.stderr}")

    # 2. Verify digest matches
    result = subprocess.run(
        ["crane", "digest", image],
        capture_output=True, text=True,
    )
    actual_digest = result.stdout.strip()
    if actual_digest != expected_digest:
        raise SecurityError(
            f"Digest mismatch: expected {expected_digest}, got {actual_digest}"
        )

    # 3. Check SBOM for critical vulnerabilities
    result = subprocess.run(
        ["grype", image, "-o", "json", "--fail-on", "critical"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        vulns = json.loads(result.stdout)
        critical = [v for v in vulns.get("matches", [])
                    if v["vulnerability"]["severity"] == "Critical"]
        raise SecurityError(
            f"Critical vulnerabilities found: {len(critical)}"
        )

    return True
```

SLSA framework levels:
1. **Level 1** — documented build process, provenance exists
2. **Level 2** — hosted build, signed provenance
3. **Level 3** — hardened build platform, non-falsifiable provenance
4. **Level 4** — two-person review, hermetic builds

Supply chain checklist:
1. **Pin dependencies** — exact versions + hash verification
2. **Scan regularly** — Dependabot, Snyk, pip-audit for known CVEs
3. **Sign artifacts** — cosign/sigstore for container images
4. **Generate SBOM** — know what's in your deliverables
5. **Verify before deploy** — check signatures and scan results'''
    ),
    (
        "security/runtime-security",
        "Show container runtime security: seccomp profiles, AppArmor, OPA/Gatekeeper policies, and Kubernetes admission control.",
        '''Container runtime security and policy enforcement:

```yaml
# --- Kubernetes Pod Security Standards ---
# Enforce restricted security context

apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/audit: restricted

---
# Pod that passes restricted policy
apiVersion: v1
kind: Pod
metadata:
  name: secure-app
  namespace: production
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: registry.example.com/app:v1.2.0@sha256:abc123
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      resources:
        limits:
          cpu: "1"
          memory: "512Mi"
        requests:
          cpu: "250m"
          memory: "256Mi"
      volumeMounts:
        - name: tmp
          mountPath: /tmp
  volumes:
    - name: tmp
      emptyDir:
        sizeLimit: 100Mi
  automountServiceAccountToken: false

---
# --- OPA Gatekeeper policies ---

# Require resource limits on all containers
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8srequiredresources
spec:
  crd:
    spec:
      names:
        kind: K8sRequiredResources
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8srequiredresources

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not container.resources.limits.memory
          msg := sprintf("Container %v must have memory limits", [container.name])
        }

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not container.resources.limits.cpu
          msg := sprintf("Container %v must have CPU limits", [container.name])
        }

---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequiredResources
metadata:
  name: require-resource-limits
spec:
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Pod"]
    namespaces: ["production"]

---
# Block latest tag
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8sdisallowedtags
spec:
  crd:
    spec:
      names:
        kind: K8sDisallowedTags
      validation:
        openAPIV3Schema:
          type: object
          properties:
            tags:
              type: array
              items:
                type: string
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8sdisallowedtags

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          tag := [t | t := input.parameters.tags[_]; endswith(container.image, concat(":", ["", t]))]
          count(tag) > 0
          msg := sprintf("Container %v uses disallowed tag", [container.name])
        }

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not contains(container.image, ":")
          msg := sprintf("Container %v must specify image tag", [container.name])
        }

---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sDisallowedTags
metadata:
  name: no-latest-tag
spec:
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Pod"]
  parameters:
    tags: ["latest"]
```

Security layers:
1. **Pod Security Standards** — enforce `restricted` policy in production namespaces
2. **Seccomp** — limit syscalls containers can make (RuntimeDefault minimum)
3. **Read-only filesystem** — prevent runtime modification of container
4. **Drop all capabilities** — remove Linux capabilities not needed
5. **OPA Gatekeeper** — policy-as-code for admission control
6. **Image pinning** — use digest (`@sha256:...`) not just tags'''
    ),
    (
        "security/secrets-management",
        "Show secrets management patterns: HashiCorp Vault integration, Kubernetes secrets, rotation, and zero-trust access.",
        '''Secrets management patterns for production:

```python
# --- HashiCorp Vault integration ---

import hvac
from functools import lru_cache
from typing import Optional
import os

class VaultClient:
    """Vault client with AppRole authentication."""

    def __init__(self, url: str = None, role_id: str = None,
                 secret_id: str = None):
        self.url = url or os.environ["VAULT_ADDR"]
        self.client = hvac.Client(url=self.url)

        # AppRole authentication
        if role_id and secret_id:
            auth = self.client.auth.approle.login(
                role_id=role_id, secret_id=secret_id
            )
            self.client.token = auth["auth"]["client_token"]
        elif os.environ.get("VAULT_TOKEN"):
            self.client.token = os.environ["VAULT_TOKEN"]

    def get_secret(self, path: str, key: str = None) -> dict | str:
        """Read secret from KV v2 engine."""
        response = self.client.secrets.kv.v2.read_secret_version(
            path=path, mount_point="secret"
        )
        data = response["data"]["data"]
        return data[key] if key else data

    def get_database_credentials(self, role: str) -> dict:
        """Get dynamic database credentials."""
        response = self.client.secrets.database.generate_credentials(
            name=role
        )
        return {
            "username": response["data"]["username"],
            "password": response["data"]["password"],
            "ttl": response["lease_duration"],
            "lease_id": response["lease_id"],
        }

    def encrypt(self, plaintext: str, key_name: str = "app") -> str:
        """Encrypt using Vault Transit engine."""
        import base64
        encoded = base64.b64encode(plaintext.encode()).decode()
        response = self.client.secrets.transit.encrypt_data(
            name=key_name, plaintext=encoded
        )
        return response["data"]["ciphertext"]

    def decrypt(self, ciphertext: str, key_name: str = "app") -> str:
        """Decrypt using Vault Transit engine."""
        import base64
        response = self.client.secrets.transit.decrypt_data(
            name=key_name, ciphertext=ciphertext
        )
        return base64.b64decode(response["data"]["plaintext"]).decode()


# --- Kubernetes External Secrets ---

EXTERNAL_SECRET_MANIFEST = """
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: api-secrets
  namespace: production
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: api-secrets
    creationPolicy: Owner
  data:
    - secretKey: database-url
      remoteRef:
        key: secret/data/production/database
        property: url
    - secretKey: api-key
      remoteRef:
        key: secret/data/production/api
        property: key
"""

# --- Secret rotation ---

class SecretRotator:
    """Rotate secrets with zero-downtime."""

    def __init__(self, vault: VaultClient, notify_fn=None):
        self.vault = vault
        self.notify = notify_fn

    async def rotate_database_password(self, path: str):
        """Rotate DB password: update Vault, then update service."""
        import secrets as sec

        # Generate new password
        new_password = sec.token_urlsafe(32)

        # Update in Vault
        current = self.vault.get_secret(path)
        current["password"] = new_password
        self.vault.client.secrets.kv.v2.create_or_update_secret(
            path=path, secret=current, mount_point="secret"
        )

        # Trigger service reload
        if self.notify:
            await self.notify("secret_rotated", {"path": path})

    async def rotate_api_key(self, path: str, service_updater=None):
        """Dual-key rotation for zero-downtime."""
        import secrets as sec

        current = self.vault.get_secret(path)

        # Move current key to secondary
        current["secondary_key"] = current.get("primary_key", "")
        current["primary_key"] = sec.token_urlsafe(48)

        self.vault.client.secrets.kv.v2.create_or_update_secret(
            path=path, secret=current, mount_point="secret"
        )

        # Update external service with new key
        if service_updater:
            await service_updater(current["primary_key"])

        # Both keys valid during transition period
        return current["primary_key"]
```

Secrets hierarchy:
1. **Vault/KMS** — centralized secrets with audit trail, dynamic credentials
2. **External Secrets Operator** — sync Vault secrets to K8s automatically
3. **Kubernetes Secrets** — encrypted at rest (etcd encryption), RBAC-controlled
4. **Environment variables** — injected at runtime, never in images
5. **Never** — hardcoded in code, committed to git, in Docker layers'''
    ),
]
