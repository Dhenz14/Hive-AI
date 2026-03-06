"""Phase 2C: Advanced Reasoning — Analogical Reasoning (Part 1/4)
Transfer knowledge between domains. Circuit breaker ↔ fuse, DB index ↔ book index,
backpressure ↔ traffic, DI ↔ outlets, git ↔ parallel universes."""

PAIRS = [
    (
        "thinking/analogy-circuit-breaker-fuse",
        "I keep hearing about the 'circuit breaker pattern' for microservices. Can you explain it? I'm an electrical engineer so I know about real circuit breakers.",
        r'''<think>
The user has a background in electrical engineering — perfect for this analogy. Let me map the concepts carefully.

In electrical systems:
- A circuit breaker monitors current flow
- If current exceeds a threshold (overload/short circuit), the breaker TRIPS (opens the circuit)
- This prevents damage to wiring and devices
- After the issue is fixed, you manually reset the breaker
- Some breakers have auto-reset with a cooldown

In software:
- The circuit breaker monitors service call failures
- If failures exceed a threshold, the breaker TRIPS (stops making calls)
- This prevents cascade failures and wasted resources
- After a timeout, it allows a "test" call through (half-open)
- If the test succeeds, the breaker closes (normal operation resumes)

Let me map the states:
- CLOSED (normal) = circuit complete = current flowing = calls go through
- OPEN (tripped) = circuit broken = no current = calls fail immediately
- HALF-OPEN = testing = limited current = one test call allowed

Where the analogy breaks down:
- Real circuit breakers protect against OVERCURRENT (too much load)
- Software circuit breakers protect against FAILURE (downstream service is broken)
- Real breakers are physical devices with specific ratings
- Software breakers are configurable (threshold, timeout, etc.)
- Real breakers don't have a "half-open" state — you reset or you don't
- Software breakers auto-test and auto-recover

The analogy is strong enough to convey the core concept, and the differences are instructive.
</think>

Since you know electrical circuit breakers, the software pattern maps almost 1:1:

**The analogy**:
```
Electrical                    Software
────────────────────────      ────────────────────────
Normal current flow           Requests to downstream service
Overcurrent / short circuit   Downstream service failing/timing out
Breaker trips (opens)         Stop calling the failing service
Wiring/devices protected      Your service stays healthy (no cascade)
Wait, then reset breaker      After timeout, try one test request
Circuit restored              Service recovered, resume normal calls
```

**The three states map directly**:
```
CLOSED (normal):
  Electrical: Circuit complete, current flows freely
  Software:   Calls go through normally, failures are counted

  if failures > threshold in window:
      → trip to OPEN

OPEN (tripped):
  Electrical: Circuit broken, no current flows, devices protected
  Software:   Calls fail IMMEDIATELY (don't even try), return fallback

  after timeout_seconds:
      → move to HALF-OPEN

HALF-OPEN (testing):
  Electrical: (no direct equivalent — you manually test and reset)
  Software:   Allow ONE test call through

  if test call succeeds → CLOSED (recovered!)
  if test call fails → OPEN (still broken, reset timer)
```

**Implementation**:
```python
import time
from enum import Enum
from threading import Lock

class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,     # "amperage rating" — trips after N failures
        recovery_timeout: float = 30,    # seconds before testing (like a thermal cooldown)
        success_threshold: int = 2,      # successful tests needed to fully close
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.state = State.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self._lock = Lock()

    def call(self, func, *args, fallback=None, **kwargs):
        with self._lock:
            if self.state == State.OPEN:
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = State.HALF_OPEN
                    self.success_count = 0
                else:
                    if fallback:
                        return fallback()
                    raise CircuitOpenError("Circuit is OPEN — failing fast")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            if fallback:
                return fallback()
            raise

    def _on_success(self):
        with self._lock:
            if self.state == State.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = State.CLOSED
                    self.failure_count = 0
            self.failure_count = 0

    def _on_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.state == State.HALF_OPEN:
                self.state = State.OPEN  # Test failed, re-trip
            elif self.failure_count >= self.failure_threshold:
                self.state = State.OPEN  # Trip the breaker

class CircuitOpenError(Exception):
    pass
```

**Where the analogy breaks down** (and what that teaches):
1. **Electrical breakers protect against overload** (too much current). Software breakers protect against **failure** (errors, timeouts). This means software breakers need to distinguish "service is broken" from "service is just busy" — something a physical breaker never has to do.
2. **Electrical breakers have no HALF-OPEN state** — you manually reset. Software breakers auto-test, which is a feature unique to software where "trying one request" has near-zero cost.
3. **Electrical breakers are local** — one per circuit. Software breakers can be shared across instances or per-host, and this choice matters for distributed systems.'''
    ),
    (
        "thinking/analogy-db-index-book-index",
        "My database queries are slow even though the table has millions of rows. My colleague says I need indexes but I don't really understand what they do or when to use them.",
        r'''<think>
Database indexes map perfectly to book indexes. Let me build the analogy:

A textbook with 1000 pages:
- WITHOUT index: to find "photosynthesis," read every page (full table scan)
- WITH index: look in the back of the book under "P" → "Photosynthesis: pages 142, 287, 503" → go directly to those pages

A database table with 1M rows:
- WITHOUT index: scan every row to find WHERE name = 'Alice' (full table scan)
- WITH index: look up 'Alice' in B-tree index → jump to row ID 42857 → done

Let me extend the analogy to cover more concepts:

1. INDEX TYPE → BOOK ANALOGY:
   - B-tree index: alphabetical index in back of book (sorted, great for ranges)
   - Hash index: dictionary — exact lookups only, O(1)
   - Full-text index: like a concordance (every word → every page it appears on)
   - Composite index: index with sub-categories (topic → subtopic → page)

2. WHY NOT INDEX EVERYTHING:
   - A book with an index for every word would be bigger than the book itself
   - Updating an indexed book: if you add a page, every index entry with higher page numbers needs updating
   - More indexes = slower writes (inserts/updates)

3. COVERING INDEX:
   - If the index has all the info you need, you don't need to look at the page — like an index that says "Photosynthesis (process by which plants convert light)" — you got your answer from the index entry itself

4. Index selectivity:
   - Indexing "chapter number" (only 10 values) is almost useless — index says "Chapter 1: pages 1-100" — you still scan 100 pages
   - Indexing "word" is much more selective — narrows to a few specific pages

Where the analogy breaks down:
- Book indexes are immutable; DB indexes auto-maintain
- Book indexes take physical space; DB indexes take disk AND memory
- B-tree structure has no real book equivalent (multi-level balanced tree)
</think>

Think of a database index exactly like the **index at the back of a textbook**:

**Without an index** — find "photosynthesis" in a 1000-page book:
```
Strategy: Start at page 1, read every page until you find it.
Time: O(n) — might need to read all 1000 pages.
This is a "full table scan" in database terms.
```

**With an index** — alphabetical listing in the back:
```
Strategy: Look up "P" → "Photosynthesis: pages 142, 287, 503"
Time: O(log n) — flip to the right section of the index, then jump to pages.
This is an "index seek" in database terms.
```

**The analogy extends to every major index concept**:

```
Book Concept                    Database Concept
──────────────────────────      ──────────────────────────
Alphabetical back-of-book index B-tree index (sorted, supports ranges)
Dictionary (word → definition)  Hash index (exact lookups only, O(1))
Concordance (every word → pages) Full-text index
Index with categories:          Composite index:
  "Animals > Mammals > Dogs"      CREATE INDEX ON pets(type, breed, name)

Glossary with definitions       Covering index (answer from index alone,
(no need to flip to the page)   no need to read the actual row)

Index of a chapter that says    Low-selectivity index (almost useless):
"Science: pages 1-500"          INDEX ON users(is_active) — 99% are true

Index entry:                    High-selectivity index (very useful):
"Quasar: page 847"              INDEX ON users(email) — unique values
```

**When to add an index** (book analogy):
```sql
-- You'd add a book index if:
-- 1. People frequently look up specific topics (frequent WHERE clause)
CREATE INDEX idx_email ON users(email);

-- 2. People need things in a specific order (frequent ORDER BY)
CREATE INDEX idx_created ON posts(created_at DESC);

-- 3. People look up combinations of things (WHERE x AND y)
CREATE INDEX idx_compound ON orders(customer_id, created_at);

-- You would NOT index if:
-- 1. The book is 10 pages (small table — just scan it)
-- 2. The index entry says "appears on pages 1-900" (low selectivity)
-- 3. Pages are constantly being added/removed (write-heavy table)
```

**Why not index everything** — the same reason a book's index for every word would be larger than the book itself:
```
Table: 1M rows × 100 bytes = 100MB
Add 10 indexes: each index ≈ 20-50MB
Total index space: 200-500MB (2-5× the data!)

Every INSERT/UPDATE must update ALL indexes.
More indexes = slower writes.
```

**The analogy breaks down at**: B-tree internal structure (multi-level balanced tree has no book equivalent), and automatic maintenance (book indexes don't update themselves when you add pages, but database indexes do — at a cost).'''
    ),
    (
        "thinking/analogy-backpressure-traffic",
        "Our microservice is getting overwhelmed by requests and crashing. My lead mentioned 'backpressure' but I don't understand the concept.",
        r'''<think>
Backpressure maps perfectly to traffic flow. Let me build the analogy.

In traffic:
- Highway has capacity of 4000 cars/hour
- During rush hour, 6000 cars/hour try to enter
- Without backpressure: everyone enters, highway grinds to a halt (traffic jam)
- With backpressure: metered on-ramp lights control entry rate

The key insight: when a system can't keep up with demand, you have two choices:
1. Accept everything and slow down (traffic jam / memory exhaustion / OOM)
2. Push back against the source (backpressure / rate limiting / queue depth limits)

In software:
- Service processes 1000 req/sec
- Load balancer sends 3000 req/sec
- Without backpressure: queue grows unboundedly → memory exhaustion → crash
- With backpressure: service says "I'm full" → load balancer routes elsewhere or returns 503

Types of backpressure:
1. Bounded queues (highway capacity limit)
2. Rate limiting (metered on-ramp)
3. Load shedding (closing on-ramp entirely)
4. TCP flow control (literal backpressure in networking)
5. Reactive streams (subscriber tells publisher how much it can handle)

Where the analogy is particularly strong:
- Both systems degrade gracefully with backpressure, catastrophically without
- Both involve upstream/downstream thinking
- Both can have cascading effects (one slow highway backs up connected highways)
</think>

**Traffic analogy — it maps perfectly**:

```
Highway                          Microservice
────────────────────────         ────────────────────────
Highway capacity: 4000 cars/hr   Service capacity: 1000 req/sec
Rush hour: 6000 cars/hr arrive   Traffic spike: 3000 req/sec arrive

WITHOUT backpressure:            WITHOUT backpressure:
Everyone enters highway          All requests accepted
→ Traffic jam (30 mph → 5 mph)   → Queue grows unboundedly
→ Nobody gets through quickly     → Memory exhaustion
→ Accidents (cascading failure)   → OOM crash (total failure)

WITH backpressure:               WITH backpressure:
Metered on-ramp lights           Bounded queue / rate limit
→ Some cars wait to enter         → Excess requests get 503
→ Highway flows at full speed     → Accepted requests complete fast
→ Total throughput maintained     → Service stays healthy
```

**Implementing backpressure at each layer**:

```python
# 1. BOUNDED QUEUE (highway capacity limit)
import asyncio

class BackpressuredService:
    def __init__(self, max_concurrent: int = 100):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.queue_depth = 0
        self.max_queue = 500  # When queue hits this, reject immediately

    async def handle_request(self, request):
        self.queue_depth += 1

        # Load shedding — if queue is too deep, reject immediately
        if self.queue_depth > self.max_queue:
            self.queue_depth -= 1
            raise HTTPException(503, "Service overloaded, try again later")

        try:
            # Bounded concurrency — wait for a slot
            async with self.semaphore:
                return await self._process(request)
        finally:
            self.queue_depth -= 1


# 2. RATE LIMITING (metered on-ramp)
from time import time

class TokenBucket:
    """Like a metered on-ramp — allows N cars per interval."""
    def __init__(self, rate: float, capacity: int):
        self.rate = rate          # tokens per second (cars per minute)
        self.capacity = capacity  # max burst size
        self.tokens = capacity
        self.last_refill = time()

    def allow(self) -> bool:
        now = time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

        if self.tokens >= 1:
            self.tokens -= 1
            return True  # Green light — enter the highway
        return False      # Red light — wait or go elsewhere


# 3. REACTIVE BACKPRESSURE (subscriber controls flow)
async def streaming_pipeline():
    """Like a highway where downstream can signal 'slow down'."""
    queue = asyncio.Queue(maxsize=100)  # Bounded — producer blocks when full

    async def producer():
        async for event in event_source():
            await queue.put(event)  # BLOCKS when queue is full
            # This IS backpressure — producer slows down to match consumer

    async def consumer():
        while True:
            event = await queue.get()
            await process_slowly(event)  # Takes time

    await asyncio.gather(producer(), consumer())
```

**The traffic analogy also explains cascading failure**:
```
One slow highway → backed-up connecting highways → citywide gridlock
One slow service → backed-up upstream services → system-wide cascade

Fix: Each service has its OWN backpressure + circuit breakers.
Like each highway having its own metered on-ramps and "highway full" signs.
```

**Where the analogy breaks down**: Software can **shed load** (return 503 and drop the request entirely) — you can't make a car disappear from a highway. Software also supports **auto-scaling** (adding more lanes dynamically), which physical highways obviously can't do.'''
    ),
    (
        "thinking/analogy-di-power-outlets",
        "Can you explain dependency injection in a way that's actually intuitive? Every explanation I've read uses abstract examples that don't click.",
        r'''<think>
Dependency Injection maps well to power outlets. Let me build this analogy.

Without DI (hardwired):
- Your lamp is WIRED directly into the electrical panel
- To change the lamp, you need to rewire the whole circuit
- To test the wiring, you need an actual lamp (can't use a test light)

With DI (pluggable):
- The wall has a standard OUTLET (interface)
- You PLUG IN whatever device you want (implementation)
- To test the outlet, plug in a test light (mock)
- To change devices, just unplug one and plug in another

The key concepts:
1. INTERFACE = outlet shape (standard plug format)
2. IMPLEMENTATION = specific device (lamp, fan, phone charger)
3. INJECTION = plugging the device into the outlet
4. CONSTRUCTOR INJECTION = wiring the outlet into the room when building it
5. MOCK = test light that verifies "is there power?" without being the real device

Where this is particularly strong:
- "Don't hardwire your dependencies" = "don't solder the lamp to the wiring"
- "Program to an interface" = "build to a standard outlet shape"
- "Swap implementations" = "unplug lamp, plug in fan"
- "Unit test with mocks" = "plug in a test light instead of the real device"

Let me make this concrete with code.
</think>

**Think of it like power outlets**:

```
WITHOUT Dependency Injection          WITH Dependency Injection
(hardwired)                           (pluggable)

    ┌──────────┐                      ┌──────────┐
    │  LAMP    │                      │  LAMP    │
    │  (hard-  │                      │          │
    │  wired)  │                      └─── ─┬── ┘
    └────┬─────┘                           ┌┴┐
         │ soldered                         │ │ plug
    ═════╧═════                        ═══[   ]═══
    WALL WIRING                        WALL OUTLET
                                       (interface)

To change the lamp:                   To change the lamp:
  → Rewire the whole circuit            → Unplug old, plug in new

To test the wiring:                   To test the outlet:
  → Need a real lamp                    → Plug in a $2 test light
```

**In code — the analogy is 1:1**:

```python
# ════════════════════════════════════════
# WITHOUT DI — "hardwired lamp"
# ══════════════════════════════════════════
class OrderService:
    def __init__(self):
        self.db = PostgresDatabase("host=prod port=5432")  # SOLDERED to PostgreSQL
        self.email = SMTPClient("smtp.gmail.com")           # SOLDERED to Gmail
        self.logger = FileLogger("/var/log/app.log")        # SOLDERED to file

    def create_order(self, data):
        self.db.insert("orders", data)      # Can't test without real Postgres
        self.email.send(data["email"], "...")  # Sends REAL emails during tests!
        self.logger.log("Order created")       # Writes to real file


# ══════════════════════════════════════════
# WITH DI — "power outlets"
# ══════════════════════════════════════════

# Step 1: Define the OUTLET SHAPE (interface)
class Database(Protocol):
    def insert(self, table: str, data: dict) -> None: ...

class EmailSender(Protocol):
    def send(self, to: str, body: str) -> None: ...

class Logger(Protocol):
    def log(self, message: str) -> None: ...


# Step 2: PLUG IN through the constructor
class OrderService:
    def __init__(self, db: Database, email: EmailSender, logger: Logger):
        self.db = db          # Whatever you PLUG IN
        self.email = email    # We don't know (or care) what it is
        self.logger = logger  # As long as it fits the outlet shape

    def create_order(self, data):
        self.db.insert("orders", data)
        self.email.send(data["email"], "Order confirmed")
        self.logger.log("Order created")


# Step 3: PLUG IN real devices for production
service = OrderService(
    db=PostgresDatabase("host=prod"),    # Real Postgres
    email=SMTPClient("smtp.gmail.com"),  # Real email
    logger=FileLogger("/var/log/app.log"),  # Real file logger
)


# Step 4: PLUG IN test lights for testing
class FakeDatabase:
    def __init__(self):
        self.inserted = []
    def insert(self, table, data):
        self.inserted.append((table, data))

class FakeEmailSender:
    def __init__(self):
        self.sent = []
    def send(self, to, body):
        self.sent.append((to, body))

def test_create_order():
    fake_db = FakeDatabase()
    fake_email = FakeEmailSender()

    service = OrderService(
        db=fake_db,                 # Test light instead of real lamp
        email=fake_email,           # No real emails sent
        logger=NullLogger(),        # /dev/null
    )

    service.create_order({"email": "alice@test.com", "item": "Widget"})

    assert len(fake_db.inserted) == 1
    assert fake_email.sent[0][0] == "alice@test.com"
    # Tested business logic without any real infrastructure!
```

**The complete analogy**:
```
Power System           Code Concept           Why It Matters
──────────────         ──────────────         ──────────────────
Outlet shape           Interface/Protocol     Defines what can plug in
Specific device        Implementation         The actual thing that runs
Plugging in            Constructor injection  Connecting at creation time
Test light             Mock/Fake              Cheap verification tool
Hardwired lamp         Direct instantiation   Can't change or test easily
Electrical code (NEC)  SOLID principles       Standards for safe wiring
```

**When NOT to use DI** (even outlets have limits): You don't put an outlet on every wire in your house — some things are fine hardwired (like the connection from the breaker panel to the outlet itself). In code: don't inject standard library functions or trivial utilities. Inject things that have **side effects** (database, network, filesystem) or **multiple possible implementations** (payment processors, notification channels).'''
    ),
    (
        "thinking/analogy-git-parallel-universes",
        "I'm new to git branching and merging. The concepts of branches, merges, and conflicts don't make sense to me. Can you explain it in a way that clicks?",
        r'''<think>
Git branches as parallel universes is a great analogy. Let me map it:

Universe (main timeline) = main branch
- Everyone agrees on the "canonical" history
- This is the "real" world that production runs on

Creating a branch = creating a parallel universe
- At a specific moment in time, the universe forks
- Both universes continue independently
- Changes in one don't affect the other

Commits = events in a universe
- Each event follows the previous one
- You can't change history without creating a paradox (rewriting git history)

Merging = two universes converging back
- Take the events from the parallel universe and merge them into main
- If both universes changed the same thing differently → CONFLICT

Conflict resolution = deciding which universe's version is "real"
- "In universe A, the wall is blue. In universe B, the wall is red."
- You have to decide: is it blue, red, or some compromise (purple)?

Rebasing = pretending the parallel universe started later
- Instead of "universe B forked from main at point X," rebase makes it "universe B forked from main at point Y (the current tip)"
- Rewrites history of universe B

Cherry-pick = stealing one event from another universe
- "In universe B, they invented teleportation. Let me grab just that invention for universe A."

This analogy is particularly strong because it captures the idea that branches are independent timelines that can diverge and reconverge.
</think>

**Think of git branches as parallel universes**:

```
Day 1: One universe exists (main)
        You and your colleague both live here
        The codebase looks the same to everyone

        main: ──A──B──C──
                         │
Day 2: Your colleague creates a branch (parallel universe forks)
                         │
        main:    ──A──B──C──D──E──        (your universe continues)
                         │
        feature: ──A──B──C──F──G──H──     (their universe continues)

        You add D and E. They add F, G, H.
        You can't see their changes. They can't see yours.
        Both universes are equally "real."

Day 5: Merge (the universes converge!)

        main: ──A──B──C──D──E──────M──    (M = merge commit)
                         │              ╱
        feature: ──A──B──C──F──G──H──╱    (their changes flow in)

        M contains everything from both universes.
```

**Conflicts = both universes changed the same thing differently**:
```
In YOUR universe (main):
    You painted the kitchen wall BLUE.
    File: kitchen.py, line 5: color = "blue"

In THEIR universe (feature):
    They painted the kitchen wall RED.
    File: kitchen.py, line 5: color = "red"

Git says: "CONFLICT! Both universes changed the wall color."

<<<<<<< HEAD (your universe)
color = "blue"
=======
color = "red"
>>>>>>> feature (their universe)

YOU decide: which universe's wall color is correct?
Or maybe you compromise: color = "purple"
```

**The full analogy**:
```
Parallel Universe Concept      Git Concept
─────────────────────────      ─────────────────
The main timeline              main branch
Fork a parallel universe       git checkout -b feature
Events in a universe           Commits
Two universes diverge          Branches with different commits
Universes converge             git merge
Same thing changed differently Merge conflict
Choose which universe wins     Resolve conflict
Grab one event from another    git cherry-pick
Pretend universe started later git rebase
Destroy a parallel universe    git branch -d feature
Look at another universe       git checkout other-branch
The multiverse map             git log --graph --all
```

**Common git operations in universe terms**:
```bash
# Create a parallel universe that forks from now
git checkout -b my-experiment

# Make events happen in this universe
echo "new feature" > feature.py
git add feature.py
git commit -m "Invented teleportation"

# Peek at the main universe (without going there)
git log main

# Go back to the main universe
git checkout main

# Merge the parallel universe's events into main
git merge my-experiment

# If conflict: you're the arbiter of reality
# Edit the conflicted files, then:
git add conflicted-file.py
git commit -m "Resolved: wall is purple (compromise)"

# The parallel universe served its purpose — close it
git branch -d my-experiment
```

**Where the analogy breaks down**: In fiction, parallel universes can't communicate. In git, you can freely peek at any branch, cherry-pick commits between them, and even rewrite history (which would create a paradox in real parallel universes). Also, git branches are cheap — creating a "universe" takes milliseconds and costs virtually no storage.'''
    ),
    (
        "thinking/analogy-caching-memory",
        "When should I add caching to my application? I'm never sure if it's worth the complexity.",
        r'''<think>
Caching maps beautifully to human short-term memory. Let me build this:

Without cache (no short-term memory):
- Every time someone asks your phone number, you look it up in the phone book
- Every time: walk to bookshelf → find book → open to page → read number
- Slow but always up-to-date

With cache (short-term memory):
- First time: look it up in the phone book → remember it
- Next 100 times: recall instantly from memory
- But if the number changes, your memory is STALE

This maps to:
- Cache HIT = you remember the answer
- Cache MISS = you forgot, need to look it up again
- TTL (Time To Live) = how long before you forget
- Cache INVALIDATION = someone tells you "that number changed, forget it"
- Cache STAMPEDE = 100 people ask you the same question at the moment you forgot it — you look it up 100 times in parallel
- Cache WARMING = proactively memorizing things you'll likely be asked

"Should I cache?" decision:
1. Is the lookup slow? (Is walking to the bookshelf slow?)
2. Is the data accessed often? (Do people ask your number often?)
3. Is staleness acceptable? (Is it OK if you give a 5-minute-old answer?)
4. Does the data change rarely? (Does the phone number change rarely?)

If all 4 are yes → cache. If any are no → maybe not.
</think>

**Think of caching like your short-term memory**:

```
WITHOUT cache (no memory):
  "What's Alice's phone number?"
  → Walk to bookshelf → find contacts book → find Alice → read number
  → Every. Single. Time.
  → Always accurate, always slow.

WITH cache (remember it):
  First time: look it up → memorize "Alice = 555-0123"
  Next time: recall instantly from memory
  → Fast! But what if Alice changed her number?
```

**The decision framework — should you memorize this?**

```
Question                              Cache?
────────────────────────────          ──────
Is looking it up slow?                If NO → don't bother caching
  (API call, DB query, computation)

Is it asked for frequently?           If NO → don't bother caching
  (same query hits 100x/minute)       (you'll memorize and forget before anyone asks again)

Is a slightly stale answer OK?        If NO → caching is dangerous
  (5-second-old data acceptable?)     (stock prices: NO. blog post: YES)

Does it change rarely?                If YES → perfect cache candidate
  (config, user profiles, product     (memorize once, valid for hours)
   listings vs real-time stock price)
```

**Cache concepts = memory concepts**:
```python
# 1. CACHE HIT — you remember! Instant answer.
cache.get("alice_phone")  # → "555-0123" (from memory, ~0.1ms)

# 2. CACHE MISS — you forgot. Look it up, then memorize.
result = cache.get("bob_phone")  # → None (not in memory)
result = db.query("SELECT phone FROM contacts WHERE name='Bob'")  # 50ms
cache.set("bob_phone", result, ttl=3600)  # Remember for 1 hour

# 3. TTL (Time To Live) — how long before you "forget"
# Like how you remember a parking spot for hours,
# but forget a random number within minutes
cache.set("parking_spot", "Level 3, Row B", ttl=8*3600)   # Remember 8 hours
cache.set("verification_code", "7294", ttl=300)             # Forget in 5 min

# 4. CACHE INVALIDATION — someone tells you the info changed
# "Hey, Alice got a new number"
def update_phone(name, new_number):
    db.update("contacts", name=name, phone=new_number)
    cache.delete(f"{name}_phone")  # Forget the old number!

# 5. CACHE STAMPEDE — 100 people ask at the moment you forgot
# You look it up 100 times simultaneously (wasteful!)
# Fix: only ONE person looks it up, others wait
async def get_with_lock(key, fetch_func):
    result = cache.get(key)
    if result:
        return result
    async with cache.lock(f"lock:{key}"):
        result = cache.get(key)  # Someone else may have set it
        if not result:
            result = await fetch_func()
            cache.set(key, result, ttl=300)
    return result
```

**When NOT to cache** (when memorizing hurts more than helps):
```
1. Write-heavy, read-light data
   → Like memorizing lottery numbers — they change every draw

2. Every request is unique
   → Like memorizing every stranger's face — you'll never see them again

3. Stale data is dangerous
   → Like memorizing medicine dosages — if it changes, wrong dose = harm

4. Data is small/fast to compute
   → Like memorizing 2+2 — you can recalculate instantly

5. You're adding caching to "fix" a slow query
   → Fix the query first. Caching hides the problem.
```

**The hardest problem in caching** (and memory): "There are only two hard things in Computer Science: cache invalidation and naming things." — Phil Karlton. Knowing WHEN to forget is harder than knowing when to remember.'''
    ),
    (
        "thinking/analogy-load-balancer-checkout-lanes",
        "We need to handle 10x our current traffic for a product launch. How does load balancing work and what strategy should we use?",
        r'''<think>
Load balancing maps perfectly to checkout lanes at a grocery store. Let me build this:

One cashier (one server):
- Line gets longer during rush hour
- If the cashier is overwhelmed, everyone waits longer
- If the cashier gets sick, NOBODY can check out

Multiple cashiers (multiple servers) with a load balancer (floor manager):
- Floor manager directs customers to available lanes
- If one cashier is overwhelmed, redirect to another
- If one cashier is sick, close that lane and redirect

Load balancing strategies:
1. Round-robin = "next customer goes to lane 1, next to lane 2, next to lane 3, repeat"
   - Simple but doesn't account for express vs full-cart customers
2. Least connections = "go to the lane with the shortest line"
   - Better but doesn't account for how fast each cashier is
3. Weighted = "lane 1 gets 50% of customers (fast cashier), lane 2 gets 30%, lane 3 gets 20%"
   - Accounts for different server capacities
4. IP hash = "your loyalty card number determines your lane"
   - Same customer always goes to same lane (sticky sessions)

Health checks = floor manager checking "is this lane open?"
- If cashier takes a break, redirect customers to other lanes
- "Active" health check: periodically ask "are you available?"
- "Passive" health check: notice if customers at that lane are complaining

Where this is particularly strong: it captures why naive strategies (round-robin) fail when requests have different "weights" (like express vs full-cart customers).
</think>

**Think of it like a grocery store with checkout lanes**:

```
ONE SERVER (one cashier):
  ┌────────────────────┐
  │ Server 1 (cashier) │ ← Everyone waits in one line
  └────────────────────┘    If cashier is sick, store closes

LOAD BALANCED (floor manager + multiple cashiers):
  ┌──────────────────┐
  │  Load Balancer   │ ← Floor manager directing traffic
  │  (floor manager) │
  └───┬──────┬──────┬┘
      │      │      │
  ┌───▼─┐ ┌─▼───┐ ┌▼────┐
  │ S1  │ │ S2  │ │ S3  │  ← 3 cashiers (servers)
  └─────┘ └─────┘ └─────┘
```

**Load balancing strategies = how the floor manager assigns lanes**:

```python
# 1. ROUND ROBIN = "next customer to lane 1, next to lane 2, next to 3, repeat"
# Good: Simple, fair distribution
# Bad: Doesn't account for slow vs fast requests
# Use when: All requests are similar size, all servers are identical
class RoundRobin:
    def __init__(self, servers):
        self.servers = servers
        self.current = 0
    def next_server(self):
        server = self.servers[self.current % len(self.servers)]
        self.current += 1
        return server

# 2. LEAST CONNECTIONS = "go to the lane with the shortest line"
# Good: Adapts to variable request sizes
# Bad: Doesn't account for server capacity differences
# Use when: Requests vary in processing time
class LeastConnections:
    def next_server(self):
        return min(self.servers, key=lambda s: s.active_connections)

# 3. WEIGHTED = "fast cashier gets more customers"
# Good: Accounts for different server sizes
# Bad: Weights are static (must be configured)
# Use when: Servers have different CPU/memory
# Example: 8-core server gets weight=3, 2-core gets weight=1

# 4. IP HASH = "your loyalty card determines your lane"
# Good: Same customer always goes to same server (session stickiness)
# Bad: Uneven distribution, can't remove servers gracefully
# Use when: Server-side sessions (avoid if possible)
```

**Health checks = floor manager checking "is this lane open?"**:
```python
# nginx configuration
upstream backend {
    server app1:8080 weight=3;  # Big server — 3x traffic share
    server app2:8080 weight=1;  # Small server — 1x traffic share
    server app3:8080 backup;    # Only used if app1 AND app2 are down
}

server {
    location / {
        proxy_pass http://backend;

        # Health check: ask each server "are you OK?" every 5 seconds
        # Like floor manager walking by each lane: "still open?"
        health_check interval=5s fails=3 passes=2;
        # If 3 checks fail → close that lane
        # If 2 checks pass → reopen that lane
    }
}
```

**For your 10x traffic product launch**:
```
Strategy:
1. Scale OUT: Add more servers (open more checkout lanes)
   3 servers → 10 servers before launch

2. Scale UP: Bigger servers (faster cashiers)
   Each server: 2 vCPU → 8 vCPU

3. Auto-scaling: Add servers when load increases
   (Like calling in off-duty cashiers during rush hour)

4. CDN for static content: Serve images/CSS from edge locations
   (Like a self-checkout kiosk for simple purchases)

5. Load test BEFORE launch: Simulate 10x traffic
   (Like a fire drill — find the bottleneck before the real rush)
```

**Where the analogy breaks down**: Servers can handle multiple requests simultaneously (async/threaded), unlike a cashier who serves one customer at a time. And auto-scaling creates new servers in seconds — you can't hire and train a new cashier that fast.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
