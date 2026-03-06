"""Phase 4A: Self-Improvement -- Training Data Generation (Part 3)

Teaching the model to generate high-quality training pairs for debugging skills.
Each pair asks the model to CREATE training data and explains why each generated pair
is effective, building the meta-skill of self-improvement through data generation.
"""

PAIRS = [
    (
        "thinking/auto-datagen-debug-memory-leaks",
        r'''Generate 3 high-quality training pairs that teach how to debug memory leaks. For each pair, explain why it's effective training data.''',
        r'''<think>
For debugging memory leaks, the progression should be:
1. Beginner: Understanding what a memory leak IS in a garbage-collected language and basic detection
2. Intermediate: Using profiling tools to identify the source -- tracemalloc in Python, heap snapshots in Node
3. Advanced: Subtle leaks from closures, event listeners, and caching without bounds

The key misconception is that garbage-collected languages "can't have memory leaks." They can -- any reference you hold prevents garbage collection. I need to show realistic leak patterns, not contrived examples.
</think>

Here are 3 training pairs for teaching how to debug memory leaks:

**Pair 1 (Beginner):**
```
Q: My Python web server's memory usage keeps growing. It starts at 200MB and after a few hours hits 4GB and gets killed by the OS. I thought Python has garbage collection -- how can it have a memory leak?

A: Python's garbage collector frees objects when nothing references them. A "memory leak" in Python means your code is keeping references to objects you no longer need, preventing the GC from reclaiming them.

Common causes:
1. **Growing collections:** Appending to a list or dict that's never cleaned up
2. **Caches without size limits:** Storing every result forever
3. **Circular references with __del__:** Objects referencing each other that define finalizers
4. **Global state accumulation:** Module-level variables that grow over time

Quick diagnosis -- add this to your app:

import tracemalloc
import signal

tracemalloc.start()

def dump_memory(signum, frame):
    snapshot = tracemalloc.take_snapshot()
    stats = snapshot.statistics('lineno')
    print("\n--- Top 10 memory consumers ---")
    for stat in stats[:10]:
        print(stat)

# Send SIGUSR1 to the process to dump memory stats
signal.signal(signal.SIGUSR1, dump_memory)

Now send `kill -USR1 <pid>` to your running server. The output shows which lines of code allocated the most memory:

--- Top 10 memory consumers ---
/app/services/analytics.py:45: size=1.8 GiB, count=2400000
/app/middleware/logging.py:12: size=800 MiB, count=5000000

Line 45 of analytics.py is holding 1.8GB. Go look at what that line is accumulating.

The most common pattern is something like:

# In analytics.py
results_cache = {}  # Module-level dict that grows forever

def get_analytics(user_id):
    if user_id not in results_cache:
        results_cache[user_id] = expensive_computation(user_id)
    return results_cache[user_id]

Fix: Use an LRU cache with a size limit, or add TTL-based expiration.
```
**Why this is effective:** It directly addresses the "but Python has GC" misconception. The tracemalloc + signal approach is a production-ready debugging technique that works on running servers without restarting. The common cause (unbounded dict) is immediately recognizable and fixable.

**Pair 2 (Intermediate):**
```
Q: I used tracemalloc and found that memory is being allocated in my WebSocket handler, but I can't see exactly what's being retained. Memory grows by ~50MB per hour. How do I find what objects are accumulating and what's holding references to them?

A: Use objgraph to visualize reference chains -- it shows you WHY objects can't be garbage collected:

pip install objgraph

# Add a diagnostic endpoint to your app:
import objgraph
import gc

@app.get("/debug/memory")
def debug_memory():
    gc.collect()  # Force garbage collection first

    # What types of objects are most common?
    objgraph.show_most_common_types(limit=15)
    # Output: dict 125000, list 98000, WebSocketSession 45000, ...

    # 45,000 WebSocketSession objects? That's suspicious if you have 100 users.
    # Find what's holding references to them:
    sessions = objgraph.by_type('WebSocketSession')
    if sessions:
        objgraph.show_backrefs(
            sessions[-1],  # Pick one instance
            max_depth=5,
            filename='/tmp/session_refs.png'  # Generates a reference graph
        )

    # Growth between snapshots (call this endpoint twice, 5 min apart):
    objgraph.show_growth(limit=10)
    # Output:
    # WebSocketSession  45000  +500
    # dict              125000 +1500
    # function          23000  +500

The reference graph image shows the chain: some global list or event handler is holding references to closed WebSocket sessions.

Typical finding:

class WebSocketHandler:
    active_connections = []  # Class variable shared across all instances

    async def on_connect(self, ws):
        self.active_connections.append(ws)

    async def on_disconnect(self, ws):
        pass  # Forgot to remove from the list!

Fix:
    async def on_disconnect(self, ws):
        self.active_connections.remove(ws)

Or better, use a WeakSet that automatically drops references when objects are garbage collected:

from weakref import WeakSet

class WebSocketHandler:
    active_connections = WeakSet()

For periodic monitoring in production, log the output of objgraph.show_growth() every 10 minutes to a file. If any type shows consistent growth, that's your leak.
```
**Why this is effective:** It goes beyond "find the allocation" (tracemalloc) to "find the retention" (objgraph), which is the harder and more important skill. The reference graph visualization makes the abstract concept of "what's holding a reference" concrete. The WeakSet solution teaches a standard library tool designed for exactly this problem.

**Pair 3 (Advanced):**
```
Q: I have a subtle memory leak in a Node.js service. Heap snapshots show growing numbers of "Detached DOM trees" or "(closure)" entries, but I can't pinpoint the source. The leak is slow -- about 10MB/hour -- and only appears under production load, not in my test environment. How do I debug this?

A: Slow leaks that only appear under load are typically caused by closures capturing variables unintentionally, or event listeners that aren't cleaned up. Here's a systematic approach:

**Step 1: Take heap snapshots under load**
Use Chrome DevTools remotely. Start Node with --inspect:

node --inspect=0.0.0.0:9229 server.js

Connect Chrome DevTools, go to Memory tab. Take Snapshot 1, wait 10 minutes under load, take Snapshot 2. Use "Comparison" view to see what was allocated between snapshots.

**Step 2: Look for closure leaks**
The most insidious leak pattern in Node.js:

function createHandler(db) {
    const cache = {};          // Intended to be short-lived
    const largeConfig = loadConfig();  // 5MB config object

    return function handler(req, res) {
        // This closure captures EVERYTHING in createHandler's scope
        // Even if handler never uses largeConfig, V8 may retain it
        // because it shares the scope with cache
        cache[req.url] = processRequest(req);
        res.json(cache[req.url]);
    };
}

// Called once per worker, but cache grows unbounded
app.get('/data', createHandler(db));

The cache object grows forever because the closure keeps it alive. Fix: bound the cache.

const LRU = require('lru-cache');

function createHandler(db) {
    const cache = new LRU({ max: 1000 });  // Bounded

    return function handler(req, res) {
        if (!cache.has(req.url)) {
            cache.set(req.url, processRequest(req));
        }
        res.json(cache.get(req.url));
    };
}

**Step 3: Find event listener leaks**
Node warns when >10 listeners are added to an emitter. But many libraries suppress this warning. Audit manually:

// Leak: adding a listener on every request, never removing it
app.post('/webhook', (req, res) => {
    const handler = (event) => {
        if (event.id === req.body.id) {
            // process event
        }
    };
    eventBus.on('update', handler);  // Listener added every request
    // handler closure captures req -- entire request object stays in memory
    res.send('ok');
});

// Fix: use once() or explicitly remove the listener
app.post('/webhook', (req, res) => {
    const handler = (event) => {
        if (event.id === req.body.id) {
            eventBus.off('update', handler);  // Clean up
            // process event
        }
    };
    eventBus.on('update', handler);
    // Also set a timeout to remove if event never arrives
    setTimeout(() => eventBus.off('update', handler), 30000);
    res.send('ok');
});

**Step 4: Reproduce under load in staging**
If it only appears under production load, create a load test that simulates the traffic pattern:

# Use autocannon or k6 to generate sustained load
npx autocannon -c 100 -d 3600 http://localhost:3000/data

Monitor process.memoryUsage().heapUsed every 60 seconds and plot it. A leak shows as a monotonically increasing line. Compare with/without specific endpoints to isolate the leaking route.

**Step 5: Use --expose-gc for controlled experiments**
node --expose-gc server.js

In your diagnostic endpoint: global.gc(); followed by process.memoryUsage(). If memory drops significantly after forced GC, you don't have a leak -- you have delayed collection. If it doesn't drop, the references are genuinely retained.
```
**Why this is effective:** It covers the complete debugging workflow (snapshots, isolation, reproduction, verification) rather than just one tool. The closure leak and event listener leak are the two most common sources of real-world Node.js memory leaks. The forced GC test in Step 5 is a crucial diagnostic that separates "real leak" from "GC hasn't run yet."

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-debug-race-conditions",
        r'''Generate 3 high-quality training pairs that teach how to debug race conditions. For each pair, explain why it's effective training data.''',
        r'''<think>
For race conditions:
1. Beginner: What a race condition is, with a counter example that fails under concurrency
2. Intermediate: Debugging a race condition in a web app (double-submit, inventory overselling)
3. Advanced: Using tools and techniques to detect races -- thread sanitizers, stress testing, deterministic replay

Race conditions are notoriously hard to reproduce. I need to teach both the conceptual understanding and practical debugging techniques.
</think>

Here are 3 training pairs for teaching how to debug race conditions:

**Pair 1 (Beginner):**
```
Q: I have a function that increments a counter in a file. When I run it from multiple threads, the final count is wrong -- I expect 1000 but I get numbers like 987 or 993. What's happening?

import threading

def increment_counter():
    with open("counter.txt") as f:
        count = int(f.read())
    count += 1
    with open("counter.txt", "w") as f:
        f.write(str(count))

threads = [threading.Thread(target=increment_counter) for _ in range(1000)]
for t in threads: t.start()
for t in threads: t.join()

A: This is a classic race condition -- a bug that occurs when multiple threads access shared state without coordination. Here's what happens:

Thread A reads counter.txt -> sees 42
Thread B reads counter.txt -> also sees 42 (A hasn't written yet)
Thread A writes 43
Thread B writes 43 (should be 44, but B based its work on stale data)

One increment was lost. This is called a "lost update" or "read-modify-write" race.

The read -> modify -> write sequence is NOT atomic (indivisible). Between the read and write, another thread can interleave.

**Fix: Use a lock to make the operation atomic:**

lock = threading.Lock()

def increment_counter():
    with lock:  # Only one thread can be inside this block at a time
        with open("counter.txt") as f:
            count = int(f.read())
        count += 1
        with open("counter.txt", "w") as f:
            f.write(str(count))

The lock ensures the entire read-modify-write happens as one uninterruptible unit. While Thread A holds the lock, Thread B waits.

**Why the bug is intermittent:** If threads happen to run sequentially (due to OS scheduling), the bug doesn't appear. It only manifests when two threads execute the read step before either executes the write step. This makes race conditions extremely hard to reproduce -- they may appear only under heavy load or on faster machines with more parallelism.

A better architecture for this specific case: use an atomic operation instead of read-modify-write. For example, a database with UPDATE counter SET value = value + 1 is atomic, or use threading.atomic (Python doesn't have this, but other languages do).
```
**Why this is effective:** The step-by-step interleaving diagram makes the invisible problem visible. Explaining WHY it's intermittent addresses the "but it works on my machine" confusion that makes race conditions so frustrating. The lock fix is immediate, and the "better architecture" hint points toward the deeper principle of designing for concurrency.

**Pair 2 (Intermediate):**
```
Q: Our e-commerce site sometimes sells more items than we have in stock. The inventory check looks correct:

def purchase(product_id, quantity):
    product = db.query("SELECT stock FROM products WHERE id = %s", product_id)
    if product.stock >= quantity:
        db.execute("UPDATE products SET stock = stock - %s WHERE id = %s", quantity, product_id)
        create_order(product_id, quantity)
        return "Success"
    return "Out of stock"

We have 5 units in stock but sometimes 6 orders go through. How is this possible?

A: Same race condition pattern as before, but at the database level:

Request A: SELECT stock -> sees 5, checks 5 >= 1 -> true
Request B: SELECT stock -> sees 5 (A hasn't updated yet), checks 5 >= 1 -> true
Request A: UPDATE stock = 5 - 1 = 4
Request B: UPDATE stock = 4 - 1 = 3  (should have been rejected!)

Both requests passed the check because they read the same stale value.

**Fix 1: Pessimistic locking (SELECT FOR UPDATE)**

def purchase(product_id, quantity):
    with db.transaction():
        # FOR UPDATE locks the row -- other transactions wait here
        product = db.query(
            "SELECT stock FROM products WHERE id = %s FOR UPDATE", product_id
        )
        if product.stock >= quantity:
            db.execute("UPDATE products SET stock = stock - %s WHERE id = %s",
                       quantity, product_id)
            create_order(product_id, quantity)
            return "Success"
        return "Out of stock"

SELECT FOR UPDATE locks the row for the duration of the transaction. Request B blocks at the SELECT until Request A commits or rolls back.

**Fix 2: Optimistic locking (conditional UPDATE)**

def purchase(product_id, quantity):
    result = db.execute(
        "UPDATE products SET stock = stock - %s WHERE id = %s AND stock >= %s",
        quantity, product_id, quantity
    )
    if result.rowcount == 1:
        create_order(product_id, quantity)
        return "Success"
    return "Out of stock"

This combines the check and update into a single atomic SQL statement. If stock < quantity, the WHERE clause doesn't match and rowcount is 0. No separate SELECT needed.

**Fix 2 is preferred for high-traffic scenarios** because it doesn't hold locks. Multiple requests can attempt the UPDATE simultaneously -- the database ensures atomicity at the row level.

**Fix 3: For extreme traffic (flash sales), use a queue:**
Don't let concurrent requests hit the database at all. Put purchase requests into a queue and process them sequentially. This is the pattern used by ticketing systems.
```
**Why this is effective:** It connects the abstract "race condition" concept to a concrete business impact (overselling inventory). The three fixes represent different points on the pessimistic/optimistic spectrum, teaching the learner to choose based on traffic patterns. Fix 2 (atomic conditional UPDATE) is the pragmatic solution most teams should use.

**Pair 3 (Advanced):**
```
Q: We have an intermittent bug in our Go microservice that causes data corruption about once a week under production load. We suspect a race condition but can't reproduce it locally. The service has ~50 goroutines and uses shared maps. How do we systematically find and fix this?

A: Go's race detector and disciplined testing are your best tools here. Here's the systematic approach:

**Step 1: Run with the race detector**
Go has a built-in race detector that instruments memory accesses:

go build -race -o myservice ./cmd/server
./myservice  # Runs with race detection enabled (~10x slower, 5-10x more memory)

When a race is detected, you get a report:

WARNING: DATA RACE
Read at 0x00c000126000 by goroutine 15:
  myapp/handlers.(*Server).handleRequest()
      /app/handlers/api.go:142 +0x1a4

Previous write at 0x00c000126000 by goroutine 23:
  myapp/handlers.(*Server).updateCache()
      /app/handlers/api.go:178 +0x2c8

Goroutine 15 (running) created at:
  ...

This tells you exactly: goroutine 15 reads a variable at api.go:142 while goroutine 23 writes it at api.go:178, without synchronization.

**Step 2: The likely culprit -- unsynchronized map access**
In Go, maps are NOT concurrency-safe. This crashes (or corrupts silently):

// UNSAFE: concurrent map read/write
type Server struct {
    cache map[string]Result  // Shared across goroutines
}

func (s *Server) handleRequest(key string) Result {
    if val, ok := s.cache[key]; ok {  // Read
        return val
    }
    result := s.compute(key)
    s.cache[key] = result  // Write -- RACE with above read
    return result
}

**Fix option A: sync.RWMutex (read-heavy workloads)**
type Server struct {
    cache map[string]Result
    mu    sync.RWMutex
}

func (s *Server) handleRequest(key string) Result {
    s.mu.RLock()
    if val, ok := s.cache[key]; ok {
        s.mu.RUnlock()
        return val
    }
    s.mu.RUnlock()

    result := s.compute(key)

    s.mu.Lock()
    s.cache[key] = result
    s.mu.Unlock()
    return result
}

RLock allows multiple concurrent readers. Lock is exclusive for writes.

**Fix option B: sync.Map (simpler, built for this)**
type Server struct {
    cache sync.Map  // Concurrency-safe, no mutex needed
}

func (s *Server) handleRequest(key string) Result {
    if val, ok := s.cache.Load(key); ok {
        return val.(Result)
    }
    result := s.compute(key)
    s.cache.Store(key, result)
    return result
}

**Step 3: Stress test to validate the fix**

// In your test file:
func TestHandleRequestConcurrent(t *testing.T) {
    server := NewServer()
    var wg sync.WaitGroup

    for i := 0; i < 1000; i++ {
        wg.Add(1)
        go func(id int) {
            defer wg.Done()
            key := fmt.Sprintf("key-%d", id%10)  // Deliberate contention on 10 keys
            server.handleRequest(key)
        }(i)
    }
    wg.Wait()
}

Run with: go test -race -count=100 ./... (run 100 times to catch intermittent races)

**Step 4: Prevent future races with CI**
Add to your CI pipeline:

go test -race -timeout 300s ./...

This runs ALL tests with race detection. Any race condition hit during any test fails the build. This is the single most effective prevention measure for Go codebases.

**Why once-a-week in production:** Race conditions depend on precise timing. Under light load, goroutines rarely execute the critical section simultaneously. Under heavy load, the probability increases. Running with -race in staging under realistic load would have caught this.
```
**Why this is effective:** It provides a complete workflow (detect, identify, fix, prevent) rather than just explaining what races are. The Go race detector is a concrete tool that immediately helps, not just theory. Including CI integration (Step 4) turns a one-time fix into a systematic prevention strategy.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-debug-slow-queries",
        r'''Generate 3 high-quality training pairs that teach how to debug slow database queries. For each pair, explain why it's effective training data.''',
        r'''<think>
For debugging slow database queries:
1. Beginner: Using EXPLAIN to understand query execution and spotting a missing index
2. Intermediate: Understanding join strategies and fixing queries that scan too many rows
3. Advanced: Analyzing complex query plans -- hash joins vs. nested loops, temp file sorts, and query rewrites

I covered some EXPLAIN basics in the SQL optimization topic, so I need to approach this from the debugging angle: "I have a slow query, how do I systematically fix it" rather than "here's how to design indexes."
</think>

Here are 3 training pairs for teaching how to debug slow database queries:

**Pair 1 (Beginner):**
```
Q: Our dashboard page takes 8 seconds to load. Our monitoring shows one query taking 7.5 seconds:

SELECT * FROM events WHERE user_id = 42 AND event_type = 'page_view' AND created_at > '2025-01-01';

The events table has 80 million rows. How do I figure out why this is slow and fix it?

A: Use EXPLAIN ANALYZE to see the database's execution plan:

EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM events WHERE user_id = 42 AND event_type = 'page_view' AND created_at > '2025-01-01';

Read the output bottom-up (innermost operation first):

Seq Scan on events  (cost=0.00..2145678.00 rows=342 width=180)
  (actual time=4521.3..7489.2 rows=287 loops=1)
  Filter: ((user_id = 42) AND (event_type = 'page_view') AND (created_at > '2025-01-01'))
  Rows Removed by Filter: 79999713
  Buffers: shared hit=12000 read=1145678
Planning Time: 0.2 ms
Execution Time: 7489.5 ms

**Red flags in this output:**
1. "Seq Scan" -- scanning all 80M rows sequentially (no index used)
2. "Rows Removed by Filter: 79,999,713" -- reading 80M rows to find 287 matches
3. "Buffers: read=1,145,678" -- reading over 1M pages from disk

**The fix -- create a composite index matching your WHERE clause:**

CREATE INDEX idx_events_user_type_date
ON events (user_id, event_type, created_at);

After creating the index:

Index Scan using idx_events_user_type_date on events
  (actual time=0.03..0.15 rows=287 loops=1)
  Buffers: shared hit=12
Execution Time: 0.2 ms

7,489ms down to 0.2ms. The index lets the database jump directly to user_id=42, then within that to event_type='page_view', then scan only the matching date range.

**How to read EXPLAIN output -- the cheat sheet:**
- Seq Scan = no index, reading everything (bad for large tables)
- Index Scan = using an index (good)
- Index Only Scan = answer from index alone, no table access (best)
- Rows Removed by Filter = wasted work
- Buffers: read = disk I/O (expensive), hit = memory cache (fast)
- actual time = first_row..last_row in milliseconds
```
**Why this is effective:** It teaches a repeatable diagnostic process, not just "add an index." The red flags checklist gives the learner a mental framework for reading any EXPLAIN output. Showing the before/after with specific numbers makes the improvement tangible.

**Pair 2 (Intermediate):**
```
Q: This query joins three tables and takes 15 seconds. EXPLAIN shows it's doing a "Nested Loop" with "loops=50000." Is the join strategy wrong?

SELECT o.id, o.total, c.name, p.name AS product_name
FROM orders o
JOIN customers c ON c.id = o.customer_id
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id
WHERE o.created_at > '2025-01-01'
ORDER BY o.created_at DESC
LIMIT 50;

EXPLAIN output (abbreviated):
Limit
  -> Sort (actual time=14892..14892 rows=50)
    -> Nested Loop (actual time=0.1..14500 rows=500000)
        -> Nested Loop (actual time=0.08..8200 rows=500000)
            -> Index Scan on orders (actual time=0.05..120 rows=50000)
            -> Index Scan on order_items (actual time=0.01..0.05 rows=10 loops=50000)
        -> Index Scan on products (actual time=0.01..0.01 rows=1 loops=500000)
    -> Index Scan on customers (actual time=0.01..0.01 rows=1 loops=50000)

A: The problem isn't the join strategy -- Nested Loop is actually correct here. The problem is that the database fetches ALL 50,000 matching orders, joins all their items (500,000 rows), sorts everything, and THEN takes the top 50.

Look at the plan: "Sort (rows=500000)" before "Limit (rows=50)". You're sorting 500,000 rows to keep 50.

**The fix depends on what you actually need:**

**If you need the 50 most recent orders with their items:**

-- Step 1: Get the 50 orders efficiently
WITH recent_orders AS (
    SELECT id, total, customer_id, created_at
    FROM orders
    WHERE created_at > '2025-01-01'
    ORDER BY created_at DESC
    LIMIT 50
)
-- Step 2: Join only those 50 orders to related tables
SELECT ro.id, ro.total, c.name, p.name AS product_name
FROM recent_orders ro
JOIN customers c ON c.id = ro.customer_id
JOIN order_items oi ON oi.order_id = ro.id
JOIN products p ON p.id = oi.product_id
ORDER BY ro.created_at DESC;

Now the CTE fetches exactly 50 orders using the index on (created_at), and the joins only process ~500 rows (50 orders x ~10 items each) instead of 500,000.

**Ensure you have the supporting index:**
CREATE INDEX idx_orders_created_at ON orders (created_at DESC);

**General principle:** When you have LIMIT + ORDER BY + JOINs, the database may need to join everything before sorting. Push the LIMIT as close to the base table as possible using CTEs or subqueries, then join the reduced result set.

**How to spot this pattern in EXPLAIN:**
- Look for Sort or Hash operations with row counts much larger than your LIMIT
- Look for "loops=N" where N is unexpectedly large
- The biggest number in the plan is usually where the time goes
```
**Why this is effective:** It corrects the wrong instinct ("Nested Loop is bad") and identifies the real problem (sort-then-limit vs. limit-then-join). The CTE rewrite is a pattern that applies to many queries, not just this specific case. Teaching how to spot the pattern in EXPLAIN output builds a transferable skill.

**Pair 3 (Advanced):**
```
Q: I have a query that runs fast (50ms) most of the time but occasionally takes 30+ seconds. EXPLAIN ANALYZE shows different plans at different times -- sometimes it uses an index, sometimes it does a sequential scan. Why does PostgreSQL change its plan, and how do I fix the inconsistency?

A: PostgreSQL's query planner chooses between plans based on estimated row counts. When estimates are wrong, it picks the wrong plan. This is called "plan instability" and it's one of the hardest performance problems to debug.

**Why plans change:**

The planner uses table statistics (pg_statistic) to estimate how many rows a query will return. If it estimates 100 rows, an index scan is efficient. If it estimates 5 million rows, a sequential scan is faster (less random I/O). When the estimate is near the tipping point, small changes in statistics cause plan flips.

**Step 1: Check if statistics are stale**

-- See when stats were last updated
SELECT relname, last_analyze, last_autoanalyze, n_live_tup
FROM pg_stat_user_tables WHERE relname = 'events';

-- Force a statistics refresh
ANALYZE events;

If autovacuum/autoanalyze isn't running frequently enough, statistics drift and estimates get wrong.

**Step 2: Compare estimated vs. actual row counts**

EXPLAIN ANALYZE SELECT * FROM events WHERE status = 'pending' AND priority > 5;

Look for mismatches:
  Index Scan on events (rows=100) (actual rows=45000)

If estimated 100 but actual 45,000, the planner underestimated and the index scan may be slow. The planner would have chosen a different strategy if it knew the real count.

**Step 3: Fix statistics accuracy for specific columns**

-- Increase statistics granularity for columns with skewed distributions
ALTER TABLE events ALTER COLUMN status SET STATISTICS 1000;
-- Default is 100 histogram buckets; 1000 gives much better estimates for skewed data
ANALYZE events;

**Step 4: If statistics can't fix it, pin the plan**

For critical queries where you KNOW the best plan, use optimizer hints (not available in PostgreSQL natively, but you can guide the planner):

-- Discourage sequential scan for this session
SET enable_seqscan = off;  -- Only for debugging! Don't leave this on.

-- Better: rewrite the query to make the good plan obvious
-- Add a covering index that makes index-only scan always win:
CREATE INDEX idx_events_status_priority ON events (status, priority)
  INCLUDE (id, user_id, created_at)
  WHERE status = 'pending';

The partial index (WHERE status = 'pending') is small and specific, so the planner will always prefer it over a sequential scan for queries filtering on status='pending'.

**Step 5: Monitor plan stability**

-- Log slow queries and their plans
ALTER SYSTEM SET log_min_duration_statement = 1000;  -- Log queries > 1 second
ALTER SYSTEM SET auto_explain.log_min_duration = 1000;
ALTER SYSTEM SET auto_explain.log_analyze = true;

With auto_explain, every slow query's execution plan is logged automatically. Compare plans over time to detect instability.

**Root cause summary:** Plan instability almost always comes from bad row count estimates, which come from stale or insufficiently granular statistics, especially on columns with highly skewed distributions (like status columns where 99% of rows are 'completed' and 1% are 'pending').
```
**Why this is effective:** Plan instability is an advanced problem that experienced DBAs encounter regularly but few tutorials cover. The systematic approach (check statistics, compare estimates, increase granularity, pin with partial indexes) is a complete toolkit. The root cause explanation (skewed distributions) gives conceptual understanding, not just recipes.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-debug-stack-traces",
        r'''Generate 3 high-quality training pairs that teach how to read and interpret stack traces. For each pair, explain why it's effective training data.''',
        r'''<think>
For stack traces:
1. Beginner: Reading a Python traceback -- understanding the call chain, finding YOUR code vs. library code
2. Intermediate: Reading a Java/JavaScript stack trace with async boundaries, understanding "Caused by" chains
3. Advanced: Interpreting stack traces from production (stripped symbols, minified code, core dumps)

The key skill is: look at the stack trace, find the line in YOUR code (not the library's), and understand the chain of calls that got there. Most beginners stare at the error message at the bottom and ignore the call stack.
</think>

Here are 3 training pairs for teaching how to read and interpret stack traces:

**Pair 1 (Beginner):**
```
Q: My Python script crashed with this error. I don't understand how to read the traceback. What does each part mean, and where should I look to fix the bug?

Traceback (most recent call last):
  File "app.py", line 45, in main
    result = process_orders("orders.csv")
  File "app.py", line 28, in process_orders
    total = calculate_total(order)
  File "app.py", line 15, in calculate_total
    subtotal = sum(item["price"] * item["qty"] for item in order["items"])
  File "app.py", line 15, in <genexpr>
    subtotal = sum(item["price"] * item["qty"] for item in order["items"])
TypeError: unsupported operand type(s) for *: 'str' and 'str'

A: A Python traceback reads TOP-DOWN as the call chain and BOTTOM-UP for diagnosis. Here's how to read each part:

**The call chain (read top to bottom -- "how did we get here?"):**
1. main() at line 45 called process_orders("orders.csv")
2. process_orders() at line 28 called calculate_total(order)
3. calculate_total() at line 15 tried to compute item["price"] * item["qty"]
4. Inside the generator expression, the multiplication failed

**The error (read bottom -- "what went wrong?"):**
TypeError: unsupported operand type(s) for *: 'str' and 'str'

This means item["price"] and item["qty"] are both strings, not numbers. You can't multiply two strings. The data from the CSV file wasn't converted to numbers.

**Where to fix:**
Not at line 15 (that's where it crashed, not where the bug is). The bug is wherever the order data is created -- probably where you read the CSV:

# Bug: CSV reader returns all values as strings
import csv
with open(filepath) as f:
    reader = csv.DictReader(f)
    orders = list(reader)  # {"price": "29.99", "qty": "3"} -- strings!

# Fix: convert types when reading
    for row in reader:
        row["price"] = float(row["price"])
        row["qty"] = int(row["qty"])

**Reading strategy for any traceback:**
1. Read the LAST line first (the error type and message)
2. Scan the call stack for lines in YOUR files (ignore library/framework files)
3. The bug is usually in your code, NOT where it crashed. The crash site tells you what's wrong; the call chain tells you where to look for why.
4. Look 1-2 frames above the crash for the bad data's origin
```
**Why this is effective:** It teaches a reading STRATEGY (bottom for what, scan for your files, look above the crash for the cause) rather than just explaining this specific error. The insight that "the crash site is not the bug site" is counterintuitive but essential. The CSV example is realistic -- type mismatches from data parsing are extremely common.

**Pair 2 (Intermediate):**
```
Q: My Java application threw this exception. It has "Caused by" sections and I'm not sure which part to focus on. Also, some frames say "at sun.reflect..." and "at org.springframework..." -- should I care about those?

Exception in thread "main" org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'userService': Injection of autowired dependencies failed
    at org.springframework.beans.factory.annotation.AutowiredAnnotationBeanPostProcessor.postProcessProperties(...)
    at org.springframework.beans.factory.support.AbstractAutowireCapableBeanFactory.populateBean(...)
    ... 15 more
Caused by: org.springframework.beans.factory.UnsatisfiedDependencyException:
Error creating bean with name 'userRepository': Unsatisfied dependency
    at org.springframework.beans.factory.support.ConstructorResolver.createArgumentArray(...)
    ... 20 more
Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
No qualifying bean of type 'javax.sql.DataSource' available
    at org.springframework.beans.factory.support.DefaultListableBeanFactory.getBean(...)
    at com.myapp.config.DatabaseConfig.dataSource(DatabaseConfig.java:23)
    ... 10 more

A: Java "Caused by" chains read BOTTOM-UP -- the last "Caused by" is the root cause. Here's how to decode this:

**Step 1: Go to the LAST "Caused by":**
NoSuchBeanDefinitionException: No qualifying bean of type 'javax.sql.DataSource' available

This is the actual problem: Spring can't find a DataSource bean (database connection pool).

**Step 2: Find YOUR code in that section:**
at com.myapp.config.DatabaseConfig.dataSource(DatabaseConfig.java:23)

Line 23 of DatabaseConfig.java is where the DataSource should be created. That's where to look.

**Step 3: Read the chain upward to understand the cascade:**
- No DataSource -> userRepository can't be created (it needs a database)
- No userRepository -> userService can't be created (it depends on userRepository)
- No userService -> application fails to start

**Filtering framework noise:**
- Ignore: org.springframework.*, sun.reflect.*, java.lang.reflect.*
- Focus: com.myapp.* (your package)
- "... 15 more" means 15 frames were identical to the parent exception's stack (space optimization, not missing information)

**The fix (in DatabaseConfig.java:23):** Either the @Bean annotation is missing, database credentials are wrong, or the database driver isn't on the classpath:

@Configuration
public class DatabaseConfig {
    @Bean  // Was this annotation missing?
    public DataSource dataSource() {
        // Check: is the DB URL correct? Is the driver JAR included?
    }
}

**Rule of thumb for "Caused by" chains:** Read like a detective story backwards. The last cause is "the gun." The middle causes are "the chain of events." The first exception is "the consequence the user saw."
```
**Why this is effective:** Java stack traces are notoriously verbose and intimidating. The "read bottom-up" strategy with the detective story metaphor makes the Caused-by chain navigable. Teaching which packages to ignore (framework internals) vs. focus on (com.myapp) is a time-saving skill that comes from experience.

**Pair 3 (Advanced):**
```
Q: We got this error in production from our Node.js service. The stack trace is incomplete -- it shows "at processTicksAndRejections" and some frames are missing. We also have a minified React frontend error that shows "at r (chunk-abc123.js:1:45234)." How do I get useful information from these?

Backend error:
UnhandledPromiseRejectionWarning: Error: Connection refused
    at TCPConnectWrap.afterConnect [as oncomplete] (net.js:1141:16)
    at processTicksAndRejections (internal/process/task_queues.js:93:5)

Frontend error:
TypeError: Cannot read property 'email' of undefined
    at r (chunk-7f3a2b.js:1:45234)
    at l (chunk-7f3a2b.js:1:67891)
    at Object.a (framework-d4e5f6.js:2:12345)

A: Both problems stem from losing context in async and build pipelines. Here's how to recover useful information:

**Backend: Missing async stack traces**

Node.js loses stack context across async boundaries (promises, callbacks). The stack shows where the error was THROWN (inside Node's TCP code), not where your code INITIATED the connection.

**Fix 1: Enable async stack traces (Node 12+):**
node --async-stack-traces server.js

Now you'll see:
Error: Connection refused
    at TCPConnectWrap.afterConnect (net.js:1141:16)
    at async UserService.fetchProfile (/app/services/user.js:45:20)
    at async Router.handleRequest (/app/routes/users.js:23:18)

**Fix 2: Add context when making connections:**
async function fetchProfile(userId) {
    try {
        return await db.query('SELECT * FROM users WHERE id = $1', [userId]);
    } catch (err) {
        // Wrap with context so the stack trace is useful
        const contextError = new Error(`Failed to fetch profile for user ${userId}`);
        contextError.cause = err;  // ES2022 error chaining
        throw contextError;
    }
}

**Frontend: Source maps for minified code**

Minified stack traces are unreadable without source maps. Your build tool (webpack, Vite) generates .map files that map minified positions back to original source.

**Step 1: Upload source maps to your error tracker:**
Most error tracking services (Sentry, Datadog, Bugsnag) can unminify stack traces automatically:

# In your build pipeline:
sentry-cli sourcemaps upload --release=v1.2.3 ./dist/assets/

The minified trace:
  at r (chunk-7f3a2b.js:1:45234)

Becomes:
  at renderUserProfile (components/UserProfile.tsx:42:18)

**Step 2: If you don't have an error tracker, use source maps locally:**
npx source-map-cli resolve chunk-7f3a2b.js.map 1 45234
# Output: components/UserProfile.tsx line 42, column 18

**Step 3: Debug the actual error:**
Now you know it's UserProfile.tsx line 42:
  const email = user.email;  // user is undefined

This means the component rendered before user data loaded. Fix with optional chaining or a loading guard:
  const email = user?.email;
  // or
  if (!user) return <LoadingSpinner />;

**Production stack trace checklist:**
- [ ] Backend: async stack traces enabled (--async-stack-traces flag)
- [ ] Backend: errors wrapped with context at service boundaries
- [ ] Frontend: source maps uploaded to error tracker on every deploy
- [ ] Frontend: source maps NOT served publicly (security risk -- they expose your source code)
- [ ] Both: structured error logging with request IDs for correlation
```
**Why this is effective:** It addresses two real production scenarios (async context loss, minified code) that frustrate developers daily. The solutions are immediately actionable (flags, source map uploads, error wrapping). The security note about not serving source maps publicly is the kind of detail that prevents a different kind of production incident.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-debug-network-api",
        r'''Generate 3 high-quality training pairs that teach how to debug network and API issues. For each pair, explain why it's effective training data.''',
        r'''<think>
For debugging network/API issues:
1. Beginner: Using curl and HTTP status codes to diagnose API failures
2. Intermediate: Debugging timeout issues, connection pooling, and DNS resolution
3. Advanced: Debugging intermittent failures with distributed tracing and correlation IDs

Network debugging requires layered thinking: is the problem DNS, TCP, TLS, HTTP, or application-level? Each layer has different tools and symptoms.
</think>

Here are 3 training pairs for teaching how to debug network and API issues:

**Pair 1 (Beginner):**
```
Q: My application is getting errors when calling an external API. The error message just says "Request failed." How do I figure out what's actually going wrong?

A: First, isolate whether the problem is in your code, the network, or the API itself. Use curl to test the API directly from your server:

# Basic request with verbose output
curl -v https://api.example.com/users/123 \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"

The -v flag shows the entire HTTP conversation:

* Trying 93.184.216.34:443...
* Connected to api.example.com (93.184.216.34) port 443
* SSL connection using TLS 1.3
> GET /users/123 HTTP/2
> Host: api.example.com
> Authorization: Bearer YOUR_TOKEN
>
< HTTP/2 401
< content-type: application/json
<
{"error": "Token expired"}

Now you know: it's a 401 (authentication error), the token is expired. Your app's "Request failed" message was hiding this.

**HTTP status code cheat sheet for debugging:**

- 400 Bad Request: Your request body or parameters are malformed. Check JSON syntax, required fields.
- 401 Unauthorized: Authentication failed. Token expired, wrong API key, missing header.
- 403 Forbidden: Authenticated but not authorized. Check permissions/scopes.
- 404 Not Found: Wrong URL or the resource doesn't exist. Check for typos in the path.
- 422 Unprocessable Entity: Valid JSON but semantic errors (e.g., email format invalid).
- 429 Too Many Requests: Rate limited. Check Retry-After header, add backoff.
- 500 Internal Server Error: The API server has a bug. Not your fault, but you should handle it gracefully.
- 502 Bad Gateway: A proxy/load balancer couldn't reach the API server. Usually transient.
- 503 Service Unavailable: API is down or overloaded. Retry with backoff.
- 504 Gateway Timeout: The API took too long to respond. Could be your request is too large or the API is slow.

**Fix your application's error handling to surface this information:**

# Bad
try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()
except Exception:
    print("Request failed")  # Useless

# Good
try:
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
except requests.exceptions.HTTPError as e:
    print(f"API returned {e.response.status_code}: {e.response.text}")
except requests.exceptions.ConnectionError:
    print(f"Could not connect to {url}")
except requests.exceptions.Timeout:
    print(f"Request to {url} timed out after 10s")
```
**Why this is effective:** It teaches the diagnostic tool (curl -v) before the theory (status codes). The progression from "Request failed" to specific error types shows the learner how much information they're losing with bare exception handling. The status code cheat sheet is a reference they'll use daily.

**Pair 2 (Intermediate):**
```
Q: Our service calls an internal API that works fine from curl, but from our Python application it intermittently times out after exactly 30 seconds. The API responds in ~200ms when tested directly. What could cause this?

A: When curl works but your application times out, the problem is usually in the client's connection management, DNS, or proxy configuration. Here's a systematic checklist:

**1. Check DNS resolution:**
import socket
start = time.time()
ip = socket.getaddrinfo("internal-api.service.local", 443)
dns_time = time.time() - start
print(f"DNS resolved to {ip[0][4]} in {dns_time:.3f}s")

If DNS takes 30 seconds, your DNS server is unreachable and the resolver is timing out before falling back. Common in Docker/Kubernetes where DNS is configured differently than the host.

**2. Check connection pooling exhaustion:**
If you're creating a new requests.Session() per request or (worse) a new connection per request, you may exhaust the connection pool:

# Bad: new connection every time (slow, can exhaust sockets)
for url in urls:
    response = requests.get(url)

# Good: reuse connections with a session
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(
    pool_connections=10,
    pool_maxsize=20,
    max_retries=3
)
session.mount('https://', adapter)
for url in urls:
    response = session.get(url)

If the pool is exhausted, new requests block waiting for a connection to free up -- that's your 30-second timeout.

**3. Check for proxy interference:**
import os
print(os.environ.get('HTTP_PROXY'), os.environ.get('HTTPS_PROXY'))

If these are set (common in corporate environments), your request is routing through a proxy that may be slow or blocking the internal URL. Fix:
os.environ['NO_PROXY'] = 'internal-api.service.local'

**4. Check for IPv6 vs IPv4 issues:**
If the hostname resolves to both IPv4 and IPv6 addresses, your app may try IPv6 first, wait for it to fail (30 seconds), then fall back to IPv4 which works. curl may default to IPv4.

Force IPv4:
import requests
from requests.packages.urllib3.util.connection import allowed_gai_family
import socket
requests.packages.urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET

**5. Add timing instrumentation to your HTTP client:**

import requests
import time

def timed_request(session, url, **kwargs):
    start = time.time()
    try:
        resp = session.get(url, timeout=(5, 30), **kwargs)  # (connect_timeout, read_timeout)
        elapsed = time.time() - start
        print(f"{url} -> {resp.status_code} in {elapsed:.3f}s")
        return resp
    except requests.exceptions.ConnectTimeout:
        print(f"{url} -> connect timeout after {time.time()-start:.3f}s")
        raise
    except requests.exceptions.ReadTimeout:
        print(f"{url} -> read timeout after {time.time()-start:.3f}s")
        raise

The separate connect vs. read timeout (5, 30) tells you whether the problem is establishing the connection or waiting for the response.
```
**Why this is effective:** It addresses a genuinely confusing scenario ("curl works, my app doesn't") with five specific checkpoints ordered by likelihood. The dual timeout (connect, read) is a practical detail that immediately helps narrow the problem. Each solution is a concrete code change, not just a concept.

**Pair 3 (Advanced):**
```
Q: We have a microservices architecture with 8 services. Users report intermittent errors ("something went wrong") but we can't figure out which service is failing. Logs from each service show different request IDs. How do we trace a request across services to find where it fails?

A: You need distributed tracing -- propagating a single trace ID across all service boundaries. Here's how to implement it:

**Step 1: Generate and propagate a correlation ID**

Every request entering your system gets a unique trace ID. Each service passes it to the next in headers:

# Service A (API gateway)
import uuid

@app.middleware("http")
async def add_trace_id(request, call_next):
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    request.state.trace_id = trace_id

    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response

# When calling Service B from Service A:
async def call_service_b(trace_id, data):
    response = await httpx.post(
        "http://service-b/process",
        json=data,
        headers={"X-Trace-ID": trace_id}
    )
    return response

# Service B receives the same trace_id and passes it to Service C, etc.

**Step 2: Include trace_id in ALL log messages**

import logging
import contextvars

trace_id_var = contextvars.ContextVar('trace_id', default='no-trace')

class TraceFilter(logging.Filter):
    def filter(self, record):
        record.trace_id = trace_id_var.get()
        return True

# Log format:
formatter = logging.Formatter(
    '%(asctime)s [%(trace_id)s] %(name)s %(levelname)s %(message)s'
)

Now every log line across every service includes the trace ID:

2025-06-15 10:23:45 [abc-123] service-a INFO  Received request GET /users/42
2025-06-15 10:23:45 [abc-123] service-b INFO  Fetching user profile
2025-06-15 10:23:46 [abc-123] service-c ERROR Database connection refused
2025-06-15 10:23:46 [abc-123] service-b ERROR Upstream error from service-c: 503
2025-06-15 10:23:46 [abc-123] service-a ERROR Request failed: 503

Search logs for [abc-123] and you see the entire request path, including the root cause (service-c database connection refused).

**Step 3: Use OpenTelemetry for structured tracing**

For production systems, use OpenTelemetry instead of manual correlation:

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

provider = TracerProvider()
provider.add_span_processor(BatchSpanExporter(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("service-a")

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    with tracer.start_as_current_span("get-user") as span:
        span.set_attribute("user.id", user_id)

        # HTTP client auto-propagates trace context
        profile = await call_service_b(user_id)

        span.set_attribute("response.status", "ok")
        return profile

OpenTelemetry automatically propagates trace context via W3C Trace Context headers, creates parent-child span relationships across services, and exports to visualization tools (Jaeger, Zipkin, Grafana Tempo).

**Step 4: Visualize and alert**

In Jaeger/Tempo, a single trace shows:
- Service A: get-user (total: 1.2s)
  - Service B: fetch-profile (450ms)
    - Service C: db-query (45ms)
  - Service D: fetch-permissions (200ms) -- FAILED (timeout after 200ms)
  - Service A: build-response (50ms)

You can immediately see: Service D timed out, causing the user's error.

Set up alerts: "Alert when >1% of traces have a span with status=ERROR in a 5-minute window."
```
**Why this is effective:** It progresses from the simplest approach (manual correlation ID) to the production standard (OpenTelemetry), letting teams adopt incrementally. The contextvars-based logging is implementable in an afternoon. The Jaeger visualization example makes the abstract concept of "distributed tracing" concrete. This is how real production debugging works.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
