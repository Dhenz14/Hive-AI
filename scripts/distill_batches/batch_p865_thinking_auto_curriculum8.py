"""Phase 4C: Self-Improvement -- Curriculum Design (Part 8)

Designing distributed systems curriculum for progressive skill development.
"""

PAIRS = [
    (
        "thinking/auto-curriculum-distributed-fundamentals",
        r'''Design the foundational portion of a distributed systems curriculum. Start from single-server concepts and build up to the core challenges: network failures, consistency, and partition tolerance.''',
        r'''<think>
Distributed systems curriculum is challenging because:
1. It requires understanding of networking, databases, and systems design
2. The concepts are counter-intuitive (things that work locally fail at scale)
3. Theory (CAP theorem) is meaningless without practical experience
4. Students need hands-on experience with failures

Progression: single server -> what changes with multiple servers -> fundamental impossibility results -> practical trade-offs
</think>

**Distributed Systems Curriculum: Foundations**

**Module 1: From Single Server to Distributed (3 hours)**

```
Learning objectives:
- Understand why we distribute systems
- Identify what breaks when moving from one server to many
- Understand the fundamental challenges unique to distributed systems

Content:
1. Why distribute?
   - Single server limits: CPU, memory, disk, network bandwidth
   - Availability: one server = single point of failure
   - Latency: users worldwide, server in one location
   - Scaling: vertical scaling has a ceiling

2. What changes when you add a second server?
   - State synchronization: both servers need the same data
   - Clock differences: servers disagree on what time it is
   - Network unreliability: messages can be lost, delayed, or duplicated
   - Partial failure: one server can fail while the other continues

3. The eight fallacies of distributed computing:
   - The network is reliable (it is not)
   - Latency is zero (it is not)
   - Bandwidth is infinite (it is not)
   - The network is secure (it is not)
   - Topology does not change (it does)
   - There is one administrator (there is not)
   - Transport cost is zero (it is not)
   - The network is homogeneous (it is not)

Exercise:
  Build a simple key-value store that runs on a single server.
  Now make it run on two servers. Discover (hands-on) the problems:
  - Write to server A, read from server B -- data is missing!
  - Both servers accept writes -- which one is correct?
  - Server A goes down -- what happens to its data?

Assessment:
  "Explain three things that work perfectly on a single server
   but break when you add a second server. For each, describe the
   failure mode and a possible solution."
  Pass criteria: correctly identifies state sync, clock skew,
                 and partial failure issues
```

**Module 2: Network Failures and Timeouts (3 hours)**

```
Prerequisites: Module 1

Learning objectives:
- Understand the types of network failures
- Design timeout strategies
- Handle partial failures gracefully
- Distinguish between "server is down" and "network is down"

Content:
1. Types of network failures:
   - Message lost (packet dropped)
   - Message delayed (congestion, routing changes)
   - Message duplicated (retransmission)
   - Message reordered (different network paths)
   - Connection reset (server crash, firewall timeout)

2. The impossibility of detecting failure:
   ```
   Client sends request to server.
   No response after 5 seconds.

   Possible causes:
   a) Server is down (crashed)
   b) Server is slow (overloaded)
   c) Network is partitioned (server is fine, can't reach it)
   d) Response was sent but lost
   e) Response is slow (network congestion)

   THE CLIENT CANNOT DISTINGUISH BETWEEN THESE.
   ```

3. Timeout strategies:
   - Fixed timeout: simple but often wrong
   - Adaptive timeout: adjusts based on observed latency
   - Deadline propagation: remaining time budget passed to each hop
   - Circuit breaker: stop trying after N failures

4. Idempotency: making retries safe
   - If you retry and the first request actually succeeded,
     you might double-charge the customer
   - Idempotency keys prevent duplicate processing

Exercise:
  Simulate network failures between two services:
  1. Introduce random 50% packet loss
  2. Add 2-second delay to 20% of requests
  3. Kill the server and observe client behavior
  4. Implement timeout + retry + idempotency key

Assessment:
  "Design a payment system between two services that handles
   all network failure modes without double-charging or losing
   charges. Explain your idempotency strategy."
  Pass criteria: idempotency key design is correct, timeout
                 strategy handles all failure modes
```

**Module 3: Consistency Models (4 hours)**

```
Prerequisites: Module 2

Learning objectives:
- Understand strong vs eventual consistency
- Explain linearizability, sequential consistency, causal consistency
- Choose the right consistency model for different use cases
- Recognize the trade-offs of each model

Content:
1. Strong consistency (linearizability):
   - Every read returns the most recent write
   - Behaves as if there is one copy of the data
   - Expensive: requires coordination between all replicas

2. Eventual consistency:
   - Reads may return stale data
   - All replicas will eventually converge
   - Cheap: no coordination needed
   - Window of inconsistency varies

3. Levels between strong and eventual:
   - Read-your-writes: you always see your own updates
   - Monotonic reads: once you see a value, you never see an older one
   - Causal consistency: cause always appears before effect

4. When to use which:
   | Use case | Consistency needed | Why |
   |----------|-------------------|-----|
   | Bank balance | Strong | Cannot show wrong balance |
   | Social media likes | Eventual | 5 seconds stale is OK |
   | Shopping cart | Read-your-writes | User must see their own items |
   | Chat messages | Causal | Reply must appear after question |
   | DNS | Eventual | Updates propagate over hours |
   | Inventory count | Strong for purchase, eventual for display |

Exercise:
  Implement a replicated counter with different consistency models:
  1. Strong consistency: use a lock (observe the performance cost)
  2. Eventual consistency: no lock (observe the inconsistency)
  3. Compare throughput and accuracy of both approaches

Assessment:
  "For each of these 5 scenarios, recommend a consistency model
   and explain the trade-off you are making:
   1. User's account balance
   2. Number of unread notifications
   3. Product inventory for display
   4. Product inventory for checkout
   5. Blog post comment count"
  Pass criteria: correct model for each scenario with clear
                 reasoning about trade-offs
```

**Module 4: CAP Theorem and Practical Trade-offs (3 hours)**

```
Prerequisites: Module 3

Learning objectives:
- Understand the CAP theorem correctly (not the oversimplified version)
- Know that CAP is about behavior DURING partitions
- Make informed AP vs CP decisions for different parts of a system
- Understand PACELC as a more complete framework

Content:
1. CAP theorem (correct version):
   - During a network partition, you must choose:
     CP: Refuse to serve requests (maintain consistency)
     AP: Serve requests with possibly stale data (maintain availability)
   - When there is NO partition, this choice does not apply
   - CAP is not about choosing 2 of 3 in general

2. Common misunderstandings:
   - "MongoDB is AP" -- NO, it depends on configuration
   - "You must choose one for your entire system" -- NO,
     different parts can make different choices
   - "CA is an option" -- NO, you cannot choose to have no partitions

3. PACELC framework (more useful):
   If Partition: choose Availability or Consistency
   Else: choose Latency or Consistency
   - PA/EL: Available during partition, low latency normally (Cassandra)
   - PC/EC: Consistent always, higher latency (traditional RDBMS)
   - PA/EC: Available during partition, consistent normally (MongoDB default)

4. Practical decision making:
   - "What should happen when the database replica is unreachable?"
   - "What should happen when the cache is stale?"
   - "What should happen when the message queue is full?"

Exercise:
  Design the consistency strategy for an e-commerce platform:
  - Product catalog: what happens during a partition?
  - Shopping cart: what happens during a partition?
  - Payment processing: what happens during a partition?
  - Order confirmation: what happens during a partition?

Assessment:
  "For a banking application, explain what CAP trade-off you would
   make for: balance queries, fund transfers, transaction history,
   and login. Justify each choice."
  Pass criteria: correct application of CAP to each feature,
                 recognition that different features need different trade-offs
```'''
    ),
    (
        "thinking/auto-curriculum-distributed-patterns",
        r'''Design the intermediate portion of a distributed systems curriculum covering practical patterns: replication, partitioning, consensus, and distributed transactions.''',
        r'''<think>
Intermediate distributed systems should cover:
1. Replication strategies (leader-follower, multi-leader, leaderless)
2. Partitioning/sharding strategies
3. Consensus protocols (simplified Raft)
4. Distributed transactions (2PC, saga pattern)

These are the patterns developers actually use in production. The curriculum should be practical with real database examples, not just theory.
</think>

**Distributed Systems Curriculum: Intermediate Patterns**

**Module 5: Replication Strategies (4 hours)**

```
Prerequisites: Modules 1-4

Learning objectives:
- Understand leader-follower, multi-leader, and leaderless replication
- Configure database replication
- Handle replication lag
- Choose the right replication strategy

Content:
1. Leader-Follower (single-leader) replication:
   ```
   Writes --> [Leader] --> [Follower 1] (read replica)
                       --> [Follower 2] (read replica)

   Pros: Simple, consistent writes
   Cons: Leader is a bottleneck, failover is complex
   Used by: PostgreSQL, MySQL, MongoDB (default)
   ```

2. Multi-leader replication:
   ```
   [Leader A] <--> [Leader B]
     |                |
   [Follower]     [Follower]

   Pros: Writes in multiple locations (multi-datacenter)
   Cons: Write conflicts (both leaders modify same row)
   Used by: CouchDB, some MySQL setups
   ```

3. Leaderless replication:
   ```
   Client writes to N replicas simultaneously.
   Client reads from N replicas, takes most recent.
   Quorum: W + R > N ensures consistency.

   Example: N=3, W=2, R=2
   Write succeeds when 2/3 replicas acknowledge.
   Read queries 2/3 replicas, returns the most recent.

   Used by: Cassandra, DynamoDB, Riak
   ```

4. Handling replication lag:
   - Read-after-write consistency with leader reads
   - Monotonic reads with session stickiness
   - Causal consistency with version vectors

Exercises:
  1. Set up PostgreSQL with one leader and two read replicas.
     Write to the leader, read from replicas.
     Observe replication lag under load.

  2. Implement read-after-write consistency:
     After a user writes, read from the leader for 5 seconds.
     After 5 seconds, read from any replica.

  3. Simulate leader failure. Promote a follower.
     What happens to writes that were not replicated yet?

Assessment:
  "Design the replication strategy for an application with users
   in the US and Europe. Consider: write latency, read latency,
   consistency requirements, and failure handling."
  Pass criteria: appropriate strategy for the scenario, handles
                 failure modes, addresses consistency trade-offs
```

**Module 6: Data Partitioning (Sharding) (4 hours)**

```
Prerequisites: Module 5

Learning objectives:
- Understand why and when to partition data
- Choose partition keys
- Handle cross-partition queries
- Rebalance partitions when adding/removing nodes

Content:
1. Why partition?
   - Dataset too large for one server
   - Write throughput exceeds one server's capacity
   - Different data needs different geographic locations

2. Partition strategies:
   ```
   Key-range partitioning:
     Partition 1: users A-M
     Partition 2: users N-Z
     Pro: range queries are efficient
     Con: hotspots (more users with names starting A-F)

   Hash partitioning:
     Partition = hash(user_id) % num_partitions
     Pro: even distribution
     Con: range queries require querying all partitions

   Consistent hashing:
     Nodes on a hash ring, keys assigned to nearest node
     Pro: adding/removing nodes moves minimal data
     Con: more complex implementation
   ```

3. Choosing partition keys:
   ```
   Good partition key: high cardinality, even distribution, used in queries
   Bad partition key: low cardinality, skewed distribution

   Examples:
   | Data | Good key | Bad key | Why bad? |
   |------|---------|---------|----------|
   | Users | user_id | country | US has 70% of users |
   | Orders | order_id | status | "completed" has 95% of orders |
   | Events | event_id | event_type | Login events dominate |
   | Messages | conversation_id | sender_id | Some users send 1000x more |
   ```

4. Cross-partition queries:
   - Scatter-gather: query all partitions, combine results
   - Global secondary indexes: maintain index across partitions
   - Denormalization: store data in multiple partitions

Exercises:
  1. Partition a user database by user_id across 4 shards.
     Write a routing layer that directs queries to the right shard.

  2. Implement a cross-partition search:
     "Find all users with email domain @example.com"
     (requires querying all shards)

  3. Add a 5th shard. Rebalance data from the existing 4 shards.
     Ensure zero downtime during rebalancing.

Assessment:
  "Design the partitioning strategy for a messaging application
   with 100M users. Consider: message storage, conversation lookups,
   search, and adding new servers."
  Pass criteria: partition key choice is justified, cross-partition
                 queries are addressed, rebalancing strategy exists
```

**Module 7: Consensus and Leader Election (4 hours)**

```
Prerequisites: Modules 5-6

Learning objectives:
- Understand why consensus is needed
- Know how Raft works at a high level
- Implement a simplified leader election
- Understand the cost of consensus

Content:
1. The consensus problem:
   - Multiple nodes must agree on a value
   - Even if some nodes fail or messages are lost
   - Examples: who is the leader? What is the committed transaction log?

2. Raft consensus (simplified):
   ```
   Three roles: Leader, Follower, Candidate

   Normal operation:
     Leader sends heartbeats to followers.
     Clients send writes to leader.
     Leader replicates to followers, commits when majority acknowledge.

   Leader failure:
     Followers stop receiving heartbeats.
     After timeout, a follower becomes a Candidate.
     Candidate requests votes from other nodes.
     If majority vote yes, Candidate becomes new Leader.

   Split brain prevention:
     A leader needs majority acknowledgment for every write.
     With 5 nodes, need 3 to acknowledge (quorum).
     Two partitions cannot both have a majority.
   ```

3. Practical consensus systems:
   - etcd (Kubernetes uses this for configuration)
   - ZooKeeper (Kafka uses this for coordination)
   - Consul (service discovery and configuration)

Exercises:
  1. Implement a simplified leader election:
     - 3 nodes communicate via HTTP
     - Each node has a random election timeout
     - On timeout, request votes from others
     - Majority wins, becomes leader

  2. Simulate a network partition:
     - Leader is isolated from 2 followers
     - Followers elect a new leader
     - Partition heals -- what happens to the old leader?

  3. Observe consensus overhead:
     - Compare write latency with 1 node vs 3 vs 5
     - Why does adding more nodes increase latency?

Assessment:
  "Explain what happens in a 5-node Raft cluster when:
   1. The leader crashes
   2. Two followers crash simultaneously
   3. A network partition splits the cluster 2-3
   4. The partition heals
   For each, describe the state transitions and final outcome."
  Pass criteria: correct description of elections, quorum behavior,
                 and partition handling
```

**Module 8: Distributed Transactions (4 hours)**

```
Prerequisites: Module 7

Learning objectives:
- Understand two-phase commit (2PC) and its limitations
- Implement the saga pattern for long-running transactions
- Choose between 2PC and sagas for different scenarios
- Handle compensation (undo) in distributed systems

Content:
1. Two-Phase Commit (2PC):
   ```
   Phase 1 (Prepare):
     Coordinator asks all participants: "Can you commit?"
     Each participant: locks resources, writes to WAL, responds Yes/No

   Phase 2 (Commit/Abort):
     If ALL said Yes: Coordinator sends "Commit" to all
     If ANY said No: Coordinator sends "Abort" to all

   Problem: If coordinator crashes between phases,
   participants are stuck holding locks forever.
   This is called the "blocking problem."
   ```

2. Saga Pattern:
   ```
   Instead of one distributed transaction,
   execute a series of local transactions with compensating actions:

   Book Flight -> Book Hotel -> Charge Payment

   If "Charge Payment" fails:
     Cancel Hotel (compensation)
     Cancel Flight (compensation)

   Saga types:
   - Choreography: each service triggers the next
   - Orchestration: a coordinator directs the flow
   ```

3. Choosing between 2PC and Sagas:
   | Factor | 2PC | Saga |
   |--------|-----|------|
   | Consistency | Strong (ACID) | Eventual |
   | Latency | High (locks held) | Low (no global locks) |
   | Availability | Low (coordinator is SPOF) | High |
   | Complexity | Protocol complexity | Compensation logic |
   | Best for | Short transactions, few participants | Long transactions, many services |

Exercises:
  1. Implement a saga for an order process:
     - Reserve inventory
     - Charge payment
     - Send confirmation email
     Implement compensating actions for each step.

  2. Introduce a failure at step 2 (payment fails).
     Verify that step 1 is compensated (inventory released).

  3. Introduce a failure in compensation itself.
     What happens when the "cancel inventory" step also fails?
     Design a solution (retry queue, manual intervention).

Assessment:
  "Design the transaction strategy for a travel booking system
   that books flights, hotels, and car rentals across three
   different external APIs. Handle all failure scenarios including:
   partial booking success, payment failure after booking, and
   compensation failure."
  Pass criteria: saga design handles all failure modes, compensation
                 logic is correct, failure of compensation is addressed
```'''
    ),
    (
        "thinking/auto-curriculum-distributed-operations",
        r'''Design the operations-focused portion of a distributed systems curriculum covering observability, debugging distributed systems, and chaos engineering.''',
        r'''<think>
Operations curriculum for distributed systems should cover:
1. Observability (metrics, logs, traces) -- you cannot fix what you cannot see
2. Debugging distributed failures -- different from single-server debugging
3. Chaos engineering -- proactively finding weaknesses
4. Incident response -- handling failures in production

This is the practical "how to run distributed systems" portion that many curricula skip.
</think>

**Distributed Systems Curriculum: Operations**

**Module 9: Distributed Observability (4 hours)**

```
Prerequisites: Modules 1-8

Learning objectives:
- Implement the three pillars of observability: metrics, logs, traces
- Correlate events across multiple services
- Build dashboards that detect problems quickly
- Set up alerting that is actionable, not noisy

Content:
1. The three pillars:
   ```
   Metrics: What is happening? (counters, gauges, histograms)
     - Request rate: 500 requests/second
     - Error rate: 2% of requests returning 5xx
     - Latency: p50=50ms, p95=200ms, p99=1.2s

   Logs: Why did it happen? (structured event records)
     - {"timestamp": "...", "request_id": "abc", "error": "connection refused",
        "service": "payment", "user_id": 42}

   Traces: How did it flow? (request path across services)
     - Request abc: API Gateway (5ms) -> Order Service (15ms)
       -> Payment Service (200ms SLOW) -> Database (3ms)
   ```

2. Correlation:
   - Request ID propagated through all services
   - One search query shows the complete request lifecycle
   - Metrics spike -> find related logs -> trace to root cause

3. Key metrics to monitor:
   ```
   RED method (for request-driven services):
     Rate: requests per second
     Errors: error rate
     Duration: latency distribution

   USE method (for resources):
     Utilization: % of resource capacity used
     Saturation: work queued waiting for resource
     Errors: error count for the resource
   ```

4. Alerting best practices:
   - Alert on symptoms (high error rate) not causes (CPU usage)
   - Every alert must be actionable (not "disk is 50% full")
   - Use severity levels: page (wake someone up) vs notify (check tomorrow)
   - Avoid alert fatigue: if you ignore an alert regularly, fix or delete it

Exercise:
  Instrument a multi-service application:
  1. Add request ID propagation between 3 services
  2. Add RED metrics to each service
  3. Set up structured JSON logging
  4. Create a dashboard showing:
     - Request rate per service
     - Error rate per service
     - Latency percentiles
     - Cross-service request trace

Assessment:
  "A user reports slow responses. Using only your observability tools
   (not the code), identify which service is slow, which endpoint,
   and what the likely cause is."
  Pass criteria: can trace from symptom to root cause using only
                 metrics, logs, and traces
```

**Module 10: Debugging Distributed Failures (3 hours)**

```
Prerequisites: Module 9

Learning objectives:
- Debug failures that span multiple services
- Handle the "works on my machine" problem at distributed scale
- Use systematic approaches instead of guessing
- Reproduce distributed failures locally

Content:
1. Why distributed debugging is hard:
   - The bug might be in any of N services
   - The bug might be in the NETWORK between services
   - The bug might only occur under specific timing/load
   - Logs are scattered across multiple machines
   - Adding debugging (print statements) changes timing

2. Systematic debugging approach:
   ```
   Step 1: Reproduce the symptom
     - What error do users see?
     - When does it happen? (time, load, specific actions)
     - How often? (always, intermittently, under load only)

   Step 2: Narrow down the scope
     - Which service returns the error? (check API gateway logs)
     - Is it the service or its dependencies? (check dependency calls)
     - Is it data-dependent? (does it happen for specific users/data?)

   Step 3: Trace the request
     - Find the request ID from the error
     - Search all service logs for that request ID
     - Build the timeline: what happened, in what order

   Step 4: Identify the root cause
     - Network issue? (timeout, connection refused)
     - Data issue? (missing record, corrupt data)
     - Race condition? (timing-dependent behavior)
     - Resource exhaustion? (memory, connections, threads)

   Step 5: Verify the fix
     - Can you reproduce the bug in a test?
     - Does the fix address the root cause?
     - Does the fix handle similar failure modes?
   ```

3. Common distributed system bugs:
   | Bug pattern | Symptom | Root cause |
   |------------|---------|------------|
   | Cascading failure | All services down | One service failure causes others to timeout |
   | Split brain | Inconsistent data | Network partition, two leaders |
   | Thundering herd | Sudden overload | Cache expiry + all clients refresh |
   | Retry storm | Amplified load | Clients retry failed requests, multiplying load |
   | Clock skew | Out-of-order events | Servers disagree on time |

Exercise:
  Debug 3 injected failures in a multi-service application:
  1. A service is returning 500 errors intermittently
  2. Data is inconsistent between two services
  3. The system slows down gradually over hours

  For each: identify the root cause, explain the failure mechanism,
  and implement a fix.

Assessment:
  Pass criteria: correctly identifies all 3 root causes using
                 systematic debugging (not guessing), fixes address
                 the root cause not just the symptom
```

**Module 11: Chaos Engineering (3 hours)**

```
Prerequisites: Modules 9-10

Learning objectives:
- Understand chaos engineering principles
- Design and run chaos experiments safely
- Build confidence in system resilience
- Create a chaos testing practice for your team

Content:
1. Chaos engineering principles:
   - Start with a hypothesis: "If service X fails, users can still checkout"
   - Minimize blast radius: test in staging first, then limited production
   - Run experiments continuously, not just once
   - Fix what breaks before running more experiments

2. Types of chaos experiments:
   ```
   Infrastructure chaos:
     - Kill a server instance
     - Fill disk to 100%
     - Introduce network latency (100ms -> 5000ms)
     - Partition network between services

   Application chaos:
     - Return errors from a service endpoint
     - Slow down a database query
     - Expire all cache entries simultaneously
     - Corrupt a message in the queue

   Dependency chaos:
     - Block access to external API
     - Return invalid data from dependency
     - Simulate DNS failure
   ```

3. Running experiments safely:
   ```
   Experiment template:
     Hypothesis: [What we expect to happen]
     Steady state: [What "normal" looks like -- metrics]
     Method: [What we will break]
     Blast radius: [Which users/services are affected]
     Abort conditions: [When to stop the experiment]
     Duration: [How long to run]

   Example:
     Hypothesis: If the payment service goes down,
                 users see a clear error message and can
                 retry later. No orders are lost.
     Steady state: Error rate < 0.1%, order success rate > 99%
     Method: Kill all payment service instances for 2 minutes
     Blast radius: 5% of traffic (canary)
     Abort: If error rate > 10% or data loss detected
     Duration: 2 minutes
   ```

Exercise:
  1. Design 3 chaos experiments for the application
  2. Run one experiment in a staging environment
  3. Document what happened vs what you expected
  4. Fix any issues discovered
  5. Re-run the experiment to verify the fix

Assessment:
  "Design a chaos engineering program for a 3-service application.
   Include: 5 experiment hypotheses, prioritization by risk,
   safety controls, and a schedule for ongoing testing."
  Pass criteria: experiments are well-designed with clear hypotheses,
                 safety controls are adequate, prioritization reflects
                 actual business risk
```'''
    ),
    (
        "thinking/auto-curriculum-distributed-advanced",
        r'''Design advanced distributed systems modules covering event sourcing, CQRS, and designing for failure. These should be for experienced engineers ready for complex architectural patterns.''',
        r'''<think>
Advanced distributed systems patterns:
1. Event sourcing -- storing events instead of state
2. CQRS -- separating read and write models
3. Designing for failure -- making failure a first-class concern

These are patterns that experienced engineers need when building complex systems. The curriculum should emphasize when to use them (and when NOT to).
</think>

**Distributed Systems Curriculum: Advanced Patterns**

**Module 12: Event Sourcing (4 hours)**

```
Prerequisites: Modules 1-8

Learning objectives:
- Understand event sourcing vs traditional CRUD
- Implement an event-sourced system
- Build projections from event streams
- Handle event schema evolution

Content:
1. Event sourcing fundamentals:
   ```
   Traditional (state storage):
     UPDATE accounts SET balance = 950 WHERE id = 42;
     -- Previous balance is LOST

   Event sourcing (event storage):
     events = [
       {type: "AccountCreated", balance: 1000, timestamp: "T1"},
       {type: "MoneyDeposited", amount: 500, timestamp: "T2"},
       {type: "MoneyWithdrawn", amount: 200, timestamp: "T3"},
       {type: "MoneyWithdrawn", amount: 350, timestamp: "T4"},
     ]
     current_balance = replay(events)  # = 950
     -- Complete history preserved!
   ```

2. When event sourcing is appropriate:
   | Scenario | Event sourcing? | Why |
   |----------|----------------|-----|
   | Financial ledger | YES | Audit trail is required by law |
   | Shopping cart | NO | History is not valuable |
   | Version control (Git) | YES (it IS event sourcing) | History is the product |
   | User profile | NO | Only current state matters |
   | IoT sensor data | YES | Time-series analysis needs history |
   | Blog posts | NO | Overcomplicated for CRUD |

3. Projections (building views from events):
   ```
   Events:
     OrderPlaced{id: 1, items: [{sku: "A", qty: 2}], total: 50}
     OrderPlaced{id: 2, items: [{sku: "A", qty: 1}], total: 25}
     OrderShipped{id: 1}
     OrderPlaced{id: 3, items: [{sku: "B", qty: 3}], total: 90}

   Projection 1: "Orders by status"
     pending: [2, 3]
     shipped: [1]

   Projection 2: "Revenue by product"
     A: $75 (2*$25 + 1*$25)
     B: $90

   Projection 3: "Daily order count"
     2024-03-15: 3 orders, $165 total

   Each projection is built by replaying the same events
   through a different reducer function.
   ```

4. Event schema evolution:
   - What happens when you add a field to an event?
   - What happens when you rename a field?
   - Versioned events and upcasting strategies

Exercise:
  Build an event-sourced bank account:
  1. Store events (Created, Deposited, Withdrawn, Transferred)
  2. Replay events to compute current balance
  3. Build projections: balance history, monthly statements
  4. Add a new event type (InterestApplied) without breaking existing events

Assessment:
  "Implement an event-sourced inventory system. Events: ItemReceived,
   ItemSold, ItemReturned, InventoryAdjusted. Build projections for:
   current stock levels, sales history, and reorder alerts."
  Pass criteria: events are immutable, projections are built from
                 events, replay produces correct state
```

**Module 13: CQRS (Command Query Responsibility Segregation) (3 hours)**

```
Prerequisites: Module 12

Learning objectives:
- Separate read and write models
- Understand eventual consistency between command and query sides
- Combine CQRS with event sourcing
- Know when CQRS adds value vs unnecessary complexity

Content:
1. CQRS principle:
   ```
   Traditional:
     Same model for reads and writes.
     One database, one schema, one API.

   CQRS:
     Write side (commands): optimized for validation and consistency
     Read side (queries): optimized for display and reporting

     Command --> [Write Model] --> [Event Store]
                                        |
                                   [Projection]
                                        |
     Query  --> [Read Model]  <---------+
   ```

2. Why separate?
   - Reads and writes often have different requirements
   - Write model needs validation, business rules, consistency
   - Read model needs speed, denormalization, search
   - Optimizing one often hurts the other

3. Practical example:
   ```
   E-commerce product page:

   Write model (commands):
     CreateProduct(name, price, category, inventory)
     UpdatePrice(product_id, new_price)
     -> Validates business rules
     -> Stores normalized data
     -> Publishes events

   Read model (queries):
     ProductListView: denormalized, includes category name, review count
     ProductDetailView: includes related products, inventory status
     SearchView: full-text search index
     -> Each view is optimized for its specific query pattern
     -> Updated asynchronously from events
   ```

4. When CQRS is worth it:
   | Scenario | CQRS worth it? | Why |
   |----------|---------------|-----|
   | Read/write ratio > 100:1 | YES | Optimize reads independently |
   | Complex domain with many views | YES | Each view has different needs |
   | Simple CRUD app | NO | One model is sufficient |
   | Real-time analytics + transactions | YES | Different consistency needs |
   | Team < 5 developers | Usually NO | Complexity overhead too high |

Exercise:
  Implement CQRS for a task management system:
  1. Write side: commands for creating, assigning, completing tasks
  2. Read side: views for "my tasks," "team dashboard," "overdue tasks"
  3. Event-driven projection from write side to read side
  4. Demonstrate that the read side is eventually consistent

Assessment:
  "When would you recommend CQRS for a new project? Describe a
   scenario where it is clearly beneficial and one where it would
   be harmful. For the beneficial scenario, sketch the architecture."
  Pass criteria: correctly identifies appropriate and inappropriate
                 scenarios, architecture sketch is practical
```

**Module 14: Designing for Failure (3 hours)**

```
Prerequisites: All previous modules

Learning objectives:
- Design systems where failure is expected, not exceptional
- Implement graceful degradation
- Build self-healing systems
- Create runbooks for common failures

Content:
1. The failure-first mindset:
   ```
   Traditional: "Everything works. Handle errors as exceptions."
   Distributed: "Everything WILL fail. Design for it."

   Questions to ask for every component:
   - What happens when this fails?
   - How will we detect the failure?
   - How will the system recover?
   - What is the user experience during failure?
   ```

2. Graceful degradation patterns:
   ```
   Level 0: Complete failure (503 error page)
   Level 1: Core features work, extras disabled
   Level 2: All features work with stale data
   Level 3: Full functionality

   Example -- News website:
   Level 3: Live articles + personalized feed + ads + comments
   Level 2: Articles (cached) + generic feed + ads + comments disabled
   Level 1: Articles (cached) + static homepage
   Level 0: "We're experiencing issues" page
   ```

3. Self-healing patterns:
   - Auto-restart on crash (supervisor, K8s restart policy)
   - Circuit breaker with automatic recovery testing
   - Connection pool refresh on stale connection detection
   - Automatic failover to healthy replicas
   - Queue-based retry for failed operations

4. Runbooks:
   ```
   For each alert, create a runbook:

   Alert: "Payment service error rate > 5%"
   Runbook:
   1. Check payment service logs: kubectl logs -l app=payment
   2. If connection errors to Stripe:
      - Check Stripe status page
      - If Stripe is down: enable fallback payment processor
      - If not: check network/firewall rules
   3. If application errors:
      - Check recent deployments: git log --oneline -5
      - If recent deploy: rollback
      - If not: escalate to payment team
   4. If resolved: monitor for 30 minutes, close alert
   ```

Exercise:
  Design a failure-resilient architecture for a food delivery app:
  1. Map all components and their failure modes
  2. Define graceful degradation levels
  3. Implement self-healing for 3 failure scenarios
  4. Write runbooks for the 3 most critical alerts

Final capstone assessment:
  "Design a distributed system that processes 10,000 orders per
   minute across 3 geographic regions. Include:
   - Data partitioning strategy
   - Replication and consistency model
   - Transaction handling (saga pattern)
   - Observability and alerting
   - Graceful degradation plan
   - Chaos experiment design
   Present your design and defend your trade-off decisions."
  Pass criteria: design is coherent, trade-offs are explicitly
                 acknowledged, failure modes are addressed,
                 the system actually works under the stated load
```'''
    ),
    (
        "thinking/auto-curriculum-distributed-capstone",
        r'''Design a capstone project for the distributed systems curriculum that requires students to build, break, and fix a multi-service system. The project should test all skills from the curriculum.''',
        r'''<think>
A distributed systems capstone should:
1. Require building a multi-service system (not just one service)
2. Include intentional failure injection and recovery
3. Test both design skills and operational skills
4. Be complex enough to demonstrate mastery but completable in 2-3 weeks
5. Produce artifacts that demonstrate understanding (architecture docs, runbooks, chaos reports)
</think>

**Capstone Project: Build a Distributed Order Processing System**

**Project Overview**

```
Build a simplified distributed e-commerce order processing system
with 4 services:

1. API Gateway: Accepts HTTP requests, routes to services
2. Order Service: Creates and manages orders
3. Payment Service: Processes payments (simulated)
4. Inventory Service: Manages product stock

Requirements:
- Services communicate via HTTP (sync) and message queue (async)
- Data is partitioned across services (each owns its data)
- System must handle service failures gracefully
- System must be observable (metrics, logs, traces)
- System must be tested with chaos experiments
```

**Phase 1: Build (Week 1)**

```
Day 1-2: Service Implementation
  Build each service with its own database:

  Order Service:
    POST /orders -- create a new order
    GET /orders/:id -- get order status
    Database: orders table (id, customer, items, status, total)

  Payment Service:
    POST /payments -- process a payment
    GET /payments/:id -- get payment status
    Database: payments table (id, order_id, amount, status)
    Simulate: 5% random payment failures

  Inventory Service:
    POST /inventory/reserve -- reserve items for an order
    POST /inventory/release -- release reserved items
    GET /inventory/:sku -- check stock level
    Database: inventory table (sku, available, reserved)

  API Gateway:
    Routes requests to appropriate service
    Implements timeout and retry logic

Day 3: Implement the Order Saga
  Order creation flow (saga pattern):
    1. Create order (status: pending)
    2. Reserve inventory (sync call)
    3. Process payment (sync call)
    4. If payment succeeds: confirm order (status: confirmed)
    5. If payment fails: release inventory (compensation)
    6. Publish OrderConfirmed or OrderFailed event (async)

  Implement compensating actions for each failure point.

Day 4: Add Observability
  For each service:
    - Structured JSON logging with request_id
    - RED metrics (rate, errors, duration)
    - Request ID propagation between services
    - Health check endpoint

Day 5: Add Resilience Patterns
    - Circuit breaker on Payment Service calls
    - Timeout on all inter-service calls (3 second max)
    - Retry with exponential backoff for transient failures
    - Fallback: if Inventory Service is down, accept order
      provisionally and validate stock later
```

**Phase 2: Break (Week 2)**

```
Day 6-7: Design and Run Chaos Experiments

  Experiment 1: Payment Service Crash
    Hypothesis: Orders are not lost when Payment Service crashes.
    Method: Kill Payment Service during order processing.
    Expected: Order stays in "pending" state, can be retried.
    Verify: No orders are stuck in inconsistent state.

  Experiment 2: Network Partition
    Hypothesis: API Gateway handles Inventory Service unreachable.
    Method: Block network between API Gateway and Inventory Service.
    Expected: Orders accepted provisionally with warning.
    Verify: When partition heals, inventory is validated.

  Experiment 3: Slow Dependency
    Hypothesis: System remains responsive when Payment is slow.
    Method: Add 10-second delay to Payment Service responses.
    Expected: Circuit breaker opens after 5 failures.
    Verify: Other orders are not affected by the slow service.

  Experiment 4: Message Queue Failure
    Hypothesis: Events are not lost when message queue is down.
    Method: Stop the message queue for 5 minutes.
    Expected: Events are retried when queue recovers.
    Verify: All OrderConfirmed events are eventually delivered.

  Experiment 5: Data Inconsistency
    Hypothesis: System detects and repairs inconsistent state.
    Method: Directly modify inventory database to create mismatch.
    Expected: Reconciliation job detects and reports the mismatch.
    Verify: Alert is triggered, data can be corrected.

Day 8: Fix Issues Found
  For each experiment that revealed a problem:
  1. Document the failure mode
  2. Implement a fix
  3. Re-run the experiment to verify
  4. Add monitoring to detect this failure in production
```

**Phase 3: Operate (Week 3)**

```
Day 9: Write Operational Documentation
  Deliverables:
  1. Architecture document:
     - Service diagram with communication patterns
     - Data ownership and consistency model
     - Saga flow diagram with compensation paths

  2. Runbooks for top 5 alerts:
     - Payment Service error rate > 10%
     - Order stuck in pending > 5 minutes
     - Inventory mismatch detected
     - Message queue backlog > 1000
     - Service health check failing

  3. Incident response procedure:
     - How to diagnose a problem using observability tools
     - How to perform emergency rollback
     - Escalation paths

Day 10: Load Test and Present
  1. Load test: process 100 orders per second for 10 minutes
     Record: success rate, latency percentiles, error rate
     Identify: bottleneck service and scaling strategy

  2. Final presentation:
     - Architecture decisions and trade-offs
     - Consistency model and why you chose it
     - Chaos experiment results
     - What would you change with more time?
     - How would you scale to 10x traffic?
```

**Grading Rubric**

```
System Design (25%)
  - Services have clear ownership boundaries
  - Saga pattern correctly implements compensation
  - Consistency model is appropriate and documented
  - Communication patterns (sync vs async) are justified

Resilience (25%)
  - Circuit breaker works correctly
  - Timeout and retry logic handles all failure modes
  - Graceful degradation when services are unavailable
  - No data loss or corruption during failures

Observability (20%)
  - Request tracing works across all services
  - Metrics capture RED signals
  - Structured logging with correlation IDs
  - Dashboards show system health at a glance

Chaos Engineering (15%)
  - Experiments have clear hypotheses
  - At least 4 experiments executed
  - Issues found are documented and fixed
  - Re-run confirms fixes work

Operations (15%)
  - Architecture document is clear and accurate
  - Runbooks are actionable
  - Load test identifies real bottleneck
  - Scaling strategy is reasonable

Bonus:
  - Implemented event sourcing for order state
  - Added distributed tracing (OpenTelemetry)
  - Implemented CQRS for order queries vs commands
  - Load test sustained 500+ orders/second
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
