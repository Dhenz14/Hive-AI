"""Phase 2C: Advanced Reasoning — Analogical Reasoning (Part 3/5)
Map concepts between domains, note where the analogy breaks:
garbage collection↔city sanitation, pub/sub↔radio broadcasting, mutex↔bathroom key,
API gateway↔hotel concierge, container↔shipping container."""

PAIRS = [
    (
        "thinking/analogy-gc-sanitation",
        "Can you explain garbage collection in programming? I understand the concept but not why there are different algorithms or why it sometimes causes pauses.",
        r'''<think>
Let me map garbage collection to city sanitation to make this intuitive.

The analogy: Memory management ↔ City waste management

Objects in memory ↔ Buildings in a city
- When you create an object, you "build" a structure that takes up space
- When you're done with it, it should be demolished and the land reclaimed
- If nobody demolishes old buildings, the city fills up (memory leak)

Manual memory management (C/C++) ↔ Property owners demolish their own buildings
- Each owner is responsible for tearing down their building when done
- Problem: owner forgets (memory leak) or demolishes while someone else is inside (use-after-free)
- Very efficient when done right, but errors are catastrophic

Garbage collection ↔ City sanitation department
- The city hires a department to find and demolish unused buildings
- Programmers don't have to think about cleanup — the GC handles it
- But the department needs time and resources to do its job

Now let me map the GC algorithms:

Reference counting ↔ Tracking how many people are in each building
- Each building has a counter: +1 when someone enters, -1 when they leave
- When counter hits 0, building is empty → demolish immediately
- Problem: two buildings with people who ONLY visit each other (circular reference)
  → Counter never reaches 0, but nobody from outside uses either building
  → City can't reclaim them
- Real example: Python uses reference counting + cycle detector

Mark-and-sweep ↔ City-wide building inspection
- Inspector starts from "important" buildings (city hall, hospitals = GC roots: stack, globals)
- Follows all roads from important buildings, marks every reachable building as "in use"
- Any building NOT marked = abandoned → demolish it
- Problem: during inspection, all construction must stop (stop-the-world pause)
  → Imagine the whole city freezing for 10 minutes while inspectors work
- Real example: Basic GC in older Java

Generational GC ↔ Inspecting new construction sites more often
- Observation: most buildings are temporary (pop-up shops, events)
  → They go up and come down quickly
- Permanent buildings (city hall, library) rarely need inspection
- Strategy: inspect the "new construction" zone frequently (young generation),
  inspect the "established" zone rarely (old generation)
- Buildings that survive multiple inspections get moved to "established" zone
- Real example: Java G1 GC, .NET GC

Concurrent GC ↔ Inspectors work while the city operates
- Instead of freezing the whole city, inspectors work alongside normal operations
- They might miss a building that just became empty, but they'll catch it next round
- Trade-off: inspections take longer total, but no city-wide freeze
- Real example: Java ZGC, Go's GC

Where the analogy breaks:
1. Memory is uniform — all "land" is equivalent. Real cities have valuable vs cheap land.
2. Compaction: GC can move objects to eliminate fragmentation. You can't easily move real buildings.
3. Speed: GC pauses are milliseconds to seconds. City operations are much slower.
4. Determinism: GC timing is unpredictable. City inspections are scheduled.

But the core insight holds: GC is about automatically finding and reclaiming resources that are no longer reachable from any active part of the program.
</think>

Think of garbage collection like a city sanitation department managing buildings. The analogy maps surprisingly well to different GC algorithms.

**The core mapping:**

| Programming | City |
|-------------|------|
| Memory | Land |
| Objects | Buildings |
| Allocation | Construction |
| GC roots (stack, globals) | Essential buildings (city hall) |
| Reachable objects | Buildings connected by roads to city hall |
| Garbage | Abandoned buildings nobody visits |

**Manual memory (C) = owners demolish their own buildings:**

```c
Building* b = build();  // Owner constructs
use(b);
demolish(b);            // Owner must remember to demolish
// If they forget → building sits empty forever (memory leak)
// If they demolish while someone's inside → crash (use-after-free)
```

**Reference counting = count how many people are in each building:**

```python
# Python uses this: each object has a refcount
a = [1, 2, 3]    # Building A: refcount = 1
b = a             # b also points to A: refcount = 2
del a             # refcount = 1 (still in use via b)
del b             # refcount = 0 → demolished immediately!

# The problem — circular references:
a = []
b = []
a.append(b)  # A references B (refcount 1)
b.append(a)  # B references A (refcount 1)
del a, b     # Refcounts are still 1 — never demolished!
# Two abandoned buildings whose only visitors are each other.
# Python needs a cycle detector to catch these.
```

**Mark-and-sweep = city-wide building inspection:**

```
Phase 1 (Mark): Start from city hall, follow all roads,
                mark every reachable building green.
Phase 2 (Sweep): Demolish every building that's NOT green.

Problem: City must FREEZE during inspection.
         → "Stop-the-world" pause. Nothing runs during GC.
```

**Generational GC = inspect new construction zones more often:**

```
Observation: 90% of objects die young (temporary variables,
             intermediate results). Like pop-up shops.

Strategy:
  Young Generation (nursery): Small, inspected frequently.
    Most objects die here → quick inspections, small pauses.

  Old Generation: Large, inspected rarely.
    Objects that survive 3+ inspections get promoted here.
    These are your long-lived caches, connection pools, etc.

// This is why Java has:
// -Xms (min heap), -Xmx (max heap)
// -XX:NewRatio (young:old ratio)
// -XX:MaxGCPauseMillis (target pause time)
```

**Why GC pauses matter in practice:**

```
Web server handling requests:
                                    ↓ 300ms GC pause
[req1][req2][req3][req4][req5][...........][req6][req7]

Users waiting 300ms+ experience: "The site is slow"
P99 latency spikes correlate with GC pauses.

Solutions:
1. Reduce allocation rate (fewer temporary objects)
2. Use a concurrent GC (Go, Java ZGC) — inspectors work during operation
3. Tune heap size — too small = frequent GC, too large = long pauses
```

**Where the analogy breaks down:**

1. **Compaction** — GC can move objects to eliminate gaps. You can't slide buildings around a city.
2. **Speed** — GC decides in nanoseconds per object. City planning takes months.
3. **Uniformity** — all memory bytes are equal. Real estate varies wildly in value.

The takeaway: GC trades deterministic performance for safety. You'll never have a use-after-free or memory leak (of reachable objects), but you'll occasionally pause while the inspector makes rounds.'''
    ),
    (
        "thinking/analogy-pubsub-radio",
        "I'm confused about pub/sub messaging. How is it different from just calling a function or making an API request?",
        r'''<think>
Let me map pub/sub to radio broadcasting to make the distinction clear.

Direct function call / API request ↔ Phone call
- Caller knows exactly who they're calling (tight coupling)
- Caller waits for the other person to pick up (synchronous, usually)
- One-to-one: one caller, one receiver
- If the receiver is unavailable, the call fails
- Both parties must be available at the same time

Pub/Sub ↔ Radio broadcasting
- Radio station (publisher) broadcasts a signal on a frequency (topic)
- Station doesn't know or care who's listening
- Listeners (subscribers) tune into frequencies they care about
- One-to-many: one broadcast reaches all listeners on that frequency
- Station broadcasts whether anyone is listening or not
- Listeners can tune in/out at any time without telling the station

The mapping:
- Publisher → Radio station
- Subscriber → Radio listener
- Topic/Channel → Radio frequency
- Message → Broadcast content
- Message broker (Kafka, RabbitMQ) → Radio tower/transmitter infrastructure

Key differences this reveals:

1. Coupling:
   Phone call: caller must know receiver's number (direct dependency)
   Radio: station broadcasts to a frequency, not to specific listeners (decoupled)

2. Cardinality:
   Phone call: 1-to-1
   Radio: 1-to-many (one message, many subscribers)

3. Timing:
   Phone call: synchronous (both parties present)
   Radio: can be asynchronous (with message persistence = like recording the broadcast)

4. Failure handling:
   Phone call: if receiver is down, caller gets an error
   Radio: if a listener's radio is off, they miss the broadcast (but station doesn't fail)

Where the analogy breaks:
1. Radio broadcasts are lossy (if you miss it, it's gone). Pub/sub systems often guarantee delivery through persistence.
2. Radio is truly one-way. Pub/sub can have acknowledgments.
3. Radio reaches anyone in range. Pub/sub requires explicit subscription.
4. In pub/sub, different subscribers can get different messages from the same topic (consumer groups in Kafka).

When to use which:
- Direct call (phone): when you need an immediate response, one specific receiver
- Pub/sub (radio): when you want to decouple sender from receiver(s), fire-and-forget, or fan-out
</think>

The difference is like a phone call vs. a radio broadcast.

**Phone call = Direct API request:**

```python
# OrderService directly calls InventoryService
# Like calling a specific phone number
class OrderService:
    def create_order(self, order):
        # I MUST know about InventoryService (tight coupling)
        inventory_service.reduce_stock(order.product_id, order.quantity)
        # I MUST wait for a response (synchronous)
        # If InventoryService is down, I fail too
        email_service.send_confirmation(order.user_email)
        # Now I also depend on EmailService
        analytics_service.track_purchase(order)
        # And AnalyticsService... coupling grows with each new requirement
```

**Radio broadcast = Pub/Sub:**

```python
# OrderService broadcasts "order created" — doesn't know who's listening
# Like a radio station broadcasting on a frequency
class OrderService:
    def create_order(self, order):
        db.save(order)
        # Broadcast to "orders" topic — that's it
        message_broker.publish("orders.created", {
            "order_id": order.id,
            "product_id": order.product_id,
            "quantity": order.quantity,
            "user_email": order.user_email,
        })
        # I don't know or care who listens

# Listeners tune in independently:
# InventoryService subscribes to "orders.created" → reduces stock
# EmailService subscribes to "orders.created" → sends confirmation
# AnalyticsService subscribes to "orders.created" → tracks purchase
# NEW: FraudService subscribes to "orders.created" → checks for fraud
# ^ Added without changing OrderService at all!
```

**The mapping:**

| Radio | Pub/Sub | Direct Call |
|-------|---------|-------------|
| Station broadcasts on FM 101.5 | Publisher sends to "orders" topic | Caller dials specific number |
| Anyone can tune to 101.5 | Any service can subscribe | Must know exact endpoint |
| Station doesn't know listeners | Publisher doesn't know subscribers | Caller knows receiver |
| 1000 listeners, same broadcast | 5 services, same message | 1 caller, 1 receiver |
| Listener's radio off? Station keeps going | Subscriber down? Publisher unaffected | Receiver down? Caller gets error |

**Practical example with Redis pub/sub:**

```python
# Publisher (radio station)
import redis
import json

r = redis.Redis()

def publish_order_created(order):
    r.publish("orders.created", json.dumps({
        "order_id": order.id,
        "product_id": order.product_id,
        "quantity": order.quantity,
    }))

# Subscriber 1: Inventory (different process/server)
def inventory_listener():
    pubsub = r.pubsub()
    pubsub.subscribe("orders.created")
    for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            reduce_stock(data["product_id"], data["quantity"])

# Subscriber 2: Email (yet another process/server)
def email_listener():
    pubsub = r.pubsub()
    pubsub.subscribe("orders.created")
    for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            send_order_confirmation(data["order_id"])
```

**Where the analogy breaks down:**

1. **Persistence** — Radio is ephemeral (miss it and it's gone). Kafka persists messages — subscribers can replay from any point. More like a DVR than live radio.
2. **Consumer groups** — In Kafka, multiple instances of InventoryService share the load (only one processes each message). Radio doesn't have this.
3. **Acknowledgment** — Pub/sub systems confirm delivery. Radio is truly fire-and-forget.
4. **Ordering** — Kafka guarantees order within a partition. Radio broadcasts are unordered.

**When to use which:**

```
Direct call when:
  ✓ You need an immediate response
  ✓ There's exactly one receiver
  ✓ Failure of the receiver should fail the caller

Pub/sub when:
  ✓ Multiple services need to react to the same event
  ✓ Publisher shouldn't depend on receivers
  ✓ Adding new reactions shouldn't change the publisher
  ✓ Operations can be asynchronous
```'''
    ),
    (
        "thinking/analogy-mutex-bathroomkey",
        "What's a mutex? I keep seeing it in threading documentation but the explanations are very abstract.",
        r'''<think>
The classic analogy: mutex ↔ bathroom key at a coffee shop.

The scenario:
- Coffee shop has one single-stall bathroom
- There's a key hanging by the counter
- To use the bathroom: take the key (acquire mutex)
- When done: return the key (release mutex)
- If someone has the key: you wait in line (thread blocked)

This maps perfectly:

Shared resource (e.g., a bank account balance) ↔ Bathroom
Mutex ↔ Key
Thread acquiring mutex ↔ Person taking the key
Thread releasing mutex ↔ Person returning the key
Thread waiting on mutex ↔ Person waiting in line
Critical section ↔ Time spent in bathroom

Why it's needed — without the key:
- Two people walk into the bathroom at the same time
- Chaos ensues (data corruption)
- In code: two threads both read balance=100, both subtract 50, both write 50
  → Balance should be 0 but is 50 (lost update)

The key properties of a mutex:
1. Mutual exclusion — only ONE person can have the key at a time
2. Non-preemptive — you can't force someone to give up the key (unless the OS kills the thread)
3. Bounded waiting — people waiting will eventually get the key (no starvation)

Where the analogy extends:

Deadlock ↔ Two keys, two bathrooms:
- Person A has key to bathroom 1, needs bathroom 2
- Person B has key to bathroom 2, needs bathroom 1
- Both wait forever for the other's key
- Only solution: always acquire keys in the same order

Recursive/reentrant mutex ↔ Key that recognizes the holder:
- If you already have the key and need to "enter" again (recursive function call)
- A regular mutex would deadlock (you're waiting for yourself!)
- A reentrant mutex says "oh you already have it, go ahead"

Read-write lock ↔ Museum vs. renovation:
- Multiple visitors can view (read) at the same time
- But renovation (write) requires exclusive access
- RWLock: many readers OR one writer, not both

Where the analogy breaks:
1. Mutex has no physical constraint — you can "forget" to return the key (forgetting to unlock → deadlock)
2. Priority inversion — a low-priority thread holds the key while a high-priority thread waits (not intuitive with bathrooms)
3. Performance — waiting for a mutex doesn't mean sitting idle; the OS can schedule other threads
</think>

A mutex is exactly like the single bathroom key at a coffee shop.

**The setup:**

```
Coffee shop bathroom:        Code equivalent:
┌─────────────────────┐     ┌─────────────────────┐
│ One bathroom (shared │     │ One bank account     │
│ resource)            │     │ (shared variable)    │
│                      │     │                      │
│ One key on hook      │     │ One mutex             │
│ (mutex)              │     │                      │
│                      │     │                      │
│ Take key to enter    │     │ Lock mutex to access  │
│ Return key when done │     │ Unlock when done      │
│ Wait if key is taken │     │ Block if locked       │
└─────────────────────┘     └─────────────────────┘
```

**Without the key (no mutex) — disaster:**

```python
# Two threads accessing shared bank balance simultaneously
balance = 100

# Thread A: withdraw 50         # Thread B: withdraw 50
read = balance  # sees 100      read = balance  # sees 100 (SAME TIME!)
balance = read - 50  # = 50     balance = read - 50  # = 50

# Final balance: 50 (should be 0!)
# $50 appeared from nowhere — you lost an update
```

**With the key (mutex) — safe:**

```python
import threading

balance = 100
key = threading.Lock()  # The bathroom key

# Thread A                      # Thread B
key.acquire()  # Takes key      # key.acquire()  ← WAITS (key is taken)
read = balance  # 100           #   ... waiting ...
balance = read - 50  # 50      #   ... waiting ...
key.release()  # Returns key    # key.acquire()  ← Got the key!
                                # read = balance  # 50
                                # balance = read - 50  # 0
                                # key.release()  ← Returns key

# Final balance: 0 ✓ Correct!
```

**In practice — always use context managers:**

```python
lock = threading.Lock()
balance = 100

def withdraw(amount):
    # "with lock" = take key, do your business, return key automatically
    # Even if an exception occurs, key is returned (no forgotten keys!)
    with lock:
        current = balance
        # Only one thread can be in here at a time
        balance = current - amount

# This is the same as:
def withdraw_manual(amount):
    lock.acquire()      # Take the key
    try:
        current = balance
        balance = current - amount
    finally:
        lock.release()  # ALWAYS return the key, even on error
```

**Extended analogies:**

```python
# DEADLOCK = two keys, two bathrooms, circular waiting
lock_a = threading.Lock()  # Key to bathroom A
lock_b = threading.Lock()  # Key to bathroom B

# Thread 1:                    # Thread 2:
lock_a.acquire()  # Has key A  lock_b.acquire()  # Has key B
lock_b.acquire()  # Wants B    lock_a.acquire()  # Wants A ← DEADLOCK!
# Both waiting for each other forever.
# Fix: always acquire locks in the same order (A then B)

# READ-WRITE LOCK = museum with renovation days
rw_lock = threading.RWLock()  # (pseudocode — use rwlock library)
# Multiple visitors (readers) can be in the museum simultaneously
# But renovation (writing) requires kicking everyone out

# SEMAPHORE = bathroom with 3 stalls
semaphore = threading.Semaphore(3)  # 3 keys available
# Up to 3 threads can be inside simultaneously
# 4th thread must wait until one finishes
```

**Where the analogy breaks:**

| Analogy says | Reality |
|---|---|
| You physically can't enter without the key | Code CAN access the variable without locking — it'll just be buggy |
| Waiting means standing in line | Waiting thread is put to sleep by the OS, using no CPU |
| Keys can't be duplicated | A bug can create two locks for the same resource (bad) |
| You always remember to return the key | Forgetting `lock.release()` = permanent deadlock |

That last point is why `with lock:` is critical — it returns the key even if your code throws an exception.'''
    ),
    (
        "thinking/analogy-apigateway-concierge",
        "What's an API gateway and why do I need one? My microservices already have their own endpoints.",
        r'''<think>
Let me map API gateway to a hotel concierge.

Without an API gateway ↔ Hotel with no front desk:
- Guest wants dinner reservation → walks around looking for the restaurant
- Guest wants room service → walks to the kitchen
- Guest wants pool towels → walks to the laundry room
- Guest must know where everything is, talk to each department directly
- No one checks if the guest is actually a guest (security gap)
- Each department logs visits differently (no unified records)

With an API gateway ↔ Hotel concierge:
- Guest tells the concierge what they need
- Concierge knows where everything is and routes the request
- Concierge checks the guest's room key first (authentication)
- Concierge handles "the restaurant is closed" gracefully (error handling)
- Concierge can limit requests ("you've asked 10 times in a minute, slow down")
- One point of contact instead of the guest knowing the hotel's internal layout

The mapping:
- API Gateway ↔ Hotel concierge
- Client (browser/app) ↔ Hotel guest
- Microservices ↔ Hotel departments (kitchen, housekeeping, restaurant)
- Routing ↔ Concierge knowing which department handles what
- Authentication ↔ Checking room key
- Rate limiting ↔ "One request at a time, please"
- Request transformation ↔ Translating guest's request to department's language
- Load balancing ↔ "Restaurant A is full, let me send you to Restaurant B"

Benefits this reveals:
1. Clients only need to know ONE address (the concierge desk)
2. Internal layout can change without guests knowing
3. Cross-cutting concerns (auth, logging, rate limiting) in one place
4. Can aggregate multiple department responses into one

Where the analogy breaks:
1. A concierge is a bottleneck — a gateway can handle millions of requests/sec
2. A concierge adds significant delay — a well-configured gateway adds < 1ms
3. A concierge is a single person — gateways are distributed and redundant
4. Unlike a concierge, the gateway can transform requests/responses in complex ways (GraphQL, protocol translation)
</think>

Think of an API gateway like a hotel concierge. Without one, guests (clients) have to find every department (service) themselves.

**Without a gateway — clients know your internal layout:**

```
Mobile App ──→ user-service:8001/users/42
           ──→ order-service:8002/orders?user=42
           ──→ payment-service:8003/payments/status
           ──→ notification-service:8004/preferences

Problems:
- Client knows 4 different URLs (tight coupling to internal architecture)
- Each service implements its own auth check (duplicated, inconsistent)
- No centralized rate limiting, logging, or error handling
- Can't reorganize services without breaking ALL clients
- Mobile app on slow network makes 4 separate HTTP requests
```

**With a gateway — one door, everything behind it:**

```
Mobile App ──→ api.myapp.com/users/42        ──→ user-service
           ──→ api.myapp.com/orders?user=42  ──→ order-service
           ──→ api.myapp.com/payments/status  ──→ payment-service
           ──→ api.myapp.com/notifications    ──→ notification-service

The gateway handles:
✓ Routing (which service handles /users?)
✓ Authentication (verify JWT once, not in every service)
✓ Rate limiting (100 req/min per user)
✓ Logging (every request, one format)
✓ CORS (one config, not per-service)
```

**Practical setup with Kong or NGINX:**

```yaml
# kong.yml — declarative API gateway configuration
services:
  - name: user-service
    url: http://user-service:8001
    routes:
      - paths: ["/api/users"]
        strip_path: false

  - name: order-service
    url: http://order-service:8002
    routes:
      - paths: ["/api/orders"]
        strip_path: false

  - name: payment-service
    url: http://payment-service:8003
    routes:
      - paths: ["/api/payments"]
        strip_path: false

plugins:
  # Auth: verify JWT on ALL routes
  - name: jwt
    config:
      secret_is_base64: false

  # Rate limiting: global
  - name: rate-limiting
    config:
      minute: 100
      policy: redis

  # Logging: unified request logs
  - name: http-log
    config:
      http_endpoint: http://log-collector:9000/logs

  # CORS: one config
  - name: cors
    config:
      origins: ["https://myapp.com"]
      methods: ["GET", "POST", "PUT", "DELETE"]
```

**Or a lightweight Python gateway (FastAPI):**

```python
# gateway.py — simple reverse proxy with auth
import httpx
from fastapi import FastAPI, Request, Depends

app = FastAPI()

SERVICE_MAP = {
    "/api/users": "http://user-service:8001",
    "/api/orders": "http://order-service:8002",
    "/api/payments": "http://payment-service:8003",
}

async def verify_auth(request: Request):
    """Authenticate once at the gateway — services trust internal traffic."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(401, "Missing token")
    user = decode_jwt(token)  # Verify JWT signature + expiry
    return user

@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(request: Request, path: str, user=Depends(verify_auth)):
    # Find the right backend service
    for prefix, service_url in SERVICE_MAP.items():
        if f"/api/{path}".startswith(prefix):
            target = f"{service_url}/api/{path}"
            break
    else:
        raise HTTPException(404, "Service not found")

    # Forward the request, adding internal auth header
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=request.method,
            url=target,
            headers={"X-User-ID": str(user.id)},  # Internal auth
            content=await request.body(),
            params=request.query_params,
        )

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers),
    )
```

**The concierge analogy mapping:**

| Hotel | API Gateway |
|-------|------------|
| Guest asks concierge | Client sends request to gateway |
| Concierge checks room key | Gateway verifies JWT |
| "Restaurant is on floor 3" | Route /api/orders → order-service:8002 |
| "Restaurant is closed, try room service" | Circuit breaker, fallback |
| "One request at a time please" | Rate limiting |
| Concierge logs all requests | Centralized access logs |
| Guest doesn't know kitchen location | Client doesn't know service addresses |

**Where the analogy breaks:**
A concierge is a bottleneck and single point of failure. A production API gateway is horizontally scaled (multiple instances behind a load balancer) and adds sub-millisecond latency. It's more like having 50 concierges who all share the same knowledge.'''
    ),
    (
        "thinking/analogy-container-shipping",
        "Why do I need Docker containers? My app runs fine on my machine.",
        r'''<think>
The shipping container analogy for Docker is the canonical one — and it's actually where the name comes from (the Docker logo is a whale carrying containers).

Before shipping containers (before Docker):
- Every type of cargo (furniture, fruit, electronics, chemicals) needed different handling
- Loading a ship was a nightmare — different shapes, sizes, fragilities
- Moving cargo from ship → truck → train required re-packing at every step
- "This piano was fine in the warehouse but broke during shipping"
  ↔ "Works on my machine but breaks in production"

After shipping containers (with Docker):
- Everything goes in a standard box (20ft or 40ft container)
- Ship, truck, and train all handle the same box
- What's inside doesn't matter — the BOX is the interface
- Load container at factory, unload at destination — no re-packing
- ↔ Build container once, runs the same everywhere

Mapping:
- Shipping container ↔ Docker container
- Cargo (furniture, fruit) ↔ Application + dependencies
- Container standard (size, corners, locking) ↔ Docker image format
- Port/crane infrastructure ↔ Docker runtime / Kubernetes
- Ship/truck/train ↔ Dev laptop / CI server / production server
- Bill of lading (manifest) ↔ Dockerfile

The "works on my machine" problem:
Before containers, deploying meant:
- "Install Python 3.9" — which minor version? What about system Python?
- "Install these packages" — pip install worked yesterday, today a dependency updated and broke
- "Set these env vars" — which ones? Were they documented?
- "Oh and you need libpq-dev, ffmpeg, and this specific version of OpenSSL"

With containers:
- Dockerfile specifies EXACTLY what's inside
- Image is built once with all dependencies frozen
- Same image runs on laptop, CI, staging, production
- No more "but I have Python 3.10 and you have 3.9"

Where the analogy breaks:
1. Shipping containers are static. Docker containers can be started/stopped/restarted in seconds.
2. You can't run multiple copies of the same physical container. You can run 10 instances of the same Docker image.
3. Shipping containers are heavy. Docker containers share the host OS kernel — they're lightweight.
4. Docker containers can communicate through virtual networks. Shipping containers don't network with each other.
5. Docker images have LAYERS — like building with transparent overlapping sheets. No physical analog.
</think>

The answer is literally in Docker's name — it's a shipping container for software. The analogy is nearly perfect.

**Before shipping containers = before Docker:**

```
Moving goods from factory to store:

Factory:  "Here's a piano, 50 bags of rice, and some chemicals"
Dock:     "How do we load these? Different sizes, different handling..."
Ship:     "The piano broke in transit. Rice got wet. Who packed this?"
Truck:    "These don't fit. We need to repack for the highway."
Store:    "We got the wrong chemicals. Where's the piano?"

= Your deployment:
Dev:      "pip install flask sqlalchemy pillow"
Staging:  "pillow needs libjpeg-dev... which isn't installed here"
CI:       "Tests pass with Python 3.9 but prod has 3.8"
Prod:     "Missing environment variable. Missing system library. Wrong config."
```

**After shipping containers = with Docker:**

```
Standard box. Doesn't matter what's inside.
Load at factory → ship → truck → warehouse. Never re-packed.

Standard image. Doesn't matter what's inside.
Build once → test → deploy. Never re-configured.
```

**The Dockerfile = packing list:**

```dockerfile
# "What goes in the container" — explicit and reproducible
FROM python:3.11-slim

# System dependencies — locked
RUN apt-get update && apt-get install -y libpq-dev

# Python dependencies — locked via requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . /app
WORKDIR /app

# How to run it
CMD ["gunicorn", "myapp:app", "-w", "4", "-b", "0.0.0.0:8000"]
```

```bash
# Build once:
docker build -t myapp:v1.2.3 .

# This EXACT image runs identically on:
docker run myapp:v1.2.3  # Your laptop
docker run myapp:v1.2.3  # CI server
docker run myapp:v1.2.3  # Staging
docker run myapp:v1.2.3  # Production

# "Works on my machine" → "Works in this container" → works everywhere
```

**The analogy mapped:**

| Shipping | Docker | Why it matters |
|----------|--------|---------------|
| Standard container (20ft box) | Docker image | Same interface everywhere |
| Cargo inside | App + dependencies | Contents don't affect handling |
| Pack at factory | `docker build` | Lock everything in once |
| Bill of lading | Dockerfile | Explicit manifest |
| Port crane | Docker runtime | Knows how to handle containers |
| Ship / truck / train | Laptop / CI / production | All handle the same container |
| Container yard | Docker registry (Docker Hub) | Store and distribute containers |

**The real problems Docker solves:**

```python
# Problem 1: "Works on my machine"
# Your laptop: Python 3.11, Ubuntu 22.04, libpq 14
# Production:  Python 3.9, Amazon Linux, libpq 12
# With Docker: Both run the SAME image. Identical environment.

# Problem 2: Dependency conflicts
# App A needs numpy 1.24
# App B needs numpy 1.21
# Without Docker: Can't run both on same server
# With Docker: Each in its own container with its own numpy

# Problem 3: "Just install these 47 things"
# Without Docker: 3-page setup guide that's always outdated
# With Docker: docker-compose up (done)
```

**docker-compose for multi-service apps:**

```yaml
# One command to run your entire stack
services:
  web:
    build: .
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql://user:pass@db/myapp
    depends_on: [db, redis]

  db:
    image: postgres:16
    volumes: [pgdata:/var/lib/postgresql/data]

  redis:
    image: redis:7

volumes:
  pgdata:
```

```bash
docker compose up  # Entire stack running in seconds
# New developer onboarding: clone repo → docker compose up → done
```

**Where the analogy breaks down:**

1. **Ephemeral** — Shipping containers persist. Docker containers are disposable — destroy and recreate in seconds.
2. **Copies** — You can't clone a shipping container. You can run 100 instances of one Docker image.
3. **Lightweight** — Docker containers share the host OS kernel. They're not VMs. Starting a container takes ~100ms, not minutes.
4. **Layers** — Docker images are built in layers (base OS, dependencies, code). Changed code? Only rebuild the code layer. No physical equivalent.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
