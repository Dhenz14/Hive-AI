"""Phase 2E: Advanced Reasoning — Causal & Counterfactual Analysis (Part 4/5)
Systematic hypothesis elimination with evidence:
API latency regression, test suite getting slower, frontend bundle bloat,
authentication failures spike, data pipeline stalls."""

PAIRS = [
    (
        "thinking/causal-api-latency-regression",
        "Our API p95 latency jumped from 200ms to 800ms after last week's deploy. We deployed 15 PRs that week. How do I figure out which one caused it?",
        r'''<think>
15 PRs deployed, latency 4x'd. Need to find the culprit. Let me think systematically.

First: is it definitely one of the 15 PRs?
- Latency correlated with deploy timing → very likely (90%)
- Could be external: DB growing, traffic increase, infrastructure change
- Quick check: did traffic volume change? Did DB grow significantly? Any infra changes?
- If no → it's in one of the 15 PRs

Strategy 1: Binary search through deploys
- If I can deploy arbitrary commits, I can bisect
- Deploy commit from middle of the 15 PRs → check latency
- If fast: problem is in the later half
- If slow: problem is in the earlier half
- 4 iterations to find the exact PR out of 15 (log2(15) ≈ 4)

Strategy 2: Analyze the PRs by type
- Which PRs COULD affect latency?
  - New database queries: likely candidate
  - New external API calls: likely candidate
  - New middleware or request processing: likely
  - UI changes, test changes, docs: very unlikely
- Focus investigation on the 3-5 PRs that touch request processing

Strategy 3: Profile the slow requests
- Where is the time being spent?
- Add timing breakdown: middleware → route handler → DB queries → external calls → response
- The component that got 600ms slower is where the bug is

Strategy 4: Check query performance
- SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC
- If a specific query went from 5ms to 300ms → find which PR introduced it
- Common cause: N+1 query, missing index on new column, full table scan

Let me also think about the SHAPE of the latency increase:
- 200ms → 800ms = +600ms for every request?
  - If yes: something added to every request (middleware, auth, logging)
- 200ms → 800ms = p95 but p50 is fine?
  - If yes: specific code path is slow (certain endpoints, certain data conditions)

The shape tells us WHERE to look.

Investigation order:
1. Check p50 vs p95 vs p99 (all requests or specific subset?)
2. Check per-endpoint latency (which endpoints got slower?)
3. Profile the slow endpoint(s)
4. Cross-reference with the 15 PRs
5. If still unclear: git bisect
</think>

15 PRs is a manageable search space. Here's how to find the culprit efficiently.

**Step 1 — Narrow the scope (5 minutes):**

```sql
-- Is it ALL requests or specific endpoints?
-- Check per-endpoint latency (if you have metrics)
SELECT
    request_path,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY duration_ms) AS p50,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95,
    COUNT(*) AS request_count
FROM request_logs
WHERE timestamp > now() - interval '24 hours'
GROUP BY request_path
ORDER BY p95 DESC
LIMIT 20;

-- Compare to last week:
-- If only /api/orders is slow → the bug is in order-related code
-- If ALL endpoints are slow → the bug is in middleware/auth/DB
```

**Step 2 — Profile the slow endpoint (10 minutes):**

```python
# Add timing middleware (temporary, for diagnosis)
import time

@app.middleware("http")
async def timing_middleware(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    response.headers["X-Response-Time"] = f"{duration:.3f}"

    if duration > 0.5:  # Log slow requests
        logger.warning("slow_request",
            path=request.url.path,
            duration_ms=int(duration * 1000),
            method=request.method,
        )
    return response
```

```sql
-- Check database: which queries got slower?
SELECT query, calls,
       mean_exec_time AS avg_ms,
       total_exec_time / 1000 AS total_sec
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Look for:
-- 1. A query that used to take 5ms now takes 300ms (new N+1 or missing index)
-- 2. A NEW query that didn't exist before (from the 15 PRs)
```

**Step 3 — Filter the 15 PRs to likely suspects:**

```bash
# Which PRs touch request handling code?
for pr in $(git log --oneline HEAD~15..HEAD --format="%h"); do
    echo "=== $pr ==="
    git diff-tree --no-commit-id --name-only -r $pr | grep -E '\.(py|sql)$'
done

# Focus on PRs that changed:
# - models.py / queries (DB changes)
# - views.py / routes (endpoint logic)
# - middleware.py (affects all requests)
# - serializers.py (response building)
# Ignore: tests, docs, frontend-only, config
```

**Step 4 — If still unclear, git bisect:**

```bash
# Automated bisect — finds the exact commit
git bisect start
git bisect bad HEAD                    # Current (slow)
git bisect good HEAD~15                # Before the 15 PRs (fast)

# For each step, run a latency test:
git bisect run ./scripts/check_latency.sh

# check_latency.sh:
#!/bin/bash
# Deploy this commit to staging, hit it with requests, check p95
docker compose up -d --build
sleep 10
p95=$(curl -s "http://localhost:8000/api/orders" -w "%{time_total}" -o /dev/null)
if (( $(echo "$p95 > 0.5" | bc -l) )); then
    exit 1  # Bad commit (slow)
else
    exit 0  # Good commit (fast)
fi

# After ~4 iterations: "abc1234 is the first bad commit"
```

**Common culprits (check these first):**

```python
# Culprit 1: N+1 query introduced by eager→lazy loading change
# PR changed: Order.objects.select_related('items').all()
# To:         Order.objects.all()  # Lazy loads items in a loop

# Culprit 2: New middleware that runs on EVERY request
# PR added: @app.middleware that calls an external service

# Culprit 3: Missing index on a new column
# PR added: .filter(new_column=value) without CREATE INDEX

# Culprit 4: Serializer now includes a relationship
# PR changed: OrderSerializer to include nested items
# Without select_related → N+1 in serialization
```

**Prevention — catch latency regressions in CI:**

```yaml
# Run a latency benchmark in CI for every PR
- name: Latency benchmark
  run: |
    docker compose up -d
    sleep 10
    # Hit endpoints and measure p95
    ab -n 100 -c 10 http://localhost:8000/api/orders/ > bench.txt
    p95=$(grep "95%" bench.txt | awk '{print $NF}')
    if [ "$p95" -gt "500" ]; then
      echo "FAIL: p95 latency ${p95}ms exceeds 500ms threshold"
      exit 1
    fi
```

Start with per-endpoint latency breakdown — it immediately tells you whether it's one endpoint or all of them, which cuts your search space from 15 PRs to 2-3.'''
    ),
    (
        "thinking/causal-frontend-bundle-bloat",
        "Our React app's bundle size grew from 200KB to 1.2MB over the past 3 months. Page load time went from 1s to 4s. How do we figure out what happened and fix it?",
        r'''<think>
Bundle grew 6x in 3 months. Let me think about what causes JavaScript bundle bloat.

Likely causes:
1. Large dependency added (e.g., moment.js = 300KB, lodash full = 70KB)
2. Images/assets accidentally bundled
3. No code splitting — entire app in one file
4. Duplicate dependencies (different versions of same library)
5. Source maps included in production build
6. CSS-in-JS library bloat (styled-components with many variants)
7. No tree shaking (importing entire libraries instead of specific functions)

Diagnostic approach:
1. Analyze what's IN the bundle (bundle analyzer)
2. Find the largest chunks
3. Determine when each was added (git blame + build history)
4. Apply targeted fixes

The most common cause of sudden growth: someone added a large dependency.
200KB → 1.2MB = +1MB added. That's likely 2-3 large libraries.

Counterfactual: "What if we hadn't added any new dependencies?"
- If bundle would still be ~200KB → it's a dependency problem
- If bundle grew even without new deps → it's a code/config problem

Let me outline a systematic investigation.
</think>

1.2MB JavaScript bundle = users wait 4 seconds staring at a blank screen. Here's how to find and fix the bloat.

**Step 1 — See what's in the bundle (2 minutes):**

```bash
# Install the bundle analyzer
npm install --save-dev webpack-bundle-analyzer

# For Create React App:
npx react-scripts build -- --stats
npx webpack-bundle-analyzer build/bundle-stats.json

# For Vite:
npx vite-bundle-visualizer

# For Next.js:
ANALYZE=true next build
```

```
# The analyzer shows a treemap like:
# ┌──────────────────────────────────────────┐
# │ node_modules (900KB)                      │
# │ ┌────────────┐┌─────────┐┌──────────────┐│
# │ │ moment.js  ││ lodash  ││ chart.js     ││
# │ │ 300KB      ││ 70KB    ││ 200KB        ││
# │ └────────────┘└─────────┘└──────────────┘│
# │ src (300KB)                               │
# │ ┌──────────────────────────────────────┐  │
# │ │ All your code in one chunk           │  │
# │ └──────────────────────────────────────┘  │
# └──────────────────────────────────────────┘
# Now you can SEE what's eating space
```

**Step 2 — Find the biggest offenders:**

```bash
# List the heaviest dependencies
npx cost-of-modules --less

# Output:
# moment          300.2 kB  ← REPLACE with dayjs (2KB)
# chart.js        196.8 kB  ← only needed on dashboard page
# lodash          71.3 kB   ← import specific functions instead
# @mui/material   45.2 kB   ← check tree shaking
# aws-sdk         128.4 kB  ← should this be in frontend?!
```

**Step 3 — Apply targeted fixes:**

```javascript
// Fix 1: Replace heavy libraries with lighter alternatives
// BEFORE: moment.js (300KB)
import moment from 'moment';
moment(date).format('YYYY-MM-DD');

// AFTER: dayjs (2KB, same API)
import dayjs from 'dayjs';
dayjs(date).format('YYYY-MM-DD');

// Fix 2: Import only what you use (tree shaking)
// BEFORE: imports entire lodash (70KB)
import _ from 'lodash';
_.debounce(fn, 300);

// AFTER: import specific function (1KB)
import debounce from 'lodash/debounce';
debounce(fn, 300);

// Fix 3: Remove accidental server-side dependencies
// aws-sdk in frontend? That's a mistake.
// Check: is this actually used in browser code?
```

```javascript
// Fix 4: Code splitting — load heavy components only when needed
// BEFORE: chart.js loaded on every page
import { Chart } from 'chart.js';

// AFTER: lazy load — only downloaded when user visits dashboard
import { lazy, Suspense } from 'react';
const Dashboard = lazy(() => import('./pages/Dashboard'));
// Dashboard page (with chart.js) is a separate chunk
// Only downloaded when user navigates there

function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/" element={<Home />} />           {/* Small chunk */}
        <Route path="/dashboard" element={<Dashboard />} /> {/* Separate chunk */}
      </Routes>
    </Suspense>
  );
}
```

```javascript
// Fix 5: Dynamic import for rarely-used features
// BEFORE: PDF export loaded for everyone
import { generatePDF } from './utils/pdf-export'; // +150KB

// AFTER: load only when user clicks "Export PDF"
const handleExport = async () => {
  const { generatePDF } = await import('./utils/pdf-export');
  generatePDF(data);
};
```

**Step 4 — Prevent future bloat:**

```json
// package.json — add bundle size budget
{
  "bundlesize": [
    {
      "path": "build/static/js/*.js",
      "maxSize": "250 kB",
      "compression": "gzip"
    }
  ]
}
```

```yaml
# CI check — fail build if bundle exceeds budget
- name: Check bundle size
  run: |
    npm run build
    BUNDLE_SIZE=$(du -sk build/static/js/ | awk '{print $1}')
    if [ "$BUNDLE_SIZE" -gt "300" ]; then
      echo "FAIL: Bundle size ${BUNDLE_SIZE}KB exceeds 300KB limit"
      echo "Run 'npx webpack-bundle-analyzer' to investigate"
      exit 1
    fi
```

**Expected results:**

```
Before:
  moment.js:    300KB → dayjs:    2KB     (saved 298KB)
  lodash full:   70KB → lodash/fn: 5KB    (saved 65KB)
  chart.js:     200KB → lazy loaded: 0KB  (saved 200KB for non-dashboard pages)
  aws-sdk:      128KB → removed:   0KB    (saved 128KB)
  No splitting:  all in one file → split into 4 chunks

After: ~250KB initial load (from 1.2MB)
Page load: ~1.2s (from 4s)
```

The investigation is always: analyze → identify biggest chunks → replace or lazy-load them → add a budget to prevent regrowth.'''
    ),
    (
        "thinking/causal-auth-failures-spike",
        "We're seeing a spike in authentication failures — 10x the normal rate. We haven't changed any auth code. What's happening?",
        r'''<think>
Auth failure spike without code changes. Let me build hypotheses systematically.

Key fact: 10x normal rate, no auth code changes.

Hypothesis 1: Credential stuffing / brute force attack
- Attackers using leaked credentials from another breach
- Trying email/password combinations against our login endpoint
- Would show: many different usernames, mostly failed, from many IPs (or few IPs with rotation)
- Test: check IP distribution of failures, username patterns
- Likelihood: HIGH — most common cause of auth failure spikes

Hypothesis 2: Token/session expiration change
- Infrastructure change: Redis restarted, clearing all sessions
- Users' tokens all expired at once → all re-auth attempts
- Some fail because cookies are stale or tokens can't refresh
- Test: did Redis/session store restart? Check token expiry timestamps
- Likelihood: MEDIUM

Hypothesis 3: Client-side change (mobile app update, frontend deploy)
- New version of the app has a bug in auth flow
- Sending wrong credentials, missing headers, incorrect token format
- Test: check if failures correlate with specific app version or user-agent
- Likelihood: MEDIUM

Hypothesis 4: Third-party auth provider issue
- If using OAuth (Google, GitHub login), their service might be degraded
- Token verification calls to the provider are failing
- Test: check third-party status pages, check if failures are all OAuth
- Likelihood: MEDIUM (if using OAuth)

Hypothesis 5: Certificate / TLS change
- SSL certificate renewed but misconfigured
- API clients can't establish secure connection
- Or: certificate pinning in mobile app rejecting new cert
- Test: check if failures are connection-level or application-level
- Likelihood: LOW-MEDIUM

Hypothesis 6: Clock skew
- Server time drifted
- JWT tokens being rejected because exp/iat checks fail
- Would affect ALL tokens, not just some
- Test: check server time, check NTP sync
- Likelihood: LOW

Hypothesis 7: Database issue
- Auth table corrupted, password hashes unreadable
- Or: DB connection pool exhausted, auth queries failing
- Test: can you manually authenticate? Check DB health
- Likelihood: LOW

Investigation priority:
1. Examine the failures — are they the same error or different errors?
2. IP analysis — few IPs (attack) or many IPs (legitimate users)?
3. Username analysis — real users or random strings (attack)?
4. Timing — sudden or gradual (deploy vs attack)?
5. Error type — wrong password vs invalid token vs connection error?
</think>

Auth failure spikes without code changes usually fall into two categories: either you're under attack, or something broke for legitimate users. Here's how to tell.

**Step 1 — Categorize the failures (5 minutes):**

```sql
-- What TYPE of auth failure?
SELECT
    error_type,
    COUNT(*) AS count,
    COUNT(DISTINCT username) AS unique_users,
    COUNT(DISTINCT ip_address) AS unique_ips
FROM auth_logs
WHERE status = 'failed'
  AND timestamp > now() - interval '1 hour'
GROUP BY error_type
ORDER BY count DESC;

-- Results tell you:
-- "invalid_password" from 1000 unique usernames, 5 IPs → credential stuffing attack
-- "invalid_token" from 500 unique users, 500 IPs → token/session issue
-- "connection_error" from all users → infrastructure issue
```

**If it's an attack (most common cause):**

```sql
-- Credential stuffing signature:
-- Many different usernames, high failure rate, few source IPs
SELECT
    ip_address,
    COUNT(*) AS attempts,
    COUNT(DISTINCT username) AS unique_usernames,
    COUNT(CASE WHEN status = 'success' THEN 1 END) AS successes,
    MIN(timestamp) AS first_attempt,
    MAX(timestamp) AS last_attempt
FROM auth_logs
WHERE timestamp > now() - interval '1 hour'
GROUP BY ip_address
HAVING COUNT(*) > 50
ORDER BY attempts DESC;

-- If you see:
-- 185.234.x.x | 5000 attempts | 4800 unique usernames | 3 successes
-- → Credential stuffing attack. Those 3 successes = compromised accounts!
```

```python
# Immediate response to attack:
# 1. Block attacking IPs
for ip in attacking_ips:
    r.setex(f"blocked_ip:{ip}", 86400, "1")

# 2. Force password reset for any accounts that had successful logins from attacking IPs
compromised_users = db.execute("""
    SELECT DISTINCT user_id FROM auth_logs
    WHERE ip_address IN :attacking_ips AND status = 'success'
""", {"attacking_ips": tuple(attacking_ips)})
for user in compromised_users:
    force_password_reset(user.user_id)
    invalidate_all_sessions(user.user_id)

# 3. Add rate limiting to login endpoint
@app.post("/auth/login")
@limiter.limit("5/minute", key_func=lambda: request.client.host)
@limiter.limit("10/minute", key_func=lambda: request.json.get("email", ""))
def login():
    ...
```

**If it's a session/token issue (legitimate users can't auth):**

```python
# Check 1: Did the session store restart?
# Redis: DBSIZE shows 0 after restart (all sessions gone)
import redis
r = redis.Redis()
print(r.dbsize())  # If 0 or very low → sessions were flushed

# Check 2: Server clock skew (JWT tokens rejected)
import subprocess
ntp_output = subprocess.check_output(["timedatectl", "status"]).decode()
print(ntp_output)
# If "System clock synchronized: no" → clock drifted → JWTs rejected

# Check 3: Token signing key changed
# Did someone rotate JWT_SECRET without a graceful migration?
# Old tokens signed with old key → verification fails
```

**If it's a client-side issue:**

```sql
-- Check by client version / user-agent
SELECT
    user_agent,
    COUNT(*) AS failures,
    COUNT(CASE WHEN status = 'success' THEN 1 END) AS successes
FROM auth_logs
WHERE timestamp > now() - interval '1 hour'
GROUP BY user_agent
ORDER BY failures DESC;

-- If you see:
-- "MyApp/2.1.0 (iOS)" | 5000 failures | 0 successes
-- → New mobile app version has a bug
-- "MyApp/2.0.0 (iOS)" | 50 failures | 4500 successes
-- → Old version works fine
```

**Decision tree:**

```
Auth failures spike
├── Mostly wrong passwords + few IPs → Credential stuffing attack
│   → Block IPs, rate limit, check for compromised accounts
├── Mostly invalid tokens + many IPs → Session/token infrastructure issue
│   → Check Redis, check clock sync, check JWT secret
├── Specific user-agent/version → Client-side bug
│   → Check recent mobile/frontend deploy
├── Connection errors → Infrastructure issue
│   → Check DB, check OAuth provider, check TLS certificates
└── All error types + gradual onset → Multiple issues or traffic pattern change
    → Deeper investigation needed
```

The first 5 minutes of investigation should answer: is this an attack (wrong passwords from few IPs) or a system issue (various errors from many legitimate users)? That determines everything else.'''
    ),
    (
        "thinking/causal-pipeline-stall",
        "Our data pipeline that runs nightly stopped working. The job starts but hangs indefinitely at the 'transform' stage. It was working fine last week. What's the investigation process?",
        r'''<think>
Pipeline hangs at transform stage. Was working last week. Let me think through possible causes.

"Hangs indefinitely" suggests it's not crashing — it's stuck. This narrows the possibilities:
- Waiting for a lock
- Waiting for a resource (memory, disk, network)
- Infinite loop
- Deadlock
- Waiting for external service that's not responding

Hypothesis 1: Data volume change
- The source data grew significantly
- Transform that handled 1M rows now faces 100M rows
- Doesn't crash, just takes much longer (or runs out of memory and swaps)
- Test: check input data size this week vs last week
- Likelihood: MEDIUM-HIGH

Hypothesis 2: Schema change in source data
- Upstream team changed a column type or added nulls
- Transform code doesn't crash but enters an infinite retry or hangs on unexpected data
- Test: compare current data schema to last week's
- Likelihood: MEDIUM

Hypothesis 3: Database lock contention
- Transform writes to a table that another process has locked
- Transform waits for the lock → hangs
- New job or query was added that locks the table during transform window
- Test: check pg_locks / SHOW PROCESSLIST during the hang
- Likelihood: HIGH

Hypothesis 4: External dependency timeout
- Transform calls an API (geocoding, enrichment) that is now slow/down
- Default timeout is infinite → hangs on network call
- Test: check if transform makes any network calls, check external service status
- Likelihood: MEDIUM

Hypothesis 5: Resource exhaustion
- Transform needs more memory than available
- System starts swapping → appears to hang (actually running at 0.001x speed)
- Test: check memory usage, swap usage, disk I/O during the hang
- Likelihood: MEDIUM

Hypothesis 6: Code change in the pipeline
- Someone modified the transform logic
- Introduced a bug that causes infinite loop or deadlock
- Test: git log on the pipeline code since last success
- Likelihood: MEDIUM (should check this first)

Investigation order:
1. Check for code changes (fastest to verify)
2. Check input data size/schema (quick comparison)
3. Check resource utilization during the hang (memory, CPU, disk)
4. Check for locks/blocking queries
5. Attach to the hanging process and see what it's doing
</think>

A pipeline that hangs (doesn't crash) has a specific set of causes. Here's the systematic investigation.

**Step 1 — Quick checks (2 minutes each):**

```bash
# Check 1: Was the pipeline code changed?
git log --since="1 week ago" --oneline -- pipeline/ etl/ transforms/
# If changes → diff them. If not → it's data or infrastructure.

# Check 2: What is the process DOING right now?
# Find the PID
ps aux | grep transform

# Check if it's CPU-bound (infinite loop) or IO-bound (waiting for something)
top -p $PID
# 100% CPU → infinite loop or computation
# 0% CPU → waiting for lock, network, or disk

# For Python: attach to see the current stack trace
py-spy dump --pid $PID
# Shows exactly which line of code the process is stuck on:
# Thread 1: transform.py:142 → db.execute("INSERT INTO ...")
# Now you know it's stuck on a DB operation!
```

**Step 2 — Based on what you find:**

**If stuck on a database operation (most common):**

```sql
-- Check for lock contention
SELECT blocked.pid, blocked.query AS blocked_query,
       blocking.pid AS blocking_pid, blocking.query AS blocking_query,
       now() - blocked.query_start AS wait_time
FROM pg_stat_activity blocked
JOIN pg_locks bl ON bl.pid = blocked.pid AND NOT bl.granted
JOIN pg_locks kl ON kl.locktype = bl.locktype
    AND kl.relation = bl.relation AND kl.granted
JOIN pg_stat_activity blocking ON kl.pid = blocking.pid
WHERE blocked.pid = <transform_pid>;

-- Common scenario:
-- blocking_query: "ALTER TABLE output_table ADD COLUMN ..." (migration!)
-- OR: "VACUUM FULL output_table" (maintenance job overlapping)
-- OR: another instance of the same pipeline running

-- Fix: kill the blocking query or reschedule jobs to not overlap
```

**If CPU is at 100% (infinite loop or data explosion):**

```python
# Check input data volume
current_count = source_db.execute("SELECT COUNT(*) FROM source_table").scalar()
print(f"Current rows: {current_count:,}")
# If it jumped from 1M to 100M → that's your problem

# Check for data that causes infinite processing
# Example: self-referencing records creating infinite traversal
# Or: NULL values causing unexpected joins that multiply row count
df = pd.read_sql("SELECT * FROM source_table LIMIT 1000", source_db)
print(df.describe())
print(df.isnull().sum())  # Unexpected NULLs?
```

**If waiting on network (0% CPU, py-spy shows network call):**

```python
# Check if transform calls external services
# The external service might be:
# - Down (hanging on connection that never completes)
# - Rate limiting (retrying forever)
# - Responding slowly (large response)

# Fix: add timeouts to ALL external calls
import httpx

# BEFORE (hangs forever if service is down):
response = httpx.get("https://api.enrichment.com/data")

# AFTER (fails after 30 seconds):
response = httpx.get("https://api.enrichment.com/data", timeout=30.0)
```

**If memory exhaustion (check swap):**

```bash
# Check memory during the hang
free -h
# If swap is heavily used → process is memory-bound

# Check the process specifically
cat /proc/$PID/status | grep -i mem
# VmRSS: actual memory usage
# VmSwap: how much is swapped (if high → that's why it's "hanging")

# Fix: process data in chunks instead of loading everything
```

```python
# BEFORE: loads entire dataset into memory
df = pd.read_sql("SELECT * FROM big_table", engine)  # 100M rows → OOM
result = transform(df)

# AFTER: process in chunks
for chunk in pd.read_sql("SELECT * FROM big_table", engine, chunksize=10000):
    result = transform(chunk)
    write_output(result)
```

**Prevention:**

```python
# Add timeouts and monitoring to the pipeline
import signal

def timeout_handler(signum, frame):
    raise TimeoutError("Transform stage exceeded 2 hour limit")

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(7200)  # 2 hour timeout

try:
    run_transform()
except TimeoutError:
    logger.error("Transform stage timed out — investigate!")
    alert_oncall("Pipeline transform hung for > 2 hours")
finally:
    signal.alarm(0)  # Cancel alarm
```

Start with `py-spy dump --pid` — it shows you the exact line of code where the process is stuck. That single command usually identifies the cause in 30 seconds.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
