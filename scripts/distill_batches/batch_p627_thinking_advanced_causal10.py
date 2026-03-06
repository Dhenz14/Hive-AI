"""Phase 2E: Advanced Reasoning — Causal & Counterfactual Analysis (Part 10)"""

PAIRS = [
    (
        "thinking/causal-api-latency-spikes",
        "Our API latency spikes from 50ms to 2-3 seconds every 5 minutes, exactly. It's incredibly regular. Between spikes, performance is perfect. What could cause such a regular pattern?",
        r'''<think>
Exactly every 5 minutes — this is the key diagnostic clue. Regular, periodic problems point to scheduled operations.

**Causal hypothesis: scheduled task or cron job**
Something runs every 5 minutes that competes for resources:
1. Health checks that are too heavy (full system check every 5 min)
2. Cache refresh/invalidation (clearing and rebuilding cache)
3. Log rotation or cleanup job
4. Metrics collection that queries the database
5. Scheduled database maintenance (autovacuum, analyze)
6. Background sync job (sync data with external service)

**Causal hypothesis: garbage collection**
Some GC implementations trigger at regular intervals under stable allocation patterns. But GC pauses are usually milliseconds, not 2-3 seconds. Less likely unless using Java with massive heap.

**Causal hypothesis: connection pool recycling**
Some connection pools recycle all connections on a timer. If all connections are recycled at once, reconnection overhead causes latency.

**Causal hypothesis: SSL/TLS certificate validation**
CRL or OCSP checks happening on a timer.

**Most likely: a scheduled job that locks shared resources**

The "exactly every 5 minutes" is too precise to be random. It's definitely something on a cron-like schedule.

**Diagnostic approach:**
1. Check crontab for 5-minute jobs
2. Check app-level schedulers (Celery beat, APScheduler, setInterval)
3. Look at database slow query log during the spike
4. Look at CPU/memory during the spike
5. Check if the spike duration varies (suggests variable workload of scheduled job)

**Counterfactual:**
- If I disable the scheduled jobs one at a time, which one makes the spikes disappear?
- If I move the scheduled job to a separate instance, do spikes disappear on the API instance?
</think>

"Every 5 minutes, exactly" is the key diagnostic. This is definitely a **scheduled task competing for resources**.

## Diagnosis: What Runs Every 5 Minutes?

```bash
# CHECK 1: System cron
crontab -l
cat /etc/cron.d/*
# Look for: */5 * * * * anything

# CHECK 2: Application schedulers
grep -rn "300\|5.*minute\|cron\|schedule\|interval" --include="*.py" --include="*.js" --include="*.yml"
# Look for: setInterval(fn, 300000), schedule.every(5).minutes, @periodic_task

# CHECK 3: Database activity during spike
# PostgreSQL:
SELECT query, state, wait_event, query_start
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start;
# Run this DURING a spike — what queries are running?

# CHECK 4: System resources during spike
# Set up monitoring to capture the moment:
while true; do
    echo "$(date): $(ps aux --sort=-%cpu | head -5)" >> /tmp/spike_monitor.log
    sleep 5
done
# Check log during spike — what process spikes CPU?
```

## Common Culprits (Ranked by Likelihood)

### 1. Heavy Scheduled Query (Most Common)

```python
# ❌ This runs every 5 minutes and locks the database:
@celery.task
@app.on_event("startup")
def refresh_dashboard_cache():
    """Runs every 5 minutes — but takes 2-3 seconds and locks tables"""
    results = db.execute("""
        SELECT u.name, COUNT(o.id), SUM(o.total)
        FROM users u
        JOIN orders o ON o.user_id = u.id
        GROUP BY u.id
        ORDER BY SUM(o.total) DESC
        LIMIT 100
    """)  # Full table scan + aggregation = locks + CPU spike
    cache.set("dashboard", results, ttl=300)

# While this runs:
#   - Database CPU spikes
#   - Table locks block other queries
#   - API requests waiting for DB = 2-3 second latency

# ✅ FIX: run on a READ REPLICA, not the primary database
@celery.task
def refresh_dashboard_cache():
    results = read_replica_db.execute("""...""")  # Doesn't affect primary
    cache.set("dashboard", results, ttl=300)

# ✅ FIX: optimize the query (add indexes, limit scope)
# ✅ FIX: run on a separate worker instance (not the API server)
```

### 2. Cache Stampede

```python
# ❌ Cache expires every 5 minutes, ALL requests miss simultaneously
cache.set("products", products, ttl=300)  # 5 minutes

# At t=300s: cache expires
# Next 100 requests ALL see cache miss
# All 100 hit the database simultaneously → spike

# ✅ FIX: staggered TTL (jitter)
import random
ttl = 300 + random.randint(-30, 30)  # 270-330 seconds
cache.set("products", products, ttl=ttl)

# ✅ FIX: background refresh before expiry
@celery.task
def refresh_products_cache():
    products = db.query_products()
    cache.set("products", products, ttl=600)  # Long TTL

# Celery beat: refresh every 4 minutes (before the 10-min TTL expires)
# Cache NEVER expires — always refreshed before TTL
```

### 3. Connection Pool Recycling

```python
# ❌ All connections recycled simultaneously
engine = create_engine(
    "postgresql://...",
    pool_recycle=300,  # Recycle connections every 5 minutes
)
# At t=300: ALL pool connections close and reconnect
# Reconnection: ~50ms per connection × 20 connections = blocking

# ✅ FIX: stagger recycling
engine = create_engine(
    "postgresql://...",
    pool_recycle=3600,  # Recycle every hour (not 5 min)
    pool_pre_ping=True, # Validate connections before use
)
```

## Diagnostic Decision Tree

```
Every 5 minutes, exactly:
  │
  ├─ Check crontab → found a */5 job?
  │   └─ YES → that's your culprit. Move to separate instance or optimize.
  │
  ├─ Check app schedulers → found a 300s interval?
  │   └─ YES → is it doing heavy DB/CPU work?
  │       └─ YES → optimize or move to read replica / background worker
  │
  ├─ Check database → slow queries during spike?
  │   └─ YES → autovacuum or analytics query running on schedule
  │       └─ FIX: move to read replica, optimize, or schedule during off-hours
  │
  └─ Check infrastructure → K8s health probes? Load balancer checks?
      └─ Heavy health checks every 5 min → make health checks lightweight

Counterfactual verification:
  Disable suspected job → spikes disappear → confirmed.
  Re-enable with fix → spikes stay gone → root cause resolved.
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
