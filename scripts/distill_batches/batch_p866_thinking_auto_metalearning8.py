"""Phase 4D: Self-Improvement — Meta-Learning (Part 8)

Learning transfer between programming paradigms — systematically
mapping concepts from OOP to FP, sync to async, and other paradigm shifts.
"""

PAIRS = [
    (
        "thinking/auto-metalearning-oop-to-fp-patterns",
        r'''I'm deeply experienced in OOP with Java and C#, and I want to learn Haskell. What OOP patterns have direct FP equivalents, and which ones have no analog at all?''',
        r'''<think>
Transferring from OOP (Java/C#) to pure FP (Haskell) is one of the most challenging paradigm shifts because Haskell doesn't just do things differently — it forbids things OOP developers take for granted (mutation, side effects, null).

**Direct equivalents:**
- Interface → Type class
- Decorator → Function composition / higher-order functions
- Strategy → First-class functions
- Factory → Smart constructors
- Observer → Reactive streams / FRP

**Partial equivalents:**
- Encapsulation → Module system (hide constructors)
- Inheritance → Type class hierarchies (but no implementation inheritance)
- Builder → Lens/record syntax

**No analog (must unlearn):**
- Mutable state as default → Everything immutable
- Null/None → Maybe/Either (no null at all)
- Exception throwing → Either/MonadError (errors are values)
- Object identity → Values have no identity
- Setter methods → Lenses (return new copies)
</think>

**OOP (Java/C#) to Haskell: Transfer Map**

**Direct equivalents — leverage these:**

| OOP (Java/C#) | Haskell | Key difference |
|----------------|---------|----------------|
| `interface Sortable { ... }` | `class Sortable a where ...` | Type classes are more powerful (ad-hoc polymorphism) |
| Strategy pattern (pass behavior) | Pass a function | No wrapping class needed |
| Decorator pattern | Function composition `f . g` | Compose functions, not objects |
| Generic types `List<T>` | Parametric polymorphism `[a]` | Nearly identical concept |
| `Optional<T>` / `Nullable<T>` | `Maybe a` | Haskell enforces it — you CANNOT skip the check |
| Iterator / Stream | Lazy list `[a]` | Haskell lists are lazy by default |

**Example — Strategy pattern:**
```java
// Java: Need a class to pass behavior
interface Comparator<T> { int compare(T a, T b); }
Collections.sort(list, new NameComparator());
```
```haskell
-- Haskell: Just pass a function
sortBy (\a b -> compare (name a) (name b)) list
-- Or even simpler:
sortOn name list
```

**Concepts with no OOP analog (must learn fresh):**

```
1. PATTERN MATCHING — No equivalent in Java/C#
   data Shape = Circle Double | Rectangle Double Double

   area :: Shape -> Double
   area (Circle r)      = pi * r * r
   area (Rectangle w h) = w * h
   -- Compiler warns if you miss a case!

2. MONADS — No equivalent (despite "monad tutorials")
   Don't try to map this to OOP. Learn it from scratch:
   - Maybe monad = chaining operations that might fail
   - IO monad = sequencing side effects
   - List monad = non-deterministic computation

3. CURRYING — Every function takes one argument
   add :: Int -> Int -> Int
   add x y = x + y
   addFive = add 5  -- partial application, no special syntax
   -- In Java, you'd need a whole new class/lambda for this

4. ALGEBRAIC DATA TYPES — More powerful than class hierarchies
   data Result a = Success a | Failure String
   -- This replaces: subclassing, null checks, exceptions
```

**Concepts you must actively UNLEARN:**

```
UNLEARN: "Objects have state that changes over time"
REPLACE: "Values are immutable. New values are created."

UNLEARN: "Null means absent"
REPLACE: "Maybe means absent. There is no null."

UNLEARN: "Throw exceptions for errors"
REPLACE: "Return Either for errors. Errors are values."

UNLEARN: "Loops iterate over collections"
REPLACE: "map, filter, fold transform collections."

UNLEARN: "I'll mutate this variable in a loop"
REPLACE: "I'll use fold/recursion to accumulate a result."
```

**The recommended learning order:**
```
Week 1-2: Pure functions, pattern matching, recursion
Week 3-4: Higher-order functions, map/filter/fold
Week 5-6: Type classes, custom data types
Week 7-8: Functors, Applicatives (build toward Monads)
Week 9-10: Monads (Maybe, Either, IO)
Week 11+: Monad transformers, lens, real projects
```

**The meta-principle:** The hardest part of OOP-to-Haskell isn't learning new concepts — it's suppressing the reflexive reach for mutation and objects. Every time you think "I need a class for this," ask "can I use a function instead?" The answer in Haskell is almost always yes.'''
    ),
    (
        "thinking/auto-metalearning-sync-to-async-transfer",
        r'''I understand synchronous programming well but I keep getting confused by async/await, callbacks, and event loops. What mental model transfers from sync to async, and where does the analogy break?''',
        r'''<think>
The sync-to-async transition confuses people because async code LOOKS sequential (with async/await) but BEHAVES differently. The key mental model shift is from "one thing at a time, in order" to "start something, do other things while waiting, come back when it's ready."

**What transfers:**
- Sequential logic within a single async function
- Error handling concepts (try/catch still works)
- Variable scope and closures
- Function composition

**What breaks:**
- Execution order assumptions
- Shared state safety (race conditions)
- Stack trace expectations
- Debugging flow
- Exception propagation

The best analogy: synchronous = phone call (you wait on the line), async = text messages (you send and continue, respond when you get a reply).
</think>

**Sync to Async: Mental Model Transfer Guide**

**The core mental shift:**
```
SYNC:  Do A, then B, then C (you wait for each to finish)
ASYNC: Start A, start B, start C (they run concurrently)
       → Collect results when each finishes

Analogy:
  Sync  = Cooking one dish at a time (finish soup, then start salad)
  Async = Cooking multiple dishes (soup simmers while you chop salad)
```

**What transfers directly:**

**1. Sequential logic within a function:**
```python
# Sync
def get_user_data(user_id):
    user = db.get_user(user_id)        # wait
    orders = db.get_orders(user_id)     # wait
    return {"user": user, "orders": orders}

# Async — looks almost identical!
async def get_user_data(user_id):
    user = await db.get_user(user_id)   # wait (but others can run)
    orders = await db.get_orders(user_id)
    return {"user": user, "orders": orders}
```

**2. Error handling:**
```python
# Sync
try:
    result = do_thing()
except ValueError as e:
    handle_error(e)

# Async — identical structure
try:
    result = await do_thing()
except ValueError as e:
    handle_error(e)
```

**Where the analogy BREAKS (critical differences):**

**1. Execution order is NOT guaranteed between tasks:**
```python
# Sync: This ALWAYS prints A, B, C
print("A")
do_something()
print("B")
do_another()
print("C")

# Async: Between awaits, OTHER code can run
print("A")
await do_something()   # other tasks may execute here
print("B")
await do_another()     # and here
print("C")
# Within THIS function, A-B-C is ordered
# But OTHER async functions may interleave
```

**2. Shared state becomes dangerous:**
```python
# Sync: This is safe
counter = 0
for item in items:
    counter += process(item)  # no interleaving, safe

# Async: This is a RACE CONDITION
counter = 0
async def process_item(item):
    nonlocal counter
    result = await process(item)  # another task could modify counter here
    counter += result              # race condition!

# Fix: Use asyncio.Lock or accumulate results differently
```

**3. One blocking call blocks EVERYTHING:**
```python
# This BREAKS async
async def bad_example():
    await async_fetch_data()       # good: non-blocking
    time.sleep(5)                  # BAD: blocks the entire event loop
    result = requests.get(url)     # BAD: sync HTTP blocks event loop

# Fix: Use async equivalents
async def good_example():
    await async_fetch_data()
    await asyncio.sleep(5)         # non-blocking sleep
    async with httpx.AsyncClient() as client:
        result = await client.get(url)  # non-blocking HTTP
```

**The event loop mental model:**
```
Think of the event loop as a single waiter in a restaurant:

Sync waiter: Takes order → goes to kitchen → waits for food
             → brings food → takes next order
             (One table at a time. Others wait.)

Async waiter: Takes order → gives to kitchen → goes to next table
              → takes their order → checks if first food is ready
              → serves it → continues
              (Many tables, one waiter, no idle waiting.)

The waiter is the event loop. Tables are tasks.
"await" = "go do something else while this cooks."
```

**The key rules for async:**
```
1. Never use blocking calls in async code (requests, time.sleep, open())
2. Always await async functions (forgetting await = bug)
3. Use asyncio.gather() for concurrent tasks, not sequential awaits
4. Shared mutable state needs locks or redesign
5. One function being slow blocks all others (no preemption)
```

**The meta-principle:** Async/await makes async code LOOK synchronous, which is both its strength and its trap. The syntax transfers from sync, but the execution model does not. The single most important thing to internalize: between any two awaits, the world can change.'''
    ),
    (
        "thinking/auto-metalearning-imperative-to-declarative",
        r'''I think in imperative terms — step-by-step instructions. How do I shift to declarative thinking (SQL, React, CSS) where I describe WHAT I want rather than HOW to do it?''',
        r'''<think>
The imperative-to-declarative shift is about moving from "do step 1, then step 2, then step 3" to "here's what the result should look like — figure out the steps." This is a fundamental paradigm shift that applies to SQL, HTML/CSS, React, Terraform, and many modern tools.

**The core difference:**
- Imperative: You specify the algorithm (HOW)
- Declarative: You specify the desired state (WHAT)

**Why it's hard:** Imperative thinkers want to control every step. Declarative systems require trusting the system to figure out the steps.

**What transfers:**
- Logical thinking (what conditions must be true)
- Data structure knowledge
- Understanding of desired outcomes

**What must change:**
- Giving up control of execution order
- Thinking in terms of state, not steps
- Trusting the runtime/engine
</think>

**Imperative to Declarative: The Mental Shift**

**The fundamental difference:**
```
Imperative (HOW):
  1. Open the refrigerator
  2. Look for eggs
  3. Take out 3 eggs
  4. Close refrigerator
  5. Get a pan
  6. Turn on stove
  7. Crack eggs into pan
  ...

Declarative (WHAT):
  "I want scrambled eggs for breakfast."
  (The chef figures out the steps.)
```

**Side-by-side examples:**

**SQL (declarative) vs. manual data processing (imperative):**
```python
# Imperative: You specify every step
result = []
for user in users:
    if user.age >= 18:
        if user.country == "US":
            result.append(user.name)
result.sort()
```
```sql
-- Declarative: You describe what you want
SELECT name FROM users
WHERE age >= 18 AND country = 'US'
ORDER BY name;
-- The database figures out HOW (index scan? table scan? sort algorithm?)
```

**React (declarative) vs. DOM manipulation (imperative):**
```javascript
// Imperative: Manually update the DOM
function updateCounter(count) {
  const el = document.getElementById('counter');
  el.textContent = count;
  if (count > 10) {
    el.classList.add('warning');
  } else {
    el.classList.remove('warning');
  }
}

// Declarative: Describe what the UI should look like
function Counter({ count }) {
  return (
    <span className={count > 10 ? 'warning' : ''}>
      {count}
    </span>
  );
  // React figures out what DOM changes to make
}
```

**CSS (declarative) vs. manual positioning (imperative):**
```css
/* Declarative: Describe the layout you want */
.container {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
/* The browser figures out exact pixel positions */
```

**The mental model shifts:**

```
Shift 1: "Steps" → "Constraints"
  Imperative: "Move X to position 100, then move Y to 200"
  Declarative: "X should be at 100 and Y should be at 200"
  (The system resolves constraints simultaneously)

Shift 2: "Do this" → "This should be true"
  Imperative: "Loop through items and remove duplicates"
  Declarative: "SELECT DISTINCT ..." (duplicates just don't exist)

Shift 3: "Update this" → "Here's the new state"
  Imperative: "Find the button, change its text to 'Saved'"
  Declarative: "<Button text={saved ? 'Saved' : 'Save'} />"

Shift 4: "In this order" → "These are the relationships"
  Imperative: "First load users, then load orders, then join"
  Declarative: "SELECT ... FROM users JOIN orders ON ..."
  (The query planner decides the order)
```

**Common mistakes when learning declarative:**
```
1. Trying to control execution order
   BAD:  "I need SQL to check users BEFORE joining orders"
   GOOD: Write the query, trust the optimizer

2. Over-specifying implementation
   BAD:  Using JavaScript to position every element pixel-by-pixel
   GOOD: Use CSS Flexbox/Grid and let the browser lay it out

3. Fighting the framework
   BAD:  Manually manipulating the DOM in React
   GOOD: Update state, let React re-render

4. Premature optimization
   BAD:  "But what if the SQL optimizer makes a bad choice?"
   GOOD: Write the correct query first, optimize only if measured
```

**The meta-principle:** Declarative thinking is about specifying the WHAT and trusting the system for the HOW. The hardest part for imperative thinkers is giving up control. But declarative systems can optimize in ways you can't manually — SQL query planners, React's virtual DOM diffing, and CSS layout engines are all smarter than hand-written imperative equivalents for most cases.'''
    ),
    (
        "thinking/auto-metalearning-single-to-multithreaded",
        r'''I've always written single-threaded code. What concepts transfer to multi-threaded/concurrent programming, and what completely new hazards do I need to learn?''',
        r'''<think>
The single-threaded to multi-threaded transition is one of the most dangerous paradigm shifts because bugs in concurrent code are non-deterministic — they might work 99% of the time and fail catastrophically under load.

**What transfers:**
- Algorithm design
- Data structure knowledge
- Logic and control flow
- Testing concepts (though testing is much harder)

**What's completely new:**
- Race conditions (two threads modifying the same data)
- Deadlocks (two threads waiting for each other's lock)
- Visibility (changes in one thread may not be visible in another)
- Atomicity (operations that aren't atomic can be interrupted)
- Memory ordering (CPU reorders instructions)

The core problem: in single-threaded code, you can reason about your program by reading it top-to-bottom. In multi-threaded code, you must reason about ALL possible interleavings of ALL threads simultaneously.
</think>

**Single-Threaded to Multi-Threaded: Transfer Guide**

**What transfers directly:**
```
Your algorithmic thinking still works — within each thread,
code runs top-to-bottom just like single-threaded code.
The problem is BETWEEN threads.

Single-threaded: "I know exactly what happened before this line."
Multi-threaded: "I know what happened in THIS thread before this line.
                 I have NO IDEA what other threads did."
```

**The new hazards (with examples):**

**1. Race conditions — The fundamental danger:**
```python
# Single-threaded: This is perfectly safe
balance = 1000
balance -= 500   # balance = 500
balance -= 300   # balance = 200
# Final balance: 200. Always.

# Multi-threaded: This WILL eventually corrupt data
balance = 1000
# Thread 1: reads balance (1000), subtracts 500, writes 500
# Thread 2: reads balance (1000), subtracts 300, writes 700
# Final balance: 700 or 500 — depends on timing!
# One withdrawal was LOST.

# Fix: Use a lock
lock = threading.Lock()
with lock:
    balance -= 500  # only one thread can do this at a time
```

**2. Deadlocks — Threads waiting forever:**
```python
# Thread 1: Lock A, then try to lock B
# Thread 2: Lock B, then try to lock A
# → Both threads wait forever for the other's lock

# The dining philosophers problem:
lock_a = Lock()
lock_b = Lock()

# Thread 1:
with lock_a:           # got A
    with lock_b:       # waiting for B... (Thread 2 has it)
        do_work()

# Thread 2:
with lock_b:           # got B
    with lock_a:       # waiting for A... (Thread 1 has it)
        do_work()

# Fix: Always acquire locks in the same order
# Both threads: lock A first, then lock B
```

**3. Visibility — Changes might be invisible:**
```java
// Thread 1 sets a flag
boolean running = true;

// Thread 1:
running = false;   // This change might NOT be visible to Thread 2!

// Thread 2:
while (running) {  // Might loop forever even after Thread 1 sets false
    doWork();
}

// Fix: Use volatile or atomic variables
volatile boolean running = true;  // guarantees visibility
```

**The mental model you need:**

```
Single-threaded mental model:
  Time →  [A] [B] [C] [D]
  One thing at a time, predictable order.

Multi-threaded mental model:
  Thread 1:  [A]     [C]       [E]
  Thread 2:     [B]       [D]     [F]
  Any interleaving is possible.
  A-before-B, B-before-A, or simultaneous.
```

**Safe patterns for beginners:**
```
1. IMMUTABLE DATA — If nothing changes, no race conditions
   Share read-only data between threads freely.

2. MESSAGE PASSING — Don't share memory, send messages
   Use queues: thread 1 puts work on queue, thread 2 reads from queue.
   No shared state, no locks needed.

3. THREAD-LOCAL STORAGE — Each thread has its own copy
   No sharing at all. Each thread works independently.

4. SINGLE WRITER — Only one thread modifies each piece of data
   Others can read (with proper visibility guarantees).
```

**The testing challenge:**
```
Single-threaded: Run test 100 times, get same result 100 times.
Multi-threaded: Run test 100 times, get correct result 99 times,
                fail once on the 100th run.

Concurrent bugs are non-deterministic. You can't reliably test
for them with normal testing. Use:
  - Thread sanitizers (TSan in C/C++)
  - Static analysis tools
  - Stress testing (run under high concurrency)
  - Formal verification for critical sections
```

**The meta-principle:** Multi-threaded programming forces you to think about ALL possible orderings of operations, not just the one you intended. The safest approach is to minimize shared mutable state — use immutable data, message passing, or isolated workers. Every piece of shared mutable state is a potential race condition waiting to manifest under load at 3 AM on a holiday weekend.'''
    ),
    (
        "thinking/auto-metalearning-rest-to-event-driven",
        r'''I'm comfortable with request-response (REST APIs) but my team is adopting event-driven architecture. What concepts transfer and what's fundamentally different?''',
        r'''<think>
The request-response to event-driven shift changes how you think about system communication fundamentally. In request-response, communication is synchronous and direct. In event-driven, communication is asynchronous and indirect.

**What transfers:**
- Data modeling (entities, schemas)
- API design principles (clear contracts)
- Error handling awareness (though mechanisms change)
- Testing concepts (though strategies change)

**What's fundamentally different:**
- Communication flow (direct → indirect via broker)
- Coupling (consumer knows producer → producer doesn't know consumers)
- Timing (immediate response → eventual processing)
- Error handling (synchronous errors → dead letter queues)
- Debugging (follow a request → trace events across services)
- Ordering guarantees (sequential → potentially out-of-order)
</think>

**Request-Response to Event-Driven: Transfer Guide**

**The core mental model shift:**
```
Request-Response (REST):
  Client → "Give me user 123" → Server → Response
  Synchronous. Direct. Immediate answer.
  Like a phone call: "Hello, I need X." "Here's X."

Event-Driven:
  Service A → "User 123 was created" → Message Broker
  Service B (listening) → "I heard user was created, updating my data"
  Service C (listening) → "I heard too, sending welcome email"
  Asynchronous. Indirect. No immediate answer.
  Like an announcement: "User was created!" (anyone interested acts on it)
```

**What transfers directly:**

| REST Concept | Event-Driven Equivalent |
|-------------|------------------------|
| API contract (endpoint + schema) | Event schema (event name + payload) |
| Versioning (`/api/v2/users`) | Event versioning (`UserCreated.v2`) |
| Authentication | Message broker authentication |
| Input validation | Event payload validation |
| Idempotency keys | Idempotent event handlers |

**What's fundamentally new:**

**1. Temporal decoupling — No immediate response:**
```
REST: POST /orders → 201 Created { "id": 123, "status": "confirmed" }
  You KNOW the order was created before you continue.

Event-Driven: publish("OrderRequested", { items: [...] })
  You DON'T know when or if the order will be processed.
  The result comes back as another event later:
  → "OrderConfirmed" or "OrderFailed"
```

**2. Spatial decoupling — You don't know who's listening:**
```
REST: UserService calls EmailService.send(email)
  UserService KNOWS about EmailService. They're coupled.

Event-Driven: UserService publishes "UserRegistered"
  UserService doesn't know who cares:
  - EmailService sends welcome email
  - AnalyticsService tracks sign-up
  - RecommendationService initializes profile
  Adding a new consumer requires ZERO changes to UserService.
```

**3. Ordering challenges:**
```
REST: Requests from one client are naturally sequential.

Events: Events can arrive out of order.
  Published: UserCreated → UserUpdated → UserDeleted
  Received:  UserUpdated → UserDeleted → UserCreated (!)

  You MUST handle out-of-order events:
  - Use sequence numbers or timestamps
  - Use partitioning (all events for user 123 go to same partition)
  - Design handlers to be order-independent when possible
```

**4. Error handling is completely different:**
```
REST:
  try { response = api.createOrder(data); }
  catch (error) { showError(error); }
  → Immediate feedback. User sees the error.

Event-Driven:
  publish("OrderRequested", data);  // always succeeds (broker accepted it)
  // ... later, the handler fails
  // Where does the error go?

  Options:
  - Dead letter queue (failed events go here for manual review)
  - Retry with backoff (try again, maybe it was transient)
  - Compensating event ("OrderFailed" sent back)
  - Error event channel (separate stream for monitoring)
```

**5. Debugging requires distributed tracing:**
```
REST: Follow the request through your server logs.
  Request 123 → Controller → Service → DB → Response

Event-Driven: Events fan out across services.
  Correlation ID must be attached to every event:
  OrderRequested (corr: abc) → InventoryChecked (corr: abc)
                              → PaymentProcessed (corr: abc)
                              → ShippingScheduled (corr: abc)
  Use tools like Jaeger, Zipkin, or OpenTelemetry to trace.
```

**When to use which:**
```
USE REST when:
  - You need an immediate answer
  - The operation is simple request-response
  - Strong consistency is required
  - Debugging simplicity matters

USE EVENTS when:
  - Multiple services need to react to the same thing
  - Processing can be asynchronous
  - You want loose coupling between services
  - You need to scale consumers independently
  - You want to add new reactions without changing the source
```

**The meta-principle:** Event-driven architecture inverts control. In REST, the caller decides who to talk to. In events, the publisher announces what happened and doesn't care who listens. This inversion gives you loose coupling and scalability, but costs you immediacy, ordering guarantees, and debugging simplicity. Choose based on what your system actually needs, not what's trendy.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
