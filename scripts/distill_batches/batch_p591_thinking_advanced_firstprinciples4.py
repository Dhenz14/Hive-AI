"""Phase 2H: Advanced Reasoning — First Principles Derivation (Part 4/8)"""

PAIRS = [
    (
        "thinking/firstprinciples-api-authentication",
        "I need to add authentication to my REST API. There are so many options — JWT, session cookies, API keys, OAuth. Can you help me understand which to use by building up from the fundamentals?",
        r'''<think>
Let me derive API authentication from first principles rather than jumping to "use JWT."

**What problem are we solving?**
HTTP is stateless. Each request is independent. But we need the server to know WHO is making the request. Authentication bridges this gap.

**First principle: Proving identity requires a shared secret**
The client must present something that:
1. Only the legitimate user could know or possess
2. The server can verify
3. Can't be easily forged or replayed

**What are the fundamental options?**
Option A: Send credentials with every request (Basic Auth)
- Client sends username:password on each request
- Simple, but: password transmitted repeatedly (even over HTTPS, this is risky)
- No way to revoke access without changing the password
- No expiration

Option B: Exchange credentials for a token, send token thereafter
- Client authenticates once, gets a token
- Token is sent on subsequent requests
- Server validates the token without needing the password again

This is fundamentally better because:
- Password is only sent once
- Token can expire
- Token can be revoked without changing the password
- Token can carry permissions (scopes)

**Now: where does the token live?**
Two options:
1. Server stores the token and looks it up (session-based)
2. Token is self-contained and server validates it cryptographically (JWT)

Session-based: Server stores session_id → user mapping in DB/Redis. Token is just a random ID.
- Pros: easy to revoke (delete from store), no size limits
- Cons: requires a database lookup on every request, hard to scale across multiple servers without shared storage

JWT: Token contains the user data, signed by the server's secret key.
- Pros: no database lookup needed (stateless), scales easily
- Cons: can't revoke until expiration (unless you add a blacklist, which reintroduces state), token size grows with claims

**When to use which?**
This depends on WHO the client is:
1. Browser (human user) → session cookies (secure, httpOnly, SameSite)
2. Mobile app → JWT (no cookie jar, needs to work cross-origin)
3. Another service (machine-to-machine) → API keys or JWT
4. Third-party app accessing user data → OAuth 2.0 (delegated authorization)

Let me derive each recommendation from the constraints.
</think>

Let me build up authentication from fundamentals rather than jumping to solutions.

## The Core Problem

```
HTTP is stateless → server doesn't know who's calling
Authentication = "prove your identity so I don't have to ask every time"
```

## First Principle: The Authentication Triangle

Every auth system must solve three things:

```
1. PROVE: Client proves they are who they claim to be
2. REMEMBER: Server remembers the proof for subsequent requests
3. FORGET: Server can revoke access when needed
```

## Deriving the Right Solution From Constraints

### Who is the client? → This determines everything.

```
Client is a BROWSER (human user)?
├── Has cookie jar ✓
├── Vulnerable to XSS and CSRF ✓
├── Needs to work with same-origin policy ✓
└── → Use SESSION COOKIES

Client is a MOBILE APP?
├── No cookie jar ✗
├── Can store tokens securely (Keychain/Keystore) ✓
├── Needs to work offline sometimes ✓
└── → Use JWT (short-lived) + REFRESH TOKEN

Client is another SERVICE (machine-to-machine)?
├── No user involved ✓
├── Long-lived credential is OK ✓
├── Needs simple integration ✓
└── → Use API KEYS

Third-party app accessing YOUR users' data?
├── You can't share your users' passwords ✓
├── Need scoped, revocable access ✓
├── Need user consent ✓
└── → Use OAUTH 2.0
```

### Implementation for Each

#### 1. Browser → Session Cookies

```python
from flask import Flask, session, request, jsonify
from flask_session import Session
import redis

app = Flask(__name__)
app.config["SESSION_TYPE"] = "redis"
app.config["SESSION_REDIS"] = redis.Redis()
Session(app)

@app.route("/login", methods=["POST"])
def login():
    user = authenticate(request.json["email"], request.json["password"])
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    session["user_id"] = user.id
    session["role"] = user.role
    # Flask sets a cookie automatically:
    # Set-Cookie: session=abc123; HttpOnly; Secure; SameSite=Lax
    return jsonify({"message": "Logged in"})

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()  # Easy revocation — delete server-side
    return jsonify({"message": "Logged out"})

@app.route("/api/data")
def get_data():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    # Session cookie sent automatically by browser
    return jsonify({"data": "..."})
```

**Why cookies for browsers?**
- `HttpOnly` flag → JavaScript can't read it (prevents XSS token theft)
- `Secure` flag → only sent over HTTPS
- `SameSite=Lax` → prevents CSRF for most cases
- Browser handles storage and sending automatically

#### 2. Mobile App → JWT + Refresh Token

```python
import jwt
import secrets
from datetime import datetime, timedelta

SECRET_KEY = os.environ["JWT_SECRET"]

@app.route("/auth/token", methods=["POST"])
def get_token():
    user = authenticate(request.json["email"], request.json["password"])
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    # Short-lived access token (15 minutes)
    access_token = jwt.encode({
        "sub": user.id,
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(minutes=15),
        "iat": datetime.utcnow(),
    }, SECRET_KEY, algorithm="HS256")

    # Long-lived refresh token (30 days) — stored in DB for revocation
    refresh_token = secrets.token_urlsafe(32)
    db.save_refresh_token(refresh_token, user_id=user.id,
                         expires_at=datetime.utcnow() + timedelta(days=30))

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": 900,
    })

@app.route("/auth/refresh", methods=["POST"])
def refresh():
    """Exchange refresh token for new access token."""
    refresh_token = request.json["refresh_token"]
    token_data = db.get_refresh_token(refresh_token)

    if not token_data or token_data.expires_at < datetime.utcnow():
        return jsonify({"error": "Invalid refresh token"}), 401

    user = db.get_user(token_data.user_id)
    access_token = jwt.encode({
        "sub": user.id,
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(minutes=15),
    }, SECRET_KEY, algorithm="HS256")

    return jsonify({"access_token": access_token, "expires_in": 900})
```

**Why JWT for mobile?**
- No cookie jar available
- Stateless verification (no DB lookup for most requests)
- Short expiry limits damage if token is stolen
- Refresh token provides long-lived sessions with revocation capability

#### 3. Machine-to-Machine → API Keys

```python
@app.route("/api/data")
def get_data():
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return jsonify({"error": "Missing API key"}), 401

    # Look up key (hashed in DB, not stored plaintext)
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    key_record = db.get_api_key(key_hash)

    if not key_record or key_record.revoked:
        return jsonify({"error": "Invalid API key"}), 401

    # Check scopes
    if "read:data" not in key_record.scopes:
        return jsonify({"error": "Insufficient permissions"}), 403

    return jsonify({"data": "..."})
```

**Why API keys for services?**
- Simplest integration (just add a header)
- Long-lived by design (no refresh flow needed)
- Easy to rotate and revoke per-service
- No user context needed

## Decision Cheat Sheet

| Client | Auth Method | Token Lifetime | Storage |
|--------|------------|---------------|---------|
| Browser | Session cookie | Hours-days | Server-side (Redis) |
| Mobile app | JWT + refresh | 15min + 30days | Client-side (Keychain) |
| Service | API key | Months-years | Server-side (DB) |
| Third-party | OAuth 2.0 | 1 hour + refresh | Client-side |

The auth method isn't about preference — it's derived from the client's constraints and capabilities.'''
    ),
    (
        "thinking/firstprinciples-database-index",
        "I know I should add indexes to my database for performance, but I don't really understand how they work or when to add them. Can you explain indexes from first principles?",
        r'''<think>
Let me derive database indexes from first principles.

**The fundamental problem:**
You have a table with 1 million rows. You want to find all orders where `customer_id = 42`. Without an index, the database must check EVERY ROW (full table scan). That's 1 million comparisons.

**What if we could skip to the right rows directly?**
This is what an index does. But HOW?

**First principles approach: think about a phone book.**
A phone book is sorted by last name. To find "Smith":
- You don't read every entry (full scan)
- You open to the middle (M), it's before S, so go right half
- Open to 3/4 (R-S area), find the S section
- Scan through Smith entries

This is binary search: O(log n) instead of O(n).
For 1 million rows: log2(1,000,000) ≈ 20 comparisons instead of 1,000,000.

**But a database isn't a sorted list.** You can't sort the table by customer_id because it's already stored in insertion order (heap). And you might need to search by customer_id, status, AND date — you can't sort by all three.

**Solution: create a SEPARATE sorted structure that points back to the table.**
This is an index. It's a sorted data structure (usually a B-tree) that maps:
`column_value → location of the row in the table`

**Why B-tree specifically?**
A binary search tree would work but has too many levels for disk I/O. Each level requires a disk read. A B-tree is a "wide" tree — each node has hundreds of children, so the tree is very shallow (usually 3-4 levels for millions of rows). 3-4 disk reads instead of 20.

**The trade-offs:**
- Index SPEEDS UP reads (find rows by indexed columns)
- Index SLOWS DOWN writes (every INSERT/UPDATE/DELETE must also update the index)
- Index USES DISK SPACE (a copy of the indexed columns + pointers)

This is why you don't index everything — each index is a cost paid on EVERY write.

**When to add an index:**
- Column is used in WHERE clauses frequently
- Column is used in JOIN conditions
- Column is used in ORDER BY
- The table has many rows (indexes are pointless on small tables)
- The column has high cardinality (many unique values)

**When NOT to add an index:**
- Table is small (<1000 rows)
- Column has low cardinality (e.g., boolean — only 2 values)
- Table is write-heavy and rarely queried
- You already have too many indexes (slowing writes)
</think>

Let me build up from the absolute basics.

## The Core Problem

```
Table: orders (1,000,000 rows)

Query: SELECT * FROM orders WHERE customer_id = 42

WITHOUT index:
  Database reads ALL 1,000,000 rows, checks each one.
  → 1,000,000 comparisons. Slow.

WITH index on customer_id:
  Database looks up "42" in a sorted structure, gets row locations.
  → ~3-4 disk reads. Fast.
```

## How It Works: The Phone Book Analogy

```
A phone book IS an index.

DATA (unsorted people in a city):
  Row 1: Alice, 555-0101, 123 Oak St
  Row 2: Charlie, 555-0103, 789 Pine St
  Row 3: Bob, 555-0102, 456 Elm St
  ... 1 million more people

PHONE BOOK (index on last_name):
  Adams, Alice → Row 1
  Brown, Bob → Row 3
  Clark, Charlie → Row 2
  ...
  (sorted alphabetically, with pointers to the actual data)

To find "Clark":
  - Don't scan all people (full table scan)
  - Binary search the phone book: open to middle, go left/right
  - 20 steps max for 1 million entries
  - Follow the pointer to Row 2
```

## The B-Tree: Why Databases Use Wide Trees

```
Binary tree (20 levels for 1M rows — too deep):
         50
        /  \
      25    75
     / \   / \
   ...  many levels deep...

B-tree (3-4 levels for 1M rows — shallow and fast):
  [10 | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90]  ← Root node (1 disk read)
   /    |    |         |                      \
  [...] [...] [...]   [...]                  [...]  ← Branch nodes (1 disk read)
  /  |   |  \
 [1,2,3] [4,5,6] [7,8,9] [10,11,12]               ← Leaf nodes (1 disk read)
                                                       (contain pointers to rows)

Each node = 1 disk page (~8KB, holds hundreds of keys)
3 disk reads to find ANY value in 1 million rows.
```

## Practical Index Usage

```sql
-- See which indexes exist on a table
-- PostgreSQL:
\d orders

-- See if your query USES an index
EXPLAIN ANALYZE SELECT * FROM orders WHERE customer_id = 42;

-- Results WITHOUT index:
--   Seq Scan on orders  (cost=0..25000 rows=1000000)
--   Filter: (customer_id = 42)
--   Execution Time: 850.000 ms

-- Results WITH index:
--   Index Scan using idx_orders_customer_id on orders  (cost=0..8.50 rows=10)
--   Index Cond: (customer_id = 42)
--   Execution Time: 0.150 ms
```

## When to Add Indexes (Decision Framework)

```sql
-- ADD an index when:

-- 1. Column in WHERE clause on large table
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
-- Speeds up: WHERE customer_id = 42

-- 2. Column in JOIN condition
CREATE INDEX idx_order_items_order_id ON order_items(order_id);
-- Speeds up: JOIN order_items ON orders.id = order_items.order_id

-- 3. Column in ORDER BY (avoids sorting)
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);
-- Speeds up: ORDER BY created_at DESC

-- 4. Composite index for multi-column queries
CREATE INDEX idx_orders_status_date ON orders(status, created_at);
-- Speeds up: WHERE status = 'pending' AND created_at > '2024-01-01'
-- Column order matters! Most selective column first.

-- 5. Covering index (includes all needed columns)
CREATE INDEX idx_orders_covering ON orders(customer_id) INCLUDE (total, status);
-- Speeds up: SELECT total, status FROM orders WHERE customer_id = 42
-- Database doesn't need to read the table at all — index has everything.
```

## When NOT to Index

```sql
-- DON'T index when:

-- 1. Small tables (<1000 rows) — full scan is fine
-- A full scan of 1000 rows takes <1ms. Index overhead isn't worth it.

-- 2. Low cardinality columns
CREATE INDEX idx_orders_is_active ON orders(is_active);  -- BAD
-- Only 2 values (true/false). Index doesn't help because
-- ~50% of rows match. Full scan might be faster.

-- 3. Write-heavy tables that are rarely queried
-- Every INSERT/UPDATE/DELETE must update ALL indexes.
-- 10 indexes on a table = 10x write overhead.

-- 4. Columns not used in queries
-- Sounds obvious but: don't preemptively index "just in case."
```

## The Trade-Off Summary

```
               Read Speed    Write Speed    Disk Space
No index:      Slow (scan)   Fast           None
With index:    Fast (lookup)  Slower         More
Many indexes:  Very fast      Much slower    Much more

Rule of thumb:
  - Most tables need 2-5 indexes
  - More than 10 indexes on one table is a code smell
  - Monitor slow queries (pg_stat_statements) and add indexes
    for actual slow queries, not hypothetical ones
```

Indexes are a sorted lookup structure separate from your data. They trade write performance and disk space for dramatically faster reads. Add them for columns you filter, join, and sort on — but only when the table is large enough to benefit.'''
    ),
    (
        "thinking/firstprinciples-message-queue",
        "Why would I use a message queue like RabbitMQ or Redis Pub/Sub instead of just making HTTP calls between my services? What problem does it actually solve?",
        r'''<think>
Let me derive message queues from first principles instead of just listing features.

**Start with the simplest architecture: direct HTTP calls**
Service A needs to notify Service B that an order was placed.
Simplest approach: A calls B's HTTP endpoint.

```
A: POST /api/orders → B: POST /api/process-order
```

This works. Why would you need anything else?

**Problem 1: Coupling**
A must know B's address, B must be running, B must respond quickly. If B is down, A either fails or has to implement retry logic. A and B are temporally coupled — they must both be alive at the same time.

**Problem 2: Blocking**
A waits for B to respond. If B takes 10 seconds, A's request takes 10+ seconds. The user is waiting.

**Problem 3: Fan-out**
Now C and D also need to know about the order. A must call B, C, and D. If E joins later, A's code must change. A knows about every consumer.

**Problem 4: Load mismatch**
A handles 1000 orders/second. B can only process 100/second. Direct calls cause B to crash. A must somehow slow down, which slows A down too.

**What if there was a middleman?**
A drops a message on a shelf. B picks it up when ready. A doesn't wait. A doesn't know who picks it up.

This is a message queue.

It solves:
1. Temporal decoupling — A and B don't need to be alive at the same time
2. Asynchrony — A doesn't block waiting for B
3. Fan-out — A publishes once, multiple consumers pick it up
4. Load leveling — B processes at its own pace

**But when do you NOT need it?**
- When you need a synchronous response (user needs the result NOW)
- When you have 2-3 services that are always available
- When the added complexity isn't worth the decoupling benefit

Let me build the whole explanation from these fundamentals.
</think>

Let me build the answer by starting with HTTP calls and discovering WHY you'd want something different.

## Start With Direct HTTP Calls

```
Simple and works:
  Order Service → POST /process → Payment Service
  Payment Service → POST /ship → Shipping Service
  Shipping Service → POST /notify → Email Service
```

This is fine until you hit one of these four walls:

## Wall 1: Service B Goes Down

```
Order Service → POST /process → Payment Service 💀 (crashed)
                                  ↓
                         Connection refused!
                                  ↓
              Order Service must: retry? fail? store and retry later?
              Meanwhile, the user is waiting...

WITH a queue:
  Order Service → [Queue] ← Payment Service (when it recovers)
                    ↓
  Message sits safely in queue until Payment Service comes back.
  Order Service already responded to the user: "Order received!"
```

## Wall 2: You Need to Notify Multiple Services

```
WITHOUT queue (A knows all consumers):
  Order Service → POST /process → Payment Service
                → POST /ship → Shipping Service
                → POST /notify → Email Service
                → POST /track → Analytics Service
                → POST /sync → CRM Service

  Adding a new consumer? Change Order Service code.

WITH queue (A publishes once):
  Order Service → publish("order.created") → [Queue]
                                               ↓
                              Payment Service subscribes ←┘
                              Shipping Service subscribes ←┘
                              Email Service subscribes ←┘
                              Analytics Service subscribes ←┘
                              (Add CRM Service without touching Order Service)
```

## Wall 3: B Is Slower Than A

```
WITHOUT queue:
  A: 1000 orders/sec → B: handles 100/sec
  B drowns. 900 requests/sec fail. B crashes. Users get errors.

WITH queue (load leveling):
  A: 1000 orders/sec → [Queue grows] → B: processes at 100/sec
  Queue absorbs the burst. B processes at its own pace.
  Queue: [████████████████████]  ← buffer
  B chews through it over time. No data lost. No crashes.
```

## Wall 4: User Doesn't Need to Wait

```
WITHOUT queue (synchronous):
  User → Order Service → Payment (2s) → Shipping (1s) → Email (3s) → User
  Total: 6 seconds. User is waiting the entire time.

WITH queue (asynchronous):
  User → Order Service → "Order received!" → User (200ms)
                       → publish("order.created")
                                ↓
              [Payment processes in background]
              [Shipping processes in background]
              [Email sends in background]
  Total wait for user: 200ms.
```

## Practical Implementation

```python
# PRODUCER: Order Service (publishes events, doesn't care who listens)
import redis

r = redis.Redis()

def create_order(order_data):
    order = db.create_order(order_data)

    # Publish event — fire and forget
    r.publish("orders", json.dumps({
        "event": "order.created",
        "order_id": order.id,
        "customer_id": order.customer_id,
        "total": float(order.total),
    }))

    return order  # Return immediately — don't wait for consumers


# CONSUMER: Payment Service (subscribes to events)
def process_orders():
    pubsub = r.pubsub()
    pubsub.subscribe("orders")

    for message in pubsub.listen():
        if message["type"] != "message":
            continue
        event = json.loads(message["data"])
        if event["event"] == "order.created":
            charge_customer(event["order_id"], event["total"])


# CONSUMER: Email Service (independently subscribes)
def send_order_emails():
    pubsub = r.pubsub()
    pubsub.subscribe("orders")

    for message in pubsub.listen():
        if message["type"] != "message":
            continue
        event = json.loads(message["data"])
        if event["event"] == "order.created":
            send_confirmation_email(event["customer_id"], event["order_id"])
```

## When to Use HTTP vs Queue

```
Use DIRECT HTTP when:
├── User needs the response NOW (synchronous)
│   Example: "Is this username available?" → must reply immediately
├── Only 2-3 services, all reliable
│   Example: Internal auth check before processing
└── Request-response pattern (ask question, get answer)
    Example: GET /api/users/123 → return user data

Use a MESSAGE QUEUE when:
├── User doesn't need to wait for all processing
│   Example: "Order placed" → process payment/shipping/email in background
├── Multiple services need the same event
│   Example: Order created → notify payment, shipping, analytics, email
├── Services process at different speeds
│   Example: Order ingestion is fast, fulfillment is slow
└── You need to survive service outages
    Example: Email service down shouldn't block order creation
```

## Redis Pub/Sub vs RabbitMQ vs Kafka

| Feature | Redis Pub/Sub | RabbitMQ | Kafka |
|---------|--------------|----------|-------|
| If consumer is offline | **Message lost** | Message queued | Message stored |
| Message ordering | No guarantee | Per-queue | Per-partition |
| Throughput | Very high | High | Very high |
| Durability | No | Yes | Yes |
| Complexity | Low | Medium | High |
| Use when | Real-time, loss OK | Task queues, reliability | Event streaming, replay |

**Start with Redis** if you just need async processing and can tolerate occasional message loss. **Upgrade to RabbitMQ** when you need guaranteed delivery. **Use Kafka** when you need to replay events or handle massive throughput.

The fundamental insight: a message queue is a BUFFER between producer and consumer that decouples them in time, space, and speed.'''
    ),
    (
        "thinking/firstprinciples-container-from-scratch",
        "What actually IS a Docker container? Not 'a lightweight VM' — what's really happening at the OS level? I want to understand the fundamentals.",
        r'''<think>
Let me derive containers from first principles at the OS level.

**Start with the problem:**
You want to run an application in isolation — it shouldn't see or affect other applications on the same machine. Traditionally, you'd use a virtual machine (full OS per application). But VMs are heavy — each one boots an entire kernel, has its own memory management, etc.

**Key insight:** You don't need a separate kernel for isolation. The Linux kernel already has mechanisms to isolate processes from each other. A container is just a process with extra isolation applied.

**What makes a container a container?**
Three Linux kernel features:
1. **Namespaces** — what the process can SEE
2. **cgroups** — what the process can USE
3. **Union filesystem** — what the process's filesystem looks like

Let me derive each from first principles.

**Namespaces (isolation of visibility):**
A normal process can see all other processes, all network interfaces, all users, the full filesystem. Namespaces limit what a process can see:
- PID namespace: process thinks it's PID 1 (init), can't see other containers' processes
- Network namespace: process has its own network stack (own IP, ports, routing)
- Mount namespace: process has its own filesystem mount points
- UTS namespace: process has its own hostname
- User namespace: process has its own user IDs (root inside container ≠ root on host)
- IPC namespace: process has its own inter-process communication

**cgroups (isolation of resources):**
Even with namespaces, a process could still use 100% CPU or all available memory. cgroups limit resource consumption:
- CPU: process can use max N% of CPU
- Memory: process can use max N MB (OOM-killed if exceeded)
- I/O: process can read/write at max N MB/s
- PIDs: process can create max N child processes

**Union filesystem (layered images):**
The container's filesystem is built from layers:
- Base layer: Ubuntu filesystem (read-only)
- Layer 2: Python installed (read-only)
- Layer 3: Your application code (read-only)
- Writable layer: runtime changes (temporary)

Layers are shared between containers. 10 containers using Python don't need 10 copies of Python.

**So what IS a container?**
A container is: A Linux process that has its own namespaces (can't see the host), resource limits via cgroups (can't consume the host), and a layered filesystem (has its own root filesystem).

It's NOT a VM. There's no separate kernel. The container shares the host's kernel.
</think>

A container is **a regular Linux process with extra kernel isolation applied**. No separate kernel, no virtualization. Just three Linux features working together.

## Building a "Container" From Scratch

You can create a container-like environment with basic Linux commands:

```bash
# Step 1: Create an isolated process with its own namespaces
# unshare creates new namespaces for a process

sudo unshare \
  --pid       # Own process ID space (process thinks it's PID 1)  \
  --net       # Own network stack (own IP, ports)                  \
  --mount     # Own filesystem mounts                              \
  --uts       # Own hostname                                       \
  --fork      # Fork into the new PID namespace                    \
  /bin/bash

# Inside this shell:
hostname "my-container"   # Only affects this namespace
ps aux                    # Only sees processes in this namespace
# This IS essentially what Docker does (with more setup)
```

## The Three Pillars

### Pillar 1: Namespaces (What the Process Can SEE)

```
NORMAL process:
  Can see ALL processes on the machine: ps aux → shows 200 processes
  Can see ALL network interfaces: ip addr → shows eth0, docker0, etc.
  Has the host's hostname
  Shares /tmp, /var, etc. with everyone

CONTAINERIZED process (namespaces applied):
  PID namespace:     ps aux → shows ONLY its own processes (PID 1 = itself)
  Network namespace: ip addr → shows only its virtual eth0
  UTS namespace:     hostname → "my-container" (not the host's name)
  Mount namespace:   sees its OWN filesystem, not the host's
  User namespace:    thinks it's root, but actually mapped to unprivileged user

# The process literally CANNOT SEE the host or other containers.
# It's not hidden — it's invisible at the kernel level.
```

### Pillar 2: cgroups (What the Process Can USE)

```bash
# Without cgroups: container could use 100% CPU and all RAM
# With cgroups: hard limits on resource consumption

# This is what Docker's --memory and --cpus flags do:
# docker run --memory=512m --cpus=1.5 myapp

# Under the hood, Docker writes to /sys/fs/cgroup:
echo "536870912" > /sys/fs/cgroup/memory/my-container/memory.limit_in_bytes
echo "150000" > /sys/fs/cgroup/cpu/my-container/cpu.cfs_quota_us

# If the container exceeds memory limit → OOM killed
# If the container exceeds CPU limit → throttled (not killed)
```

### Pillar 3: Union Filesystem (Layered Images)

```
Docker image = stack of read-only layers

Layer 1 (base):     Ubuntu 22.04 filesystem (~70MB)
Layer 2 (runtime):  Python 3.11 installed (~50MB)
Layer 3 (deps):     pip install -r requirements.txt (~30MB)
Layer 4 (app):      COPY . /app (~5MB)

Container = image layers + one writable layer on top

┌─────────────────────────┐
│ Writable layer (runtime) │  ← Container writes go here (temporary)
├─────────────────────────┤
│ Layer 4: Your app code   │  ← Read-only (shared across containers)
├─────────────────────────┤
│ Layer 3: Python packages │  ← Read-only (shared)
├─────────────────────────┤
│ Layer 2: Python 3.11     │  ← Read-only (shared)
├─────────────────────────┤
│ Layer 1: Ubuntu 22.04    │  ← Read-only (shared)
└─────────────────────────┘

10 containers using the same Python image share layers 1-2.
They don't each have a copy. This is why containers are small.
```

## Container vs VM: What's Actually Different

```
VIRTUAL MACHINE:
┌─────────────────┐  ┌─────────────────┐
│ App A            │  │ App B            │
│ Libraries        │  │ Libraries        │
│ Guest OS Kernel  │  │ Guest OS Kernel  │  ← Each VM has its OWN kernel
├─────────────────┤  ├─────────────────┤
│    Hypervisor (VMware, KVM, Hyper-V)   │  ← Hardware virtualization
├────────────────────────────────────────┤
│           Host OS Kernel               │
│           Hardware                     │
└────────────────────────────────────────┘
  Boot time: 30-60 seconds
  Memory overhead: 500MB-2GB per VM
  Size: 1-10 GB per VM

CONTAINER:
┌──────────┐  ┌──────────┐
│ App A     │  │ App B     │
│ Libraries │  │ Libraries │
├──────────┤  ├──────────┤
│ namespaces + cgroups    │  ← Kernel-level isolation (no separate kernel)
├─────────────────────────┤
│    Host OS Kernel        │  ← SHARED kernel
│    Hardware              │
└─────────────────────────┘
  Boot time: <1 second (it's just starting a process)
  Memory overhead: ~10MB
  Size: 50-500 MB (shared layers)
```

## The Bottom Line

```
Docker container = process + namespaces + cgroups + union filesystem

That's it. No magic. No VMs. No separate kernels.

When someone says "a container is a lightweight VM" — it's wrong.
A container is a PROCESS that can't see the rest of the system
and has hard limits on resource usage. The kernel does all the work.
```

This is why containers start in milliseconds (just `fork()` a process), use almost no extra memory (no guest kernel), and share disk space (layered filesystem). The Linux kernel already knew how to isolate processes — Docker just made it usable.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
