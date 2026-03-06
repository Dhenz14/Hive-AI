"""Phase 2E: Advanced Reasoning — Causal & Counterfactual Analysis (Part 7/8)"""

PAIRS = [
    (
        "thinking/causal-kubernetes-pod-crashloop",
        "Our Kubernetes pod keeps going into CrashLoopBackOff. It starts, runs for about 30 seconds, then crashes. The same Docker image works fine when run locally with `docker run`. Logs show the application starts successfully but then exits with code 137. What's happening?",
        r'''<think>
Exit code 137 — this is a very specific and telling clue. Let me trace the causal chain.

**Exit code 137 = 128 + 9 = SIGKILL (signal 9)**
The process was killed by the kernel, not by itself. It didn't crash — it was TERMINATED.

**What sends SIGKILL in Kubernetes?**

1. **OOMKill (Out of Memory)**: The container exceeded its memory limit, and the kernel killed it.
2. **Liveness probe failure**: Kubernetes detected the pod as unhealthy and killed it.
3. **Resource limits exceeded**: cgroup memory limit enforcement.

**The timing matters: 30 seconds after start.**

If it's OOMKill:
- Memory usage grows during startup (loading models, caches, initializing)
- After 30 seconds, it exceeds the container's memory limit
- Kernel sends SIGKILL
- Works locally because Docker has no memory limit by default (or a higher one)

If it's liveness probe:
- Default liveness probe initial delay might be 30 seconds
- Application might not be ready to respond to health checks
- Kubernetes kills it, restarts, repeat → CrashLoopBackOff

**How to differentiate:**
- `kubectl describe pod <name>` will show: `Last State: Terminated - Reason: OOMKilled`
- Or: `Last State: Terminated - Reason: Error` + liveness probe failure events

**Most likely cause given the clues:**
- Exit code 137 → SIGKILL
- Works locally (no memory limits) → fails in K8s (memory limits set)
- 30 seconds → memory grows during initialization
- Verdict: **OOMKill** — memory limit too low

**Counterfactual:**
- If memory limit was higher → would it survive startup? Check.
- If there was no memory limit → would it run indefinitely? Check.
- If the Docker run locally had the same memory limit → would it crash? Yes.
</think>

Exit code 137 = **SIGKILL** (128 + 9). The container isn't crashing — Kubernetes is KILLING it. Here's the diagnosis:

## Step 1: Identify the Kill Reason

```bash
# This tells you exactly why
kubectl describe pod <pod-name> | grep -A 5 "Last State"

# You'll see one of:
#   Last State: Terminated
#   Reason:     OOMKilled     ← Memory limit exceeded
#   Exit Code:  137
#
# OR:
#   Last State: Terminated
#   Reason:     Error
#   Exit Code:  137
#   (plus events showing "Liveness probe failed")
```

## Most Likely: OOMKill (90% Confident)

```yaml
# Your pod spec probably has:
resources:
  limits:
    memory: "256Mi"   # Container can use max 256MB

# But your app needs more during startup:
# - Loading libraries: 100MB
# - JIT compilation / warmup: 50MB
# - Application data structures: 150MB
# - Total: 300MB > 256MB limit → OOMKilled at 30 seconds
```

**Why it works locally:** `docker run` has NO memory limit by default. Your app uses 400MB freely. In Kubernetes, the memory limit is enforced.

```bash
# Verify: check actual memory usage
kubectl top pod <pod-name>
# If it shows memory climbing to the limit before crash → OOMKill confirmed

# Also check node events
kubectl get events --field-selector involvedObject.name=<pod-name>
# Look for: "Container was OOMKilled"
```

### Fix: Increase Memory Limit

```yaml
# Increase limits based on actual usage (add 20-30% buffer)
resources:
  requests:
    memory: "256Mi"   # Scheduler guarantee
    cpu: "100m"
  limits:
    memory: "512Mi"   # Actual ceiling — increase this
    cpu: "500m"
```

### Fix: Reduce Application Memory Usage

```python
# If you can't increase limits, optimize your app:

# 1. Lazy loading (don't load everything at startup)
# ❌ Load all data at startup
data = load_entire_dataset()  # 200MB

# ✅ Load on demand
@lru_cache(maxsize=1000)
def get_item(item_id):
    return db.fetch_item(item_id)

# 2. For Python: reduce worker memory
# gunicorn with --preload shares memory across workers
CMD ["gunicorn", "--preload", "--workers", "2", "app:app"]
```

## Second Possibility: Liveness Probe Failure

```yaml
# Your liveness probe might have too short an initial delay:
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10   # ← Too short! App needs 30s to start
  periodSeconds: 5
  failureThreshold: 3
  # After 10s + (3 × 5s) = 25s, Kubernetes kills the pod
  # because it hasn't passed health checks yet
```

### Fix: Use Startup Probe (Kubernetes 1.18+)

```yaml
# Startup probe: gives the app time to start
# Liveness probe: checks health AFTER startup
startupProbe:
  httpGet:
    path: /health
    port: 8000
  failureThreshold: 30
  periodSeconds: 2
  # Allows up to 60 seconds for startup

livenessProbe:
  httpGet:
    path: /health
    port: 8000
  periodSeconds: 10
  failureThreshold: 3
  # Only starts checking AFTER startupProbe passes
```

## Diagnostic Summary

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Reason: OOMKilled` | Memory limit too low | Increase limits or optimize app |
| `Liveness probe failed` events | App not ready when probe starts | Add startupProbe, increase initialDelay |
| Exit code 137, no other info | Check `dmesg` on the node for kernel OOM messages | Same as OOMKill |

The causal chain: works locally (no memory limits) → crashes in K8s (memory limits enforced) → exit 137 (kernel SIGKILL) → CrashLoopBackOff (K8s keeps restarting, exponential backoff).'''
    ),
    (
        "thinking/causal-ssl-certificate-expiry-outage",
        "Our production site went down at 3 AM with SSL certificate errors. All browsers show 'Your connection is not private.' We use Let's Encrypt with auto-renewal. The certificate expired even though renewal was supposed to be automatic. How did this happen and how do we prevent it?",
        r'''<think>
SSL certificate expired despite auto-renewal. Let me trace the possible causal chains.

**How Let's Encrypt auto-renewal works:**
1. Certbot (or similar) runs on a cron schedule (usually daily)
2. If certificate expires within 30 days, it attempts renewal
3. Renewal requires an ACME challenge (HTTP-01 or DNS-01)
4. Certbot writes the new certificate files
5. Web server (nginx/Apache) needs to reload to use the new cert

**Possible failure points:**

1. **Certbot cron stopped running**
   - Server was rebuilt, cron wasn't set up
   - Crontab was overwritten during deployment
   - Cron daemon itself crashed

2. **ACME challenge failed**
   - HTTP-01 challenge: needs port 80 accessible. If a firewall rule changed, or a load balancer doesn't pass through to the right server, the challenge fails.
   - DNS-01 challenge: API credentials for DNS provider expired or changed.
   - Challenge path blocked by nginx config (location /.well-known/acme-challenge/ not configured)

3. **Certificate renewed but web server didn't reload**
   - Certbot renewed the cert files on disk
   - But nginx is still serving the old cert from memory
   - Needs `nginx -s reload` after renewal (certbot --deploy-hook)

4. **Infrastructure changed**
   - Moved behind a CDN (CloudFront, Cloudflare) — certificate is now on the CDN, not the origin
   - Moved to a new server, old certbot configs not migrated
   - Load balancer handles SSL now, certbot still runs on the wrong server

5. **Certificate for wrong domain**
   - Added www.example.com but cert only covers example.com
   - SAN (Subject Alternative Name) doesn't include all domains

**Most likely causes for "it was working and then stopped":**
1. Infrastructure change broke the ACME challenge path
2. Certbot ran but nginx didn't reload
3. Cron was lost during server provisioning

Let me provide both immediate fix and prevention.
</think>

Auto-renewal failures have a few common root causes. Here's the diagnostic and permanent fix:

## Immediate Fix (Right Now)

```bash
# 1. Manually renew the certificate
sudo certbot renew --force-renewal

# 2. If that fails, check why:
sudo certbot renew --dry-run --verbose
# This will show the exact error

# 3. Reload the web server
sudo nginx -s reload
# or
sudo systemctl reload nginx

# 4. Verify it's working
echo | openssl s_client -connect yourdomain.com:443 2>/dev/null | openssl x509 -noout -dates
# Should show: notAfter=<date 90 days from now>
```

## Root Cause Diagnosis

```bash
# Check 1: Is certbot's cron/timer active?
sudo systemctl status certbot.timer    # systemd timer
# or
sudo crontab -l | grep certbot         # cron job
# If missing → cron was lost during deployment/rebuild

# Check 2: Can the ACME challenge reach your server?
curl -I http://yourdomain.com/.well-known/acme-challenge/test
# If 404 or blocked → nginx isn't serving the challenge directory

# Check 3: Did certbot try and fail?
sudo cat /var/log/letsencrypt/letsencrypt.log
# Look for errors around the expected renewal date

# Check 4: Was the cert renewed but nginx not reloaded?
sudo ls -la /etc/letsencrypt/live/yourdomain.com/
# Check file dates — if recent but site shows old cert → reload issue

# Check 5: Is port 80 accessible? (needed for HTTP-01 challenge)
curl -I http://yourdomain.com/
# If blocked → firewall or load balancer change broke the challenge
```

## Most Common Root Causes and Fixes

### Cause 1: Nginx Didn't Reload After Renewal

```bash
# ❌ Certbot renewed the cert files, but nginx is serving the old cert from memory

# ✅ FIX: Add a deploy hook
sudo certbot renew --deploy-hook "systemctl reload nginx"

# Make it permanent in certbot's config:
# /etc/letsencrypt/renewal/yourdomain.com.conf
[renewalparams]
deploy_hook = systemctl reload nginx
```

### Cause 2: ACME Challenge Path Blocked

```nginx
# ❌ nginx config redirects ALL HTTP to HTTPS (including challenge)
server {
    listen 80;
    return 301 https://$host$request_uri;  # Blocks .well-known too!
}

# ✅ FIX: Allow ACME challenges through
server {
    listen 80;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;  # Let certbot serve challenge files
    }

    location / {
        return 301 https://$host$request_uri;
    }
}
```

### Cause 3: Cron Lost During Server Rebuild

```bash
# ✅ FIX: Use systemd timer (survives rebuilds better than crontab)
# /etc/systemd/system/certbot-renewal.timer
[Unit]
Description=Certbot renewal timer

[Timer]
OnCalendar=*-*-* 02:00:00
RandomizedDelaySec=3600

[Install]
WantedBy=timers.target

# /etc/systemd/system/certbot-renewal.service
[Unit]
Description=Certbot renewal

[Service]
Type=oneshot
ExecStart=/usr/bin/certbot renew --deploy-hook "systemctl reload nginx"

# Enable
sudo systemctl enable certbot-renewal.timer
sudo systemctl start certbot-renewal.timer
```

## Prevention: Never Let This Happen Again

```bash
#!/bin/bash
# /opt/scripts/check_ssl_expiry.sh
# Run daily — alerts if cert expires within 14 days

DOMAIN="yourdomain.com"
DAYS_WARNING=14

expiry_date=$(echo | openssl s_client -connect $DOMAIN:443 2>/dev/null \
  | openssl x509 -noout -enddate | cut -d= -f2)
expiry_epoch=$(date -d "$expiry_date" +%s)
now_epoch=$(date +%s)
days_left=$(( (expiry_epoch - now_epoch) / 86400 ))

if [ $days_left -lt $DAYS_WARNING ]; then
    # Send alert via Slack, PagerDuty, email, etc.
    curl -X POST "$SLACK_WEBHOOK" \
      -d "{\"text\": \"⚠️ SSL cert for $DOMAIN expires in $days_left days!\"}"
fi

echo "SSL cert for $DOMAIN: $days_left days remaining"
```

```bash
# Add to cron (separate from certbot — monitors certbot's work)
0 8 * * * /opt/scripts/check_ssl_expiry.sh
```

## The Complete Prevention Stack

| Layer | What it does |
|-------|-------------|
| Certbot timer | Auto-renews cert 30 days before expiry |
| Deploy hook | Reloads nginx after renewal |
| SSL monitor | Alerts if cert is <14 days from expiry |
| Uptime monitor | Detects the outage immediately (not at 3 AM) |

The causal chain that caused the outage: something broke the renewal process (challenge blocked, cron lost, or reload missing) → cert expired → browsers reject HTTPS → site is down. The fix is defense in depth: auto-renew + verify + alert.'''
    ),
    (
        "thinking/causal-git-merge-conflict-patterns",
        "We keep having the same merge conflicts in the same files. Particularly our routes file, our database migration files, and a shared constants file. Two developers can't work on features simultaneously without conflicts. What's causing this pattern and how do we fix it?",
        r'''<think>
Recurring merge conflicts in the same files. Let me analyze the root causes.

**Why do these specific files conflict?**

1. **Routes file**: Every new feature adds routes. Two features = two devs adding routes to the same file at the same position (usually the end). When both merge, the end-of-file additions conflict.

Root cause: Routes are defined in ONE centralized file. All features modify the same file.

Fix: Distribute route definitions to feature modules. Auto-discover routes.

2. **Migration files**: Django/Alembic migrations have a linear dependency chain. Two devs create migrations independently — both depend on the same "latest" migration. When merged, they're siblings, not sequential.

Root cause: Migration dependency chain is centralized.

Fix: After merging, create a merge migration. Or use a convention to avoid simultaneous migrations.

3. **Shared constants file**: Every feature that needs a new constant adds it here. Same end-of-file conflict pattern.

Root cause: Constants are centralized in one file instead of living with their feature.

**The meta-pattern:** All three are caused by CENTRALIZATION — multiple features modifying the same file because all related things are gathered in one place.

**The fix:** DISTRIBUTE the concerns. Each feature should own its own routes, its own constants, and coordinate on migrations.
</think>

The root cause is **centralization** — all three files are bottlenecks where every feature must add their changes to the same location.

## The Pattern: Centralization → Conflicts

```
Every new feature must modify these files:

routes.py:          Feature A adds routes at line 150
                    Feature B adds routes at line 150 → CONFLICT

migrations/:        Feature A creates 0045_add_field.py (depends on 0044)
                    Feature B creates 0045_add_table.py (also depends on 0044) → CONFLICT

constants.py:       Feature A adds FEATURE_A_LIMIT = 100 at the end
                    Feature B adds FEATURE_B_TIMEOUT = 30 at the end → CONFLICT
```

## Fix 1: Distributed Routes (Eliminates Route Conflicts)

```python
# ❌ BEFORE: One routes.py file (conflict magnet)
# routes.py — everyone edits this
urlpatterns = [
    path('users/', views.users),
    path('orders/', views.orders),
    # ... 100 more routes
    # Feature A adds here
    # Feature B adds here → CONFLICT
]

# ✅ AFTER: Each feature defines its own routes
# users/urls.py
urlpatterns = [
    path('', views.list_users),
    path('<int:id>/', views.get_user),
]

# orders/urls.py
urlpatterns = [
    path('', views.list_orders),
    path('<int:id>/', views.get_order),
]

# main urls.py — rarely changes
urlpatterns = [
    path('api/users/', include('users.urls')),
    path('api/orders/', include('orders.urls')),
    # New features add ONE line here (or use auto-discovery)
]
```

## Fix 2: Migration Conflict Protocol (Eliminates Migration Conflicts)

```bash
# The problem: two devs create migrations from the same base

# Developer A (feature branch):
# migrations/0045_add_payment_field.py (depends on 0044)

# Developer B (feature branch):
# migrations/0045_add_shipping_table.py (depends on 0044)

# When both merge: two migrations numbered 0045, both depend on 0044 → CONFLICT
```

```bash
# FIX: Create migrations AFTER merging to main

# Workflow:
# 1. Developer makes model changes on feature branch
# 2. DON'T create migration on feature branch
# 3. Merge feature to main
# 4. On main: python manage.py makemigrations
# 5. Commit the migration on main

# If you MUST create migrations on branches:
# After merging both branches, run:
python manage.py makemigrations --merge
# This creates a merge migration that resolves the dependency conflict
```

```python
# Alternative: use squashmigrations periodically
# Reduces the chain length and conflict surface
python manage.py squashmigrations myapp 0001 0045
```

## Fix 3: Distributed Constants (Eliminates Constants Conflicts)

```python
# ❌ BEFORE: One constants.py (conflict magnet)
# constants.py — 200 constants, everyone adds here
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
DEFAULT_PAGE_SIZE = 20
PAYMENT_TIMEOUT = 30
SHIPPING_RATE = 5.99
# Feature A adds here
# Feature B adds here → CONFLICT

# ✅ AFTER: Constants live with their feature
# payments/constants.py
PAYMENT_TIMEOUT = 30
MAX_RETRY_ATTEMPTS = 3

# shipping/constants.py
SHIPPING_RATE = 5.99
FREE_SHIPPING_THRESHOLD = 50.00

# users/constants.py
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
DEFAULT_AVATAR_URL = "/static/default-avatar.png"

# If you need truly shared constants (rare):
# core/constants.py (only for cross-cutting concerns)
DEFAULT_PAGE_SIZE = 20
DATE_FORMAT = "%Y-%m-%d"
```

## The General Principle

```
CENTRALIZED (conflict-prone):
  All routes in one file
  All constants in one file
  All migrations in one directory with linear deps

DISTRIBUTED (conflict-free):
  Routes in each feature module
  Constants in each feature module
  Migrations coordinated via merge protocol

Rule: if two developers regularly modify the same file
for UNRELATED features, the file needs to be split.
```

## Measuring Success

```bash
# Track conflict frequency before and after
git log --merges --grep="conflict" --since="3 months ago" | wc -l

# Or track which files cause the most merge conflicts
git log --all --pretty=format: --name-only --diff-filter=U | sort | uniq -c | sort -rn | head
# The top files in this list are your conflict hotspots
```

The meta-insight: merge conflicts aren't a Git problem — they're an architecture problem. Files that everyone edits are architectural bottlenecks. Distribute ownership and conflicts disappear.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
