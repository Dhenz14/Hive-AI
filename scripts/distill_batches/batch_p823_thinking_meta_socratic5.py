"""Phase 3B: Metacognition — Socratic Method for Debugging (Part 5)

Training the model to ask the right questions to guide users toward
finding bugs themselves, rather than just providing answers.
"""

PAIRS = [
    (
        "thinking/meta-socratic-debug-race-condition",
        r'''My application works fine in development but randomly fails in production. Sometimes it returns the wrong user's data. I have no idea where to start.''',
        r'''<think>
This sounds like a concurrency issue — returning the wrong user's data is a classic symptom of shared mutable state or a race condition. But rather than jumping to conclusions, I should guide the user to discover this themselves through targeted questions.

The Socratic approach here is:
1. Help them narrow down the symptom (what exactly happens, when, how often)
2. Guide them to the difference between dev and prod (concurrency!)
3. Lead them to examine shared state in their code
4. Help them verify the hypothesis

The key insight I want them to arrive at: development typically runs with one process/thread, production runs with multiple — shared mutable state that works in single-threaded mode breaks under concurrency.

I should ask questions that lead to this realization rather than stating it directly.
</think>

Let's work through this systematically. I'm going to ask you questions that will help narrow this down. The symptom — returning wrong user's data — is very revealing.

**First, let's understand the environment difference:**

1. In development, how many server processes/workers are running?
   - Is it a single process (e.g., `flask run`, `node app.js`)?
   - In production, how many? (Check your gunicorn/uvicorn/PM2 config)

*The reason I'm asking:* The most common cause of "works in dev, fails in prod" is concurrency. Dev typically runs one process; prod runs many.

**Second, let's trace the data path:**

2. When a request comes in, how does your code know which user is making the request?
   - Is it from a JWT token? Session cookie? Request header?
   - At what point in the request lifecycle is the "current user" determined?

3. Is the "current user" stored in any of these?
   - A global variable or module-level variable
   - A class attribute shared across requests
   - A cache key that doesn't include the user ID

*I'm asking because:* If user identity is stored in shared state rather than per-request state, concurrent requests can overwrite each other.

**Third, let's look for the smoking gun:**

4. Search your codebase for these patterns:
```python
# Red flags — shared mutable state:
current_user = None          # Module-level variable
app.current_user = user      # Stored on the app object
g.user = user                # Flask g is OK, but check if you're using it correctly

# Look for any variable that's set in one request and read in another
```

5. Do you use any request-scoped vs application-scoped context?
   - In Flask: `g` is per-request, but module variables are not
   - In Express: `req.user` is per-request, but `app.locals` is shared
   - In Django: `request.user` is per-request

**What I suspect you'll find:**

Somewhere in your code, user identity or user-specific data is stored in a location that's shared across concurrent requests. In dev (single process), requests are sequential so this works. In prod (multiple concurrent requests), they overwrite each other.

**Verify this theory by answering:** Does the problem happen more often under high traffic? If yes, this strongly points to a concurrency/shared-state issue.'''
    ),
    (
        "thinking/meta-socratic-debug-memory-leak",
        r'''Our Node.js service restarts every few hours in production. The ops team says it's hitting the memory limit. How do I find the memory leak?''',
        r'''<think>
Memory leaks in Node.js are a common but tricky problem. Rather than giving a long lecture on memory profiling tools, I should guide them through a diagnostic process that teaches them to think about memory leaks systematically.

The Socratic approach:
1. First, confirm it's actually a leak (vs just high memory usage)
2. Guide them to think about common Node.js leak patterns
3. Help them narrow down through targeted questions
4. Show them how to verify

Common Node.js memory leak sources:
- Event listeners not removed (the #1 cause)
- Growing arrays/maps/caches without eviction
- Closures holding references to large objects
- Unreferenced timers/intervals
- Streams not properly consumed or destroyed

I want them to learn the diagnostic process, not just get a tool recommendation.
</think>

Let's work through this methodically. Memory leaks are findable — you just need to know where to look.

**Step 1 — Confirm it's a leak, not just high usage:**

Can you add this to your service and watch the output over a few hours?
```javascript
setInterval(() => {
    const mem = process.memoryUsage();
    console.log(JSON.stringify({
        rss_mb: Math.round(mem.rss / 1024 / 1024),
        heap_used_mb: Math.round(mem.heapUsed / 1024 / 1024),
        heap_total_mb: Math.round(mem.heapTotal / 1024 / 1024),
        external_mb: Math.round(mem.external / 1024 / 1024),
        timestamp: new Date().toISOString()
    }));
}, 60000);  // Every minute
```

**Questions about the pattern:**
- Does `heap_used_mb` grow steadily, or does it spike suddenly?
- Does it ever go DOWN (meaning GC is working but something keeps growing)?
- Is `external_mb` growing? (That points to native addons or Buffers)

**Step 2 — Think about what grows over time in your code:**

Ask yourself these questions:
1. Do you have any in-memory caches? (Maps, objects that accumulate entries)
   ```javascript
   // This is a leak — grows forever
   const cache = {};
   app.get('/user/:id', (req, res) => {
       cache[req.params.id] = fetchUser(req.params.id);
   });
   ```

2. Do you add event listeners inside request handlers?
   ```javascript
   // This is the #1 Node.js leak — listeners accumulate
   app.get('/stream', (req, res) => {
       emitter.on('data', handler);  // Added per request, never removed
   });
   ```

3. Do you have setInterval or setTimeout without cleanup?

4. Do you store request/response objects in any long-lived structure?

**Step 3 — Search for the common culprits:**

Run these searches on your codebase and tell me what you find:
```bash
# Event listeners added without removal
grep -rn '\.on(' src/ | grep -v 'node_modules'
grep -rn '\.addEventListener' src/

# Growing collections
grep -rn 'Map()' src/
grep -rn '= {}' src/  # Module-level objects used as caches
grep -rn '\.push(' src/  # Arrays that grow

# Timers without cleanup
grep -rn 'setInterval' src/
grep -rn 'setTimeout' src/
```

**Step 4 — If the code search doesn't reveal it:**

Which of these descriptions matches your service?
- (a) Handles WebSocket connections
- (b) Processes file uploads
- (c) Connects to databases/Redis
- (d) Uses streaming (readable/writable streams)

Each has a specific common leak pattern. Tell me which applies and I'll help you narrow down further.

*The goal here is for YOU to understand how to find memory leaks systematically, not just fix this one instance.*'''
    ),
    (
        "thinking/meta-socratic-debug-slow-query",
        r'''One of our API endpoints went from 50ms to 3 seconds response time. Nothing in the code changed. Help!''',
        r'''<think>
"Nothing changed" is almost never true — something changed in the environment, data, or dependencies. The Socratic approach here is to guide them to discover WHAT changed by asking the right questions.

Key diagnostic dimensions:
1. What exactly changed? (data growth, infrastructure, dependencies)
2. Is it all requests or some? (data-dependent vs systemic)
3. Is the slowness in the DB, application, or network?

I want to guide them through a structured diagnostic process that they can reuse for any performance regression.
</think>

"Nothing changed" — let's test that assumption. Something changed; we just need to find it. I'm going to guide you through a diagnostic process.

**Question 1: Is it ALL requests to this endpoint, or just some?**

Test with different inputs:
```bash
# Try several different request parameters
time curl -s https://yourapi.com/endpoint?id=1
time curl -s https://yourapi.com/endpoint?id=100
time curl -s https://yourapi.com/endpoint?id=999999
```

- If ALL requests are slow: likely infrastructure/systemic change
- If SOME requests are slow: likely data-dependent (specific records trigger the problem)

**Question 2: Where is the time being spent?**

Can you add timing to break down the request?
```python
@app.get("/endpoint")
async def handler():
    t0 = time.perf_counter()

    # Database query
    t1 = time.perf_counter()
    data = await db.fetch(query)
    t2 = time.perf_counter()

    # Processing
    result = process(data)
    t3 = time.perf_counter()

    # Serialization
    response = jsonify(result)
    t4 = time.perf_counter()

    print(f"DB: {t2-t1:.3f}s | Process: {t3-t2:.3f}s | Serialize: {t4-t3:.3f}s")
    return response
```

What does this show? This tells us which layer to investigate.

**Question 3 (if DB is slow): What DIDN'T change in the code, but DID change?**

Even if no code was deployed, consider:
- Has the data volume grown significantly? (Table went from 10K to 10M rows)
- Did a scheduled job run that changed indexes? (pg_repack, REINDEX)
- Did the database statistics become stale? (Run `ANALYZE`)
- Was a table recently loaded with new data that the query planner isn't handling well?

Check this:
```sql
-- How big is the table now vs when it was fast?
SELECT relname, n_live_tup FROM pg_stat_user_tables
WHERE relname = 'your_table';

-- When were statistics last updated?
SELECT last_analyze, last_autoanalyze FROM pg_stat_user_tables
WHERE relname = 'your_table';

-- Run EXPLAIN ANALYZE on the slow query
EXPLAIN (ANALYZE, BUFFERS) SELECT ... ;
```

**Question 4: What changed in the infrastructure?**

- Did the database server run out of disk space or memory?
- Was there an OS update or restart?
- Did connection pool settings change?
- Is the database on a different host/instance than before?

**Follow this trail** and tell me:
1. Is the slowness in DB, application code, or network?
2. Is it all requests or data-dependent?
3. What does EXPLAIN ANALYZE show?

Each answer eliminates possibilities and narrows the search.'''
    ),
    (
        "thinking/meta-socratic-debug-auth-failure",
        r'''Users are randomly getting logged out of our application. It doesn't happen to everyone, and we can't reproduce it locally. Where should we look?''',
        r'''<think>
Random logouts that can't be reproduced locally — this is a great Socratic debugging scenario because the developer needs to think about the differences between local and production environments.

Common causes of random logouts:
1. Session storage issues (Redis eviction, file sessions on multiple servers)
2. JWT expiration or clock skew
3. Cookie configuration (domain, path, SameSite, Secure attributes)
4. Load balancer routing to different servers with different sessions
5. Token rotation race conditions
6. CORS/cookie issues in specific browsers

The Socratic approach: ask questions that reveal the architecture and guide them to the most likely cause based on their answers.
</think>

"Random" and "can't reproduce locally" are strong clues. Let me guide you through this with questions that narrow the possibilities.

**Question 1: How are sessions managed?**

Which describes your setup?
- (a) Server-side sessions stored in memory (e.g., express-session default)
- (b) Server-side sessions stored in Redis/database
- (c) JWT tokens stored in cookies
- (d) JWT tokens stored in localStorage

*Why I'm asking:* Each has a completely different failure mode.

**If (a) — in-memory sessions:** Do you have multiple server instances behind a load balancer? If yes, this is almost certainly your problem. User hits server A (gets session), next request goes to server B (no session, logged out).

**If (b) — Redis sessions:** Is Redis evicting keys? Check:
```bash
redis-cli INFO memory
# Look at: used_memory vs maxmemory
# Look at: evicted_keys — if this is non-zero, Redis is dropping sessions
```

**If (c) or (d) — JWT:** When was the last time you rotated the signing secret? If the secret changed, all existing tokens become invalid.

**Question 2: Which users are affected?**

- Is there a pattern by browser? (Safari has stricter cookie rules)
- Is there a pattern by device? (mobile vs desktop)
- Is there a pattern by time? (after X minutes? after midnight?)
- Does it happen after specific actions? (password change? profile update?)

**Question 3: Check your cookie configuration.**

Look at your Set-Cookie header in production. Does it include:
```
Set-Cookie: session=abc123;
    Domain=.yourapp.com;   ← Does this match your production domain exactly?
    Path=/;                ← Is this set?
    Secure;                ← Are you serving over HTTPS?
    HttpOnly;
    SameSite=Lax;          ← Strict can cause issues with external links
    Max-Age=86400;         ← When does it expire?
```

**Question 4: Why can't you reproduce locally?**

Think about what's different:
- Local: one server process, one browser, no load balancer
- Production: multiple servers, various browsers, load balancer, CDN

Which of these production characteristics are you NOT replicating locally?

**Start investigating by answering these questions.** Each answer eliminates possibilities:
- Session type determines the likely failure mode
- Affected user patterns reveal the trigger
- Cookie config reveals misconfiguration
- Local vs prod differences point to the root cause

Report back what you find and we'll narrow it further.'''
    ),
    (
        "thinking/meta-socratic-debug-data-corruption",
        r'''We found that some records in our database have impossible values — negative prices, future dates for past events, duplicate unique IDs. How did this happen?''',
        r'''<think>
Data corruption with specific patterns (negative prices, wrong dates, duplicate "unique" IDs) — each of these has different likely causes. Rather than guessing, I should guide them to investigate each type of corruption separately, as they may have different root causes.

Socratic approach:
1. Help them classify the corruption types
2. For each type, ask questions that reveal the cause
3. Guide them to check their data validation layers
4. Help them build defenses

Key insight: if the database has these values, then either:
- Constraints aren't in place
- Constraints were bypassed
- A migration/script introduced the bad data
- An application bug wrote bad data

I want them to discover which layer failed.
</think>

These three types of corruption likely have different causes. Let's investigate each one separately.

**First, let's classify and timestamp:**

For each corruption type, can you run:
```sql
-- When were the bad records created/modified?
SELECT id, price, created_at, updated_at
FROM products WHERE price < 0
ORDER BY updated_at DESC;

SELECT id, event_date, created_at
FROM events WHERE event_date > NOW()
  AND type = 'past_event';

-- For duplicates:
SELECT unique_field, COUNT(*), MIN(created_at), MAX(created_at)
FROM records
GROUP BY unique_field HAVING COUNT(*) > 1;
```

**This tells us:**
- Did the corruption happen all at once? (migration/script)
- Did it accumulate over time? (application bug)
- Did it start on a specific date? (deployment introduced a bug)

**Question 1 — Negative prices: Where is validation?**

Walk me through the layers a price value passes through:
```
User input → Frontend validation → API validation → Business logic → Database

Which layers have price validation?
- [ ] Frontend: does the form prevent negative values?
- [ ] API: does the endpoint reject negative prices?
- [ ] Business logic: is there a check before saving?
- [ ] Database: is there a CHECK constraint?
```

```sql
-- Check if the database has constraints:
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'products'::regclass;

-- If no CHECK constraint exists, that's your gap:
ALTER TABLE products ADD CONSTRAINT price_positive CHECK (price >= 0);
```

**Question 2 — Future dates for past events: What writes to this field?**

- Is the date set by the user or auto-generated?
- Could it be a timezone issue? (UTC vs local time confusion)
- Is there a background job that updates dates?
- Could it be a date parsing issue? (`MM/DD/YYYY` vs `DD/MM/YYYY`)

**Question 3 — Duplicate "unique" IDs: Is there a UNIQUE constraint?**

```sql
-- Check if uniqueness is enforced at the database level:
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename = 'your_table' AND indexdef LIKE '%UNIQUE%';
```

- If no UNIQUE constraint: the "uniqueness" was only enforced in application code, which has race conditions
- If UNIQUE exists: was it added after data was already duplicated? Or was it temporarily dropped during a migration?

**The meta-lesson I want you to take away:**

```
Application validation can be bypassed (bugs, race conditions, direct DB access)
Database constraints cannot be bypassed

Every business rule that MUST be true should have a database constraint:
- NOT NULL for required fields
- CHECK for value ranges
- UNIQUE for unique fields
- FOREIGN KEY for relationships
```

Tell me what you find from the timestamp analysis and constraint checks — that will reveal whether this was a one-time event or an ongoing bug.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
