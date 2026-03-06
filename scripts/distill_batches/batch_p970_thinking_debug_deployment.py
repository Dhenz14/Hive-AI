PAIRS = [
    ("thinking/debugging", r'''Our application crashes on startup in production with:

```
KeyError: 'DATABASE_URL'
```

The environment variable is set in our deployment config:

```yaml
# kubernetes deployment.yaml
spec:
  containers:
    - name: app
      image: myapp:latest
      envFrom:
        - secretRef:
            name: app-secrets
```

But `kubectl get secret app-secrets -o yaml` shows the secret exists with the right key. The pod starts, the env var is missing, and the app crashes. Locally it works fine with a .env file.''', r'''<think>
Several possible causes:

1. The secret key name might have a different case or extra whitespace
2. The secret might be in a different namespace
3. The secret might have been created with a different encoding
4. The secretRef name might be misspelled
5. The pod might not have permission to read the secret (RBAC)
6. The application reads the env var before it's available

Let me think about common Kubernetes secret issues...

The most common cause is that the secret data keys contain whitespace, or the base64 encoding is wrong (common when using `kubectl create secret` with a file that has a trailing newline).

Another common issue: the secret was created in the default namespace but the pod is in a different namespace.
</think>

There are several common causes for secrets not appearing as environment variables in Kubernetes. Let me go through the diagnostic steps:

**Step 1: Verify the secret exists in the correct namespace**

```bash
# Check the pod's namespace
kubectl get pod <pod-name> -o jsonpath='{.metadata.namespace}'

# Check the secret exists in that SAME namespace
kubectl get secret app-secrets -n <namespace>

# Secrets are namespace-scoped! A secret in 'default' is not visible in 'production'
```

**Step 2: Check the secret key names**

```bash
kubectl get secret app-secrets -o jsonpath='{.data}' | python -m json.tool
```

Common issues:
```yaml
# WRONG: key has a dot (becomes invalid env var name)
data:
  database.url: base64value  # becomes DATABASE.URL which is invalid

# WRONG: key has trailing whitespace
data:
  "DATABASE_URL ": base64value  # note the trailing space!

# RIGHT:
data:
  DATABASE_URL: base64value
```

**Step 3: Verify the base64 encoding**

```bash
# Decode and check for trailing newlines
kubectl get secret app-secrets -o jsonpath='{.data.DATABASE_URL}' | base64 -d | cat -A

# If you see a trailing $ or ^M, there's a newline or carriage return
# postgres://user:pass@host:5432/mydb$   <- trailing newline

# The env var will include the newline, which can break connection strings!
```

**Fix: Recreate the secret without trailing newlines**

```bash
# WRONG: echo adds a trailing newline
echo "postgres://user:pass@host:5432/mydb" | base64
# Result includes newline in the value

# RIGHT: echo -n (no trailing newline)
kubectl create secret generic app-secrets \
    --from-literal=DATABASE_URL='postgres://user:pass@host:5432/mydb'

# Or from file with proper encoding:
printf '%s' 'postgres://user:pass@host:5432/mydb' > /tmp/db_url
kubectl create secret generic app-secrets --from-file=DATABASE_URL=/tmp/db_url
rm /tmp/db_url
```

**Step 4: Check RBAC permissions**

```bash
# Can the pod's service account read secrets?
kubectl auth can-i get secrets --as=system:serviceaccount:<namespace>:<sa-name>
```

**Step 5: Check pod events for errors**

```bash
kubectl describe pod <pod-name> | grep -A 5 "Events"
# Look for:
# Warning  Failed  ... Error: secret "app-secrets" not found
# Warning  Failed  ... Error: couldn't find key DATABASE_URL in Secret
```

**Fix the application to fail clearly:**

```python
import os
import sys

REQUIRED_ENV_VARS = ['DATABASE_URL', 'SECRET_KEY', 'REDIS_URL']

missing = [var for var in REQUIRED_ENV_VARS if var not in os.environ]
if missing:
    print(f"FATAL: Missing required environment variables: {', '.join(missing)}")
    print(f"Available env vars: {sorted(os.environ.keys())}")
    sys.exit(1)
```

**Prevention tips:**
- Always validate required environment variables at startup with clear error messages
- Use `--from-literal` when creating secrets to avoid encoding issues
- Keep secrets and deployments in the same namespace
- Use `kubectl describe pod` to check for secret mounting errors
- Add a startup probe that validates configuration before accepting traffic
- Use a configuration library (like python-decouple or pydantic-settings) with validation'''),

    ("thinking/debugging", r'''Our secret rotation broke production. We rotated the database password but the application kept using the old password:

```
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError)
FATAL: password authentication failed for user "app_user"
```

We updated the secret in Kubernetes:
```bash
kubectl create secret generic db-secret \
    --from-literal=DB_PASSWORD='new-password-xyz' \
    --dry-run=client -o yaml | kubectl apply -f -
```

But pods still use the old password. They don't automatically pick up the new secret.''', r'''<think>
Kubernetes does NOT automatically restart pods when a secret changes. If the secret is injected as an environment variable (via envFrom or env.valueFrom), the pod retains the env var values from when it started. The pod must be restarted to pick up the new secret.

If the secret is mounted as a volume, Kubernetes does update the mounted file eventually (kubelet sync period, default ~1 minute), but environment variables are never updated.

The fix: restart the pods after rotating the secret, or use a volume mount and watch for file changes, or use an external secret manager with built-in rotation.
</think>

Kubernetes does NOT automatically update environment variables when a secret changes. Environment variables are set when the container starts and never change during the container's lifetime. You must restart the pods to pick up the new secret value.

**The problem:**

```
1. Pod starts with DB_PASSWORD=old-password-abc (from secret)
2. Secret is updated to DB_PASSWORD=new-password-xyz
3. Pod still has DB_PASSWORD=old-password-abc in its environment
4. Old password is revoked on the database
5. Pod tries to connect with old password -> authentication fails
```

**Fix 1: Restart pods after secret rotation**

```bash
# Update the secret
kubectl create secret generic db-secret \
    --from-literal=DB_PASSWORD='new-password-xyz' \
    --dry-run=client -o yaml | kubectl apply -f -

# Restart pods to pick up new secret
kubectl rollout restart deployment myapp

# Verify new pods are running
kubectl rollout status deployment myapp
```

**Fix 2: Use a rolling restart with zero downtime**

```bash
# Annotate the deployment to trigger a rolling update
kubectl patch deployment myapp -p \
    "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"secret-rotation\":\"$(date +%s)\"}}}}}"
```

This changes the pod template, triggering a rolling update. Old pods with the old password are replaced one by one with new pods that have the new password.

**Fix 3: Mount secrets as files (auto-updated)**

```yaml
spec:
  containers:
    - name: app
      volumeMounts:
        - name: db-secret
          mountPath: /etc/secrets
          readOnly: true
  volumes:
    - name: db-secret
      secret:
        secretName: db-secret
```

Mounted secret files are updated by kubelet periodically (default ~1 minute). Your application must read the file on each connection:

```python
def get_db_password():
    with open('/etc/secrets/DB_PASSWORD', 'r') as f:
        return f.read().strip()

def get_connection():
    password = get_db_password()  # reads fresh value each time
    return create_engine(f'postgresql://app_user:{password}@db-host/mydb')
```

**Fix 4: Use a proper secret rotation strategy**

```
Phase 1: Add new password to database (both old and new work)
  ALTER USER app_user SET PASSWORD 'new-password-xyz';
  -- Old password still works during transition

Phase 2: Update secret and restart pods
  kubectl apply secret + kubectl rollout restart

Phase 3: Verify all pods use new password
  kubectl get pods -o wide  # check all pods are new

Phase 4: Revoke old password (if supported)
  -- On PostgreSQL, changing password invalidates the old one immediately
  -- So phases 1-3 must happen quickly
```

**Fix 5: Use Vault or external secret operator**

```yaml
# Using External Secrets Operator
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
spec:
  refreshInterval: 1m
  secretStoreRef:
    name: vault-backend
  target:
    name: db-secret
  data:
    - secretKey: DB_PASSWORD
      remoteRef:
        key: secret/data/production/db
        property: password
```

This automatically syncs secrets from Vault to Kubernetes and can trigger pod restarts.

**Prevention tips:**
- Never revoke the old credential before all pods have the new one
- Use a rolling deployment strategy for zero-downtime rotation
- Mount secrets as files instead of env vars for auto-refresh capability
- Use a secret management tool (Vault, AWS Secrets Manager) with built-in rotation
- Implement connection retry with exponential backoff to survive brief rotation windows
- Monitor for authentication failures as an alert for rotation issues'''),

    ("thinking/debugging", r'''Our blue-green deployment had a race condition during cutover. Some requests went to the blue (old) environment and some to green (new), causing data inconsistency:

```
Timeline:
t=0: Blue is live, Green is warmed up
t=1: Switch DNS/LB from Blue to Green
t=2: Requests still hitting Blue (DNS TTL, connection keep-alive)
t=3: Blue and Green both processing requests
t=4: User creates order on Green (order #1001)
t=5: User refreshes, hits Blue (doesn't see order #1001!)
t=6: User creates same order on Blue (duplicate order #1001!)
```

How do we prevent this split-brain scenario?''', r'''<think>
Blue-green deployment race conditions happen because:
1. DNS propagation is not instant (TTL)
2. Existing HTTP connections stay open (keep-alive)
3. Client-side DNS caching
4. CDN/proxy caching

Both environments are running simultaneously during the cutover window, and they may have different database states or even different databases.

Solutions:
1. Share the same database between blue and green
2. Use connection draining on the old environment
3. Use a load balancer with instant cutover (not DNS-based)
4. Implement request routing at the application level
</think>

Blue-green deployment split-brain occurs because DNS and network infrastructure cannot switch all traffic instantaneously. During the transition window, both environments process requests, leading to data inconsistency.

**Root causes of lingering traffic to old environment:**

1. **DNS TTL**: Clients cache DNS records. Even with TTL=60s, some resolvers ignore TTL and cache longer.
2. **HTTP keep-alive**: Existing TCP connections to Blue remain open and active.
3. **Client-side caching**: Browsers, mobile apps, and CDNs cache the old IP.
4. **In-flight requests**: Requests sent before the switch may arrive after.

**Fix 1: Share the same database (most important)**

```
Blue  -> [Shared Database] <- Green
```

Both environments must read/write the same database. This ensures a user creating an order on Green sees it when their next request hits Blue (or vice versa).

**Fix 2: Use load balancer cutover (not DNS)**

```bash
# AWS ALB: instant target group switching
aws elbv2 modify-listener \
    --listener-arn $LISTENER_ARN \
    --default-actions Type=forward,TargetGroupArn=$GREEN_TARGET_GROUP
```

Load balancer switching is near-instant (no DNS propagation delay). New requests go to Green immediately. However, existing connections to Blue may still be active.

**Fix 3: Connection draining on the old environment**

```yaml
# AWS Target Group: enable deregistration delay
resource "aws_lb_target_group" "blue" {
    deregistration_delay = 300  # 5 minutes to finish in-flight requests
}
```

```nginx
# Nginx: drain connections gracefully
# After cutover, stop accepting NEW connections on Blue
# but let existing connections finish
```

**Fix 4: Application-level request routing**

```python
# Add a version header to responses
@app.after_request
def add_version_header(response):
    response.headers['X-Deploy-Version'] = 'green-v2.1'
    return response

# Client detects version mismatch and forces refresh
if (response.headers['X-Deploy-Version'] !== expectedVersion) {
    window.location.reload(true);  // force fresh DNS lookup
}
```

**Fix 5: Use a deployment stamp/cookie**

```python
@app.before_request
def check_deployment_version():
    client_version = request.cookies.get('deploy_version')
    current_version = os.environ['DEPLOY_VERSION']

    if client_version and client_version != current_version:
        # Client was talking to old version, redirect to current
        response = redirect(request.url)
        response.set_cookie('deploy_version', current_version)
        return response

@app.after_request
def set_deployment_cookie(response):
    response.set_cookie('deploy_version', os.environ['DEPLOY_VERSION'])
    return response
```

**The complete safe cutover procedure:**

```
1. Deploy Green with same database as Blue
2. Warm up Green (health checks pass, caches populated)
3. Switch load balancer to Green (instant, no DNS)
4. Enable connection draining on Blue (300s)
5. Monitor error rates for 5 minutes
6. If errors spike: switch back to Blue (instant rollback)
7. After drain period: shut down Blue
```

**Prevention tips:**
- Always share the database between blue and green environments
- Use load balancer switching instead of DNS switching
- Enable connection draining on the old environment
- Keep the old environment running for 5-10 minutes after cutover
- Monitor error rates and have a one-click rollback ready
- Use feature flags instead of full deployments for risky changes
- Test the cutover process in staging before production'''),

    ("thinking/debugging", r'''Our health check returns 200 but the application is not actually healthy:

```python
@app.route('/health')
def health_check():
    return jsonify({'status': 'ok'}), 200
```

The health check always returns 200 even when:
- The database connection is down
- The Redis cache is unreachable
- The disk is full
- The application is in a degraded state

The load balancer keeps routing traffic to this unhealthy instance because the health check passes.''', r'''<think>
The health check is a static response that doesn't actually check anything. It needs to verify that the application's dependencies are healthy.

But there's a balance: the health check should not be too expensive or slow, and it should distinguish between liveness (is the process alive?) and readiness (can it serve traffic?).
</think>

The health check is a static response that does not verify any actual application health. It would return 200 even if the database is down, disk is full, or the application is in a crash loop. The load balancer uses this to route traffic, so a false-positive health check sends users to a broken instance.

**Fix: Implement meaningful health checks**

```python
import time
from functools import wraps

def health_check_with_timeout(check_func, timeout=5):
    """Run a health check with a timeout."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(check_func)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return False, "Check timed out"

@app.route('/health')
def health_check():
    """Comprehensive health check."""
    checks = {}
    overall_healthy = True

    # Database check
    try:
        db.session.execute(text('SELECT 1'))
        checks['database'] = {'status': 'ok'}
    except Exception as e:
        checks['database'] = {'status': 'error', 'message': str(e)}
        overall_healthy = False

    # Redis check
    try:
        redis_client.ping()
        checks['redis'] = {'status': 'ok'}
    except Exception as e:
        checks['redis'] = {'status': 'error', 'message': str(e)}
        overall_healthy = False

    # Disk space check
    import shutil
    disk = shutil.disk_usage('/')
    free_pct = disk.free / disk.total * 100
    if free_pct < 5:
        checks['disk'] = {'status': 'error', 'message': f'Only {free_pct:.1f}% free'}
        overall_healthy = False
    else:
        checks['disk'] = {'status': 'ok', 'free_percent': f'{free_pct:.1f}%'}

    status_code = 200 if overall_healthy else 503
    return jsonify({
        'status': 'ok' if overall_healthy else 'degraded',
        'checks': checks,
        'timestamp': time.time(),
    }), status_code
```

**Separate liveness from readiness (Kubernetes pattern):**

```python
@app.route('/healthz')  # Liveness: is the process alive?
def liveness():
    """Simple check -- just verify the process can respond."""
    return jsonify({'status': 'ok'}), 200

@app.route('/readyz')  # Readiness: can it serve traffic?
def readiness():
    """Verify all dependencies are available."""
    try:
        db.session.execute(text('SELECT 1'))
        redis_client.ping()
        return jsonify({'status': 'ready'}), 200
    except Exception as e:
        return jsonify({'status': 'not ready', 'error': str(e)}), 503
```

```yaml
# Kubernetes pod spec
livenessProbe:
    httpGet:
        path: /healthz
        port: 8080
    initialDelaySeconds: 10
    periodSeconds: 10
    failureThreshold: 3    # restart pod after 3 failures

readinessProbe:
    httpGet:
        path: /readyz
        port: 8080
    initialDelaySeconds: 5
    periodSeconds: 5
    failureThreshold: 2    # stop sending traffic after 2 failures
```

**Health check best practices:**

```python
# DO: Check actual dependencies
db.session.execute(text('SELECT 1'))

# DO: Set timeouts on checks
# A hung database connection should fail the check, not hang it

# DON'T: Run expensive queries
db.session.execute(text('SELECT COUNT(*) FROM large_table'))  # too slow!

# DON'T: Return 200 for degraded state
# 503 tells the load balancer to stop sending traffic

# DO: Cache health check results briefly
from functools import lru_cache
import time

_health_cache = {'result': None, 'timestamp': 0}

@app.route('/health')
def health():
    now = time.time()
    if now - _health_cache['timestamp'] < 5:  # cache for 5 seconds
        return _health_cache['result']
    result = run_health_checks()
    _health_cache['result'] = result
    _health_cache['timestamp'] = now
    return result
```

**Prevention tips:**
- Health checks must verify actual dependencies, not just return 200
- Separate liveness (is it alive?) from readiness (can it serve?)
- Set timeouts on all health check operations
- Cache health check results to avoid overloading dependencies
- Return 503 for unhealthy state so load balancers route traffic away
- Keep health check endpoints lightweight (no auth, no logging, no complex logic)
- Monitor health check response times as an early warning signal'''),

    ("thinking/debugging", r'''Our database migration ran in production but the rollback failed, leaving the database in an inconsistent state:

```sql
-- Forward migration (ran successfully):
ALTER TABLE users ADD COLUMN phone VARCHAR(20);
UPDATE users SET phone = '' WHERE phone IS NULL;
ALTER TABLE users ALTER COLUMN phone SET NOT NULL;

-- Rollback (FAILED):
ALTER TABLE users DROP COLUMN phone;
-- Error: column "phone" is referenced by foreign key constraint on table "orders"
```

The forward migration added a column that another migration (run afterward) created a foreign key reference to. Now we can't rollback and the application code for the old version doesn't know about the phone column.''', r'''<think>
This is a common migration problem. The forward migration added a column, and a subsequent migration added a foreign key referencing it. Rolling back the first migration requires dropping the column, but the foreign key prevents that.

The issue is that migrations were not designed to be safely rollable, and dependencies between migrations were not considered.

Solutions:
1. Fix the immediate issue: drop the FK constraint first, then drop the column
2. Use a forward-fix approach instead of rollback
3. Design migrations to be backwards-compatible
</think>

The rollback failed because migration dependencies were not considered. A later migration created a foreign key to the `phone` column, making it impossible to drop. This is a common issue with sequential migrations that have implicit dependencies.

**Immediate fix: Manual rollback with correct ordering**

```sql
-- Step 1: Drop the foreign key constraint that references phone
ALTER TABLE orders DROP CONSTRAINT IF EXISTS fk_orders_phone;

-- Step 2: Drop any indexes on the column
DROP INDEX IF EXISTS idx_users_phone;

-- Step 3: Now drop the column
ALTER TABLE users DROP COLUMN phone;
```

**But wait -- should you even rollback?**

In most cases, a forward-fix is safer than a rollback:

```sql
-- Forward fix: make the column nullable (compatible with both old and new code)
ALTER TABLE users ALTER COLUMN phone DROP NOT NULL;
ALTER TABLE users ALTER COLUMN phone SET DEFAULT NULL;
```

This makes the column optional so the old application code can work without it. You can clean up the column in a future migration.

**The safe migration pattern (expand-contract):**

Instead of making breaking changes in one migration, split into three phases:

```
Phase 1: EXPAND (backwards-compatible)
  - Add new column as nullable
  - Deploy new code that writes to both old and new columns
  - Backfill existing data

Phase 2: MIGRATE
  - Deploy code that reads from new column
  - Verify all data is migrated

Phase 3: CONTRACT (cleanup)
  - Drop old column
  - Add NOT NULL constraint
  - Deploy final code
```

**Example safe migration:**

```python
# Migration 1: Add column (safe, backwards-compatible)
def upgrade():
    op.add_column('users', sa.Column('phone', sa.String(20), nullable=True))

def downgrade():
    op.drop_column('users', 'phone')

# Migration 2: Backfill data (safe, no schema change)
def upgrade():
    op.execute("UPDATE users SET phone = '' WHERE phone IS NULL")

def downgrade():
    pass  # data-only migration, no structural rollback needed

# Migration 3: Add NOT NULL (only after code handles the column)
def upgrade():
    op.alter_column('users', 'phone', nullable=False, server_default='')

def downgrade():
    op.alter_column('users', 'phone', nullable=True, server_default=None)
```

**Testing migration rollbacks:**

```bash
# Test forward + backward in CI
alembic upgrade head
alembic downgrade -1  # test rollback of latest migration
alembic upgrade head   # verify re-apply works
```

```python
# In CI pipeline:
def test_migrations_are_reversible():
    """Verify each migration can be rolled back."""
    alembic_upgrade('head')
    for rev in get_all_revisions():
        alembic_downgrade(f'-1')
        alembic_upgrade(f'+1')
```

**Prevention tips:**
- Always test rollback in CI before deploying migrations
- Use the expand-contract pattern for breaking changes
- Never add NOT NULL to an existing column in a single migration
- Document dependencies between migrations
- Keep migrations small and focused (one change per migration)
- Use `IF EXISTS` in rollback DDL to make rollbacks idempotent
- Prefer forward-fixes over rollbacks in production
- Take a database backup before running migrations'''),
]
