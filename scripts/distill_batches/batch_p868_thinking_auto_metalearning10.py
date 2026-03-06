"""Phase 4D: Self-Improvement — Meta-Learning (Part 10)

Building mental models for new technologies — how to rapidly
construct accurate internal representations of unfamiliar systems.
"""

PAIRS = [
    (
        "thinking/auto-metalearning-mental-model-construction",
        r'''When I encounter a new technology, I struggle to form a coherent mental model of how it works. I end up memorizing API calls without understanding why. How do I build better mental models?''',
        r'''<think>
Mental model construction is the difference between "I know the commands" and "I understand the system." A good mental model lets you predict behavior, debug problems, and adapt to new situations. A poor mental model means you're copying patterns without understanding them.

**The process of building a mental model:**
1. Identify the core abstraction (what is the fundamental concept?)
2. Map the data flow (what goes in, what comes out, what transforms it?)
3. Identify the constraints (what can't you do? what are the rules?)
4. Find the boundaries (where does this system end and another begin?)
5. Test the model (does it predict behavior correctly?)

**Why developers skip this:** It's faster in the short term to just copy examples. But without a mental model, you can't debug or adapt.
</think>

**Building Mental Models for New Technologies**

**The 5-question mental model framework:**

When encountering ANY new technology, answer these questions:

```
1. WHAT IS THE CORE ABSTRACTION?
   Every technology is built around one key idea.
   - Docker: "Isolated, reproducible environments"
   - Git: "Snapshots of file trees connected in a graph"
   - React: "UI is a function of state"
   - SQL: "Declare what data you want, not how to get it"
   - Kubernetes: "Declare desired state, system converges to it"

   If you can state the core abstraction in one sentence,
   you understand the technology's reason for existing.

2. WHAT GOES IN, WHAT COMES OUT?
   - Docker: Dockerfile in → running container out
   - Git: file changes in → commit history out
   - React: state + props in → rendered DOM out
   - SQL: query in → result set out

3. WHAT ARE THE RULES/CONSTRAINTS?
   - Docker: Containers are ephemeral (data dies with container unless mounted)
   - Git: History is immutable (you can rewrite, but original exists)
   - React: State updates are asynchronous (can't read immediately after setting)
   - SQL: Operations are set-based (think in sets, not loops)

4. WHERE ARE THE BOUNDARIES?
   - Docker: Container ↔ Host (network, filesystem, processes are isolated)
   - Git: Local repo ↔ Remote repo (push/pull are the boundaries)
   - React: Component ↔ Component (props are the interface)

5. WHAT HAPPENS WHEN THINGS GO WRONG?
   - Docker: Container crash → restart policy → logs
   - Git: Merge conflict → manual resolution → commit
   - React: Render error → error boundary → fallback UI
```

**Example: Building a mental model for Redis**

```
Step 1: Core abstraction
  "A fast in-memory key-value store"

Step 2: What goes in, what comes out
  SET key value → OK
  GET key → value (or nil)
  Data types: strings, lists, sets, hashes, sorted sets

Step 3: Rules/constraints
  - Data is in memory (limited by RAM)
  - Single-threaded (one operation at a time — no race conditions!)
  - Persistence is optional (RDB snapshots, AOF log)
  - Keys can expire (TTL)

Step 4: Boundaries
  - Client ↔ Redis server (TCP connection)
  - Redis ↔ Disk (optional persistence)
  - Redis ↔ Redis (replication, clustering)

Step 5: Failure modes
  - Out of memory → eviction policy kicks in
  - Server crash → data loss since last snapshot
  - Network partition → split brain in cluster mode

Mental model summary:
  "Redis is a dictionary in RAM. It's fast because memory,
   simple because single-threaded, and lossy because RAM is
   volatile. Use it for caching and ephemeral data, not as
   your only data store."
```

**The "draw it" technique:**
```
For any new technology, draw a box diagram:

  [Client] → request → [Technology] → result → [Client]
                              ↓
                         [Storage/State]

Then fill in:
  - What are the clients?
  - What kinds of requests?
  - What state does it maintain?
  - Where does state live? (memory, disk, network)

If you can draw the system, you understand it.
If you can't draw it, you don't understand it yet.
```

**Testing your mental model:**
```
Make predictions, then verify:
  "Based on my model, if I do X, Y should happen."
  → Try it. Did Y happen?
  → Yes: Model is accurate (for this case)
  → No: Model is wrong. Update it.

Example with Docker:
  Prediction: "If I write a file inside a container and restart
               the container, the file should be gone."
  Test: Write file, restart, check.
  Result: File is gone → Model confirmed (containers are ephemeral)
```

**The meta-principle:** A mental model doesn't need to be perfectly accurate — it needs to be useful. Start with a simple model that explains 80% of behavior, then refine it as you encounter cases it doesn't explain. The goal is predictive power: if your model lets you guess what will happen before trying it, it's a good model.'''
    ),
    (
        "thinking/auto-metalearning-mental-model-for-databases",
        r'''I use databases but I don't really understand what happens between my query and the result. How do I build a mental model for how databases actually process queries?''',
        r'''<think>
Most developers treat databases as black boxes — write a query, get results. But a mental model of query processing helps you write better queries, understand performance, and debug slow queries.

The key stages:
1. Parse the SQL → syntax tree
2. Plan the query → execution plan (this is the critical part)
3. Execute the plan → read/write data
4. Return results

The query planner is where the magic happens — it decides HOW to get the data (which index, which join algorithm, what order). Understanding the planner's decisions is what separates developers who write fast queries from those who don't.
</think>

**Mental Model: How Databases Process Queries**

**The query lifecycle:**
```
Your query: SELECT * FROM users WHERE email = 'a@b.com'

Step 1: PARSE
  SQL text → Abstract Syntax Tree
  "Is this valid SQL? What tables/columns are referenced?"
  → If syntax error, stop here with an error message.

Step 2: PLAN (this is where performance is determined)
  "How should I get this data?"

  Option A: Full table scan
    Read EVERY row in users table, check email column.
    Cost: O(n) — reads all 10 million rows.

  Option B: Index scan
    Look up 'a@b.com' in the email index → get row location → read row.
    Cost: O(log n) — reads ~23 entries in the index tree.

  The planner picks the cheapest option based on:
    - Available indexes
    - Table statistics (how many rows, data distribution)
    - Memory available for sorting/hashing

Step 3: EXECUTE
  Run the chosen plan, reading data from disk/cache.

Step 4: RETURN
  Stream results back to the client.
```

**The critical mental model: Indexes**
```
Without index:
  Table: [row1][row2][row3]...[row10M]
  Finding email = 'a@b.com' → scan ALL rows → slow

With index on email:
  Index (B-tree):
              [m]
           /       \
        [d]         [s]
       /   \       /   \
    [a@b] [f@g] [p@q] [z@w]
      ↓     ↓     ↓     ↓
    row5  row2  row8  row1

  Finding email = 'a@b.com' → traverse tree → 3 lookups → fast

  Think of it like a book index:
    Without index: Read every page to find "async programming"
    With index: Look up "async" in the back → go to page 47
```

**The mental model for JOINs:**
```
SELECT * FROM orders JOIN users ON orders.user_id = users.id

The database has THREE ways to join:

1. Nested Loop Join (simple, good for small tables):
   For each order:
     Find the matching user
   Like: Looking up each student's grade one at a time

2. Hash Join (good for large tables, no index):
   Load all users into a hash table
   For each order: hash lookup → instant match
   Like: Building a lookup directory first, then using it

3. Merge Join (good when both sides are sorted):
   Sort both tables by join key
   Walk through both simultaneously, matching as you go
   Like: Merging two sorted card decks

The planner picks based on table sizes, available indexes,
and available memory.
```

**The mental model for transactions:**
```
BEGIN TRANSACTION;
  UPDATE accounts SET balance = balance - 100 WHERE id = 1;
  UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;

What the database guarantees (ACID):
  Atomic: Both updates happen, or neither does.
  Consistent: Constraints are checked (balance >= 0).
  Isolated: Other transactions see the old OR new state, not half.
  Durable: After COMMIT, data survives a power outage.

Mental model: A transaction is a bubble. Inside the bubble,
you see your changes. Outside, nobody sees anything until
you commit. If you abort, nothing happened.
```

**How to use this mental model practically:**
```
Slow query? Ask:
  1. "Is there an index on the columns in my WHERE clause?"
     → No? Create one. Instant 100-1000x speedup possible.

  2. "Am I selecting more columns than I need?"
     → SELECT * reads entire rows. SELECT name, email reads less.

  3. "Am I joining too many tables?"
     → Each join multiplies the work. Can I denormalize?

  4. "Am I doing work the database could do?"
     → Filter in SQL (WHERE), not in application code.
     → Sort in SQL (ORDER BY), not in application code.

  Use EXPLAIN to see what the planner chose:
    EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'a@b.com';
    → Shows: index scan vs table scan, time per step, rows examined
```

**The meta-principle:** You don't need to understand B-tree page splits or buffer pool management. But you DO need to understand: indexes make lookups fast, the planner chooses how to execute, and EXPLAIN shows you the plan. That mental model covers 90% of database performance issues you'll encounter.'''
    ),
    (
        "thinking/auto-metalearning-mental-model-for-networking",
        r'''I know HTTP requests go from browser to server and back, but my mental model falls apart when things go wrong (timeouts, DNS failures, TLS errors). How do I build a more complete networking mental model?''',
        r'''<think>
Most developers have a "happy path" mental model for networking: request goes out, response comes back. But networking failures are common, and without understanding the layers involved, debugging becomes guesswork.

The key is the layer model — not memorizing all 7 OSI layers, but understanding the 4 practical layers that matter for web developers:
1. DNS (name → IP address)
2. TCP (reliable connection)
3. TLS (encryption)
4. HTTP (application data)

Each layer can fail independently, and each produces different error messages.
</think>

**Mental Model: Web Networking for Developers**

**The 4 layers that matter (simplified):**
```
When you type https://api.example.com/users:

Layer 1: DNS — "What IP address is api.example.com?"
  Your computer → DNS resolver → "It's 93.184.216.34"
  Time: 1-100ms (cached after first lookup)
  Failure: "DNS resolution failed" / "Name not found"

Layer 2: TCP — "Establish a reliable connection"
  Your computer ↔ 93.184.216.34 (3-way handshake: SYN, SYN-ACK, ACK)
  Time: 10-200ms (depends on distance)
  Failure: "Connection refused" / "Connection timed out"

Layer 3: TLS — "Encrypt the connection"
  Verify certificate → negotiate encryption → exchange keys
  Time: 50-300ms (adds 1-2 round trips)
  Failure: "Certificate error" / "TLS handshake failed"

Layer 4: HTTP — "Send the request, get the response"
  Send: GET /users HTTP/1.1 Host: api.example.com
  Receive: 200 OK { "users": [...] }
  Time: Varies (depends on server processing + data size)
  Failure: 4xx/5xx status codes, timeout

Total time for a new HTTPS request: 200-700ms for the first request.
Subsequent requests reuse the connection: 10-100ms.
```

**Debugging with the layer model:**

```
ERROR: "Could not resolve host"
  → DNS failed (Layer 1)
  → Is the domain spelled correctly?
  → Is DNS working? Try: nslookup api.example.com
  → Are you on a network? Can you resolve google.com?

ERROR: "Connection refused"
  → TCP failed (Layer 2) — server is not listening
  → Is the server running?
  → Is the port correct? (80 for HTTP, 443 for HTTPS)
  → Is a firewall blocking the connection?

ERROR: "Connection timed out"
  → TCP failed (Layer 2) — no response at all
  → Is the server reachable? Try: ping 93.184.216.34
  → Is there a network path? Try: traceroute api.example.com
  → Is a firewall DROPPING (not rejecting) packets?

ERROR: "SSL certificate problem"
  → TLS failed (Layer 3)
  → Is the certificate expired?
  → Does the certificate match the hostname?
  → Is it a self-signed cert? (need to explicitly trust it)
  → Is the clock on your machine correct? (cert validation uses time)

ERROR: "500 Internal Server Error"
  → HTTP layer (Layer 4) — request reached the server, server crashed
  → Check server logs
  → Is the request well-formed?

ERROR: "Timeout (30s)"
  → Could be any layer, but usually Layer 4
  → Server is processing too slowly
  → Check: Is the server under heavy load?
  → Check: Is the query/operation slow? (database?)
```

**The connection lifecycle mental model:**
```
First request to a new server:

  [DNS lookup]  →  [TCP handshake]  →  [TLS handshake]  →  [HTTP request/response]
     50ms              100ms               200ms                 150ms
                                                          Total: ~500ms

Second request (connection reuse):

  [HTTP request/response]
         50ms
  Total: ~50ms (10x faster!)

This is why:
  - Connection pooling matters (reuse connections)
  - HTTP/2 multiplexing matters (multiple requests on one connection)
  - Keep-alive headers matter (don't close connections between requests)
```

**The timeout mental model:**
```
Different things can time out at different layers:

DNS timeout:     ~5 seconds (then try next DNS server)
TCP connect:     ~10-30 seconds (OS default)
TLS handshake:   ~10-30 seconds (part of connect timeout)
HTTP response:   Configurable (you set this in your HTTP client)
  - Read timeout: Time waiting for data after connection established
  - Total timeout: Total time for the entire request

Best practice:
  connect_timeout = 5 seconds (if can't connect in 5s, it's down)
  read_timeout = 30 seconds (server has 30s to start responding)
  total_timeout = 60 seconds (entire operation must complete)
```

**The meta-principle:** Every network request passes through multiple layers, and each layer can fail independently. When something goes wrong, identify WHICH layer failed — the error message usually tells you. DNS errors, connection errors, TLS errors, and HTTP errors have completely different causes and solutions. Don't guess — diagnose by layer.'''
    ),
    (
        "thinking/auto-metalearning-mental-model-for-containers",
        r'''I use Docker but I don't really get what containers are. My mental model is "lightweight VMs" but I've been told that's wrong. How do I build an accurate mental model for containers?''',
        r'''<think>
"Containers are lightweight VMs" is the most common misconception. It's a useful starting analogy but it breaks down in important ways. The key difference: VMs virtualize hardware (each VM has its own kernel), while containers virtualize the OS (all containers share the host kernel).

**Accurate mental model:**
A container is a process (or group of processes) running on the host OS, but with isolated views of:
- The filesystem (sees its own root filesystem)
- The network (has its own IP address, ports)
- The process table (can only see its own processes)
- Users (root in container is not root on host, usually)

It's like a process wearing blinders — it can only see what it's been allowed to see. But it's still running on the same kernel as the host.
</think>

**Mental Model: What Containers Actually Are**

**The wrong model (VM analogy):**
```
Virtual Machine:
  ┌──────────────────┐  ┌──────────────────┐
  │   App A          │  │   App B          │
  │   Libraries      │  │   Libraries      │
  │   Guest OS       │  │   Guest OS       │
  │   Virtual HW     │  │   Virtual HW     │
  └──────────────────┘  └──────────────────┘
  ┌──────────────────────────────────────────┐
  │         Hypervisor (VMware, KVM)         │
  │         Host OS + Real Hardware          │
  └──────────────────────────────────────────┘

  Each VM has its OWN operating system kernel.
  Heavy: 500MB+ per VM, minutes to start.
```

**The correct model (isolated process):**
```
Container:
  ┌──────────────┐  ┌──────────────┐
  │  App A       │  │  App B       │
  │  Libraries   │  │  Libraries   │
  │  (isolated   │  │  (isolated   │
  │   view)      │  │   view)      │
  └──────┬───────┘  └──────┬───────┘
         │                  │
  ┌──────┴──────────────────┴──────┐
  │     Shared Host OS Kernel      │
  │     Real Hardware              │
  └────────────────────────────────┘

  Containers share the host kernel.
  Light: ~10MB overhead, seconds to start.
  They're just PROCESSES with restrictions.
```

**The "process with blinders" mental model:**
```
A container is a normal process that:
  1. Has its own filesystem (can't see host files)
  2. Has its own network (own IP, own ports)
  3. Has its own process list (can't see other containers' processes)
  4. Has resource limits (can only use X% CPU, Y MB RAM)

It's like an employee in a cubicle:
  - They have their own desk (filesystem)
  - They have their own phone extension (network)
  - They can't see into other cubicles (process isolation)
  - They have a budget limit (resource constraints)
  But they're all in the SAME BUILDING (same kernel).

A VM is like a separate building entirely.
```

**What this means in practice:**

```
IMPLICATION 1: Containers start fast (it's just starting a process)
  docker run → ~1 second (not booting an OS, just running a process)
  VM start → ~30-60 seconds (booting a full OS)

IMPLICATION 2: Containers share the host kernel
  Linux containers run on a Linux kernel.
  "Docker for Mac/Windows" runs a hidden Linux VM,
  then runs containers inside THAT.

IMPLICATION 3: Isolation is weaker than VMs
  A VM escape requires breaking through the hypervisor (very hard).
  A container escape requires breaking through kernel namespaces
  (harder than normal process escape, but easier than VM escape).
  → Don't run untrusted code in containers without extra security.

IMPLICATION 4: The filesystem is layered
  Docker images are built in layers:
    Layer 1: Ubuntu base (200MB)
    Layer 2: Python installed (+50MB)
    Layer 3: Your app code (+5MB)

  Layers are shared between containers.
  10 containers using the same base image don't use 10x the disk space.
  Like transparent sheets stacked on an overhead projector.
```

**The Dockerfile mental model:**
```
A Dockerfile is a recipe for building a filesystem:

  FROM python:3.11        ← Start with Python's filesystem
  COPY app.py /app/       ← Add your code
  RUN pip install flask   ← Install dependencies
  CMD ["python", "/app/app.py"]  ← Default command to run

  Each line creates a LAYER.
  Think of it as: "Start with this base, then modify."

  The resulting image is a snapshot of the filesystem.
  Running the image creates a container (a process using that filesystem).
```

**Docker Compose mental model:**
```
docker-compose.yml describes a group of containers:

  services:
    web:     ← container 1: your app
    db:      ← container 2: PostgreSQL
    redis:   ← container 3: Redis cache

  They share a virtual network (can talk to each other by name).
  "web" can reach "db" at hostname "db" on port 5432.

  Think of it as: "Here are the services I need running together."
```

**The meta-principle:** A container is not a VM — it's a process with isolated views of the filesystem, network, and process table. This distinction matters for security (containers are less isolated than VMs), performance (containers are lighter than VMs), and debugging (you can inspect container processes from the host because they're just processes). Once you internalize "it's just a process with blinders," Docker behavior becomes intuitive.'''
    ),
    (
        "thinking/auto-metalearning-mental-model-revision",
        r'''My mental models sometimes turn out to be wrong. How do I detect when a mental model is inaccurate and how do I update it without starting from scratch?''',
        r'''<think>
Mental model revision is crucial because wrong models lead to wrong predictions, wrong debugging strategies, and wrong design decisions. The challenge is that we tend to defend our existing models rather than update them — confirmation bias makes us notice evidence that supports our model and ignore evidence that contradicts it.

**Signs a mental model needs revision:**
1. Predictions based on the model are wrong
2. Debugging using the model leads to dead ends
3. Experts describe the system differently than your model
4. Edge cases can't be explained by your model
5. You need many "special case" exceptions to maintain the model

**The update process:**
- Don't throw out the entire model (usually most of it is right)
- Identify the specific part that's wrong
- Understand WHY it's wrong (what does the correct model explain that yours doesn't?)
- Update the specific part while keeping what works
</think>

**Detecting and Updating Wrong Mental Models**

**Signs your mental model is broken:**

```
Signal 1: SURPRISE
  If the system does something you didn't expect, your model
  is wrong about SOMETHING.

  "I expected this query to use the index, but EXPLAIN shows
   a full table scan."
  → Your model of when the optimizer uses indexes is wrong.

Signal 2: DEBUGGING DEAD ENDS
  If your debugging strategy (based on your model) keeps
  leading nowhere, the model guiding your search is wrong.

  "I keep checking the cache because my model says the problem
   is caching, but the cache is fine every time."
  → Maybe the problem isn't caching. Question the model.

Signal 3: THE "EXCEPT" COUNT
  If you need to say "except" more than twice, the model
  is probably wrong:

  "React re-renders when state changes, EXCEPT when using
   useMemo, EXCEPT when the dependency array is wrong,
   EXCEPT when using useRef, EXCEPT in concurrent mode..."
  → Too many exceptions. Your base model of "when React
     re-renders" needs revision.

Signal 4: EXPERT DISAGREEMENT
  When an expert describes the system differently than your model:

  You: "Containers are like lightweight VMs"
  Expert: "Actually, containers are just processes with
           namespace isolation"
  → Don't defend your model. Ask: "What does your model
     explain that mine can't?"
```

**The model update protocol:**

```
Step 1: IDENTIFY THE BROKEN PART
  Your model: "JavaScript is single-threaded, so async
               operations block the thread."
  Reality: Async operations DON'T block the thread.
  Broken part: Understanding of what "single-threaded" means
               for async operations.
  (The "single-threaded" part is correct. The "blocking" part is wrong.)

Step 2: UNDERSTAND WHY IT'S WRONG
  Single-threaded means one call stack.
  But async operations (network, timers) are handled by the
  browser/OS OUTSIDE the JS thread.
  The event loop picks up results when the thread is free.

Step 3: UPDATE THE SPECIFIC PART
  Old model: "Single-threaded → everything blocks"
  New model: "Single-threaded → one call stack, but async
              work happens outside the thread. The event loop
              bridges between the thread and external work."

Step 4: TEST THE UPDATED MODEL
  "If my new model is right, then a setTimeout(fn, 0) shouldn't
   block, and fn should run after the current call stack clears."
  → Test it. Confirmed? Model updated successfully.
```

**Common mental model revisions developers need:**

| Wrong model | Correct model |
|-------------|---------------|
| "More threads = faster" | "More threads = faster for I/O-bound work, not CPU-bound (GIL, context switching)" |
| "Caching always helps" | "Caching helps for read-heavy, rarely-changing data. Cache invalidation causes bugs." |
| "Microservices are better than monoliths" | "Microservices solve scaling/team problems but add complexity. Monoliths are fine for small teams." |
| "NoSQL is faster than SQL" | "NoSQL trades consistency/query flexibility for specific performance characteristics." |
| "HTTPS is slow" | "HTTPS adds ~100ms for the first connection. HTTP/2+TLS is faster than HTTP/1.1 without TLS." |

**The "steel man" technique for model updates:**
```
When your model conflicts with new information:

1. DON'T: "That must be a special case. My model is right."
   (Defending the old model)

2. DO: "What is the STRONGEST version of the new information?
        If it's true, what part of my model must change?"
   (Steel-manning the new information)

3. TEST: "Can I design an experiment that would show whether
          my old model or the new model is correct?"
   (Let evidence decide)
```

**The meta-principle:** Mental models are tools, not identities. When a model stops making accurate predictions, it needs maintenance — just like code. The best developers continuously revise their models based on evidence. Holding onto a wrong model because you've believed it for years is like refusing to fix a bug because the code has been in production for years. Fix the model, make better predictions, write better software.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
