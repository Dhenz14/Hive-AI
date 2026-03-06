"""Phase 2C: Advanced Reasoning — Analogical Reasoning (Part 8/8)"""

PAIRS = [
    (
        "thinking/analogy-garbage-collection-to-housekeeping",
        "Can you explain garbage collection in programming languages? I'm learning Go and I keep seeing references to GC pauses. Why does it matter?",
        r'''<think>
Garbage collection for someone learning Go. The housekeeping analogy works well here because it maps the key concepts: when to clean, what to clean, and the cost of cleaning.

**Housekeeping analogy:**
- Your house (memory) fills with stuff (objects/allocations)
- Some stuff you're actively using (referenced objects)
- Some stuff you're done with but haven't thrown out (unreferenced objects = garbage)
- Eventually you need to clean up (garbage collection)

**When do you clean?**
- Stop-the-world: Stop everything, clean the entire house (STW GC pause)
- Concurrent: Clean while people are still living/working in the house (concurrent GC)
- Incremental: Clean a little bit at a time between activities (incremental GC)

**GC pauses = the time your program stops to clean up.**
- Like pausing a dinner party to vacuum the whole house
- Guests (requests) have to wait
- Go's GC is designed to minimize these pauses (<1ms target)

**Where the analogy maps well:**
- Mark phase: Walk through every room, tag everything that's still being used
- Sweep phase: Throw out everything that's not tagged
- Generational GC: Clean the kitchen daily (young gen), deep-clean the attic yearly (old gen)
- Memory leak: a box you'll never open but keep a note about, so the cleaner never throws it out

**Where it breaks down:**
- Memory is more structured than a house (heap, stack)
- Compaction (defragmentation) doesn't have a great household equivalent
- Finalizers/destructors add complexity that housekeeping doesn't capture
</think>

Think of garbage collection like **housekeeping in a busy household**.

## The Core Analogy

```
YOUR PROGRAM'S MEMORY = YOUR HOUSE

Creating objects    = Bringing new stuff into the house
Using objects       = Actively using furniture, tools, appliances
Dereferencing       = Putting something in the corner, never touching it again
Garbage             = Stuff nobody uses but it's still taking up space
GC running          = The housekeeper cleaning up

The problem: if nobody cleans, the house fills up until
there's no room for anything new (out of memory).
```

## How Garbage Collection Works

```
MARK PHASE: "What are we still using?"
  Housekeeper walks through every room:
  ✓ Kitchen table — people eating here        (mark: in use)
  ✓ Living room couch — someone sitting       (mark: in use)
  ✗ Old newspaper pile — nobody reading        (mark: garbage)
  ✗ Empty pizza box — clearly done             (mark: garbage)
  ✓ Toolbox in garage — referenced by repair list (mark: in use)

SWEEP PHASE: "Throw out everything not marked"
  Remove old newspapers, empty boxes, broken things
  Free up the space they occupied

In code:
  The GC starts from "roots" (stack variables, global variables)
  and follows every reference chain. Anything reachable = alive.
  Anything unreachable = garbage → free its memory.
```

## GC Pauses: Why They Matter

```
STOP-THE-WORLD GC (like old Java, Python):
  "Everyone STOP. Nobody move. I'm vacuuming."

  Dinner party analogy:
    8 PM: Guests arrive, having fun           (program running)
    9 PM: "EVERYONE FREEZE!"                  (GC pause starts)
           Housekeeper vacuums entire house
           Guests stand still for 5 minutes    (program paused)
    9:05 PM: "OK, continue!"                  (GC pause ends)

  For a web server:
    Normal: handling requests in 5ms
    GC pause: ALL requests wait 50-200ms
    Users experience random lag spikes

CONCURRENT GC (Go's approach):
  "Keep partying. I'll clean around you."

  Housekeeper cleans WHILE guests are active:
    - Picks up empty glasses between conversations
    - Sweeps under tables while people are standing
    - Brief "hold still" moment for final sweep (~0.1ms)

  Go's GC target: < 1ms pause time
  This is why Go is popular for web servers — predictable latency
```

## Types of GC (Cleaning Strategies)

```
STRATEGY              HOUSE ANALOGY                 USED BY
──────────────────────────────────────────────────────────────
Reference counting    Each item has a tag showing    Python, Swift
                      how many people are using it.
                      When tag reaches 0 → trash it
                      immediately. (No big cleanup
                      needed, but can't handle
                      circular references — two
                      items referencing each other)

Mark and sweep        Walk the whole house, mark     Go, Java (old)
                      what's used, sweep the rest.

Generational          Kitchen (young gen): cleaned    Java, .NET, JS
                      daily — most trash is recent.
                      Attic (old gen): cleaned
                      yearly — old stuff rarely
                      becomes trash.

Concurrent            Clean while people are home.    Go, Java G1/ZGC
                      Minimal disruption.
```

## Memory Leaks: When Cleaning Can't Help

```
A memory leak in GC'd languages:

  You have a box in the attic you'll NEVER open again.
  But your to-do list says "box in attic — might need someday."
  The housekeeper sees it's on the list → doesn't throw it out.
  The box stays forever, taking up space.

In code:
  // This slice grows forever — items are referenced so GC can't collect them
  var cache []Result

  func handleRequest(r Request) {
      result := processRequest(r)
      cache = append(cache, result)  // Never removed!
      // GC sees cache → sees all results → all "in use"
      // Memory grows until OOM
  }

Fix: remove references you don't need anymore
  // Use a bounded cache with eviction
  var cache = lru.New(1000)  // Max 1000 items, oldest evicted
```

## Where the Analogy Breaks Down

```
1. COMPACTION (defragmentation):
   After cleaning, stuff is scattered across rooms.
   GC can "compact" — move all live objects together.
   House equivalent: rearranging ALL furniture into fewer rooms.
   (This doesn't map well — houses don't work this way)

2. STACK vs HEAP:
   Local variables (stack) = stuff in your hands, auto-dropped when you leave
   Heap allocations = stuff placed in rooms, needs GC to clean up
   (In houses, all stuff is "in rooms" — there's no hand-holding equivalent)

3. FINALIZATION:
   Some objects need special cleanup (close files, release locks).
   Like hazardous waste — can't just throw it in the bin.
   GC must run special cleanup code before freeing.
```

## Practical Go Implications

```go
// Go's GC is concurrent and low-pause. But you still care because:

// 1. ALLOCATION RATE matters
// More allocations = more work for GC = more CPU spent cleaning
func badLoop() {
    for i := 0; i < 1000000; i++ {
        s := fmt.Sprintf("item-%d", i)  // Allocates a new string each time
        process(s)
    }
}

// 2. Reduce allocations with sync.Pool or pre-allocation
var bufPool = sync.Pool{
    New: func() interface{} { return new(bytes.Buffer) },
}
func betterLoop() {
    buf := bufPool.Get().(*bytes.Buffer)
    defer bufPool.Put(buf)
    // Reuse buffer instead of allocating new ones
}

// 3. GOGC environment variable controls GC frequency
// GOGC=100 (default): GC when heap doubles
// GOGC=200: GC when heap triples (less frequent, more memory used)
// GOGC=50: GC when heap grows 50% (more frequent, less memory)
```'''
    ),
    (
        "thinking/analogy-middleware-to-airport-security",
        "What is middleware in web frameworks? I see it in Express, Django, FastAPI — everyone uses it but I don't understand what it actually does or why I'd write my own.",
        r'''<think>
Middleware — the airport security analogy works perfectly because:
- Requests pass through multiple checkpoints in order
- Each checkpoint can inspect, modify, or reject the request
- The order matters
- Each checkpoint has a specific job

**Airport security mapping:**
1. Ticket check (authentication middleware) — do you have valid credentials?
2. Passport control (authorization middleware) — are you allowed to enter this area?
3. Baggage screening (input validation middleware) — is your data safe?
4. Metal detector (rate limiting middleware) — are you sending too many requests?
5. Customs (CORS middleware) — are you coming from an allowed origin?

Each checkpoint:
- Inspects the passenger/request
- May modify (stamp passport = add headers)
- May reject (no ticket = 401 unauthorized)
- Passes to the next checkpoint

**Where analogy works:**
- Linear pipeline: each middleware runs in order ✓
- Can short-circuit: reject without reaching the destination ✓
- Response passes back through: like going through customs on the way OUT too ✓
- Order matters: you check tickets before scanning bags ✓

**Where it breaks down:**
- Airport security is rigid; middleware is highly customizable
- Middleware can run code both BEFORE and AFTER the handler (request/response)
- Error middleware can catch and handle problems from downstream
</think>

Think of middleware like **airport security checkpoints**. Every request (passenger) must pass through them in order before reaching the destination (your route handler).

## The Analogy

```
WITHOUT MIDDLEWARE:
  Passenger walks directly from parking lot to airplane.
  No checks. Anyone can board any flight. Chaos.

WITH MIDDLEWARE (airport security):
  Parking lot
    → Ticket check         (authentication: who are you?)
    → Passport control     (authorization: are you allowed?)
    → Baggage screening    (input validation: is your data safe?)
    → Metal detector       (rate limiting: too many trips today?)
    → Gate                 (your route handler)
    → Board airplane       (response sent)

Each checkpoint can:
  ✓ INSPECT the passenger/request (read headers, body, cookies)
  ✓ MODIFY the passenger/request (stamp passport = add user info to request)
  ✓ REJECT and send home         (no ticket = 401 Unauthorized)
  ✓ PASS to the next checkpoint  (call next())
```

## In Code: What Middleware Actually Looks Like

```python
# FastAPI / Starlette middleware

# Each middleware wraps the next one like layers of an onion:
#
#   Request →  [Logging]  →  [Auth]  →  [RateLimit]  →  Handler
#   Response ← [Logging]  ←  [Auth]  ←  [RateLimit]  ←  Handler

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    # BEFORE: request arrives (passenger enters checkpoint)
    start_time = time.time()
    print(f"→ {request.method} {request.url}")

    response = await call_next(request)  # Pass to next checkpoint

    # AFTER: response returns (passenger leaves)
    duration = time.time() - start_time
    print(f"← {response.status_code} ({duration:.2f}s)")
    return response


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Ticket check: do you have valid credentials?
    token = request.headers.get("Authorization")

    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)  # No ticket needed for public areas

    if not token:
        return JSONResponse(status_code=401, content={"error": "No ticket"})
        # REJECTED — never reaches the gate (handler)

    user = verify_token(token)
    request.state.user = user  # Stamp passport — add user info for later checkpoints
    return await call_next(request)
```

```javascript
// Express middleware — same concept

// Logging checkpoint
app.use((req, res, next) => {
    console.log(`→ ${req.method} ${req.url}`);
    next();  // Pass to next checkpoint
});

// Auth checkpoint
app.use((req, res, next) => {
    const token = req.headers.authorization;
    if (!token) return res.status(401).json({ error: "No ticket" });

    const user = verifyToken(token);
    req.user = user;  // Stamp passport
    next();           // Pass to next checkpoint
});

// Rate limiting checkpoint
app.use(rateLimit({ windowMs: 60000, max: 100 }));

// THE GATE (your actual route handler — the destination)
app.get('/api/orders', (req, res) => {
    // By the time we get here, we KNOW:
    // - Request is logged ✓
    // - User is authenticated ✓
    // - Rate limit not exceeded ✓
    const orders = getOrdersForUser(req.user.id);
    res.json(orders);
});
```

## Order Matters (Just Like Airport Security)

```
CORRECT ORDER:
  1. CORS          → "Are you coming from an allowed origin?"
  2. Rate limiting → "Too many requests?"
  3. Body parsing  → "Parse the request body"
  4. Authentication→ "Who are you?"
  5. Authorization → "Are you allowed to do this?"
  6. Validation    → "Is your data valid?"
  7. Handler       → "Process the request"

WRONG ORDER:
  Body parsing AFTER authentication
    → Auth middleware can't read the request body
  Rate limiting AFTER authentication
    → Attacker floods login endpoint (auth hasn't run yet)
  CORS AFTER everything
    → Browser blocks the response anyway, wasted all that processing
```

## Why Write Your Own Middleware

```python
# Common custom middleware examples:

# 1. Request ID tracking (trace requests through microservices)
@app.middleware("http")
async def request_id_middleware(request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

# 2. Database transaction per request
@app.middleware("http")
async def db_transaction_middleware(request, call_next):
    async with db.transaction():
        response = await call_next(request)
        if response.status_code >= 400:
            raise Rollback()
        return response

# 3. Tenant isolation (multi-tenant SaaS)
@app.middleware("http")
async def tenant_middleware(request, call_next):
    tenant = get_tenant_from_subdomain(request.url.hostname)
    if not tenant:
        return JSONResponse(404, {"error": "Unknown tenant"})
    request.state.tenant = tenant
    set_database_schema(tenant.schema_name)
    return await call_next(request)
```

## Where the Analogy Breaks Down

```
1. RESPONSE PROCESSING:
   Airport: you don't go through security again when LEAVING.
   Middleware: runs on the way OUT too (add headers, log response time).
   Middleware is more like a two-way tunnel than a one-way checkpoint.

2. ERROR HANDLING:
   Airport: if you get sick at the gate, security doesn't handle it.
   Middleware: error middleware catches exceptions from downstream
   and can transform them into proper error responses.

3. ROUTE-SPECIFIC MIDDLEWARE:
   Airport: everyone goes through the same checkpoints.
   Code: you can apply middleware to specific routes only.
   app.get('/admin', adminOnly, handler)  // Only this route
```'''
    ),
    (
        "thinking/analogy-container-orchestration-to-restaurant-chain",
        "I understand Docker containers but I don't get why I need Kubernetes. My Docker Compose setup works fine. When does Kubernetes actually make sense?",
        r'''<think>
Docker Compose vs Kubernetes — the restaurant analogy works here.

**Restaurant chain analogy:**
- Docker container = a standardized restaurant kitchen (consistent food regardless of location)
- Docker Compose = running one restaurant with multiple kitchens (one location, all services together)
- Kubernetes = managing a CHAIN of restaurants (multiple locations, scaling, failover)

**When you have ONE restaurant (Docker Compose):**
- You manage everything yourself
- If the oven breaks, you fix it
- If it's a busy night, you're stuck with the kitchen you have
- If you close for renovations, customers can't eat

**When you have a CHAIN (Kubernetes):**
- Central management decides: how many restaurants per city, which menu, staffing levels
- If one restaurant burns down, others absorb the customers automatically
- Busy weekend? Open a pop-up location automatically
- Renovating one location? Redirect customers to the nearest one seamlessly

**When do you NEED a chain manager (K8s)?**
- One restaurant: Docker Compose is perfect. Don't over-engineer.
- 2-5 locations that rarely change: still probably fine without K8s
- 10+ locations with variable demand: you need orchestration

**Where analogy maps:**
- Pods = individual kitchen stations
- Deployments = recipe + staffing plan
- Services = the restaurant's phone number (doesn't change when staff changes)
- Horizontal Pod Autoscaler = opening more stations when it's busy
- Health checks = manager walking around checking if kitchens are operational
- Rolling updates = renovating one kitchen at a time, never closing the restaurant

**Where it breaks down:**
- Networking in K8s is more complex than restaurant logistics
- ConfigMaps/Secrets don't have a clean restaurant equivalent
- The K8s learning curve is massive compared to managing a few restaurants
</think>

Think of it this way: Docker Compose is running **one restaurant**. Kubernetes is managing a **restaurant chain**.

## The Analogy

```
DOCKER CONTAINER:
  A standardized kitchen in a shipping container.
  Same equipment, same recipes, works identically everywhere.
  "It works on my machine" → "It works in any container."

DOCKER COMPOSE:
  One restaurant building with multiple kitchens:
    - Grill station (web server)
    - Prep station (database)
    - Dessert station (cache)
  All in one location, you manage everything manually.
  Perfect for one restaurant.

KUBERNETES:
  A restaurant chain management system:
    - "We need 5 grill stations across 3 locations" (replicas)
    - "If a station breaks, replace it automatically" (self-healing)
    - "Friday night rush? Open 10 more stations" (auto-scaling)
    - "New recipe? Roll it out one kitchen at a time" (rolling updates)
    - "Station caught fire? Redirect orders to others" (failover)
```

## Docker Compose: When It's Enough

```yaml
# docker-compose.yml — your single restaurant
services:
  web:
    image: myapp:latest
    ports: ["8080:8080"]
  db:
    image: postgres:16
    volumes: ["pgdata:/var/lib/postgresql/data"]
  redis:
    image: redis:7

# This is FINE when:
#   ✓ One server handles all traffic
#   ✓ You can tolerate downtime during deploys
#   ✓ You manually SSH in to fix problems
#   ✓ Traffic is predictable (no sudden spikes)
#   ✓ One instance of each service is sufficient
```

```
Docker Compose limitations (one restaurant problems):

  "Web container crashed at 3 AM"
  → Nobody restarts it until morning. Site is down.
  Docker Compose: no automatic recovery

  "Black Friday traffic is 10x normal"
  → Can't add more web containers dynamically.
  Docker Compose: manual scaling only (docker compose up --scale web=3)
  But no load balancer, no health checks, no auto-scaling.

  "Need to deploy new version"
  → docker compose down, docker compose up
  → 30 seconds of downtime every deploy.
  Docker Compose: no zero-downtime deployments built in.
```

## Kubernetes: When You Need It

```
Kubernetes solves the CHAIN problems:

1. SELF-HEALING (replace broken kitchens automatically)
   Container crashes → K8s restarts it in seconds
   Server dies → K8s moves containers to healthy servers
   You: sleeping at 3 AM, unaware anything happened

2. SCALING (open/close kitchens based on demand)
   CPU > 70% → K8s adds more containers automatically
   Traffic drops → K8s removes extra containers (saves money)
   Black Friday → handles 10x spike without human intervention

3. ZERO-DOWNTIME DEPLOYS (renovate one kitchen at a time)
   Deploy v2: K8s starts new containers with v2
              → health check passes → route traffic to v2
              → stop old v1 containers
   Users never see downtime.

4. SERVICE DISCOVERY (the restaurant's phone number never changes)
   Web app calls "database:5432" — K8s routes to the right container
   Container IP changes? Doesn't matter — the name stays the same.
```

## The Decision Framework

```
YOU NEED DOCKER COMPOSE WHEN:
  ✓ 1 server, < 10 containers
  ✓ Downtime during deploys is acceptable
  ✓ Traffic is predictable
  ✓ You or someone is available to fix problems manually
  ✓ Budget is tight (K8s has overhead)
  → Most side projects, small apps, dev environments

YOU NEED KUBERNETES WHEN:
  ✓ Multiple servers (can't fit on one machine)
  ✓ Zero-downtime deployments required
  ✓ Auto-scaling needed (variable traffic)
  ✓ Self-healing required (can't have 3 AM incidents)
  ✓ Multiple teams deploying independently
  → Production services with SLAs, multiple microservices

YOU MIGHT WANT SOMETHING IN BETWEEN:
  ✓ Docker Swarm (simpler orchestration, built into Docker)
  ✓ Managed platforms (Railway, Fly.io, Render)
  ✓ AWS ECS / Google Cloud Run (container orchestration without K8s complexity)
  → When you need some orchestration but K8s is overkill
```

## Cost of Kubernetes (Why Not to Use It Prematurely)

```
Docker Compose overhead:
  Learning: 1 day
  Config: 1 YAML file
  Operations: docker compose up/down
  Infrastructure: 1 server

Kubernetes overhead:
  Learning: weeks to months
  Config: 10-50+ YAML files (Deployments, Services, Ingress,
          ConfigMaps, Secrets, HPA, PDB, NetworkPolicies...)
  Operations: kubectl, Helm charts, monitoring stack
  Infrastructure: minimum 3 nodes for HA (control plane)
  Cost: $200+/month for managed K8s (EKS, GKE, AKS)

If your Docker Compose setup handles your traffic,
and you can tolerate brief downtime during deploys,
stay with Docker Compose. Kubernetes is a tool for problems
you may not have yet.
```

## Where the Analogy Breaks Down

```
1. NETWORKING:
   Restaurant chain: customers just walk in.
   K8s: complex overlay networks, service meshes, ingress controllers.
   Network configuration is K8s's steepest learning curve.

2. STATE:
   Restaurant: food is consumed (stateless).
   K8s: databases need persistent storage — StatefulSets, PVCs.
   Running stateful workloads on K8s is significantly harder.

3. CONFIGURATION:
   Restaurant chain: standard menu is simple to distribute.
   K8s: ConfigMaps, Secrets, environment variables, Helm values.
   Configuration management in K8s is its own discipline.
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
