"""Phase 1H: Foundation Thinking — Data Modeling & DevOps (Part 7)

CI/CD pipeline design and zero-downtime deployment strategies
with realistic YAML configurations and rollback patterns.
"""

PAIRS = [
    (
        "thinking/devops-cicd-pipeline-design",
        r'''We're setting up CI/CD for a Python monorepo with 3 services (api, worker, admin-dashboard). Currently, every push triggers a full build and test for all services, taking 25 minutes. Most PRs only change one service. Our stack:

- GitHub Actions
- pytest for API tests
- Playwright for admin dashboard E2E tests
- Docker images pushed to ECR
- Deployed to ECS Fargate

How do we design a pipeline that only builds/tests what changed and still ensures nothing is broken?''',
        r'''<think>
The core problem is: in a monorepo, how do you avoid running the full 25-minute pipeline when only one service changed?

**Approach: Affected service detection + selective pipelines**

Step 1: Determine which services are affected by the changed files
Step 2: Only run build/test/deploy for affected services
Step 3: Still run cross-cutting tests (integration, shared libraries) when shared code changes

**File structure (assumed):**
```
/
├── services/
│   ├── api/
│   ├── worker/
│   └── admin-dashboard/
├── shared/
│   ├── models/
│   └── utils/
├── tests/
│   ├── integration/
│   └── e2e/
├── infrastructure/
│   └── terraform/
└── .github/
    └── workflows/
```

**Change detection logic:**
- Changes in `services/api/` → build+test api only
- Changes in `services/worker/` → build+test worker only
- Changes in `services/admin-dashboard/` → build+test admin only
- Changes in `shared/` → build+test ALL services (shared dependency)
- Changes in `tests/integration/` → run integration tests
- Changes in `infrastructure/` → run infra plan/apply
- Changes in `.github/` → run all (pipeline itself changed)

**GitHub Actions implementation options:**

1. **Path filters on workflow triggers:** Simple but limited - each workflow only runs when specific paths change. Problem: can't have conditional steps within a single workflow.

2. **Dorny/paths-filter action:** Detects which paths changed and sets output variables. Then use those in `if:` conditions.

3. **Separate workflow files per service:** Each service has its own workflow triggered by path changes. Most flexible.

**I'll go with option 2 (paths-filter) + a matrix strategy** for the best balance of simplicity and flexibility.

**Pipeline stages:**
1. Detect changes → output which services changed
2. Lint (parallel per service, only changed)
3. Test (parallel per service, only changed)
4. Build Docker images (parallel, only changed)
5. Deploy to staging (sequential, only changed services)
6. E2E tests on staging
7. Deploy to production (manual approval, only changed services)

**Caching strategy:**
- pip cache between runs (saves ~2 min)
- Docker layer cache (saves ~3 min per service)
- Playwright browser cache (saves ~1 min for E2E)

**Estimated time after optimization:**
- Single service change: ~8 min (was 25 min)
- Shared code change: ~15 min (tests run in parallel)
- No changes to services: ~1 min (skip everything)
</think>

### Optimized CI/CD pipeline with change detection

```yaml
# .github/workflows/ci-cd.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read
  id-token: write  # For AWS OIDC

env:
  AWS_REGION: us-east-1
  ECR_REGISTRY: 123456789.dkr.ecr.us-east-1.amazonaws.com

jobs:
  # ============================================
  # Stage 1: Detect which services changed
  # ============================================
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      api: ${{ steps.filter.outputs.api }}
      worker: ${{ steps.filter.outputs.worker }}
      admin: ${{ steps.filter.outputs.admin }}
      shared: ${{ steps.filter.outputs.shared }}
      infra: ${{ steps.filter.outputs.infra }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            api:
              - 'services/api/**'
              - 'shared/**'
              - 'requirements/api.txt'
            worker:
              - 'services/worker/**'
              - 'shared/**'
              - 'requirements/worker.txt'
            admin:
              - 'services/admin-dashboard/**'
              - 'shared/**'
              - 'package.json'
            shared:
              - 'shared/**'
            infra:
              - 'infrastructure/**'

  # ============================================
  # Stage 2: Lint + Test (parallel per service)
  # ============================================
  test-api:
    needs: detect-changes
    if: needs.detect-changes.outputs.api == 'true'
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
        ports: [5432:5432]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        ports: [6379:6379]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"
          cache-dependency-path: "requirements/api.txt"
      - run: pip install -r requirements/api.txt -r requirements/test.txt
      - name: Run API tests
        run: |
          cd services/api
          pytest --cov=. --cov-report=xml -x -q
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/postgres
          REDIS_URL: redis://localhost:6379/0
      - uses: codecov/codecov-action@v4
        with:
          file: services/api/coverage.xml
          flags: api

  test-worker:
    needs: detect-changes
    if: needs.detect-changes.outputs.worker == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"
      - run: pip install -r requirements/worker.txt -r requirements/test.txt
      - run: cd services/worker && pytest --cov=. -x -q

  test-admin:
    needs: detect-changes
    if: needs.detect-changes.outputs.admin == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: "npm"
      - run: cd services/admin-dashboard && npm ci
      - run: cd services/admin-dashboard && npm run lint
      - run: cd services/admin-dashboard && npm run test -- --coverage

  # ============================================
  # Stage 3: Build Docker images (parallel)
  # ============================================
  build-api:
    needs: [detect-changes, test-api]
    if: |
      always() &&
      needs.detect-changes.outputs.api == 'true' &&
      (needs.test-api.result == 'success' || needs.test-api.result == 'skipped')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789:role/github-actions
          aws-region: ${{ env.AWS_REGION }}
      - uses: aws-actions/amazon-ecr-login@v2
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v5
        with:
          context: .
          file: services/api/Dockerfile
          push: ${{ github.ref == 'refs/heads/main' }}
          tags: |
            ${{ env.ECR_REGISTRY }}/api:${{ github.sha }}
            ${{ env.ECR_REGISTRY }}/api:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # (Similar build jobs for worker and admin)

  # ============================================
  # Stage 4: Deploy to staging
  # ============================================
  deploy-staging:
    needs: [detect-changes, build-api]  # add build-worker, build-admin
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789:role/github-actions
          aws-region: ${{ env.AWS_REGION }}
      - name: Deploy changed services to ECS
        run: |
          if [ "${{ needs.detect-changes.outputs.api }}" == "true" ]; then
            aws ecs update-service --cluster staging --service api \
              --force-new-deployment
          fi
          if [ "${{ needs.detect-changes.outputs.worker }}" == "true" ]; then
            aws ecs update-service --cluster staging --service worker \
              --force-new-deployment
          fi

  # ============================================
  # Stage 5: E2E tests on staging
  # ============================================
  e2e-tests:
    needs: deploy-staging
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npx playwright install --with-deps chromium
      - run: npx playwright test
        env:
          BASE_URL: https://staging.example.com

  # ============================================
  # Stage 6: Deploy to production (manual gate)
  # ============================================
  deploy-production:
    needs: [detect-changes, e2e-tests]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production  # Requires manual approval in GitHub
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789:role/github-actions
          aws-region: ${{ env.AWS_REGION }}
      - name: Deploy to production
        run: |
          if [ "${{ needs.detect-changes.outputs.api }}" == "true" ]; then
            aws ecs update-service --cluster production --service api \
              --force-new-deployment
            aws ecs wait services-stable --cluster production --services api
          fi
```

### Pipeline timing comparison

```
Before (run everything):
  Lint all:     2 min
  Test all:    15 min (sequential)
  Build all:    5 min
  Deploy:       3 min
  Total:       25 min

After (change detection + parallel):
  Detect:        10 sec
  Test (1 svc):  4 min  (parallel, only changed)
  Build (1 svc): 2 min  (Docker cache)
  Deploy:        3 min
  Total:         9 min (64% faster for single-service changes)
```'''
    ),
    (
        "thinking/devops-zero-downtime-rolling-deploy",
        r'''We're deploying a Node.js API to Kubernetes (3 replicas). During deployments, users see occasional 502 errors and dropped WebSocket connections. Our current deployment config:

apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
  template:
    spec:
      containers:
      - name: api
        image: myapp:latest
        ports:
        - containerPort: 3000

How do we achieve true zero-downtime deployments?''',
        r'''<think>
502 errors during rolling deployment happen because of several issues:

1. **No readiness probe**: Kubernetes routes traffic to new pods before they're ready. Node.js apps take time to load modules, warm caches, establish DB connections.

2. **No graceful shutdown**: When Kubernetes kills old pods, it sends SIGTERM. If the app doesn't handle SIGTERM, in-flight requests are dropped immediately. WebSocket connections are cut.

3. **No preStop hook**: Even with graceful shutdown, there's a race condition. Kubernetes sends SIGTERM and simultaneously removes the pod from the service endpoints. But endpoint removal is asynchronous — traffic might still be routed to a terminating pod for a few seconds.

4. **`maxUnavailable` and `maxSurge` not configured**: Default rolling update allows 25% unavailable. With 3 replicas, that's 1 pod down during update = 33% capacity loss.

5. **No resource requests/limits**: Without resource requests, the scheduler might place all pods on the same node. Node overload during deployment.

6. **Using `latest` tag**: Can't rollback to specific version, and imagePullPolicy might not pull the new image.

**The fix requires addressing ALL of these:**

1. **Readiness probe**: Only route traffic when the app is ready
2. **Liveness probe**: Restart unhealthy pods
3. **Graceful shutdown handler**: Finish in-flight requests on SIGTERM
4. **preStop hook**: Add a small delay before SIGTERM so endpoint removal propagates
5. **terminationGracePeriodSeconds**: Give enough time for graceful shutdown
6. **maxUnavailable: 0, maxSurge: 1**: Never reduce capacity during rollout
7. **PodDisruptionBudget**: Prevent voluntary evictions from killing too many pods

Let me detail each fix.
</think>

### Why 502s happen during rolling updates

```
Timeline of a pod termination:
t=0s: Kubernetes decides to terminate pod
t=0s: SIGTERM sent to container    ← (1) App starts shutting down
t=0s: Pod removed from endpoints   ← (2) But endpoint update is ASYNC
t=0-2s: Kube-proxy/ingress still routes to dying pod → 502!
t=Xs: Container killed (SIGKILL if still running)
```

The race between (1) and (2) causes 502s. Traffic is sent to pods that are already shutting down.

### Fixed Kubernetes deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 3
  # Never reduce capacity during rollout
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0    # Never kill a pod before new one is ready
      maxSurge: 1          # Add 1 extra pod during rollout (3→4→3)
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      # Give pods time to shut down gracefully
      terminationGracePeriodSeconds: 60

      containers:
      - name: api
        image: myapp:v1.2.3  # Pinned version, NOT :latest
        ports:
        - containerPort: 3000

        # Readiness probe: only route traffic when app is truly ready
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 3000
          initialDelaySeconds: 5
          periodSeconds: 5
          failureThreshold: 3

        # Liveness probe: restart if app is stuck
        livenessProbe:
          httpGet:
            path: /health/live
            port: 3000
          initialDelaySeconds: 15
          periodSeconds: 10
          failureThreshold: 3

        # Startup probe: for slow-starting apps (don't kill during startup)
        startupProbe:
          httpGet:
            path: /health/live
            port: 3000
          failureThreshold: 30
          periodSeconds: 2

        # Resource requests ensure proper scheduling
        resources:
          requests:
            cpu: "250m"
            memory: "256Mi"
          limits:
            cpu: "1000m"
            memory: "512Mi"

        # preStop hook: delay SIGTERM so endpoint removal propagates first
        lifecycle:
          preStop:
            exec:
              command: ["sh", "-c", "sleep 10"]
              # Wait 10s → endpoints updated → THEN SIGTERM → graceful shutdown

      # Spread pods across nodes
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: kubernetes.io/hostname
        whenUnsatisfiable: DoNotSchedule
        labelSelector:
          matchLabels:
            app: api
---
# Prevent too many pods from being evicted at once
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: api-pdb
spec:
  minAvailable: 2  # Always keep at least 2 of 3 pods running
  selector:
    matchLabels:
      app: api
```

### Application-side graceful shutdown (Node.js)

```javascript
const express = require('express');
const http = require('http');

const app = express();
const server = http.createServer(app);

// Track active connections for graceful shutdown
let isShuttingDown = false;
const connections = new Set();

server.on('connection', (conn) => {
    connections.add(conn);
    conn.on('close', () => connections.delete(conn));
});

// Health endpoints
app.get('/health/ready', (req, res) => {
    if (isShuttingDown) {
        return res.status(503).json({ status: 'shutting_down' });
    }
    // Check dependencies (DB, Redis)
    res.json({ status: 'ready' });
});

app.get('/health/live', (req, res) => {
    res.json({ status: 'alive' });
});

// Graceful shutdown on SIGTERM
process.on('SIGTERM', () => {
    console.log('SIGTERM received, starting graceful shutdown...');
    isShuttingDown = true;

    // Stop accepting new connections
    server.close(() => {
        console.log('All connections closed, exiting');
        process.exit(0);
    });

    // Close idle keep-alive connections
    for (const conn of connections) {
        conn.end();
    }

    // Force exit after timeout (before Kubernetes SIGKILL)
    setTimeout(() => {
        console.error('Graceful shutdown timed out, forcing exit');
        process.exit(1);
    }, 50000);  // Must be < terminationGracePeriodSeconds (60s)
});

server.listen(3000);
```

### Deployment timeline (after fix)

```
Rolling update: v1.2.3 → v1.2.4 (3 replicas, maxSurge=1)

t=0s:  New pod (v1.2.4) created    → [v1.2.3, v1.2.3, v1.2.3, v1.2.4(starting)]
t=10s: New pod passes readiness    → [v1.2.3, v1.2.3, v1.2.3, v1.2.4(ready)]
t=10s: Old pod #1 marked for deletion
t=10s: preStop sleep(10) starts    → endpoint removal propagates
t=20s: SIGTERM sent to old pod #1  → graceful shutdown begins
t=25s: In-flight requests complete → old pod #1 exits
t=25s: Next new pod created        → repeat cycle

Total rollout: ~75 seconds, ZERO dropped requests
```

### WebSocket handling during deployment

```javascript
const WebSocket = require('ws');
const wss = new WebSocket.Server({ server });

// On SIGTERM: notify WebSocket clients to reconnect
process.on('SIGTERM', () => {
    // Send reconnect message to all WebSocket clients
    wss.clients.forEach((client) => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify({
                type: 'server_shutdown',
                message: 'reconnect_to_another_instance'
            }));
            // Close with 1001 (going away) — client should auto-reconnect
            client.close(1001, 'Server shutting down');
        }
    });
});
```

```javascript
// Client-side: auto-reconnect on server shutdown
function connectWebSocket() {
    const ws = new WebSocket('wss://api.example.com/ws');

    ws.onclose = (event) => {
        if (event.code === 1001) {
            // Server going away — reconnect immediately
            setTimeout(connectWebSocket, 100);
        } else {
            // Other close — exponential backoff
            setTimeout(connectWebSocket, Math.min(1000 * Math.pow(2, retries), 30000));
        }
    };
}
```'''
    ),
    (
        "thinking/devops-blue-green-deployment",
        r'''We're evaluating deployment strategies for our payment processing service. Requirements:
1. Zero downtime (handles $2M/day in transactions)
2. Instant rollback if something goes wrong
3. Database migrations must be compatible with both versions
4. We need to test the new version with real traffic before full switchover

Currently we do rolling updates on ECS, but rollbacks take 5-10 minutes and we've had incidents where bad deploys processed transactions incorrectly for those minutes. What deployment strategy should we use?''',
        r'''<think>
For a payment processing system handling $2M/day, the requirements are:
1. Zero downtime
2. INSTANT rollback (not 5-10 minutes)
3. DB compatibility between versions
4. Real traffic testing before full switchover

Let me evaluate the strategies:

**Rolling update (current):**
- Gradually replaces old pods with new
- Rollback = deploy old version (5-10 min)
- Can't test with real traffic before full rollout
- Not suitable for payment processing

**Blue-green deployment:**
- Two identical environments: Blue (current) and Green (new)
- Deploy new version to Green, test it, switch traffic
- Rollback = switch traffic back to Blue (instant, seconds)
- Both versions run simultaneously during transition
- Higher infrastructure cost (double the servers during deploy)

**Canary deployment:**
- Route a small percentage of traffic (1%, 5%, 10%) to new version
- Monitor metrics, gradually increase if OK
- Rollback = route all traffic back to old version (instant)
- Tests with real traffic progressively
- More complex routing configuration

**Blue-green + canary (best for payments):**
- Deploy to Green environment
- Route 1% of traffic to Green (canary)
- Monitor error rates, latency, transaction success rates
- Gradually increase: 1% → 5% → 25% → 50% → 100%
- At any point: instant rollback by routing 100% to Blue
- Keep Blue running for 24-48 hours after full switchover

This is the safest for payment processing because:
1. You can test with real transactions at low risk (1% canary)
2. Rollback is a traffic routing change, not a redeployment
3. If Green has a bug, only 1% of transactions are affected before detection
4. Blue stays warm for instant fallback

**Database compatibility:**
Both versions must work with the same database. This means:
- Migrations must be backward-compatible (expand-only)
- No column renames or drops until old version is fully decommissioned
- Use the expand-contract pattern for schema changes

Let me design this for AWS ECS with Application Load Balancer.
</think>

### Recommendation: Blue-green with canary promotion

For payment processing, you need instant rollback AND real-traffic testing. Blue-green + canary gives both.

### Architecture

```
                    ALB (weighted routing)
                   /                      \
          Blue Target Group           Green Target Group
          (current: v1.5.0)          (new: v1.6.0)
          Weight: 99%                 Weight: 1% (canary)
          3 tasks on ECS              3 tasks on ECS
                   \                      /
                    Shared PostgreSQL DB
                    (migrations must be backward-compatible)
```

### AWS CDK / CloudFormation setup

```yaml
# ECS services with two target groups
Resources:
  BlueService:
    Type: AWS::ECS::Service
    Properties:
      Cluster: !Ref Cluster
      ServiceName: payment-api-blue
      TaskDefinition: !Ref BlueTaskDef
      DesiredCount: 3
      LoadBalancers:
        - TargetGroupArn: !Ref BlueTargetGroup
          ContainerName: api
          ContainerPort: 8000

  GreenService:
    Type: AWS::ECS::Service
    Properties:
      Cluster: !Ref Cluster
      ServiceName: payment-api-green
      TaskDefinition: !Ref GreenTaskDef
      DesiredCount: 3
      LoadBalancers:
        - TargetGroupArn: !Ref GreenTargetGroup
          ContainerName: api
          ContainerPort: 8000

  # ALB listener with weighted routing
  ListenerRule:
    Type: AWS::ElasticLoadBalancingV2::ListenerRule
    Properties:
      Actions:
        - Type: forward
          ForwardConfig:
            TargetGroups:
              - TargetGroupArn: !Ref BlueTargetGroup
                Weight: 100  # Start: all traffic to blue
              - TargetGroupArn: !Ref GreenTargetGroup
                Weight: 0    # Start: no traffic to green
```

### Deployment automation script

```python
import boto3
import time
import sys

elbv2 = boto3.client("elbv2")
cloudwatch = boto3.client("cloudwatch")

LISTENER_ARN = "arn:aws:elasticloadbalancing:..."
BLUE_TG = "arn:aws:elasticloadbalancing:.../blue"
GREEN_TG = "arn:aws:elasticloadbalancing:.../green"

# Canary stages: (green_weight, observation_minutes)
CANARY_STAGES = [
    (1, 10),     # 1% for 10 minutes
    (5, 10),     # 5% for 10 minutes
    (25, 15),    # 25% for 15 minutes
    (50, 15),    # 50% for 15 minutes
    (100, 0),    # Full switchover
]

# Rollback thresholds
MAX_ERROR_RATE = 0.01   # 1% error rate
MAX_LATENCY_P99 = 2000  # 2 seconds

def set_weights(blue_weight: int, green_weight: int):
    """Update ALB traffic weights."""
    elbv2.modify_rule(
        RuleArn=LISTENER_ARN,
        Actions=[{
            "Type": "forward",
            "ForwardConfig": {
                "TargetGroups": [
                    {"TargetGroupArn": BLUE_TG, "Weight": blue_weight},
                    {"TargetGroupArn": GREEN_TG, "Weight": green_weight},
                ]
            }
        }]
    )
    print(f"Traffic weights: Blue={blue_weight}%, Green={green_weight}%")

def check_health(target_group: str) -> bool:
    """Check error rate and latency for the target group."""
    # Query CloudWatch for the last 5 minutes
    error_rate = get_metric(target_group, "HTTPCode_Target_5XX_Count")
    request_count = get_metric(target_group, "RequestCount")

    if request_count > 0 and (error_rate / request_count) > MAX_ERROR_RATE:
        print(f"ERROR RATE TOO HIGH: {error_rate/request_count:.2%}")
        return False

    p99_latency = get_metric(target_group, "TargetResponseTime", stat="p99")
    if p99_latency > MAX_LATENCY_P99:
        print(f"LATENCY TOO HIGH: p99={p99_latency}ms")
        return False

    return True

def rollback():
    """Instant rollback: send all traffic to Blue."""
    set_weights(100, 0)
    print("ROLLBACK COMPLETE: All traffic routed to Blue")
    # Alert the team
    send_alert("Deployment rolled back due to health check failure")

def deploy_canary():
    """Progressive canary deployment with automatic rollback."""
    print("Starting canary deployment...")

    for green_weight, observe_minutes in CANARY_STAGES:
        blue_weight = 100 - green_weight
        set_weights(blue_weight, green_weight)

        if observe_minutes == 0:
            print("Full switchover complete!")
            break

        # Observe for the specified duration
        print(f"Observing for {observe_minutes} minutes...")
        for minute in range(observe_minutes):
            time.sleep(60)

            if not check_health(GREEN_TG):
                print(f"Health check failed at {green_weight}% traffic!")
                rollback()
                sys.exit(1)

            print(f"  Minute {minute+1}/{observe_minutes}: healthy")

    print("Canary deployment successful!")
    print("Blue environment kept warm for 24h rollback window")

if __name__ == "__main__":
    deploy_canary()
```

### Database migration compatibility rules

```python
# SAFE migrations (backward-compatible):
# - ADD COLUMN (nullable or with default)
# - ADD INDEX CONCURRENTLY
# - ADD TABLE
# - ADD CONSTRAINT NOT VALID + VALIDATE

# UNSAFE migrations (break old version):
# - DROP COLUMN (old version still reads it)
# - RENAME COLUMN (old version uses old name)
# - CHANGE COLUMN TYPE (old version expects old type)
# - DROP TABLE

# Solution: Expand-contract with deployment phases
#
# Deploy v1.6.0 (expand):
#   - Add new column "shipping_status" (nullable)
#   - v1.5.0 ignores the new column (safe)
#   - v1.6.0 writes to both old and new columns
#
# After v1.5.0 is fully decommissioned (contract):
#   - Drop old column in v1.7.0 migration
#   - Now safe because v1.5.0 no longer exists
```

### Rollback timing comparison

| Strategy | Rollback time | Risk during rollback |
|----------|-------------|---------------------|
| Rolling update | 5-10 minutes | Traffic hits broken version |
| Blue-green | 1-5 seconds | Zero (Blue is still running) |
| Blue-green + canary | 1-5 seconds | Only canary % was exposed |

### Cost analysis

```
Rolling update:
  3 tasks × 1 service = 3 tasks running
  During deploy: 4 tasks briefly

Blue-green:
  3 tasks × 2 services = 6 tasks during deploy
  After deploy: can scale down Blue to 1 task (warm standby)
  Extra cost: ~30% during deploy, ~10% for standby

For $2M/day in transactions:
  5 minutes of bad transactions = $6,944 at risk
  Blue-green extra cost = ~$50/month
  ROI: One prevented incident pays for years of extra infra
```'''
    ),
    (
        "thinking/devops-feature-flags-deployment",
        r'''We want to decouple deployments from feature releases. Currently, merging a feature branch to main triggers a deployment that immediately exposes the feature to all users. We want:

1. Deploy code with features hidden behind flags
2. Gradually enable features for specific users/groups
3. Instantly disable a feature if it causes issues (without redeploying)
4. A/B test different feature variants

Our stack is Python/FastAPI with React frontend. We're considering building our own feature flag system vs using LaunchDarkly/Unleash. What's the right approach?''',
        r'''<think>
Feature flags are a deployment strategy that separates code deployment from feature release. Let me analyze build vs buy and the implementation.

**Build vs Buy:**

Build your own:
- Pros: No vendor dependency, no per-seat pricing, customizable
- Cons: Need to build flag management UI, targeting rules, audit logging, gradual rollout, SDK caching. This is a lot of work done right.
- Estimated effort: 2-4 weeks for a basic system, ongoing maintenance

Use LaunchDarkly/Unleash:
- LaunchDarkly: SaaS, $10-20/seat/month, excellent SDK support, real-time flag updates
- Unleash: Open source (self-hosted), has a cloud option too
- Pros: Battle-tested, rich targeting, analytics, audit log out of the box
- Cons: Cost (LaunchDarkly can get expensive), vendor dependency

**For a startup/mid-size team:**
Start with Unleash (open source, self-hosted) or a simple homegrown system. Migrate to LaunchDarkly if you need enterprise features.

**For a large team with compliance needs:**
LaunchDarkly is worth the cost for audit logging, approval workflows, and enterprise SSO.

**For this answer, I'll show both:** A practical homegrown system and how to integrate with Unleash.

**Key design decisions for a homegrown system:**

1. **Flag storage:** PostgreSQL table + Redis cache. Flags rarely change but are read on every request.

2. **Evaluation:** Flags can target by user ID, user attributes (plan, country), percentage rollout, or environment.

3. **SDK pattern:** Server-side evaluates flags, frontend gets flag values via API (not direct DB access).

4. **Cache invalidation:** When a flag changes in the DB, invalidate Redis cache. Use pub/sub for multi-instance.

5. **Default values:** If the flag system is down, the default must be safe (feature OFF).

Let me design a practical system.
</think>

### Recommendation: Start with a lightweight homegrown system

For most teams, a simple PostgreSQL-backed flag system covers 90% of needs. Migrate to LaunchDarkly/Unleash when you need advanced targeting or audit compliance.

### Database schema for feature flags

```sql
CREATE TABLE feature_flags (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,      -- 'new-checkout-flow'
    description TEXT,
    flag_type VARCHAR(20) NOT NULL DEFAULT 'boolean',  -- boolean, percentage, variant
    enabled BOOLEAN NOT NULL DEFAULT false, -- Global kill switch

    -- Targeting rules (JSONB for flexibility)
    rules JSONB NOT NULL DEFAULT '[]',
    -- Example: [
    --   {"type": "user_ids", "values": [1, 2, 3]},
    --   {"type": "percentage", "value": 10},
    --   {"type": "attribute", "key": "plan", "values": ["enterprise"]}
    -- ]

    -- A/B test variants
    variants JSONB,
    -- Example: {"control": 50, "variant_a": 25, "variant_b": 25}

    default_value BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by VARCHAR(100)
);

-- Audit log: who changed what, when
CREATE TABLE feature_flag_audit (
    id BIGSERIAL PRIMARY KEY,
    flag_key VARCHAR(100) NOT NULL,
    action VARCHAR(20) NOT NULL,  -- 'created', 'enabled', 'disabled', 'rules_updated'
    old_value JSONB,
    new_value JSONB,
    changed_by VARCHAR(100) NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### Server-side flag evaluation (Python/FastAPI)

```python
import hashlib
import json
from functools import lru_cache
from typing import Any, Optional
import redis

redis_client = redis.Redis()
CACHE_TTL = 60  # seconds

class FeatureFlagClient:
    """Evaluate feature flags with caching and targeting rules."""

    def is_enabled(
        self,
        flag_key: str,
        user_id: Optional[int] = None,
        attributes: Optional[dict] = None,
        default: bool = False,
    ) -> bool:
        """Check if a feature flag is enabled for a user."""
        flag = self._get_flag(flag_key)
        if flag is None:
            return default  # Flag doesn't exist — safe default

        if not flag["enabled"]:
            return False  # Global kill switch

        # Evaluate targeting rules
        rules = flag.get("rules", [])
        if not rules:
            return flag["enabled"]  # No rules = enabled for everyone

        for rule in rules:
            if self._evaluate_rule(rule, user_id, attributes or {}):
                return True

        return flag.get("default_value", default)

    def get_variant(
        self,
        flag_key: str,
        user_id: int,
        default: str = "control",
    ) -> str:
        """Get A/B test variant for a user (deterministic by user_id)."""
        flag = self._get_flag(flag_key)
        if flag is None or not flag.get("enabled"):
            return default

        variants = flag.get("variants", {})
        if not variants:
            return default

        # Deterministic bucketing: same user always gets same variant
        hash_val = int(hashlib.sha256(
            f"{flag_key}:{user_id}".encode()
        ).hexdigest(), 16) % 100

        cumulative = 0
        for variant_name, percentage in variants.items():
            cumulative += percentage
            if hash_val < cumulative:
                return variant_name

        return default

    def _evaluate_rule(self, rule: dict, user_id: Optional[int], attrs: dict) -> bool:
        rule_type = rule.get("type")

        if rule_type == "user_ids":
            return user_id in rule.get("values", [])

        elif rule_type == "percentage":
            if user_id is None:
                return False
            # Deterministic: same user always gets same bucket
            bucket = int(hashlib.md5(str(user_id).encode()).hexdigest(), 16) % 100
            return bucket < rule["value"]

        elif rule_type == "attribute":
            attr_value = attrs.get(rule["key"])
            return attr_value in rule.get("values", [])

        return False

    def _get_flag(self, flag_key: str) -> Optional[dict]:
        """Get flag from Redis cache, fallback to DB."""
        cached = redis_client.get(f"ff:{flag_key}")
        if cached:
            return json.loads(cached)

        # Cache miss — load from DB
        flag = db.fetch_one(
            "SELECT * FROM feature_flags WHERE key = $1", flag_key
        )
        if flag:
            flag_dict = dict(flag)
            redis_client.setex(f"ff:{flag_key}", CACHE_TTL, json.dumps(flag_dict))
            return flag_dict
        return None

flags = FeatureFlagClient()
```

### Usage in FastAPI endpoints

```python
from fastapi import FastAPI, Depends, Request

app = FastAPI()

@app.get("/api/checkout")
async def checkout(request: Request):
    user = request.state.user

    if flags.is_enabled("new-checkout-flow", user_id=user.id, attributes={"plan": user.plan}):
        return await new_checkout_flow(user)
    else:
        return await legacy_checkout_flow(user)

@app.get("/api/pricing")
async def pricing(request: Request):
    user = request.state.user

    variant = flags.get_variant("pricing-experiment", user_id=user.id)
    if variant == "variant_a":
        return {"prices": get_annual_pricing()}
    elif variant == "variant_b":
        return {"prices": get_usage_pricing()}
    else:
        return {"prices": get_standard_pricing()}
```

### React frontend integration

```typescript
// API endpoint that returns all flags for the current user
// GET /api/flags → {"new-checkout-flow": true, "dark-mode": false, ...}

import { createContext, useContext, useEffect, useState } from 'react';

const FlagContext = createContext<Record<string, boolean>>({});

export function FlagProvider({ children }: { children: React.ReactNode }) {
  const [flags, setFlags] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetch('/api/flags')
      .then(r => r.json())
      .then(setFlags)
      .catch(() => setFlags({}));  // Default: all flags off if API fails

    // Poll for flag changes every 30 seconds
    const interval = setInterval(() => {
      fetch('/api/flags').then(r => r.json()).then(setFlags);
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  return <FlagContext.Provider value={flags}>{children}</FlagContext.Provider>;
}

export function useFlag(key: string, defaultValue = false): boolean {
  const flags = useContext(FlagContext);
  return flags[key] ?? defaultValue;
}

// Usage in components:
function CheckoutPage() {
  const useNewCheckout = useFlag('new-checkout-flow');

  return useNewCheckout ? <NewCheckoutFlow /> : <LegacyCheckoutFlow />;
}
```

### Admin API for flag management

```python
@app.post("/admin/flags/{flag_key}/enable")
async def enable_flag(flag_key: str, admin: AdminUser = Depends(get_admin)):
    old = await db.fetch_one("SELECT * FROM feature_flags WHERE key = $1", flag_key)
    await db.execute("UPDATE feature_flags SET enabled = true WHERE key = $1", flag_key)
    redis_client.delete(f"ff:{flag_key}")  # Invalidate cache

    # Audit log
    await db.execute("""
        INSERT INTO feature_flag_audit (flag_key, action, old_value, new_value, changed_by)
        VALUES ($1, 'enabled', $2, $3, $4)
    """, flag_key, json.dumps({"enabled": False}), json.dumps({"enabled": True}), admin.email)

    return {"status": "enabled", "flag": flag_key}

@app.post("/admin/flags/{flag_key}/rollout")
async def set_rollout_percentage(flag_key: str, percentage: int, admin: AdminUser = Depends(get_admin)):
    """Gradually roll out: 1% → 5% → 25% → 50% → 100%"""
    await db.execute("""
        UPDATE feature_flags SET rules = $1 WHERE key = $2
    """, json.dumps([{"type": "percentage", "value": percentage}]), flag_key)
    redis_client.delete(f"ff:{flag_key}")
    return {"status": "updated", "rollout": f"{percentage}%"}
```

### Build vs buy comparison

| Criteria | Homegrown | Unleash (OSS) | LaunchDarkly |
|----------|----------|--------------|-------------|
| Cost | Dev time only | Free (self-hosted) | $10-20/seat/month |
| Setup time | 1-2 weeks | 1 day | 1 hour |
| Targeting rules | Basic | Advanced | Enterprise |
| Audit log | Build it | Built-in | Built-in + compliance |
| Real-time updates | Polling | Webhooks | Streaming |
| Best for | Small teams | Mid-size | Enterprise |'''
    ),
    (
        "thinking/devops-rollback-strategy",
        r'''We deployed a bad version to production that corrupted data for ~200 users before we noticed. Rolling back the code was easy (revert to previous container image) but the corrupted database records remain. Our current rollback plan only covers code, not data. How should we design a comprehensive rollback strategy that handles both code AND data issues?''',
        r'''<think>
This is a critical gap in most teams' rollback strategies. Code rollback is well understood (deploy previous version), but data rollback is much harder because:

1. Database changes aren't versioned like code
2. New data may have been written after corruption
3. Rolling back the entire database loses ALL changes since the backup, not just corrupted ones
4. Schema migrations may be irreversible (dropped columns, renamed tables)

**Levels of rollback:**

Level 1: Code rollback (deploy previous version)
- Covers: bugs in application logic, broken UI, performance regressions
- Doesn't cover: corrupted data, bad migrations, data mutations

Level 2: Feature flag rollback (disable the feature)
- Covers: feature-specific bugs without full redeployment
- Doesn't cover: data already corrupted by the feature

Level 3: Selective data rollback (fix corrupted records)
- Covers: specific records corrupted by a known bug
- Requires: audit log or CDC (Change Data Capture) to identify what changed

Level 4: Full database rollback (restore from backup)
- Covers: catastrophic data corruption
- Loses: all valid data changes since the backup
- Last resort only

**For the "200 corrupted user records" case:**

You need Level 3: selective data rollback. This requires:
1. Identifying which records were affected
2. Knowing what the records looked like before corruption
3. Restoring just those records without affecting others

**How to build this:**

1. **Audit log / CDC**: Track every data mutation with before/after snapshots
2. **Point-in-time recovery**: PostgreSQL's WAL allows PITR to any moment
3. **Event sourcing**: Reconstruct state by replaying events (for critical domains)
4. **Logical backups**: pg_dump of specific tables at regular intervals

For the comprehensive rollback strategy, I'll cover:
- Immediate response (contain the blast radius)
- Investigation (identify affected records)
- Selective repair (fix corrupted data)
- Prevention (avoid future data corruption)
</think>

### The gap: Most rollback plans only cover code, not data

```
Code rollback:   Deploy previous version     → 30 seconds ✓
Schema rollback: Reverse migration            → Minutes (if reversible)
Data rollback:   Fix corrupted records        → ??? (usually manual panic)
```

### Comprehensive rollback strategy (4 layers)

### Layer 1: Audit log for selective data recovery

```sql
-- Append-only audit log capturing every mutation
CREATE TABLE data_audit_log (
    id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    record_id BIGINT NOT NULL,
    action VARCHAR(10) NOT NULL,  -- INSERT, UPDATE, DELETE
    old_data JSONB,               -- State BEFORE the change
    new_data JSONB,               -- State AFTER the change
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by VARCHAR(100),      -- User or service that made the change
    app_version VARCHAR(50),      -- Deployment version (critical for rollback!)
    request_id UUID,              -- Trace to the specific request
    session_id VARCHAR(100)
);

CREATE INDEX idx_audit_table_record ON data_audit_log (table_name, record_id, changed_at DESC);
CREATE INDEX idx_audit_version ON data_audit_log (app_version, changed_at);

-- Generic trigger for audit logging
CREATE OR REPLACE FUNCTION audit_trigger() RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO data_audit_log (table_name, record_id, action, old_data, new_data, app_version)
    VALUES (
        TG_TABLE_NAME,
        COALESCE(NEW.id, OLD.id),
        TG_OP,
        CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN row_to_json(OLD)::jsonb END,
        CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN row_to_json(NEW)::jsonb END,
        current_setting('app.version', true)  -- Set per-connection
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Apply to critical tables
CREATE TRIGGER audit_users AFTER INSERT OR UPDATE OR DELETE ON users
    FOR EACH ROW EXECUTE FUNCTION audit_trigger();
CREATE TRIGGER audit_orders AFTER INSERT OR UPDATE OR DELETE ON orders
    FOR EACH ROW EXECUTE FUNCTION audit_trigger();
```

### Layer 2: Selective data rollback tooling

```python
class DataRollback:
    """Roll back specific records to their pre-corruption state."""

    async def identify_affected_records(
        self,
        table: str,
        bad_version: str,
        start_time: str,
        end_time: str,
    ) -> list[dict]:
        """Find all records modified by the bad deployment."""
        return await db.fetch_all("""
            SELECT DISTINCT record_id, old_data, new_data, changed_at
            FROM data_audit_log
            WHERE table_name = $1
              AND app_version = $2
              AND changed_at BETWEEN $3 AND $4
            ORDER BY record_id, changed_at
        """, table, bad_version, start_time, end_time)

    async def preview_rollback(self, table: str, bad_version: str,
                                start_time: str, end_time: str) -> list[dict]:
        """Show what the rollback would do BEFORE executing it."""
        affected = await self.identify_affected_records(
            table, bad_version, start_time, end_time
        )
        preview = []
        for record in affected:
            current = await db.fetch_one(
                f"SELECT * FROM {table} WHERE id = $1", record['record_id']
            )
            preview.append({
                'record_id': record['record_id'],
                'current_state': dict(current) if current else None,
                'will_restore_to': record['old_data'],
                'was_corrupted_at': record['changed_at'],
            })
        return preview

    async def execute_rollback(
        self,
        table: str,
        bad_version: str,
        start_time: str,
        end_time: str,
        approved_by: str,
    ) -> dict:
        """Roll back affected records to their pre-corruption state."""
        affected = await self.identify_affected_records(
            table, bad_version, start_time, end_time
        )

        rolled_back = 0
        skipped = 0
        errors = []

        async with db.transaction():
            for record in affected:
                try:
                    if record['old_data'] is None:
                        # Record was INSERTed by bad version — delete it
                        await db.execute(
                            f"DELETE FROM {table} WHERE id = $1",
                            record['record_id']
                        )
                    else:
                        # Record was UPDATed — restore old values
                        old = record['old_data']
                        columns = ', '.join(f"{k} = ${i+2}" for i, k in enumerate(old.keys()))
                        await db.execute(
                            f"UPDATE {table} SET {columns} WHERE id = $1",
                            record['record_id'], *old.values()
                        )
                    rolled_back += 1
                except Exception as e:
                    errors.append({'record_id': record['record_id'], 'error': str(e)})

            # Log the rollback itself
            await db.execute("""
                INSERT INTO data_audit_log (table_name, record_id, action, app_version, changed_by)
                VALUES ('_rollback_event', 0, 'ROLLBACK', $1, $2)
            """, bad_version, approved_by)

        return {
            'rolled_back': rolled_back,
            'skipped': skipped,
            'errors': errors,
            'approved_by': approved_by,
        }

rollback = DataRollback()
```

### Layer 3: PostgreSQL point-in-time recovery

```bash
# For catastrophic corruption: restore entire DB to a specific moment
# Requires WAL archiving enabled in postgresql.conf:
#   archive_mode = on
#   archive_command = 'aws s3 cp %p s3://db-backups/wal/%f'

# 1. Stop the current database
pg_ctl -D /var/lib/postgresql/data stop

# 2. Restore base backup
aws s3 sync s3://db-backups/base/latest/ /var/lib/postgresql/data/

# 3. Configure recovery to stop at the moment BEFORE corruption
cat > /var/lib/postgresql/data/recovery.signal << 'EOF'
EOF

cat >> /var/lib/postgresql/data/postgresql.conf << 'EOF'
restore_command = 'aws s3 cp s3://db-backups/wal/%f %p'
recovery_target_time = '2026-03-05 14:30:00 UTC'  # Just before the bad deploy
recovery_target_action = 'promote'
EOF

# 4. Start PostgreSQL — it replays WAL up to the target time
pg_ctl -D /var/lib/postgresql/data start
```

### Layer 4: Incident response runbook

```markdown
## Data Corruption Incident Response

### Immediate (first 5 minutes)
1. [ ] Roll back code: deploy previous known-good version
2. [ ] Disable feature flag if applicable
3. [ ] Identify time window: when did bad version start serving traffic?
4. [ ] Estimate blast radius: how many records affected?

### Investigation (5-30 minutes)
5. [ ] Query audit log to identify affected records:
       SELECT COUNT(*) FROM data_audit_log
       WHERE app_version = 'bad-version' AND action = 'UPDATE';
6. [ ] Categorize severity:
       - <100 records: selective rollback (Layer 2)
       - 100-10K records: selective rollback with review
       - >10K records or unknown scope: consider PITR (Layer 3)

### Repair (30-120 minutes)
7. [ ] Generate rollback preview (dry run)
8. [ ] Review with second engineer
9. [ ] Execute selective rollback with approval
10. [ ] Verify repaired records
11. [ ] Notify affected users

### Post-incident
12. [ ] Write incident report
13. [ ] Add test coverage for the bug
14. [ ] Review: could feature flags have prevented this?
15. [ ] Review: was the audit log sufficient to identify all affected records?
```

### Prevention checklist

| Prevention | Covers | Effort |
|-----------|--------|--------|
| Feature flags (gradual rollout) | Limits blast radius to canary % | Low |
| Audit log on critical tables | Enables selective rollback | Medium |
| WAL archiving + PITR | Full DB recovery to any point | Medium |
| Pre-deploy data validation | Catches corruption patterns early | Low |
| Read replica for rollback queries | Don't slow production during investigation | Low |'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
