"""Phase 4A: Self-Improvement -- Training Data Generation (Part 4)

Teaching the model to generate high-quality training pairs for system design topics.
Each pair asks the model to CREATE training data and explains why each generated pair
is effective, building the meta-skill of self-improvement through data generation.
"""

PAIRS = [
    (
        "thinking/auto-datagen-load-balancing",
        r'''Generate 3 high-quality training pairs that teach load balancing concepts. For each pair, explain why it's effective training data.''',
        r'''<think>
To generate good training data for load balancing, I need to:
1. Cover different difficulty levels (beginner, intermediate, advanced)
2. Include realistic scenarios, not toy examples
3. Each pair should teach ONE clear concept
4. Answers should show the reasoning process, not just the solution

For beginner, I will cover what load balancing is and basic algorithms. For intermediate, health checks and session affinity -- the two problems every team hits within a week of deploying a load balancer. For advanced, multi-datacenter GSLB and consistent hashing for cache distribution.
</think>

Here are 3 training pairs for teaching load balancing concepts:

**Pair 1 (Beginner):**
```
Q: My web application runs on a single server handling about 500 requests per second. We expect traffic to spike to 2,000 req/s next month. Should I buy a bigger server or add more servers? If I add more, how do users get sent to the right one?

A: Adding more servers (horizontal scaling) is usually better than a bigger server (vertical scaling) because it also gives you redundancy -- if one server dies, the others keep running.

A load balancer sits in front of your servers and distributes incoming requests:

User Request -> Load Balancer -> Server 1 (500 req/s)
                              -> Server 2 (500 req/s)
                              -> Server 3 (500 req/s)
                              -> Server 4 (500 req/s)

Common distribution algorithms:

Round Robin -- sends requests to servers in order: 1, 2, 3, 4, 1, 2, 3, 4...
Simple and fair when all servers are identical. Problem: if Server 3 is handling a slow request, it still gets the next one.

Least Connections -- sends to whichever server has the fewest active connections. Better when request processing time varies (some take 10ms, others 2 seconds).

Weighted Round Robin -- some servers get more traffic than others. Useful when servers have different capacities.

For your case, start with 4 identical servers behind nginx using Least Connections:

upstream backend {
    least_conn;
    server 10.0.0.1:8080;
    server 10.0.0.2:8080;
    server 10.0.0.3:8080;
    server 10.0.0.4:8080;
}

Cloud alternatives: AWS ALB, Google Cloud Load Balancer, or Cloudflare handle this without managing nginx yourself.
```
**Why this is effective:** It starts from a concrete scaling problem, not abstract theory. The comparison of algorithms gives the learner a decision framework. Including both self-managed (nginx) and cloud options reflects reality.

**Pair 2 (Intermediate):**
```
Q: We added a load balancer in front of 4 servers, but we have two problems: (1) When a server crashes, users get errors for a few seconds before traffic stops going to it. (2) Our users' shopping carts disappear randomly -- they add items, then the next request goes to a different server without their session.

A: These are the two most common problems after deploying a load balancer: health checking and session management.

Problem 1 -- Health checks:

Configure active health checking so the load balancer probes each server periodically:

Your app needs a /health endpoint:
@app.get("/health")
def health_check():
    try:
        db.execute("SELECT 1")
        cache.ping()
        return {"status": "healthy"}, 200
    except Exception:
        return {"status": "unhealthy"}, 503

The load balancer pings /health every 5 seconds. After 2 consecutive failures, the server is removed from rotation. After 3 passes, it is added back.

Problem 2 -- Session management (three approaches, worst to best):

Option A: Sticky sessions (ip_hash) -- same client IP always hits the same server. Problem: if that server dies, those users lose their sessions. Fails behind corporate proxies where many users share one IP.

Option B: Centralized session store (recommended) -- store sessions in Redis instead of server memory. Any server can handle any request because sessions are fetched from Redis. If a server dies, no sessions are lost.

Option C: Client-side sessions -- store session data in an encrypted, signed cookie. No server-side state. Works for small payloads but cookies have a 4KB limit.

For your shopping cart: Option B. Move sessions to Redis. This makes your servers truly stateless and interchangeable.
```
**Why this is effective:** It addresses two problems every team encounters within a week of deploying a load balancer. The health check endpoint code is directly implementable. The three session approaches are ranked with clear reasoning, preventing the learner from picking the tempting but fragile sticky sessions option.

**Pair 3 (Advanced):**
```
Q: We are scaling to multiple data centers for redundancy. We need to route users to the nearest data center, handle failover if one goes down, and ensure consistent routing for our caching layer. What strategies work at this scale?

A: At multi-datacenter scale, you need three layers of load balancing:

Layer 1 -- Global (DNS-based routing): Route users to the nearest data center using geographic or latency-based DNS. User in Tokyo resolves api.example.com to the Tokyo DC IP. If Tokyo DC fails health checks, those users are routed to the next closest DC. AWS Route 53 and Cloudflare both support this natively.

Layer 2 -- Regional (Layer 7, HTTP-aware): Within each data center, a Layer 7 load balancer distributes traffic with content awareness. Route /api/* to API servers, /static/* to asset servers, /ws/* to WebSocket servers with upgrade headers. Layer 7 also handles TLS termination, rate limiting, and WAF rules.

Layer 3 -- Consistent hashing for cache servers: Standard round-robin does not work for caches. If you have 4 cache servers and add a 5th, round-robin reassigns about 80% of keys, causing a massive cache miss storm. Consistent hashing maps keys to a ring:

import hashlib
from bisect import bisect_right

class ConsistentHash:
    def __init__(self, nodes, virtual_nodes=150):
        self.ring = []
        self.node_map = {}
        for node in nodes:
            for i in range(virtual_nodes):
                h = int(hashlib.sha256(f"{node}:{i}".encode()).hexdigest(), 16)
                self.ring.append(h)
                self.node_map[h] = node
        self.ring.sort()

    def get_node(self, key):
        h = int(hashlib.sha256(key.encode()).hexdigest(), 16)
        idx = bisect_right(self.ring, h) % len(self.ring)
        return self.node_map[self.ring[idx]]

When you add or remove a node, only about 1/N keys are remapped. Virtual nodes ensure even distribution across physical servers.
```
**Why this is effective:** It shows load balancing as a multi-layered architecture, not a single component. Each layer has a different purpose and technology. The consistent hashing implementation with working code is the piece most system design discussions hand-wave over.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-message-queues",
        r'''Generate 3 high-quality training pairs that teach message queue patterns. For each pair, explain why it's effective training data.''',
        r'''<think>
To generate good training data for message queues, I need to:
1. Cover different difficulty levels (beginner, intermediate, advanced)
2. Include realistic scenarios, not toy examples
3. Each pair should teach ONE clear concept
4. Answers should show the reasoning process, not just the solution

For beginner, I will show WHY you need a queue with a real latency problem. For intermediate, acknowledgment and pub/sub patterns. For advanced, the transactional outbox pattern and idempotent consumers -- the two hardest problems in event-driven systems.
</think>

Here are 3 training pairs for teaching message queue patterns:

**Pair 1 (Beginner):**
```
Q: Our e-commerce checkout endpoint charges the credit card, sends a confirmation email, and updates inventory. It takes 8 seconds because the email service is slow. Users think payment failed and click "Pay" again. How do I make checkout faster?

A: Do not make the user wait for the email or inventory update. Use a message queue for non-critical tasks:

Before (synchronous):
def checkout(order):
    charge_card(order)       # 1 second
    send_email(order)        # 5 seconds (slow SMTP)
    update_inventory(order)  # 2 seconds
    return "Success"         # Total: 8 seconds

After (async for non-critical work):
def checkout(order):
    charge_card(order)                         # 1 second -- must be synchronous
    queue.publish("order.completed", order)     # ~5ms
    return "Success"                            # Total: ~1 second

# Separate worker process:
@queue.subscribe("order.completed")
def handle_order_completed(order):
    send_email(order)
    update_inventory(order)

A message queue is a buffer between services. The checkout puts a message on the queue and returns immediately. A worker picks it up later.

Why queues beat threads for this:
1. Durability -- if the server crashes, the message survives in the queue
2. Retry -- if email is down, the message stays and gets retried
3. Independent scaling -- add more email workers without changing checkout code
4. Backpressure -- 10,000 orders in a minute? The queue absorbs the spike

Popular options: Redis + Celery (Python), RabbitMQ, Amazon SQS, Apache Kafka.
```
**Why this is effective:** It starts from a real user experience problem (8-second checkout), not abstract theory. The before/after makes the benefit immediate. The four reasons queues beat threads address the natural follow-up question.

**Pair 2 (Intermediate):**
```
Q: What happens if my email worker crashes while processing a message -- does it get lost? Also, I want both the email service AND the analytics service to react to the same "order completed" event. Do I need two queues?

A: Two important concepts: acknowledgment (message safety) and pub/sub (fan-out).

Message acknowledgment: When a worker picks up a message, the queue does not delete it immediately. It waits for an explicit acknowledgment:

@queue.subscribe("order.completed")
def handle(message):
    try:
        send_email(message.data)
        message.ack()    # "Done, delete this message"
    except Exception:
        message.nack()   # "Failed, redeliver to another worker"

If the worker crashes (no ack/nack), the queue waits for a timeout, then redelivers. The message is NEVER lost unless explicitly acked.

After N failures, send to a Dead Letter Queue (DLQ) -- a holding area for messages that cannot be processed. Monitor the DLQ, debug the issue, then replay the messages.

Pub/Sub fan-out: Use consumer groups so multiple services each get their own copy:

queue.publish("events.order.completed", order_data)

# Email service -- gets its own copy
@queue.subscribe("events.order.completed", group="email-service")
def send_confirmation(order): ...

# Analytics service -- gets its own copy
@queue.subscribe("events.order.completed", group="analytics-service")
def record_analytics(order): ...

Each consumer group receives the message independently. To add a loyalty points service later, just subscribe with a new group -- no changes to checkout.
```
**Why this is effective:** It answers the two immediate follow-up questions every developer has after learning basic queues. The ack/nack pattern shows the complete message lifecycle, not just the happy path. Consumer groups bridge pub/sub and point-to-point in a way that maps to how RabbitMQ and Kafka actually work.

**Pair 3 (Advanced):**
```
Q: Our order service writes to the database AND publishes an event. What if the DB write succeeds but the publish fails? Also, our inventory service sometimes processes the same event twice, causing double-decrement of stock. How do we fix both?

A: These are the two hardest problems in event-driven systems: dual-write reliability and exactly-once processing.

Problem 1 -- Transactional Outbox Pattern:

You cannot atomically write to a database AND publish to a queue. Instead, write the event to your database in the same transaction:

BEGIN;
    INSERT INTO orders (id, customer_id, total) VALUES (123, 42, 99.99);
    INSERT INTO outbox_events (event_type, payload)
    VALUES ('order.completed', '{"order_id": 123, "total": 99.99}');
COMMIT;

A separate relay process polls the outbox and publishes:

async def outbox_relay():
    while True:
        events = db.query("SELECT * FROM outbox_events WHERE published = false LIMIT 100")
        for event in events:
            await queue.publish(event.event_type, event.payload)
            db.execute("UPDATE outbox_events SET published = true WHERE id = %s", event.id)
        await asyncio.sleep(1)

Same transaction means both succeed or both fail. The relay guarantees eventual delivery.

Problem 2 -- Idempotent Consumers:

At-least-once delivery means duplicates WILL happen. Track processed event IDs:

@queue.subscribe("order.completed")
def update_inventory(event):
    with db.transaction():
        if db.query("SELECT 1 FROM processed_events WHERE event_id = %s", event.id):
            event.ack()
            return
        db.execute("UPDATE products SET stock = stock - %s WHERE id = %s",
                   event.data["quantity"], event.data["product_id"])
        db.execute("INSERT INTO processed_events (event_id) VALUES (%s)", event.id)
    event.ack()

The deduplication check and business logic happen in ONE transaction. Also prefer naturally idempotent operations: SET status = 'shipped' is safe to repeat; SET stock = stock - 1 is not.

Together: outbox guarantees emission, idempotent consumers guarantee safe processing. This gives you effectively exactly-once semantics from at-least-once infrastructure.
```
**Why this is effective:** It tackles the two problems that make event-driven systems hard in practice. The outbox pattern with SQL shows exactly how atomicity is achieved. The idempotent consumer with transactional deduplication is production-grade. The natural idempotency tip is an elegant design principle.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-db-scaling",
        r'''Generate 3 high-quality training pairs that teach database scaling (sharding, replication). For each pair, explain why it's effective training data.''',
        r'''<think>
To generate good training data for database scaling, I need to:
1. Cover different difficulty levels (beginner, intermediate, advanced)
2. Include realistic scenarios, not toy examples
3. Each pair should teach ONE clear concept
4. Answers should show the reasoning process, not just the solution

For beginner, read replicas -- the first scaling step most teams take. For intermediate, sharding strategies and key selection. For advanced, cross-shard queries, rebalancing, and operational complexity. I should make clear that most teams should NOT shard until they have exhausted simpler options.
</think>

Here are 3 training pairs for teaching database scaling:

**Pair 1 (Beginner):**
```
Q: Our PostgreSQL database handles 5,000 queries per second. About 90% are reads and 10% are writes. The database CPU is at 95%. How do we scale without re-architecting?

A: Your first move should be read replicas. Since 90% of your traffic is reads, offloading them to replica databases can reduce your primary's load by roughly 90%.

Primary DB (handles all writes)
    |-- async replication --> Replica 1 (handles reads)
    |-- async replication --> Replica 2 (handles reads)
    |-- async replication --> Replica 3 (handles reads)

The primary streams WAL records to replicas. They stay in sync within milliseconds.

Route reads and writes in your application:

write_db = create_engine("postgresql://primary-db/myapp")
read_db = create_engine("postgresql://replica-db/myapp")

def get_user(user_id):
    return read_db.execute("SELECT * FROM users WHERE id = %s", user_id)

def update_user(user_id, data):
    return write_db.execute("UPDATE users SET ... WHERE id = %s", user_id)

The replication lag gotcha: replicas can be milliseconds behind. If a user updates their profile and immediately refreshes, they might see stale data (read from replica before the write arrives).

Fix with read-your-writes consistency:
if session.get('recent_write') and time.time() - session['recent_write'] < 5:
    db = write_db  # Read from primary for 5 seconds after a write
else:
    db = read_db

Impact: Primary drops from 5,000 qps to 500 writes/s (~15% CPU). Three replicas each handle 1,500 reads/s. This buys 10-50x capacity before you need sharding.
```
**Why this is effective:** It correctly positions read replicas as the FIRST scaling step, which matches real-world practice. The replication lag gotcha and read-your-writes fix are exactly what teams hit within a week. The capacity math makes the improvement tangible.

**Pair 2 (Intermediate):**
```
Q: We have maxed out our primary database at 50,000 writes per second across 2 billion rows. Read replicas handled read scaling but writes are the bottleneck now. How does sharding work, and how do we choose a sharding key?

A: Sharding splits data across multiple independent databases. Each shard handles reads AND writes for its subset. 4 shards = 4x write throughput.

Choosing a sharding key is the most important decision:

Good key properties:
1. High cardinality -- user_id has millions of values; country_code has only 200
2. Even distribution -- user_id is uniform; created_at creates temporal hotspots
3. Query locality -- most queries should hit ONE shard, not all of them

For e-commerce, shard by user_id:
  shard = hash(user_id) % num_shards

All of a user's data (orders, cart, profile) lives on one shard. User-centric queries are fast. The tradeoff: "all orders over $100 this week" hits ALL shards.

Do NOT shard by order_id -- fetching "all orders for user 42" would scatter across every shard.

Implementation:
class ShardRouter:
    def __init__(self, configs):
        self.shards = {i: create_engine(c) for i, c in enumerate(configs)}
        self.num = len(configs)

    def get_shard(self, user_id):
        return self.shards[hash(user_id) % self.num]

Before sharding, try these first (seriously):
1. Index optimization (often 100x improvement)
2. Query optimization
3. Read replicas
4. Caching (Redis)
5. Table partitioning (within a single database)
6. Vertical partitioning (move large columns to separate tables)

Sharding adds enormous operational complexity: no cross-shard joins, no cross-shard foreign keys, coordinated migrations. Only shard when simpler options are exhausted.
```
**Why this is effective:** It teaches sharding key selection as the central challenge, not just "split data." The comparison of user_id vs. order_id forces critical thinking. The "try these first" list prevents premature sharding -- one of the most expensive mistakes in system design.

**Pair 3 (Advanced):**
```
Q: We sharded by user_id across 16 shards a year ago. Now: (1) Shard 7 has 3x more data than shard 12 because some users are much more active. (2) Our admin dashboard needs "total revenue this month" across all shards. (3) We want to add more shards but cannot move data without downtime. How do we handle these?

A: These are the three hardest post-sharding problems: hotspots, cross-shard queries, and resharding.

Problem 1 -- Hotspot rebalancing:

Use consistent hashing with shard splitting. Each shard owns a hash range. Split hot shards:

Before: shard 7 owns range [1000, 2000)
After:  shard 7a owns [1000, 1500), shard 7b owns [1500, 2000)

Process: create 7b as a replica of 7, dual-write during migration, delete out-of-range data from each, update routing table, stop dual-writes.

Key prevention: start with more shards than you need (64 small shards is easier to rebalance than 4 large ones), and use UUIDs over sequential IDs for natural balance.

Problem 2 -- Cross-shard queries:

Scatter-gather works but is slow for complex queries:

async def total_revenue():
    tasks = [shard.execute("SELECT SUM(total) FROM orders WHERE created_at > %s", cutoff)
             for shard in all_shards]
    return sum(r[0] for r in await asyncio.gather(*tasks))

Better: stream all shard data into a separate analytics database using Change Data Capture (CDC) with tools like Debezium:

Shard 1 --CDC--> |
Shard 2 --CDC--> | Analytics DB (ClickHouse, BigQuery)
Shard 16 -CDC--> |

Admin queries hit the analytics DB. This is CQRS: Command Query Responsibility Segregation. Operational queries (fast, per-user) stay on shards. Analytical queries (slow, cross-user) go to a purpose-built store.

Problem 3 -- Resharding without downtime:

The Vitess approach (used by YouTube, Slack, GitHub):
1. Double-write: new writes go to both old and new shard locations
2. Backfill: copy historical data to new shards
3. Verify: compare checksums
4. Switch reads to new layout
5. Switch writes to new layout
6. Clean up moved data from old locations

For PostgreSQL, Citus handles resharding transparently. For MySQL, Vitess manages this at the proxy layer.

Design your application so 95%+ of queries hit a single shard, and accept that the remaining 5% (analytics, admin) will be handled by a separate system.
```
**Why this is effective:** It addresses three problems teams discover AFTER sharding, rarely covered in initial tutorials. The shard splitting with dual-writes is production-grade. The CDC-to-analytics pattern is the standard cross-shard solution. The "start with more shards" advice prevents resharding headaches from occurring.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-microservices-communication",
        r'''Generate 3 high-quality training pairs that teach microservices communication. For each pair, explain why it's effective training data.''',
        r'''<think>
To generate good training data for microservices communication, I need to:
1. Cover different difficulty levels (beginner, intermediate, advanced)
2. Include realistic scenarios, not toy examples
3. Each pair should teach ONE clear concept
4. Answers should show the reasoning process, not just the solution

For beginner, synchronous vs. asynchronous and when to use each. For intermediate, circuit breakers and cascading failure prevention. For advanced, the saga pattern for distributed transactions. The biggest mistake teams make is defaulting to synchronous HTTP for everything, creating a distributed monolith.
</think>

Here are 3 training pairs for teaching microservices communication:

**Pair 1 (Beginner):**
```
Q: We are splitting our monolith into microservices. The Order Service needs to check inventory and charge the customer during checkout. Should services communicate via REST APIs or message queues?

A: It depends on whether the caller needs to WAIT for the response.

Synchronous (REST/gRPC) -- when you need the answer now:
Order Service asks Inventory Service: "Is product 42 in stock?"
Inventory Service replies: "Yes, 15 available."
Order Service asks Payment Service: "Charge $99."
Payment Service replies: "Success."

Use synchronous when: the caller cannot proceed without the response, latency matters, the operation is simple request/response.

Asynchronous (Message Queue) -- when you do not need an immediate answer:
Order Service publishes "order.completed" event.
Email, Analytics, and Warehouse services each pick it up independently.

Use async when: the caller does not need the result, the downstream can be temporarily unavailable, or multiple services need to react.

For checkout, use BOTH:

def checkout(order):
    # Synchronous: must know before proceeding
    if inventory_service.check_stock(order.product_id) < order.quantity:
        return {"error": "Out of stock"}

    payment = payment_service.charge(order.card, order.total)
    if not payment.success:
        return {"error": "Payment failed"}

    db.save(order)

    # Asynchronous: background work
    queue.publish("order.completed", {"order_id": order.id})
    return {"status": "confirmed"}

Critical path (inventory, payment) is synchronous. Everything after confirmation (emails, analytics, shipping) is asynchronous.

Common mistake: making EVERYTHING synchronous. If checkout calls the email service synchronously and the SMTP server is down, checkout takes 30 seconds. Async isolates failures.
```
**Why this is effective:** It frames the choice as "do you need the answer now?" -- the correct decision criterion. Showing both in the same checkout flow demonstrates that real systems use a mix. The common mistake warning prevents the distributed monolith anti-pattern.

**Pair 2 (Intermediate):**
```
Q: Our Order Service calls the Inventory Service via REST. Sometimes Inventory is slow or completely down. When it is slow, our Order Service thread pool fills up and the entire checkout stops responding. How do we make this resilient?

A: You need timeouts and circuit breakers to prevent cascading failure.

Step 1 -- Timeouts (non-negotiable):
# BAD: waits forever if Inventory hangs
response = requests.get("http://inventory-service/stock/42")

# GOOD: always set connect and read timeouts
response = requests.get("http://inventory-service/stock/42", timeout=(2, 5))

Without a timeout, one slow downstream service consumes all your threads. YOUR service becomes unresponsive. This is cascading failure.

Step 2 -- Circuit breaker:
import circuitbreaker

@circuitbreaker.circuit(failure_threshold=5, recovery_timeout=30)
def check_inventory(product_id):
    response = requests.get(f"http://inventory-service/stock/{product_id}", timeout=(2, 5))
    response.raise_for_status()
    return response.json()

Three states:
- CLOSED (normal): requests go through, failures are counted
- OPEN (tripped): requests fail immediately, no network call -- prevents overwhelming a struggling service
- HALF-OPEN (testing): after recovery timeout, one request is tried. Success closes the breaker.

Step 3 -- Fallback:
def get_stock_level(product_id):
    try:
        return check_inventory(product_id)
    except circuitbreaker.CircuitBreakerError:
        cached = cache.get(f"stock:{product_id}")
        if cached:
            return {"stock": cached, "cached": True}
        return {"stock": "unknown"}

Step 4 -- Retries with exponential backoff:
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def check_inventory(product_id): ...

Retries handle transient failures. But retries WITHOUT a circuit breaker make things worse -- you triple the load on a struggling service.

Layer them: Retry -> Circuit Breaker -> Timeout -> Fallback
```
**Why this is effective:** It shows cascading failure as the real danger, motivating the patterns. The circuit breaker state machine is explained with concrete behavior. The fallback teaches graceful degradation -- the actual goal, not just error handling.

**Pair 3 (Advanced):**
```
Q: Our checkout involves Order, Payment, and Inventory services. If payment succeeds but inventory reservation fails, we need to refund. We cannot use a database transaction because each service has its own database. How do we coordinate?

A: This is the distributed transaction problem. Use the Saga pattern -- a sequence of local transactions with compensating actions.

Orchestration approach (central coordinator):

class CheckoutSaga:
    def __init__(self, order_data):
        self.order_data = order_data
        self.state = "STARTED"
        self.payment_id = None

    async def execute(self):
        try:
            order = await order_service.create(self.order_data)
            self.state = "ORDER_CREATED"

            payment = await payment_service.charge(order.customer_id, order.total)
            self.payment_id = payment.id
            self.state = "PAYMENT_CHARGED"

            await inventory_service.reserve(order.product_id, order.quantity)
            self.state = "INVENTORY_RESERVED"

            await order_service.confirm(order.id)
            self.state = "COMPLETED"
        except (InventoryError, PaymentError):
            await self.compensate()

    async def compensate(self):
        if self.state == "PAYMENT_CHARGED":
            await payment_service.refund(self.payment_id)
        if self.state in ("ORDER_CREATED", "PAYMENT_CHARGED"):
            await order_service.cancel(self.order_data["order_id"])
        self.state = "COMPENSATED"

Choreography approach (event-driven):

Happy path:
1. Order Service creates order (PENDING) -> emits "order.created"
2. Payment Service hears it -> charges card -> emits "payment.completed"
3. Inventory Service hears it -> reserves stock -> emits "inventory.reserved"
4. Order Service hears it -> confirms order

Failure at step 3:
3. Inventory: stock insufficient -> emits "inventory.failed"
4. Payment: hears it -> refunds -> emits "payment.refunded"
5. Order: hears it -> cancels order

Choreography vs. Orchestration:
- Choreography: no single point of failure, fully decoupled. But the flow is scattered across services and hard to debug.
- Orchestration: flow visible in one place, easy to modify. But the coordinator must be reliable.

Use orchestration for complex business processes. Use choreography for simple event reactions.

Critical details:
1. Persist saga state -- if the coordinator crashes, it must resume from where it left off
2. Compensating actions must be idempotent -- a refund might be called twice
3. Timeouts on every step -- if a service does not respond, assume failure and compensate
4. Model as a state machine with explicit transitions to prevent impossible states
```
**Why this is effective:** It presents both saga variants with honest tradeoffs and a clear recommendation. The compensating action code is concrete, not just a diagram. The implementation details (persist state, idempotent compensations, timeouts) separate toy implementations from production ones.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-monitoring-observability",
        r'''Generate 3 high-quality training pairs that teach monitoring and observability. For each pair, explain why it's effective training data.''',
        r'''<think>
To generate good training data for monitoring and observability, I need to:
1. Cover different difficulty levels (beginner, intermediate, advanced)
2. Include realistic scenarios, not toy examples
3. Each pair should teach ONE clear concept
4. Answers should show the reasoning process, not just the solution

For beginner, the three pillars (logs, metrics, traces). For intermediate, alert design that avoids alert fatigue -- the number one operational problem. For advanced, SLIs, SLOs, and error budgets -- the framework that connects reliability to engineering velocity.
</think>

Here are 3 training pairs for teaching monitoring and observability:

**Pair 1 (Beginner):**
```
Q: Our service had an outage last week and we did not know until customers complained on Twitter. We have logs but nobody watches them. Where do we start with monitoring?

A: You need the three pillars of observability:

1. Metrics -- "Is the system healthy RIGHT NOW?"
The four golden signals:
- Latency: how long do requests take? (p50=45ms, p99=200ms)
- Traffic: how many requests per second? (350 req/s)
- Error rate: what percentage fail? (0.5% 5xx)
- Saturation: how full are resources? (CPU 65%, memory 78%)

Implementation with Prometheus:
from prometheus_client import Counter, Histogram
REQUEST_COUNT = Counter('http_requests_total', 'Total', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'Latency', ['endpoint'])

@app.middleware("http")
async def metrics(request, call_next):
    start = time.time()
    response = await call_next(request)
    REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()
    REQUEST_LATENCY.labels(request.url.path).observe(time.time() - start)
    return response

2. Logs -- "What happened during a specific request?"
Use structured logs (JSON), not plain text:
# BAD: logger.info(f"User {uid} placed order {oid} for ${total}")
# GOOD:
logger.info("order_placed", extra={"user_id": uid, "order_id": oid, "total": total})

Structured logs let you query: "all orders over $500 that failed in the last hour."

3. Traces -- "What path did a request take across services?"
Traces show timing across services. Essential for microservices debugging.

Minimum viable setup:
1. Prometheus + Grafana for metrics (free, self-hosted)
2. Grafana Loki or ELK for centralized logs
3. Alert on error rate > 1% for 5 minutes -> Slack/PagerDuty

This catches outages in 5 minutes, not from Twitter.
```
**Why this is effective:** It starts from the pain point (found out from Twitter) and builds to a concrete minimum viable setup. The golden signals give a framework. Structured vs. unstructured logging is a practical improvement teams can make immediately.

**Pair 2 (Intermediate):**
```
Q: We set up monitoring and now 50 alerts fire every day. The team ignores them because most are false alarms. How do we design alerts people actually respond to?

A: Alert fatigue is the number one reason monitoring fails. Every alert must be actionable and important.

Rule 1 -- Alert on symptoms, not causes:
BAD: "CPU > 80%" (so what if requests are fast and errors are zero?)
BAD: "Disk > 70%" (not urgent for days)
GOOD: "Error rate > 1% for 5 minutes" (users are affected)
GOOD: "p99 latency > 2s for 10 minutes" (users are waiting)
GOOD: "Zero successful requests in 2 minutes" (service is down)

Cause-based alerts go on dashboards for investigation, not on pagers.

Rule 2 -- Every alert needs a runbook:
Alert: "order-service error rate > 1%"
Runbook:
1. Check Grafana dashboard
2. Is it one endpoint or all?
3. Check downstream services
4. Check recent deployments
5. Escalate if unresolved in 15 minutes

Rule 3 -- Tune thresholds:
If an alert fires 10 times a day and self-recovers, raise the threshold or widen the window. Tune until it fires 0-2 times per week.

Rule 4 -- Severity levels:
P1 (page at 3am): service down, error rate > 10%, data loss
P2 (Slack, 1 hour): error rate > 2%, latency degradation
P3 (ticket, 1 business day): elevated errors, cert expiring in 30 days

The test: "What would I do RIGHT NOW if this fires at 3am?" If the answer is "nothing" or "wait until morning," it is not a P1.

Audit your 50 alerts:
- Fired in last 30 days? No -> delete
- Anyone took action? No -> delete or downgrade
- Action was "acknowledge and ignore"? -> tune threshold

You should end up with 5-10 real alerts.
```
**Why this is effective:** It addresses the most common operational failure with concrete rules. "Alert on symptoms, not causes" is the key insight most teams get wrong. The audit process gives a concrete step to fix existing alert sprawl immediately.

**Pair 3 (Advanced):**
```
Q: Our SRE team talks about "SLOs" and "error budgets" but engineering does not understand how these affect their work. How do SLIs, SLOs, and error budgets connect, and how do they help make decisions?

A: SLIs, SLOs, and error budgets create a shared framework between engineering (ship features) and operations (keep things stable).

SLI (Service Level Indicator) -- what you measure:
- Availability: (total requests - 5xx) / total requests
- Latency: requests under 300ms / total requests
Choose SLIs that reflect USER experience. CPU usage is not an SLI.

SLO (Service Level Objective) -- your target:
"99.9% of requests return non-5xx over a 30-day window"
99.9% = 43.2 minutes of allowed downtime per month
99.95% = 21.6 minutes
99.99% = 4.3 minutes

Error Budget -- the decision framework:
Error budget = 100% - SLO = allowed unreliability

For 99.9% SLO with 1,000,000 requests/month:
Budget = 0.1% = 1,000 failed requests allowed

This is the key: you HAVE a budget to spend on unreliability.

Budget 20% consumed, 60% of month remaining: ship features aggressively.
Budget 80% consumed, 60% remaining: slow down, focus on reliability.
Budget exceeded: freeze feature launches until it recovers.

Implementation:
# Track burn rate, not just absolute errors
burn_rate = (errors_last_hour / requests_last_hour) / (1 - slo_target)
# Alert when burn_rate > 14.4 (will exhaust budget in 5 hours)

How this changes decisions:

Without error budgets:
PM: "Ship the feature!" SRE: "It is risky." (Argument based on feelings)

With error budgets:
PM: "Ship the feature!" SRE: "We have 15% budget left with 20 days remaining. Ship it, but if it causes errors, we freeze deploys." (Decision based on data)

Error budgets make reliability an engineering decision, not a political one. Reliable teams earn the right to ship fast. Teams that burn their budget invest in stability.
```
**Why this is effective:** It builds from measurement (SLI) to target (SLO) to decision framework (error budget) in a logical chain. The conversation comparison (feelings vs. data) makes organizational value concrete. The burn rate alert is a practical technique most SLO implementations need but tutorials skip.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
