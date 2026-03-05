PAIRS = [
    (
        "cicd/github-actions-advanced-workflows",
        "Explain advanced GitHub Actions CI/CD patterns including reusable workflows, matrix strategies, composite actions, OIDC cloud authentication, caching strategies, and environment protection rules with complete pipeline implementation",
        r"""# Advanced GitHub Actions: Production-Grade CI/CD Pipelines

## Why GitHub Actions Architecture Matters

GitHub Actions has evolved from a simple CI runner into a full orchestration platform, **because** it now supports reusable workflows, composite actions, OIDC federation, and environment protection rules that rival dedicated CI/CD tools like Jenkins or CircleCI. **However**, most teams underutilize these features, relying on copy-pasted workflow files across repositories instead of building a composable pipeline architecture. **Therefore**, understanding the advanced patterns is essential for maintaining CI/CD at scale without drowning in YAML duplication.

The **best practice** is to treat your CI/CD configuration as a layered system: reusable workflows define the high-level stages, composite actions encapsulate reusable steps, and repository-level workflows wire everything together with environment-specific configuration. A **common mistake** is mixing all concerns into a single monolithic workflow file that becomes unmaintainable as the project grows.

## Reusable Workflows and Composite Actions

### Reusable Workflows

Reusable workflows are called from other workflows using the `workflow_call` trigger. They accept inputs and secrets, making them ideal for standardizing CI/CD stages across an organization. The **trade-off** is that reusable workflows run as a separate job graph, so they cannot share the local filesystem with the caller — you must use artifacts or outputs to pass data between them.

```yaml
# .github/workflows/reusable-build-test.yml
# Reusable workflow for build and test stages
name: Build and Test

on:
  workflow_call:
    inputs:
      node-version:
        description: "Node.js version to use"
        required: false
        type: string
        default: "20"
      working-directory:
        description: "Directory containing package.json"
        required: false
        type: string
        default: "."
      enable-coverage:
        description: "Whether to collect code coverage"
        required: false
        type: boolean
        default: true
      artifact-retention-days:
        description: "Days to retain build artifacts"
        required: false
        type: number
        default: 5
    secrets:
      NPM_TOKEN:
        description: "NPM registry auth token"
        required: false
    outputs:
      build-version:
        description: "Semantic version of the build"
        value: ${{ jobs.build.outputs.version }}
      coverage-percent:
        description: "Test coverage percentage"
        value: ${{ jobs.test.outputs.coverage }}

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.version.outputs.version }}
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js with caching
        uses: actions/setup-node@v4
        with:
          node-version: ${{ inputs.node-version }}
          cache: "npm"
          cache-dependency-path: "${{ inputs.working-directory }}/package-lock.json"

      - name: Install dependencies
        working-directory: ${{ inputs.working-directory }}
        run: npm ci
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}

      - name: Extract version
        id: version
        working-directory: ${{ inputs.working-directory }}
        run: |
          VERSION=$(node -p "require('./package.json').version")
          SHORT_SHA=${GITHUB_SHA::8}
          echo "version=${VERSION}-${SHORT_SHA}" >> $GITHUB_OUTPUT

      - name: Build application
        working-directory: ${{ inputs.working-directory }}
        run: npm run build

      - name: Upload build artifacts
        uses: actions/upload-artifact@v4
        with:
          name: build-output-${{ github.sha }}
          path: ${{ inputs.working-directory }}/dist/
          retention-days: ${{ inputs.artifact-retention-days }}

  test:
    needs: build
    runs-on: ubuntu-latest
    outputs:
      coverage: ${{ steps.coverage.outputs.percent }}
    strategy:
      fail-fast: false
      matrix:
        shard: [1, 2, 3, 4]
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: ${{ inputs.node-version }}
          cache: "npm"
          cache-dependency-path: "${{ inputs.working-directory }}/package-lock.json"

      - name: Install dependencies
        working-directory: ${{ inputs.working-directory }}
        run: npm ci

      - name: Run sharded tests
        working-directory: ${{ inputs.working-directory }}
        run: |
          npx jest --shard=${{ matrix.shard }}/4 \
            --ci --reporters=default --reporters=jest-junit \
            ${{ inputs.enable-coverage && '--coverage --coverageReporters=json' || '' }}
        env:
          JEST_JUNIT_OUTPUT_DIR: ./reports

      - name: Extract coverage
        if: inputs.enable-coverage && matrix.shard == 1
        id: coverage
        working-directory: ${{ inputs.working-directory }}
        run: |
          PERCENT=$(node -p "JSON.parse(require('fs').readFileSync('coverage/coverage-summary.json','utf8')).total.lines.pct")
          echo "percent=${PERCENT}" >> $GITHUB_OUTPUT
```

### Composite Actions for Reusable Steps

Composite actions bundle multiple steps into a single reusable unit. Unlike reusable workflows, they run **within** the calling job, sharing the filesystem and environment. This makes them ideal for setup tasks, repeated step sequences, and encapsulating vendor-specific logic. A **pitfall** to watch for is that composite actions cannot directly access `secrets` — you must pass them as inputs.

```yaml
# .github/actions/docker-build-push/action.yml
# Composite action for building and pushing Docker images
name: "Docker Build and Push"
description: "Build, scan, and push a Docker image with caching"

inputs:
  registry:
    description: "Container registry URL"
    required: true
  image-name:
    description: "Image name (without tag)"
    required: true
  dockerfile:
    description: "Path to Dockerfile"
    required: false
    default: "./Dockerfile"
  context:
    description: "Build context directory"
    required: false
    default: "."
  push:
    description: "Whether to push the image"
    required: false
    default: "true"
  scan-severity:
    description: "Trivy scan severity threshold"
    required: false
    default: "CRITICAL,HIGH"

outputs:
  image-digest:
    description: "The image digest"
    value: ${{ steps.build.outputs.digest }}
  image-tag:
    description: "The full image tag"
    value: ${{ steps.meta.outputs.tags }}
  scan-results:
    description: "Security scan result status"
    value: ${{ steps.scan.outputs.exit-code }}

runs:
  using: "composite"
  steps:
    - name: Docker metadata
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: ${{ inputs.registry }}/${{ inputs.image-name }}
        tags: |
          type=sha,prefix=
          type=ref,event=branch
          type=ref,event=pr
          type=semver,pattern={{version}}
          type=semver,pattern={{major}}.{{minor}}

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3

    - name: Build image
      id: build
      uses: docker/build-push-action@v5
      with:
        context: ${{ inputs.context }}
        file: ${{ inputs.dockerfile }}
        push: ${{ inputs.push }}
        tags: ${{ steps.meta.outputs.tags }}
        labels: ${{ steps.meta.outputs.labels }}
        cache-from: type=gha
        cache-to: type=gha,mode=max
        provenance: true
        sbom: true

    - name: Scan image with Trivy
      id: scan
      uses: aquasecurity/trivy-action@master
      with:
        image-ref: ${{ inputs.registry }}/${{ inputs.image-name }}@${{ steps.build.outputs.digest }}
        format: "sarif"
        output: "trivy-results.sarif"
        severity: ${{ inputs.scan-severity }}
        exit-code: "1"
      continue-on-error: true

    - name: Upload scan results
      if: always()
      uses: github/codeql-action/upload-sarif@v3
      with:
        sarif_file: "trivy-results.sarif"
      shell: bash
```

## OIDC Authentication for Cloud Deploys

A **best practice** for deploying to cloud providers is using OIDC (OpenID Connect) federation instead of storing long-lived credentials as repository secrets. **Because** GitHub Actions can mint a short-lived JWT for each workflow run, cloud providers can verify the token's claims (repository, branch, environment) and issue temporary credentials. This eliminates secret rotation entirely and follows the principle of least privilege.

```yaml
# .github/workflows/deploy-production.yml
# Production deployment with OIDC, environment protection, and rollback
name: Deploy to Production

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version to deploy"
        required: true
        type: string
  workflow_call:
    inputs:
      version:
        required: true
        type: string

permissions:
  id-token: write
  contents: read
  deployments: write

concurrency:
  group: production-deploy
  cancel-in-progress: false

jobs:
  pre-deploy-checks:
    runs-on: ubuntu-latest
    outputs:
      previous-version: ${{ steps.current.outputs.version }}
    steps:
      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/github-actions-deploy
          role-session-name: pre-deploy-check-${{ github.run_id }}
          aws-region: us-east-1

      - name: Get current deployed version
        id: current
        run: |
          CURRENT=$(aws ssm get-parameter \
            --name /app/production/version \
            --query "Parameter.Value" --output text)
          echo "version=${CURRENT}" >> $GITHUB_OUTPUT

      - name: Validate deployment artifact exists
        run: |
          aws s3 ls "s3://deploy-artifacts/releases/${{ inputs.version }}/" \
            || (echo "Artifact not found for version ${{ inputs.version }}" && exit 1)

  deploy:
    needs: pre-deploy-checks
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://app.example.com
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/github-actions-deploy
          role-session-name: deploy-${{ github.run_id }}
          aws-region: us-east-1

      - name: Deploy to ECS
        run: |
          aws ecs update-service \
            --cluster production \
            --service api \
            --task-definition "api:${{ inputs.version }}" \
            --force-new-deployment

      - name: Wait for deployment stability
        run: |
          aws ecs wait services-stable \
            --cluster production \
            --services api
        timeout-minutes: 15

      - name: Run smoke tests
        run: |
          for endpoint in /health /api/v1/status; do
            STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://app.example.com${endpoint}")
            if [ "$STATUS" != "200" ]; then
              echo "Smoke test failed: ${endpoint} returned ${STATUS}"
              exit 1
            fi
          done

      - name: Update deployed version parameter
        if: success()
        run: |
          aws ssm put-parameter \
            --name /app/production/version \
            --value "${{ inputs.version }}" \
            --type String --overwrite

  rollback:
    needs: [pre-deploy-checks, deploy]
    if: failure() && needs.pre-deploy-checks.outputs.previous-version != ''
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/github-actions-deploy
          role-session-name: rollback-${{ github.run_id }}
          aws-region: us-east-1

      - name: Rollback to previous version
        run: |
          PREV="${{ needs.pre-deploy-checks.outputs.previous-version }}"
          echo "Rolling back to version ${PREV}"
          aws ecs update-service \
            --cluster production \
            --service api \
            --task-definition "api:${PREV}" \
            --force-new-deployment

      - name: Wait for rollback stability
        run: |
          aws ecs wait services-stable \
            --cluster production \
            --services api
        timeout-minutes: 15
```

### Environment Protection Rules

GitHub environments provide approval gates, deployment branch restrictions, and wait timers. **Therefore**, you should define separate environments for staging and production, requiring manual approval for production deployments. The **trade-off** is slower deployments versus safety — in practice, the few minutes of human review prevent catastrophic production incidents.

## Caching Strategies

Effective caching can reduce CI run times by 50-80%. The `actions/cache` action supports key-based caching with restore keys for partial matches. A **common mistake** is using overly broad cache keys that rarely hit, or overly narrow keys that waste storage. The **best practice** is a hierarchical key strategy: exact match first, then progressively broader fallbacks.

## Summary and Key Takeaways

- **Reusable workflows** standardize CI/CD stages across repositories — use `workflow_call` with typed inputs and outputs to create a composable pipeline library
- **Composite actions** encapsulate multi-step logic that runs within a job — ideal for setup sequences and vendor integrations
- **Matrix strategies** with `fail-fast: false` enable parallel test sharding, dramatically reducing feedback time
- **OIDC authentication** eliminates long-lived cloud credentials — configure trust policies scoped to specific repositories, branches, and environments
- **Environment protection rules** add human approval gates and deployment restrictions — the **trade-off** of slightly slower deploys is vastly outweighed by the safety guarantees
- **Hierarchical caching** with restore-key fallbacks ensures cache hits even when lock files change partially
- **Concurrency controls** with `cancel-in-progress` prevent resource waste on superseded commits while protecting production deploys from concurrent execution
- **Artifact management** with retention policies keeps storage costs under control while ensuring build outputs are available for deployment and debugging"""
    ),
    (
        "cicd/gitops-argocd-progressive-delivery",
        "Explain GitOps with ArgoCD including Application CRDs, sync policies, health checks, rollback strategies, multi-cluster management, Kustomize overlays, and progressive delivery with Argo Rollouts for canary and blue-green deployments",
        r"""# GitOps with ArgoCD: Declarative Deployments and Progressive Delivery

## The GitOps Paradigm and Why It Matters

GitOps fundamentally changes how teams deploy software **because** it shifts the source of truth from imperative scripts and CI pipelines to declarative manifests stored in Git. Instead of a CI system pushing changes to a cluster (which requires storing cluster credentials externally), ArgoCD runs **inside** the cluster and continuously pulls desired state from Git. **Therefore**, the attack surface is dramatically reduced — no external system holds cluster admin credentials, and every change is auditable through Git history.

**However**, adopting GitOps is not simply "put YAML in Git." It requires careful repository structure, sync policy configuration, and health check definitions. A **common mistake** is treating the GitOps repository as a dumping ground for raw manifests without layering or environment separation. The **best practice** is to use Kustomize or Helm for environment-specific overlays, keeping base manifests DRY while allowing per-environment customization.

## ArgoCD Application CRDs and Sync Policies

### Application Manifest Structure

An ArgoCD Application CRD defines the relationship between a Git source and a cluster destination. The sync policy controls whether ArgoCD automatically applies changes or waits for manual approval. **Because** production environments require more caution, you typically enable auto-sync for staging but require manual sync for production.

```yaml
# applications/base/api-application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: api-production
  namespace: argocd
  labels:
    app.kubernetes.io/part-of: platform
    environment: production
  # Finalizer ensures ArgoCD cleans up resources when the Application is deleted
  finalizers:
    - resources-finalizer.argocd.argoproj.io
  annotations:
    # Notification triggers for Slack/Teams integration
    notifications.argoproj.io/subscribe.on-sync-succeeded.slack: deployments
    notifications.argoproj.io/subscribe.on-sync-failed.slack: deployments-alerts
    notifications.argoproj.io/subscribe.on-health-degraded.slack: deployments-alerts
spec:
  project: production
  source:
    repoURL: https://github.com/org/gitops-manifests.git
    targetRevision: main
    path: overlays/production/api
    kustomize:
      # Override image tag dynamically
      images:
        - "api=registry.example.com/api"
      commonAnnotations:
        managed-by: argocd
  destination:
    server: https://kubernetes.default.svc
    namespace: api-production
  syncPolicy:
    automated:
      prune: true       # Delete resources no longer in Git
      selfHeal: true     # Revert manual cluster changes
      allowEmpty: false  # Prevent accidental deletion of all resources
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
      - PruneLast=true
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
    retry:
      limit: 3
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
  ignoreDifferences:
    # Ignore fields mutated by controllers
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas   # HPA manages replicas
    - group: autoscaling
      kind: HorizontalPodAutoscaler
      jqPathExpressions:
        - .status
  # Custom health checks for CRDs
  info:
    - name: documentation
      value: https://wiki.example.com/api-deployment
```

### AppProject for RBAC and Resource Restrictions

ArgoCD Projects provide RBAC boundaries, restricting which repositories, clusters, and resource types an Application can use. This is a **best practice** for multi-team environments **because** it prevents one team's Application from accidentally deploying to another team's namespace.

```yaml
# projects/production-project.yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: production
  namespace: argocd
spec:
  description: "Production workloads — restricted access"
  sourceRepos:
    - "https://github.com/org/gitops-manifests.git"
    - "https://github.com/org/helm-charts.git"
  destinations:
    - server: https://kubernetes.default.svc
      namespace: "api-production"
    - server: https://kubernetes.default.svc
      namespace: "web-production"
    # Deny deploying to kube-system or argocd namespaces
  clusterResourceWhitelist:
    - group: ""
      kind: Namespace
  namespaceResourceBlacklist:
    - group: ""
      kind: ResourceQuota   # Only platform team manages quotas
    - group: ""
      kind: LimitRange
  roles:
    - name: deployer
      description: "Can sync applications but not modify project"
      policies:
        - "p, proj:production:deployer, applications, sync, production/*, allow"
        - "p, proj:production:deployer, applications, get, production/*, allow"
      groups:
        - "org:deploy-team"
  syncWindows:
    # Only allow syncs during business hours for production
    - kind: allow
      schedule: "0 9 * * 1-5"   # Mon-Fri 9am
      duration: 10h              # Until 7pm
      applications: ["*"]
    - kind: deny
      schedule: "0 0 25 12 *"   # No deploys on Christmas
      duration: 24h
      applications: ["*"]
```

## Kustomize Overlays for Environment Management

Kustomize provides a template-free approach to manifest customization. The base layer defines the application structure, while overlays patch environment-specific values. This is the **best practice** **because** it avoids the complexity of Helm templating for simple customization needs while keeping manifests readable and auditable.

```yaml
# base/api/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - deployment.yaml
  - service.yaml
  - hpa.yaml
  - pdb.yaml
  - serviceaccount.yaml

commonLabels:
  app.kubernetes.io/name: api
  app.kubernetes.io/component: backend

configMapGenerator:
  - name: api-config
    literals:
      - LOG_LEVEL=info
      - METRICS_ENABLED=true

---
# overlays/production/api/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../../base/api

namespace: api-production

commonLabels:
  environment: production

patches:
  - target:
      kind: Deployment
      name: api
    patch: |
      - op: replace
        path: /spec/replicas
        value: 5
      - op: add
        path: /spec/template/spec/containers/0/resources
        value:
          requests:
            cpu: "500m"
            memory: "512Mi"
          limits:
            cpu: "2000m"
            memory: "2Gi"
      - op: add
        path: /spec/template/spec/topologySpreadConstraints
        value:
          - maxSkew: 1
            topologyKey: topology.kubernetes.io/zone
            whenUnsatisfiable: DoNotSchedule
            labelSelector:
              matchLabels:
                app.kubernetes.io/name: api
  - target:
      kind: HorizontalPodAutoscaler
      name: api
    patch: |
      - op: replace
        path: /spec/minReplicas
        value: 5
      - op: replace
        path: /spec/maxReplicas
        value: 50

configMapGenerator:
  - name: api-config
    behavior: merge
    literals:
      - LOG_LEVEL=warn
      - RATE_LIMIT_RPS=1000
      - CACHE_TTL=300
```

## Progressive Delivery with Argo Rollouts

Argo Rollouts extends Kubernetes Deployments with canary and blue-green strategies. **However**, the **trade-off** is added complexity — you replace standard Deployments with Rollout resources and must configure analysis templates for automated promotion decisions. The payoff is dramatically safer deployments, **because** bad releases are caught during the canary phase before reaching all users.

```yaml
# base/api/rollout.yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: api
spec:
  replicas: 10
  revisionHistoryLimit: 5
  selector:
    matchLabels:
      app.kubernetes.io/name: api
  strategy:
    canary:
      canaryService: api-canary
      stableService: api-stable
      trafficRouting:
        istio:
          virtualServices:
            - name: api-vsvc
              routes:
                - primary
      steps:
        # Step 1: Send 5% traffic to canary
        - setWeight: 5
        - pause: { duration: 5m }
        # Step 2: Run analysis at 5%
        - analysis:
            templates:
              - templateName: canary-success-rate
              - templateName: canary-latency
            args:
              - name: service-name
                value: api-canary
              - name: threshold
                value: "0.99"
        # Step 3: Increase to 25%
        - setWeight: 25
        - pause: { duration: 10m }
        # Step 4: Run analysis at 25%
        - analysis:
            templates:
              - templateName: canary-success-rate
            args:
              - name: service-name
                value: api-canary
              - name: threshold
                value: "0.995"
        # Step 5: Increase to 50%, final analysis
        - setWeight: 50
        - pause: { duration: 10m }
        - analysis:
            templates:
              - templateName: canary-success-rate
              - templateName: canary-latency
              - templateName: canary-error-budget
        # Step 6: Full promotion
        - setWeight: 100
      # Automatic rollback on failure
      abortScaleDownDelaySeconds: 30
      dynamicStableScale: true
  template:
    metadata:
      labels:
        app.kubernetes.io/name: api
    spec:
      containers:
        - name: api
          image: registry.example.com/api:latest
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /livez
              port: 8080
            initialDelaySeconds: 15
            periodSeconds: 10

---
# analysis/canary-success-rate.yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: canary-success-rate
spec:
  args:
    - name: service-name
    - name: threshold
      value: "0.99"
  metrics:
    - name: success-rate
      interval: 60s
      count: 5
      successCondition: "result[0] >= asFloat(args.threshold)"
      failureLimit: 2
      provider:
        prometheus:
          address: http://prometheus.monitoring:9090
          query: |
            sum(rate(http_requests_total{service="{{args.service-name}}", status=~"2.."}[2m]))
            /
            sum(rate(http_requests_total{service="{{args.service-name}}"}[2m]))
```

## Multi-Cluster Management

For organizations running workloads across multiple clusters, ArgoCD supports registering external clusters and deploying Applications to them. The **pitfall** here is network connectivity — ArgoCD's application controller must be able to reach the target cluster's API server. **Therefore**, in air-gapped or private-network environments, you may need to run separate ArgoCD instances per cluster and use ApplicationSets with a pull-based model.

## Summary and Key Takeaways

- **GitOps with ArgoCD** eliminates credential sprawl by pulling desired state from Git rather than pushing from CI pipelines — the cluster reconciles itself continuously
- **Application CRDs** define the Git-to-cluster mapping; use `syncPolicy.automated` with `selfHeal` and `prune` for staging, manual sync for production
- **AppProjects** enforce RBAC boundaries, restricting which repos, clusters, and namespaces each team can deploy to — a **best practice** for multi-tenant clusters
- **Kustomize overlays** keep base manifests DRY while allowing per-environment resource tuning, replica counts, and configuration without Helm template complexity
- **Argo Rollouts** provide canary and blue-green strategies with automated analysis — the **trade-off** is added complexity versus dramatically safer deployments
- **AnalysisTemplates** query Prometheus during canary phases and automatically abort rollouts when metrics breach thresholds
- **Sync windows** restrict deployment timing, preventing production changes during maintenance windows or holidays
- **Multi-cluster** patterns range from centralized ArgoCD with registered clusters to federated ApplicationSets for air-gapped environments"""
    ),
    (
        "cicd/container-image-building-optimization",
        "Explain advanced container image building patterns including multi-stage Docker builds, BuildKit features, layer caching optimization, distroless base images, security scanning with Trivy and Grype, and SBOM generation for multiple language stacks",
        r"""# Container Image Building: Optimization, Security, and Best Practices

## Why Container Image Architecture Matters

Container images are the fundamental unit of deployment in modern infrastructure, and their construction has a direct impact on build speed, runtime security, image size, and supply chain integrity. **Because** every layer in a Docker image is cached independently, understanding how the build cache works is critical for fast CI pipelines. **However**, most teams treat Dockerfiles as an afterthought, leading to bloated images with unnecessary dependencies, long rebuild times, and security vulnerabilities from unpatched base images. **Therefore**, investing in optimized, multi-stage builds with security scanning pays dividends across the entire deployment lifecycle.

A **common mistake** is installing build tools (compilers, dev headers, package managers) in the final runtime image. This inflates the image size by hundreds of megabytes and dramatically increases the attack surface. The **best practice** is to use multi-stage builds where the first stage compiles and builds, and the final stage contains only the runtime binary and its minimal dependencies.

## Multi-Stage Builds for Different Language Stacks

### Python Application with Distroless Base

Python presents a unique challenge **because** it is an interpreted language that requires the interpreter at runtime. The **trade-off** is between using a full Python image (large but easy to debug) versus a distroless image (minimal but harder to troubleshoot). For production workloads, distroless is the **best practice** since it eliminates shell access entirely, which mitigates container escape attacks.

```dockerfile
# syntax=docker/dockerfile:1.7
# Optimized Python multi-stage build

# ---- Stage 1: Build dependencies ----
FROM python:3.12-slim AS builder

# Install build dependencies needed for compiled packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment for clean copy to runtime
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies first (cached unless requirements change)
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-compile -r requirements.txt

# ---- Stage 2: Production runtime ----
FROM gcr.io/distroless/python3-debian12:nonroot AS runtime

# Copy only the virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY --chown=nonroot:nonroot src/ /app/src/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
USER nonroot:nonroot

EXPOSE 8080

ENTRYPOINT ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Go Application with Scratch Base

Go produces statically linked binaries, making it ideal for scratch-based images. **Because** Go compiles to a single binary with no runtime dependencies (when using CGO_ENABLED=0), the final image can be as small as 5-15MB. A **pitfall** is forgetting to disable CGO, which would introduce dynamic library dependencies and break the scratch base.

```dockerfile
# syntax=docker/dockerfile:1.7
# Optimized Go multi-stage build

# ---- Stage 1: Build ----
FROM golang:1.22-alpine AS builder

# Install CA certificates and timezone data for the runtime
RUN apk add --no-cache ca-certificates tzdata

WORKDIR /build

# Cache module downloads separately from build
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download && go mod verify

# Copy source and build
COPY . .
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -ldflags="-s -w -X main.version=$(git describe --tags --always)" \
    -trimpath -o /app/server ./cmd/server

# ---- Stage 2: Minimal runtime ----
FROM scratch

# Copy CA certs and timezone data from builder
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /usr/share/zoneinfo /usr/share/zoneinfo

# Copy the binary
COPY --from=builder /app/server /server

# Run as non-root (UID 65534 = nobody)
USER 65534:65534

EXPOSE 8080

ENTRYPOINT ["/server"]
```

### Node.js Application with Layered Caching

Node.js images benefit from careful layer ordering **because** `node_modules` is typically the largest and most frequently cached layer. The **best practice** is to copy `package.json` and `package-lock.json` first, install dependencies, then copy application code. This ensures the dependency layer is only rebuilt when the lock file changes.

```dockerfile
# syntax=docker/dockerfile:1.7
# Optimized Node.js multi-stage build

# ---- Stage 1: Install dependencies ----
FROM node:20-alpine AS deps

WORKDIR /app

# Copy only dependency manifests first for layer caching
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --ignore-scripts && \
    npm cache clean --force

# ---- Stage 2: Build ----
FROM node:20-alpine AS builder

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build the application (Next.js, Vite, etc.)
RUN npm run build

# Prune dev dependencies for production
RUN npm prune --production

# ---- Stage 3: Production runtime ----
FROM gcr.io/distroless/nodejs20-debian12:nonroot

WORKDIR /app

# Copy only production artifacts
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package.json .

ENV NODE_ENV=production \
    PORT=3000

USER nonroot:nonroot
EXPOSE 3000

CMD ["dist/server.js"]
```

## BuildKit Advanced Features

BuildKit is the modern build engine for Docker, enabled by default in Docker 23+. It provides several features that dramatically improve build performance and security.

### Cache Mounts and Secret Mounts

Cache mounts (`--mount=type=cache`) persist data across builds without including it in image layers. This is essential for package manager caches. Secret mounts (`--mount=type=secret`) inject secrets during build without leaking them into any layer — a **best practice** for accessing private registries or downloading licensed software. **However**, a **pitfall** is that secrets are still visible to the build process, so you must trust the Dockerfile.

### Multi-Platform Builds

BuildKit's `docker buildx` enables building images for multiple architectures (amd64, arm64) in a single command. This is crucial for teams deploying to both x86 servers and ARM-based instances (like AWS Graviton). The **trade-off** is significantly longer build times due to QEMU emulation, so the **best practice** is to use native runners per architecture in CI and merge manifests.

## Security Scanning and SBOM Generation

### Integrated Scanning Pipeline

Security scanning should be automated in CI, blocking deployments that contain critical vulnerabilities. **Because** scanner databases update daily, an image that passed scanning last week may fail today. **Therefore**, scan both at build time and periodically in the registry.

```python
import subprocess
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pathlib import Path


class Severity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


@dataclass
class Vulnerability:
    vuln_id: str
    package_name: str
    installed_version: str
    fixed_version: Optional[str]
    severity: Severity
    title: str
    description: str

    @property
    def is_fixable(self) -> bool:
        return self.fixed_version is not None and self.fixed_version != ""


@dataclass
class ScanResult:
    image: str
    scanner: str
    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    sbom_path: Optional[str] = None

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == Severity.HIGH)

    @property
    def fixable_criticals(self) -> list[Vulnerability]:
        # Only fixable critical vulns should block deployment,
        # because unfixable vulns need upstream patches
        return [v for v in self.vulnerabilities
                if v.severity == Severity.CRITICAL and v.is_fixable]

    def passes_policy(self, max_critical: int = 0, max_high: int = 5) -> bool:
        # Policy gate: zero fixable criticals, limited highs
        return len(self.fixable_criticals) <= max_critical and self.high_count <= max_high


def scan_with_trivy(image: str, output_dir: Path) -> ScanResult:
    # Run Trivy JSON scan
    result_file = output_dir / "trivy-results.json"
    subprocess.run([
        "trivy", "image",
        "--format", "json",
        "--output", str(result_file),
        "--severity", "CRITICAL,HIGH,MEDIUM",
        "--ignore-unfixed",
        image
    ], check=True)

    with open(result_file) as f:
        data = json.load(f)

    vulns: list[Vulnerability] = []
    for target in data.get("Results", []):
        for v in target.get("Vulnerabilities", []):
            vulns.append(Vulnerability(
                vuln_id=v["VulnerabilityID"],
                package_name=v["PkgName"],
                installed_version=v["InstalledVersion"],
                fixed_version=v.get("FixedVersion"),
                severity=Severity(v["Severity"]),
                title=v.get("Title", ""),
                description=v.get("Description", "")[:200],
            ))

    return ScanResult(image=image, scanner="trivy", vulnerabilities=vulns)


def generate_sbom(image: str, output_dir: Path) -> str:
    # Generate SPDX SBOM using Trivy
    sbom_file = output_dir / "sbom.spdx.json"
    subprocess.run([
        "trivy", "image",
        "--format", "spdx-json",
        "--output", str(sbom_file),
        image
    ], check=True)
    return str(sbom_file)


def main() -> int:
    image = sys.argv[1] if len(sys.argv) > 1 else "myapp:latest"
    output_dir = Path("scan-results")
    output_dir.mkdir(exist_ok=True)

    print(f"Scanning {image}...")
    result = scan_with_trivy(image, output_dir)
    result.sbom_path = generate_sbom(image, output_dir)

    print(f"Found {len(result.vulnerabilities)} vulnerabilities")
    print(f"  Critical (fixable): {len(result.fixable_criticals)}")
    print(f"  High: {result.high_count}")
    print(f"  SBOM: {result.sbom_path}")

    if not result.passes_policy():
        print("POLICY VIOLATION: Image fails security policy")
        for v in result.fixable_criticals:
            print(f"  {v.vuln_id}: {v.package_name} {v.installed_version} -> {v.fixed_version}")
        return 1

    print("Image passes security policy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## Layer Caching Optimization Strategies

Understanding Docker's layer caching model is essential for fast builds. Each instruction creates a layer, and Docker invalidates the cache for a layer and all subsequent layers when the instruction or its inputs change. **Therefore**, the ordering of instructions matters enormously:

1. **System packages** first (rarely change)
2. **Dependency manifests** next (change occasionally)
3. **Dependency installation** (cached unless manifests change)
4. **Application source code** last (changes every commit)

A **pitfall** is using `COPY . .` early in the Dockerfile, which invalidates the cache on every code change, forcing a full dependency reinstall. The **best practice** is to copy only the files needed for each stage.

## Summary and Key Takeaways

- **Multi-stage builds** separate build-time dependencies from runtime, reducing image sizes by 80-95% and eliminating unnecessary attack surface
- **Distroless and scratch bases** provide the smallest possible runtime images — use scratch for Go, distroless for Python/Node.js/Java
- **BuildKit cache mounts** persist package manager caches across builds without bloating image layers — this is the single most impactful optimization for dependency-heavy builds
- **Layer ordering** follows the principle of least-frequently-changed first: system packages, then dependency manifests, then dependency install, then source code
- **Security scanning** with Trivy or Grype should run at build time in CI and periodically against deployed images, **because** new CVEs are published daily
- **SBOM generation** in SPDX or CycloneDX format enables supply chain transparency and is increasingly required for compliance
- **Multi-platform builds** with `docker buildx` target both amd64 and arm64, but the **trade-off** is build time — use native runners per architecture when possible
- **Secret mounts** (`--mount=type=secret`) inject credentials during build without leaking them into layers — never use `ARG` or `ENV` for secrets"""
    ),
    (
        "cicd/database-migration-strategies-zero-downtime",
        "Explain database migration strategies in CI/CD pipelines including Flyway and Liquibase patterns, zero-downtime expand-contract migrations, data backfill strategies, migration testing, rollback support, and pre-deploy and post-deploy verification steps",
        r"""# Database Migration Strategies in CI/CD: Zero-Downtime Patterns

## Why Database Migrations Are the Hardest Part of CI/CD

Database migrations are uniquely challenging in CI/CD pipelines **because** they involve stateful changes that cannot be simply rolled back like a container image swap. A bad migration can corrupt data, lock tables for minutes, or create schema incompatibilities with running application instances. **Therefore**, database changes require a fundamentally different deployment strategy than application code. While a failed code deployment can be fixed by reverting to the previous container image, a failed migration that has already altered data may require manual intervention.

The **best practice** is to treat database migrations as a separate deployment phase that runs before application deployment, using the **expand-contract pattern** (also called parallel change) to ensure backward compatibility at every step. A **common mistake** is coupling schema changes directly to application releases, which forces big-bang deployments and eliminates the ability to roll back the application independently of the database.

## The Expand-Contract Pattern

### How It Works

The expand-contract pattern splits breaking schema changes into three phases:

1. **Expand**: Add new columns, tables, or indexes alongside existing ones. The old application code continues working because nothing is removed.
2. **Migrate**: Deploy new application code that writes to both old and new schemas. Backfill existing data into the new schema.
3. **Contract**: Once all application instances use the new schema, remove the old columns, tables, or indexes.

**However**, this pattern requires discipline — each phase must be a separate deployment, often spanning multiple release cycles. The **trade-off** is slower schema evolution versus zero-downtime guarantees. In practice, this is always worth it for production systems, **because** the cost of downtime far exceeds the cost of an extra deployment.

### Example: Renaming a Column

A classic scenario is renaming `user_name` to `display_name`. A **pitfall** is trying to do this in a single migration with `ALTER TABLE RENAME COLUMN`, which breaks all running application instances immediately.

```python
# migration_manager.py
# Database migration framework with expand-contract support
import hashlib
import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Protocol
from abc import abstractmethod
import logging

logger = logging.getLogger(__name__)


class MigrationPhase(Enum):
    EXPAND = "expand"        # Add new structures (backward compatible)
    MIGRATE_DATA = "migrate" # Backfill data to new structures
    CONTRACT = "contract"    # Remove old structures (after full rollout)


class DatabaseConnection(Protocol):
    @abstractmethod
    def execute(self, sql: str, params: Optional[tuple] = None) -> None: ...
    @abstractmethod
    def fetchone(self, sql: str, params: Optional[tuple] = None) -> Optional[tuple]: ...
    @abstractmethod
    def fetchall(self, sql: str, params: Optional[tuple] = None) -> list[tuple]: ...


@dataclass
class Migration:
    # Each migration has a unique version, phase, and up/down SQL
    version: str
    description: str
    phase: MigrationPhase
    up_sql: str
    down_sql: str
    # Validation queries to confirm migration succeeded
    validation_queries: list[tuple[str, Callable]] = field(default_factory=list)
    # Estimated execution time for planning
    estimated_seconds: int = 0
    # Whether this migration requires a maintenance window
    requires_downtime: bool = False

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.up_sql.encode()).hexdigest()[:16]


class MigrationRunner:
    # Manages migration execution with safety checks and rollback

    def __init__(self, db: DatabaseConnection, schema_table: str = "schema_migrations"):
        self.db = db
        self.schema_table = schema_table
        self._ensure_schema_table()

    def _ensure_schema_table(self) -> None:
        self.db.execute(
            f"CREATE TABLE IF NOT EXISTS {self.schema_table} ("
            "  version VARCHAR(50) PRIMARY KEY,"
            "  description VARCHAR(500) NOT NULL,"
            "  phase VARCHAR(20) NOT NULL,"
            "  checksum VARCHAR(16) NOT NULL,"
            "  applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,"
            "  execution_time_ms INTEGER,"
            "  applied_by VARCHAR(100)"
            ")"
        )

    def get_applied_versions(self) -> set[str]:
        rows = self.db.fetchall(
            f"SELECT version FROM {self.schema_table} ORDER BY applied_at"
        )
        return {row[0] for row in rows}

    def get_pending(self, migrations: list[Migration]) -> list[Migration]:
        applied = self.get_applied_versions()
        return [m for m in migrations if m.version not in applied]

    def validate_checksum_integrity(self, migrations: list[Migration]) -> list[str]:
        # Detect if previously applied migrations have been tampered with,
        # because this indicates a serious process violation
        errors = []
        for m in migrations:
            row = self.db.fetchone(
                f"SELECT checksum FROM {self.schema_table} WHERE version = %s",
                (m.version,)
            )
            if row and row[0] != m.checksum:
                errors.append(
                    f"Checksum mismatch for {m.version}: "
                    f"expected {m.checksum}, found {row[0]}"
                )
        return errors

    def apply(self, migration: Migration, dry_run: bool = False) -> bool:
        logger.info(
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"Applying {migration.version}: {migration.description} "
            f"(phase={migration.phase.value})"
        )

        if dry_run:
            logger.info(f"SQL:\n{migration.up_sql}")
            return True

        start = datetime.datetime.now()
        try:
            self.db.execute(migration.up_sql)

            # Run validation queries
            for query, validator in migration.validation_queries:
                result = self.db.fetchone(query)
                if not validator(result):
                    raise ValueError(
                        f"Validation failed for {migration.version}: "
                        f"query={query}, result={result}"
                    )

            elapsed_ms = int(
                (datetime.datetime.now() - start).total_seconds() * 1000
            )
            self.db.execute(
                f"INSERT INTO {self.schema_table} "
                f"(version, description, phase, checksum, execution_time_ms) "
                f"VALUES (%s, %s, %s, %s, %s)",
                (migration.version, migration.description,
                 migration.phase.value, migration.checksum, elapsed_ms)
            )
            logger.info(f"Applied {migration.version} in {elapsed_ms}ms")
            return True

        except Exception as e:
            logger.error(f"Failed to apply {migration.version}: {e}")
            logger.info(f"Attempting rollback with down_sql...")
            try:
                self.db.execute(migration.down_sql)
                logger.info(f"Rollback successful for {migration.version}")
            except Exception as rollback_err:
                logger.critical(
                    f"ROLLBACK FAILED for {migration.version}: {rollback_err}. "
                    f"Manual intervention required!"
                )
            return False

    def run_pending(
        self, migrations: list[Migration],
        phase_filter: Optional[MigrationPhase] = None,
        dry_run: bool = False,
    ) -> tuple[int, int]:
        # Returns (applied_count, failed_count)
        pending = self.get_pending(migrations)
        if phase_filter:
            pending = [m for m in pending if m.phase == phase_filter]

        if not pending:
            logger.info("No pending migrations")
            return (0, 0)

        applied, failed = 0, 0
        for m in pending:
            if self.apply(m, dry_run=dry_run):
                applied += 1
            else:
                failed += 1
                # Stop on first failure, because subsequent migrations
                # likely depend on this one
                logger.error("Stopping migration run due to failure")
                break

        return (applied, failed)
```

## Column Rename: Three-Phase Migration

Here is the expand-contract pattern applied to renaming `user_name` to `display_name` across three separate releases:

```python
# migrations/v2_rename_username.py
# Three-phase expand-contract migration for column rename
from migration_manager import Migration, MigrationPhase

# Phase 1 (Release N): Add new column alongside old one
expand_migration = Migration(
    version="2.0.0-expand",
    description="Add display_name column alongside user_name",
    phase=MigrationPhase.EXPAND,
    up_sql=(
        "-- Add new column (nullable initially, because existing rows lack data)\n"
        "ALTER TABLE users ADD COLUMN display_name VARCHAR(255);\n"
        "\n"
        "-- Create trigger to keep both columns in sync during transition\n"
        "CREATE OR REPLACE FUNCTION sync_display_name()\n"
        "RETURNS TRIGGER AS $$\n"
        "BEGIN\n"
        "    IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN\n"
        "        IF NEW.display_name IS NULL THEN\n"
        "            NEW.display_name := NEW.user_name;\n"
        "        END IF;\n"
        "        IF NEW.user_name IS NULL THEN\n"
        "            NEW.user_name := NEW.display_name;\n"
        "        END IF;\n"
        "    END IF;\n"
        "    RETURN NEW;\n"
        "END;\n"
        "$$ LANGUAGE plpgsql;\n"
        "\n"
        "CREATE TRIGGER trg_sync_display_name\n"
        "    BEFORE INSERT OR UPDATE ON users\n"
        "    FOR EACH ROW EXECUTE FUNCTION sync_display_name();\n"
        "\n"
        "-- Create index concurrently to avoid table locks\n"
        "CREATE INDEX CONCURRENTLY idx_users_display_name\n"
        "    ON users (display_name);"
    ),
    down_sql=(
        "DROP TRIGGER IF EXISTS trg_sync_display_name ON users;\n"
        "DROP FUNCTION IF EXISTS sync_display_name();\n"
        "DROP INDEX CONCURRENTLY IF EXISTS idx_users_display_name;\n"
        "ALTER TABLE users DROP COLUMN IF EXISTS display_name;"
    ),
    validation_queries=[
        # Verify column exists
        (
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'display_name'",
            lambda r: r is not None
        ),
    ],
    estimated_seconds=5,
    requires_downtime=False,
)

# Phase 2 (Release N+1): Backfill data
migrate_data_migration = Migration(
    version="2.0.0-migrate",
    description="Backfill display_name from user_name",
    phase=MigrationPhase.MIGRATE_DATA,
    up_sql=(
        "-- Batch update to avoid long-running transactions\n"
        "-- This approach processes 10000 rows per batch\n"
        "DO $$\n"
        "DECLARE\n"
        "    batch_size INTEGER := 10000;\n"
        "    rows_updated INTEGER;\n"
        "BEGIN\n"
        "    LOOP\n"
        "        UPDATE users\n"
        "        SET display_name = user_name\n"
        "        WHERE id IN (\n"
        "            SELECT id FROM users\n"
        "            WHERE display_name IS NULL\n"
        "            LIMIT batch_size\n"
        "            FOR UPDATE SKIP LOCKED\n"
        "        );\n"
        "        GET DIAGNOSTICS rows_updated = ROW_COUNT;\n"
        "        EXIT WHEN rows_updated = 0;\n"
        "        RAISE NOTICE 'Updated %% rows', rows_updated;\n"
        "        COMMIT;\n"
        "    END LOOP;\n"
        "END $$;\n"
        "\n"
        "-- Now that all data is backfilled, add NOT NULL constraint\n"
        "ALTER TABLE users\n"
        "    ALTER COLUMN display_name SET NOT NULL;"
    ),
    down_sql=(
        "ALTER TABLE users ALTER COLUMN display_name DROP NOT NULL;"
    ),
    validation_queries=[
        # Verify no nulls remain
        (
            "SELECT COUNT(*) FROM users WHERE display_name IS NULL",
            lambda r: r[0] == 0
        ),
    ],
    estimated_seconds=120,
    requires_downtime=False,
)

# Phase 3 (Release N+2): Remove old column after all apps use display_name
contract_migration = Migration(
    version="2.0.0-contract",
    description="Remove deprecated user_name column and sync trigger",
    phase=MigrationPhase.CONTRACT,
    up_sql=(
        "DROP TRIGGER IF EXISTS trg_sync_display_name ON users;\n"
        "DROP FUNCTION IF EXISTS sync_display_name();\n"
        "ALTER TABLE users DROP COLUMN user_name;"
    ),
    down_sql=(
        "-- Restore old column from new column data\n"
        "ALTER TABLE users ADD COLUMN user_name VARCHAR(255);\n"
        "UPDATE users SET user_name = display_name;\n"
        "ALTER TABLE users ALTER COLUMN user_name SET NOT NULL;"
    ),
    validation_queries=[
        # Verify old column is gone
        (
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'user_name'",
            lambda r: r is None
        ),
    ],
    estimated_seconds=10,
    requires_downtime=False,
)

MIGRATIONS = [expand_migration, migrate_data_migration, contract_migration]
```

## CI/CD Integration: Pre-Deploy and Post-Deploy Verification

### Pre-Deploy Validation

Before applying migrations in production, run them against a schema snapshot to catch errors early. **Because** migration SQL may behave differently against an empty schema versus a schema with millions of rows, the **best practice** is to test against a clone of production data (anonymized) or at minimum against the current production schema structure.

```python
# ci/migration_validator.py
# Pre-deploy migration validation for CI pipelines
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class ValidationResult:
    passed: bool
    migration_version: str
    error_message: Optional[str] = None
    execution_time_ms: int = 0
    rollback_tested: bool = False
    rollback_passed: bool = False


def validate_migrations_against_schema(
    migrations_dir: Path,
    schema_dump_url: str,
    db_url: str,
) -> list[ValidationResult]:
    # Spins up an ephemeral database, loads schema, applies migrations,
    # then tests rollback for each migration
    results: list[ValidationResult] = []

    # Step 1: Create ephemeral database from schema dump
    # Using pg_restore for PostgreSQL
    subprocess.run(
        ["pg_restore", "--no-owner", "--no-acl",
         "-d", db_url, schema_dump_url],
        check=True,
        capture_output=True,
    )

    # Step 2: Validate each pending migration
    # Import after schema is ready
    from migration_manager import MigrationRunner, DatabaseConnection

    # Connect to ephemeral DB (implementation depends on driver)
    db = create_connection(db_url)
    runner = MigrationRunner(db)

    # Step 3: Check for checksum tampering on already-applied migrations
    from migrations import ALL_MIGRATIONS
    integrity_errors = runner.validate_checksum_integrity(ALL_MIGRATIONS)
    if integrity_errors:
        for err in integrity_errors:
            results.append(ValidationResult(
                passed=False,
                migration_version="integrity-check",
                error_message=err,
            ))
        return results

    # Step 4: Dry-run then real-run each pending migration
    pending = runner.get_pending(ALL_MIGRATIONS)
    for migration in pending:
        result = ValidationResult(
            migration_version=migration.version,
            passed=True,
        )

        # Test forward migration
        if not runner.apply(migration):
            result.passed = False
            result.error_message = f"Migration {migration.version} failed"
            results.append(result)
            break  # Stop on first failure

        # Test rollback
        result.rollback_tested = True
        try:
            db.execute(migration.down_sql)
            result.rollback_passed = True
            # Re-apply after successful rollback test
            runner.apply(migration)
        except Exception as e:
            result.rollback_passed = False
            result.error_message = f"Rollback failed: {e}"

        results.append(result)

    return results


def create_connection(db_url: str) -> "DatabaseConnection":
    # Factory for database connections (placeholder)
    raise NotImplementedError("Implement for your DB driver")


if __name__ == "__main__":
    results = validate_migrations_against_schema(
        migrations_dir=Path("migrations"),
        schema_dump_url=sys.argv[1],
        db_url=sys.argv[2],
    )
    failures = [r for r in results if not r.passed]
    if failures:
        for f in failures:
            print(f"FAIL: {f.migration_version}: {f.error_message}")
        sys.exit(1)
    print(f"All {len(results)} migrations validated successfully")
```

### Post-Deploy Verification

After migrations are applied, verify data integrity. A **common mistake** is assuming the migration succeeded just because it did not raise an error. **Therefore**, always run post-migration checks that validate row counts, constraint integrity, and application-level queries.

## Summary and Key Takeaways

- **Expand-contract pattern** splits breaking changes into three phases (expand, migrate data, contract) — this guarantees zero downtime **because** the old and new schemas coexist
- **Sync triggers** keep old and new columns consistent during the transition period, allowing old and new application versions to run simultaneously
- **Batched backfills** with `SKIP LOCKED` avoid long-running transactions that block other queries — a **common mistake** is running a single `UPDATE` on millions of rows
- **Checksum validation** detects if previously applied migrations have been tampered with, which is a serious process violation
- **Pre-deploy validation** in CI runs migrations against a schema clone to catch errors before production — test both the forward migration and rollback
- **Post-deploy verification** confirms data integrity after migration — never assume success based solely on the absence of errors
- **Separate migration deployments** from application deployments — this gives you independent rollback capability for each concern
- **Phase filtering** lets you run only expand-phase migrations first, deploy the new app code, then run contract-phase migrations in a later release"""
    ),
    (
        "cicd/feature-flags-progressive-delivery",
        "Explain feature flag systems and progressive delivery patterns including LaunchDarkly and Unleash concepts, canary and blue-green deployments, percentage-based rollouts, kill switches, evaluation rules, targeting, and monitoring integration for safe releases",
        r"""# Feature Flags and Progressive Delivery: Safe Releases at Scale

## Why Feature Flags Transform Deployment Safety

Feature flags fundamentally decouple **deployment** from **release**, which is one of the most important architectural decisions a team can make. **Because** deploying code to production no longer means exposing it to users, teams can deploy continuously (even multiple times per day) while controlling exactly who sees new functionality and when. **Therefore**, the blast radius of any change is limited to the targeted percentage of users, and a **kill switch** can instantly disable a problematic feature without requiring a rollback deployment.

**However**, feature flags introduce their own complexity. Stale flags accumulate as technical debt, flag evaluation logic can become a performance bottleneck, and poorly structured flag systems create hidden coupling between services. A **common mistake** is treating feature flags as permanent configuration — they should have a defined lifecycle with scheduled cleanup dates. The **best practice** is to categorize flags by type (release, experiment, ops, permission) and enforce different lifecycle policies for each.

## Feature Flag Architecture

### Core Evaluation Engine

The flag evaluation engine is the heart of any feature flag system. It must be fast (evaluated on every request), deterministic (same inputs always produce the same result), and resilient (defaults to a safe value when the flag service is unavailable). **Because** flag evaluation happens in the hot path, the **best practice** is to cache flag definitions locally and use server-sent events or polling for updates, rather than making a network call per evaluation.

```python
# feature_flags/engine.py
# Feature flag evaluation engine with targeting and progressive rollout
import hashlib
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Union
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class FlagType(Enum):
    RELEASE = "release"       # Temporary, for shipping features
    EXPERIMENT = "experiment"  # A/B testing, time-boxed
    OPS = "ops"               # Operational toggles (kill switches, circuit breakers)
    PERMISSION = "permission"  # Long-lived, entitlement-based


class RolloutStrategy(Enum):
    ALL = "all"
    PERCENTAGE = "percentage"
    USER_LIST = "user_list"
    ATTRIBUTE = "attribute"
    GRADUAL = "gradual"


@dataclass
class UserContext:
    # Represents the evaluation context for a flag check
    user_id: str
    email: Optional[str] = None
    organization_id: Optional[str] = None
    plan: Optional[str] = None
    country: Optional[str] = None
    custom_attributes: dict[str, Any] = field(default_factory=dict)

    def get_attribute(self, key: str) -> Optional[Any]:
        # Check standard fields first, then custom attributes
        if hasattr(self, key):
            return getattr(self, key)
        return self.custom_attributes.get(key)


@dataclass
class TargetingRule:
    # A single targeting rule within a flag definition
    attribute: str
    operator: str  # "eq", "neq", "in", "not_in", "gt", "lt", "contains", "regex"
    value: Any
    variation: str  # Which variation to serve when this rule matches

    def evaluate(self, context: UserContext) -> Optional[str]:
        user_value = context.get_attribute(self.attribute)
        if user_value is None:
            return None

        match self.operator:
            case "eq":
                return self.variation if user_value == self.value else None
            case "neq":
                return self.variation if user_value != self.value else None
            case "in":
                return self.variation if user_value in self.value else None
            case "not_in":
                return self.variation if user_value not in self.value else None
            case "gt":
                return self.variation if user_value > self.value else None
            case "lt":
                return self.variation if user_value < self.value else None
            case "contains":
                return self.variation if self.value in str(user_value) else None
            case _:
                logger.warning(f"Unknown operator: {self.operator}")
                return None


@dataclass
class FlagDefinition:
    key: str
    flag_type: FlagType
    enabled: bool
    default_variation: str
    variations: dict[str, Any]  # variation_name -> value
    # Targeting rules evaluated in order; first match wins
    targeting_rules: list[TargetingRule] = field(default_factory=list)
    # Percentage rollout configuration
    rollout_percentage: int = 100  # 0-100
    rollout_variation: str = ""    # Variation for users in rollout
    # Override list: specific user_ids that always get a specific variation
    user_overrides: dict[str, str] = field(default_factory=dict)
    # Metadata for lifecycle management
    created_at: Optional[str] = None
    stale_after: Optional[str] = None  # Date when flag should be cleaned up
    owner: Optional[str] = None


def _hash_percentage(flag_key: str, user_id: str) -> int:
    # Deterministic hash for percentage rollout.
    # Using flag_key + user_id ensures consistent bucketing per flag
    # but different distribution across flags (avoids correlation).
    # This is a best practice because it prevents users from being
    # consistently in the "canary" group for ALL flags.
    hash_input = f"{flag_key}:{user_id}"
    hash_bytes = hashlib.sha256(hash_input.encode()).digest()
    return int.from_bytes(hash_bytes[:4], "big") % 100


class FlagEvaluator:
    # Thread-safe flag evaluator with local caching

    def __init__(self) -> None:
        self._flags: dict[str, FlagDefinition] = {}
        self._evaluation_count: int = 0
        self._last_update: float = 0.0

    def load_flags(self, flags: list[FlagDefinition]) -> None:
        # Atomic swap of flag definitions
        new_flags = {f.key: f for f in flags}
        self._flags = new_flags
        self._last_update = time.time()
        logger.info(f"Loaded {len(new_flags)} flag definitions")

    def evaluate(
        self,
        flag_key: str,
        context: UserContext,
        default: Any = None,
    ) -> Any:
        self._evaluation_count += 1
        flag = self._flags.get(flag_key)

        if flag is None:
            logger.warning(f"Flag '{flag_key}' not found, returning default")
            return default

        # Kill switch: if flag is disabled, return default variation
        if not flag.enabled:
            return flag.variations.get(flag.default_variation, default)

        # Step 1: Check user-level overrides
        if context.user_id in flag.user_overrides:
            override_variation = flag.user_overrides[context.user_id]
            return flag.variations.get(override_variation, default)

        # Step 2: Evaluate targeting rules in order
        for rule in flag.targeting_rules:
            matched_variation = rule.evaluate(context)
            if matched_variation is not None:
                return flag.variations.get(matched_variation, default)

        # Step 3: Percentage rollout
        if flag.rollout_percentage < 100:
            user_bucket = _hash_percentage(flag_key, context.user_id)
            if user_bucket >= flag.rollout_percentage:
                # User is outside the rollout percentage
                return flag.variations.get(flag.default_variation, default)

        # Step 4: User is in rollout, serve rollout variation
        rollout_var = flag.rollout_variation or flag.default_variation
        return flag.variations.get(rollout_var, default)

    def get_all_flags_for_context(
        self, context: UserContext
    ) -> dict[str, Any]:
        # Bulk evaluation for frontend bootstrap
        # This avoids N+1 evaluation calls on page load
        return {
            key: self.evaluate(key, context)
            for key in self._flags
        }

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_flags": len(self._flags),
            "evaluation_count": self._evaluation_count,
            "last_update": self._last_update,
        }
```

### Monitoring Integration

Feature flags without monitoring are flying blind. You must track flag evaluation outcomes alongside application metrics to detect when a flag change causes a degradation. **Because** feature flags change behavior without changing code, traditional deployment monitoring will not detect flag-related incidents. **Therefore**, you need a dedicated flag-aware monitoring layer.

```python
# feature_flags/monitoring.py
# Monitoring integration for feature flag evaluations
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Callable
import logging

logger = logging.getLogger(__name__)


@dataclass
class FlagMetrics:
    # Tracks evaluation outcomes per flag per variation
    evaluations: int = 0
    variation_counts: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    error_count: int = 0
    last_evaluation_at: float = 0.0
    avg_evaluation_ms: float = 0.0
    _total_eval_ms: float = 0.0


class FlagMonitor:
    # Collects and reports feature flag metrics

    def __init__(
        self,
        metrics_reporter: Optional[Callable[[str, float, dict], None]] = None,
        alert_callback: Optional[Callable[[str, str], None]] = None,
        error_rate_threshold: float = 0.05,
    ) -> None:
        self._metrics: dict[str, FlagMetrics] = defaultdict(FlagMetrics)
        self._lock = threading.Lock()
        self._reporter = metrics_reporter
        self._alert_callback = alert_callback
        self._error_threshold = error_rate_threshold

    def record_evaluation(
        self,
        flag_key: str,
        variation: str,
        duration_ms: float,
        error: bool = False,
    ) -> None:
        with self._lock:
            m = self._metrics[flag_key]
            m.evaluations += 1
            m.variation_counts[variation] += 1
            m.last_evaluation_at = time.time()
            m._total_eval_ms += duration_ms
            m.avg_evaluation_ms = m._total_eval_ms / m.evaluations
            if error:
                m.error_count += 1

        # Report to external metrics system (Prometheus, Datadog, etc.)
        if self._reporter:
            self._reporter(
                "feature_flag.evaluation",
                duration_ms,
                {"flag": flag_key, "variation": variation, "error": str(error)},
            )

        # Check error rate threshold
        if m.evaluations > 100:
            error_rate = m.error_count / m.evaluations
            if error_rate > self._error_threshold and self._alert_callback:
                self._alert_callback(
                    flag_key,
                    f"Flag '{flag_key}' error rate {error_rate:.2%} "
                    f"exceeds threshold {self._error_threshold:.2%}"
                )

    def get_flag_summary(self, flag_key: str) -> dict:
        m = self._metrics.get(flag_key)
        if not m:
            return {"flag": flag_key, "status": "no_data"}

        return {
            "flag": flag_key,
            "total_evaluations": m.evaluations,
            "variation_distribution": dict(m.variation_counts),
            "error_count": m.error_count,
            "error_rate": m.error_count / max(m.evaluations, 1),
            "avg_evaluation_ms": round(m.avg_evaluation_ms, 3),
        }

    def detect_rollout_anomalies(
        self,
        flag_key: str,
        expected_percentage: int,
        tolerance: float = 0.05,
    ) -> Optional[str]:
        # Detects if actual rollout percentage deviates from expected.
        # This is a best practice because hash distribution issues
        # or targeting rule conflicts can cause unexpected skew.
        m = self._metrics.get(flag_key)
        if not m or m.evaluations < 1000:
            return None  # Not enough data

        total = sum(m.variation_counts.values())
        # Assuming "on" variation is the rollout variation
        on_count = m.variation_counts.get("on", 0)
        actual_pct = (on_count / total) * 100

        if abs(actual_pct - expected_percentage) > (expected_percentage * tolerance):
            msg = (
                f"Rollout anomaly for '{flag_key}': "
                f"expected ~{expected_percentage}%, actual {actual_pct:.1f}%"
            )
            logger.warning(msg)
            return msg

        return None


class MonitoredEvaluator:
    # Wraps FlagEvaluator with automatic monitoring

    def __init__(self, evaluator, monitor: FlagMonitor) -> None:
        self._evaluator = evaluator
        self._monitor = monitor

    def evaluate(self, flag_key: str, context, default=None):
        start = time.monotonic()
        error = False
        variation = "default"
        try:
            result = self._evaluator.evaluate(flag_key, context, default)
            # Determine which variation was served
            flag = self._evaluator._flags.get(flag_key)
            if flag:
                for var_name, var_value in flag.variations.items():
                    if var_value == result:
                        variation = var_name
                        break
            return result
        except Exception as e:
            error = True
            logger.error(f"Flag evaluation error for '{flag_key}': {e}")
            return default
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            self._monitor.record_evaluation(
                flag_key, variation, duration_ms, error
            )
```

## Progressive Delivery Patterns

### Canary Deployments

Canary deployments route a small percentage of traffic to the new version and gradually increase it based on health metrics. **Because** the canary serves real production traffic, it catches issues that testing environments cannot — such as performance degradation under load, unexpected data patterns, or third-party service incompatibilities. The **trade-off** is slower rollouts versus much higher confidence in each release.

### Blue-Green Deployments

Blue-green maintains two identical production environments. At any time, one (blue) serves live traffic while the other (green) receives the new deployment. After validation, traffic switches entirely from blue to green. The **pitfall** with blue-green is database migrations — both environments share the database, so schema changes must be backward compatible (the expand-contract pattern from database migrations applies here). A **common mistake** is assuming blue-green is simpler than canary — it actually requires more infrastructure (double the capacity) and does not provide gradual traffic shifting.

### Percentage-Based Rollouts with Feature Flags

The most flexible approach combines feature flags with infrastructure-level traffic routing. **Therefore**, you can control rollout at both the infrastructure level (which pods receive traffic) and the application level (which users see new features). This layered approach provides the finest-grained control **because** you can target specific user segments (beta testers, enterprise customers, specific regions) independently of infrastructure routing.

## Kill Switches and Incident Response

Kill switches are a special category of feature flag designed for instant incident mitigation. **Because** they must work even when the flag service itself is degraded, the **best practice** is to cache kill switch states aggressively and default to "disabled" (safe mode) when the flag service is unreachable. Every customer-facing feature should have a corresponding kill switch.

```python
# feature_flags/kill_switches.py
# Kill switch implementation with circuit breaker pattern
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class CircuitState:
    is_open: bool = False
    failure_count: int = 0
    last_failure_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    half_open_attempts: int = 0


class KillSwitchManager:
    # Manages kill switches with automatic circuit breaker integration.
    # When error rates exceed thresholds, kill switches activate automatically.

    def __init__(
        self,
        evaluator,  # FlagEvaluator instance
        failure_threshold: int = 10,
        recovery_timeout: timedelta = timedelta(minutes=5),
        half_open_max_attempts: int = 3,
    ) -> None:
        self._evaluator = evaluator
        self._circuits: dict[str, CircuitState] = {}
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max = half_open_max_attempts

    def record_failure(self, feature_key: str) -> None:
        # Record a failure for a feature. If failures exceed threshold,
        # the circuit opens and the kill switch activates.
        circuit = self._circuits.setdefault(feature_key, CircuitState())
        circuit.failure_count += 1
        circuit.last_failure_at = datetime.utcnow()

        if circuit.failure_count >= self._failure_threshold and not circuit.is_open:
            circuit.is_open = True
            circuit.opened_at = datetime.utcnow()
            logger.critical(
                f"KILL SWITCH ACTIVATED for '{feature_key}' "
                f"after {circuit.failure_count} failures"
            )

    def record_success(self, feature_key: str) -> None:
        circuit = self._circuits.get(feature_key)
        if circuit and circuit.is_open:
            circuit.half_open_attempts += 1
            if circuit.half_open_attempts >= self._half_open_max:
                # Enough successful attempts in half-open state; close circuit
                circuit.is_open = False
                circuit.failure_count = 0
                circuit.half_open_attempts = 0
                logger.info(f"Kill switch deactivated for '{feature_key}'")

    def is_killed(self, feature_key: str) -> bool:
        circuit = self._circuits.get(feature_key)
        if circuit is None or not circuit.is_open:
            return False

        # Check if recovery timeout has elapsed (half-open state)
        if circuit.opened_at:
            elapsed = datetime.utcnow() - circuit.opened_at
            if elapsed > self._recovery_timeout:
                # Allow limited traffic through (half-open)
                logger.info(f"Kill switch for '{feature_key}' entering half-open state")
                return False

        return True

    def get_status(self) -> dict[str, dict]:
        return {
            key: {
                "is_killed": state.is_open,
                "failure_count": state.failure_count,
                "opened_at": str(state.opened_at) if state.opened_at else None,
            }
            for key, state in self._circuits.items()
        }
```

## Summary and Key Takeaways

- **Feature flags decouple deployment from release** — deploy code to production at any time, control visibility with flag evaluation rules. This is the foundation of progressive delivery
- **Deterministic hashing** (flag_key + user_id) ensures consistent user bucketing across evaluations while preventing cross-flag correlation — a **best practice** that avoids the "always-canary" user problem
- **Targeting rules** provide fine-grained control: serve variations based on user attributes (plan, org, country) with ordered evaluation and first-match semantics
- **Monitoring integration** is non-negotiable — track evaluation outcomes, variation distribution, and error rates per flag. **Because** flag changes do not appear in deployment logs, you need flag-specific observability
- **Kill switches** with circuit breaker patterns provide automatic incident mitigation — configure failure thresholds and recovery timeouts for self-healing behavior
- **Canary deployments** route a small traffic percentage to the new version with automated health analysis, while **blue-green** provides instant full-traffic switching with the **trade-off** of doubled infrastructure cost
- **Flag lifecycle management** prevents technical debt: categorize flags by type (release, experiment, ops, permission), set stale dates, and enforce cleanup policies
- **Local caching** of flag definitions ensures evaluation remains fast (sub-millisecond) and resilient to flag service outages — default to the safe variation when the service is unreachable"""
    ),
]
