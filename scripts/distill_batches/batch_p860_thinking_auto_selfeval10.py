"""Phase 4B: Self-Improvement -- Self-Evaluation (Part 10)

Evaluating own debugging methodology for soundness and completeness.
"""

PAIRS = [
    (
        "thinking/auto-selfeval-debug-production-incident",
        r'''A developer reports: "Our production API is returning 500 errors intermittently. About 10% of requests fail." I am about to recommend restarting the servers. Let me evaluate whether that is the right first step:

My draft: "Try restarting your application servers. This often fixes intermittent issues caused by memory leaks or stale connections. If the problem persists after restart, check your logs."''',
        r'''<think>
Let me evaluate my debugging recommendation:

**The problem:** 10% of requests returning 500 errors intermittently.

**My recommendation:** Restart servers, then check logs.

**Is this good advice? NO. This is backwards and potentially harmful.**

**Problem 1: Restarting destroys evidence**
- In-memory state that might explain the bug is lost
- Active connections/requests being processed are killed
- If there is a memory leak, the heap dump that would diagnose it is lost
- If there is a thread deadlock, the thread dump is lost
- After restart, you know it "works" but not WHY it failed

**Problem 2: Restart is not a fix**
- If the root cause is a bug, it will happen again
- If 10% of requests fail, restart might briefly help, then the problem returns
- "Restart to fix" creates a culture of not understanding your systems

**Problem 3: Logs should be FIRST, not last**
- Logs are the primary diagnostic tool for production issues
- Checking logs AFTER restarting means you might miss the error patterns
- Log rotation might have already removed evidence

**What I should have recommended:**
1. Check logs and error tracking FIRST (before anything else)
2. Identify WHICH requests fail (endpoint? user? geography?)
3. Look for patterns (time-based? load-based? specific input?)
4. THEN take action based on what you find

**Verdict:** My advice would destroy diagnostic evidence and not fix the root cause. Rating: 2/10.
</think>

**Self-evaluation: "Restart the servers" is cargo-cult debugging, not a methodology. Rating: 2/10.**

**Why restarting first is wrong:**
| Action | Evidence preserved? | Root cause found? | Problem solved permanently? |
|--------|-------------------|-------------------|---------------------------|
| Restart first | NO -- state lost | NO | NO -- will recur |
| Investigate first | YES | Likely YES | YES -- fix the cause |

**What I should recommend instead:**

"Don't restart yet. Let's find the root cause first:

**Step 1: Check error tracking (2 minutes)**
```bash
# If you use Sentry/Datadog/similar:
# - What exception types are the 500 errors?
# - What endpoints are affected?
# - When did this start?
# - Is there a common stack trace?
```

**Step 2: Check application logs (5 minutes)**
```bash
# Find the 500 errors:
grep -i 'error\|exception\|500' /var/log/app/app.log | tail -100

# Look for patterns:
# - Same error message repeated?
# - Same endpoint?
# - Timestamps clustering at certain intervals?
```

**Step 3: Check system metrics (2 minutes)**
```bash
# CPU, memory, disk, network
top -bn1 | head -20
free -h
df -h
netstat -an | grep ESTABLISHED | wc -l
```

**Step 4: Check downstream dependencies (3 minutes)**
```bash
# Database: is it healthy?
# External APIs: are they responding?
# Message queue: is it backed up?
# DNS: is resolution working?
```

**Step 5: Narrow down the cause**
Based on what you find:
- Same endpoint always fails -> Bug in that endpoint's code
- Random endpoints fail -> Resource exhaustion or infrastructure
- Errors spike at certain times -> Load-related or cron job conflict
- Errors started at a specific time -> Check what was deployed then

**ONLY THEN** decide if a restart is appropriate (and take a heap dump first if you suspect memory issues)."

**Self-evaluation lesson:** Never skip diagnosis and jump to remediation. Restarting is like turning off a fire alarm without checking for fire -- it stops the noise but not the danger.'''
    ),
    (
        "thinking/auto-selfeval-debug-performance-issue",
        r'''A user says their web application is slow. I am about to ask them to add more caching. Let me evaluate my debugging approach:

My draft: "Add Redis caching to your database queries. Cache the results for 5 minutes. Also, consider adding a CDN for static assets and enabling gzip compression."''',
        r'''<think>
Let me evaluate my debugging approach:

**The problem:** "Web application is slow" -- this is incredibly vague.

**My recommendation:** Add caching, CDN, gzip compression.

**Is this good debugging? ABSOLUTELY NOT.**

**Problem 1: I don't know what "slow" means**
- Page load time? API response time? Database query time?
- How slow? 500ms (acceptable)? 5 seconds (bad)? 30 seconds (broken)?
- Slow for all users? Some users? One page? All pages?
- Slow always? Or only under load?

**Problem 2: I'm prescribing solutions without a diagnosis**
- Caching only helps if the bottleneck is database queries
- CDN only helps if the bottleneck is static asset delivery
- Gzip only helps if the bottleneck is response payload size
- If the bottleneck is a slow external API call, NONE of these help

**Problem 3: Shotgun approach wastes time**
- Adding caching, CDN, AND gzip is three separate changes
- If only one was needed, the other two were wasted effort
- If none address the actual bottleneck, ALL were wasted effort

**What I should have done:**
1. Ask clarifying questions (what is slow, how slow, since when)
2. Recommend profiling to find the bottleneck
3. THEN recommend a targeted fix

**Verdict:** I skipped the entire diagnostic process and jumped to three random optimizations. This might help by luck, but it is not engineering. Rating: 2/10.
</think>

**Self-evaluation: I prescribed three treatments without any diagnosis. This is not debugging -- it is guessing. Rating: 2/10.**

**The fundamental error:** Jumping from "it's slow" to "add caching + CDN + gzip" without any measurement.

**What I should recommend instead:**

"Before adding anything, let's find WHERE the time is spent:

**Step 1: Define 'slow' precisely**
- Which page/endpoint is slow?
- How slow exactly? (measure with browser DevTools Network tab)
- For all users or specific ones? (geography? device? browser?)
- When did it become slow? (was there a deployment? traffic spike?)

**Step 2: Profile the request end-to-end**
Break down where time is spent:

```
Total request time: 4.2 seconds
  DNS resolution:        0.05s
  TCP connection:        0.08s
  TLS handshake:         0.12s
  Server processing:     3.50s  <-- THIS is the bottleneck
  Content transfer:      0.45s
```

**Step 3: Profile the server processing**
```python
# Add timing to your endpoint:
import time

@app.route('/slow-page')
def slow_page():
    t0 = time.perf_counter()
    users = db.query('SELECT * FROM users')
    t1 = time.perf_counter()
    orders = db.query('SELECT * FROM orders WHERE ...')
    t2 = time.perf_counter()
    recommendations = external_api.get_recommendations()
    t3 = time.perf_counter()
    html = render_template('page.html', ...)
    t4 = time.perf_counter()

    logger.info(f'DB users: {t1-t0:.3f}s, DB orders: {t2-t1:.3f}s, '
                f'API: {t3-t2:.3f}s, Render: {t4-t3:.3f}s')
    return html
```

**Step 4: Fix the actual bottleneck**
| If the bottleneck is... | Fix |
|------------------------|-----|
| Database query (3s) | Check EXPLAIN, add indexes |
| External API (3s) | Add timeout, cache responses, or make async |
| Template rendering (3s) | Simplify template, precompute data |
| Response payload (large) | Paginate, compress, return less data |
| DNS/TLS (slow) | CDN, keep-alive connections |

**Then and only then** consider caching as an optimization on top of a fix."

**Self-evaluation lesson:** Never optimize without profiling. The bottleneck is almost never where you think it is. Measure first, fix second.'''
    ),
    (
        "thinking/auto-selfeval-debug-memory-leak",
        r'''A developer reports their Python application's memory usage grows over time until it crashes. I am about to recommend upgrading to a server with more RAM. Let me evaluate this advice:

My draft: "You probably need more memory. Try upgrading your server to 16GB RAM. Also, you could set up a cron job to restart the application every 6 hours to prevent the memory from growing too large."''',
        r'''<think>
Let me evaluate my recommendation:

**The problem:** Memory grows continuously until crash. This is a textbook memory leak.

**My recommendation:** More RAM + periodic restarts.

**Is this good advice? This is TERRIBLE advice.**

**Problem 1: More RAM does not fix a leak**
- If memory grows 100MB/hour, 8GB buys you ~80 hours instead of ~40 hours
- The application still crashes, just later
- It is like fixing a leaking pipe by putting a bigger bucket underneath

**Problem 2: Periodic restarts are a band-aid**
- Restarting every 6 hours means dropped requests, broken connections
- If the leak rate increases (more traffic), 6 hours might not be enough
- This masks the real bug and creates technical debt
- It becomes permanent "infrastructure" that no one dares remove

**Problem 3: I did not investigate the CAUSE**
- Memory leaks in Python usually have specific, fixable causes
- Common causes: growing caches, unclosed resources, circular references, global lists
- Finding and fixing the leak is usually a few hours of work

**What I should have recommended:**
1. Profile memory to find what is growing
2. Identify the specific leak source
3. Fix the root cause
4. Monitor to verify the fix

**Verdict:** I recommended throwing hardware and cron jobs at a software bug. This wastes money, adds complexity, and does not fix anything. Rating: 1/10.
</think>

**Self-evaluation: Recommending more RAM for a memory leak is like recommending a bigger bucket for a leaking pipe. Rating: 1/10.**

**What I should recommend instead:**

"This is a memory leak. Let's find and fix it:

**Step 1: Confirm it is a leak (not normal growth)**
```python
# Add memory tracking to your app:
import psutil, os

def log_memory():
    process = psutil.Process(os.getpid())
    mem = process.memory_info().rss / 1024 / 1024
    print(f'Memory usage: {mem:.1f} MB')

# Call this periodically. If it ALWAYS grows, it is a leak.
# If it grows then stabilizes, it is caching (probably fine).
```

**Step 2: Find what is growing**
```python
# Use tracemalloc to track allocations:
import tracemalloc

tracemalloc.start()

# ... run your application for a while ...

# Take a snapshot and see top allocators:
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

print('Top 10 memory allocators:')
for stat in top_stats[:10]:
    print(stat)
# This tells you EXACTLY which lines of code are allocating the most memory
```

**Step 3: Common leak patterns in Python**

```python
# LEAK 1: Growing global list/dict
_cache = {}  # Never evicted!
def get_data(key):
    if key not in _cache:
        _cache[key] = expensive_query(key)  # Grows forever
    return _cache[key]
# FIX: Use LRU cache with a size limit
from functools import lru_cache
@lru_cache(maxsize=1000)
def get_data(key): ...

# LEAK 2: Unclosed resources
def process_file(path):
    f = open(path)  # Never closed!
    data = f.read()
    return data
# FIX: Use context managers
def process_file(path):
    with open(path) as f:
        return f.read()

# LEAK 3: Event handlers / callbacks accumulating
def setup():
    for item in items:
        event_bus.on('update', lambda: handle(item))  # Adds handler every call!
# FIX: Remove handlers when no longer needed, or register once

# LEAK 4: Circular references preventing garbage collection
class Node:
    def __init__(self):
        self.parent = None
        self.children = []
    def add_child(self, child):
        child.parent = self  # Circular: parent -> child -> parent
        self.children.append(child)
# FIX: Use weakref for back-references
import weakref
class Node:
    def __init__(self):
        self._parent = None
        self.children = []
    def add_child(self, child):
        child._parent = weakref.ref(self)
        self.children.append(child)
```

**Step 4: Verify the fix**
```python
# Run with memory monitoring for 24 hours
# Memory should stabilize (grow to a plateau, not grow forever)
# Set up an alert if memory exceeds a threshold
```"

**Self-evaluation lesson:** Hardware and restarts are not debugging. When something is broken, find and fix the root cause. Memory leaks are always caused by specific code and can always be fixed.'''
    ),
    (
        "thinking/auto-selfeval-debug-race-condition",
        r'''A developer says: "Our application has a bug where sometimes two users can book the same timeslot. It happens maybe once a week." I am about to recommend adding a unique constraint. Let me evaluate whether that fully addresses the issue:

My draft: "Add a UNIQUE constraint on (timeslot_id, date) in your bookings table. This will prevent duplicate bookings at the database level."''',
        r'''<think>
Let me evaluate my recommendation:

**The problem:** Two users can sometimes book the same timeslot. This happens intermittently (once a week), suggesting a race condition.

**My recommendation:** Add a UNIQUE constraint.

**Is this partially correct? YES, but it is incomplete.**

**What the UNIQUE constraint does:**
- Prevents duplicate rows in the database (good!)
- One of the two concurrent bookings will get a database error
- This is a SAFETY NET, not a solution

**What the UNIQUE constraint does NOT do:**
- It does not provide a good user experience (one user gets an error)
- It does not explain WHY the race condition exists
- It does not fix the application logic that allows it

**The likely root cause:**
```python
# Classic check-then-act race condition:
def book_timeslot(user_id, timeslot_id, date):
    # Thread 1: checks, sees it is available
    # Thread 2: checks, sees it is available (same time!)
    existing = db.query("SELECT * FROM bookings WHERE timeslot_id = ? AND date = ?",
                        timeslot_id, date)
    if existing:
        return "Already booked"

    # Both threads pass the check, both insert
    db.execute("INSERT INTO bookings (user_id, timeslot_id, date) VALUES (?, ?, ?)",
               user_id, timeslot_id, date)
    return "Booked!"
```

**The UNIQUE constraint catches the duplicate INSERT, but the user gets an ugly error instead of a graceful "sorry, just booked" message.**

**What I should have recommended:**
1. YES, add the UNIQUE constraint (safety net)
2. AND fix the application logic to handle the race condition
3. AND handle the constraint violation gracefully

**Verdict:** My advice is correct but incomplete. The constraint prevents data corruption but does not fix the user experience or the underlying race condition. Rating: 5/10.
</think>

**Self-evaluation: The UNIQUE constraint is necessary but not sufficient. Rating: 5/10.**

**What I should recommend instead:**

"You have a race condition. Fix it at multiple levels:

**Level 1: Database constraint (safety net)**
```sql
ALTER TABLE bookings ADD CONSTRAINT uq_booking_timeslot
    UNIQUE (timeslot_id, date);
```
This prevents data corruption even if the application logic has bugs.

**Level 2: Fix the race condition in application code**

Option A: Use SELECT FOR UPDATE (pessimistic locking):
```python
def book_timeslot(user_id, timeslot_id, date):
    with db.transaction():
        # Lock the row so no other transaction can read it
        existing = db.query(
            'SELECT * FROM bookings WHERE timeslot_id = %s AND date = %s FOR UPDATE',
            timeslot_id, date
        )
        if existing:
            return {'error': 'This timeslot was just booked. Please choose another.'}

        db.execute(
            'INSERT INTO bookings (user_id, timeslot_id, date) VALUES (%s, %s, %s)',
            user_id, timeslot_id, date
        )
        return {'success': 'Timeslot booked!'}
```

Option B: Use INSERT with conflict handling (optimistic):
```python
def book_timeslot(user_id, timeslot_id, date):
    try:
        db.execute(
            'INSERT INTO bookings (user_id, timeslot_id, date) VALUES (%s, %s, %s)',
            user_id, timeslot_id, date
        )
        return {'success': 'Timeslot booked!'}
    except UniqueViolation:
        return {'error': 'This timeslot was just booked. Please choose another.'}
```

**Level 3: UI feedback**
- When a user selects a timeslot, show real-time availability
- After booking, confirm with a clear success message
- On conflict, show a friendly message with available alternatives

**Which approach to use:**
| Approach | Best when | Drawback |
|----------|-----------|----------|
| SELECT FOR UPDATE | Low contention, need to check complex rules | Holds locks |
| INSERT + catch conflict | High contention, simple constraint | Less control over error message |
| Both (belt and suspenders) | Critical business logic | Slightly more code |

For booking systems, I recommend the optimistic approach (INSERT + catch conflict) because it is simpler and conflicts are rare (once a week)."

**Self-evaluation lesson:** A database constraint is a safety net, not a solution. Always fix the race condition at the application level AND add the constraint as defense in depth.'''
    ),
    (
        "thinking/auto-selfeval-debug-deployment-failure",
        r'''Our latest deployment broke the application. Users are seeing errors. I am about to recommend immediately rolling back. Let me evaluate whether that is always the right first response:

My draft: "Roll back immediately to the previous version. You can investigate the issue after the service is restored."''',
        r'''<think>
Let me evaluate my recommendation:

**The problem:** Latest deployment broke the application.

**My recommendation:** Roll back immediately, investigate later.

**Is this good advice? MOSTLY YES, but with important caveats.**

**When rolling back is the RIGHT first response:**
- Users are actively affected (errors, downtime)
- The severity is high (payments failing, data loss)
- You have a quick rollback mechanism (container swap, blue/green)
- The rollback is safe (no database migrations that are one-way)

**When rolling back may be WRONG or RISKY:**
- Database migrations have already run (you may need a forward fix)
- Rolling back causes data loss (new data written with new schema)
- The bug exists in the OLD version too (rollback does not help)
- External dependencies changed (API version, third-party update)
- The rollback itself is risky (no tested rollback process)

**Problem with my advice: "investigate after"**
- This is partially correct -- restore service first
- But you should capture evidence BEFORE rolling back
- After rollback, the broken state is gone
- If you did not capture logs, metrics, and error details, diagnosis is harder

**What I should have recommended:**
1. Assess severity and capture evidence
2. THEN roll back if appropriate
3. Investigate using captured evidence
4. Deploy a fix (not just stay on old version)

**Verdict:** My advice is correct for the simple case but ignores important edge cases and the need to preserve diagnostic information. Rating: 6/10.
</think>

**Self-evaluation: Rollback is usually right, but "always roll back immediately" is oversimplified. Rating: 6/10.**

**What I should recommend instead:**

"Here is the deployment failure response protocol:

**Phase 1: Assess (1-2 minutes)**
```
1. What is broken?
   - All requests failing? Or specific endpoints?
   - Data corruption? Or just errors?
   - What does the error look like?

2. How severe?
   - CRITICAL: All users affected, data at risk -> Phase 2 immediately
   - HIGH: Many users affected, no data risk -> Phase 2 after capturing evidence
   - MEDIUM: Some users, workaround exists -> Investigate before deciding

3. Can we roll back safely?
   - Were there database migrations? -> Check if reversible
   - Were there schema changes? -> New data may be incompatible with old code
   - Were there external API changes? -> Old code may not work with new API
```

**Phase 2: Capture evidence before rollback (1-3 minutes)**
```bash
# Save current error state:
kubectl logs deployment/myapp --since=10m > /tmp/crash-logs.txt
# or: journalctl -u myapp --since '10 minutes ago' > /tmp/crash-logs.txt

# Save error tracking data:
# Screenshot or export Sentry/Datadog errors

# Check what changed:
git log --oneline HEAD~5..HEAD  # What commits were in this deploy?
```

**Phase 3: Roll back (if appropriate)**
```bash
# If using container orchestration:
kubectl rollout undo deployment/myapp

# If using platform hosting:
git revert HEAD && git push

# If database migrations are involved:
# Do NOT blindly roll back -- check if migration is reversible first
python manage.py showmigrations  # Check current state
python manage.py migrate myapp 0042  # Roll back to specific migration
```

**Phase 4: Verify recovery**
```bash
# Check that errors stopped:
curl -s https://myapp.com/health | jq .

# Monitor error rate for 5 minutes
# Confirm the rollback actually fixed the issue
```

**Phase 5: Investigate and fix (next priority)**
```
1. Review captured logs and error traces
2. Reproduce locally with the broken code
3. Write a fix
4. Add a test that catches this specific failure
5. Deploy the fix (not just stay on old version forever)
```

**Decision tree:**
```
Is the site completely down?
  YES -> Roll back immediately (skip evidence capture)
  NO -> Capture evidence first (2 min), then assess

Were there database migrations?
  YES, reversible -> Roll back code AND migration
  YES, irreversible -> Forward fix required (do NOT roll back)
  NO -> Safe to roll back

Is data being corrupted?
  YES -> Stop the application immediately, then investigate
  NO -> Roll back at normal pace
```"

**Self-evaluation lesson:** "Roll back immediately" is good instinct but oversimplified. Capture evidence, check for migration risks, and verify the rollback actually fixes the issue. The goal is not just to stop the error -- it is to understand and prevent it from happening again.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
