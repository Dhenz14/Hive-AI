"""Phase 2C: Advanced Reasoning — Analogical Reasoning (Part 4/5)
Map concepts between domains, note where the analogy breaks:
state machine↔vending machine, dependency injection↔hiring contractors,
event loop↔restaurant waiter, database transaction↔bank transfer,
CAP theorem↔project management triangle."""

PAIRS = [
    (
        "thinking/analogy-statemachine-vending",
        "I need to model a complex workflow with many states and transitions. My code is a mess of if/else chains. What's a better approach?",
        r'''<think>
Let me map state machines to vending machines — it's an almost perfect analogy.

A vending machine has:
- States: idle, accepting_money, item_selected, dispensing, returning_change
- Transitions: insert_coin, select_item, dispense, return_change
- Rules: can't dispense without payment, can't select without being in accepting_money state
- Each button press (event) causes a specific transition from one state to another

This maps directly to software workflows:
- States: the current step in the workflow
- Transitions: events/actions that move between steps
- Rules: which transitions are valid from each state
- Invalid transitions are rejected (can't go from "shipped" to "created")

The key insight from the vending machine:
1. The machine doesn't have if/else for every combination — it has a STATE TABLE
2. Given current state + input → next state + action
3. This is a lookup, not a chain of conditions

Where the analogy extends well:
- A vending machine jammed (stuck in a state) = a workflow stuck in processing
- Adding a new drink option = adding a new transition
- The display showing "INSERT COIN" = the current state visible to the user

Where the analogy breaks:
1. Vending machines are sequential (one customer at a time). Software state machines can handle concurrent instances (1000 orders each in their own state).
2. Vending machines don't have history. State machines can log every transition.
3. Vending machines have one path. State machines can have parallel states (order is "being packed" AND "payment processing" simultaneously).

Let me show the code transformation.
</think>

Your if/else workflow is like a vending machine where every button has its own giant function checking "what was the last button pressed?" A state machine replaces that chaos with a simple table.

**The vending machine analogy:**

```
Vending Machine:                    Your Workflow:
┌─────────┐ insert coin  ┌────────┐    ┌─────────┐ submit   ┌──────────┐
│  IDLE   │────────────→│ACCEPTING│    │ DRAFT   │─────────→│ PENDING  │
└─────────┘              └────────┘    └─────────┘          └──────────┘
                           │ select                            │ approve
                           ▼                                   ▼
                        ┌────────┐                          ┌──────────┐
                        │DISPENSE│                          │ APPROVED │
                        └────────┘                          └──────────┘

Rules: Can't dispense from IDLE     Rules: Can't approve from DRAFT
       Can't insert coin while             Can't submit from APPROVED
       dispensing                           Can only reject from PENDING
```

**Your code now (the mess):**

```python
# if/else spaghetti — every method checks every possible state
def approve_order(order):
    if order.status == "pending":
        if order.payment_status == "verified":
            if order.items_in_stock:
                order.status = "approved"
            else:
                order.status = "backorder"
        else:
            raise ValueError("Payment not verified")
    elif order.status == "draft":
        raise ValueError("Can't approve a draft")
    elif order.status == "approved":
        raise ValueError("Already approved")
    elif order.status == "shipped":
        raise ValueError("Already shipped")
    # ... 20 more elif branches
```

**State machine approach:**

```python
from enum import Enum
from typing import Callable

class OrderStatus(Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

# The state table — ALL valid transitions in one place
TRANSITIONS: dict[tuple[OrderStatus, str], OrderStatus] = {
    # (current_state, event) → next_state
    (OrderStatus.DRAFT, "submit"):       OrderStatus.PENDING,
    (OrderStatus.PENDING, "approve"):    OrderStatus.APPROVED,
    (OrderStatus.PENDING, "reject"):     OrderStatus.REJECTED,
    (OrderStatus.APPROVED, "ship"):      OrderStatus.SHIPPED,
    (OrderStatus.SHIPPED, "deliver"):    OrderStatus.DELIVERED,
    # Cancel is allowed from multiple states
    (OrderStatus.DRAFT, "cancel"):       OrderStatus.CANCELLED,
    (OrderStatus.PENDING, "cancel"):     OrderStatus.CANCELLED,
    (OrderStatus.APPROVED, "cancel"):    OrderStatus.CANCELLED,
}

class OrderStateMachine:
    def __init__(self, order):
        self.order = order

    def transition(self, event: str) -> OrderStatus:
        current = OrderStatus(self.order.status)
        key = (current, event)

        if key not in TRANSITIONS:
            valid_events = [e for (s, e) in TRANSITIONS if s == current]
            raise ValueError(
                f"Cannot '{event}' order in '{current.value}' state. "
                f"Valid actions: {valid_events}"
            )

        new_status = TRANSITIONS[key]
        self.order.status = new_status.value
        return new_status

# Usage — clean, predictable, impossible to reach invalid states
sm = OrderStateMachine(order)
sm.transition("submit")   # draft → pending ✓
sm.transition("approve")  # pending → approved ✓
sm.transition("submit")   # approved → ??? → ValueError!
#   "Cannot 'submit' order in 'approved' state. Valid actions: ['ship', 'cancel']"
```

**Add transition side effects (guards and actions):**

```python
# Optional: run code on specific transitions
TRANSITION_ACTIONS = {
    (OrderStatus.PENDING, "approve"): lambda order: send_approval_email(order),
    (OrderStatus.APPROVED, "ship"): lambda order: notify_warehouse(order),
    (OrderStatus.SHIPPED, "deliver"): lambda order: send_delivery_confirmation(order),
}

TRANSITION_GUARDS = {
    (OrderStatus.PENDING, "approve"): lambda order: order.payment_verified,
    (OrderStatus.APPROVED, "ship"): lambda order: order.items_in_stock,
}

def transition(self, event: str):
    current = OrderStatus(self.order.status)
    key = (current, event)

    if key not in TRANSITIONS:
        raise ValueError(...)

    # Check guard condition
    guard = TRANSITION_GUARDS.get(key)
    if guard and not guard(self.order):
        raise ValueError(f"Guard failed for {event}")

    new_status = TRANSITIONS[key]
    self.order.status = new_status.value

    # Run side effect
    action = TRANSITION_ACTIONS.get(key)
    if action:
        action(self.order)

    return new_status
```

**Where the analogy breaks:**
1. A vending machine handles one transaction at a time. Your system has 10,000 orders each in their own state simultaneously.
2. Vending machines don't have parallel states. A real workflow might need: "order is being packed AND payment is being processed" (use a state machine per concern, or a state chart library).
3. Adding a new drink is easy. Adding a new status to a production system requires a database migration.

State machines turn complex workflow logic from scattered if/else into a single, reviewable transition table.'''
    ),
    (
        "thinking/analogy-eventloop-waiter",
        "I don't understand async/await. How can my code do multiple things at once if Python only has one thread?",
        r'''<think>
The restaurant waiter analogy is perfect for event loops and async/await.

Synchronous (blocking) code ↔ One waiter per table:
- Waiter takes order at table 1
- Goes to kitchen, STANDS THERE waiting for food
- While waiting, tables 2, 3, 4, 5 are all unserved
- Food arrives, brings it to table 1
- NOW goes to table 2
- Terrible throughput — 5 tables but serving one at a time

This is how synchronous I/O works:
```python
data = requests.get(url)  # Thread BLOCKS here waiting for network
# Nothing else happens during the wait (seconds of wasted time)
```

Async (non-blocking) code ↔ One efficient waiter:
- Takes order at table 1 → sends to kitchen
- Doesn't wait! Goes to table 2 → takes order → sends to kitchen
- Goes to table 3 → takes order → sends to kitchen
- Kitchen bell rings: "Table 1 food ready!"
- Delivers food to table 1
- Kitchen bell rings: "Table 3 food ready!"
- Delivers food to table 3
- One waiter, multiple tables, nobody waits for food unnecessarily

This is how async I/O works:
```python
data = await httpx.get(url)  # "Send order to kitchen, go serve other tables"
# While waiting for network, other async tasks can run
```

The key insight:
- The waiter doesn't CLONE themselves (that's multi-threading)
- There's still only ONE waiter (one thread)
- The waiter is just SMART about not standing idle when waiting for the kitchen
- The kitchen (network, disk, database) does the actual work
- The waiter just coordinates

What 'await' means:
- "I'm waiting for the kitchen, go help other tables"
- The event loop (the waiter's brain) remembers all pending orders
- When a result comes back, it resumes the task that was waiting

What ISN'T async:
- CPU-heavy work (chopping vegetables) — the waiter IS doing work, can't serve tables
- This is like a function doing heavy computation — it blocks the event loop
- For CPU work, you need actual multiple workers (threads/processes)

Where the analogy breaks:
1. A waiter has physical constraints (can only carry so many plates). An event loop can handle thousands of concurrent connections.
2. A waiter makes decisions about priority. An event loop is FIFO (unless you use priority queues).
3. Kitchen responses in real life are unpredictable. Network responses have more consistent patterns.
</think>

Think of Python's async as a single waiter serving multiple tables — not by cloning themselves, but by never standing around idle.

**Synchronous = one waiter who waits at the kitchen:**

```python
# Each request BLOCKS until response arrives
# The thread just... stands there. Doing nothing.

def handle_requests():
    r1 = requests.get("https://api.users.com/1")    # Wait 200ms...
    r2 = requests.get("https://api.orders.com/1")    # Wait 200ms...
    r3 = requests.get("https://api.products.com/1")  # Wait 200ms...
    return combine(r1, r2, r3)
    # Total: 600ms (sequential — waiter stands at kitchen each time)

# Like:
# Waiter → takes order table 1 → goes to kitchen → STANDS THERE 200ms
#        → brings food → takes order table 2 → kitchen → STANDS THERE 200ms
#        → brings food → takes order table 3 → kitchen → STANDS THERE 200ms
# Total: 600ms for 3 tables
```

**Async = one waiter who multitasks:**

```python
import asyncio
import httpx

async def handle_requests():
    async with httpx.AsyncClient() as client:
        # Send ALL requests to the kitchen at once
        r1, r2, r3 = await asyncio.gather(
            client.get("https://api.users.com/1"),     # "Kitchen, table 1 order!"
            client.get("https://api.orders.com/1"),     # "Kitchen, table 2 order!"
            client.get("https://api.products.com/1"),   # "Kitchen, table 3 order!"
        )
    return combine(r1, r2, r3)
    # Total: 200ms (parallel — waiter sends all orders, then delivers as ready)

# Like:
# Waiter → table 1 order → kitchen!
#        → table 2 order → kitchen!
#        → table 3 order → kitchen!
#        → kitchen bell! table 2 ready → deliver
#        → kitchen bell! table 1 ready → deliver
#        → kitchen bell! table 3 ready → deliver
# Total: 200ms for 3 tables (max of the three waits)
```

**What `await` actually means:**

```python
async def serve_table(table_number):
    print(f"Taking order from table {table_number}")

    order = await kitchen.prepare(table_number)
    # ↑ "await" = "I'm waiting for the kitchen.
    #              Dear event loop, go serve other tables.
    #              Come back to me when the food is ready."

    print(f"Delivering food to table {table_number}")
    return order

# The event loop is the waiter's BRAIN:
# It remembers: "Table 1 is waiting for food, Table 3 is waiting for food"
# When food arrives: "Ah, Table 3 food is ready! Resume serving Table 3."
```

**When async helps vs. doesn't:**

```python
# ✅ ASYNC HELPS: I/O-bound work (waiting for network, DB, files)
# The waiter is WAITING, not working → can serve other tables
async def fetch_user(user_id):
    return await db.fetch_one("SELECT * FROM users WHERE id=$1", user_id)
    # While waiting for DB response, other requests are served

# ❌ ASYNC DOESN'T HELP: CPU-bound work (computing, not waiting)
# The waiter is CHOPPING VEGETABLES → can't leave the kitchen
async def compute_report(data):
    result = heavy_number_crunching(data)  # No await — this BLOCKS!
    # While crunching, NO other requests are served (waiter is busy)
    # For CPU work, use multiprocessing instead:
    result = await asyncio.to_thread(heavy_number_crunching, data)
```

**Real-world FastAPI example:**

```python
# FastAPI handles each request as an async task (like tables in a restaurant)
# One worker thread can handle 1000+ concurrent requests if they're I/O-bound

@app.get("/dashboard/{user_id}")
async def get_dashboard(user_id: int):
    # All three queries run concurrently — like ordering for 3 tables at once
    user, orders, notifications = await asyncio.gather(
        get_user(user_id),          # DB query ~50ms
        get_recent_orders(user_id),  # DB query ~100ms
        get_notifications(user_id),  # Redis query ~10ms
    )
    # Total: ~100ms (max of the three) instead of 160ms (sum of the three)
    return {"user": user, "orders": orders, "notifications": notifications}
```

**Where the analogy breaks:**
1. A waiter has a physical limit (maybe 10 tables). An event loop can handle 10,000+ concurrent connections.
2. In a restaurant, food preparation takes variable time. In code, you can set timeouts: "if the kitchen takes more than 30 seconds, give up."
3. A waiter works in a single restaurant. An event loop can "serve tables" across multiple "restaurants" (multiple I/O sources simultaneously).

The one-line summary: `async/await` doesn't make things run simultaneously — it makes your code not waste time sitting idle while waiting for I/O.'''
    ),
    (
        "thinking/analogy-cap-theorem-triangle",
        "Someone mentioned the CAP theorem in a meeting about our database choice. I know it involves consistency, availability, and partition tolerance, but I don't really understand what it means practically.",
        r'''<think>
Let me map CAP theorem to the project management triangle (fast, cheap, good — pick two) because it has the same structure and is more intuitive.

Project management triangle:
- Good quality
- Fast delivery
- Low cost
- Pick two. You can't have all three.
  - Good + Fast = Expensive
  - Good + Cheap = Slow
  - Fast + Cheap = Poor quality

CAP theorem:
- Consistency: every read gets the most recent write
- Availability: every request gets a response (no errors)
- Partition tolerance: system works even when network splits
- Pick two... sort of.

Actually, let me be more precise. The CAP theorem says:
When a network partition occurs (and it WILL in distributed systems), you must choose between Consistency and Availability.

So it's really: during a network partition, do you:
- Stay Consistent (refuse to respond if you can't guarantee latest data) = CP
- Stay Available (respond with potentially stale data) = AP

Let me make this concrete with a real scenario:

Imagine a bank with two branches (two database nodes):
- Branch A in New York
- Branch B in London
- They replicate data between them

Normal operation: Alice deposits $100 at Branch A. Branch A tells Branch B. Both show $100. Everything works.

Network partition: The undersea cable between NY and London breaks.

Now Alice's account shows $100 at Branch A.
Branch B still shows $0 (hasn't received the update).
Alice walks into Branch B and asks her balance.

CP choice (consistency): "Sorry, we can't serve you right now because we're not sure we have the latest data. Come back when the network is fixed."
- Pro: Alice never sees wrong data
- Con: Alice is denied service

AP choice (availability): "Your balance is $0" (stale but we respond!)
- Pro: Alice gets a response
- Con: Alice sees wrong data, might overdraw

The bank analogy maps perfectly:
- Consistency = "We'd rather say 'out of service' than give you wrong information"
- Availability = "We'll always give you an answer, even if it might be slightly out of date"
- Partition = "The branches can't communicate"

Where the analogy breaks:
1. In banking, showing wrong balance is VERY bad (financial liability). In social media, showing a post count as 999 instead of 1000 is fine.
2. Real partitions are more nuanced — partial partitions, intermittent connectivity.
3. "Pick two" is oversimplified. In practice, you tune the trade-off per operation (strong consistency for payments, eventual consistency for likes).
</think>

Think of CAP like the project management triangle — "fast, cheap, good: pick two" — but for distributed databases.

**The project management version you already know:**

```
        Good
       / \
      /   \
    Fast ── Cheap

Pick two:
  Good + Fast  = Expensive (hire more people)
  Good + Cheap = Slow (take your time)
  Fast + Cheap = Low quality (cut corners)
```

**The CAP theorem version:**

```
     Consistent
       / \
      /   \
Available ── Partition Tolerant

When a network partition happens, pick one:
  Consistent + Partition Tolerant (CP) = Sometimes unavailable
  Available + Partition Tolerant (AP)  = Sometimes stale data
```

**Made real with a bank analogy:**

```
Two bank branches: New York and London
Both have a copy of your account: Balance = $1000

Normal day: You deposit $500 in NY → NY tells London → Both show $1500 ✓

Then the undersea cable breaks (network partition):
NY knows balance = $1500
London still shows = $1000

You walk into the London branch. What happens?

CP (Consistent): "Sorry, our systems are temporarily unavailable.
                  We can't confirm your balance right now."
  → You're denied service, but you'll never see wrong data.
  → Example: Traditional banks, PostgreSQL (single node)

AP (Available):  "Your balance is $1000."
                  (Stale! Missing the $500 deposit)
  → You get an answer, but it might be wrong.
  → Example: Social media feeds, DynamoDB, Cassandra
```

**What this means for database choices:**

```
CP systems (choose consistency):
┌──────────────────────────────────────────────────┐
│ PostgreSQL, MySQL, MongoDB (default), Redis      │
│                                                  │
│ "If I can't guarantee correct data, I'll refuse" │
│                                                  │
│ Good for: Financial transactions, inventory,     │
│           anything where wrong data = money lost │
└──────────────────────────────────────────────────┘

AP systems (choose availability):
┌──────────────────────────────────────────────────┐
│ Cassandra, DynamoDB, CouchDB, Redis Cluster      │
│                                                  │
│ "I'll always respond, but data might be stale"   │
│                                                  │
│ Good for: Social feeds, analytics, caching,      │
│           anything where slightly old data is OK │
└──────────────────────────────────────────────────┘
```

**Practical implications for your system:**

```python
# You don't choose CP or AP for your ENTIRE system.
# You choose PER OPERATION.

# Payment processing → MUST be consistent (CP)
async def process_payment(order_id, amount):
    # Use PostgreSQL with serializable isolation
    async with db.transaction(isolation_level="serializable"):
        balance = await get_balance(user_id)
        if balance < amount:
            raise InsufficientFunds()
        await deduct_balance(user_id, amount)
    # If the DB can't guarantee consistency, this transaction FAILS
    # rather than potentially double-charging

# Social feed "likes" count → availability is fine (AP)
async def get_like_count(post_id):
    # Use Redis cache — might be slightly stale
    count = await redis.get(f"likes:{post_id}")
    if count is not None:
        return int(count)  # Might be 999 instead of 1000 — that's OK
    count = await db.count_likes(post_id)
    await redis.setex(f"likes:{post_id}", 60, count)
    return count

# Product inventory → depends on context
# Displaying "In Stock" on product page → AP is fine
#   (Show "5 left" even if it's actually 4 — close enough)
# Decrementing stock during checkout → MUST be CP
#   (Don't sell item that's already sold)
```

**Where the analogy breaks:**
1. "Pick two" is oversimplified — modern systems tune the trade-off per operation (strong consistency for payments, eventual consistency for display).
2. Partitions are temporary — after the network heals, AP systems synchronize and become consistent again ("eventual consistency").
3. Single-node databases (your PostgreSQL on one server) don't have partitions — CAP only applies to distributed systems.

For most apps: use PostgreSQL (CP) for your primary database, add Redis (AP) for caching and real-time counters. You get the best of both worlds without thinking about CAP for most operations.'''
    ),
    (
        "thinking/analogy-transaction-banktransfer",
        "I keep hearing about database transactions and ACID properties but I don't get why they matter. My simple INSERT/UPDATE queries work fine without explicitly using transactions.",
        r'''<think>
Let me map database transactions to bank transfers — the analogy is literal since databases were originally designed for banking.

The scenario: Transfer $500 from checking to savings.

Without a transaction (just two SQL statements):
```sql
UPDATE accounts SET balance = balance - 500 WHERE id = 'checking';
-- POWER OUTAGE HERE --
UPDATE accounts SET balance = balance + 500 WHERE id = 'savings';
```

If the power goes out between the two statements:
- Checking: -$500 ✓
- Savings: +$0 ✗
- $500 vanished! The money was subtracted but never added.

This is EXACTLY why transactions exist. A transaction groups multiple operations into one atomic unit: either ALL happen or NONE happen.

```sql
BEGIN;
UPDATE accounts SET balance = balance - 500 WHERE id = 'checking';
UPDATE accounts SET balance = balance + 500 WHERE id = 'savings';
COMMIT;
```

If power goes out between the two UPDATEs, the database rolls back BOTH. The money stays in checking.

Now let me map ACID to banking:

A = Atomicity: "All or nothing"
- The transfer either fully completes or fully rolls back
- No partial transfers (money subtracted but not added)
- Banking: money never disappears or appears from nothing

C = Consistency: "Rules are always enforced"
- balance >= 0 constraint is always maintained
- Can't transfer $500 from an account with $300
- Banking: account balances always add up correctly

I = Isolation: "Transactions don't see each other's incomplete work"
- While transfer is happening, another query sees EITHER before-state OR after-state
- Never sees "checking = -500, savings = 0" (the intermediate state)
- Banking: your online banking never shows $500 "in transit"

D = Durability: "Once committed, it's permanent"
- After COMMIT, even if the server crashes, the transfer is saved
- The database writes to disk before confirming
- Banking: once the receipt prints, the transfer is guaranteed

Where the analogy is perfectly literal:
This ISN'T even an analogy — databases were designed for exactly this use case. ACID was coined to describe what banks need from their computer systems.

Why their simple queries "work fine":
- Single INSERT/UPDATE is automatically wrapped in a transaction
- The problem only appears when you need MULTIPLE operations to be atomic
- Creating an order + creating order_items + decrementing inventory = need a transaction
</think>

Database transactions are literally modeled after bank transfers — it's not even an analogy, it's the original use case.

**The problem transactions solve:**

```sql
-- Transfer $500 from checking to savings
-- WITHOUT a transaction:

UPDATE accounts SET balance = balance - 500 WHERE account = 'checking';
-- ⚡ SERVER CRASHES HERE ⚡
UPDATE accounts SET balance = balance + 500 WHERE account = 'savings';

-- Result: $500 vanished into thin air
-- Checking lost $500, savings gained $0
-- The books don't balance
```

```sql
-- WITH a transaction:
BEGIN;
UPDATE accounts SET balance = balance - 500 WHERE account = 'checking';
-- ⚡ SERVER CRASHES HERE ⚡
UPDATE accounts SET balance = balance + 500 WHERE account = 'savings';
COMMIT;

-- Result: NOTHING happened. Both updates rolled back.
-- Checking still has the $500. Transfer can be retried.
```

**ACID = the four guarantees, explained with banking:**

```
A = Atomicity: "All or nothing"
  Transfer: debit AND credit both happen, or neither does.
  No partial transfers. Money never vanishes.

  Code equivalent:
    BEGIN;
    INSERT INTO orders (user_id, total) VALUES (1, 99.99);
    INSERT INTO order_items (order_id, product_id) VALUES (...);
    UPDATE inventory SET stock = stock - 1 WHERE product_id = 42;
    COMMIT;
    -- If inventory update fails → order AND items are rolled back
    -- No orphaned orders without items, no stock decremented without order

C = Consistency: "Rules always hold"
  Account balance can't go negative (CHECK constraint).
  A transfer that would overdraw is rejected entirely.

  Code equivalent:
    ALTER TABLE accounts ADD CONSTRAINT positive_balance CHECK (balance >= 0);
    -- Transaction that violates this is rolled back automatically

I = Isolation: "Other people see before OR after, never during"
  While the transfer is happening:
  - Online banking shows EITHER $1000 checking + $0 savings (before)
  - OR $500 checking + $500 savings (after)
  - NEVER $500 checking + $0 savings (during)

  Code equivalent:
    -- User A is transferring, User B is checking balance
    -- User B never sees the intermediate state

D = Durability: "Once confirmed, it's permanent"
  After the bank says "transfer complete," it survives power outages.
  The database flushes to disk before returning COMMIT success.
```

**Why your simple queries "work fine" without explicit transactions:**

```python
# Single statements ARE automatically transactional:
db.execute("INSERT INTO users (name) VALUES ('Alice')")
# PostgreSQL wraps this in an implicit BEGIN/COMMIT
# If the server crashes mid-write, it's fully rolled back

# You need EXPLICIT transactions when multiple statements must be atomic:
async with db.transaction():
    order = await db.execute("INSERT INTO orders ...")
    for item in items:
        await db.execute("INSERT INTO order_items ...")
    await db.execute("UPDATE inventory SET stock = stock - ...")
    # If ANY of these fail → ALL are rolled back
```

**Real scenarios where you NEED transactions:**

```python
# Scenario 1: Creating an order (multiple tables must stay consistent)
async with db.transaction():
    order = await create_order(user_id, total)
    await create_order_items(order.id, items)
    await decrement_inventory(items)
    await charge_payment(user_id, total)
    # Crash after inventory decrement? → ALL rolled back
    # No orphaned orders, no phantom inventory changes

# Scenario 2: User registration (account + profile + welcome email record)
async with db.transaction():
    user = await create_user(email, password_hash)
    await create_profile(user.id, name)
    await create_email_queue_entry(user.id, "welcome")
    # If profile creation fails → user is rolled back too
    # No user without a profile

# Scenario 3: NOT needed — single operation
await db.execute("UPDATE users SET name = 'Bob' WHERE id = 1")
# This is already atomic on its own — no explicit transaction needed
```

**In Python (SQLAlchemy):**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

engine = create_engine("postgresql://...")

# Context manager handles BEGIN/COMMIT/ROLLBACK automatically
with Session(engine) as session:
    with session.begin():  # BEGIN
        order = Order(user_id=1, total=99.99)
        session.add(order)
        session.flush()  # Get order.id

        item = OrderItem(order_id=order.id, product_id=42)
        session.add(item)

        product = session.get(Product, 42)
        product.stock -= 1
    # COMMIT happens here automatically
    # If ANY exception occurs → ROLLBACK automatically
```

Rule of thumb: if you're doing 2+ related write operations that must all succeed or all fail, wrap them in a transaction. For single INSERT/UPDATE/DELETE, the database handles it automatically.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
