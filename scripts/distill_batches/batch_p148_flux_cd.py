"""Flux CD — GitOps continuous delivery for Kubernetes."""

PAIRS = [
    (
        "devops/flux-cd-gitops",
        "Show Flux CD GitOps patterns: source controllers, kustomization, HelmRelease, image automation, and multi-tenant setup.",
        '''Flux CD GitOps for Kubernetes:

```yaml
# --- Bootstrap: install Flux into cluster ---
# flux bootstrap github \
#   --owner=myorg --repository=fleet-infra \
#   --branch=main --path=./clusters/production \
#   --personal

# --- Directory structure ---
# fleet-infra/
# ├── clusters/
# │   ├── production/
# │   │   ├── flux-system/         # Auto-generated Flux components
# │   │   ├── infrastructure.yaml  # Kustomization for infra
# │   │   └── apps.yaml            # Kustomization for apps
# │   └── staging/
# │       ├── infrastructure.yaml
# │       └── apps.yaml
# ├── infrastructure/
# │   ├── sources/                 # Git/Helm/OCI repositories
# │   ├── configs/                 # Shared configs (cert-manager, ingress)
# │   └── monitoring/             # Prometheus, Grafana
# └── apps/
#     ├── base/                    # Base manifests
#     ├── production/              # Production overlays
#     └── staging/                 # Staging overlays


# === Source Controllers ===

# --- GitRepository source ---
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: fleet-infra
  namespace: flux-system
spec:
  interval: 5m
  url: https://github.com/myorg/fleet-infra
  ref:
    branch: main
  secretRef:
    name: flux-system  # GitHub deploy key
  ignore: |
    # Exclude non-deployment files
    /*
    !/clusters
    !/infrastructure
    !/apps

---
# --- HelmRepository source ---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: bitnami
  namespace: flux-system
spec:
  interval: 30m
  url: https://charts.bitnami.com/bitnami
  type: default  # or "oci" for OCI registries

---
# --- OCI Repository (container registry as source) ---
apiVersion: source.toolkit.fluxcd.io/v1beta2
kind: OCIRepository
metadata:
  name: app-manifests
  namespace: flux-system
spec:
  interval: 5m
  url: oci://ghcr.io/myorg/app-manifests
  ref:
    tag: latest
  provider: generic  # or "aws", "gcp", "azure" for cloud auth


# === Kustomization (deployment pipeline) ===

---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: infrastructure
  namespace: flux-system
spec:
  interval: 10m
  retryInterval: 2m
  timeout: 5m
  sourceRef:
    kind: GitRepository
    name: fleet-infra
  path: ./infrastructure
  prune: true                    # Delete resources removed from git
  wait: true                     # Wait for resources to be ready
  healthChecks:
    - apiVersion: apps/v1
      kind: Deployment
      name: ingress-nginx-controller
      namespace: ingress-nginx

---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: apps
  namespace: flux-system
spec:
  interval: 10m
  sourceRef:
    kind: GitRepository
    name: fleet-infra
  path: ./apps/production
  prune: true
  dependsOn:
    - name: infrastructure       # Apps deploy after infra is ready
  patches:                       # Inline patches for environment-specific config
    - patch: |
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: all
        spec:
          replicas: 3
      target:
        kind: Deployment
        labelSelector: "tier=frontend"
  postBuild:
    substitute:                  # Variable substitution from ConfigMaps/Secrets
      CLUSTER_ENV: production
      DOMAIN: app.example.com
    substituteFrom:
      - kind: ConfigMap
        name: cluster-settings
      - kind: Secret
        name: cluster-secrets


# === HelmRelease (Helm chart deployment) ===

---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: redis
  namespace: cache
spec:
  interval: 30m
  chart:
    spec:
      chart: redis
      version: "18.x"           # Semver range
      sourceRef:
        kind: HelmRepository
        name: bitnami
        namespace: flux-system
      interval: 12h              # Check for new chart versions
  values:
    architecture: replication
    replica:
      replicaCount: 3
    auth:
      existingSecret: redis-credentials
    metrics:
      enabled: true
  valuesFrom:
    - kind: ConfigMap
      name: redis-values
      valuesKey: overrides.yaml
  install:
    remediation:
      retries: 3
  upgrade:
    remediation:
      retries: 3
      remediateLastFailure: true
    cleanupOnFail: true
  test:
    enable: true                 # Run Helm tests after install/upgrade
  rollback:
    cleanupOnFail: true


# === Image Automation (auto-update on new container images) ===

---
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImageRepository
metadata:
  name: myapp
  namespace: flux-system
spec:
  image: ghcr.io/myorg/myapp
  interval: 5m
  provider: generic

---
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImagePolicy
metadata:
  name: myapp
  namespace: flux-system
spec:
  imageRepositoryRef:
    name: myapp
  policy:
    semver:
      range: ">=1.0.0"          # Only promote semver-tagged images
  filterTags:
    pattern: "^v(?P<version>[0-9]+\\.[0-9]+\\.[0-9]+)$"
    extract: "$version"

---
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImageUpdateAutomation
metadata:
  name: flux-system
  namespace: flux-system
spec:
  interval: 30m
  sourceRef:
    kind: GitRepository
    name: fleet-infra
  git:
    checkout:
      ref:
        branch: main
    commit:
      author:
        email: flux@example.com
        name: flux-bot
      messageTemplate: |
        chore: update images
        {{range .Changed.Changes}}
        - {{.OldValue}} -> {{.NewValue}}
        {{end}}
    push:
      branch: main
  update:
    path: ./apps
    strategy: Setters            # Uses image policy markers in manifests


# === Multi-tenant setup ===

---
# Tenant namespace with Flux access
apiVersion: v1
kind: Namespace
metadata:
  name: team-frontend
  labels:
    toolkit.fluxcd.io/tenant: team-frontend

---
# Tenant service account (limited RBAC)
apiVersion: v1
kind: ServiceAccount
metadata:
  name: team-frontend
  namespace: team-frontend

---
# Tenant Kustomization (scoped to their namespace)
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: team-frontend-apps
  namespace: team-frontend
spec:
  interval: 5m
  sourceRef:
    kind: GitRepository
    name: team-frontend-repo
    namespace: flux-system
  path: ./deploy
  prune: true
  serviceAccountName: team-frontend    # RBAC-scoped
  targetNamespace: team-frontend       # Force all resources into tenant namespace
  validation: client                   # Dry-run validation before apply
```

```bash
# --- Flux CLI commands ---

# Check Flux health
flux check

# Reconcile immediately (don't wait for interval)
flux reconcile kustomization apps --with-source

# Suspend/resume deployments (maintenance window)
flux suspend kustomization apps
flux resume kustomization apps

# View Flux events and logs
flux events --for Kustomization/apps
flux logs --kind=Kustomization --name=apps

# Diff: preview what would change
flux diff kustomization apps --path=./apps/production

# Export current state
flux export kustomization --all > kustomizations.yaml

# Create alerts (Slack, Teams, Discord, etc.)
flux create alert-provider slack \
  --type=slack \
  --channel=deployments \
  --address=https://hooks.slack.com/services/xxx

flux create alert apps-alert \
  --provider-ref=slack \
  --event-source="Kustomization/*" \
  --event-source="HelmRelease/*" \
  --event-severity=error
```

Flux CD patterns:
1. **Source controllers** — poll Git/Helm/OCI repos for changes; `interval` controls reconciliation frequency
2. **Kustomization** — applies manifests from a source path; `dependsOn` chains deployments in order
3. **HelmRelease** — declarative Helm with semver ranges, auto-remediation, and rollback on failure
4. **Image automation** — watches container registries, updates manifests with new tags, commits back to Git
5. **Multi-tenancy** — `serviceAccountName` + `targetNamespace` scope tenant deployments to their namespace only'''
    ),
    (
        "devops/gitops-patterns",
        "Show GitOps best practices: environment promotion, drift detection, secrets management, and progressive delivery with Flux CD and Flagger.",
        '''GitOps patterns with Flux CD and Flagger:

```yaml
# === Environment Promotion Pipeline ===

# Strategy: separate directories per environment, promote via PR
#
# apps/
# ├── base/
# │   ├── deployment.yaml
# │   ├── service.yaml
# │   └── kustomization.yaml
# ├── staging/
# │   ├── kustomization.yaml    # patches: replicas=1, resources=small
# │   └── patch-resources.yaml
# └── production/
#     ├── kustomization.yaml    # patches: replicas=3, resources=large
#     ├── patch-resources.yaml
#     └── patch-hpa.yaml

# --- apps/base/kustomization.yaml ---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml

# --- apps/staging/kustomization.yaml ---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: staging
resources:
  - ../base
patches:
  - path: patch-resources.yaml

# --- apps/production/kustomization.yaml ---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: production
resources:
  - ../base
patches:
  - path: patch-resources.yaml
  - path: patch-hpa.yaml


# === Secrets Management with SOPS ===

# Flux decrypts SOPS-encrypted secrets automatically

---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: apps
  namespace: flux-system
spec:
  interval: 10m
  sourceRef:
    kind: GitRepository
    name: fleet-infra
  path: ./apps/production
  prune: true
  decryption:
    provider: sops                # Auto-decrypt SOPS files
    secretRef:
      name: sops-age-key         # Age private key for decryption


# --- Encrypted secret in Git ---
# Created with: sops --encrypt --age <age-public-key> secret.yaml > secret.enc.yaml

# secret.enc.yaml (safe to commit — values are encrypted)
---
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
  namespace: production
type: Opaque
stringData:
  DATABASE_URL: ENC[AES256_GCM,data:x7Bz...truncated,type:str]
  API_KEY: ENC[AES256_GCM,data:k9Qm...truncated,type:str]
sops:
  age:
    - recipient: age1abc...
      enc: |
        -----BEGIN AGE ENCRYPTED FILE-----
        ...
        -----END AGE ENCRYPTED FILE-----


# === Progressive Delivery with Flagger ===

---
# Install Flagger (works alongside Flux)
# flux create source helm flagger \
#   --url=https://flagger.app \
#   --namespace=flagger-system

apiVersion: flagger.app/v1beta1
kind: Canary
metadata:
  name: myapp
  namespace: production
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: myapp
  service:
    port: 80
    targetPort: 8080
    gateways:
      - public-gateway
    hosts:
      - app.example.com
  analysis:
    # Canary promotion criteria
    interval: 1m                    # Check metrics every minute
    threshold: 5                    # Max failed checks before rollback
    maxWeight: 50                   # Max traffic percentage to canary
    stepWeight: 10                  # Increase by 10% each interval
    metrics:
      - name: request-success-rate
        thresholdRange:
          min: 99                   # Require 99%+ success rate
        interval: 1m
      - name: request-duration
        thresholdRange:
          max: 500                  # p99 latency < 500ms
        interval: 1m
    webhooks:
      - name: load-test
        url: http://flagger-loadtester.flagger-system/
        metadata:
          type: cmd
          cmd: "hey -z 1m -q 10 -c 2 http://myapp-canary.production/"
      - name: acceptance-test
        url: http://flagger-loadtester.flagger-system/
        metadata:
          type: bash
          cmd: "curl -sf http://myapp-canary.production/healthz"


# === Drift Detection and Remediation ===

---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: apps
  namespace: flux-system
spec:
  interval: 10m
  sourceRef:
    kind: GitRepository
    name: fleet-infra
  path: ./apps/production
  prune: true
  force: false                   # Don't force-apply (detect conflicts)
  patches:
    - patch: |
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: all
          annotations:
            # Detect and correct manual kubectl edits
            fluxcd.io/automated: "true"
      target:
        kind: Deployment
```

```python
# --- CI/CD promotion script ---

import subprocess
import sys
from pathlib import Path


def promote_to_production(app: str, staging_tag: str):
    """Promote a staging image to production via Git commit.

    GitOps principle: the ONLY way to deploy is via Git.
    No kubectl apply, no helm install — only git push.
    """
    repo_root = Path("fleet-infra")

    # Update production kustomization with new image tag
    prod_kustomization = repo_root / "apps" / "production" / "kustomization.yaml"
    content = prod_kustomization.read_text()
    content = update_image_tag(content, app, staging_tag)
    prod_kustomization.write_text(content)

    # Commit and push (Flux will reconcile automatically)
    subprocess.run(["git", "add", str(prod_kustomization)], check=True)
    subprocess.run([
        "git", "commit", "-m",
        f"promote: {app}:{staging_tag} -> production"
    ], check=True)
    subprocess.run(["git", "push", "origin", "main"], check=True)

    print(f"Promoted {app}:{staging_tag} to production")
    print("Flux will reconcile within 5 minutes (or run: flux reconcile ks apps)")


def update_image_tag(content: str, app: str, tag: str) -> str:
    """Update image tag in kustomization."""
    import yaml

    data = yaml.safe_load(content)
    if "images" not in data:
        data["images"] = []

    for img in data["images"]:
        if img["name"] == f"ghcr.io/myorg/{app}":
            img["newTag"] = tag
            break
    else:
        data["images"].append({
            "name": f"ghcr.io/myorg/{app}",
            "newTag": tag,
        })

    return yaml.dump(data, default_flow_style=False)
```

GitOps best practices:
1. **Environment promotion** — separate dirs per env, promote via PR/commit; never `kubectl apply` directly
2. **SOPS encryption** — store encrypted secrets in Git; Flux decrypts with Age/GPG keys at apply time
3. **Progressive delivery** — Flagger canary analysis: gradual traffic shift with automated rollback on metric violations
4. **Drift detection** — `prune: true` deletes resources removed from Git; Flux re-applies on every reconciliation to correct manual changes
5. **Immutable deployments** — always use image digest or semver tags, never `:latest`; image automation commits exact versions'''
    ),
]
"""
