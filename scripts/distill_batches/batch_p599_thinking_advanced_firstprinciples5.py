"""Phase 2H: Advanced Reasoning — First Principles Derivation (Part 5/8)"""

PAIRS = [
    (
        "thinking/firstprinciples-load-balancer-derive",
        "How does a load balancer actually work? I know it distributes traffic, but what are the fundamental mechanics? Can you derive it from scratch?",
        r'''<think>
Let me derive load balancing from first principles.

**The fundamental problem:**
You have one server. It can handle 100 requests/second. You need to handle 500 requests/second. What do you do?

Option 1: Buy a bigger server (vertical scaling). But there's a limit to how big one server can be. And it's a single point of failure.

Option 2: Buy 5 servers and split the traffic between them. But how does traffic get split?

**First attempt: DNS-based distribution**
Give each server a different IP. Put all IPs in DNS. Each client gets a random IP.
```
DNS: example.com → 10.0.0.1, 10.0.0.2, 10.0.0.3, 10.0.0.4, 10.0.0.5
```
Problem: clients cache DNS. If one server dies, clients keep going to the dead IP. No health checking. No fair distribution (DNS round-robin is coarse).

**Second attempt: single entry point that forwards**
One server that receives ALL traffic and forwards it to backend servers:
```
Client → Load Balancer (10.0.0.1) → Server A (10.0.1.1)
                                   → Server B (10.0.1.2)
                                   → Server C (10.0.1.3)
```
This is a load balancer. It needs to decide:
1. WHICH server to send each request to (routing algorithm)
2. WHETHER a server is healthy (health checking)
3. HOW to forward the request (layer 4 vs layer 7)

**Routing algorithms — derived from needs:**

Round-robin: next request goes to the next server in rotation.
- Simple, fair if all requests are equal.
- Problem: what if Server A is handling a slow request and Server B is idle?

Least-connections: send to the server with the fewest active connections.
- Better distribution under uneven load.
- Requires tracking connection count per server.

Weighted: assign weights based on server capacity.
- Server A (8 cores): weight 4
- Server B (2 cores): weight 1
- A gets 4x more traffic than B

IP hash: hash the client's IP, map to a server.
- Same client always goes to same server (session affinity)
- Problem: uneven distribution if hash distribution is poor

**Health checking:**
The load balancer must detect dead/slow servers and stop sending traffic:
- Active: periodically send a probe (HTTP GET /health, TCP connect)
- Passive: track error rates per server, remove if too many failures

**Layer 4 vs Layer 7:**
- Layer 4 (TCP): forwards TCP connections. Fast, can't inspect content. Can't route by URL.
- Layer 7 (HTTP): inspects HTTP requests. Can route by URL path, headers, cookies. Can add/modify headers. More flexible, slightly more overhead.

So a load balancer is fundamentally: a reverse proxy + routing algorithm + health checking.
</think>

A load balancer is derived from three primitives: **a reverse proxy, a routing algorithm, and health checking**. Let me build it up from scratch.

## The Problem

```
1 server handles 100 req/s. You need 500 req/s. Buy 5 servers.
But clients know ONE address. How do they reach 5 servers?

Answer: Put a traffic director (load balancer) in front.

  Client → Load Balancer → Server 1 (100 req/s)
                          → Server 2 (100 req/s)
                          → Server 3 (100 req/s)
                          → Server 4 (100 req/s)
                          → Server 5 (100 req/s)

  Combined: 500 req/s through ONE address
```

## Component 1: Reverse Proxy (The Forwarder)

```python
# A reverse proxy receives a request and forwards it to a backend server
# This is the simplest possible "load balancer" — 1 backend

import httpx
from fastapi import FastAPI, Request, Response

app = FastAPI()
BACKEND = "http://10.0.1.1:8000"

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    async with httpx.AsyncClient() as client:
        # Forward the request to the backend
        response = await client.request(
            method=request.method,
            url=f"{BACKEND}/{path}",
            headers=dict(request.headers),
            content=await request.body(),
        )
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
        )
```

## Component 2: Routing Algorithm (Which Server?)

```python
# Now add multiple backends and a way to choose between them
import itertools
import random
from collections import defaultdict

class RoundRobin:
    """Send to each server in turn: A, B, C, A, B, C, ..."""
    def __init__(self, servers):
        self._cycle = itertools.cycle(servers)

    def next(self) -> str:
        return next(self._cycle)

class LeastConnections:
    """Send to the server with the fewest active requests."""
    def __init__(self, servers):
        self.servers = servers
        self.active = defaultdict(int)

    def next(self) -> str:
        return min(self.servers, key=lambda s: self.active[s])

    def connect(self, server):
        self.active[server] += 1

    def disconnect(self, server):
        self.active[server] -= 1

class IPHash:
    """Same client IP always goes to the same server (sticky sessions)."""
    def __init__(self, servers):
        self.servers = servers

    def next(self, client_ip: str) -> str:
        index = hash(client_ip) % len(self.servers)
        return self.servers[index]

class WeightedRoundRobin:
    """Servers with more capacity get more traffic."""
    def __init__(self, server_weights: dict):
        # {"server-a": 4, "server-b": 1} → A gets 4x more traffic
        self._pool = []
        for server, weight in server_weights.items():
            self._pool.extend([server] * weight)
        self._cycle = itertools.cycle(self._pool)

    def next(self) -> str:
        return next(self._cycle)
```

## Component 3: Health Checking (Is the Server Alive?)

```python
import asyncio
import time

class HealthChecker:
    """Periodically check if backends are alive."""

    def __init__(self, servers, check_interval=10, unhealthy_threshold=3):
        self.servers = servers
        self.interval = check_interval
        self.threshold = unhealthy_threshold
        self.healthy = set(servers)
        self._fail_counts = defaultdict(int)

    async def check_loop(self):
        """Run continuously, checking each server periodically."""
        while True:
            for server in self.servers:
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            f"{server}/health",
                            timeout=5.0
                        )
                        if resp.status_code == 200:
                            self._fail_counts[server] = 0
                            self.healthy.add(server)
                        else:
                            self._mark_failed(server)
                except Exception:
                    self._mark_failed(server)

            await asyncio.sleep(self.interval)

    def _mark_failed(self, server):
        self._fail_counts[server] += 1
        if self._fail_counts[server] >= self.threshold:
            self.healthy.discard(server)

    def get_healthy_servers(self) -> list[str]:
        return list(self.healthy)
```

## Putting It Together: A Complete Load Balancer

```python
SERVERS = [
    "http://10.0.1.1:8000",
    "http://10.0.1.2:8000",
    "http://10.0.1.3:8000",
]

router = LeastConnections(SERVERS)
health = HealthChecker(SERVERS)

@app.on_event("startup")
async def start_health_checks():
    asyncio.create_task(health.check_loop())

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def load_balance(path: str, request: Request):
    healthy = health.get_healthy_servers()
    if not healthy:
        return Response(status_code=503, content="No healthy backends")

    # Choose a backend
    server = router.next()
    while server not in healthy:
        server = router.next()

    # Forward the request
    router.connect(server)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=request.method,
                url=f"{server}/{path}",
                headers={
                    **dict(request.headers),
                    "X-Forwarded-For": request.client.host,
                    "X-Real-IP": request.client.host,
                },
                content=await request.body(),
                timeout=30.0,
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
            )
    finally:
        router.disconnect(server)
```

## The Real-World Equivalent

In production, you use nginx or HAProxy instead of building your own:

```nginx
# nginx.conf — does everything above in ~10 lines
upstream backend {
    least_conn;                    # Routing algorithm
    server 10.0.1.1:8000;         # Backend 1
    server 10.0.1.2:8000;         # Backend 2
    server 10.0.1.3:8000;         # Backend 3
}

server {
    listen 80;
    location / {
        proxy_pass http://backend;  # Forward to pool
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

A load balancer is three things composed: a forwarder (reverse proxy) + a chooser (routing algorithm) + a monitor (health checker). Everything else is refinement of these three primitives.'''
    ),
    (
        "thinking/firstprinciples-hashing-passwords",
        "Why can't I just store passwords in the database? What's the actual threat model? Walk me through why we hash passwords from first principles.",
        r'''<think>
Password storage — let me derive the requirements from the threat model.

**Start with the simplest approach: store passwords in plaintext**
```
users table:
  id | email          | password
  1  | alice@co.com   | alice123
  2  | bob@co.com     | hunter2
```

**Threat: database breach**
If an attacker gets access to the database (SQL injection, stolen backup, insider threat), they have EVERY user's password. Most people reuse passwords, so the attacker can now log into their email, bank, etc.

Probability of a breach: high enough that it has happened to LinkedIn, Adobe, Yahoo, Equifax, etc.

**First attempt: encrypt passwords**
Encrypt with a key: `AES(password, secret_key) → ciphertext`
If the attacker gets the database, they can't read passwords without the key.

Problem: where do you store the key? If it's on the same server (or in the code), the attacker who got the database probably also got the key. Encryption is REVERSIBLE — if the key is compromised, ALL passwords are compromised at once.

**Key insight: you don't NEED to reverse passwords**
The server never needs to know the original password. It only needs to verify "does this input match what the user registered with?"

This means we need a ONE-WAY function: easy to compute, impossible to reverse.

**Second attempt: hash passwords**
`hash(password) → fixed-length digest`
SHA-256("alice123") → "a6bf6..."

Store the hash. When user logs in, hash their input and compare.
If the database is stolen, attacker has hashes, not passwords.

Problem: hashing is deterministic. Every user with "alice123" has the same hash. An attacker can:
1. Pre-compute hashes for millions of common passwords (rainbow table)
2. Compare against the stolen database
3. Crack passwords instantly

**Third attempt: salted hashing**
Add a unique random value (salt) per user:
`hash(salt + password) → digest`

```
  id | email        | salt      | password_hash
  1  | alice@co.com | x9f3k2... | hash("x9f3k2..." + "alice123")
  2  | bob@co.com   | j7m4n8... | hash("j7m4n8..." + "alice123")
```

Same password, different salts → different hashes. Rainbow tables don't work because the attacker would need a separate table per salt.

Problem: SHA-256 is FAST. A GPU can compute 10 billion SHA-256 hashes per second. An attacker can brute-force common passwords even with salts.

**Fourth attempt: slow hashing**
Use an intentionally SLOW hash function. If each hash takes 0.1 seconds instead of 0.0000000001 seconds, brute-forcing becomes impractical:
- SHA-256: 10 billion guesses/second → crack "alice123" in milliseconds
- bcrypt: 10 guesses/second → crack "alice123" takes years for complex passwords

This is what bcrypt, scrypt, and Argon2 do. They're designed to be SLOW and memory-hard (can't be parallelized efficiently on GPUs).
</think>

Let me build up the reasoning from the simplest approach to the correct one, showing why each step is necessary.

## Step 1: Why Not Plaintext?

```
Threat: Someone gets your database.
How: SQL injection, stolen backup, insider, misconfigured S3 bucket.
Frequency: Happens to major companies every year.

If passwords are plaintext:
  Attacker has EVERY user's password instantly.
  Most users reuse passwords → their email, bank, everything is compromised.
  You're on the news. Your company faces lawsuits.
```

## Step 2: Why Not Encryption?

```python
# Attempt: encrypt passwords
from cryptography.fernet import Fernet
key = Fernet.generate_key()  # Where do you store THIS?
cipher = Fernet(key)

encrypted = cipher.encrypt(b"alice123")  # Reversible!

# Problem: if attacker gets the database, they probably also get the key.
# Key is in: environment variables, config files, the same server.
# One key compromise → ALL passwords decrypted at once.

# Fundamental issue: encryption is REVERSIBLE.
# You don't need to reverse passwords — you only need to VERIFY them.
```

## Step 3: Why Not Simple Hashing?

```python
import hashlib

# One-way function: can't reverse hash → password
password_hash = hashlib.sha256("alice123".encode()).hexdigest()
# "ef92b778bafe771e89245b89ecbc0..."

# Verify: hash the input, compare to stored hash
def verify(input_password, stored_hash):
    return hashlib.sha256(input_password.encode()).hexdigest() == stored_hash
```

```
Problem: SHA-256 is deterministic.
Every user with "alice123" has the SAME hash.

Attacker pre-computes hashes for 10 million common passwords:
  "password"  → "5e884898da280..."
  "123456"    → "8d969eef6eca..."
  "alice123"  → "ef92b778bafe..."
  ... 10 million more

Then compares against your database. Instant lookup.
This is a "rainbow table" attack.
```

## Step 4: Why Not Salted SHA-256?

```python
import hashlib
import os

# Add a unique random salt per user
salt = os.urandom(16)  # 16 random bytes
password_hash = hashlib.sha256(salt + b"alice123").hexdigest()

# Store both salt and hash
# Salt: a8f3e2... | Hash: 7b2c9d...

# Same password + different salt = different hash
# Rainbow tables don't work (would need one per salt)
```

```
Problem: SHA-256 is FAST. Really fast.

GPU brute-force speed:
  SHA-256: ~10,000,000,000 (10 billion) hashes/second on a single GPU

  An 8-character password has ~200 billion combinations.
  Time to crack: 200B / 10B = 20 seconds.

  Even with salts, the attacker just brute-forces each user individually.
  10 billion guesses per second per user.
```

## Step 5: The Correct Approach — Slow Hashing

```python
import bcrypt

# bcrypt is intentionally SLOW (adjustable via cost factor)
password = b"alice123"
salt = bcrypt.gensalt(rounds=12)  # 2^12 = 4,096 iterations
hashed = bcrypt.hashpw(password, salt)

# Verify
def verify(input_password: bytes, stored_hash: bytes) -> bool:
    return bcrypt.checkpw(input_password, stored_hash)

# Speed comparison:
# SHA-256: 10,000,000,000 hashes/second (GPU)
# bcrypt (rounds=12): ~10 hashes/second (GPU)
#
# Time to crack 8-char password:
# SHA-256: 20 seconds
# bcrypt: 634 YEARS
```

## Why bcrypt/Argon2 Are Designed to Be Slow

```
Normal hashing goal: be as FAST as possible
  → Great for file checksums, data integrity

Password hashing goal: be as SLOW as possible (for attackers)
  → Each verification still takes <1s (fine for login)
  → But brute-force becomes computationally infeasible

bcrypt features:
  1. Built-in salt (no separate salt management)
  2. Adjustable cost (rounds parameter — increase over time as GPUs get faster)
  3. Memory-hard (hard to parallelize on GPUs)

Argon2 (newer, recommended for new projects):
  1. Winner of the Password Hashing Competition (2015)
  2. Configurable memory usage (harder to crack with specialized hardware)
  3. Configurable parallelism and time cost
```

## The Complete Implementation

```python
# For new projects, use Argon2. For existing projects, bcrypt is fine.
from argon2 import PasswordHasher

ph = PasswordHasher(
    time_cost=2,        # Number of iterations
    memory_cost=65536,   # 64 MB of memory per hash
    parallelism=1,       # Number of threads
)

def register(email: str, password: str):
    # Hash generates a unique salt automatically
    password_hash = ph.hash(password)
    # Stored: "$argon2id$v=19$m=65536,t=2,p=1$salt$hash"
    db.create_user(email=email, password_hash=password_hash)

def login(email: str, password: str) -> bool:
    user = db.get_user_by_email(email)
    try:
        return ph.verify(user.password_hash, password)
    except argon2.exceptions.VerifyMismatchError:
        return False
```

## The Derivation Summary

```
Plaintext     → breach exposes all passwords           → NO
Encryption    → reversible, key compromise = game over  → NO
Fast hash     → rainbow tables crack in seconds         → NO
Salted fast   → brute force at 10B guesses/second       → NO
Slow hash     → brute force at 10 guesses/second        → YES ✓

Each step fixes the previous step's vulnerability.
The "correct" answer is derived by understanding the threat model.
```'''
    ),
    (
        "thinking/firstprinciples-pagination-cursor-derive",
        "Why is cursor-based pagination better than offset pagination? I keep hearing this but don't understand the fundamental reason.",
        r'''<think>
Let me derive WHY cursor pagination is better by starting with how offset pagination works at the database level.

**Offset pagination: how it works internally**
```sql
SELECT * FROM orders ORDER BY created_at DESC LIMIT 20 OFFSET 1000;
```

What the database does:
1. Find ALL rows matching the query
2. Sort them by created_at
3. Skip the first 1000 rows
4. Return 20 rows

The key problem: the database MUST process ALL 1000 rows it's skipping. It can't jump to row 1000 — it has to count from the beginning.

Page 1 (offset 0): process 20 rows
Page 50 (offset 1000): process 1020 rows (skip 1000, return 20)
Page 500 (offset 10000): process 10020 rows (skip 10000, return 20)

Each subsequent page is SLOWER because the database processes more rows. At page 10000 on a large table, this query can take seconds.

**Cursor pagination: how it works**
Instead of "skip N rows," you say "give me rows AFTER this specific point":
```sql
SELECT * FROM orders WHERE created_at < '2024-01-15T10:30:00Z'
ORDER BY created_at DESC LIMIT 20;
```

What the database does:
1. Use the INDEX to jump directly to '2024-01-15T10:30:00Z'
2. Read the next 20 rows
3. Done

The database doesn't process ANY skipped rows. It jumps directly to the right position using the index. Page 1 and page 10000 are equally fast.

**But there's a trade-off:**
Cursor pagination gives up random access. You can't jump to "page 47" — you can only go to "the next page after this cursor." This is fine for infinite scrolling but not for "jump to page" UI.

**Another problem with offset: data consistency**
If a row is inserted while you're paginating:
- Page 1: rows 1-20
- New row inserted at position 5
- Page 2 (offset 20): rows 21-40... but row 20 is now row 21 due to the insert
- You see row 20 TWICE (once on page 1, once on page 2) and miss the new row

Cursor pagination doesn't have this problem because it anchors to a specific row, not a position.
</think>

The fundamental reason is how databases process these queries internally. Let me derive it.

## How Offset Works (Inside the Database)

```sql
-- "Give me page 50 (20 items per page)"
SELECT * FROM orders ORDER BY created_at DESC LIMIT 20 OFFSET 980;
```

```
What the database ACTUALLY does:

Step 1: Scan the index to find rows in order
Step 2: Read row 1... skip ✗
Step 3: Read row 2... skip ✗
Step 4: Read row 3... skip ✗
        ...
Step 981: Read row 980... skip ✗  (980 rows processed for nothing)
Step 982: Read row 981... return ✓
Step 983: Read row 982... return ✓
        ...
Step 1001: Read row 1000... return ✓  (20 rows returned)

Total rows processed: 1000 (but only 20 returned)
```

```
Performance by page number:
  Page 1   (OFFSET 0):     20 rows processed    → 2ms
  Page 10  (OFFSET 180):   200 rows processed   → 5ms
  Page 100 (OFFSET 1980):  2,000 rows processed → 20ms
  Page 1000 (OFFSET 19980): 20,000 rows         → 200ms
  Page 10000:               200,000 rows         → 2,000ms+ 💥

Deep pages get progressively slower. This is O(offset + limit).
```

## How Cursor Works (Inside the Database)

```sql
-- "Give me 20 items after this timestamp"
SELECT * FROM orders
WHERE created_at < '2024-01-15T10:30:00Z'
ORDER BY created_at DESC
LIMIT 20;
```

```
What the database ACTUALLY does:

Step 1: Look up '2024-01-15T10:30:00Z' in the B-tree index
        (3-4 disk reads — instant, regardless of position)
Step 2: Read the next 20 rows from that position
Step 3: Done.

Total rows processed: 20 (always, regardless of "page number")
```

```
Performance by depth:
  First 20 items:      20 rows processed → 2ms
  Items 180-200:       20 rows processed → 2ms
  Items 19980-20000:   20 rows processed → 2ms
  Items 199980-200000: 20 rows processed → 2ms  ← same speed!

Every "page" is equally fast. This is O(limit) — constant time.
```

## The Second Problem: Data Consistency

```
OFFSET pagination with concurrent inserts:

Time 1: User loads page 1 (items 1-20)
Time 2: New item inserted at position 3
Time 3: User loads page 2 (items 21-40)

But wait — the insert shifted everything down:
  Old item 20 is now at position 21
  User sees item 20 TWICE (page 1 and page 2)
  User never sees the new item (it's on page 1, already loaded)

CURSOR pagination with concurrent inserts:

Time 1: User loads first 20 items, cursor = last item's timestamp
Time 2: New item inserted (doesn't matter where)
Time 3: User loads next 20 items AFTER the cursor timestamp

Result: no duplicates, no missed items.
The cursor is an absolute position, not a relative offset.
```

## Implementation Comparison

```python
# OFFSET: simple but slow for deep pages
@app.get("/api/orders")
def list_orders(page: int = 1, per_page: int = 20):
    offset = (page - 1) * per_page
    orders = db.execute(
        "SELECT * FROM orders ORDER BY created_at DESC LIMIT %s OFFSET %s",
        (per_page, offset)
    )
    total = db.execute("SELECT COUNT(*) FROM orders")  # Also slow on large tables!
    return {
        "data": orders,
        "page": page,
        "total_pages": total // per_page,
    }


# CURSOR: fast at any depth
import base64

@app.get("/api/orders")
def list_orders(cursor: str = None, limit: int = 20):
    if cursor:
        cursor_value = base64.b64decode(cursor).decode()
        orders = db.execute(
            "SELECT * FROM orders WHERE created_at < %s "
            "ORDER BY created_at DESC LIMIT %s",
            (cursor_value, limit + 1)  # +1 to check if there's a next page
        )
    else:
        orders = db.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT %s",
            (limit + 1,)
        )

    has_next = len(orders) > limit
    if has_next:
        orders = orders[:limit]

    next_cursor = None
    if has_next and orders:
        next_cursor = base64.b64encode(
            str(orders[-1].created_at).encode()
        ).decode()

    return {
        "data": orders,
        "next_cursor": next_cursor,
        "has_next": has_next,
    }
```

## When to Use Which

| Feature | Offset | Cursor |
|---------|--------|--------|
| "Jump to page 47" | ✅ Easy | ❌ Not possible |
| Infinite scroll | ❌ Slow at depth | ✅ Fast always |
| Large datasets (>100K rows) | ❌ Degrades | ✅ Constant speed |
| Data consistency during pagination | ❌ Duplicates/gaps | ✅ Consistent |
| Implementation complexity | Simple | Moderate |
| Total count ("page X of Y") | ✅ (but COUNT is slow) | ❌ Not available |

**Rule of thumb:** Use cursor pagination by default. Only use offset when you specifically need "jump to page N" (admin panels, small datasets).'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
