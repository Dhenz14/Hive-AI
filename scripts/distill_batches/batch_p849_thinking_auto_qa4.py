"""Phase 4F: Self-Improvement — Quality Assurance (Part 4)

Quality checklists for deployment advice — ensuring deployment
recommendations are safe, complete, and production-ready.
"""

PAIRS = [
    (
        "thinking/auto-qa-deployment-safety-checklist",
        r'''What quality checklist should I run before giving someone deployment advice to make sure I'm not leading them into a production incident?''',
        r'''<think>
Deployment advice is high-stakes. If someone follows bad deployment advice, the result can be downtime, data loss, or security breaches. I need a rigorous quality checklist before giving any deployment recommendation.

**Key risks in deployment advice:**
1. Missing rollback strategy (what if the deploy breaks things?)
2. Missing health checks (how do you know it worked?)
3. Skipping database migration safety (destructive migrations can't be undone)
4. Ignoring zero-downtime requirements
5. Missing environment-specific configuration
6. Forgetting about secrets management
7. No mention of monitoring/alerting
</think>

**Deployment Advice Quality Checklist**

**Run this checklist before giving ANY deployment advice:**

**1. Rollback strategy (CRITICAL)**
```
□ Have I mentioned how to roll back if this deploy fails?
□ Is the rollback tested and documented?
□ Can the rollback happen without downtime?
□ Is there a clear trigger for when to roll back?
  (e.g., "if error rate exceeds 5% within 10 minutes")
```

**2. Database migration safety**
```
□ Are migrations backward-compatible?
  (Can the old code still work with the new schema?)
□ No destructive operations without confirmation?
  (DROP TABLE, DELETE column should be separate deploys)
□ Migration can be run independently of the code deploy?
□ Large data migrations have been tested on a copy?
```

**3. Zero-downtime considerations**
```
□ Blue-green or rolling deployment strategy mentioned?
□ New instances start before old ones stop?
□ Health check endpoints are configured?
□ Load balancer drains connections before removing instances?
```

**4. Environment configuration**
```
□ All environment variables documented?
□ Secrets are NOT in the deployment script?
□ Environment-specific configs (dev/staging/prod) are separated?
□ Feature flags are set correctly for this environment?
```

**5. Verification steps**
```
□ How to verify the deploy succeeded?
□ Smoke tests to run post-deploy?
□ Monitoring dashboards to watch?
□ Who to alert if something goes wrong?
□ How long to wait before considering the deploy stable?
```

**6. Communication plan**
```
□ Does the team know this deploy is happening?
□ Is there a maintenance window if needed?
□ Are stakeholders informed of any expected changes?
□ Is there an incident channel ready if things go wrong?
```

**Example of bad vs. good deployment advice:**

**BAD (missing safety):**
```
"Run: kubectl apply -f deployment.yaml"
```

**GOOD (safe deployment advice):**
```
"Deploy with safety:
1. Backup: kubectl get deployment myapp -o yaml > backup.yaml
2. Deploy: kubectl apply -f deployment.yaml
3. Watch: kubectl rollout status deployment/myapp --timeout=300s
4. Verify: curl -f https://myapp.example.com/health
5. If failing: kubectl rollout undo deployment/myapp
6. Monitor error rates for 30 minutes before considering stable"
```

**The meta-principle:** Deployment advice without a rollback plan is incomplete. Deployment advice without verification steps is dangerous. Every deployment recommendation should answer: "How do we know it worked?" and "How do we undo it if it didn't?"'''
    ),
    (
        "thinking/auto-qa-deployment-database-migrations",
        r'''What specific quality checks should I apply when advising someone on database migrations as part of a deployment?''',
        r'''<think>
Database migrations are the most dangerous part of most deployments because:
1. They can be irreversible (DROP COLUMN, DROP TABLE)
2. They can cause downtime (locking tables during ALTER TABLE)
3. They can cause data loss
4. They often can't be rolled back cleanly
5. They interact with the running application in complex ways

**Quality checks needed:**
- Is the migration reversible?
- Does it lock tables? For how long?
- Is it backward-compatible with the current running code?
- Has it been tested on production-sized data?
- Is there a separate deploy for migration vs. code?
</think>

**Database Migration Quality Checklist**

**Before advising on any database migration:**

**Tier 1: Safety (MUST check)**
```
□ REVERSIBILITY: Can this migration be undone?
  - Adding a column → Yes (DROP COLUMN later)
  - Dropping a column → NO (data is gone)
  - Renaming a column → Risky (code references the old name)

□ BACKWARD COMPATIBILITY: Can the current running code
  work with the new schema?
  - Adding a nullable column → Yes (old code ignores it)
  - Removing a column → NO (old code will crash)
  - Changing a column type → Depends (might break queries)

□ LOCKING: Will this lock the table?
  - Adding a column (PostgreSQL) → Brief lock
  - Adding an index → Use CONCURRENTLY to avoid lock
  - ALTER TABLE on large table → Can lock for minutes/hours
```

**Tier 2: Performance (SHOULD check)**
```
□ DATA SIZE: How large is the affected table?
  - <1M rows → most operations are fast
  - 1M-100M rows → need to be careful
  - >100M rows → need specialized approach

□ INDEX CREATION: Large indexes must be created concurrently
  CREATE INDEX CONCURRENTLY idx_name ON table(column);
  (Not inside a transaction!)

□ DATA BACKFILL: If filling a new column with data:
  - Do it in batches, not one UPDATE for all rows
  - UPDATE table SET col = value WHERE id BETWEEN x AND y
```

**Tier 3: Process (GOOD PRACTICE)**
```
□ TESTED ON STAGING: Migration ran on a staging environment
  with production-sized data?
□ TIMING: How long does the migration take on production data?
  If >1 minute, consider running during low-traffic hours
□ MONITORING: Someone watching the database during migration?
□ COMMUNICATION: Team informed before running migration?
```

**The safe migration pattern (expand and contract):**
```
Instead of one risky migration, use three safe ones:

Step 1 — EXPAND: Add new column alongside old one
  ALTER TABLE users ADD COLUMN email_new VARCHAR(255);

Step 2 — MIGRATE: Code writes to both columns, reads from new
  Deploy code that writes to email AND email_new
  Backfill: UPDATE users SET email_new = email WHERE email_new IS NULL

Step 3 — CONTRACT: Remove old column (after verification)
  Deploy code that only uses email_new
  ALTER TABLE users DROP COLUMN email;

This avoids any moment where running code disagrees with the schema.
```

**Red flags in migration advice:**
```
DANGEROUS — always flag these:
  - "ALTER TABLE ... DROP COLUMN" without backup confirmation
  - "UPDATE ... SET" on millions of rows without batching
  - "CREATE INDEX" without CONCURRENTLY on large tables
  - Migration and code deploy in the same step
  - No mention of testing on staging first
```

**The meta-principle:** Database migrations should be boring. If a migration feels exciting or risky, it should be broken into smaller, safer steps. The safest migration is one that can be rolled back without data loss.'''
    ),
    (
        "thinking/auto-qa-deployment-containerization",
        r'''What quality checks should I apply when advising on containerized deployments (Docker, Kubernetes)?''',
        r'''<think>
Container deployments have their own set of failure modes that are different from traditional deployments. Common mistakes:

1. Running as root in containers
2. Using :latest tags instead of pinned versions
3. No resource limits (CPU/memory)
4. No health checks
5. Storing state in containers (ephemeral by nature)
6. Secrets in environment variables visible in `docker inspect`
7. Not handling SIGTERM gracefully
8. Oversized images (pulling takes too long, slows deploys)
</think>

**Container Deployment Quality Checklist**

**Before advising on any containerized deployment:**

**Docker Image Quality:**
```
□ BASE IMAGE: Using a specific tag, not :latest?
  BAD:  FROM python:latest
  GOOD: FROM python:3.12-slim

□ IMAGE SIZE: Is the image as small as possible?
  - Multi-stage build used?
  - .dockerignore configured?
  - Unnecessary tools/packages excluded?

□ SECURITY: Running as non-root user?
  BAD:  (no USER directive — runs as root)
  GOOD: RUN adduser --system appuser
        USER appuser

□ DEPENDENCIES: All deps pinned to specific versions?
  BAD:  pip install flask
  GOOD: pip install flask==3.0.1
```

**Kubernetes Deployment Quality:**
```
□ RESOURCE LIMITS: CPU and memory limits set?
  resources:
    requests:
      memory: "256Mi"
      cpu: "250m"
    limits:
      memory: "512Mi"
      cpu: "500m"
  (Without limits, one pod can starve others)

□ HEALTH CHECKS: Liveness and readiness probes configured?
  livenessProbe:
    httpGet:
      path: /health
      port: 8080
    initialDelaySeconds: 15
    periodSeconds: 10
  readinessProbe:
    httpGet:
      path: /ready
      port: 8080

□ REPLICAS: More than 1 replica for production?
  replicas: 3  (minimum for high availability)

□ ROLLING UPDATE: Deployment strategy configured?
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
```

**Graceful Shutdown:**
```
□ Application handles SIGTERM?
  When Kubernetes stops a pod, it sends SIGTERM.
  The app has terminationGracePeriodSeconds (default: 30s)
  to finish in-flight requests.

  Python example:
    import signal
    def handle_sigterm(signum, frame):
        server.shutdown()  # finish current requests
        sys.exit(0)
    signal.signal(signal.SIGTERM, handle_sigterm)

□ Pre-stop hook configured if app needs extra time?
  lifecycle:
    preStop:
      exec:
        command: ["sh", "-c", "sleep 5"]
```

**Secrets Management:**
```
□ Secrets NOT in Dockerfile or docker-compose.yml?
□ Using Kubernetes Secrets or external vault (HashiCorp Vault)?
□ Secrets mounted as files, not environment variables?
  (env vars are visible in `kubectl describe pod`)

  BETTER:
    volumeMounts:
    - name: secrets
      mountPath: /etc/secrets
      readOnly: true
```

**Common mistakes to flag:**
```
DANGEROUS:
  - "docker run --privileged" (gives container root access to host)
  - Exposing Docker socket inside container
  - No resource limits in production
  - Using :latest in production

PROBLEMATIC:
  - Storing data inside containers (use volumes/PVCs)
  - No log aggregation strategy
  - No network policies (all pods can talk to all pods)
```

**The meta-principle:** Containers add abstraction, and each layer of abstraction introduces new failure modes. Don't assume containers are "just like running on a server." They have unique requirements for health checks, resource management, graceful shutdown, and secrets handling that must be addressed explicitly.'''
    ),
    (
        "thinking/auto-qa-deployment-cicd-pipeline",
        r'''What quality checks should I apply when advising someone on setting up or modifying their CI/CD pipeline?''',
        r'''<think>
CI/CD pipelines are the backbone of deployment safety. A poorly configured pipeline can either block all deployments (too strict) or let broken code through (too loose). The quality checks need to ensure the pipeline is both safe and efficient.

**Key concerns:**
1. Are tests actually running? (not just passing because they're skipped)
2. Is the pipeline fast enough that people don't skip it?
3. Are secrets handled securely in the pipeline?
4. Is there a staging step before production?
5. Does the pipeline handle failures gracefully?
6. Are artifacts reproducible?
</think>

**CI/CD Pipeline Quality Checklist**

**Before advising on any CI/CD pipeline:**

**Pipeline Structure:**
```
□ STAGES: Does the pipeline have distinct stages?
  Minimum recommended:
  1. Lint / Format check
  2. Unit tests
  3. Integration tests
  4. Build artifact
  5. Deploy to staging
  6. Smoke tests on staging
  7. Deploy to production (manual gate or auto)
  8. Post-deploy verification

□ FAIL FAST: Cheap checks run before expensive ones?
  - Linting (seconds) before tests (minutes)
  - Unit tests before integration tests
  - Build before deploy

□ PARALLELISM: Independent steps run in parallel?
  - Lint and test can run simultaneously
  - Multiple test suites can run in parallel
```

**Test Quality:**
```
□ TESTS ACTUALLY RUN: Not just "exit 0"?
  Check: Does the pipeline fail when you deliberately break a test?

□ COVERAGE THRESHOLD: Is there a minimum coverage gate?
  Not 100% (impractical), but something meaningful (70-80%)

□ TEST TYPES: Multiple layers?
  - Unit tests (fast, isolated)
  - Integration tests (verify component interactions)
  - End-to-end tests (verify user flows)

□ FLAKY TEST HANDLING: Are flaky tests tracked and addressed?
  Not ignored or auto-retried into oblivion
```

**Security in the Pipeline:**
```
□ SECRETS: Not hardcoded in pipeline config?
  BAD:  env: API_KEY=sk-abc123
  GOOD: env: API_KEY=${{ secrets.API_KEY }}

□ DEPENDENCY SCANNING: Automated vulnerability checks?
  - npm audit / pip audit / Snyk / Dependabot
  - Run on every PR, not just weekly

□ SAST: Static analysis for security issues?
  - Semgrep, CodeQL, or similar
  - Runs automatically, blocks merge on critical findings

□ SECRET SCANNING: Prevent accidental secret commits?
  - git-secrets, trufflehog, or GitHub secret scanning
```

**Deployment Safety:**
```
□ STAGING BEFORE PRODUCTION: Always?
  Production deploys should NEVER be the first deploy
  of a particular build.

□ MANUAL GATE FOR PRODUCTION: Requires human approval?
  For most teams, production deploys should require
  explicit approval (click a button, not automatic).

□ ARTIFACT IMMUTABILITY: Same artifact in staging and production?
  Don't rebuild for production — deploy the exact same
  artifact that was tested in staging.

□ ROLLBACK: Can the pipeline roll back quickly?
  One-click rollback to previous version should be available.
```

**Pipeline Performance:**
```
□ TOTAL TIME: Under 15 minutes for the full pipeline?
  If longer, developers will skip it or push to bypass.

□ CACHING: Dependencies cached between runs?
  - node_modules, pip cache, Docker layers
  - Can cut pipeline time by 50%+

□ INCREMENTAL: Only running tests affected by changes?
  For large monorepos, running ALL tests on every PR is slow.
  Use tools like nx affected or pytest --collect-only with git diff.
```

**Common pipeline anti-patterns to flag:**
```
DANGEROUS:
  - No pipeline at all (deploying from local machine)
  - Tests disabled "temporarily" (they're never re-enabled)
  - Production deploy without staging
  - Secrets in pipeline config files

PROBLEMATIC:
  - Pipeline takes >30 minutes (people bypass it)
  - No caching (wasteful and slow)
  - Manual deployment steps mixed with automated ones
  - No artifact versioning (can't reproduce old deploys)
```

**The meta-principle:** A good CI/CD pipeline is one that developers trust and don't try to bypass. If people are skipping the pipeline, it's either too slow, too flaky, or too strict on things that don't matter. Balance safety with speed — both are essential.'''
    ),
    (
        "thinking/auto-qa-deployment-monitoring",
        r'''What quality checks should I apply when advising on monitoring and observability as part of a deployment strategy?''',
        r'''<think>
Monitoring and observability are often an afterthought in deployment advice, but they're what tells you whether your deployment actually succeeded. Without monitoring, you're deploying blind.

**Key monitoring aspects:**
1. What to monitor (metrics, logs, traces)
2. What to alert on (and what NOT to alert on)
3. Dashboards that actually help during incidents
4. SLOs/SLIs that matter to the business
5. On-call and incident response integration

**Common mistakes:**
- Monitoring everything but alerting on nothing useful
- Too many alerts (alert fatigue)
- Dashboards that look pretty but don't help debug
- No correlation between metrics, logs, and traces
- Missing business metrics (only technical metrics)
</think>

**Monitoring and Observability Quality Checklist**

**Before advising on monitoring for any deployment:**

**The Three Pillars (verify all present):**
```
□ METRICS: Quantitative measurements over time
  Minimum set:
  - Request rate (requests/second)
  - Error rate (errors/second and error percentage)
  - Latency (P50, P95, P99)
  - Saturation (CPU, memory, disk, connections)

□ LOGS: Structured event records
  Minimum requirements:
  - Structured format (JSON, not plain text)
  - Request ID for correlation
  - Severity levels used correctly (ERROR vs. WARN vs. INFO)
  - PII excluded from logs

□ TRACES: Request flow across services
  Needed when:
  - Multiple services involved
  - Need to find WHERE a request slows down
  - Debugging distributed transactions
```

**Alerting Quality:**
```
□ ACTIONABLE: Every alert has a clear response action?
  BAD:  "CPU is at 75%" (so what?)
  GOOD: "Error rate >5% for 5 minutes. Runbook: [link]"

□ SEVERITY LEVELS: Alerts are tiered?
  CRITICAL: Immediate response needed (page on-call)
  WARNING: Investigate within hours
  INFO: Track, no immediate action

□ NO ALERT FATIGUE: Fewer than 5 pages per week?
  If the team gets paged constantly, they stop responding.
  Each false alert erodes trust in the alerting system.

□ SLO-BASED: Alerts tied to service level objectives?
  "Error budget burn rate >10x" is better than
  "Error rate >1%" because it accounts for context.
```

**Dashboard Quality:**
```
□ THE FOUR GOLDEN SIGNALS visible on one screen:
  1. Latency (how long requests take)
  2. Traffic (how many requests)
  3. Errors (how many are failing)
  4. Saturation (how full are resources)

□ TIME RANGE: Comparison with "normal" visible?
  Show current metrics overlaid with last week's metrics
  so anomalies are immediately visible.

□ DRILL-DOWN: Can you go from dashboard to specific logs?
  Click high error rate → see which endpoints → see error logs

□ DEPLOYMENT MARKERS: Deploys visible on graphs?
  This lets you instantly correlate problems with deploys.
```

**Post-Deploy Monitoring Protocol:**
```
After every deployment, monitor for 30 minutes:
1. Error rate: Did it increase? (even 0.1% increase matters)
2. Latency: Did P99 increase? (tail latency catches regressions)
3. Traffic: Is traffic flowing normally? (zero traffic = broken routing)
4. Resource usage: Memory/CPU spike? (memory leak in new code)
5. Business metrics: Are users completing key flows?

If any metric degrades beyond threshold → trigger rollback.
```

**Common monitoring advice mistakes to avoid:**
```
BAD ADVICE:
  "Add logging everywhere" → Generates noise, increases costs
  "Alert on everything" → Alert fatigue, team ignores alerts
  "Monitor CPU and memory" → Missing the metrics that matter
  "Use [specific tool]" → Without explaining what to monitor

GOOD ADVICE:
  "Monitor the four golden signals, alert only on SLO violations,
   use structured logging with request correlation, and deploy
   markers on all dashboards."
```

**The meta-principle:** Monitoring is not about collecting data — it's about answering the question "is the system healthy?" If your monitoring can't answer that question within 30 seconds of looking at a dashboard, it needs to be restructured around the signals that matter.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
