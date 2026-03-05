"""
Batch P2 — DevOps: GitOps, Pulumi, platform engineering, observability.
"""

PAIRS = [
    # --- 1. GitOps with ArgoCD ---
    (
        "gitops_argocd_production",
        "Explain GitOps principles and build a production ArgoCD setup with app-of-apps pattern, "
        "progressive delivery (canary/blue-green), secrets management, and multi-cluster deployment. "
        "Include the YAML manifests and explain why each design decision matters.",
        """\
# GitOps with ArgoCD: Production-Grade Continuous Delivery

## GitOps Principles

GitOps is a paradigm where **Git is the single source of truth for declarative infrastructure
and applications**. The key principles:

1. **Declarative**: The entire system is described declaratively (YAML/JSON)
2. **Versioned and immutable**: Git provides the audit trail and rollback capability
3. **Pulled automatically**: Agents (ArgoCD) pull desired state from Git
4. **Continuously reconciled**: Drift from desired state is automatically corrected

**Why GitOps over CI/CD push?**
- Push-based: CI pipeline has cluster credentials, pushes changes → security risk, no drift detection
- Pull-based: ArgoCD lives IN the cluster, pulls from Git → no external credential exposure, continuous reconciliation

## Repository Structure

```
gitops-repo/
├── apps/                    # ArgoCD Application manifests
│   ├── root-app.yaml        # App-of-apps root
│   ├── staging/
│   │   ├── api.yaml
│   │   └── web.yaml
│   └── production/
│       ├── api.yaml
│       └── web.yaml
├── base/                    # Kustomize bases (shared across envs)
│   ├── api/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── hpa.yaml
│   │   └── kustomization.yaml
│   └── web/
│       ├── deployment.yaml
│       ├── service.yaml
│       └── kustomization.yaml
├── overlays/                # Environment-specific patches
│   ├── staging/
│   │   ├── api/
│   │   │   ├── replicas-patch.yaml
│   │   │   └── kustomization.yaml
│   │   └── web/
│   └── production/
│       ├── api/
│       │   ├── replicas-patch.yaml
│       │   ├── resources-patch.yaml
│       │   └── kustomization.yaml
│       └── web/
└── charts/                  # Helm charts for third-party
    └── values/
        ├── staging/
        └── production/
```

## App-of-Apps Pattern

Instead of registering each application manually, one root app manages all others:

```yaml
# apps/root-app.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://github.com/myorg/gitops-repo.git
    targetRevision: main
    path: apps/production  # Contains Application manifests for all prod apps
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true       # Delete resources no longer in Git
      selfHeal: true    # Fix manual changes (drift correction)
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground

# apps/production/api.yaml — managed by root app
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: api-production
  namespace: argocd
  labels:
    app.kubernetes.io/part-of: production
  annotations:
    # Notification on sync failure
    notifications.argoproj.io/subscribe.on-sync-failed.slack: deployments
spec:
  project: production
  source:
    repoURL: https://github.com/myorg/gitops-repo.git
    targetRevision: main
    path: overlays/production/api
  destination:
    server: https://kubernetes.default.svc
    namespace: api-production
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    retry:
      limit: 3
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
  # Health checks — ArgoCD waits for these before marking "Healthy"
  ignoreDifferences:
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas  # Ignore HPA-managed replica count
```

## Progressive Delivery with Argo Rollouts

```yaml
# base/api/rollout.yaml — replaces Deployment
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: api
spec:
  replicas: 10
  revisionHistoryLimit: 3
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: myorg/api:v2.1.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
  strategy:
    canary:
      # Traffic splitting — gradual rollout
      steps:
        - setWeight: 5          # 5% traffic to canary
        - pause: {duration: 2m} # Wait 2 minutes
        - analysis:              # Run automated analysis
            templates:
              - templateName: success-rate
            args:
              - name: service-name
                value: api
        - setWeight: 25         # 25% if analysis passed
        - pause: {duration: 5m}
        - setWeight: 50
        - pause: {duration: 5m}
        - setWeight: 100        # Full rollout

      # Automatic rollback triggers
      canaryMetadata:
        labels:
          role: canary
      stableMetadata:
        labels:
          role: stable

      # Traffic management via Istio/Nginx
      trafficRouting:
        nginx:
          stableIngress: api-stable
          additionalIngressAnnotations:
            canary-by-header: X-Canary

---
# Analysis template — automated canary validation
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: success-rate
spec:
  args:
    - name: service-name
  metrics:
    - name: success-rate
      # Query Prometheus for canary error rate
      interval: 30s
      count: 5              # Run 5 measurements
      successCondition: result[0] >= 0.99  # 99% success rate
      failureLimit: 2       # Allow 2 failures before abort
      provider:
        prometheus:
          address: http://prometheus:9090
          query: |
            sum(rate(http_requests_total{
              service="{{args.service-name}}",
              role="canary",
              status=~"2.."
            }[2m])) /
            sum(rate(http_requests_total{
              service="{{args.service-name}}",
              role="canary"
            }[2m]))
    - name: latency-p99
      interval: 30s
      count: 5
      successCondition: result[0] <= 500  # P99 under 500ms
      failureLimit: 2
      provider:
        prometheus:
          address: http://prometheus:9090
          query: |
            histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{
              service="{{args.service-name}}",
              role="canary"
            }[2m]))
```

## Secrets Management

**Never store secrets in Git.** Options:

```yaml
# Option 1: External Secrets Operator (recommended)
# Syncs secrets from AWS Secrets Manager / Vault / GCP SM into K8s Secrets
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: api-secrets
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: ClusterSecretStore
  target:
    name: api-secrets
    creationPolicy: Owner
  data:
    - secretKey: DATABASE_URL
      remoteRef:
        key: production/api/database-url
    - secretKey: API_KEY
      remoteRef:
        key: production/api/api-key

# Option 2: Sealed Secrets (encrypted in Git)
# Encrypt with kubeseal, only the controller in-cluster can decrypt
# kubeseal --format=yaml < secret.yaml > sealed-secret.yaml
apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: api-secrets
spec:
  encryptedData:
    DATABASE_URL: AgBy3i... # Encrypted, safe to commit
    API_KEY: AgDf8k...
```

## Multi-Cluster Deployment

```yaml
# ArgoCD ApplicationSet — deploy to multiple clusters from one definition
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: api-multi-cluster
  namespace: argocd
spec:
  generators:
    - clusters:
        selector:
          matchLabels:
            env: production
        # ArgoCD must have these clusters registered
  template:
    metadata:
      name: 'api-{{name}}'  # Templated per cluster
    spec:
      project: production
      source:
        repoURL: https://github.com/myorg/gitops-repo.git
        targetRevision: main
        path: 'overlays/production/api'
      destination:
        server: '{{server}}'
        namespace: api-production
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
```

## Key Decisions Explained

1. **Kustomize over Helm for applications**: Helm templates are harder to review in PRs.
   Kustomize overlays show the actual YAML being applied.

2. **App-of-apps over ApplicationSets**: App-of-apps gives more control per application.
   ApplicationSets are better for homogeneous deployments across clusters.

3. **Argo Rollouts over native Deployments**: Deployments only support rolling updates.
   Rollouts add canary, blue-green, and automated analysis — essential for production.

4. **External Secrets over Sealed Secrets**: External Secrets supports rotation and pulls
   from existing secret managers. Sealed Secrets require re-encryption on key rotation.

5. **Automated sync + selfHeal**: Without selfHeal, manual `kubectl` changes persist
   until next Git commit. With selfHeal, ArgoCD continuously enforces Git state.
"""
    ),

    # --- 2. Pulumi Infrastructure as Code ---
    (
        "pulumi_iac_typescript",
        "Explain Pulumi's approach to Infrastructure as Code using real programming languages, "
        "compare it with Terraform's HCL approach, and build a production AWS infrastructure "
        "(VPC, ECS Fargate, RDS, CDN) in TypeScript with proper patterns.",
        """\
# Pulumi: Infrastructure as Code with Real Languages

## Why Pulumi over Terraform?

| Aspect | Terraform (HCL) | Pulumi (TypeScript/Python/Go) |
|--------|-----------------|-------------------------------|
| Language | Domain-specific (HCL) | General-purpose (TS, Python, Go, C#) |
| Loops | `count`, `for_each` (limited) | Native `for`, `map`, `filter` |
| Conditionals | Ternary only | Full `if/else`, `switch` |
| Testing | Limited (`terraform test`) | Standard test frameworks (Jest, pytest) |
| Abstraction | Modules (file-based) | Classes, functions, packages |
| Type safety | None (stringly-typed) | Full type checking |
| IDE support | Basic | Full autocomplete, refactoring |
| State | S3/Consul/Cloud | Pulumi Cloud (free) or self-managed |

**Key insight**: Terraform invented a language to describe infrastructure. Pulumi uses
languages that already exist. This means you can use NPM packages, write unit tests,
create class hierarchies, and apply every software engineering practice to infra code.

## Production AWS Stack in TypeScript

```typescript
import * as pulumi from "@pulumi/pulumi";
import * as aws from "@pulumi/aws";
import * as awsx from "@pulumi/awsx";  // Higher-level components

const config = new pulumi.Config();
const environment = pulumi.getStack();  // "staging" or "production"
const dbPassword = config.requireSecret("dbPassword");

// ============================================================
// VPC — using awsx for sensible defaults
// ============================================================
const vpc = new awsx.ec2.Vpc("main", {
    cidrBlock: "10.0.0.0/16",
    numberOfAvailabilityZones: environment === "production" ? 3 : 2,
    natGateways: {
        strategy: environment === "production"
            ? awsx.ec2.NatGatewayStrategy.OnePerAz  // HA but expensive
            : awsx.ec2.NatGatewayStrategy.Single,    // Cost-effective for staging
    },
    subnetSpecs: [
        { type: awsx.ec2.SubnetType.Public, cidrMask: 24 },
        { type: awsx.ec2.SubnetType.Private, cidrMask: 24 },
        { type: awsx.ec2.SubnetType.Isolated, cidrMask: 24 },  // For RDS
    ],
    tags: { Environment: environment },
});

// ============================================================
// RDS PostgreSQL — in isolated subnet
// ============================================================
const dbSubnetGroup = new aws.rds.SubnetGroup("db", {
    subnetIds: vpc.isolatedSubnetIds,
});

const dbSecurityGroup = new aws.ec2.SecurityGroup("db", {
    vpcId: vpc.vpcId,
    ingress: [{
        protocol: "tcp",
        fromPort: 5432,
        toPort: 5432,
        securityGroups: [],  // Will add ECS SG after creation
    }],
});

const db = new aws.rds.Instance("main", {
    engine: "postgres",
    engineVersion: "16.1",
    instanceClass: environment === "production"
        ? "db.r6g.xlarge"
        : "db.t4g.micro",
    allocatedStorage: 50,
    maxAllocatedStorage: 200,  // Autoscaling
    dbName: "hiveai",
    username: "admin",
    password: dbPassword,
    dbSubnetGroupName: dbSubnetGroup.name,
    vpcSecurityGroupIds: [dbSecurityGroup.id],
    multiAz: environment === "production",
    backupRetentionPeriod: environment === "production" ? 30 : 7,
    deletionProtection: environment === "production",
    performanceInsightsEnabled: true,
    storageEncrypted: true,
    tags: { Environment: environment },
});

// ============================================================
// ECS Fargate Service
// ============================================================
const cluster = new aws.ecs.Cluster("main", {
    settings: [{
        name: "containerInsights",
        value: "enabled",
    }],
});

// Application Load Balancer
const alb = new awsx.lb.ApplicationLoadBalancer("api", {
    subnetIds: vpc.publicSubnetIds,
    defaultTargetGroup: {
        port: 8080,
        protocol: "HTTP",
        healthCheck: {
            path: "/healthz",
            interval: 15,
            healthyThreshold: 2,
            unhealthyThreshold: 3,
        },
        deregistrationDelay: 30,
    },
});

// ECS Task Definition + Service
const apiService = new awsx.ecs.FargateService("api", {
    cluster: cluster.arn,
    desiredCount: environment === "production" ? 3 : 1,
    networkConfiguration: {
        subnets: vpc.privateSubnetIds,
        securityGroups: [apiSecurityGroup.id],
    },
    taskDefinitionArgs: {
        container: {
            name: "api",
            image: `myorg/api:${config.require("apiVersion")}`,
            cpu: 512,
            memory: 1024,
            portMappings: [{
                containerPort: 8080,
                targetGroup: alb.defaultTargetGroup,
            }],
            environment: [
                { name: "NODE_ENV", value: environment },
                { name: "PORT", value: "8080" },
            ],
            secrets: [
                {
                    name: "DATABASE_URL",
                    valueFrom: dbUrlSecret.arn,  // From AWS Secrets Manager
                },
            ],
            logConfiguration: {
                logDriver: "awslogs",
                options: {
                    "awslogs-group": `/ecs/${environment}/api`,
                    "awslogs-region": aws.getRegion().then(r => r.name),
                    "awslogs-stream-prefix": "api",
                },
            },
        },
    },
});

// Auto-scaling
const scaling = new aws.appautoscaling.Target("api", {
    maxCapacity: environment === "production" ? 20 : 3,
    minCapacity: environment === "production" ? 3 : 1,
    resourceId: pulumi.interpolate`service/${cluster.name}/${apiService.service.name}`,
    scalableDimension: "ecs:service:DesiredCount",
    serviceNamespace: "ecs",
});

new aws.appautoscaling.Policy("api-cpu", {
    policyType: "TargetTrackingScaling",
    resourceId: scaling.resourceId,
    scalableDimension: scaling.scalableDimension,
    serviceNamespace: scaling.serviceNamespace,
    targetTrackingScalingPolicyConfiguration: {
        predefinedMetricSpecification: {
            predefinedMetricType: "ECSServiceAverageCPUUtilization",
        },
        targetValue: 70,
        scaleInCooldown: 300,
        scaleOutCooldown: 60,
    },
});

// ============================================================
// CloudFront CDN
// ============================================================
const cdn = new aws.cloudfront.Distribution("main", {
    origins: [{
        originId: "alb",
        domainName: alb.loadBalancer.dnsName,
        customOriginConfig: {
            httpPort: 80,
            httpsPort: 443,
            originProtocolPolicy: "https-only",
            originSslProtocols: ["TLSv1.2"],
        },
    }],
    enabled: true,
    defaultCacheBehavior: {
        targetOriginId: "alb",
        viewerProtocolPolicy: "redirect-to-https",
        allowedMethods: ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
        cachedMethods: ["GET", "HEAD"],
        forwardedValues: {
            queryString: true,
            headers: ["Authorization", "Host"],
            cookies: { forward: "none" },
        },
        minTtl: 0,
        defaultTtl: 0,     // Don't cache API responses by default
        maxTtl: 86400,
        compress: true,
    },
    restrictions: {
        geoRestriction: { restrictionType: "none" },
    },
    viewerCertificate: {
        cloudfrontDefaultCertificate: true,
    },
});

// ============================================================
// Outputs
// ============================================================
export const vpcId = vpc.vpcId;
export const dbEndpoint = db.endpoint;
export const albDns = alb.loadBalancer.dnsName;
export const cdnDomain = cdn.domainName;
export const ecsCluster = cluster.name;
```

## Unit Testing Pulumi with Jest

```typescript
// __tests__/infrastructure.test.ts
import * as pulumi from "@pulumi/pulumi";

// Mock Pulumi runtime
pulumi.runtime.setMocks({
    newResource: (args) => ({ id: `${args.name}-id`, state: args.inputs }),
    call: (args) => args.inputs,
});

describe("Production infrastructure", () => {
    let infra: typeof import("../index");

    beforeAll(async () => {
        infra = await import("../index");
    });

    test("RDS has encryption enabled", async () => {
        const encrypted = await new Promise<boolean>((resolve) =>
            pulumi.all([infra.dbEncrypted]).apply(([e]) => resolve(e))
        );
        expect(encrypted).toBe(true);
    });

    test("RDS has multi-AZ in production", async () => {
        const multiAz = await new Promise<boolean>((resolve) =>
            pulumi.all([infra.dbMultiAz]).apply(([m]) => resolve(m))
        );
        expect(multiAz).toBe(true);
    });

    test("ECS service has minimum 3 replicas in production", async () => {
        const count = await new Promise<number>((resolve) =>
            pulumi.all([infra.desiredCount]).apply(([c]) => resolve(c))
        );
        expect(count).toBeGreaterThanOrEqual(3);
    });
});
```

## Key Patterns

1. **Stack-based environments**: `pulumi stack select staging` vs `production` — same code, different configs
2. **ComponentResources**: Create reusable infrastructure classes (like a `DatabaseCluster` component)
3. **Config secrets**: `pulumi config set --secret dbPassword xyz` — encrypted in state
4. **Stack references**: Import outputs from other stacks (e.g., network stack → app stack)
5. **Policy as Code**: `pulumi policy` to enforce rules (e.g., "all S3 buckets must be encrypted")
"""
    ),

    # --- 3. Observability Stack ---
    (
        "observability_opentelemetry",
        "Build a comprehensive observability stack using OpenTelemetry, covering the three pillars "
        "(traces, metrics, logs), auto-instrumentation, custom spans, correlation between signals, "
        "and a production Grafana dashboard setup. Show code in Python and Go.",
        """\
# Production Observability with OpenTelemetry

## The Three Pillars — And Why Correlation Matters

```
                    Observability Pillars

   Traces                Metrics               Logs
   (What happened?)      (How much?)            (What details?)
   ┌─────────────┐      ┌─────────────┐       ┌─────────────┐
   │ Request flow │      │ Counters    │       │ Structured  │
   │ across svcs  │      │ Histograms  │       │ events with │
   │ with timing  │      │ Gauges      │       │ context     │
   └──────┬───────┘      └──────┬──────┘       └──────┬──────┘
          │                     │                      │
          └─────────────────────┼──────────────────────┘
                                │
                    trace_id links all three
                    (exemplars in metrics → traces)
                    (trace_id in logs → trace context)
```

**Without correlation**, you have three separate data silos. **With correlation**, you can:
- See a spike in error rate metrics → click exemplar → see the exact trace → find the log with error details
- All connected by `trace_id`.

## Python: Full OTel Setup

```python
# otel_setup.py — Initialize once at application startup
import logging
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat

def setup_observability(service_name: str, version: str, otlp_endpoint: str):
    """Initialize all three pillars of observability."""

    # Shared resource — identifies this service in all telemetry
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: version,
        "deployment.environment": os.getenv("ENV", "development"),
    })

    # ── TRACES ──
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanExporter(OTLPSpanExporter(endpoint=otlp_endpoint))
    )
    trace.set_tracer_provider(tracer_provider)

    # ── METRICS ──
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=otlp_endpoint),
        export_interval_millis=30000,  # Export every 30s
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # ── LOGS ──
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=otlp_endpoint))
    )
    # Bridge Python logging → OTel logs (with trace context!)
    handler = LoggingHandler(logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)

    # ── AUTO-INSTRUMENTATION ──
    # These automatically create spans for every HTTP request, DB query, etc.
    FastAPIInstrumentor.instrument()
    SQLAlchemyInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()

    return tracer_provider, meter_provider, logger_provider
```

### Custom Instrumentation in Application Code

```python
# services/payment.py
import logging
from opentelemetry import trace, metrics

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Custom metrics
payment_counter = meter.create_counter(
    "payments.processed",
    description="Number of payments processed",
    unit="1",
)
payment_duration = meter.create_histogram(
    "payments.duration",
    description="Payment processing duration",
    unit="ms",
)
active_payments = meter.create_up_down_counter(
    "payments.active",
    description="Currently processing payments",
)

async def process_payment(order_id: str, amount: float, currency: str):
    # Custom span with rich attributes
    with tracer.start_as_current_span(
        "process_payment",
        attributes={
            "payment.order_id": order_id,
            "payment.amount": amount,
            "payment.currency": currency,
        },
    ) as span:
        active_payments.add(1)
        start = time.monotonic()

        try:
            # Child span for fraud check
            with tracer.start_as_current_span("fraud_check") as fraud_span:
                risk_score = await check_fraud(order_id, amount)
                fraud_span.set_attribute("fraud.risk_score", risk_score)

                if risk_score > 0.8:
                    span.set_status(trace.Status(trace.StatusCode.ERROR, "High fraud risk"))
                    span.add_event("payment_rejected", {"reason": "fraud_score_high"})
                    logger.warning(
                        "Payment rejected for fraud",
                        extra={"order_id": order_id, "risk_score": risk_score},
                    )
                    payment_counter.add(1, {"status": "rejected", "reason": "fraud"})
                    return {"status": "rejected"}

            # Child span for gateway call
            with tracer.start_as_current_span("gateway_charge") as gw_span:
                result = await stripe_charge(amount, currency)
                gw_span.set_attribute("gateway.transaction_id", result.tx_id)

            # Structured log with trace context automatically injected
            logger.info(
                "Payment processed successfully",
                extra={
                    "order_id": order_id,
                    "amount": amount,
                    "transaction_id": result.tx_id,
                },
            )

            payment_counter.add(1, {"status": "success", "currency": currency})
            return {"status": "success", "tx_id": result.tx_id}

        except Exception as e:
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            span.record_exception(e)
            logger.exception("Payment failed", extra={"order_id": order_id})
            payment_counter.add(1, {"status": "error", "error_type": type(e).__name__})
            raise

        finally:
            duration_ms = (time.monotonic() - start) * 1000
            payment_duration.record(duration_ms, {"currency": currency})
            active_payments.add(-1)
```

## Go: OTel Setup and Custom Instrumentation

```go
package observability

import (
    "context"
    "log/slog"
    "time"

    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
    "go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetricgrpc"
    "go.opentelemetry.io/otel/metric"
    "go.opentelemetry.io/otel/sdk/resource"
    sdktrace "go.opentelemetry.io/otel/sdk/trace"
    sdkmetric "go.opentelemetry.io/otel/sdk/metric"
    semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
    "go.opentelemetry.io/otel/trace"
)

func SetupOTel(ctx context.Context, serviceName, version string) (func(), error) {
    res := resource.NewWithAttributes(
        semconv.SchemaURL,
        semconv.ServiceName(serviceName),
        semconv.ServiceVersion(version),
    )

    // Traces
    traceExporter, _ := otlptracegrpc.New(ctx)
    tp := sdktrace.NewTracerProvider(
        sdktrace.WithBatcher(traceExporter),
        sdktrace.WithResource(res),
        sdktrace.WithSampler(sdktrace.ParentBased(
            sdktrace.TraceIDRatioBased(0.1), // Sample 10% in production
        )),
    )
    otel.SetTracerProvider(tp)

    // Metrics
    metricExporter, _ := otlpmetricgrpc.New(ctx)
    mp := sdkmetric.NewMeterProvider(
        sdkmetric.WithReader(sdkmetric.NewPeriodicReader(metricExporter)),
        sdkmetric.WithResource(res),
    )
    otel.SetMeterProvider(mp)

    cleanup := func() {
        tp.Shutdown(ctx)
        mp.Shutdown(ctx)
    }
    return cleanup, nil
}

// Usage in application code
var (
    tracer        = otel.Tracer("myapp/orders")
    meter         = otel.Meter("myapp/orders")
    orderCounter  metric.Int64Counter
    orderDuration metric.Float64Histogram
)

func init() {
    orderCounter, _ = meter.Int64Counter("orders.created")
    orderDuration, _ = meter.Float64Histogram("orders.duration_ms")
}

func CreateOrder(ctx context.Context, req OrderRequest) (*Order, error) {
    ctx, span := tracer.Start(ctx, "CreateOrder",
        trace.WithAttributes(
            attribute.String("order.customer_id", req.CustomerID),
            attribute.Float64("order.total", req.Total),
        ),
    )
    defer span.End()
    start := time.Now()

    // Validate — child span
    ctx, valSpan := tracer.Start(ctx, "ValidateOrder")
    if err := validate(req); err != nil {
        valSpan.RecordError(err)
        valSpan.End()
        return nil, err
    }
    valSpan.End()

    // Save to DB — auto-instrumented if using otelsql
    order, err := repo.Save(ctx, req)
    if err != nil {
        span.RecordError(err)
        orderCounter.Add(ctx, 1, metric.WithAttributes(
            attribute.String("status", "error"),
        ))
        return nil, err
    }

    // Structured log with trace context
    slog.InfoContext(ctx, "order created",
        "order_id", order.ID,
        "total", req.Total,
        "trace_id", span.SpanContext().TraceID().String(),
    )

    orderCounter.Add(ctx, 1, metric.WithAttributes(
        attribute.String("status", "success"),
    ))
    orderDuration.Record(ctx, float64(time.Since(start).Milliseconds()))

    return order, nil
}
```

## OTel Collector Pipeline

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 1000
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
  # Add service graph metrics from traces
  servicegraph:
    metrics_exporter: prometheus
    latency_histogram_buckets: [1, 5, 10, 50, 100, 500, 1000]
  # Tail sampling — keep all error traces, sample 10% of success
  tail_sampling:
    policies:
      - name: errors
        type: status_code
        status_code: {status_codes: [ERROR]}
      - name: slow
        type: latency
        latency: {threshold_ms: 1000}
      - name: sample-rest
        type: probabilistic
        probabilistic: {sampling_percentage: 10}

exporters:
  otlp/tempo:
    endpoint: tempo:4317
    tls: { insecure: true }
  prometheus:
    endpoint: 0.0.0.0:8889
  loki:
    endpoint: http://loki:3100/loki/api/v1/push

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, tail_sampling, batch]
      exporters: [otlp/tempo]
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [prometheus]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [loki]
```

## Key Insights

1. **Start with auto-instrumentation** — it covers HTTP, DB, gRPC with zero code changes
2. **Add custom spans only where business logic matters** — don't over-instrument
3. **Always propagate context** — pass `ctx` (Go) or use `contextvars` (Python) so child spans connect to parents
4. **Use tail sampling in the collector** — sample 100% of errors, 10% of success. This saves storage while keeping debuggability
5. **Exemplars connect metrics to traces** — a histogram data point links to the trace that generated it, enabling "click from dashboard to trace"
"""
    ),

    # --- 4. Platform Engineering ---
    (
        "platform_engineering_idp",
        "Explain the platform engineering approach, how to build an Internal Developer Platform (IDP), "
        "and show a complete Backstage-based developer portal with service catalog, templates, and "
        "self-service infrastructure provisioning.",
        """\
# Platform Engineering: Building an Internal Developer Platform

## What is Platform Engineering?

Platform engineering is the discipline of building and maintaining an **Internal Developer
Platform (IDP)** — a self-service layer that abstracts away infrastructure complexity so
application developers can focus on business logic.

```
Without platform engineering:
  Developer → "I need a database" → Ticket to DevOps → 3 day wait → Config manually

With platform engineering:
  Developer → Self-service portal → Click "New PostgreSQL" → Running in 5 minutes
  (Platform team built the automation once, everyone uses it)
```

### The Platform Maturity Model

```
Level 0: Manual         → kubectl apply, manual cloud console clicks
Level 1: Scripted       → Shell scripts, basic CI/CD, shared runbooks
Level 2: Self-service   → Templates, automated provisioning, service catalog
Level 3: Optimized      → Golden paths, automated compliance, cost optimization
Level 4: Intelligent    → AI-assisted troubleshooting, predictive scaling
```

## Backstage: The Open-Source IDP Framework

Backstage (by Spotify, now CNCF) provides three core features:

1. **Software Catalog**: Registry of all services, libraries, APIs, infrastructure
2. **Software Templates**: Self-service scaffolding for new projects
3. **TechDocs**: Documentation as code, rendered in the portal

### Software Catalog Configuration

```yaml
# catalog-info.yaml — lives in every service's repo
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: payment-service
  description: Handles payment processing and settlement
  tags:
    - python
    - fastapi
    - critical
  annotations:
    # Link to monitoring, CI, docs, etc.
    grafana/dashboard-selector: "service=payment-service"
    github.com/project-slug: myorg/payment-service
    backstage.io/techdocs-ref: dir:.
    pagerduty.com/integration-key: $PAGERDUTY_KEY
    sonarqube.org/project-key: myorg:payment-service
  links:
    - url: https://api.myorg.com/payments/docs
      title: API Documentation
      icon: docs
spec:
  type: service
  lifecycle: production
  owner: team-payments       # Links to a Group entity
  system: checkout-system    # Links to a System entity
  providesApis:
    - payment-api            # Links to an API entity
  consumesApis:
    - user-api
    - notification-api
  dependsOn:
    - resource:payments-db
    - resource:payments-redis

---
apiVersion: backstage.io/v1alpha1
kind: API
metadata:
  name: payment-api
  description: Payment processing REST API
spec:
  type: openapi
  lifecycle: production
  owner: team-payments
  definition:
    $text: ./openapi.yaml  # Auto-renders API docs in Backstage

---
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: payments-db
  description: PostgreSQL database for payment data
spec:
  type: database
  owner: team-payments
  system: checkout-system
```

### Software Template: Self-Service New Service

```yaml
# templates/new-service/template.yaml
apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata:
  name: new-microservice
  title: Create a New Microservice
  description: |
    Scaffolds a production-ready microservice with CI/CD, monitoring,
    database, and Kubernetes deployment — all pre-configured.
  tags:
    - python
    - recommended
spec:
  owner: team-platform
  type: service

  # Input form — the developer fills this out
  parameters:
    - title: Service Details
      required:
        - name
        - owner
        - description
      properties:
        name:
          title: Service Name
          type: string
          pattern: "^[a-z][a-z0-9-]*$"
          ui:help: "Lowercase, hyphens only (e.g., user-service)"
        description:
          title: Description
          type: string
        owner:
          title: Owner Team
          type: string
          ui:field: OwnerPicker
          ui:options:
            catalogFilter:
              kind: Group

    - title: Infrastructure
      properties:
        database:
          title: Database
          type: string
          enum: ["none", "postgresql", "redis", "both"]
          default: postgresql
        cpu:
          title: CPU Request
          type: string
          enum: ["250m", "500m", "1000m"]
          default: "250m"
        memory:
          title: Memory Request
          type: string
          enum: ["256Mi", "512Mi", "1Gi"]
          default: "512Mi"
        environment:
          title: Initial Environment
          type: string
          enum: ["staging", "staging+production"]
          default: staging

  # Actions — what happens when they click "Create"
  steps:
    # 1. Fetch and render the template
    - id: fetch
      name: Fetch Template
      action: fetch:template
      input:
        url: ./skeleton  # Template files with {{ values.name }} placeholders
        values:
          name: ${{ parameters.name }}
          description: ${{ parameters.description }}
          owner: ${{ parameters.owner }}
          database: ${{ parameters.database }}
          cpu: ${{ parameters.cpu }}
          memory: ${{ parameters.memory }}

    # 2. Create GitHub repo
    - id: publish
      name: Create Repository
      action: publish:github
      input:
        repoUrl: github.com?owner=myorg&repo=${{ parameters.name }}
        description: ${{ parameters.description }}
        defaultBranch: main
        protectDefaultBranch: true
        requireCodeOwnerReview: true

    # 3. Register in Backstage catalog
    - id: register
      name: Register in Catalog
      action: catalog:register
      input:
        repoContentsUrl: ${{ steps.publish.output.repoContentsUrl }}
        catalogInfoPath: /catalog-info.yaml

    # 4. Provision infrastructure via Pulumi/Terraform
    - id: provision-infra
      name: Provision Infrastructure
      action: http:backstage:request
      input:
        method: POST
        path: /api/proxy/infra-api/provision
        headers:
          Content-Type: application/json
        body:
          serviceName: ${{ parameters.name }}
          database: ${{ parameters.database }}
          environment: ${{ parameters.environment }}

    # 5. Create PagerDuty service
    - id: pagerduty
      name: Create PagerDuty Service
      action: pagerduty:create-service
      input:
        name: ${{ parameters.name }}
        escalationPolicyId: ${{ parameters.owner }}-policy

  output:
    links:
      - title: Repository
        url: ${{ steps.publish.output.remoteUrl }}
      - title: Service in Catalog
        url: ${{ steps.register.output.catalogInfoUrl }}
      - title: CI/CD Pipeline
        url: https://github.com/myorg/${{ parameters.name }}/actions
```

### Template Skeleton Files

```
skeleton/
├── src/
│   ├── main.py
│   ├── config.py
│   └── routes/
│       └── health.py
├── tests/
│   └── test_health.py
├── Dockerfile
├── catalog-info.yaml       # Pre-filled with {{ values.name }}
├── .github/
│   └── workflows/
│       └── ci.yaml         # CI/CD pre-configured
├── k8s/
│   ├── base/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── kustomization.yaml
│   └── overlays/
│       ├── staging/
│       └── production/
├── pyproject.toml
└── README.md
```

## The Golden Path Concept

A golden path is the **opinionated, pre-paved way** to do something. It's not the only way,
but it's the recommended way that comes with full platform support:

```
Golden Path for "Deploy a new API":
1. Use the Backstage template (creates repo, CI/CD, monitoring, DB)
2. Write business logic in the generated service
3. Push to main → CI runs tests → ArgoCD deploys to staging
4. Create PR to promote to production → automated canary rollout
5. Monitoring dashboards auto-configured, alerts auto-created

Deviation (allowed but unsupported):
- Custom build system → You maintain it
- Different monitoring stack → No automatic dashboards
- Manual deployment → No rollback support
```

## Measuring Platform Success

The key metrics are from DORA (DevOps Research and Assessment):

1. **Deployment frequency**: How often can teams deploy? (Target: multiple per day)
2. **Lead time for changes**: Commit to production (Target: < 1 hour)
3. **Change failure rate**: % of deployments causing incidents (Target: < 5%)
4. **Time to restore**: How fast to recover from incidents (Target: < 1 hour)

Additional platform-specific metrics:
- **Time to first deploy**: New developer → first production deploy (Target: < 1 day)
- **Self-service ratio**: % of infra requests handled without platform team involvement
- **Template adoption**: % of new services using golden path templates
- **Developer satisfaction**: Regular surveys (NPS-style)

The goal of platform engineering is to make the right thing the easy thing. Developers
should WANT to use the platform because it makes them faster, not because they're forced to.
"""
    ),
]
