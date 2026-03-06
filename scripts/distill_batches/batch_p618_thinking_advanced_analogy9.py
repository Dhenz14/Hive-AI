"""Phase 2C: Advanced Reasoning — Analogical Reasoning (Part 9)"""

PAIRS = [
    (
        "thinking/analogy-api-versioning-to-language-evolution",
        "How should I handle API versioning? We keep breaking our clients when we make changes to our REST API.",
        r'''<think>
API versioning — the language evolution analogy works well here.

**Language evolution analogy:**
- API = a language spoken between systems
- Clients = speakers of that language
- Breaking changes = suddenly changing the meaning of words
- Versioning = how languages evolve without breaking communication

English doesn't version. It evolves:
- New words are ADDED ("selfie", "google" as a verb)
- Old words are rarely REMOVED (just fall out of use naturally)
- Grammar rarely changes drastically
- If Shakespeare read modern English, he'd mostly understand it

This maps to API evolution:
- ADD new fields → old clients ignore them (backwards compatible)
- DEPRECATE old fields → still work, but documentation says "use new field"
- REMOVE old fields → only after long deprecation period
- NEVER change the meaning of an existing field

**Where it maps:**
- Adding a word to a language = adding a field to an API ✓
- Deprecating a word = marking a field deprecated ✓
- Removing a word suddenly = breaking change ✓
- Slang evolving = informal API contracts that clients depend on ✓

**Where it breaks down:**
- Languages evolve organically; APIs are designed deliberately
- Languages don't have "versions" but APIs sometimes need them
- API consumers are machines that can't infer meaning from context
</think>

Think of your API as **a language your clients speak**. Breaking changes are like suddenly changing what words mean.

## The Analogy

```
API EVOLUTION ≈ LANGUAGE EVOLUTION

English doesn't "version." It evolves gracefully:
  ✓ New words are ADDED:    "selfie" (2013), "google" as verb
  ✓ Old words still work:   "telephone" still understood
  ✓ Meanings rarely change: "car" doesn't suddenly mean "boat"
  ✗ Sudden changes = chaos: imagine if "yes" suddenly meant "no"

Your API should work the same way:
  ✓ ADD new fields:         clients that don't know them just ignore them
  ✓ Old fields still work:  existing clients continue working
  ✓ Don't change semantics: status=1 shouldn't suddenly mean something new
  ✗ REMOVING a field:       like deleting a word from the dictionary mid-sentence
```

## Strategy 1: Additive-Only Evolution (Recommended)

```python
# VERSION 1: original response
GET /api/users/42
{
    "id": 42,
    "name": "Alice Smith"
}

# VERSION 1.1: ADD fields (non-breaking)
GET /api/users/42
{
    "id": 42,
    "name": "Alice Smith",           # Still here — old clients still work
    "first_name": "Alice",           # NEW — old clients ignore this
    "last_name": "Smith",            # NEW — old clients ignore this
    "email": "alice@example.com"     # NEW — old clients ignore this
}

# VERSION 1.2: DEPRECATE (non-breaking)
GET /api/users/42
{
    "id": 42,
    "name": "Alice Smith",           # Deprecated (docs say: use first_name/last_name)
    "first_name": "Alice",           # Preferred
    "last_name": "Smith",            # Preferred
    "email": "alice@example.com"
}
# "name" still works — old clients are fine
# New clients use first_name/last_name

# VERSION 1.3: REMOVE after deprecation period (breaking — but planned)
# Only after monitoring shows < 1% of requests use "name" field
```

## Strategy 2: URL Versioning (When Breaking Changes Are Necessary)

```
When additive evolution isn't enough
(e.g., changing authentication, restructuring resources):

  /api/v1/users/42     ← old clients use this
  /api/v2/users/42     ← new clients use this

Both run simultaneously until v1 is sunset.
Like translating a book — both editions exist side by side.
```

```python
# Practical implementation:
from fastapi import APIRouter

v1 = APIRouter(prefix="/api/v1")
v2 = APIRouter(prefix="/api/v2")

@v1.get("/users/{user_id}")
def get_user_v1(user_id: int):
    user = db.get_user(user_id)
    return {
        "id": user.id,
        "name": f"{user.first_name} {user.last_name}",  # Old format
    }

@v2.get("/users/{user_id}")
def get_user_v2(user_id: int):
    user = db.get_user(user_id)
    return {
        "id": user.id,
        "first_name": user.first_name,    # New format
        "last_name": user.last_name,
        "email": user.email,
    }

app.include_router(v1)
app.include_router(v2)
```

## The Rules of API Evolution

```
SAFE CHANGES (like adding new words to a language):
  ✓ Add new fields to responses
  ✓ Add new optional parameters to requests
  ✓ Add new endpoints
  ✓ Add new enum values (if clients handle unknown values)
  ✓ Widen input validation (accept more formats)

BREAKING CHANGES (like changing word meanings):
  ✗ Remove fields from responses
  ✗ Rename fields
  ✗ Change field types (string → number)
  ✗ Change the meaning of a value
  ✗ Make optional parameters required
  ✗ Narrow input validation (reject previously accepted input)
  ✗ Change HTTP methods or status codes

WHEN YOU MUST BREAK:
  1. Announce deprecation (sunset header, docs, changelog)
  2. Give clients time to migrate (3-12 months)
  3. Monitor usage of deprecated fields
  4. Remove only when usage is negligible
```

## Deprecation Headers (Communicating Change)

```python
# Tell clients about upcoming changes in HTTP headers:

@app.get("/api/v1/users/{user_id}")
def get_user_v1(user_id: int):
    user = db.get_user(user_id)
    response = JSONResponse({"id": user.id, "name": user.full_name})

    # Standard deprecation headers
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Sat, 01 Jun 2026 00:00:00 GMT"
    response.headers["Link"] = '</api/v2/users>; rel="successor-version"'

    return response

# Clients that check these headers can auto-alert before the deadline.
# Like a "this word will be removed from the dictionary on June 1" notice.
```'''
    ),
    (
        "thinking/analogy-load-balancer-to-restaurant-host",
        "Can you explain how load balancers work? I understand the basic idea of distributing traffic but I don't get the different algorithms or when to use which.",
        r'''<think>
Load balancers — the restaurant host/hostess analogy is perfect.

**Restaurant host analogy:**
A busy restaurant with 5 servers (waiters). The host at the front door decides which server handles each party (request).

**Load balancing algorithms as seating strategies:**

1. Round Robin = "take turns"
   Host seats parties at server 1, 2, 3, 4, 5, 1, 2, 3...
   Simple. Fair. But ignores that server 3 has a huge party (slow request).

2. Least Connections = "give it to the least busy"
   Host looks at each server's current table count. Seats the next party at the server with fewest tables.
   Better than round robin because it accounts for load.

3. Weighted Round Robin = "some servers can handle more"
   Server 1 is experienced (powerful server): gets 3 tables per rotation
   Server 5 is new (weaker server): gets 1 table per rotation
   Accounts for heterogeneous capacity.

4. IP Hash = "regulars go to same server"
   "Oh, the Smiths? They always sit in Sarah's section."
   Same client always goes to same server (session affinity).

5. Least Response Time = "whoever is fastest"
   Host tracks how quickly each server takes orders. Sends to the fastest one.

**Health checks:**
Host periodically checks: "Is server 3 still working?" If server 3 called in sick, stop seating there.

**Where analogy maps well:**
- Multiple servers handling requests ✓
- Different algorithms for different needs ✓
- Health checks ✓
- Session affinity ("sticky sessions") ✓

**Where it breaks down:**
- Restaurants have physical proximity; load balancers route over networks
- SSL termination doesn't have a restaurant equivalent
- L4 vs L7 load balancing distinction is hard to map
</think>

Think of a load balancer as the **host/hostess at a busy restaurant** with multiple servers (waiters).

## The Core Analogy

```
RESTAURANT                          LOAD BALANCER
──────────────────────────────────────────────────
Host at the door                    Load balancer
Waiters (servers)                   Backend servers
Incoming parties (customers)        Incoming requests
Seating a party at a table          Routing a request to a server
Waiter calling in sick              Server health check failing
"Your usual table?"                 Sticky sessions / session affinity
```

## Load Balancing Algorithms (Seating Strategies)

### Round Robin: "Take turns"

```
Party 1 → Server A
Party 2 → Server B
Party 3 → Server C
Party 4 → Server A   ← back to start
Party 5 → Server B

Simple, fair, predictable.

GOOD WHEN: all servers are identical, all requests are similar size.
BAD WHEN: some requests take much longer (one waiter stuck with
          a 20-person party while others serve 2-person tables).
```

### Least Connections: "Give it to whoever is least busy"

```
Current state:
  Server A: 5 active requests
  Server B: 2 active requests    ← least busy
  Server C: 8 active requests

Next request → Server B (has fewest connections)

GOOD WHEN: request duration varies widely (some fast, some slow).
          Naturally balances uneven workloads.
BAD WHEN: servers have different capacities
          (weaker server gets same share as powerful one).
```

### Weighted Round Robin: "Some servers can handle more"

```
Server A (8 CPU):  weight 4    → gets 4 requests per cycle
Server B (4 CPU):  weight 2    → gets 2 requests per cycle
Server C (2 CPU):  weight 1    → gets 1 request per cycle

Cycle: A, A, A, A, B, B, C, A, A, A, A, B, B, C...

Like an experienced waiter handling 8 tables vs a new hire handling 2.

GOOD WHEN: servers have different hardware specs.
```

### IP Hash: "Regulars go to the same server"

```
Client 192.168.1.1 → hash → Server A (always)
Client 192.168.1.2 → hash → Server C (always)
Client 192.168.1.3 → hash → Server A (always)

Like "The Smiths always sit in Sarah's section."

GOOD WHEN: you need session affinity without sticky cookies.
          User always hits the same server → local cache/session works.
BAD WHEN: one client sends way more traffic than others
          (one server gets overloaded).
```

### Least Response Time: "Whoever is fastest right now"

```
Server A: avg response time 45ms     ← fastest
Server B: avg response time 120ms
Server C: avg response time 80ms

Next request → Server A

Like seating parties with the waiter who's been serving fastest tonight.

GOOD WHEN: you want to optimize for user experience.
           Naturally routes away from struggling servers.
```

## Health Checks: "Is the waiter still working?"

```
RESTAURANT:
  Manager checks every 5 minutes: "Server C, are you OK?"
  Server C: (no response — went home sick)
  Manager: "Stop seating parties with Server C!"

LOAD BALANCER:
  Every 10 seconds, send: GET /health → each server
  Server A: 200 OK    ✓ healthy
  Server B: 200 OK    ✓ healthy
  Server C: timeout   ✗ remove from rotation!

  Server C comes back:
  3 consecutive 200 OK responses → add back to rotation

# Health check endpoint:
@app.get("/health")
def health_check():
    db_ok = check_database()
    cache_ok = check_redis()
    if db_ok and cache_ok:
        return {"status": "healthy"}, 200
    return {"status": "unhealthy"}, 503
```

## When to Use Which Algorithm

```
ALGORITHM          USE CASE                         EXAMPLE
──────────────────────────────────────────────────────────────
Round Robin        Simple, identical servers         Stateless API servers
                                                    behind Nginx

Least Connections  Varying request duration          WebSocket servers,
                                                    file upload servers

Weighted RR        Heterogeneous hardware            Mixed instance types
                                                    (c5.xlarge + c5.2xlarge)

IP Hash            Need session affinity             Legacy apps that
                   without cookies                   store session in memory

Least Response     Optimize for user experience      Global services with
Time                                                servers in multiple regions

Most common for web apps: LEAST CONNECTIONS.
It handles varying request duration naturally and
doesn't require knowing server capacity in advance.
```

## Practical Setup (Nginx)

```nginx
# Round Robin (default)
upstream api {
    server 10.0.0.1:8080;
    server 10.0.0.2:8080;
    server 10.0.0.3:8080;
}

# Least Connections
upstream api {
    least_conn;
    server 10.0.0.1:8080;
    server 10.0.0.2:8080;
    server 10.0.0.3:8080;
}

# Weighted
upstream api {
    server 10.0.0.1:8080 weight=4;    # Powerful server
    server 10.0.0.2:8080 weight=2;    # Medium server
    server 10.0.0.3:8080 weight=1;    # Small server
}

# IP Hash (sticky)
upstream api {
    ip_hash;
    server 10.0.0.1:8080;
    server 10.0.0.2:8080;
    server 10.0.0.3:8080;
}

server {
    location /api/ {
        proxy_pass http://api;
    }
}
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
