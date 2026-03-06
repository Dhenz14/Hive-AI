"""Phase 3E: Metacognition — Learning From Mistakes (Part 8)

Remaining pairs for scenarios 11-13: encoding bugs, deployment failures, monitoring gaps.
"""

PAIRS = [
    (
        "thinking/meta-mistakes-encoding-path-unicode",
        r'''Our file upload system works in development but fails for some users in production. The error is:

```
UnicodeEncodeError: 'ascii' codec can't encode character '\u00e9' in position 5: ordinal not in range(128)
```

The code:
```python
def save_upload(file, username):
    filepath = f"/uploads/{username}/{file.filename}"
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'wb') as f:
        f.write(file.read())
```

It fails when usernames contain accented characters like "René" or "José".''',
        r'''<think>
I made an error: the system's filesystem encoding or locale doesn't support Unicode characters in file paths. On Linux, if the locale is set to C or POSIX (common in Docker containers), file paths are treated as ASCII-only.

The mistake was: using user-provided strings (usernames) directly in file paths without sanitizing or encoding them. Even if the filesystem supports Unicode, it's fragile.

The root cause was: two issues — (1) not controlling the locale/encoding in the deployment environment, and (2) using user-provided strings directly in filesystem paths. In dev (macOS/Windows), Unicode filenames just work. In production Docker containers, the default locale is often `C` (ASCII only).

Generalizable lesson: Never use user-provided strings directly in file paths. Sanitize to ASCII-safe characters, or use UUIDs/hashes as file paths and store the human-readable name in a database. Also, always set locale in Docker containers.

Checklist item: For any code that creates file paths from user input: (1) Is the input sanitized? (2) What's the filesystem encoding in production? (3) Would a UUID be safer?

Similar situations where this lesson applies:
1. Email attachments with Unicode filenames
2. S3 object keys with special characters
3. Log files named after user input
</think>

**Two fixes needed: Docker locale + safe file paths.**

**Fix 1: Set locale in Docker (immediate fix):**
```dockerfile
# Dockerfile
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
```
Or in your entrypoint: `export LANG=C.UTF-8`

**Fix 2: Don't use user input in file paths (proper fix):**
```python
import uuid

def save_upload(file, username):
    # Use UUID for the filesystem, store metadata in DB
    file_id = str(uuid.uuid4())
    filepath = f"/uploads/{file_id}"

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'wb') as f:
        f.write(file.read())

    # Store the mapping in the database
    db.create(Upload,
        id=file_id,
        username=username,  # Unicode is fine in the DB
        original_filename=file.filename,
        path=filepath
    )
    return file_id
```

**Why UUIDs are better than sanitized names:**
- No encoding issues (UUIDs are ASCII hex)
- No path traversal attacks (`../../etc/passwd`)
- No filename collisions
- No need to handle special characters, spaces, or length limits

**The lesson: keep user input out of file paths.** Use opaque identifiers (UUIDs) for the filesystem and store human-readable names in the database. This eliminates encoding, security, and collision problems simultaneously.'''
    ),
    (
        "thinking/meta-mistakes-encoding-json-bytes",
        r'''Our API returns garbled data for some non-English users. The response JSON contains \uXXXX escape sequences instead of actual characters:

```python
@app.get("/users/{user_id}")
def get_user(user_id: int):
    user = db.get(User, user_id)
    return Response(
        content=json.dumps(user.to_dict()),
        media_type="application/json"
    )
```

Response: `{"name": "\u5f20\u4e09", "city": "\u5317\u4eac"}` instead of `{"name": "张三", "city": "北京"}`.''',
        r'''<think>
I made an error: `json.dumps()` by default escapes non-ASCII characters to `\uXXXX` sequences. While this is valid JSON, it's ugly and some clients don't handle it well.

The mistake was: not using `ensure_ascii=False` in `json.dumps()`. Python's default is `ensure_ascii=True`, which escapes all non-ASCII characters.

The root cause was: not understanding json.dumps() defaults. The `\uXXXX` output is technically valid JSON — any compliant parser will decode it correctly. But it's harder to read, takes more bytes, and some poorly-written clients or logging systems don't decode it.

Generalizable lesson: When generating JSON with non-ASCII content, use `ensure_ascii=False` and set the Content-Type charset to utf-8. This produces readable, compact JSON. Also, use your framework's built-in JSON response (which usually handles this correctly) instead of manual Response construction.

Checklist item: When using json.dumps() directly: is ensure_ascii set? Is the response Content-Type correct? Could you use the framework's JSONResponse instead?

Similar situations where this lesson applies:
1. Logging JSON with Unicode — escaped sequences make logs unreadable
2. Storing JSON in files — ensure_ascii=False saves space with non-ASCII data
3. API documentation showing escaped characters confusing consumers
</think>

**Use `ensure_ascii=False` in json.dumps():**

```python
# Before (escaped):
json.dumps({"name": "张三"})
# '{"name": "\\u5f20\\u4e09"}'

# After (readable):
json.dumps({"name": "张三"}, ensure_ascii=False)
# '{"name": "张三"}'
```

**Better fix — use the framework's JSONResponse:**
```python
from fastapi.responses import JSONResponse

@app.get("/users/{user_id}")
def get_user(user_id: int):
    user = db.get(User, user_id)
    return JSONResponse(content=user.to_dict())
    # FastAPI's JSONResponse handles encoding correctly
```

**Or configure globally in FastAPI:**
```python
from fastapi.responses import ORJSONResponse  # or UJSONResponse

app = FastAPI(default_response_class=ORJSONResponse)
```

Both `\uXXXX` and actual Unicode are valid JSON, but:
- `\uXXXX` takes more bytes
- Logs and debugging become unreadable
- Some clients handle it poorly

**The lesson: use your framework's JSON response instead of manual json.dumps().** If you must use json.dumps(), set `ensure_ascii=False` for non-ASCII content.'''
    ),
    (
        "thinking/meta-mistakes-deployment-no-rollback",
        r'''We deployed a database migration that added a NOT NULL column without a default value. The deployment succeeded but the app immediately crashed because existing rows violated the constraint. We couldn't roll back because the migration had already altered the table:

```python
# migration
def upgrade():
    op.add_column('users', sa.Column('phone', sa.String(), nullable=False))

def downgrade():
    op.drop_column('users', 'phone')
```

We had to write an emergency migration to make it nullable, but the app was down for 45 minutes.''',
        r'''<think>
I made an error: adding a NOT NULL column without a default value fails immediately if the table has existing rows. This is a known PostgreSQL behavior — you can't add a NOT NULL column without a default to a table with data.

The mistake was: not testing the migration against a copy of production data. It worked in dev (empty or small table) but failed in production (millions of rows).

The root cause was: treating database migrations as regular code deployments. Code deployments are easily reversible (redeploy old version). Database migrations are NOT — they alter shared state. A destructive migration with no rollback plan = guaranteed risk.

Generalizable lesson: Database migrations should be backwards-compatible and reversible. Never add NOT NULL without a default. Always test migrations against production-sized data. Make deploys reversible by separating schema changes from code changes.

Checklist item: For any migration: (1) Does it work on a table with existing data? (2) Can the old code still work with the new schema? (3) Can I roll back without data loss?

Similar situations where this lesson applies:
1. Renaming columns (old code can't find the column)
2. Dropping columns that old code still references
3. Changing column types with incompatible data
</think>

**NOT NULL without a default is an instant failure on tables with existing data.**

**Safe migration pattern — expand/migrate/contract:**

**Step 1: Add column as nullable (safe, backwards-compatible):**
```python
def upgrade():
    op.add_column('users', sa.Column('phone', sa.String(), nullable=True))
```

**Step 2: Backfill existing rows (separate migration):**
```python
def upgrade():
    op.execute("UPDATE users SET phone = '' WHERE phone IS NULL")
```

**Step 3: Add NOT NULL constraint (after backfill completes):**
```python
def upgrade():
    op.alter_column('users', 'phone', nullable=False, server_default='')
```

**Each step is independently deployable and reversible.** If step 2 is slow (millions of rows), it doesn't block deploys or lock the table.

**Migration safety checklist:**
- ❌ Never `ADD COLUMN ... NOT NULL` without a default
- ❌ Never `DROP COLUMN` while old code might reference it
- ❌ Never `RENAME COLUMN` in a single step
- ✅ Add nullable columns, backfill, then add constraint
- ✅ Add new column, migrate code, then drop old column
- ✅ Test against a production-sized database copy

**The lesson: make deploys reversible.** Database migrations should be additive and backwards-compatible. The old code should work with the new schema, and the new code should work with the old schema. This gives you a safe rollback path.'''
    ),
    (
        "thinking/meta-mistakes-deployment-migration-lock",
        r'''Our deployment took down the entire application for 20 minutes. We were adding an index to a table with 50M rows:

```python
def upgrade():
    op.create_index('idx_orders_user_date', 'orders', ['user_id', 'created_at'])
```

The migration locked the entire `orders` table, blocking all reads and writes. The app couldn't process any orders during the migration.''',
        r'''<think>
I made an error: `CREATE INDEX` in PostgreSQL takes an ACCESS EXCLUSIVE lock by default, which blocks all reads and writes on the table for the duration of the index build. On a 50M row table, this can take minutes.

The mistake was: not using `CREATE INDEX CONCURRENTLY`, which builds the index without locking the table.

The root cause was: not understanding that database DDL operations can lock tables. In development with small tables, index creation is instant. In production with millions of rows, it can take minutes — and the lock blocks the entire application.

Generalizable lesson: DDL operations on large tables can lock the table and cause downtime. Always use non-blocking variants: `CREATE INDEX CONCURRENTLY`, `ALTER TABLE ... ADD COLUMN` (doesn't lock in modern PostgreSQL for nullable columns), etc. Test migrations on production-sized data to understand lock duration.

Checklist item: For any migration on a table with > 100K rows: "Does this operation lock the table? Is there a non-blocking alternative?"

Similar situations where this lesson applies:
1. Adding a foreign key constraint (validates all existing rows, locks table)
2. Changing a column type (rewrites entire table, locks it)
3. VACUUM FULL on a large table (rewrites and locks)
</think>

**`CREATE INDEX` locks the entire table. Use `CREATE INDEX CONCURRENTLY` instead.**

**Fix:**
```python
def upgrade():
    # CONCURRENTLY builds the index without locking reads/writes
    op.execute("CREATE INDEX CONCURRENTLY idx_orders_user_date ON orders (user_id, created_at)")

def downgrade():
    op.execute("DROP INDEX CONCURRENTLY idx_orders_user_date")
```

**Important: Alembic requires special handling for CONCURRENTLY:**
```python
from alembic import op

def upgrade():
    # Must disable transaction for CONCURRENTLY
    op.execute("COMMIT")  # End Alembic's transaction
    op.execute("CREATE INDEX CONCURRENTLY idx_orders_user_date ON orders (user_id, created_at)")
```

Or in the migration header:
```python
# revision directives
revision = 'abc123'
down_revision = 'def456'

# Disable transaction wrapping for this migration
transaction = False
```

**PostgreSQL locking cheat sheet:**
| Operation | Locks table? | Non-blocking alternative |
|-----------|-------------|------------------------|
| CREATE INDEX | Yes | CREATE INDEX CONCURRENTLY |
| ADD COLUMN (nullable) | No (PG 11+) | Already safe |
| ADD COLUMN NOT NULL + default | Rewrites table (< PG 11) | Add nullable, backfill, add constraint |
| DROP COLUMN | Brief lock | Safe, just drop |
| ADD FOREIGN KEY | Validates all rows | ADD CONSTRAINT ... NOT VALID, then VALIDATE |
| ALTER COLUMN TYPE | Rewrites table | Create new column, migrate, drop old |

**The lesson: test migrations on production-sized data.** A migration that takes 1ms on 100 rows can take 20 minutes on 50M rows — with a full table lock. Always use CONCURRENTLY for indexes on large tables.'''
    ),
    (
        "thinking/meta-mistakes-deployment-env-var-missing",
        r'''We deployed a new version that requires a new environment variable (ANALYTICS_API_KEY). The deployment succeeded but the analytics feature started throwing errors because the env var wasn't added to the production configuration:

```python
# New code
ANALYTICS_API_KEY = os.environ["ANALYTICS_API_KEY"]  # KeyError in production!
```

The deploy pipeline didn't catch this because the env var existed in staging but not in production.''',
        r'''<think>
I made an error: the code requires a new environment variable but the deployment process doesn't verify that all required env vars are present before starting the new version.

The mistake was: treating code deployment and configuration as separate, uncoordinated concerns. New code that requires new config should fail the deploy if the config isn't present.

The root cause was: no automated verification of environment configuration during deployment. The staging environment happened to have the variable (someone added it manually), but production didn't. There's no checklist or automated check to ensure parity.

Generalizable lesson: Deployments should verify that all required configuration exists BEFORE starting the new version. Use startup health checks that validate config, and make the deploy process check configuration parity between environments.

Checklist item: When adding a new environment variable: (1) Add it to ALL environments before deploying the code that uses it. (2) Add it to the config validation/health check. (3) Document it in the env.example file.

Similar situations where this lesson applies:
1. Feature flags that exist in staging but not production
2. Database migrations that are run in staging but forgotten in production
3. New external service endpoints configured in dev but not prod
</think>

**Deploy pipeline should verify required config before starting new code.**

**Fix 1: Startup config validation (catch immediately):**
```python
# config.py — runs at startup
REQUIRED_VARS = [
    "DATABASE_URL",
    "REDIS_URL",
    "ANALYTICS_API_KEY",  # Add new vars here
]

def validate_config():
    missing = [var for var in REQUIRED_VARS if var not in os.environ]
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")

validate_config()  # App crashes immediately, not hours later
```

**Fix 2: Pre-deploy health check:**
```yaml
# deploy.yml (GitHub Actions / CI)
- name: Verify required env vars in production
  run: |
    REQUIRED="DATABASE_URL REDIS_URL ANALYTICS_API_KEY"
    for var in $REQUIRED; do
      if ! kubectl exec deploy/myapp -- printenv $var > /dev/null 2>&1; then
        echo "MISSING in production: $var"
        exit 1
      fi
    done
```

**Fix 3: Rolling deploy with health checks:**
```yaml
# Kubernetes deployment
spec:
  containers:
  - name: myapp
    livenessProbe:
      httpGet:
        path: /health
        port: 8080
      initialDelaySeconds: 5
    # If /health fails (config missing), rollback automatically
```

**The deployment checklist for new env vars:**
1. Add to `.env.example` (documentation)
2. Add to all environments BEFORE deploying code
3. Add to config validation in the app
4. Verify in CI/CD pipeline pre-deploy check

**The lesson: make deploys reversible with automated checks.** New code + new config = deploy the config first, then the code. Health checks ensure the app rolls back automatically if config is missing.'''
    ),
    (
        "thinking/meta-mistakes-monitoring-uptime-not-function",
        r'''Our monitoring says the API is healthy (200 OK on /health) but users report they can't complete purchases. We didn't notice for 4 hours:

```python
@app.get("/health")
def health():
    return {"status": "ok"}  # Always returns 200

# Meanwhile, the Stripe integration was failing because the API key expired
# Users got errors on checkout but /health still said "ok"
```''',
        r'''<think>
I made an error: the health check only verifies that the web server is running, not that the application actually works. It's a liveness check, not a readiness check.

The mistake was: implementing the simplest possible health check (return 200) instead of actually checking dependencies. If the database is down, Redis is unreachable, or Stripe keys are expired, /health still says "ok."

The root cause was: monitoring the wrong thing. We monitored "is the process alive" (symptoms: server responds) but not "can the app serve users" (symptoms: checkout works). Alerting on server health when the real concern is business function.

Generalizable lesson: Alert on symptoms, not causes. Monitor what users experience (can they check out? do pages load in < 2s?) not just what servers report (process is running, CPU is normal). Health checks should verify actual functionality — database connectivity, external API availability, and critical path operations.

Checklist item: For every health endpoint: "If [dependency] is down, does /health still return 200?" If yes, add that dependency check.

Similar situations where this lesson applies:
1. Monitoring CPU/memory instead of response times
2. Checking that a queue consumer is running but not that messages are being processed
3. Monitoring that cron jobs start but not that they complete successfully
</think>

**Your health check doesn't check health.** It only proves the web server responds.

**Fix — check actual dependencies:**
```python
@app.get("/health")
def health():
    checks = {}

    # Check database
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Check Redis
    try:
        redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # Check Stripe connectivity
    try:
        stripe.Account.retrieve()
        checks["stripe"] = "ok"
    except Exception as e:
        checks["stripe"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503

    return JSONResponse(
        content={"status": "ok" if all_ok else "degraded", "checks": checks},
        status_code=status_code
    )
```

**Two types of health checks:**

| Check | What it answers | When to use |
|-------|----------------|-------------|
| **Liveness** (`/healthz`) | "Is the process alive?" | Kubernetes restart decisions |
| **Readiness** (`/readyz`) | "Can it serve traffic?" | Load balancer routing |

```python
@app.get("/healthz")
def liveness():
    return {"status": "alive"}  # Simple, always 200 if process runs

@app.get("/readyz")
def readiness():
    # Check all dependencies
    if not db.is_connected() or not redis.ping():
        return JSONResponse({"status": "not ready"}, status_code=503)
    return {"status": "ready"}
```

**Then monitor business metrics too:**
- Checkout success rate (should be > 95%)
- Payment processing time (should be < 5s)
- Error rate by endpoint

**The lesson: alert on symptoms, not causes.** Monitor what users experience (can they check out?) not just what servers report (process is alive). A health check that always returns 200 is useless.'''
    ),
    (
        "thinking/meta-mistakes-monitoring-alert-fatigue",
        r'''We have 200+ alerts configured but our team ignores most of them because they fire constantly. Last week we missed a real outage because the alert was buried in hundreds of "warning" notifications:

```yaml
# Our alerting rules (sample):
- alert: HighCPU
  expr: cpu_usage > 70
  for: 5m
- alert: HighMemory
  expr: memory_usage > 60
  for: 5m
- alert: SlowQuery
  expr: query_duration > 100ms
  for: 1m
- alert: HighErrorRate
  expr: error_rate > 0.1%
  for: 1m
# ... 196 more alerts
```

These fire dozens of times daily. The team has muted the Slack channel.''',
        r'''<think>
I made an error: creating too many sensitive alerts that fire on normal operational noise. When alerts fire constantly, the team learns to ignore them (alert fatigue), and real incidents get buried.

The mistake was: setting thresholds too aggressively. 70% CPU is normal under load. 60% memory is expected. 100ms queries happen during batch jobs. 0.1% error rate includes client errors (404s). These are warnings at best, not alerts.

The root cause was: alerting on causes instead of symptoms, with thresholds that don't account for normal operational variance. High CPU doesn't mean users are affected. What matters is: are users getting errors? Are requests timing out?

Generalizable lesson: Alert on user-facing symptoms, not internal metrics. Fewer, high-quality alerts that always indicate a real problem. Every alert should be actionable — if it fires, someone needs to do something. If you can't define the action, delete the alert.

Checklist item: For every alert: "When this fires, what does the on-call engineer DO?" If the answer is "look at it and dismiss it," the alert is noise — remove it.

Similar situations where this lesson applies:
1. Log level warnings that are really informational
2. CI notifications for non-blocking test flakes
3. Security scanners that flag hundreds of "medium" issues
</think>

**200 noisy alerts = 0 effective alerts.** Alert fatigue is the #1 monitoring failure mode.

**Fix — reduce to ~10-20 high-signal alerts:**

**Keep (user-facing symptoms):**
```yaml
- alert: HighErrorRate
  expr: http_errors_5xx / http_requests_total > 0.01  # 1% server errors
  for: 5m
  severity: critical  # Page on-call

- alert: HighLatency
  expr: http_request_duration_p99 > 2s
  for: 10m
  severity: critical

- alert: CheckoutFailureRate
  expr: checkout_failures / checkout_attempts > 0.05  # 5% checkout failures
  for: 5m
  severity: critical

- alert: DatabaseDown
  expr: pg_up == 0
  for: 1m
  severity: critical
```

**Remove or convert to dashboards (internal metrics):**
```yaml
# These are NOT alerts — they're dashboard metrics:
# - CPU > 70% (normal under load)
# - Memory > 60% (expected)
# - Query > 100ms (some queries are slow, that's fine)
# - Error rate > 0.1% (includes 404s, client errors)
```

**Alert severity tiers:**
| Tier | Threshold | Action | Channel |
|------|-----------|--------|---------|
| Critical | User-facing impact confirmed | Page on-call immediately | PagerDuty |
| Warning | Potential issue, investigate soon | Notify during business hours | Slack (separate channel) |
| Info | Interesting but no action needed | Dashboard only | No notification |

**Rules for good alerts:**
1. Every alert must have a runbook (what to do when it fires)
2. If an alert fires > 2x/week without action, raise the threshold or delete it
3. Alert on symptoms (error rate, latency) not causes (CPU, memory)
4. Use `for: 5m+` to avoid flapping on brief spikes

**The lesson: fewer, higher-quality alerts that always mean "take action now."** If your team is ignoring alerts, the alerts are broken. Fix the alerts, not the team.'''
    ),
    (
        "thinking/meta-mistakes-monitoring-no-baseline",
        r'''We got paged for "high response time" but couldn't tell if it was actually abnormal because we don't know what normal looks like:

```
ALERT: Average response time is 450ms (threshold: 400ms)
```

Is 450ms actually bad? We don't know our normal baseline. Some days it's 300ms, some days it's 500ms. The alert fires every few days and we never know if it's a real problem.''',
        r'''<think>
I made an error: setting a static threshold without understanding the normal distribution of response times. A fixed 400ms threshold doesn't account for daily patterns, traffic variations, or seasonal differences.

The mistake was: picking a threshold by gut feeling instead of measuring the actual baseline. 400ms might be below the normal peak-hours average, causing constant false alarms.

The root cause was: alerting without first establishing a baseline. Without knowing what "normal" looks like, you can't define "abnormal."

Generalizable lesson: Before setting alert thresholds, measure the baseline for at least 2 weeks. Use percentile-based thresholds (p99, p95) instead of averages. Use dynamic thresholds (standard deviations from the rolling average) instead of static numbers. Alert on significant deviations from normal, not on arbitrary fixed values.

Checklist item: For any performance alert: "What's the normal range for this metric? Is the threshold based on measured data or a guess?"

Similar situations where this lesson applies:
1. Error rate alerts without knowing the normal error rate
2. Disk usage alerts without knowing the growth rate
3. Queue depth alerts without knowing normal processing patterns
</think>

**You can't alert on abnormal without defining normal first.**

**Step 1: Measure the baseline (2 weeks minimum):**
```python
# Collect percentile data over time:
# p50 (median): 250ms
# p95: 500ms
# p99: 1200ms
# Daily pattern: 200ms at 3am, 600ms at 2pm (lunch rush)
# Weekly pattern: faster on weekends
```

**Step 2: Set thresholds based on actual data:**
```yaml
# Bad: static threshold with no basis
- alert: HighLatency
  expr: avg(response_time) > 400ms  # Fires randomly

# Good: percentile-based, accounts for distribution
- alert: HighLatency
  expr: histogram_quantile(0.99, http_request_duration) > 2s
  for: 10m
  # P99 > 2s for 10 minutes = genuinely abnormal

# Better: dynamic threshold (standard deviation from rolling average)
- alert: LatencyAnomaly
  expr: |
    avg(response_time[5m]) >
    avg(response_time[7d]) + 2 * stddev(response_time[7d])
  for: 15m
  # Alert when current latency is 2+ standard deviations above the 7-day average
```

**Key principles:**
- **Use p99, not average**: Average hides outliers. P99 shows what slow users experience
- **Use `for:` durations**: Brief spikes are normal. Sustained degradation isn't
- **Compare to history**: "450ms" means nothing. "2x the 7-day average" means something
- **Account for daily patterns**: 2pm is always slower than 3am — don't alert on expected patterns

**The lesson: measure before you alert.** Establish a baseline, then alert on statistically significant deviations from it. Static thresholds based on gut feelings create noise.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
