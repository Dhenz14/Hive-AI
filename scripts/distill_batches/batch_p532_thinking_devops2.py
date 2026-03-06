"""Phase 1H: Foundation Thinking — Data Modeling & DevOps (Part 4/5)
Kubernetes, scaling, reliability engineering, incident response."""

PAIRS = [
    (
        "thinking/devops-horizontal-scaling",
        "Our API server handles 1000 requests/second on a single instance. We expect 10x growth. Should we scale vertically (bigger server) or horizontally (more servers)?",
        r'''<think>
Vertical vs horizontal scaling:

Vertical (bigger server):
- Simpler (no distributed system concerns)
- Has a ceiling (can't buy infinite CPU/RAM)
- Single point of failure
- Can handle 2-4x growth easily

Horizontal (more servers):
- Theoretically unlimited scaling
- Requires stateless application design
- Adds complexity (load balancing, session management, distributed state)
- Better availability (no single point of failure)

For 10x growth: horizontal is the way. But the app needs to be stateless first.
</think>

For 10x growth, **horizontal scaling** — but your app must be stateless first.

## Making Your App Stateless

```python
# STATEFUL (can't scale horizontally):
app.sessions = {}  # In-memory sessions
app.cache = {}     # In-memory cache
uploaded_files = "/tmp/uploads/"  # Local filesystem

# STATELESS (ready for horizontal scaling):
sessions → Redis
cache → Redis
files → S3/MinIO
```

## Horizontal Scaling Architecture

```
                    ┌─────────────┐
                    │ Load Balancer│
                    └──────┬──────┘
              ┌────────┬───┴───┬────────┐
              │        │       │        │
           [API 1] [API 2] [API 3] [API 4]
              │        │       │        │
              └────────┴───┬───┴────────┘
                    ┌──────┴──────┐
                    │  PostgreSQL  │  ← Shared state
                    │  Redis Cache │
                    │  S3 Storage  │
                    └─────────────┘
```

## Auto-Scaling Configuration (Kubernetes)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70  # Scale up when CPU > 70%
    - type: Pods
      pods:
        metric:
          name: http_requests_per_second
        target:
          type: AverageValue
          averageValue: "200"     # Scale up when >200 rps per pod
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60   # Wait 1 min before scaling up
    scaleDown:
      stabilizationWindowSeconds: 300  # Wait 5 min before scaling down
```

## Scaling Bottlenecks to Address

```
Layer          Bottleneck              Fix
─────          ──────────              ───
Load Balancer  Connection limit        Use managed LB (AWS ALB)
API Servers    CPU/Memory              Horizontal auto-scale
Database       Connection exhaustion   Connection pooling (PgBouncer)
Database       Read throughput         Read replicas
Database       Write throughput        Sharding or write-optimized DB
Cache          Memory limit            Redis Cluster
File Storage   I/O throughput          CDN + S3
```

## Vertical vs Horizontal Decision

| Factor | Vertical | Horizontal |
|--------|----------|------------|
| Growth expected | 2-4x | 5x+ |
| App architecture | Stateful OK | Must be stateless |
| Budget | Higher per-server cost | Lower total cost at scale |
| Availability | Single point of failure | Survives instance failures |
| Complexity | Simple | Distributed system concerns |

**Default**: Start with the biggest single server that's cost-effective. When you need >4x capacity or high availability, go horizontal.'''
    ),
    (
        "thinking/devops-kubernetes-patterns",
        "I'm new to Kubernetes. What are the essential patterns I need to know for deploying a web application?",
        r'''<think>
Essential K8s patterns for a web app:
1. Deployment (rolling updates, replicas)
2. Service (internal load balancing)
3. Ingress (external traffic routing)
4. ConfigMap/Secret (configuration)
5. Health checks (liveness, readiness)
6. Resource limits (CPU, memory)
7. HPA (auto-scaling)

Let me provide a practical example that covers all of these.
</think>

## Complete Web App Deployment

### 1. Deployment (Your Application)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 3
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
          image: ghcr.io/myorg/myapp:v1.2.3
          ports:
            - containerPort: 8000

          # Resource limits (prevent one pod from consuming all resources)
          resources:
            requests:
              cpu: 250m       # 0.25 CPU cores guaranteed
              memory: 256Mi   # 256 MB guaranteed
            limits:
              cpu: 1000m      # Max 1 CPU core
              memory: 512Mi   # Max 512 MB (OOM killed if exceeded)

          # Health checks
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8000
            initialDelaySeconds: 15
            periodSeconds: 20

          # Configuration
          envFrom:
            - configMapRef:
                name: api-config
            - secretRef:
                name: api-secrets

          # Graceful shutdown
          lifecycle:
            preStop:
              exec:
                command: ["sleep", "10"]
      terminationGracePeriodSeconds: 30
```

### 2. Service (Internal Load Balancing)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: api
spec:
  selector:
    app: api
  ports:
    - port: 80
      targetPort: 8000
```

### 3. Ingress (External Traffic)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-ingress
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt
spec:
  tls:
    - hosts: [api.myapp.com]
      secretName: api-tls
  rules:
    - host: api.myapp.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: api
                port:
                  number: 80
```

### 4. ConfigMap and Secret

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: api-config
data:
  LOG_LEVEL: "info"
  ALLOWED_ORIGINS: "https://myapp.com"
  CACHE_TTL: "300"

---
apiVersion: v1
kind: Secret
metadata:
  name: api-secrets
type: Opaque
stringData:
  DATABASE_URL: postgresql://user:pass@db/myapp
  REDIS_URL: redis://redis:6379
```

### 5. Health Check Endpoints

```python
# In your FastAPI/Flask app
@app.get("/health/live")
def liveness():
    """Am I running? (restart if this fails)"""
    return {"status": "alive"}

@app.get("/health/ready")
def readiness():
    """Can I serve traffic? (remove from LB if this fails)"""
    try:
        db.execute("SELECT 1")
        redis.ping()
        return {"status": "ready"}
    except Exception:
        return Response(status_code=503)
```

## Quick Reference

```
kubectl apply -f deployment.yaml    # Deploy
kubectl get pods                    # Check status
kubectl logs -f deploy/api          # View logs
kubectl rollout undo deploy/api     # Rollback
kubectl scale deploy/api --replicas=5  # Manual scale
kubectl exec -it pod/api-xxx -- bash   # Debug shell
```'''
    ),
    (
        "thinking/devops-incident-response",
        "Our production service went down at 2AM. It took 4 hours to fix because nobody knew what to do. How do we handle incidents better?",
        r'''<think>
Incident response framework:
1. Detection (monitoring + alerting)
2. Triage (severity assessment)
3. Communication (stakeholder updates)
4. Mitigation (stop the bleeding)
5. Resolution (fix the root cause)
6. Postmortem (prevent recurrence)

The key is having a playbook BEFORE incidents happen.
</think>

## Incident Response Framework

### 1. Severity Levels

```
SEV 1 (Critical):  Service completely down, revenue impact
  → Page on-call immediately, all hands
  → Update every 15 minutes
  → Postmortem required

SEV 2 (Major):     Degraded service, some users affected
  → Page on-call, assemble team
  → Update every 30 minutes
  → Postmortem required

SEV 3 (Minor):     Minor feature broken, workaround available
  → Create ticket, fix next business day
  → No page, no status update

SEV 4 (Low):       Cosmetic issue, edge case
  → Backlog ticket
```

### 2. Incident Playbook

```markdown
## When You Get Paged

### First 5 Minutes
1. Acknowledge the alert
2. Check the monitoring dashboard: https://grafana.myapp.com
3. Determine severity (see matrix above)
4. If SEV 1-2: Post in #incidents Slack channel:
   "Investigating [alert name]. Impact: [what users see]. ETA: unknown."

### Next 15 Minutes (Triage)
1. Check recent deployments: `kubectl rollout history deploy/api`
2. Check error logs: `kubectl logs -l app=api --tail=200 | grep ERROR`
3. Check dependencies: hit health endpoints of each service
4. Check infrastructure: AWS status page, DB metrics

### Mitigation (Stop the Bleeding)
- Bad deploy? → `kubectl rollout undo deploy/api`
- Database overloaded? → Kill slow queries, enable read replica
- External dependency down? → Enable circuit breaker
- Traffic spike? → Scale up, enable rate limiting

### Resolution
- Fix the root cause
- Deploy the fix through normal CI/CD
- Monitor for 30 minutes after fix

### After the Incident
- Update status page: "Resolved"
- Schedule postmortem within 48 hours
```

### 3. Postmortem Template

```markdown
# Incident Postmortem: [Title]

## Summary
- **Date**: 2024-01-15 02:00 - 06:00 UTC
- **Duration**: 4 hours
- **Severity**: SEV 1
- **Impact**: 100% of users unable to log in

## Timeline
- 02:00 — Alert fires: "Login error rate > 50%"
- 02:05 — On-call acknowledges, begins investigation
- 02:15 — Root cause identified: Redis cluster ran out of memory
- 02:30 — Attempted fix: flush expired keys → partial recovery
- 03:00 — Scaled Redis to larger instance
- 04:00 — Full recovery confirmed
- 06:00 — Incident closed after monitoring period

## Root Cause
Redis maxmemory reached 100%. Session storage grew unbounded because
expired sessions were not being cleaned up (TTL was not set on session keys).

## What Went Well
- Alert fired within 2 minutes of impact
- On-call responded within 5 minutes

## What Went Wrong
- No monitoring on Redis memory usage
- No TTL on session keys (created in migration 3 months ago)
- Runbook didn't cover Redis memory issues

## Action Items
- [ ] Add TTL to all session keys (owner: @alice, due: Jan 20)
- [ ] Add Redis memory monitoring + alert at 80% (owner: @bob, due: Jan 18)
- [ ] Update runbook with Redis troubleshooting (owner: @alice, due: Jan 22)
- [ ] Load test session storage at 10x current load (owner: @charlie, due: Jan 25)

## Lessons Learned
Every cache key must have a TTL. "Temporary" data without TTL becomes permanent.
```

### Key Principles
1. **Blameless postmortems** — focus on systems, not people
2. **Action items with owners and deadlines** — or they won't happen
3. **Measure MTTR** (Mean Time To Recovery) — this matters more than MTBF
4. **Practice incidents** — run game days before real incidents happen'''
    ),
    (
        "thinking/devops-log-aggregation",
        "Our logs are scattered across 12 servers. When there's a bug, we SSH into each server and grep through logs. This takes forever. What's the right approach?",
        r'''<think>
Centralized logging stack options:
1. ELK (Elasticsearch + Logstash + Kibana) — powerful, complex
2. Loki + Grafana — lightweight, label-based (like Prometheus for logs)
3. Cloud-native: CloudWatch (AWS), Stackdriver (GCP), Application Insights (Azure)
4. Datadog / New Relic — managed, expensive but easy

For most teams: Loki + Grafana (if self-hosted) or cloud-native logging (if on cloud).

Key principles:
1. Structured logging (JSON, not plain text)
2. Correlation IDs (trace requests across services)
3. Log levels (debug, info, warn, error)
4. Centralized aggregation
</think>

## Step 1: Structured Logging (In Your App)

```python
# BEFORE (unstructured — impossible to parse):
logger.info(f"User {user_id} placed order {order_id} for ${total}")

# AFTER (structured JSON — easy to search and filter):
import structlog

logger = structlog.get_logger()

logger.info("order_placed",
    user_id=user_id,
    order_id=order_id,
    total=float(total),
    items_count=len(items),
)

# Output:
# {"event": "order_placed", "user_id": 123, "order_id": "abc",
#  "total": 49.99, "items_count": 3, "timestamp": "2024-01-15T10:30:00Z",
#  "level": "info", "service": "order-api", "host": "api-server-3"}
```

## Step 2: Ship Logs to Central Location

### Option A: Loki + Grafana (Self-Hosted, Lightweight)

```yaml
# docker-compose.yml
services:
  loki:
    image: grafana/loki:2.9.0
    ports: ["3100:3100"]
    volumes:
      - loki-data:/loki

  promtail:
    image: grafana/promtail:2.9.0
    volumes:
      - /var/log:/var/log             # System logs
      - ./promtail.yml:/etc/promtail/config.yml

  grafana:
    image: grafana/grafana:10.0.0
    ports: ["3000:3000"]
```

### Option B: Cloud-Native (Simplest)

```python
# AWS CloudWatch
import watchtower

logger.addHandler(watchtower.CloudWatchLogHandler(
    log_group="myapp",
    log_stream_name="api-{hostname}",
))
```

## Step 3: Search and Filter

```
# In Grafana/Loki:
{service="order-api"} |= "error"                    # All errors
{service="order-api"} | json | user_id = 123         # Specific user
{service="order-api"} | json | total > 1000           # High-value orders
{service=~"order-api|payment-api"} | json | trace_id="abc-123"  # Cross-service trace
```

## Step 4: Correlation Across Services

```python
# Middleware adds trace_id to all log entries
@app.middleware("http")
async def add_trace_id(request, call_next):
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    structlog.contextvars.bind_contextvars(trace_id=trace_id)
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response

# Now search by trace_id to see the entire request flow:
# {trace_id="abc-123"} → shows logs from ALL services for this request
```

## Log Levels Guide

```
DEBUG  → Variable values, loop iterations (dev only, never in prod)
INFO   → Business events: order placed, user registered, payment processed
WARN   → Recoverable issues: retry succeeded, fallback used, slow query
ERROR  → Failures: payment declined, service unavailable, unhandled exception
```

**Rule**: If you SSH into a server to read logs, your logging infrastructure is broken.'''
    ),
    (
        "thinking/devops-database-backup-recovery",
        "We've never tested restoring from our database backups. Last week we accidentally deleted production data and found our backups were corrupted. How do we set up reliable backup and recovery?",
        r'''<think>
Backup strategy must include:
1. Automated backups (not manual)
2. Multiple backup types (full, incremental, WAL archiving)
3. Off-site storage (different region/provider)
4. Regular restore testing (most important!)
5. Point-in-time recovery (PITR)
6. Monitoring and alerting on backup failures

The golden rule: a backup you haven't tested restoring is not a backup.
</think>

## The Golden Rule

> **An untested backup is not a backup.** If you haven't restored from it, you don't know if it works.

## PostgreSQL Backup Strategy

### 1. Automated Daily Backups

```bash
#!/bin/bash
# scripts/backup_db.sh — run via cron daily at 2AM

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/postgres"
S3_BUCKET="s3://myapp-backups/postgres"

# Full backup with compression
pg_dump -h localhost -U postgres myapp \
    --format=custom \
    --compress=9 \
    > "${BACKUP_DIR}/myapp_${TIMESTAMP}.dump"

# Upload to S3 (off-site)
aws s3 cp "${BACKUP_DIR}/myapp_${TIMESTAMP}.dump" \
    "${S3_BUCKET}/daily/myapp_${TIMESTAMP}.dump"

# Verify backup is valid
pg_restore --list "${BACKUP_DIR}/myapp_${TIMESTAMP}.dump" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "BACKUP VERIFICATION FAILED" | mail -s "ALERT: Backup Failed" ops@myapp.com
    exit 1
fi

# Clean up local backups older than 7 days
find "${BACKUP_DIR}" -name "*.dump" -mtime +7 -delete
```

```cron
# crontab
0 2 * * * /opt/scripts/backup_db.sh >> /var/log/backup.log 2>&1
```

### 2. Point-in-Time Recovery (WAL Archiving)

```ini
# postgresql.conf — enable WAL archiving
wal_level = replica
archive_mode = on
archive_command = 'aws s3 cp %p s3://myapp-backups/wal/%f'
```

This lets you restore to any second, not just the last backup time.

### 3. Automated Restore Testing

```bash
#!/bin/bash
# scripts/test_restore.sh — run weekly

echo "Testing backup restore..."

# Get latest backup
LATEST=$(aws s3 ls s3://myapp-backups/postgres/daily/ | sort | tail -1 | awk '{print $4}')
aws s3 cp "s3://myapp-backups/postgres/daily/${LATEST}" /tmp/test_restore.dump

# Restore to test database
dropdb --if-exists myapp_restore_test
createdb myapp_restore_test
pg_restore -d myapp_restore_test /tmp/test_restore.dump

# Verify data integrity
USERS=$(psql myapp_restore_test -t -c "SELECT COUNT(*) FROM users")
ORDERS=$(psql myapp_restore_test -t -c "SELECT COUNT(*) FROM orders")

if [ "$USERS" -gt 0 ] && [ "$ORDERS" -gt 0 ]; then
    echo "Restore test PASSED: ${USERS} users, ${ORDERS} orders"
else
    echo "Restore test FAILED" | mail -s "ALERT: Restore Test Failed" ops@myapp.com
fi

# Cleanup
dropdb myapp_restore_test
rm /tmp/test_restore.dump
```

### 4. Recovery Procedure (Runbook)

```markdown
## Database Recovery Runbook

### Full Restore (Latest Backup)
1. Get latest backup: `aws s3 ls s3://myapp-backups/postgres/daily/`
2. Download: `aws s3 cp s3://...latest.dump /tmp/restore.dump`
3. Create new DB: `createdb myapp_restored`
4. Restore: `pg_restore -d myapp_restored /tmp/restore.dump`
5. Verify: `psql myapp_restored -c "SELECT COUNT(*) FROM users"`
6. Switch app: Update DATABASE_URL to point to myapp_restored
7. Rename: `ALTER DATABASE myapp RENAME TO myapp_old; ALTER DATABASE myapp_restored RENAME TO myapp;`

### Point-in-Time Recovery (Restore to Specific Moment)
1. Restore base backup
2. Replay WAL files up to target time:
   `recovery_target_time = '2024-01-15 14:30:00 UTC'`
3. This recovers all data up to 2:30 PM, before the accidental delete
```

### 5. Monitoring

```yaml
# Alert if backup hasn't run in 26 hours
- alert: BackupMissing
  expr: time() - backup_last_success_timestamp > 93600
  severity: page
  annotations:
    summary: "Database backup has not completed in 26 hours"
```

## Backup Strategy Summary

```
Continuous: WAL archiving to S3 (PITR capability)
Daily:      Full pg_dump to S3 (7-day local, 90-day S3)
Weekly:     Automated restore test (verify backup is valid)
Monthly:    Full recovery drill (team practices the procedure)
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
