"""Phase 2: Advanced Reasoning — Reasoning Under Uncertainty (Part 2)

Training the model to make well-reasoned decisions and provide useful guidance
even when information is incomplete, ambiguous, or unavailable, while being
transparent about confidence levels and assumptions.
"""

PAIRS = [
    (
        "thinking/advanced-uncertainty-capacity-estimation",
        r'''We need to estimate how many concurrent users our new web application can handle before launch, but we haven't done any load testing yet and don't have production benchmarks. The app is a Python/Django backend with PostgreSQL, served behind Nginx on a single 8-core, 32GB server. How should we approach estimating capacity?''',
        r'''<think>
This is a classic estimation-under-uncertainty problem. I don't have benchmarks for their specific application, but I can use general heuristics, back-of-envelope calculations, and identify the likely bottlenecks.

Let me think about what I DO know:
- Django/Python: single-threaded per worker (GIL), typically use Gunicorn with multiple workers
- Common rule of thumb: 2-4 workers per CPU core for CPU-bound, more for I/O-bound
- PostgreSQL: default max_connections is 100, each connection uses ~5-10MB RAM
- Nginx: can handle thousands of concurrent connections (not the bottleneck)

Estimation approach:
1. Identify the bottleneck (usually DB or app workers, not web server)
2. Estimate per-request resource usage
3. Calculate theoretical capacity
4. Apply safety factors for real-world conditions

For a typical Django app:
- Average response time: 100-500ms (highly variable)
- If 200ms average, each worker handles ~5 requests/second
- With 8 cores, 16-24 Gunicorn workers reasonable
- That's 80-120 requests/second theoretical max
- Concurrent users != requests/second (users make requests intermittently)
- Typical web app: 1 request every 10-30 seconds per active user
- So 80-120 req/s could serve 800-3600 "concurrent" users (very rough)

But this is extremely variable based on:
- Query complexity (N+1 queries? Complex joins?)
- Caching strategy (cached responses are 10-100x faster)
- Static asset serving (should be CDN, not Django)
- WebSocket usage (changes the concurrency model entirely)
- Background task load (competing for same resources)

I should give them a framework for estimation plus strong advice to actually load test before launch.
</think>

Without benchmarks, we're working with informed estimates and significant uncertainty margins. Here's a structured approach.

## Step 1: Identify the Likely Bottleneck

For a Django/PostgreSQL stack, the bottleneck order is typically:

```
Most likely bottleneck:
  1. Database queries        ← Slow queries dominate most Django apps
  2. Application workers     ← Python's GIL limits per-process throughput
  3. Memory                  ← 32GB is generous for a single app
  4. Network / Nginx         ← Almost never the bottleneck
```

## Step 2: Back-of-Envelope Estimation

**Application layer:**
```
Assumptions (typical Django app):
  Average response time:     200ms (moderate complexity)
  Gunicorn workers:          16-24 (2-3x CPU cores, I/O-bound app)
  Requests per worker/sec:   ~5 (1000ms / 200ms)
  Total throughput:           80-120 requests/second

Concurrent users (assuming 1 page action every 15 seconds):
  80 req/s × 15s = ~1,200 concurrent users (lower bound)
  120 req/s × 15s = ~1,800 concurrent users (upper bound)
```

**Database layer:**
```
PostgreSQL on 32GB RAM:
  Shared buffers:            ~8GB (25% of RAM)
  Max connections:           100 (default) → increase to ~200
  Connection pool:           PgBouncer with 20-30 server connections

  Typical bottleneck: not connection count, but query execution time
  If avg query takes 10ms, and you have 30 connections:
    → ~3,000 queries/second theoretical max
  If each request makes 5-10 queries:
    → Supports 300-600 requests/second from DB side
```

**Memory:**
```
  Each Gunicorn worker:      ~50-150MB (depends on app)
  20 workers × 150MB:        ~3GB for app workers
  PostgreSQL:                ~10GB (shared buffers + working memory)
  OS + Nginx + overhead:     ~2GB
  Total estimated:           ~15GB of 32GB → Memory is NOT the bottleneck
```

## Step 3: Realistic Estimate with Uncertainty

```
                    Pessimistic    Likely      Optimistic
                    (heavy pages)  (typical)   (cached/light)
Avg response time:  500ms          200ms       50ms
Throughput:         32 req/s       100 req/s   400 req/s
Concurrent users:   480            1,500       6,000

Assumptions: 1 request per 15s per user, 16 Gunicorn workers
```

**My honest confidence: LOW to MEDIUM.** These estimates can be off by 3-5x in either direction depending on:

| Factor | Impact if bad | Impact if good |
|--------|--------------|----------------|
| N+1 query problems | 5-10x slower | - |
| Effective caching | - | 5-20x faster |
| Unoptimized ORM queries | 2-5x slower | - |
| Static files via CDN | - | Removes 50%+ of load |
| Heavy file uploads | Could saturate workers | - |
| WebSocket connections | Changes model entirely | - |

## Step 4: What You Should Actually Do Before Launch

**Quick wins (do these now, no load test needed):**

```python
# 1. Add django-debug-toolbar in development
#    Look for N+1 queries — the #1 Django performance killer
INSTALLED_APPS += ['debug_toolbar']

# 2. Add select_related / prefetch_related everywhere
# Bad (N+1: one query per product's category):
products = Product.objects.all()
for p in products:
    print(p.category.name)  # Extra query each time

# Good (2 queries total):
products = Product.objects.select_related('category').all()

# 3. Set up connection pooling
# pip install django-db-connection-pool or use PgBouncer

# 4. Serve static files via CDN, not Django
STATIC_URL = 'https://cdn.yourapp.com/static/'
```

**Minimum viable load test (do this, it takes 2 hours):**

```bash
# Install locust (Python load testing)
pip install locust

# Create a basic test
cat > locustfile.py << 'PYEOF'
from locust import HttpUser, task, between

class WebUser(HttpUser):
    wait_time = between(5, 15)

    @task(3)
    def view_homepage(self):
        self.client.get("/")

    @task(2)
    def view_product(self):
        self.client.get("/products/1/")

    @task(1)
    def search(self):
        self.client.get("/search/?q=test")
PYEOF

# Run against a staging environment
locust --host=https://staging.yourapp.com
# Ramp up users until response times degrade
# THAT number is your actual capacity
```

## The Bottom Line

My rough estimate for your setup: **1,000-2,000 concurrent users** for a typical Django app with moderate query complexity and no aggressive caching. But I would treat this as a very rough order-of-magnitude guide, not a planning number.

The only number you should trust is one from an actual load test against your actual application. The estimation above tells you whether you're in the "hundreds" or "thousands" range, which helps with infrastructure planning, but it cannot replace measurement.'''
    ),
    (
        "thinking/advanced-uncertainty-ambiguous-requirements",
        r'''My product manager says we need to "support real-time collaboration" in our document editing app. When I ask for details, they say "like Google Docs." But we're a small team with limited backend experience. Requirements are vague. How do I choose the right technology when I don't fully understand what we're building?''',
        r'''<think>
This is a great example of decision-making under requirement ambiguity. The key challenge: "real-time collaboration like Google Docs" could mean many different things with vastly different implementation complexity:

1. Simple: Show who's online, cursor presence indicators
2. Medium: Live updates when someone saves (polling or simple WebSocket)
3. Hard: Character-by-character live editing with conflict resolution (OT or CRDT)
4. Google-level: All of the above + suggestions, comments, version history, offline support

The technology choice depends enormously on WHERE on this spectrum they actually need to be. And the PM probably doesn't know yet either.

My approach should be:
1. Help them decompose "real-time collaboration" into concrete features
2. Map each feature to complexity/effort
3. Choose technology that supports the CURRENT need but doesn't prevent growth
4. Avoid over-committing to a complex solution before requirements are clear

Technologies to consider:
- Simple presence: WebSockets + Redis pub/sub (straightforward)
- Live document sync: Yjs or Automerge (CRDT libraries) — these handle the hard parts
- Roll your own OT: DON'T — this is extremely complex
- Firebase/Supabase Realtime: managed solution, quick to prototype
- Liveblocks: purpose-built SaaS for collaborative features

For a small team with limited backend experience, I should strongly recommend a managed solution or a high-level library, not building from scratch.
</think>

When requirements are ambiguous, the worst thing you can do is pick a technology based on the most complex interpretation and build for months. Instead, decompose and de-risk.

## Step 1: Decompose "Like Google Docs" Into Concrete Features

"Real-time collaboration" is not one feature. It's a spectrum:

```
Complexity:  Low ──────────────────────────────────────── Extreme

Level 1:    "Who's viewing this document?"
            → Online presence indicators
            → Effort: 1-2 days

Level 2:    "See changes when someone saves"
            → Save-and-refresh sync, no simultaneous editing
            → Effort: 1-2 weeks

Level 3:    "See each other's cursors and selections"
            → Real-time cursor presence
            → Effort: 2-4 weeks

Level 4:    "Edit the same paragraph simultaneously"
            → Conflict resolution (CRDT or OT)
            → Effort: 2-6 months (or 2-4 weeks with a library)

Level 5:    "Full Google Docs: suggestions, comments, offline, version history"
            → Effort: years (Google has 100+ engineers on Docs)
```

**Go back to your PM with this list and ask: "Which of these levels do we need for the MVP?"**

Most PMs, when they see the effort breakdown, realize they need Level 2 or 3 for launch, not Level 4 or 5.

## Step 2: Choose Technology Based on Current Needs + Growth Path

**If you need Level 1-2 (presence + save-based sync):**
```
Technology: WebSockets + any backend you already know
Complexity: Low
Time:       1-2 weeks

// Simple approach with Socket.IO
io.on('connection', (socket) => {
  socket.join(documentId);

  // Presence
  socket.to(documentId).emit('user-joined', { userId });

  // Save-based sync
  socket.on('document-saved', (content) => {
    saveToDatabase(documentId, content);
    socket.to(documentId).emit('document-updated', content);
  });
});
```

**If you need Level 3-4 (cursors + simultaneous editing):**
```
Option A: Yjs (CRDT library) — RECOMMENDED for small teams
  - Handles conflict resolution automatically
  - Works with many editors (TipTap, ProseMirror, Monaco, CodeMirror)
  - Built-in cursor awareness
  - Can use y-websocket for transport
  - Open source, well-documented

Option B: Liveblocks (SaaS)
  - Purpose-built for collaborative features
  - Presence, cursors, conflict-free storage
  - Less control, but dramatically less code
  - Good if you want to minimize backend work

Option C: Build OT/CRDT from scratch
  - DO NOT DO THIS with a small team
  - Google has published papers on this; it took them years
  - Every edge case will eat weeks of debugging
```

## Step 3: The Decision Framework for Ambiguous Requirements

Since you genuinely don't know the final requirements, apply this principle:

**Choose the technology that is:**
1. Adequate for the CURRENT known need (not the imagined future need)
2. Not a dead end (can be extended or replaced without rewriting everything)
3. Within your team's ability to operate and debug

```
Decision matrix for your situation:

                        Fits       Growth    Team can    Debug-
                        MVP?       path?     operate?    gable?
WebSocket + manual sync  Yes(L1-2)  Limited   Yes         Yes
Yjs (CRDT library)       Yes(L1-4)  Good      Moderate    Moderate
Liveblocks (SaaS)        Yes(L1-4)  Good      Yes         Limited
Firebase Realtime        Yes(L1-3)  Moderate  Yes         Limited
Roll your own CRDT       Overkill   N/A       No          No
```

## My Recommendation Given Your Constraints

Small team + limited backend experience + ambiguous requirements:

**Start with Yjs + TipTap (if your editor is rich text):**

```javascript
import * as Y from 'yjs'
import { WebsocketProvider } from 'y-websocket'
import { Editor } from '@tiptap/core'
import Collaboration from '@tiptap/extension-collaboration'
import CollaborationCursor from '@tiptap/extension-collaboration-cursor'

const ydoc = new Y.Doc()
const provider = new WebsocketProvider('ws://localhost:1234', docId, ydoc)

const editor = new Editor({
  extensions: [
    // ... your extensions
    Collaboration.configure({ document: ydoc }),
    CollaborationCursor.configure({ provider }),
  ],
})
// That's it. You now have real-time collaborative editing with cursors.
```

**Why Yjs:**
- Gives you Level 4 capability with Level 2 effort
- If PM decides they only need presence, you've over-built slightly but not wasted months
- If PM decides they need full simultaneous editing, you're already there
- The y-websocket server is a single Node process, easy to operate
- Active community, well-documented

**The meta-lesson:** When requirements are ambiguous, don't try to predict the future. Choose tools that give you the most flexibility per unit of effort, and ship something concrete that the PM can react to. Concrete demos resolve ambiguous requirements faster than any amount of planning.'''
    ),
    (
        "thinking/advanced-uncertainty-failure-prediction",
        r'''We're designing a new event-driven architecture using Kafka, multiple consumer services, and a shared PostgreSQL database. This is our first time with this architecture. What failure modes should we anticipate that we might not have thought of?''',
        r'''<think>
The question asks me to predict failure modes for an architecture I haven't seen in detail. This is inherently uncertain, but event-driven architectures with Kafka have well-known failure categories. Let me systematically think through failure modes by component and interaction.

Kafka-specific failures:
- Consumer lag → backpressure → cascading delays
- Consumer rebalancing storms (frequent restarts or long GC pauses)
- Message ordering violations (partitioning strategy matters)
- Deserialization failures (schema evolution gone wrong)
- Topic compaction deleting messages consumers haven't read

Consumer service failures:
- Poison messages that crash consumers repeatedly
- Non-idempotent processing causing duplicate effects
- Slow consumers causing consumer group rebalancing
- Out-of-order processing when using multiple partitions
- Consumer offset management bugs (processing messages twice or skipping)

Shared PostgreSQL failures:
- Connection pool exhaustion (multiple services competing)
- Lock contention between services writing to same tables
- Write amplification from multiple services
- Schema migration coordination across services
- Inconsistency between Kafka state and DB state

Interaction failures (the hardest to predict):
- Dual-write problem: writing to DB and publishing to Kafka non-atomically
- Event ordering across multiple topics
- Exactly-once semantics being harder than expected
- Monitoring gaps between services

"Shared PostgreSQL" is a particular red flag — this undermines the independence that event-driven architectures are supposed to provide.

I should be transparent that my predictions are based on common patterns, not their specific system, and some issues may not apply while others I can't foresee might emerge.
</think>

Here are the failure modes I'd anticipate, ordered roughly by likelihood and severity. Note that I'm reasoning from common patterns in event-driven systems, so some may not apply to your specific design while others unique to your situation may be missing.

## Critical: The Dual-Write Problem

This is the most common and insidious failure in event-driven architectures, and many teams don't discover it until production.

```
The problem:
  1. Service writes to PostgreSQL         ← succeeds
  2. Service publishes event to Kafka     ← fails (network blip, Kafka down)

  Result: Database is updated, but no event is emitted.
  Downstream consumers never learn about the change.
  Your system is now silently inconsistent.

The reverse is equally bad:
  1. Service publishes event to Kafka     ← succeeds
  2. Service writes to PostgreSQL         ← fails

  Result: Event is emitted for a change that didn't persist.
```

**Solutions (pick one):**
```
Option A: Transactional Outbox (recommended)
  1. Write business data + event record to PostgreSQL in ONE transaction
  2. Separate process polls outbox table and publishes to Kafka
  3. Guarantees: if data is written, event WILL be published

Option B: Change Data Capture (CDC)
  Use Debezium to capture PostgreSQL WAL changes and publish to Kafka
  The database IS the source of truth, events are derived automatically

Option C: Event Sourcing
  Don't write to PostgreSQL at all — Kafka IS the database
  Services materialize views from the event stream
  Most complex, but eliminates dual-write entirely
```

## High Likelihood: Poison Messages

```
Scenario:
  Producer publishes a malformed event (null field, wrong schema, unexpected value)
  Consumer tries to process it → crashes
  Consumer restarts → picks up same message → crashes again
  Infinite crash loop

Your monitoring shows: "Consumer keeps restarting"
But you don't realize it's stuck on ONE bad message.
```

**Mitigation:**
```
Every consumer needs a dead-letter strategy:

try:
    process(message)
    commit_offset(message)
except DeserializationError:
    send_to_dead_letter_topic(message)
    commit_offset(message)  # Skip past the poison message
except ProcessingError as e:
    if message.retry_count > MAX_RETRIES:
        send_to_dead_letter_topic(message)
        commit_offset(message)
    else:
        retry_with_backoff(message)
```

## High Likelihood: Non-Idempotent Consumers

```
Scenario:
  Consumer processes message, charges customer $50
  Consumer crashes BEFORE committing the offset
  Consumer restarts, reprocesses the same message
  Customer is charged $100

  This WILL happen. "At least once" delivery is Kafka's guarantee.
  "Exactly once" requires YOUR code to handle it.
```

**Mitigation:**
```sql
-- Track processed message IDs
CREATE TABLE processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP DEFAULT NOW()
);

-- In your consumer:
-- 1. Check if event_id already processed
-- 2. Process + insert event_id in same transaction
-- 3. Commit Kafka offset
```

## Medium Likelihood: Shared Database Contention

**This is a design smell.** Multiple services writing to the same PostgreSQL database undermines the independence that event-driven architecture is supposed to provide.

```
Problems:
  Service A locks rows in orders table → Service B waits → timeout → retry → storm
  Service A runs migration → Service B's queries break
  Connection pool: 5 services × 20 connections = 100 connections competing
  Performance investigation: "Which service is causing the slow queries?"

         Service A ──┐
         Service B ──┼──→ Shared PostgreSQL  ← contention here
         Service C ──┘
```

**Better approach:**
```
         Service A ──→ Service A's DB
         Service B ──→ Service B's DB    ← each owns its data
         Service C ──→ Service C's DB

         Services communicate via Kafka events, not shared tables
```

If you can't separate databases immediately, at minimum ensure each service owns specific tables and no two services write to the same table.

## Medium Likelihood: Consumer Lag Cascading

```
Timeline:
  t=0:   Spike in events (marketing campaign, batch import)
  t=1:   Consumer falls behind (processing slower than production rate)
  t=5m:  Lag grows to 100,000 messages
  t=10m: Kafka triggers consumer group rebalancing (thinks consumer is stuck)
  t=11m: Rebalancing causes ALL consumers to pause briefly
  t=12m: After rebalance, lag is now worse; some consumers reset to wrong offset
  t=15m: Cascading delays across all downstream services
```

**Mitigation:**
- Monitor consumer lag as a primary metric (not just error rates)
- Set `max.poll.interval.ms` appropriately (don't let it trigger rebalances for normal processing)
- Design consumers to handle bursts (or have autoscaling)
- Consider backpressure mechanisms for upstream producers

## Failure Modes You Might Not Expect

| Failure Mode | What Happens | How to Detect |
|-------------|-------------|---------------|
| Schema evolution breaks consumers | Producer adds field, consumer's deserializer chokes | Schema registry + compatibility checks |
| Partition key skew | 90% of events go to one partition, one consumer drowns | Monitor per-partition lag |
| Clock skew between services | Event ordering assumptions break | Use logical clocks or event sequence numbers |
| Kafka retention expires before consumer catches up | Messages deleted before processing | Monitor lag vs retention period |
| Network partition between app and Kafka | Events queue in local buffer, burst on reconnection | Monitor producer queue depth |

## What I'm Less Certain About

My predictions above are based on common patterns. Factors specific to YOUR system that could introduce different failure modes:
- The nature of your events (size, frequency, schema complexity)
- Whether consumers are stateless or maintain local state
- Your deployment topology (single DC vs multi-region)
- Whether you're using Kafka transactions or manual offset management

**I'd strongly recommend:** before going to production, run a chaos engineering exercise. Kill a consumer mid-processing, kill a Kafka broker, simulate a PostgreSQL failover, and observe what actually breaks. The failure modes you discover will be more valuable than any list I can provide.'''
    ),
    (
        "thinking/advanced-uncertainty-incomplete-monitoring",
        r'''Our production system is experiencing intermittent slowdowns. Response times spike to 5-10 seconds every few hours, then return to normal. We have basic metrics (CPU, memory, request count) but no distributed tracing, no database query monitoring, and limited logging. How do we diagnose this with incomplete data?''',
        r'''<think>
This is a real-world diagnostic problem with incomplete observability. Let me think about how to approach this systematically.

What we know:
- Intermittent (every few hours) — not constant, so it's likely triggered by something periodic
- Spikes to 5-10 seconds — significant, not minor jitter
- Returns to normal — self-resolving, so it's not a resource leak or accumulating problem
- We have: CPU, memory, request count
- We lack: distributed tracing, DB query monitoring, detailed logs

What commonly causes periodic slowdowns:
1. Garbage collection pauses (JVM, .NET, Go to a lesser extent)
2. Database maintenance (autovacuum in PostgreSQL, stats collection)
3. Cron jobs or scheduled tasks consuming resources
4. Connection pool exhaustion and recovery
5. DNS resolution timeouts (often 5 second timeout matches)
6. External service dependencies timing out
7. Cache expiration (thundering herd on cache miss)
8. Log rotation or filesystem operations
9. Background workers competing for resources
10. SSL/TLS certificate validation checking OCSP responders

The "every few hours" pattern strongly suggests something scheduled or periodic. The "returns to normal" pattern suggests it's a bounded event, not a leak.

Diagnostic approach with limited tooling:
1. Correlate timing — does it happen at regular intervals? Same time of day?
2. Check what we CAN see — do CPU/memory spikes correlate with slowdowns?
3. Add lightweight instrumentation — we can add some monitoring without a full tracing deployment
4. Systematic elimination — check the most common causes first

I should be honest about the uncertainty: without proper observability, some of this will be educated guessing, and I should help them prioritize which monitoring to add.
</think>

Diagnosing intermittent issues with limited monitoring is frustrating but doable with a systematic approach. Here's how to work with what you have and strategically add the minimum instrumentation needed.

## Step 1: Characterize the Pattern with What You Have

Before adding any tooling, extract maximum signal from existing data.

```bash
# Correlate timing: are slowdowns periodic?
# Export your metrics and look for patterns

# Check if spikes happen at regular intervals
# Every 1 hour → likely a cron job
# Every 4 hours → possibly log rotation, scheduled task
# Random but clustered → possibly GC, cache expiry, or external dependency

# Check if CPU or memory spike DURING the slowdown
# CPU spikes → compute-bound cause (GC, background job, query)
# Memory spikes → allocation pressure, GC trigger
# Neither spikes → waiting on something external (DB, network, external API)
```

**The most critical question:** Do CPU/memory correlate with the slowdowns?

| CPU during slowdown | Memory during slowdown | Likely cause |
|--------------------|-----------------------|-------------|
| Spikes high | Stable | CPU-bound: background job, expensive computation |
| Spikes high | Also spikes | GC pressure, memory-intensive operation |
| Normal | Normal | Blocked on I/O: database, external service, DNS |
| Normal | Spikes then drops | GC pause (allocate, then collect) |

## Step 2: Check the Usual Suspects (No New Tools Needed)

```bash
# 1. Cron jobs — the #1 cause of periodic slowdowns
crontab -l
ls /etc/cron.d/
ls /etc/cron.hourly/
# Look for anything running every few hours

# 2. Database maintenance (if PostgreSQL)
# Autovacuum runs periodically and can cause I/O spikes
# Check if you can access pg_stat_activity even briefly
psql -c "SELECT pid, state, query, wait_event_type, wait_event
         FROM pg_stat_activity
         WHERE state != 'idle'
         ORDER BY query_start;"

# 3. Check for log rotation
ls -la /var/log/*.gz    # Recent rotations
cat /etc/logrotate.conf  # Rotation schedule

# 4. DNS issues (5-second timeout is a telltale sign)
# If your slowdowns are consistently ~5 seconds, DNS is a strong suspect
# The default DNS timeout on Linux is 5 seconds
cat /etc/resolv.conf    # Check DNS configuration
```

## Step 3: Add Minimum Viable Monitoring

You don't need full distributed tracing to diagnose this. Add targeted instrumentation.

```python
# Add this to your application — lightweight request timing with context
import time
import logging

logger = logging.getLogger('slowrequest')

class SlowRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)
        duration = time.monotonic() - start

        if duration > 2.0:  # Log any request over 2 seconds
            logger.warning(
                "SLOW REQUEST: %.2fs | %s %s | status=%s",
                duration, request.method, request.path,
                response.status_code,
                extra={
                    'duration': duration,
                    'path': request.path,
                    'method': request.method,
                }
            )
        return response
```

```python
# Add database query timing (even without full monitoring)
import logging
from django.db import connection

# In Django settings:
LOGGING = {
    'loggers': {
        'django.db.backends': {
            'level': 'WARNING',  # Only log slow queries
        },
    },
}

# Or add a simple query counter per request:
class QueryCountMiddleware:
    def __call__(self, request):
        from django.db import reset_queries
        reset_queries()

        response = self.get_response(request)

        queries = connection.queries
        if len(queries) > 20 or sum(float(q['time']) for q in queries) > 1.0:
            logger.warning(
                "HEAVY DB: %d queries, %.2fs total | %s",
                len(queries),
                sum(float(q['time']) for q in queries),
                request.path
            )
        return response
```

## Step 4: Set a Trap for the Next Occurrence

Since the issue is intermittent, set up monitoring that captures state DURING the slowdown.

```bash
# Create a script that runs every minute and captures system state
# when response times are elevated

cat > /opt/diagnose_slowdown.sh << 'BASHEOF'
#!/bin/bash
# Check if app is responding slowly
RESPONSE_TIME=$(curl -o /dev/null -s -w '%{time_total}' http://localhost:8000/health)

if (( $(echo "$RESPONSE_TIME > 3.0" | bc -l) )); then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    DIR="/var/log/slowdown_captures/${TIMESTAMP}"
    mkdir -p "$DIR"

    # Capture everything we can
    ps aux > "$DIR/processes.txt"
    top -b -n 1 > "$DIR/top.txt"
    ss -tlnp > "$DIR/connections.txt"
    iostat -x 1 3 > "$DIR/iostat.txt"
    vmstat 1 5 > "$DIR/vmstat.txt"

    # Database state (if accessible)
    psql -c "SELECT * FROM pg_stat_activity WHERE state != 'idle'" > "$DIR/pg_activity.txt" 2>/dev/null

    # Network state
    ss -s > "$DIR/socket_stats.txt"

    echo "Captured slowdown data at $TIMESTAMP (response time: ${RESPONSE_TIME}s)"
fi
BASHEOF

chmod +x /opt/diagnose_slowdown.sh
# Run every minute via cron
echo "* * * * * /opt/diagnose_slowdown.sh" | crontab -
```

## Step 5: Interpret What You Find

**If the capture shows high I/O wait:**
```
→ Likely database or disk issue
→ Check for autovacuum, large sequential scans, or log rotation
→ Next step: enable pg_stat_statements for query-level monitoring
```

**If the capture shows many connections in TIME_WAIT:**
```
→ Connection pool exhaustion
→ An external service is slow, causing connections to pile up
→ Next step: check which external endpoints are timing out
```

**If the capture shows a specific process consuming CPU:**
```
→ Background job or scheduled task
→ Check if it's your app process (GC? expensive computation?) or system process
→ Next step: schedule the job during off-peak or throttle it
```

**If the capture shows nothing unusual:**
```
→ The problem might be outside this server (load balancer, CDN, DNS, external API)
→ Next step: add timing for every external call your app makes
```

## What I Cannot Determine Without More Data

I want to be transparent about the limits of remote diagnosis:
- I cannot tell you whether this is a database, application, or infrastructure issue without seeing the correlation data
- The "every few hours" pattern could be 10 different root causes
- My list of suspects is ordered by probability, not certainty

**The single highest-value action:** deploy the slow-request middleware and the capture script, wait for 2-3 occurrences, and look at the captured data. That will narrow the possibilities from "almost anything" to 1-2 likely causes.'''
    ),
    (
        "thinking/advanced-uncertainty-refactoring-risk",
        r'''We have a 4-year-old Django monolith with about 200K lines of code, minimal tests (roughly 15% coverage), and we want to do a major refactoring of the core data models. Our CTO is asking me to assess the risk. How do I evaluate the risk of this refactoring when I can only partially understand the system?''',
        r'''<think>
This is a question about evaluating risk under deep uncertainty. The key challenge: with a 200K line codebase at 15% test coverage, there's a lot of unknown behavior that could break.

Let me think about what makes this risky:
1. 200K lines means extensive surface area for breakage
2. 15% test coverage means 85% of behavior is unguarded — changes could silently break things
3. Core data models are the foundation — everything depends on them
4. 4 years old means accumulated implicit dependencies, undocumented assumptions, edge cases in production
5. "Major refactoring" is vague — the scope matters enormously

Risk dimensions:
- Technical risk: Will it break things? How many things?
- Business risk: Will it cause outages, data loss, customer impact?
- Timeline risk: Will it take much longer than estimated?
- Team risk: Do the developers understand the system well enough?
- Opportunity cost: What features aren't being built during the refactoring?

I should help them think about:
1. How to assess what they don't know (the unknown unknowns)
2. Strategies to reduce risk before committing
3. How to scope the refactoring to manage risk
4. What signals indicate they should stop or change approach

I should be honest that this is genuinely risky and help them quantify it rather than just saying "it'll be fine" or "don't do it."
</think>

This is genuinely high-risk, and I want to help you assess it honestly rather than provide false reassurance. Here's a structured risk evaluation framework.

## Risk Assessment Summary

| Risk Dimension | Level | Key Factor |
|---------------|-------|-----------|
| Silent breakage | **HIGH** | 85% of behavior has no test coverage |
| Data corruption | **HIGH** | Core model changes can corrupt existing data |
| Timeline overrun | **HIGH** | 4-year-old systems have hidden complexity |
| Partial understanding | **HIGH** | No one person understands all 200K lines |
| Business disruption | **MEDIUM-HIGH** | Depends on deployment strategy |
| Team morale | **MEDIUM** | Long refactoring efforts are demoralizing |

**My overall assessment: This is a high-risk effort that will likely take 2-3x longer than estimated.** That doesn't mean don't do it — but go in with eyes open.

## Why 15% Test Coverage Makes This Especially Dangerous

```
What tests do during a refactoring:

  200K lines of code
  ┌──────────────────────────────────────────────────┐
  │                                                  │
  │   ████████  Tested (15%) — you'll know if these  │
  │              break immediately                   │
  │                                                  │
  │   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │
  │   Untested (85%) — breakage is SILENT            │
  │   You find out when customers report bugs        │
  │   or when data is already corrupted              │
  │                                                  │
  └──────────────────────────────────────────────────┘
```

With core data model changes, the untested 85% is where the worst bugs hide: broken queries, incorrect data transformations, subtle logic errors that produce wrong results without raising exceptions.

## How to Assess What You Don't Know

**1. Map the blast radius of the data models you're changing:**

```bash
# Find every file that imports or references the models you're changing
grep -r "from.*models import.*YourModel" --include="*.py" -l | wc -l
grep -r "YourModel" --include="*.py" -l | wc -l
grep -r "your_model_table" --include="*.py" --include="*.sql" -l | wc -l

# Check for raw SQL that won't be caught by ORM changes
grep -r "SELECT.*FROM.*your_table" --include="*.py" -l
grep -r "your_column_name" --include="*.py" -l
```

If a model is referenced in 20 files, the risk is manageable. If it's referenced in 200 files, the blast radius is enormous.

**2. Identify implicit dependencies you probably don't know about:**

```python
# Things that break silently during model changes:

# Django signals — triggered by model operations, often in distant files
from django.db.models.signals import post_save
# Search for: post_save.connect, pre_save.connect, etc.

# Celery tasks that query these models
# Search for: YourModel.objects in tasks.py files

# Management commands
# Search for: YourModel in management/commands/

# Template filters and tags that assume model structure
# Search for: model field names in templates

# Third-party integrations (webhooks, exports, API serializers)
# Search for: model references in serializers.py, views.py

# Database views, triggers, or stored procedures
# Check: psql -c "\dv" and psql -c "\df"
```

**3. Check for hardcoded assumptions:**

```python
# These are the bugs that won't raise exceptions but produce wrong results:

# Hardcoded field names in dictionary access
data['old_field_name']  # KeyError only if accessed, silent if conditional

# Assumptions about field types
if model.status == 1:  # What if status changes from int to string?

# Assumptions about relationships
model.related_thing.name  # What if the FK changes?

# Cached or denormalized data
# Changing the source model doesn't update denormalized copies
```

## Risk Reduction Strategies (Before You Commit)

**Strategy 1: Write characterization tests first (2-4 weeks investment)**

```python
# Before changing anything, write tests that capture CURRENT behavior
# These aren't testing correctness — they're capturing "what happens now"

class CharacterizationTests(TestCase):
    def test_order_creation_flow(self):
        """Capture current behavior of order creation."""
        # Set up data as it exists in production
        # Walk through the critical business flows
        # Assert on actual outputs (even if they seem wrong)
        # These tests will tell you WHEN behavior changes

    def test_invoice_calculation(self):
        """Capture current invoice math."""
        # Use production-like data
        # Assert exact outputs
```

This takes time upfront but converts unknown risk into known risk. When your refactoring breaks a characterization test, you can evaluate whether the behavior change is intentional or a bug.

**Strategy 2: Strangler Fig pattern instead of big-bang refactoring**

```
Instead of:
  "Rewrite core models in one big effort"

Do:
  1. Create new models alongside old ones
  2. New code writes to both old and new models
  3. Gradually migrate reads to new models
  4. Once all reads use new models, remove old ones

  ┌──────────────┐     ┌──────────────┐
  │  Old Models   │ ←── │ Legacy Code   │  (still works)
  │              │     └──────────────┘
  │              │
  │  New Models   │ ←── │  New Code     │  (gradually takes over)
  │              │     └──────────────┘
  └──────────────┘
```

This is slower but dramatically safer. You can deploy incrementally and roll back if problems emerge.

**Strategy 3: Data migration dry runs**

```bash
# Before touching production:
# 1. Take a production database snapshot
# 2. Run your migration on the snapshot
# 3. Run your full test suite against the migrated data
# 4. Manually verify critical business flows
# 5. Check for data inconsistencies

# Critical: compare row counts before and after
psql -c "SELECT 'before', count(*) FROM your_table;"
# Run migration
psql -c "SELECT 'after', count(*) FROM your_table;"
# Any difference = data loss risk
```

## What to Tell Your CTO

Frame the assessment honestly:

> **Risk level: HIGH.** The combination of core model changes, low test coverage, and a large codebase means there is significant probability of production bugs that we won't catch before deployment.
>
> **Timeline risk: Expect 2-3x the initial estimate.** Historical data on large-codebase refactoring consistently shows underestimation.
>
> **Risk mitigation is possible but requires upfront investment:**
> - 2-4 weeks of characterization testing before we start
> - Strangler fig approach instead of big-bang rewrite
> - Database migration dry runs on production snapshots
>
> **The alternative to evaluate:** Is the refactoring truly necessary, or can we achieve 80% of the benefit with smaller, targeted improvements to the worst pain points?

The last question is important. "Major refactoring of core data models" should be a last resort, not a first choice. Often the actual pain comes from 2-3 specific design flaws that can be addressed individually with much less risk.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
