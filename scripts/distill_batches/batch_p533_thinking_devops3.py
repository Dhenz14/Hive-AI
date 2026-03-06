"""Phase 1H: Foundation Thinking — Data Modeling & DevOps (Part 5/5)
Performance optimization, capacity planning, cost optimization, SRE practices."""

PAIRS = [
    (
        "thinking/devops-capacity-planning",
        "Our app currently handles 5,000 daily active users. We're launching a marketing campaign that could bring 50,000 users. How do we prepare?",
        r'''<think>
Capacity planning for 10x growth:
1. Profile current resource usage per user
2. Identify bottlenecks at 10x
3. Load test at target scale
4. Plan infrastructure changes
5. Set up auto-scaling
6. Have a degradation plan

Key areas to check:
- Database (connections, query performance, storage)
- API servers (CPU, memory, concurrent connections)
- Cache (memory, hit rate)
- External services (rate limits, quotas)
</think>

## Step 1: Profile Current Usage

```python
# Calculate per-user resource consumption
current_users = 5_000
target_users = 50_000

# Database
queries_per_user_per_day = 200  # From slow query log
current_qps = 5000 * 200 / 86400  # ≈ 11.6 QPS
target_qps = 50000 * 200 / 86400  # ≈ 115.7 QPS

# API
requests_per_user_per_day = 150
current_rps = 5000 * 150 / 86400  # ≈ 8.7 RPS
target_rps = 50000 * 150 / 86400  # ≈ 86.8 RPS
peak_rps = target_rps * 3  # 3x peak factor ≈ 260 RPS

# Storage
storage_per_user_mb = 50  # Files, images, data
target_storage = 50000 * 50 / 1024  # ≈ 2.4 TB
```

## Step 2: Identify Bottlenecks

```
Component          Current       10x Target     Bottleneck?
─────────          ───────       ──────────     ──────────
API servers        2 × t3.medium  Need 6+       Auto-scale ✓
Database (RDS)     db.t3.medium   db.r5.large   Upgrade needed ⚠️
  Connections      20             200           PgBouncer needed ⚠️
  Storage          10 GB          100 GB        Resize ✓
Redis              cache.t3.micro cache.t3.small Upgrade ⚠️
S3 Storage         50 GB          2.4 TB        No limit ✓
CDN                N/A            Needed        Add CloudFront ⚠️
Email service      500/day        5000/day      Check plan limits ⚠️
```

## Step 3: Load Test

```python
# locustfile.py
from locust import HttpUser, task, between

class WebUser(HttpUser):
    wait_time = between(1, 5)

    @task(5)
    def browse(self):
        self.client.get("/api/feed")

    @task(2)
    def search(self):
        self.client.get("/api/search?q=test")

    @task(1)
    def create(self):
        self.client.post("/api/posts", json={"text": "Hello"})
```

```bash
# Ramp to 260 concurrent users (peak RPS target)
locust -f locustfile.py --headless \
    -u 260 -r 10 --run-time 10m \
    --html report.html
```

## Step 4: Prepare Infrastructure

```
Before Campaign:
□ Database: Upgrade to db.r5.large
□ Add PgBouncer (connection pooling)
□ Add read replica for search queries
□ Redis: Upgrade to cache.t3.small
□ Enable CDN for static assets
□ Set up auto-scaling (min:3, max:15 pods)
□ Pre-warm caches with popular content
□ Check email service limits (upgrade plan)
□ Enable rate limiting (protect against abuse)
□ Verify backup/restore works at new data volume

Campaign Day:
□ Monitor dashboard open
□ On-call team aware
□ Rollback plan ready
□ Feature flags ready to disable non-critical features
```

## Step 5: Degradation Plan

```python
# If load exceeds capacity, gracefully degrade:
FEATURE_FLAGS = {
    'recommendations': True,    # First to disable (expensive)
    'real_time_search': True,   # Switch to cached results
    'notifications': True,      # Queue instead of real-time
    'image_thumbnails': True,   # Serve originals instead
    'analytics_tracking': True, # Disable non-critical
}
```

**Rule**: Don't guess — load test at target scale. The bottleneck is never where you think it is.'''
    ),
    (
        "thinking/devops-cost-optimization",
        "Our AWS bill is $15,000/month and growing. We're a 5-person startup. Where should I look to cut costs?",
        r'''<think>
Common AWS cost waste:
1. Oversized instances (paying for unused CPU/RAM)
2. Idle resources (dev environments running 24/7)
3. No reserved instances/savings plans
4. Unattached EBS volumes
5. Oversized RDS instances
6. No lifecycle policies on S3
7. NAT Gateway costs
8. Data transfer between AZs

Let me provide a systematic checklist.
</think>

## Cost Optimization Checklist

### 1. Right-Size Instances (Usually 30-50% Savings)

```bash
# Check actual CPU/memory usage
aws cloudwatch get-metric-statistics \
    --namespace AWS/EC2 \
    --metric-name CPUUtilization \
    --dimensions Name=InstanceId,Value=i-xxx \
    --start-time 2024-01-01 --end-time 2024-01-31 \
    --period 86400 --statistics Average

# If average CPU < 20%, you're oversized
# t3.xlarge ($0.17/hr) → t3.medium ($0.04/hr) = 76% savings
```

### 2. Stop Dev/Staging Outside Hours

```python
# Lambda function: stop dev instances at 7PM, start at 8AM
import boto3

def lambda_handler(event, context):
    ec2 = boto3.client('ec2')
    action = event.get('action', 'stop')

    instances = ec2.describe_instances(
        Filters=[{'Name': 'tag:Environment', 'Values': ['dev', 'staging']}]
    )

    instance_ids = [
        i['InstanceId']
        for r in instances['Reservations']
        for i in r['Instances']
    ]

    if action == 'stop':
        ec2.stop_instances(InstanceIds=instance_ids)
    else:
        ec2.start_instances(InstanceIds=instance_ids)

# 13 hours off × 30 days = 60% savings on dev instances
```

### 3. Reserved Instances / Savings Plans

```
On-demand:  t3.medium = $0.0416/hr × 730 hrs = $30.37/month
Reserved:   t3.medium = $0.0262/hr × 730 hrs = $19.13/month (37% off)
Spot:       t3.medium = $0.0125/hr × 730 hrs = $9.13/month  (70% off)

For stable workloads: 1-year reserved instance
For batch/test workloads: Spot instances
```

### 4. S3 Lifecycle Policies

```json
{
    "Rules": [{
        "ID": "ArchiveOldData",
        "Status": "Enabled",
        "Transitions": [
            {"Days": 30, "StorageClass": "STANDARD_IA"},
            {"Days": 90, "StorageClass": "GLACIER"}
        ],
        "Expiration": {"Days": 365}
    }]
}
```

```
S3 Standard:     $0.023/GB/month
S3 Infrequent:   $0.0125/GB/month (46% cheaper)
S3 Glacier:      $0.004/GB/month  (83% cheaper)
```

### 5. Quick Wins Checklist

```
□ Delete unattached EBS volumes (check monthly)
□ Delete old snapshots (keep last 30 days)
□ Delete unused Elastic IPs ($3.65/month each if unattached)
□ Reduce RDS to single-AZ for dev/staging
□ Use Aurora Serverless for low-traffic databases
□ Move static assets to S3 + CloudFront (cheaper than serving from EC2)
□ Use NAT Instance instead of NAT Gateway ($32/month vs $32/month + $0.045/GB)
□ Enable S3 Intelligent-Tiering for unknown access patterns
□ Review data transfer costs (cross-AZ and internet egress)
```

### Typical $15K → $7K Breakdown

```
Right-sizing instances:    -$3,000 (oversized EC2 + RDS)
Stop dev outside hours:    -$1,500 (60% of dev costs)
Reserved instances:        -$2,000 (37% off stable workloads)
S3 lifecycle policies:     -$500 (archive old data)
Cleanup unused resources:  -$1,000 (EBS, snapshots, IPs)
Total saved:               ~$8,000/month
```'''
    ),
    (
        "thinking/devops-slo-sli-sla",
        "Our CEO keeps asking 'is our service reliable?' and we don't have a clear answer. How do we define and measure reliability?",
        r'''<think>
SRE concepts:
- SLI (Service Level Indicator): measurable metric (latency, error rate, uptime)
- SLO (Service Level Objective): target for the SLI (99.9% uptime)
- SLA (Service Level Agreement): contract with consequences (refund if below SLO)
- Error budget: how much unreliability you can "afford"

For a startup, define SLOs internally first. SLAs come later with enterprise contracts.
</think>

## Define What "Reliable" Means

### Step 1: Choose SLIs (What to Measure)

```
Availability:  % of requests that succeed (non-5xx)
Latency:       % of requests faster than threshold
Correctness:   % of requests returning correct data
Freshness:     % of data updated within expected time
```

### Step 2: Set SLOs (Targets)

```
API Availability:  99.9%  (43 minutes downtime/month allowed)
API Latency:       99%   of requests complete in < 500ms
                   99.9% of requests complete in < 2000ms
Data Freshness:    99.5% of dashboard data < 5 minutes old
```

### Step 3: Calculate Error Budget

```
99.9% SLO = 0.1% error budget = 43 minutes/month

If you've used 30 minutes this month:
  → 13 minutes remaining
  → Ship features carefully
  → Maybe skip that risky migration

If you've used 5 minutes this month:
  → 38 minutes remaining
  → Ship faster, take more risks
  → Deploy that experimental feature
```

### Step 4: Measure Automatically

```python
# Prometheus metrics
from prometheus_client import Counter, Histogram

request_total = Counter('http_requests_total', 'Total requests',
                        ['method', 'endpoint', 'status'])
request_latency = Histogram('http_request_duration_seconds',
                            'Request latency',
                            ['method', 'endpoint'],
                            buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5])
```

```yaml
# Prometheus recording rules
groups:
  - name: slo
    rules:
      # Availability SLI: % of non-5xx requests
      - record: sli:availability:ratio_rate5m
        expr: |
          1 - (
            rate(http_requests_total{status=~"5.."}[5m])
            / rate(http_requests_total[5m])
          )

      # Latency SLI: % of requests < 500ms
      - record: sli:latency:ratio_rate5m
        expr: |
          rate(http_request_duration_seconds_bucket{le="0.5"}[5m])
          / rate(http_request_duration_seconds_count[5m])

      # Error budget remaining this month
      - record: slo:error_budget:remaining
        expr: |
          1 - (
            (1 - sli:availability:ratio_rate30d) / (1 - 0.999)
          )
```

### Step 5: Dashboard for the CEO

```
┌─────────────────────────────────────────┐
│          Service Reliability            │
│                                         │
│  Availability:  99.95%  ✅ (SLO: 99.9%) │
│  Latency p99:   420ms   ✅ (SLO: 500ms) │
│  Error Budget:  72% remaining           │
│  ████████████████░░░░░░░                │
│                                         │
│  Status: HEALTHY — safe to ship         │
└─────────────────────────────────────────┘
```

### The Error Budget Policy

```markdown
## Error Budget Policy

### When error budget is > 50%:
- Ship features at normal pace
- Approve risky deployments
- Run experiments

### When error budget is 10-50%:
- Slow down feature work
- Prioritize reliability improvements
- Review deployment frequency

### When error budget is exhausted (0%):
- Freeze feature deployments
- All engineering on reliability
- Only bug fixes and performance improvements
- Resume features when budget recovers
```

This gives the CEO a single number: "72% error budget remaining — we're reliable and can ship faster."'''
    ),
    (
        "thinking/devops-feature-flags",
        "We want to deploy code to production without releasing features to users. We also want to A/B test and do gradual rollouts. How?",
        r'''<think>
Feature flags (feature toggles) decouple deployment from release. Deploy code anytime, enable features separately.

Types:
1. Release toggles: deploy dark, enable when ready
2. Experiment toggles: A/B testing
3. Ops toggles: circuit breakers, kill switches
4. Permission toggles: premium features

Implementation options:
1. Simple: config file or environment variables
2. Database-backed: admin UI for toggling
3. Service: LaunchDarkly, Unleash, Flagsmith
</think>

## Simple Feature Flags (Start Here)

```python
# feature_flags.py
import os

class FeatureFlags:
    def __init__(self):
        self._flags = {}
        self._overrides = {}

    def register(self, name: str, default: bool = False):
        # Check env var first, then default
        env_val = os.environ.get(f"FF_{name.upper()}")
        if env_val is not None:
            self._flags[name] = env_val.lower() in ('1', 'true', 'yes')
        else:
            self._flags[name] = default

    def is_enabled(self, name: str, user_id: str = None) -> bool:
        # User-specific overrides (for beta testers)
        if user_id and (name, user_id) in self._overrides:
            return self._overrides[(name, user_id)]
        return self._flags.get(name, False)

    def enable_for_user(self, name: str, user_id: str):
        self._overrides[(name, user_id)] = True

flags = FeatureFlags()
flags.register('new_checkout', default=False)
flags.register('dark_mode', default=True)
flags.register('ai_recommendations', default=False)
```

## Usage in Code

```python
@app.get("/api/checkout")
def checkout(request):
    if flags.is_enabled('new_checkout', user_id=request.user.id):
        return new_checkout_flow(request)
    return legacy_checkout_flow(request)

# In templates
def render_dashboard(user):
    context = {
        'show_ai_panel': flags.is_enabled('ai_recommendations', user.id),
        'dark_mode': flags.is_enabled('dark_mode', user.id),
    }
    return template.render(**context)
```

## Percentage Rollout

```python
import hashlib

def is_enabled_for_percentage(flag_name: str, user_id: str, percentage: int) -> bool:
    """Deterministic: same user always gets same result."""
    hash_input = f"{flag_name}:{user_id}"
    hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
    return (hash_value % 100) < percentage

# Gradual rollout: 10% → 25% → 50% → 100%
NEW_SEARCH_ROLLOUT = 25  # Currently at 25%

@app.get("/api/search")
def search(request):
    if is_enabled_for_percentage('new_search', request.user.id, NEW_SEARCH_ROLLOUT):
        return new_search_engine(request)
    return old_search_engine(request)
```

## Database-Backed (With Admin UI)

```python
# models.py
class FeatureFlag(db.Model):
    name = db.Column(db.String(100), primary_key=True)
    enabled = db.Column(db.Boolean, default=False)
    rollout_percentage = db.Column(db.Integer, default=0)
    description = db.Column(db.Text)
    updated_by = db.Column(db.String(100))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

# Admin API
@admin_app.post("/api/flags/{name}/toggle")
def toggle_flag(name: str, enabled: bool):
    flag = FeatureFlag.query.get(name)
    flag.enabled = enabled
    flag.updated_by = request.user.email
    db.session.commit()
    cache.delete('feature_flags')  # Invalidate cache
```

## Feature Flag Lifecycle

```
1. DEPLOY:   Code with flag (disabled) → production
2. TEST:     Enable for internal users → verify
3. ROLLOUT:  10% → 25% → 50% → 100% of users
4. CLEANUP:  Remove flag and old code path (CRITICAL!)
```

**Critical**: Remove flags after full rollout. Flags that live forever become tech debt. Track them:

```python
# flags.py — track creation date
flags.register('new_checkout', default=False, created='2024-01-15')

# CI check: flag older than 30 days without 100% rollout → warning
```'''
    ),
    (
        "thinking/devops-gitops-workflow",
        "Our deployment process is a shell script that one person runs manually. Only they know how it works. How do we make deployments reproducible and safe?",
        r'''<think>
GitOps — use Git as the single source of truth for what's deployed. All changes go through PRs. The deployment tool (ArgoCD, Flux) watches Git and applies changes automatically.

Benefits:
1. Auditable (git log shows who deployed what and when)
2. Reproducible (checkout any commit, that's what was deployed)
3. Rollback = git revert
4. PR-based review for infrastructure changes
</think>

## GitOps: Git as the Source of Truth

### Repository Structure

```
myapp/
├── app/                    # Application code
│   ├── src/
│   ├── tests/
│   └── Dockerfile
├── k8s/                    # Kubernetes manifests
│   ├── base/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── kustomization.yaml
│   ├── staging/
│   │   └── kustomization.yaml   # Staging overrides
│   └── production/
│       └── kustomization.yaml   # Production overrides
└── .github/workflows/
    └── ci.yml
```

### Environment-Specific Overrides

```yaml
# k8s/base/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: api
          image: ghcr.io/myorg/myapp:TAG  # Placeholder

# k8s/production/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
bases:
  - ../base
patches:
  - patch: |-
      apiVersion: apps/v1
      kind: Deployment
      metadata:
        name: api
      spec:
        replicas: 5  # More replicas in production
images:
  - name: ghcr.io/myorg/myapp
    newTag: v1.2.3  # THIS is what controls the deployed version
```

### Deployment Flow

```
Developer:
  1. Merge feature PR to main
  2. CI builds Docker image, tags as v1.2.4
  3. CI opens PR to update k8s/production/kustomization.yaml
     (changes newTag from v1.2.3 to v1.2.4)
  4. Team reviews deployment PR
  5. Merge → ArgoCD detects change → deploys automatically

Rollback:
  1. git revert the deployment PR
  2. ArgoCD detects revert → deploys previous version
  3. Done in 30 seconds
```

### ArgoCD Configuration

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myapp-production
spec:
  project: default
  source:
    repoURL: https://github.com/myorg/myapp
    targetRevision: main
    path: k8s/production
  destination:
    server: https://kubernetes.default.svc
    namespace: production
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### Benefits Over Shell Scripts

| Shell Script | GitOps |
|-------------|--------|
| One person knows how | Anyone can deploy via PR |
| No audit trail | Full git history |
| Rollback = "uh, what was the previous version?" | Rollback = git revert |
| "Did we deploy?" — check server | "What's deployed?" — check git |
| Manual, error-prone | Automated, reproducible |

**Start simple**: Even without ArgoCD, just having Kubernetes manifests in Git with a CI job that applies them is a huge improvement over shell scripts.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
