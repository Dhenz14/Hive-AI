"""
Ambiguous request handling pairs - vague bug reports
"""

pairs = [
    {
        "instruction": r'''It's broken. Can you fix it?''',
        "output": r'''<think>
"It's broken" -- this tells me almost nothing. What's broken? An error message? Wrong output? Crash? Blank screen? What changed recently? What's the expected behavior vs actual behavior? I don't even know what "it" refers to. I need to guide them toward giving me actionable information without being dismissive of their frustration.
</think>

I want to help, but I need a bit more to go on:

1. **What's the symptom?** Error message, crash, wrong output, blank page, or something else? If there's an error message or stack trace, that's the most useful thing you can share.
2. **What were you doing when it broke?** Which page/action/feature?
3. **When did it start?** Was it working before and stopped, or has it never worked?
4. **Did anything change recently?** New deployment, config change, dependency update?

While you gather that info, here's a quick diagnostic checklist you can run through:

```text
== Quick triage ==

1. Check the logs first:
   - Application logs (stderr, log files, or your logging service)
   - Web server logs (nginx/apache access + error logs)
   - Browser console (F12 -> Console tab) if it's a frontend issue

2. Can you reproduce it?
   - Every time, or intermittent?
   - All users or just some?
   - All browsers/devices or specific ones?

3. What's different between "working" and "broken"?
   - Recent deployments: git log --oneline -10
   - Config changes: git diff HEAD~5 -- '*.env' '*.yml' '*.json'
   - Dependency changes: git diff HEAD~5 -- '*lock*' 'requirements*'
```

```bash
# Quick health checks to run right now:
# Check if the service is running
curl -s http://localhost:YOUR_PORT/health

# Check recent logs for errors
tail -100 /var/log/your-app/error.log | grep -i "error\|exception\|traceback"

# Check disk space (full disk causes mysterious failures)
df -h

# Check memory (OOM kills look like random crashes)
free -h
```

Share what you find and I'll diagnose the specific issue.'''
    },
    {
        "instruction": r'''Something's wrong with the data. Users are seeing incorrect values.''',
        "output": r'''<think>
"Something's wrong with the data" and "incorrect values" -- this could be a data corruption issue, a calculation bug, a caching problem showing stale data, a race condition, a timezone issue, a type conversion issue, or data from the wrong environment. I need to know which data, what's wrong about it, and whether it's a display issue or the stored data itself is bad.
</think>

Data issues can be tricky to pin down. Let me ask some targeted questions:

1. **Which values are wrong?** Can you give me a specific example -- "User X sees value Y but it should be Z"?
2. **Is the data wrong in the database, or just displayed wrong?** Check the DB directly -- if the stored value is correct, it's a frontend/API issue. If the DB itself is wrong, it's a write-path bug.
3. **Is it all data or specific records?** All users affected, or just some?
4. **When did correct data become incorrect?** Was it written wrong originally, or did it change at some point?

Here's a systematic approach to diagnosing data issues:

```python
# Step 1: Compare what the API returns vs what's in the DB
# Run this query directly against your database:

"""
SELECT id, name, balance, updated_at
FROM accounts
WHERE id = <the_affected_user_id>;
"""

# Then hit the API and compare:
# curl -s https://yourapp.com/api/accounts/<id> | python -m json.tool

# Step 2: Common culprits to check

# A. Caching returning stale data
#    - Is there a Redis/memcache layer? Check if cached value differs from DB
#    - Try clearing the cache for the affected record and see if it fixes it

# B. Timezone issues (extremely common)
#    - Dates stored as UTC but displayed in local time (or vice versa)
#    - Check: SELECT created_at, created_at AT TIME ZONE 'UTC' FROM ...

# C. Floating point math
#    - Are you doing money calculations with float instead of Decimal?
#    0.1 + 0.2 == 0.30000000000000004 in most languages

# D. Race conditions
#    - Two requests updating the same record simultaneously
#    - Check if affected records have very close updated_at timestamps

# Step 3: Audit trail -- find when the data changed
"""
-- If you have an audit/history table:
SELECT * FROM account_history
WHERE account_id = <id>
ORDER BY changed_at DESC
LIMIT 20;

-- If not, check updated_at timestamps:
SELECT id, balance, updated_at
FROM accounts
WHERE updated_at > '2026-03-01'
ORDER BY updated_at DESC;
"""
```

Give me a concrete example of a wrong value and I'll trace the root cause.'''
    },
    {
        "instruction": r'''Users are complaining about the app. Can you look into it?''',
        "output": r'''<think>
"Users are complaining" -- about what? Performance? Errors? Confusing UI? Missing features? Data issues? This is the vaguest possible bug report. I don't even know what they're complaining about, let alone what's causing it. I need to understand the nature of the complaints before I can investigate anything meaningful.
</think>

I'd love to help, but I need to understand what users are actually reporting:

1. **What are the complaints?** Can you share a few verbatim user reports or support tickets? (e.g., "I click save and nothing happens" vs "the page is slow" are very different problems)
2. **How many users?** One person or widespread?
3. **When did complaints start?** Correlate with recent deployments or changes.

Here's how to quickly triage user complaints if you don't have specifics yet:

```text
== Investigation priorities (check in this order) ==

1. ERROR MONITORING (Sentry, Datadog, CloudWatch, etc.)
   - Are there new/spiking errors in the last 24-48 hours?
   - Sort by "first seen" to find recently introduced bugs

2. DEPLOYMENT HISTORY
   - What was deployed in the last few days?
   - git log --oneline --since="3 days ago"
   - Correlate deployment times with complaint times

3. PERFORMANCE METRICS
   - Are response times elevated?
   - Any endpoints timing out?
   - Database CPU/memory spikes?

4. STATUS PAGE / THIRD PARTIES
   - Are any external services down? (payment provider, email, CDN)
   - Check status pages for AWS, Stripe, etc.
```

```bash
# Quick diagnostic commands:

# Check error rate in recent logs
grep -c "ERROR\|500\|Exception" /var/log/app/app.log

# Check for recent spikes in response time (if using structured logs)
# Look for requests over 5 seconds in the last hour
grep "$(date -d '1 hour ago' '+%Y-%m-%d %H')" /var/log/app/access.log | \
    awk '$NF > 5000 {print $0}' | wc -l

# Check system resources
uptime        # load average
free -h       # memory
df -h         # disk space
```

If you can share even one specific user complaint or a recent error from your monitoring, I can start tracing the actual issue. Generic "users are unhappy" is hard to act on without a concrete symptom.'''
    },
    {
        "instruction": r'''It works on my machine but not in production. Help!''',
        "output": r'''<think>
"Works locally but not in prod" -- classic environment difference issue. Could be: different environment variables, different database (empty/different schema), different OS/runtime version, different file paths, missing dependencies, different network topology (can't reach services), permissions differences, HTTPS vs HTTP, CORS in browser, or config file not deployed. I need to know the error and what "doesn't work" looks like.
</think>

The classic "works on my machine" -- this is almost always an environment difference. Key questions:

1. **What does "doesn't work" look like in prod?** Error message, blank page, wrong behavior, timeout, 500 error?
2. **How is prod different from local?** (Docker vs bare metal, different OS, cloud provider, reverse proxy like nginx in front?)
3. **Can you access prod logs?** The error message is usually the fastest path to the answer.

Here's a systematic checklist of the most common local-vs-prod differences:

```text
== Environment differences to check (ranked by frequency) ==

1. ENVIRONMENT VARIABLES
   - Missing or different values in prod
   - Check: compare your .env / docker-compose / cloud config
   - Common: DATABASE_URL, API_KEY, SECRET_KEY, DEBUG=true vs false

2. DATABASE
   - Different schema (missing migration?)
   - Different data (empty tables, missing seed data)
   - Check: run your migrations in prod, compare schema

3. FILE PATHS
   - Hardcoded paths that don't exist in prod
   - /home/yourname/project/ vs /app/ in Docker
   - File permissions (can the process read/write?)

4. NETWORK
   - Service URLs different (localhost:5432 vs prod-db.internal:5432)
   - Firewall/security groups blocking connections
   - DNS resolution differences

5. DEPENDENCIES
   - Different versions (pip install vs pinned requirements.txt)
   - Missing system libraries (libpq, imagemagick, etc.)
   - Node: node_modules built on Mac vs Linux (native deps)

6. RUNTIME VERSION
   - Python 3.11 locally vs 3.9 in prod
   - Node 20 locally vs Node 18 in prod
```

```bash
# Quick comparison commands to run on BOTH local and prod:

# Runtime version
python --version  # or node --version

# Environment variables (redact secrets!)
env | sort | grep -v "KEY\|SECRET\|PASSWORD\|TOKEN"

# Installed packages
pip freeze | sort > /tmp/deps.txt  # compare between environments

# Check if you can reach dependent services
curl -s http://your-database-host:5432 || echo "Can't reach database"
curl -s http://your-redis-host:6379 || echo "Can't reach Redis"

# Check recent logs in prod
journalctl -u your-app -n 50 --no-pager
# or: docker logs your-container --tail 50
# or: kubectl logs deployment/your-app --tail 50
```

The prod error message will tell us exactly which of these it is. Can you grab the logs?'''
    },
    {
        "instruction": r'''We're seeing intermittent failures. Sometimes it works, sometimes it doesn't.''',
        "output": r'''<think>
"Intermittent failures" -- these are the hardest bugs. Could be race conditions, connection pool exhaustion, timeout from external services, memory pressure, DNS resolution flakiness, load balancer issues, cache expiration timing, or even time-dependent logic bugs. Without knowing what fails, how often, and whether there's a pattern, I can only suggest diagnostic approaches. I need to know what the failure looks like and any patterns.
</think>

Intermittent bugs are the hardest to track down. A few questions that will narrow it quickly:

1. **What does the failure look like?** Error message, timeout, wrong data, or different symptoms each time?
2. **What's the frequency?** 1 in 10 requests? Once a day? Under high load only?
3. **Any patterns?** Time of day, specific users, specific actions, after a certain uptime duration?

Intermittent failures almost always fall into one of these categories. Here's how to diagnose each:

```text
== Common causes of intermittent failures ==

1. RACE CONDITIONS
   Pattern: Fails when two users do the same thing at once
   Diagnose: Check if failures correlate with concurrent requests
   Fix: Add database locks or optimistic concurrency control

2. CONNECTION POOL EXHAUSTION
   Pattern: Works fine, then suddenly many requests fail, then recovers
   Diagnose: Monitor active DB/Redis connections over time
   Fix: Increase pool size, add connection timeouts, fix connection leaks

3. EXTERNAL SERVICE TIMEOUTS
   Pattern: Fails when a third-party API is slow
   Diagnose: Log response times from external calls
   Fix: Add timeouts, retries with backoff, circuit breakers

4. MEMORY PRESSURE
   Pattern: Works after restart, degrades over hours/days
   Diagnose: Monitor memory usage over time
   Fix: Find and fix the memory leak

5. DNS / NETWORK FLAKINESS
   Pattern: Random connection refused or timeout errors
   Diagnose: Log the specific error (connection refused vs timeout vs DNS)
   Fix: Use connection pooling, retry logic, health checks
```

```python
# Add this to your codebase to catch intermittent issues:

import logging
import time
import traceback
from functools import wraps

logger = logging.getLogger("diagnostics")

def log_failures(func):
    """Log detailed context on every failure for post-mortem analysis."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            if elapsed > 2.0:  # log slow successes too
                logger.warning(
                    "SLOW %s took %.1fs args=%s",
                    func.__name__, elapsed, str(args)[:200]
                )
            return result
        except Exception as e:
            elapsed = time.perf_counter() - start
            logger.error(
                "FAILED %s after %.1fs error=%s args=%s\n%s",
                func.__name__, elapsed, str(e), str(args)[:200],
                traceback.format_exc()
            )
            raise
    return wrapper

# Apply to suspect functions:
# @log_failures
# def call_payment_api(order_id):
#     ...
```

The key is to log enough context on each failure that you can find the pattern. Once you tell me what the error looks like, I can narrow it to a specific cause.'''
    },
]
