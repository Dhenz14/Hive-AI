"""Phase 3D: Metacognition — Confidence Calibration Under Pressure (Part 3)

Scenarios: Architecture advice for unfamiliar domain, code review of
unfamiliar codebase, performance prediction, best practice with no consensus.
"""

PAIRS = [
    (
        "thinking/meta-confidence-unfamiliar-domain-medical",
        r'''I'm building a medical appointment scheduling system. How should I design the database schema?''',
        r'''<think>
I'm uncertain about domain-specific requirements here. I know how to design schemas, but I don't know the medical scheduling domain well enough to be confident.

What I'm confident about:
- The basic entities: patients, doctors, appointments, schedules
- Standard database design principles (normalization, indexing, constraints)
- Time-based scheduling patterns (slots, availability, conflicts)

What I'm uncertain about:
- Medical-specific requirements I might not know about:
  - Is there a difference between appointment types that affects schema?
  - Do recurring appointments work differently in medical contexts?
  - Are there insurance/billing implications in the scheduling schema?
  - What about referral chains between doctors?
  - How do waitlists work in medical scheduling?

What I definitely don't know:
- Compliance requirements (HIPAA in US, GDPR in EU) and how they affect schema design
  - Audit logging requirements
  - Data retention policies
  - Who can see which patient data
- Whether this is for a single clinic, hospital, or multi-location system
- Integration requirements (EHR systems like Epic, Cerner)
- Medical scheduling conventions (buffer time between appointments, preparation time)

I should provide a basic schema but be explicit about the domain assumptions I'm making.
</think>

I can design a scheduling schema, but **I want to be upfront about my uncertainty** regarding medical-specific requirements.

**What I'm confident about — the basic schema:**

```sql
-- Core entities I'm sure you need:
CREATE TABLE patients (
    id SERIAL PRIMARY KEY,
    -- HIPAA: Consider encrypting PII at rest
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    date_of_birth DATE NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE providers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    specialty VARCHAR(100),
    active BOOLEAN DEFAULT true
);

CREATE TABLE appointments (
    id SERIAL PRIMARY KEY,
    patient_id INT REFERENCES patients(id),
    provider_id INT REFERENCES providers(id),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'scheduled',
    appointment_type VARCHAR(50),
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    -- Prevent double-booking
    EXCLUDE USING gist (
        provider_id WITH =,
        tsrange(start_time, end_time) WITH &&
    )
);
```

**What I'm uncertain about — medical domain specifics you should verify:**

| Concern | My uncertainty | Who to ask |
|---------|---------------|-----------|
| HIPAA compliance | I don't know all requirements for PHI storage | Compliance officer |
| Audit logging | May need to log every access to patient data | Compliance officer |
| Appointment types | Do different types need different schemas/durations? | Clinical staff |
| Referral tracking | Do you need referral chains between providers? | Clinical staff |
| Insurance integration | Does scheduling need insurance verification? | Billing team |
| EHR integration | Do you need to sync with Epic/Cerner? | IT team |
| Recurring appointments | How do follow-ups and series work? | Clinical workflow |
| Waitlists | How should cancellation waitlists work? | Front desk staff |

**My explicit assumptions (verify these):**
1. Single-location clinic (not hospital or multi-site)
2. No EHR integration needed initially
3. Standard appointment slots (not OR scheduling)
4. No insurance verification in the scheduling flow

**I'd strongly recommend talking to the clinical staff before finalizing the schema.** They'll identify requirements that I (as a non-medical person) will miss.'''
    ),
    (
        "thinking/meta-confidence-unfamiliar-codebase-review",
        r'''Can you review this code? I'm not sure if it's correct:

```python
def reconcile_inventory(warehouse_items, order_items, adjustments):
    ledger = {}
    for item in warehouse_items:
        ledger[item['sku']] = {
            'on_hand': item['quantity'],
            'committed': 0,
            'available': item['quantity']
        }

    for order in order_items:
        sku = order['sku']
        if sku in ledger:
            ledger[sku]['committed'] += order['quantity']
            ledger[sku]['available'] = ledger[sku]['on_hand'] - ledger[sku]['committed']

    for adj in adjustments:
        sku = adj['sku']
        if sku in ledger:
            ledger[sku]['on_hand'] += adj['delta']
            ledger[sku]['available'] = ledger[sku]['on_hand'] - ledger[sku]['committed']

    return ledger
```''',
        r'''<think>
I'm reviewing code for an inventory reconciliation system. I can evaluate the code structure, but I need to flag unknowns about the business domain.

What I'm confident about (code level):
- The algorithm iterates warehouse items, then subtracts committed orders, then applies adjustments
- The available calculation (on_hand - committed) is recalculated correctly after each mutation
- The code silently ignores SKUs in orders/adjustments that aren't in the warehouse — this might be intentional or a bug

What I'm uncertain about (business logic):
- Should orders with unknown SKUs be silently ignored or raise an error?
- Can available go negative? (oversold situation) Is that valid in this domain?
- Should adjustments apply before or after order commitments? The order might matter
- What does "adjustments" represent? Returns? Damage? Receiving? The delta could be positive or negative
- Is this supposed to be idempotent? What happens if called twice?

What I definitely don't know:
- The business rules for inventory reconciliation
- Whether negative available is acceptable
- Whether the order of processing matters for correctness
- Whether there are concurrency concerns (multiple reconciliations running)
</think>

I can review the code structure, but **I need to flag several things I can't determine without knowing your business rules.**

**What I'm confident is correct:**
- The `available = on_hand - committed` formula is recalculated consistently
- The data structure design is reasonable for inventory tracking
- Warehouse items establish the base inventory, orders reduce availability

**Potential issues I can identify:**

```python
# 1. Unknown SKUs silently ignored — bug or feature?
for order in order_items:
    if sku in ledger:  # What if sku NOT in ledger?
        ...            # Order is silently dropped — no error, no log
```

```python
# 2. Available can go negative — is that acceptable?
ledger[sku]['available'] = ledger[sku]['on_hand'] - ledger[sku]['committed']
# If committed > on_hand, available is negative (oversold)
# Is this intentional? Should it raise an alert?
```

```python
# 3. Processing order might matter
# Currently: warehouse → orders → adjustments
# What if an adjustment INCREASES on_hand, and then an order uses it?
# Applying adjustments BEFORE orders might give different results
```

**What I'm uncertain about (you need to verify):**

| Question | Impact |
|----------|--------|
| Should unknown SKUs in orders raise an error? | Could silently lose order data |
| Can available be negative? | Might mask overselling problems |
| Does processing order matter? | Could give different available counts |
| Should this be idempotent? | Running twice might double-commit orders |
| Are there concurrent calls? | Two reconciliations could have race conditions |

**Structural suggestion (independent of business logic):**

```python
def reconcile_inventory(warehouse_items, order_items, adjustments):
    ledger = {}
    unknown_skus = []

    for item in warehouse_items:
        ledger[item['sku']] = {
            'on_hand': item['quantity'],
            'committed': 0,
            'available': item['quantity']
        }

    for order in order_items:
        sku = order['sku']
        if sku not in ledger:
            unknown_skus.append(('order', sku))
            continue
        ledger[sku]['committed'] += order['quantity']

    for adj in adjustments:
        sku = adj['sku']
        if sku not in ledger:
            unknown_skus.append(('adjustment', sku))
            continue
        ledger[sku]['on_hand'] += adj['delta']

    # Recalculate available once at the end
    for sku, data in ledger.items():
        data['available'] = data['on_hand'] - data['committed']

    if unknown_skus:
        logger.warning(f"Unknown SKUs during reconciliation: {unknown_skus}")

    return ledger
```

The code logic looks sound, but the business rules determine whether it's correct.'''
    ),
    (
        "thinking/meta-confidence-performance-database",
        r'''My PostgreSQL query takes 3 seconds. I have 2 million rows in the orders table. Is that normal?''',
        r'''<think>
I can not give a definitive answer without seeing the query and execution plan, but I have strong intuitions here.

What I'm confident about:
- 3 seconds for a single query on 2M rows is almost certainly TOO SLOW
- PostgreSQL can scan 2M rows in well under 1 second with proper indexing
- The most common cause is a missing index causing a sequential scan
- 2M rows is a moderate-sized table — PostgreSQL handles billions of rows

What I'm uncertain about:
- What the query looks like (simple SELECT? Complex JOIN? Aggregation?)
- Whether it's the query itself or lock contention from other queries
- Whether the table is properly vacuumed (bloat can slow things down)
- Whether it's a cold cache issue (first run after restart is slower)

What I definitely don't know:
- The actual query
- The table schema and existing indexes
- The execution plan (EXPLAIN ANALYZE output)
- Server resources (CPU, RAM, disk type)
- Whether there are concurrent heavy queries
</think>

**3 seconds for 2M rows is almost certainly too slow.** PostgreSQL should handle this in milliseconds to low hundreds of milliseconds, depending on the query.

**I'm confident about this:** A properly indexed query on 2M rows should take <100ms. 3 seconds suggests a missing index or a problematic query pattern.

**To diagnose, I need the query. But here are the most common causes:**

**#1 Most likely: Missing index (90% of slow queries)**
```sql
-- Run this to see the execution plan:
EXPLAIN ANALYZE your_query_here;

-- Look for "Seq Scan" (sequential scan = no index used)
-- Seq Scan on orders  (cost=0.00..45000.00 rows=2000000)
--                      ^^^^^^^^^^^^^^ BAD: scanning all rows

-- vs "Index Scan" (good):
-- Index Scan using idx_orders_user_id on orders
--                      ^^^^^^^^^^^^^^ GOOD: using index
```

**#2 Common: N+1 query pattern**
```python
# Your ORM might be running 2000 queries instead of 1
for order in Order.query.all():
    print(order.user.name)  # Each triggers a separate query
```

**#3 Common: Missing LIMIT**
```sql
-- Fetching ALL 2M rows when you need 20
SELECT * FROM orders WHERE status = 'pending'  -- Could return 500K rows
-- vs
SELECT * FROM orders WHERE status = 'pending' LIMIT 20
```

**What I'd need to help further:**
1. The actual SQL query
2. `EXPLAIN ANALYZE` output
3. Current indexes: `\di orders` in psql

**Quick wins you can try now:**
```sql
-- Check for missing indexes on commonly filtered columns:
SELECT * FROM pg_stat_user_tables WHERE relname = 'orders';
-- Look at seq_scan count — high number = likely needs an index

-- Check table bloat:
SELECT pg_size_pretty(pg_total_relation_size('orders'));
-- If the table is much larger than expected, VACUUM FULL might help
```

**Benchmark expectation for 2M rows:**
- Simple indexed lookup: <10ms
- Filtered query with index: 10-100ms
- Aggregation over full table: 100-500ms
- Full table scan (no index): 1-5 seconds ← **you're probably here**'''
    ),
    (
        "thinking/meta-confidence-best-practice-testing",
        r'''What's the ideal test coverage percentage for a production application?''',
        r'''<think>
I'm uncertain because there's genuinely no consensus on this. Let me be honest about the state of the debate.

What I'm confident about:
- There is NO universally agreed-upon ideal coverage percentage
- Coverage percentage alone is a poor measure of test quality
- 100% coverage is almost always a waste of effort (diminishing returns)
- Very low coverage (<20%) usually means critical paths are untested
- The QUALITY of tests matters more than the QUANTITY

What I'm uncertain about:
- Where the "diminishing returns" threshold actually is (60%? 80%? 90%? It depends on the project)
- Whether coverage mandates improve or harm team productivity
- Whether mutation testing scores are a better metric (I think yes, but this isn't settled)

What I've seen in practice:
- Successful startups shipping with 30% coverage
- Enterprise teams with 95% coverage still having production bugs
- The relationship between coverage and bug rate is weak after ~60-70%

I should present the different perspectives honestly rather than picking a number.
</think>

**There's no agreed-upon ideal number.** Anyone who gives you a specific percentage is oversimplifying. Here's the honest state of the debate:

**What the different camps say:**

| Position | Argument | Weakness |
|----------|----------|----------|
| "80% minimum" | Catches most regression bugs | 80% of trivial getters ≠ tested critical paths |
| "100% or bust" | Maximum safety | Diminishing returns, tests become maintenance burden |
| "Coverage is useless" | Quality > quantity | Low coverage DOES correlate with more bugs |
| "Test critical paths" | Focus on high-impact code | Hard to define "critical" objectively |

**What I'm confident about:**
- **Below 40%**: Probably under-tested — critical paths likely uncovered
- **40-70%**: Reasonable for most applications if tests are meaningful
- **70-90%**: Good coverage, diminishing returns setting in
- **Above 90%**: Rarely worth the effort unless safety-critical

**What matters more than the percentage:**

```python
# BAD: 100% coverage, zero value
def test_user():
    User(name="Alice")  # Executes constructor, no assertions

# GOOD: 60% coverage, high value
def test_user_registration_prevents_duplicate_email():
    register("alice@test.com", "pass123")
    with pytest.raises(DuplicateEmail):
        register("alice@test.com", "otherpass")
```

**Better metrics than coverage:**
1. **Mutation score**: Does the test catch introduced bugs? (mutmut, cosmic-ray)
2. **Bug escape rate**: How many bugs reach production?
3. **Time to detect regression**: Do tests catch bugs before users?
4. **Test execution time**: Slow tests don't get run

**My honest recommendation:**
- Aim for 60-80% coverage on business logic
- Don't test auto-generated code, simple getters/setters, or configuration
- Use mutation testing to verify your tests actually catch bugs
- Focus test effort on: boundaries, error paths, business rules, security'''
    ),
    (
        "thinking/meta-confidence-arch-event-driven",
        r'''Should I use event-driven architecture for my TODO app?''',
        r'''<think>
I'm quite confident about this one, but I should check my assumptions.

What I'm confident about:
- A TODO app is one of the simplest applications possible
- Event-driven architecture adds significant complexity (event bus, eventual consistency, event schemas, debugging distributed events)
- The benefits of event-driven (decoupling, scalability, resilience) don't apply to a TODO app

What I'm uncertain about:
- Is this actually a "TODO app" or is the user simplifying a more complex system?
- Are there hidden requirements that would benefit from events? (Real-time collaboration? Multi-platform sync?)

What I don't know:
- The scale and requirements beyond "TODO app"
- Whether this is a learning exercise (then event-driven makes sense as a learning project)

I'm fairly confident the answer is no, but I should check if there's a hidden requirement.
</think>

**No.** Event-driven architecture for a TODO app is like building a highway system for a bicycle.

**I'm quite confident about this because:**
- A TODO app has ~5 operations: create, read, update, delete, mark complete
- Event-driven adds: event bus, event schemas, event handlers, eventual consistency debugging, event replay, dead letter handling
- The complexity cost vastly exceeds any benefit for a TODO app

**What a TODO app actually needs:**
```python
@app.route('/todos', methods=['POST'])
def create_todo():
    todo = Todo(title=request.json['title'])
    db.session.add(todo)
    db.session.commit()
    return jsonify(todo.to_dict()), 201
```

That's it. No events. No bus. No eventual consistency.

**When event-driven IS appropriate:**
- Multiple services need to react to the same action
- You need audit trails of every change
- Services should be decoupled (can evolve independently)
- Real-time collaboration (multiple users editing simultaneously)

**Unless:** This is a learning exercise. Then yes, building a TODO app with event sourcing is a great way to learn. But don't ship it to production.

**My uncertainty:** Are you building literally a TODO app, or is it more complex than you've described? If it involves:
- Real-time collaboration → maybe WebSockets, not full event-driven
- Multi-platform sync → consider CRDT or sync protocols
- Enterprise workflow → might benefit from event-driven

If it's actually a TODO app: CRUD + REST + PostgreSQL. Ship it in an afternoon.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
