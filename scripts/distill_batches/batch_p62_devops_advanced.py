"""DevOps — GitOps, service mesh, ArgoCD, and infrastructure patterns."""

PAIRS = [
    (
        "devops/gitops-argocd",
        "Show GitOps patterns with ArgoCD: application definitions, sync policies, multi-environment, and rollbacks.",
        '''GitOps with ArgoCD patterns:

```yaml
# --- ArgoCD Application definition ---

apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: my-app-production
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
  annotations:
    notifications.argoproj.io/subscribe.on-sync-succeeded.slack: deployments
    notifications.argoproj.io/subscribe.on-health-degraded.slack: alerts
spec:
  project: production

  source:
    repoURL: https://github.com/org/k8s-manifests.git
    targetRevision: main
    path: environments/production/my-app

    # Kustomize overlay
    kustomize:
      images:
        - my-registry.com/my-app  # Tag set by CI via image updater

    # OR Helm values
    # helm:
    #   releaseName: my-app
    #   valueFiles:
    #     - values-production.yaml
    #   parameters:
    #     - name: image.tag
    #       value: "v1.2.3"

  destination:
    server: https://kubernetes.default.svc
    namespace: production

  syncPolicy:
    automated:
      prune: true        # Delete resources removed from git
      selfHeal: true     # Revert manual kubectl changes
      allowEmpty: false   # Don't sync if no resources
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
      - ServerSideApply=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m

  # Health checks
  ignoreDifferences:
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas  # Ignore HPA-managed replica count


---
# --- ApplicationSet for multi-environment ---

apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: my-app-environments
  namespace: argocd
spec:
  generators:
    - list:
        elements:
          - env: staging
            cluster: https://staging-cluster.example.com
            revision: develop
            replicas: "2"
          - env: production
            cluster: https://kubernetes.default.svc
            revision: main
            replicas: "5"

  template:
    metadata:
      name: "my-app-{{env}}"
      namespace: argocd
    spec:
      project: "{{env}}"
      source:
        repoURL: https://github.com/org/k8s-manifests.git
        targetRevision: "{{revision}}"
        path: "environments/{{env}}/my-app"
        kustomize:
          patches:
            - target:
                kind: Deployment
              patch: |
                - op: replace
                  path: /spec/replicas
                  value: {{replicas}}
      destination:
        server: "{{cluster}}"
        namespace: "{{env}}"
      syncPolicy:
        automated:
          prune: true
          selfHeal: true


---
# --- AppProject with RBAC ---

apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: production
  namespace: argocd
spec:
  description: Production applications
  sourceRepos:
    - "https://github.com/org/k8s-manifests.git"
  destinations:
    - namespace: production
      server: https://kubernetes.default.svc
  clusterResourceWhitelist:
    - group: ""
      kind: Namespace
  namespaceResourceBlacklist:
    - group: ""
      kind: ResourceQuota
  roles:
    - name: deployer
      description: Can sync applications
      policies:
        - p, proj:production:deployer, applications, sync, production/*, allow
        - p, proj:production:deployer, applications, get, production/*, allow
      groups:
        - org:deploy-team
```

```bash
# --- ArgoCD CLI operations ---

# Sync application
argocd app sync my-app-production

# Rollback to previous version
argocd app rollback my-app-production 1

# View sync history
argocd app history my-app-production

# Diff what would change
argocd app diff my-app-production

# Wait for health
argocd app wait my-app-production --health --timeout 300
```

GitOps patterns:
1. **`selfHeal: true`** — ArgoCD reverts manual `kubectl` changes to match git
2. **`prune: true`** — resources deleted from git are deleted from cluster
3. **ApplicationSet** — generate apps for multiple environments from templates
4. **AppProject RBAC** — restrict which repos/namespaces teams can deploy to
5. **`ignoreDifferences`** — ignore HPA-managed fields to prevent sync conflicts'''
    ),
    (
        "devops/service-mesh",
        "Show service mesh patterns with Istio: traffic management, mTLS, circuit breaking, and observability.",
        '''Service mesh patterns with Istio:

```yaml
# --- VirtualService: traffic routing ---

apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: my-service
  namespace: production
spec:
  hosts:
    - my-service
  http:
    # Canary: 90% stable, 10% canary
    - match:
        - headers:
            x-canary:
              exact: "true"
      route:
        - destination:
            host: my-service
            subset: canary
          weight: 100

    - route:
        - destination:
            host: my-service
            subset: stable
          weight: 90
        - destination:
            host: my-service
            subset: canary
          weight: 10

      # Retry policy
      retries:
        attempts: 3
        perTryTimeout: 2s
        retryOn: 5xx,reset,connect-failure

      # Timeouts
      timeout: 10s

      # Fault injection (testing)
      # fault:
      #   delay:
      #     percentage:
      #       value: 5
      #     fixedDelay: 3s
      #   abort:
      #     percentage:
      #       value: 1
      #     httpStatus: 503


---
# --- DestinationRule: load balancing + circuit breaking ---

apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: my-service
spec:
  host: my-service
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        h2UpgradePolicy: DEFAULT
        maxRequestsPerConnection: 10
        maxRetries: 3

    outlierDetection:
      consecutive5xxErrors: 5
      interval: 30s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
      minHealthPercent: 30

    # mTLS between services
    tls:
      mode: ISTIO_MUTUAL

  subsets:
    - name: stable
      labels:
        version: stable
    - name: canary
      labels:
        version: canary


---
# --- PeerAuthentication: enforce mTLS ---

apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: production
spec:
  mtls:
    mode: STRICT  # All traffic must be mTLS


---
# --- AuthorizationPolicy: service-to-service access control ---

apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: order-service-policy
  namespace: production
spec:
  selector:
    matchLabels:
      app: order-service
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/production/sa/api-gateway"
              - "cluster.local/ns/production/sa/admin-service"
      to:
        - operation:
            methods: ["GET", "POST"]
            paths: ["/api/orders*"]
    - from:
        - source:
            principals:
              - "cluster.local/ns/production/sa/payment-service"
      to:
        - operation:
            methods: ["POST"]
            paths: ["/api/orders/*/pay"]


---
# --- ServiceEntry: external service access ---

apiVersion: networking.istio.io/v1beta1
kind: ServiceEntry
metadata:
  name: stripe-api
spec:
  hosts:
    - api.stripe.com
  ports:
    - number: 443
      name: https
      protocol: TLS
  location: MESH_EXTERNAL
  resolution: DNS
```

Service mesh patterns:
1. **Weighted routing** — canary deployments with percentage-based traffic split
2. **Circuit breaking** — `outlierDetection` ejects unhealthy pods from load balancing
3. **mTLS STRICT** — all service-to-service traffic encrypted and authenticated
4. **AuthorizationPolicy** — fine-grained service-to-service access control by path
5. **Fault injection** — test resilience by injecting delays and errors'''
    ),
    (
        "devops/monitoring-dashboards",
        "Show monitoring and dashboard patterns: Grafana dashboards, Prometheus queries, and SLO tracking.",
        '''Monitoring and SLO dashboard patterns:

```yaml
# --- Prometheus recording rules for SLOs ---

groups:
  - name: slo_rules
    interval: 30s
    rules:
      # Request success rate (availability SLI)
      - record: sli:http_requests:availability
        expr: |
          sum(rate(http_requests_total{status!~"5.."}[5m])) by (service)
          /
          sum(rate(http_requests_total[5m])) by (service)

      # Latency SLI (% requests under 300ms)
      - record: sli:http_requests:latency
        expr: |
          sum(rate(http_request_duration_seconds_bucket{le="0.3"}[5m])) by (service)
          /
          sum(rate(http_request_duration_seconds_count[5m])) by (service)

      # Error budget remaining
      - record: slo:error_budget:remaining
        expr: |
          1 - (
            (1 - sli:http_requests:availability)
            /
            (1 - 0.999)
          )

      # Error budget burn rate (how fast we're consuming budget)
      - record: slo:error_budget:burn_rate_1h
        expr: |
          (1 - sli:http_requests:availability)
          /
          (1 - 0.999)
```

```python
# --- Grafana dashboard as code (grafonnet / Python) ---

def create_slo_dashboard(service_name: str) -> dict:
    """Generate Grafana dashboard JSON for SLO monitoring."""
    return {
        "dashboard": {
            "title": f"{service_name} SLO Dashboard",
            "tags": ["slo", service_name],
            "timezone": "utc",
            "refresh": "30s",
            "panels": [
                # Availability gauge
                {
                    "type": "gauge",
                    "title": "Availability (30d)",
                    "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0},
                    "targets": [{
                        "expr": f'sli:http_requests:availability{{service="{service_name}"}}',
                    }],
                    "fieldConfig": {
                        "defaults": {
                            "thresholds": {
                                "steps": [
                                    {"color": "red", "value": None},
                                    {"color": "orange", "value": 0.99},
                                    {"color": "yellow", "value": 0.999},
                                    {"color": "green", "value": 0.9995},
                                ]
                            },
                            "min": 0.99, "max": 1,
                            "unit": "percentunit",
                        }
                    },
                },
                # Error budget remaining
                {
                    "type": "stat",
                    "title": "Error Budget Remaining",
                    "gridPos": {"h": 8, "w": 6, "x": 6, "y": 0},
                    "targets": [{
                        "expr": f'slo:error_budget:remaining{{service="{service_name}"}}',
                    }],
                    "fieldConfig": {
                        "defaults": {
                            "thresholds": {
                                "steps": [
                                    {"color": "red", "value": None},
                                    {"color": "orange", "value": 0.25},
                                    {"color": "green", "value": 0.5},
                                ]
                            },
                            "unit": "percentunit",
                        }
                    },
                },
                # Request rate
                {
                    "type": "timeseries",
                    "title": "Request Rate",
                    "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
                    "targets": [
                        {
                            "expr": f'sum(rate(http_requests_total{{service="{service_name}"}}[5m])) by (status)',
                            "legendFormat": "{{{{status}}}}",
                        },
                    ],
                },
                # Latency heatmap
                {
                    "type": "heatmap",
                    "title": "Request Latency Distribution",
                    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
                    "targets": [{
                        "expr": f'sum(rate(http_request_duration_seconds_bucket{{service="{service_name}"}}[5m])) by (le)',
                        "format": "heatmap",
                    }],
                },
                # P50/P95/P99 latency
                {
                    "type": "timeseries",
                    "title": "Latency Percentiles",
                    "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
                    "targets": [
                        {
                            "expr": f'histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket{{service="{service_name}"}}[5m])) by (le))',
                            "legendFormat": "P50",
                        },
                        {
                            "expr": f'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{{service="{service_name}"}}[5m])) by (le))',
                            "legendFormat": "P95",
                        },
                        {
                            "expr": f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{{service="{service_name}"}}[5m])) by (le))',
                            "legendFormat": "P99",
                        },
                    ],
                },
            ],
        },
    }


# --- Key Prometheus queries ---

USEFUL_QUERIES = {
    # RED method (Rate, Errors, Duration)
    "request_rate": 'sum(rate(http_requests_total[5m])) by (service)',
    "error_rate": 'sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))',
    "p99_latency": 'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))',

    # USE method (Utilization, Saturation, Errors)
    "cpu_utilization": 'avg(rate(container_cpu_usage_seconds_total[5m])) by (pod) / avg(container_spec_cpu_quota/container_spec_cpu_period) by (pod)',
    "memory_utilization": 'container_memory_working_set_bytes / container_spec_memory_limit_bytes',
    "pod_restarts": 'rate(kube_pod_container_status_restarts_total[1h])',
}
```

Monitoring patterns:
1. **Recording rules** — pre-compute expensive SLI queries for fast dashboards
2. **Error budget** — track remaining budget as % of allowed downtime
3. **RED method** — Rate, Errors, Duration for request-driven services
4. **Latency percentiles** — P50/P95/P99 from histogram buckets
5. **Dashboard as code** — generate Grafana JSON programmatically for consistency'''
    ),
]
"""
