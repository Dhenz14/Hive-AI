"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 16)"""

PAIRS = [
    (
        "thinking/backtrack-inheritance-to-composition",
        "I have a deep class hierarchy: Animal → Pet → Dog → ServiceDog → GuideServiceDog. Every time I add a new type of animal it breaks things. How do I fix this?",
        r'''<think>
Deep inheritance hierarchy problem. Classic case where inheritance was chosen but composition would be better.

**Initial instinct: refactor the hierarchy**
Maybe I could reorganize the levels? But that doesn't fix the fundamental problem — inheritance creates rigid coupling. Every subclass is tightly bound to its parent's implementation.

**The real issue:**
- Animal → Pet: not all animals are pets
- Pet → Dog: fine, but then Cat needs a parallel hierarchy
- Dog → ServiceDog: "service" is a ROLE, not a type
- ServiceDog → GuideServiceDog: "guide" is a SPECIALIZATION of a role

The problem: they're encoding ROLES and CAPABILITIES as types. A guide dog isn't a different TYPE of dog — it's a dog WITH certain capabilities.

**Backtrack: composition over inheritance**
Instead of IS-A relationships, use HAS-A:
- A Dog HAS behaviors (can fetch, can bark)
- A Dog HAS roles (service animal, therapy animal)
- A Dog HAS capabilities (guide, alert, mobility assist)

This is the classic "favor composition over inheritance" principle.

**Implementation approach:**
- Entity + Component pattern
- Or: base class + mixins/interfaces
- Or: strategy pattern for behaviors
</think>

Your hierarchy encodes **roles as types**, which is the root problem. A guide service dog isn't a different *type* — it's a dog *with certain capabilities*.

## The Problem With Deep Inheritance

```
Animal → Pet → Dog → ServiceDog → GuideServiceDog
                   → TherapyDog                    ← where does this go?
                   → PoliceDog                     ← and this?
             → Cat → ... another parallel hierarchy?
       → WildAnimal → Wolf → ... ?

What about a therapy dog that's ALSO a service dog? Multiple inheritance? Diamond problem?
```

## Backtrack: Composition Over Inheritance

```python
# ❌ BEFORE: deep hierarchy, rigid, breaks when requirements change
class Animal:
    def eat(self): ...
class Pet(Animal):
    def __init__(self, owner): ...
class Dog(Pet):
    def bark(self): ...
class ServiceDog(Dog):
    def __init__(self, owner, handler): ...
class GuideServiceDog(ServiceDog):
    def guide(self): ...

# ✅ AFTER: flat hierarchy + composition
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol

# Capabilities as composable behaviors
class Capability(Protocol):
    def describe(self) -> str: ...

class GuidingCapability:
    def describe(self) -> str:
        return "Can guide visually impaired handler"
    def guide(self, destination: str) -> str:
        return f"Guiding handler to {destination}"

class TherapyCapability:
    def describe(self) -> str:
        return "Provides emotional support therapy"
    def comfort(self) -> str:
        return "Providing comfort and emotional support"

class AlertCapability:
    def __init__(self, alert_type: str):
        self.alert_type = alert_type
    def describe(self) -> str:
        return f"Can alert to {self.alert_type}"

# Roles as data, not types
class Role(Enum):
    PET = auto()
    SERVICE = auto()
    THERAPY = auto()
    WORKING = auto()

# Simple, flat class hierarchy
@dataclass
class Animal:
    species: str
    name: str

@dataclass
class Dog(Animal):
    breed: str
    roles: set[Role] = field(default_factory=set)
    capabilities: list[Capability] = field(default_factory=list)
    handler: str | None = None

    def __init__(self, name: str, breed: str):
        super().__init__(species="dog", name=name)
        self.breed = breed
        self.roles = set()
        self.capabilities = []
        self.handler = None

    def add_role(self, role: Role):
        self.roles.add(role)
        return self  # Fluent interface

    def add_capability(self, capability: Capability):
        self.capabilities.append(capability)
        return self

# Now creating any combination is easy:
buddy = (Dog("Buddy", "Labrador")
    .add_role(Role.SERVICE)
    .add_role(Role.THERAPY)  # Can be BOTH — no diamond problem
    .add_capability(GuidingCapability())
    .add_capability(AlertCapability("seizures"))
)

# A therapy dog that's also a pet — trivial:
luna = (Dog("Luna", "Golden Retriever")
    .add_role(Role.PET)
    .add_role(Role.THERAPY)
    .add_capability(TherapyCapability())
)
```

## The Principle

```
INHERITANCE = "is-a" = rigid, single axis of variation
COMPOSITION = "has-a" = flexible, multiple axes of variation

Use inheritance for: genuine type hierarchies (Animal → Dog, Shape → Circle)
Use composition for: capabilities, roles, behaviors, configurations

Rule of thumb: if you're past 2 levels deep, you probably need composition.
```'''
    ),
    (
        "thinking/causal-websocket-connections-dropping",
        "Our WebSocket connections drop after exactly 60 seconds of inactivity. Users complain that real-time updates stop working if they leave a tab open. What's causing this?",
        r'''<think>
WebSocket connections dropping after exactly 60 seconds. The "exactly 60 seconds" is the key clue — that's a timeout, not a random failure.

**Causal chain:**
1. Connection established → works fine
2. No messages for 60 seconds → connection drops
3. "Exactly 60 seconds" → something has a 60-second idle timeout

**What has idle timeouts?**
1. **Reverse proxy (most likely)** — Nginx default `proxy_read_timeout` is 60s. If no data flows for 60s, Nginx closes the connection.
2. **Load balancer** — AWS ALB default idle timeout is 60s. Azure, GCP similar.
3. **Cloud provider firewall** — Some NAT gateways drop idle TCP connections.
4. **The application server itself** — Less likely if HTTP works fine.

**Most probable cause: Nginx or load balancer**
The 60-second exact timeout strongly suggests Nginx's default `proxy_read_timeout: 60s`. This is the #1 cause of WebSocket drops in production.

**Solution: ping/pong heartbeat**
WebSocket protocol has built-in ping/pong frames. Send a ping every 30 seconds — this keeps the connection "active" from the proxy's perspective.

Also increase proxy timeouts for WebSocket endpoints specifically.
</think>

The "exactly 60 seconds" is the smoking gun — that's a **proxy timeout**, not a WebSocket issue.

## Root Cause

```
Most likely: Nginx proxy_read_timeout (default: 60s)
Also possible: Load balancer idle timeout (AWS ALB default: 60s)

Causal chain:
  WebSocket established → works fine
  → 60 seconds with no messages
  → Nginx/LB sees "idle connection"
  → Proxy closes the TCP connection
  → Client sees WebSocket disconnect
```

## Fix 1: Add Heartbeat (Ping/Pong)

```javascript
// SERVER SIDE (Node.js with ws library)
const WebSocket = require('ws');
const wss = new WebSocket.Server({ server });

// Send ping every 30 seconds (under the 60s timeout)
const HEARTBEAT_INTERVAL = 30000;

wss.on('connection', (ws) => {
    ws.isAlive = true;

    ws.on('pong', () => {
        ws.isAlive = true;  // Client responded to ping
    });
});

// Ping all clients periodically
const interval = setInterval(() => {
    wss.clients.forEach((ws) => {
        if (!ws.isAlive) {
            return ws.terminate();  // Dead connection — clean up
        }
        ws.isAlive = false;
        ws.ping();  // Send ping — expect pong back
    });
}, HEARTBEAT_INTERVAL);

wss.on('close', () => clearInterval(interval));

// CLIENT SIDE
const ws = new WebSocket('wss://api.example.com/ws');

// Browser WebSocket auto-responds to server pings with pong
// But also implement reconnection:
ws.onclose = (event) => {
    console.log('WebSocket closed, reconnecting...', event.code);
    setTimeout(() => reconnect(), 1000);  // Reconnect after 1 second
};
```

## Fix 2: Increase Proxy Timeouts

```nginx
# Nginx configuration for WebSocket endpoints
location /ws {
    proxy_pass http://backend;
    proxy_http_version 1.1;

    # Required for WebSocket upgrade
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    # Increase timeouts for WebSocket (default is 60s)
    proxy_read_timeout 3600s;    # 1 hour
    proxy_send_timeout 3600s;

    # Don't buffer WebSocket traffic
    proxy_buffering off;
}
```

## Fix 3: Client-Side Reconnection (Defense in Depth)

```javascript
class ReconnectingWebSocket {
    constructor(url) {
        this.url = url;
        this.reconnectDelay = 1000;
        this.maxDelay = 30000;
        this.connect();
    }

    connect() {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
            this.reconnectDelay = 1000;  // Reset delay on success
        };

        this.ws.onclose = (event) => {
            // Reconnect with exponential backoff
            setTimeout(() => this.connect(), this.reconnectDelay);
            this.reconnectDelay = Math.min(
                this.reconnectDelay * 2,
                this.maxDelay
            );
        };

        this.ws.onmessage = (event) => {
            this.onmessage?.(event);
        };
    }
}
```

## Diagnostic Check

```bash
# Verify: is it Nginx?
grep -r "proxy_read_timeout\|proxy_send_timeout" /etc/nginx/

# Verify: is it the load balancer?
# AWS: check ALB idle timeout in console (Target Group → Attributes)
aws elbv2 describe-target-group-attributes --target-group-arn $ARN \
  | grep idle_timeout

# Test: does the connection survive with traffic?
# If sending messages every 30s prevents disconnection,
# it's definitely an idle timeout.
```

**Do both:** add heartbeats AND increase proxy timeouts. Heartbeats are the primary fix; timeout increases are defense in depth.'''
    ),
    (
        "thinking/analogy-pub-sub-newspaper",
        "Can you explain the pub/sub messaging pattern? I don't understand why I'd use it instead of just calling functions directly.",
        r'''<think>
Pub/sub explained via analogy. The newspaper/magazine subscription model is the perfect real-world analogy.

**Direct function calls = phone calls**
You call someone directly. You need to know their number. If they're busy, you wait. If you want to tell 10 people, you make 10 calls.

**Pub/sub = newspaper subscription**
The newspaper publishes articles. Subscribers receive them. The newspaper doesn't know who reads it. Subscribers don't know who writes it. They're completely decoupled.

This maps perfectly:
- Publisher = newspaper/magazine
- Subscriber = reader
- Topic/channel = newspaper section (sports, business, etc.)
- Message broker = the postal service / distribution system
- Message = the newspaper/article itself

Why use pub/sub:
1. Decoupling — publisher doesn't need to know subscribers
2. Scalability — add subscribers without changing publisher
3. Flexibility — subscribe to only the topics you care about
</think>

Think of it like **newspaper subscriptions** vs **phone calls**.

## The Analogy

```
DIRECT FUNCTION CALLS = PHONE CALLS
  You want to tell 5 people about a sale:
  → Call Person 1 (wait for answer...)
  → Call Person 2 (wait for answer...)
  → Call Person 3 (busy, try again later...)
  → Call Person 4 (wait for answer...)
  → Call Person 5 (no answer, leave voicemail...)

  Problems:
  - You need everyone's phone number (tight coupling)
  - You call them one by one (slow)
  - If someone gets a new number, you need to update YOUR contacts
  - If you want to add Person 6, YOU have to change YOUR code
  - If Person 3 is busy, YOU have to deal with it

PUB/SUB = NEWSPAPER SUBSCRIPTION
  You want to tell people about a sale:
  → Publish an ad in the newspaper
  → Anyone subscribed to the "Sales" section sees it
  → You don't know who reads it, and you don't care

  Benefits:
  - You don't need to know the readers (decoupled)
  - 5 readers or 5000 — same effort for you (scalable)
  - Readers subscribe/unsubscribe without telling you (flexible)
  - The postal service handles delivery (broker)
```

## In Code

```python
# ❌ DIRECT CALLS: order service knows about EVERY downstream system
class OrderService:
    def place_order(self, order):
        self.save_to_database(order)

        # I need to know about ALL of these and call them directly:
        self.email_service.send_confirmation(order)     # What if email is down?
        self.inventory_service.reduce_stock(order)       # What if it's slow?
        self.analytics_service.track_purchase(order)     # What if we add a new one?
        self.loyalty_service.add_points(order)           # Another dependency...
        self.shipping_service.create_shipment(order)     # And another...
        # Adding a new service = modifying OrderService (bad!)

# ✅ PUB/SUB: order service publishes an event, doesn't know who listens
class OrderService:
    def __init__(self, event_bus):
        self.event_bus = event_bus

    def place_order(self, order):
        self.save_to_database(order)
        # Publish ONE event — done. Don't know or care who's listening.
        self.event_bus.publish("order.placed", {
            "order_id": order.id,
            "user_id": order.user_id,
            "items": order.items,
            "total": order.total,
        })

# Each service subscribes independently:
event_bus.subscribe("order.placed", email_service.send_confirmation)
event_bus.subscribe("order.placed", inventory_service.reduce_stock)
event_bus.subscribe("order.placed", analytics_service.track_purchase)

# Adding a new service? Just subscribe. OrderService never changes:
event_bus.subscribe("order.placed", loyalty_service.add_points)
event_bus.subscribe("order.placed", fraud_detector.check_order)
```

## When to Use Each

```
USE DIRECT CALLS when:
  - You need an immediate response (query a database)
  - There's only ONE recipient
  - Order matters (step 1 must finish before step 2)
  - You need the result to continue ("get user, then check permissions")

USE PUB/SUB when:
  - Multiple systems need to react to the same event
  - Publisher shouldn't know/care about subscribers
  - Processing can happen asynchronously
  - You want to add new behaviors without modifying existing code

ANALOGY:
  Direct call = "Hey John, the meeting moved to 3pm"
  Pub/sub = posting on the team calendar that the meeting moved
```'''
    ),
    (
        "thinking/adversarial-graphql-security",
        "We're exposing a GraphQL API for our mobile app. What security issues should we be aware of?",
        r'''<think>
GraphQL security — this has very specific attack vectors that are different from REST.

**GraphQL-specific attacks:**

1. **Query depth attacks** — deeply nested queries that cause exponential DB joins
2. **Query complexity/width attacks** — requesting every field on every object
3. **Batching attacks** — sending hundreds of queries in one request
4. **Introspection exposure** — the schema itself reveals your entire data model
5. **Authorization bypass via field-level access** — user can query fields they shouldn't see
6. **Injection via variables** — SQL injection through GraphQL variables
7. **Alias-based attacks** — using aliases to bypass rate limiting
8. **Directive abuse** — custom directives that expose internal behavior

Let me think about what an attacker would specifically try...

The most dangerous GraphQL-specific issue is probably the query depth attack because it can DoS your server with a single request. In REST, one request = one operation. In GraphQL, one request can trigger thousands of database queries.
</think>

GraphQL has **unique attack vectors** that REST doesn't. Here's what an attacker would try.

## 1. Query Depth Attack (DoS with One Request)

```graphql
# ❌ ATTACK: exponential database queries from a single request
query Evil {
  users {           # 100 users
    posts {         # 100 posts each = 10,000
      comments {    # 50 comments each = 500,000
        author {    # 1 author each = 500,000
          posts {   # 100 posts each = 50,000,000
            comments { ... }  # Your server is dead
          }
        }
      }
    }
  }
}
# One HTTP request → millions of database queries → OOM crash
```

```python
# ✅ FIX: limit query depth
from graphene import Schema
from graphql_depth_limit import DepthLimitValidator

schema = Schema(query=Query)

# Reject queries deeper than 5 levels
result = schema.execute(
    query,
    validation_rules=[DepthLimitValidator(max_depth=5)]
)
```

## 2. Query Complexity Attack

```graphql
# ❌ ATTACK: wide query requesting everything
query Expensive {
  allUsers(first: 10000) {
    id name email
    orders(first: 1000) { id total items { id name price } }
    reviews(first: 1000) { id rating text }
    addresses { street city country }
    paymentMethods { type last4 }
  }
}
```

```python
# ✅ FIX: query cost analysis
# Assign costs to fields, reject queries exceeding budget
from graphql_cost_analysis import CostAnalysisValidator

cost_map = {
    "Query.allUsers": {"complexity": 10, "multiplier": "first"},
    "User.orders": {"complexity": 5, "multiplier": "first"},
    "User.reviews": {"complexity": 3, "multiplier": "first"},
}

# Max cost of 1000 per query
validator = CostAnalysisValidator(maximum_cost=1000, cost_map=cost_map)
```

## 3. Introspection Exposure

```graphql
# ❌ ATTACK: discover your entire schema
query {
  __schema {
    types {
      name
      fields {
        name
        type { name }
      }
    }
  }
}
# Attacker now knows: User.ssn, User.passwordHash,
# AdminMutation.deleteAllUsers, InternalQuery.debugInfo
```

```python
# ✅ FIX: disable introspection in production
from graphql import validate

# Option 1: Disable introspection entirely
schema = Schema(query=Query, auto_camelcase=False)
# In production middleware:
if not settings.DEBUG:
    from graphql.validation import NoSchemaIntrospectionCustomRule
    extra_rules = [NoSchemaIntrospectionCustomRule]
```

## 4. Alias-Based Rate Limit Bypass

```graphql
# ❌ ATTACK: bypass "1 login attempt per second" rate limit
# This is ONE request but tries 100 passwords:
mutation {
  attempt1: login(email: "admin@co.com", password: "password1") { token }
  attempt2: login(email: "admin@co.com", password: "password2") { token }
  attempt3: login(email: "admin@co.com", password: "password3") { token }
  # ... 97 more attempts
  attempt100: login(email: "admin@co.com", password: "password100") { token }
}
```

```python
# ✅ FIX: count operations, not HTTP requests
# Rate limit by operation count within a single request
def execute_with_alias_limit(query, max_aliases=10):
    parsed = parse(query)
    for definition in parsed.definitions:
        selections = definition.selection_set.selections
        if len(selections) > max_aliases:
            raise GraphQLError(f"Too many operations: {len(selections)}")
```

## 5. Field-Level Authorization Bypass

```graphql
# ❌ ATTACK: user queries fields they shouldn't see
query {
  user(id: "other-user-id") {
    email            # Maybe allowed
    passwordHash     # Should NEVER be exposed
    ssn              # PII — needs authorization
    internalNotes    # Admin only
  }
}
```

```python
# ✅ FIX: field-level authorization
class UserType(graphene.ObjectType):
    email = graphene.String()
    ssn = graphene.String()

    def resolve_ssn(self, info):
        # Only the user themselves or admins can see SSN
        current_user = info.context.user
        if current_user.id != self.id and not current_user.is_admin:
            raise PermissionError("Not authorized to view SSN")
        return self.ssn

    # BETTER: don't expose sensitive fields AT ALL
    # password_hash should never be in the schema
```

## 6. Batch Query Attack

```json
// ❌ ATTACK: send 1000 queries in one HTTP request
[
  {"query": "{ user(id: 1) { name } }"},
  {"query": "{ user(id: 2) { name } }"},
  // ... 998 more
]
```

```python
# ✅ FIX: limit batch size
MAX_BATCH_SIZE = 10

@app.route('/graphql', methods=['POST'])
def graphql_endpoint():
    data = request.get_json()
    if isinstance(data, list) and len(data) > MAX_BATCH_SIZE:
        return jsonify({"error": f"Max {MAX_BATCH_SIZE} queries per batch"}), 400
```

## Security Checklist

```
□ Query depth limit (max 5-7 levels)
□ Query complexity/cost analysis (budget per query)
□ Disable introspection in production
□ Rate limit by operation count, not HTTP requests
□ Field-level authorization on sensitive fields
□ Batch query size limit
□ Timeout per query execution (5-10 seconds max)
□ Input validation on all arguments
□ Never expose internal fields (passwordHash, internal IDs)
□ Persisted queries in production (whitelist allowed queries)
```'''
    ),
    (
        "thinking/firstprinciples-why-hashing-passwords",
        "Why do we hash passwords? Can't we just encrypt them so we can decrypt if a user forgets their password?",
        r'''<think>
Password hashing from first principles. Why hash instead of encrypt?

**The fundamental question: what does the application NEED from a password?**
It only needs to VERIFY: "does this input match what the user set?" It never needs to RETRIEVE the original password.

**Encryption is reversible by design:**
- encrypt(password, key) → ciphertext
- decrypt(ciphertext, key) → password
- If someone gets the key, ALL passwords are exposed at once
- If someone gets the database AND the key (common in breaches), game over

**Hashing is one-way by design:**
- hash(password) → digest
- There is NO un-hash function
- To verify: hash(input) == stored_hash
- Even if someone gets the database, they can't reverse the hashes

**Why not decrypt for forgotten passwords?**
If YOU can decrypt, so can:
- A disgruntled employee
- An attacker who compromises your server
- A government subpoena
- Anyone who gets the encryption key

The correct answer to "I forgot my password" is "set a new one" — never "here's your old one."

**Additional considerations:**
- Plain hashing isn't enough (rainbow tables)
- Need salt (unique random value per password)
- Need slow hash function (bcrypt, argon2) — not SHA256
- Why slow? To make brute-force infeasible
</think>

The key insight: your application never needs to **know** the password. It only needs to **verify** it.

## From First Principles

```
WHAT DOES YOUR APP ACTUALLY DO WITH A PASSWORD?

  Login flow:
    1. User types password
    2. App checks: "does this match what they set before?"
    3. Yes → grant access. No → reject.

  At no point does the app need to RETRIEVE the original password.
  It only needs to VERIFY a match.

  ENCRYPTION: "I can lock it AND unlock it"
    → Designed for data you need back (files, messages, credit cards)
    → Reversible: decrypt(encrypt(x)) = x

  HASHING: "I can lock it but NOBODY can unlock it"
    → Designed for verification only
    → One-way: there is no un-hash function
    → To verify: hash(input) == stored_hash
```

## Why Encryption Is Dangerous for Passwords

```
SCENARIO: Your database gets breached (this WILL happen eventually)

WITH ENCRYPTION:
  Database has: encrypt("password123", KEY) → "a8f2e9..."
  Attacker also finds the encryption key (same server, env var, config file)
  decrypt("a8f2e9...", KEY) → "password123"
  → ALL passwords exposed instantly
  → Every user's OTHER accounts compromised too
     (because 65% of people reuse passwords)

WITH HASHING:
  Database has: hash("password123") → "ef92b7..."
  Attacker has "ef92b7..."
  There is NO reverse function. No key to steal.
  → Attacker must GUESS passwords and hash each guess
  → With bcrypt (slow hash): ~5 guesses per second
  → "password123" = cracked in minutes (common password)
  → "j#K9$mP2!xQ" = never cracked (heat death of universe)
```

## The Right Way

```python
import bcrypt

# STORING a password (registration)
def store_password(password: str) -> str:
    # bcrypt automatically:
    # 1. Generates a unique salt (random bytes)
    # 2. Hashes password + salt together
    # 3. Embeds the salt IN the hash (so you can verify later)
    # 4. Is intentionally SLOW (~100ms per hash)
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
    return hashed.decode()  # Store this in database

# VERIFYING a password (login)
def verify_password(input_password: str, stored_hash: str) -> bool:
    # bcrypt extracts the salt from the stored hash,
    # hashes the input with the same salt,
    # and compares
    return bcrypt.checkpw(
        input_password.encode(),
        stored_hash.encode()
    )

# "FORGOT PASSWORD" FLOW
def forgot_password(email: str):
    # Generate a random reset token (NOT the password)
    token = secrets.token_urlsafe(32)
    store_reset_token(email, token, expires_in=timedelta(hours=1))
    send_email(email, f"Reset your password: https://app.com/reset?token={token}")
    # User clicks link → sets NEW password → old password is gone forever
    # This is correct. You should NEVER be able to retrieve the old password.
```

## Why Bcrypt/Argon2 Instead of SHA-256?

```
SHA-256: designed to be FAST (billions per second on a GPU)
  → Attacker can try billions of password guesses per second
  → Common passwords cracked in seconds

bcrypt: designed to be SLOW (configurable, ~5-10 per second)
  → Attacker can try ~5 guesses per second
  → Even common passwords take much longer

argon2: designed to be slow AND memory-hard
  → Can't parallelize easily on GPUs
  → Current best practice for new applications

Speed comparison for an attacker trying to crack one hash:
  SHA-256:  10,000,000,000 guesses/sec → dictionary attack in seconds
  bcrypt:              5 guesses/sec → dictionary attack takes weeks
  argon2:              2 guesses/sec → dictionary attack takes months
```

## Why Salt?

```
WITHOUT SALT:
  hash("password123") always = "ef92b778..."
  If 1000 users have "password123", all 1000 have the same hash
  Attacker precomputes hashes of common passwords (rainbow table)
  → Instant lookup: "ef92b778..." → "password123"

WITH SALT (unique random value per user):
  hash("password123" + "a8f2") = "7c3d91..."  (user 1)
  hash("password123" + "b9e4") = "2f8a03..."  (user 2)
  Same password, different hashes. Rainbow tables are useless.
  Attacker must brute-force EACH user separately.
```

**Never email users their password.** If your system CAN show a user their password, your system is insecure. The answer to "I forgot my password" is always "set a new one."'''
    ),
    (
        "thinking/multiperspective-testing-strategy",
        "Our team argues constantly about testing. Some want 90% code coverage, others say integration tests are all you need, and our lead says we should only test critical paths. Who's right?",
        r'''<think>
Testing strategy debate — let me analyze each perspective.

**Perspective 1: High code coverage (90%+)**
Pros:
- Catches regressions
- Forces thinking about edge cases
- Provides confidence for refactoring
Cons:
- Coverage != correctness (you can have 100% coverage and miss all the bugs)
- Testing trivial code wastes time (getters, setters, data classes)
- Creates brittle test suites coupled to implementation
- Slows down development velocity

**Perspective 2: Integration tests only**
Pros:
- Tests actual user behavior
- Catches issues between components
- More resistant to refactoring (tests behavior, not implementation)
Cons:
- Slow to run (database, network, etc.)
- Hard to debug when they fail (which component broke?)
- Combinatorial explosion (can't cover all paths)
- Flaky (timeouts, race conditions, external dependencies)

**Perspective 3: Test critical paths only**
Pros:
- Pragmatic — focuses effort where it matters
- 80/20 rule — 20% of code handles 80% of value
- Faster development for non-critical features
Cons:
- Who decides what's "critical"? Subjective
- Bugs in "non-critical" paths still hurt users
- Critical paths can change as the product evolves

**My synthesis:**
The Testing Trophy (Kent C. Dodds) or Testing Pyramid modified:
- Many unit tests for pure logic / algorithms
- Fewer integration tests for component interactions
- Few E2E tests for critical user journeys
- All three are needed — the question is the ratio
</think>

They're each partially right. Here's the synthesis.

## Each Perspective's Strength and Blind Spot

```
HIGH COVERAGE ADVOCATE:
  Strength: "Untested code is unknown code. We need confidence to refactor."
  Blind spot: coverage ≠ correctness. 100% coverage with bad assertions
  catches nothing. Testing trivial code wastes time.

INTEGRATION-ONLY ADVOCATE:
  Strength: "Test what users actually do, not implementation details."
  Blind spot: Integration tests are slow, flaky, and hard to debug.
  Can't cover all edge cases. A failing integration test tells you
  SOMETHING broke but not WHAT.

CRITICAL-PATHS-ONLY ADVOCATE:
  Strength: "Focus effort where it matters. Don't test getters."
  Blind spot: "Critical" is subjective and changes over time.
  The billing bug that costs $1M was in code nobody thought was critical.
```

## The Practical Synthesis: Test by Risk and Complexity

```
DON'T organize tests by type (unit vs integration).
DO organize tests by what you're protecting:

HIGH RISK + COMPLEX LOGIC → thorough unit tests + integration tests
  Payment processing, authentication, authorization, data migrations
  "If this breaks, we lose money or trust"

HIGH RISK + SIMPLE LOGIC → integration tests
  CRUD operations on critical data, API contracts
  "Simple code, but failure is costly — verify it works end-to-end"

LOW RISK + COMPLEX LOGIC → unit tests
  Utility functions, data transformations, algorithms
  "Complex enough to have bugs, cheap enough to test thoroughly"

LOW RISK + SIMPLE LOGIC → skip or minimal tests
  Getters/setters, simple wiring, configuration, data classes
  "If this breaks, it's obvious and easy to fix"
```

## What This Looks Like in Practice

```python
# HIGH RISK + COMPLEX → thorough testing
# Payment calculation with discounts, taxes, currency conversion
def test_payment_calculation():
    assert calculate_total(items=[...], discount=0.1, tax_rate=0.08) == 108.00
    assert calculate_total(items=[], ...) == 0  # Edge case
    assert calculate_total(items=[...], discount=1.0, ...) == 0  # 100% discount
    # Also test with integration test hitting real payment API (sandbox)

# HIGH RISK + SIMPLE → integration test
# User registration (simple CRUD but critical)
def test_user_registration_flow():
    response = client.post("/register", json={"email": "a@b.com", ...})
    assert response.status_code == 201
    assert db.query(User).filter_by(email="a@b.com").one()
    # Verify email was sent, user can login, etc.

# LOW RISK + COMPLEX → unit test
# Date formatting utility with timezone handling
def test_format_date_with_timezone():
    assert format_date(dt, tz="US/Pacific") == "2024-03-05 PST"
    assert format_date(dt, tz="UTC") == "2024-03-05 UTC"

# LOW RISK + SIMPLE → skip
# class UserDTO:
#     def __init__(self, name, email): ...
# Don't test this. It's a data class.
```

## The Metrics That Actually Matter

```
INSTEAD OF: "We have 90% code coverage" (vanity metric)

TRACK:
  1. Bug escape rate — bugs found in production vs caught in tests
     "Are our tests catching the things that matter?"

  2. Time to debug — when a test fails, how fast can you find the cause?
     "Are our tests giving useful failure messages?"

  3. Test suite speed — how long does the full suite take?
     "Can developers run tests before every commit?"
     Under 5 minutes: good
     Over 15 minutes: developers skip tests

  4. Test maintenance cost — how often do tests break from refactoring?
     "Are tests coupled to implementation or behavior?"

  5. Deploy confidence — would you deploy on Friday at 4pm?
     If not, your tests aren't testing the right things.
```

## Practical Recommendations

```
START WITH:
  1. Integration tests for critical user journeys (login, purchase, etc.)
  2. Unit tests for complex business logic (pricing, permissions, etc.)
  3. Contract tests for API boundaries (between services)

SKIP:
  - Testing framework/library code (it's already tested)
  - Testing trivial getters/setters
  - Testing private methods (test through public interface)
  - Aiming for a coverage number (aim for confidence instead)

RULE OF THUMB:
  "Test the things that would wake you up at 3 AM if they broke."
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
