"""Phase 2C: Advanced Reasoning — Analogical Reasoning (Part 2/4)
Microservices ↔ team organization, eventual consistency ↔ bank reconciliation,
observer pattern ↔ newspaper subscription, MapReduce ↔ vote counting."""

PAIRS = [
    (
        "thinking/analogy-microservices-teams",
        "We're splitting our monolith into microservices. How do we decide where to draw the service boundaries?",
        r'''<think>
This maps perfectly to Conway's Law: "Organizations which design systems are constrained to produce designs which are copies of the communication structures of these organizations."

In other words: service boundaries should match team boundaries. Let me build this analogy:

A company with departments:
- Sales department handles customer relationships
- Engineering department builds the product
- Finance department handles money
- Each department has its own internal processes
- Departments communicate through well-defined channels (emails, meetings, tickets)
- Each department can reorganize internally without affecting others

Microservices:
- Each service handles one business domain
- Services have their own internal implementation
- Services communicate through well-defined APIs
- Each service can be redeployed independently

The mapping:
- Department = Service
- Department responsibilities = Bounded context
- Inter-department communication = API contracts
- Department reorganization = Internal refactoring
- Cross-department project = Distributed transaction (hard!)

Where the analogy is strongest:
- If two departments constantly need real-time coordination, they should probably be one department
- Same with services: if two services need synchronous calls for every request, they should probably be one service

Where it breaks down:
- You can't "merge" departments as easily as you can merge code
- Departments have humans with feelings; services are just code
- But the organizational insight is real: team structure drives architecture
</think>

**Conway's Law: your service boundaries should mirror your team boundaries.**

```
Company Organization                Microservice Architecture
────────────────────                ────────────────────────────
Sales Department                    Customer Service
  - owns customer relationships      - owns customer data
  - internal CRM processes           - internal implementation
  - communicates via email/meetings   - communicates via REST API

Finance Department                  Billing Service
  - owns financial data               - owns payment data
  - internal accounting processes     - internal payment logic
  - regulated, audited separately     - separate compliance, logging

Engineering Department              Product Service
  - owns the product                   - owns product catalog
  - internal dev processes             - internal implementation

Cross-department project            Distributed transaction
  (needs Sales + Finance + Eng)      (needs Customer + Billing + Product)
  = SLOW, lots of coordination       = SLOW, lots of API calls
  = Should minimize these!            = Should minimize these!
```

**Drawing boundaries using this analogy**:
```python
# RULE 1: One team = one service
# If team A owns the User service and team B owns the Order service,
# they can deploy independently (just like departments operate independently)

# BAD: Two teams co-own one service
# → Every deploy requires coordination
# → Like two departments sharing one budget — endless conflict

# GOOD: Each team owns 1-3 services
# → Independent deploys, independent priorities
# → Like each department managing its own budget

# RULE 2: Minimize cross-service calls (minimize cross-department coordination)
# If Service A calls Service B on EVERY request → they should be one service
# Like: if Sales calls Finance for EVERY customer interaction, merge the teams

# RULE 3: Services share data through APIs, not databases
# Like: departments share information through reports, not by reading each other's files
# BAD:
#   Order service reads from User database directly
#   → Like Sales reading Finance's spreadsheets — no ownership boundary
# GOOD:
#   Order service calls User service API to get user info
#   → Like Sales requesting a report from Finance

# RULE 4: Draw boundaries around BUSINESS CAPABILITIES, not technical layers
# BAD boundaries (technical):
#   "Database service", "API service", "Frontend service"
#   → Like organizing by job function: "all managers", "all analysts", "all juniors"
#
# GOOD boundaries (business):
#   "Order service", "Payment service", "Notification service"
#   → Like organizing by business function: Sales, Finance, Engineering
```

**Practical boundary-drawing exercise**:
```python
# Step 1: List your bounded contexts (business domains)
domains = {
    "Users":         {"owns": ["profiles", "auth", "preferences"]},
    "Products":      {"owns": ["catalog", "inventory", "pricing"]},
    "Orders":        {"owns": ["cart", "checkout", "order history"]},
    "Payments":      {"owns": ["billing", "invoices", "refunds"]},
    "Notifications": {"owns": ["email", "sms", "push"]},
}

# Step 2: Map communication patterns (which domains talk to which?)
communication = {
    ("Orders", "Products"):      "every request",  # TIGHT — maybe merge?
    ("Orders", "Payments"):      "on checkout only", # LOOSE — good boundary
    ("Orders", "Notifications"): "on status change",  # LOOSE — good boundary
    ("Users", "Notifications"):  "on signup only",    # LOOSE — good boundary
}

# Step 3: If two domains communicate "every request" → consider keeping them together
# Orders ↔ Products: every order checks inventory → keep together initially
# Orders ↔ Payments: only at checkout → good service boundary
```

**Where the analogy breaks down** (and what that teaches): You can't A/B test organizational structures, but you CAN A/B test service architectures. You can't clone a department, but you CAN scale a service horizontally. Use the analogy for boundary decisions, but remember that code is more malleable than organizations.'''
    ),
    (
        "thinking/analogy-eventual-consistency-bank",
        "I don't understand eventual consistency. How can a system be 'eventually' consistent? Doesn't that mean it's sometimes wrong?",
        r'''<think>
Bank reconciliation is the perfect analogy for eventual consistency.

When you write a check:
1. You write check for $500 (your ledger says -$500)
2. Recipient deposits the check (their ledger says +$500)
3. Banks process the check (takes 1-3 business days)
4. Your bank account shows -$500 (eventually)

During steps 2-3, the system is INCONSISTENT:
- Your checkbook says -$500
- Your bank account still shows the old balance
- The recipient's bank says +$500
- The clearing house is in the middle of processing

But eventually (after 1-3 days), ALL ledgers agree. This is eventual consistency!

The key insight: the real world has ALWAYS been eventually consistent. Immediate consistency is the exception, not the rule.

Other examples:
- ATM withdrawals: you can overdraw because the ATM doesn't have real-time balance
- Stock trading: your trade is "submitted," then "filled" later
- Email: you send a message, recipient doesn't see it for 1-30 seconds
- DNS: you update a DNS record, it takes hours to propagate worldwide

The trade-off: immediate consistency requires coordination (slow). Eventual consistency allows independence (fast).

Where the analogy is strongest:
- Both handle conflicts with reconciliation (bank resolves double-spending, distributed systems resolve conflicting writes)
- Both have a "source of truth" that eventually wins
- Both accept temporary inconsistency as a feature, not a bug

Where it breaks down:
- Banks have legal frameworks for disputes; distributed systems have conflict resolution algorithms
- Bank reconciliation happens daily; distributed systems reconcile in milliseconds to seconds
</think>

**Think of it like banking — a system you already use that's eventually consistent.**

```
When you write a check:

Day 0 (Monday):
  Your checkbook:    Balance = $1000 - $500 = $500  ✓
  Your bank account: Balance = $1000                 ✗ (hasn't processed yet)
  Recipient's bank:  Balance = $0                    ✗ (check not deposited yet)
  → System is INCONSISTENT. Three different answers for "how much money?"

Day 1 (Tuesday):
  Your checkbook:    Balance = $500                  ✓
  Your bank account: Balance = $1000                 ✗ (still processing)
  Recipient's bank:  Balance = $500                  ✓ (deposited, pending)
  → Still inconsistent!

Day 3 (Thursday):
  Your checkbook:    Balance = $500                  ✓
  Your bank account: Balance = $500                  ✓ (check cleared)
  Recipient's bank:  Balance = $500                  ✓
  → EVENTUALLY CONSISTENT! All agree.
```

**In distributed systems, it's the same thing — just faster**:
```
Write to Primary DB (us-east):
  0ms:   Primary (us-east): user.name = "Alice"     ✓
         Replica (us-west): user.name = "old_name"    ✗ (replication lag)
         Replica (eu-west): user.name = "old_name"    ✗ (replication lag)

  50ms:  Primary (us-east): user.name = "Alice"     ✓
         Replica (us-west): user.name = "Alice"      ✓ (replicated!)
         Replica (eu-west): user.name = "old_name"    ✗ (still replicating)

  150ms: Primary (us-east): user.name = "Alice"     ✓
         Replica (us-west): user.name = "Alice"      ✓
         Replica (eu-west): user.name = "Alice"      ✓
         → EVENTUALLY CONSISTENT (took 150ms, not 3 days!)
```

**The trade-off (same as banking)**:
```python
# STRONG CONSISTENCY (like a wire transfer — synchronous)
async def transfer_money_strong(from_acct, to_acct, amount):
    async with db.transaction():  # Lock both accounts
        await db.execute("UPDATE accounts SET balance = balance - $1 WHERE id = $2", amount, from_acct)
        await db.execute("UPDATE accounts SET balance = balance + $1 WHERE id = $2", amount, to_acct)
    # Both accounts are updated AT THE SAME INSTANT
    # But: requires coordination, slower, can't work across databases

# EVENTUAL CONSISTENCY (like a check — asynchronous)
async def transfer_money_eventual(from_acct, to_acct, amount):
    # Debit immediately (your checkbook)
    await db.execute("UPDATE accounts SET balance = balance - $1 WHERE id = $2", amount, from_acct)
    # Credit asynchronously (check clearing)
    await event_bus.publish("credit", {"account": to_acct, "amount": amount})
    # Eventually, the credit is applied
    # But: temporarily inconsistent, need conflict resolution
```

**When each is appropriate**:
```
Use STRONG consistency:          Use EVENTUAL consistency:
──────────────────────           ──────────────────────────
Bank transfers between accounts  Social media likes/counters
Inventory reservation            User profile updates
Seat booking                     Search index updates
Payment processing               Email delivery
                                 Analytics/metrics
                                 Cache refresh

Ask: "Is temporary inconsistency harmful or just annoying?"
If harmful → strong consistency
If annoying → eventual consistency
```

**The banking analogy teaches the key insight**: Eventual consistency isn't a compromise — it's **how the real world already works**. Immediate consistency is the expensive exception, useful only when temporary inconsistency would cause real harm.'''
    ),
    (
        "thinking/analogy-observer-newspaper",
        "When should I use the Observer pattern vs just calling functions directly?",
        r'''<think>
The newspaper subscription analogy maps perfectly:

Without Observer (direct calls):
- Every morning, you call the newspaper office: "Do you have today's paper?"
- If yes, they tell you the news
- If no, you call back in an hour
- This is POLLING — wasteful and annoying

With Observer (subscription):
- You SUBSCRIBE to the newspaper
- They DELIVER it to your door when it's ready
- You don't call them; they notify you
- You can UNSUBSCRIBE any time

In code:
- Without Observer: the "newspaper office" (event source) needs to know about every subscriber
- With Observer: subscribers register themselves, the source just publishes

Where the analogy is strongest:
- Decoupling: the newspaper doesn't know what you do with the news (read it, use it for birdcage, ignore it)
- Multiple subscribers: many people subscribe; the newspaper publishes once
- Late subscribers: you can subscribe any time; new code can register as observer

Where to use Observer vs direct calls:
- Observer: when the publisher shouldn't know/care about subscribers (events, notifications)
- Direct: when there's exactly one consumer and coupling is fine
</think>

**The newspaper subscription analogy makes it clear**:

```
WITHOUT Observer (polling/direct calls):
  ┌─────────┐                    ┌──────────┐
  │ You     │── "Any news?" ──→ │ Newspaper │
  │         │← "No" ───────────│ Office    │
  │         │── "Any news?" ──→ │           │
  │         │← "No" ───────────│           │
  │         │── "Any news?" ──→ │           │
  │         │← "Yes! Here..." ─│           │
  └─────────┘                    └──────────┘
  You keep asking. Wasteful. You need to know the office phone number.

WITH Observer (subscription):
  ┌─────────┐  "Subscribe" ┌──────────┐
  │ You     │──────────────│ Newspaper │
  │ Alice   │              │ Office    │
  └─────────┘              │           │
  ┌─────────┐  "Subscribe" │           │
  │ Bob     │──────────────│           │
  └─────────┘              └──────┬────┘
                                  │ New edition!
                           ┌──────▼──────┐
                           │  Deliver to: │
                           │  - You       │
                           │  - Alice     │
                           │  - Bob       │
                           └─────────────┘
  Newspaper doesn't know what you do with it. You can unsubscribe anytime.
```

**In code**:
```python
# WITHOUT Observer: OrderService knows about EVERY downstream system
class OrderService:
    def __init__(self):
        self.email_service = EmailService()       # Tight coupling
        self.inventory_service = InventoryService() # Tight coupling
        self.analytics_service = AnalyticsService() # Tight coupling
        self.loyalty_service = LoyaltyService()     # Tight coupling

    async def create_order(self, order: Order):
        await self.save(order)
        # OrderService must know about ALL subscribers
        await self.email_service.send_confirmation(order)     # What if we add SMS?
        await self.inventory_service.reserve_items(order)      # What if we remove this?
        await self.analytics_service.track_purchase(order)     # What if analytics is down?
        await self.loyalty_service.add_points(order)           # Adding = changing OrderService

# Adding a new "subscriber" requires modifying OrderService!
# Like: the newspaper office has to update their code every time someone subscribes.

# ─────────────────────────────────────────────────

# WITH Observer: OrderService just publishes the event
class EventBus:
    """The newspaper delivery system."""
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable):
        self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: Callable):
        self._subscribers.get(event_type, []).remove(handler)

    async def publish(self, event_type: str, data: Any):
        for handler in self._subscribers.get(event_type, []):
            await handler(data)

# Publisher doesn't know about subscribers
class OrderService:
    def __init__(self, event_bus: EventBus):
        self.events = event_bus

    async def create_order(self, order: Order):
        await self.save(order)
        await self.events.publish("order_created", order)  # That's it!

# Subscribers register themselves — OrderService doesn't change
event_bus = EventBus()
event_bus.subscribe("order_created", email_service.send_confirmation)
event_bus.subscribe("order_created", inventory_service.reserve_items)
event_bus.subscribe("order_created", analytics_service.track_purchase)
event_bus.subscribe("order_created", loyalty_service.add_points)
# Adding SMS? Just subscribe — OrderService is untouched:
event_bus.subscribe("order_created", sms_service.send_notification)
```

**When to use each**:
```
Use DIRECT calls when:               Use OBSERVER when:
────────────────────────              ────────────────────────
Exactly 1 consumer                   Multiple consumers (or might be)
Caller needs the result              Fire-and-forget
Tight coupling is OK                 Publisher shouldn't know about subscribers
Synchronous flow required            Async/decoupled flow is fine
```

Like newspapers: if you're the ONLY reader and you need today's headline RIGHT NOW, call the editor directly. If many people want the news and the editor shouldn't care who reads it, publish a newspaper.'''
    ),
    (
        "thinking/analogy-mapreduce-voting",
        "Can you explain MapReduce in a way that's intuitive? I've read the Wikipedia article but the abstract description doesn't click.",
        r'''<think>
Vote counting is the perfect analogy for MapReduce because it's something everyone understands and it has the exact same structure.

Without MapReduce (serial):
- One person counts ALL votes. Takes forever.

With MapReduce:
- MAP: Each precinct counts their own votes (parallel)
- SHUFFLE: Group results by candidate (organize)
- REDUCE: Sum the totals per candidate (aggregate)

This is exactly how real elections work, and it's exactly how MapReduce works.

The key insights:
1. MAP is embarrassingly parallel: each precinct is independent
2. SHUFFLE is the expensive part: gathering results from all precincts
3. REDUCE combines partial results into final answer
4. The pattern works because the operation (counting) is associative and commutative

Let me extend the analogy to more complex MapReduce patterns:
- Word count: like counting how many times each candidate's name appears on ballots
- Average: like calculating average voter age per precinct
- Join: like matching voter registrations with actual votes
</think>

**Think of it like counting votes in an election:**

```
ELECTION DAY (the problem):
  10 million votes need to be counted across 1000 precincts.
  One person counting ALL votes: 3 months.
  MapReduce approach: 4 hours.

STEP 1: MAP (each precinct counts locally — parallel)
  ┌─────────────────────────────────────────────┐
  │ Precinct 1: "Alice:347, Bob:289, Carol:164" │
  │ Precinct 2: "Alice:512, Bob:401, Carol:87"  │
  │ Precinct 3: "Alice:203, Bob:356, Carol:441" │
  │ ...                                         │
  │ Precinct 1000: "Alice:98, Bob:76, Carol:126"│
  └─────────────────────────────────────────────┘
  1000 precincts count in PARALLEL → done in minutes, not months

STEP 2: SHUFFLE (group by candidate — organize)
  ┌───────────────────────────────────────────────┐
  │ Alice: [347, 512, 203, ..., 98]  (1000 numbers)│
  │ Bob:   [289, 401, 356, ..., 76]  (1000 numbers)│
  │ Carol: [164, 87, 441, ..., 126]  (1000 numbers)│
  └───────────────────────────────────────────────┘

STEP 3: REDUCE (sum totals per candidate — aggregate)
  ┌────────────────────────────────┐
  │ Alice: 347+512+203+...+98 = 245,891  │
  │ Bob:   289+401+356+...+76 = 231,445  │
  │ Carol: 164+87+441+...+126 = 222,664  │
  └────────────────────────────────┘
  Winner: Alice!
```

**In code — same structure**:
```python
# Example: Count word frequency across 1000 files

from collections import Counter
from multiprocessing import Pool

# STEP 1: MAP — process each file independently (parallel)
def map_function(file_path: str) -> dict[str, int]:
    """Like a precinct counting its own ballots."""
    word_counts = Counter()
    with open(file_path) as f:
        for line in f:
            for word in line.strip().lower().split():
                word_counts[word] += 1
    return dict(word_counts)
    # Returns: {"the": 347, "and": 289, "python": 164, ...}

# STEP 2 & 3: SHUFFLE + REDUCE — combine results
def reduce_function(results: list[dict[str, int]]) -> dict[str, int]:
    """Like summing precinct results into a final tally."""
    total = Counter()
    for partial_result in results:
        total.update(partial_result)
    return dict(total)

# Run it
with Pool(processes=8) as pool:
    # MAP: 8 workers process files in parallel
    partial_results = pool.map(map_function, list_of_1000_files)

# REDUCE: combine all partial results
final_counts = reduce_function(partial_results)
# {"the": 1_245_891, "and": 931_445, "python": 522_664, ...}
```

**The analogy extends to explain WHY MapReduce works**:
```
Election insight → MapReduce insight
─────────────── → ───────────────────
Each precinct counts independently → MAP workers don't need to communicate
Order of counting doesn't matter  → Operation is commutative and associative
You can count precincts in any order → MAP tasks can run in any order
The final sum is the same          → REDUCE produces the same result regardless of order
Adding more precincts = more workers → MapReduce scales linearly
One slow precinct doesn't block others → Stragglers can be reassigned
```

**Where the analogy breaks down**: In real elections, the data is naturally partitioned (each precinct has its own ballots). In MapReduce, the SHUFFLE step (distributing data by key across machines) is often the bottleneck — like if ballots from ALL precincts were mixed together and you had to sort them by candidate before counting.'''
    ),
    (
        "thinking/analogy-saga-travel-booking",
        "What's the Saga pattern for distributed transactions? I can never remember how it works.",
        r'''<think>
Travel booking is the perfect analogy because it's a multi-step process where each step can fail and needs to be "undone."

Booking a vacation:
1. Book flight ($500)
2. Book hotel ($800)
3. Book rental car ($200)

What if the hotel is fully booked (step 2 fails)?
- You need to CANCEL the flight (undo step 1)
- Don't book the car (skip step 3)

This is exactly the Saga pattern:
- Each step is a separate transaction (separate services)
- If a step fails, run COMPENSATING TRANSACTIONS for all previous steps
- Compensating transaction = the "undo" for that step

The key insight: in distributed systems, you CAN'T have a single transaction across multiple services. Each service has its own database. So instead of ROLLBACK, you COMPENSATE.

Types of Saga:
1. Choreography: each service triggers the next (like dominos)
2. Orchestration: a coordinator directs the flow (like a travel agent)

The travel agent analogy maps to orchestration:
- You (the orchestrator/travel agent) coordinate all bookings
- If one fails, you call each previous service to cancel
- You track the state of the overall booking
</think>

**Think of it like booking a vacation with a travel agent:**

```
BOOKING A VACATION:
  Step 1: Book flight ($500)    → Compensation: Cancel flight (refund $500)
  Step 2: Book hotel ($800)     → Compensation: Cancel reservation
  Step 3: Book rental car ($200) → Compensation: Cancel rental

HAPPY PATH (everything works):
  ✅ Flight booked → ✅ Hotel booked → ✅ Car booked → Vacation confirmed!

SAD PATH (hotel is full):
  ✅ Flight booked → ❌ Hotel failed → Cancel flight (compensate!)
  The car is never booked (skipped).
  You don't end up with a flight and no hotel.

SADDER PATH (car fails after hotel):
  ✅ Flight booked → ✅ Hotel booked → ❌ Car failed
  → Cancel hotel (compensate!)
  → Cancel flight (compensate!)
  Everything unwound in REVERSE order.
```

**In code — the Saga orchestrator**:
```python
from dataclasses import dataclass, field
from enum import Enum

class StepStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"

@dataclass
class SagaStep:
    name: str
    action: Callable       # The forward action (book flight)
    compensation: Callable  # The undo action (cancel flight)
    status: StepStatus = StepStatus.PENDING

class SagaOrchestrator:
    """The travel agent — coordinates the multi-step booking."""

    def __init__(self):
        self.steps: list[SagaStep] = []
        self.completed_steps: list[SagaStep] = []

    def add_step(self, name: str, action, compensation):
        self.steps.append(SagaStep(name=name, action=action, compensation=compensation))

    async def execute(self) -> bool:
        """Run all steps. If any fails, compensate all completed steps."""
        for step in self.steps:
            try:
                await step.action()
                step.status = StepStatus.COMPLETED
                self.completed_steps.append(step)
                logger.info(f"Saga step '{step.name}' completed")
            except Exception as e:
                step.status = StepStatus.FAILED
                logger.error(f"Saga step '{step.name}' failed: {e}")

                # Compensate in REVERSE order (cancel car → hotel → flight)
                await self._compensate()
                return False

        return True

    async def _compensate(self):
        """Undo all completed steps in reverse order."""
        for step in reversed(self.completed_steps):
            try:
                await step.compensation()
                step.status = StepStatus.COMPENSATED
                logger.info(f"Compensated step '{step.name}'")
            except Exception as e:
                # Compensation failed — needs manual intervention!
                logger.critical(f"COMPENSATION FAILED for '{step.name}': {e}")
                # Alert ops team — this is a partially unwound transaction


# Usage — booking a vacation
async def book_vacation(user, flight, hotel, car):
    saga = SagaOrchestrator()

    flight_booking = None
    hotel_booking = None
    car_booking = None

    saga.add_step(
        "book_flight",
        action=lambda: book_flight(user, flight),
        compensation=lambda: cancel_flight(flight_booking.id),
    )
    saga.add_step(
        "book_hotel",
        action=lambda: book_hotel(user, hotel),
        compensation=lambda: cancel_hotel(hotel_booking.id),
    )
    saga.add_step(
        "book_car",
        action=lambda: book_car(user, car),
        compensation=lambda: cancel_car(car_booking.id),
    )

    success = await saga.execute()
    if success:
        return VacationConfirmation(flight_booking, hotel_booking, car_booking)
    else:
        return VacationFailed("One or more bookings failed, all compensated")
```

**The analogy teaches the key differences from normal transactions**:
```
Regular transaction (one database):    Saga (multiple services):
─────────────────────────────          ─────────────────────────
BEGIN; ... ROLLBACK;                    Execute → Compensate
Instant undo                           Compensation might take time
Guaranteed consistency                 Temporary inconsistency is possible
Automatic                              You must write compensation logic
One system                             Multiple independent systems
```

**Where the analogy breaks down**: When you cancel a real flight, you might not get a full refund (cancellation fees). In software sagas, the compensation should fully undo the action. This is why designing idempotent compensations is crucial — "cancel flight" must work even if called twice.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
