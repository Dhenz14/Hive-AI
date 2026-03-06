"""Phase 2C: Advanced Reasoning — Analogical Reasoning (Part 7/8)"""

PAIRS = [
    (
        "thinking/analogy-database-indexes-to-book-index",
        "How do I explain to a junior developer when to add a database index and when NOT to? They keep wanting to add indexes to every column.",
        r'''<think>
Database indexes for a junior — they need to understand the trade-off. The book index analogy is perfect here because it directly maps.

**Book index analogy:**
- A book without an index: to find "recursion," you read every page (full table scan)
- A book WITH an index: look up "recursion" in the back → page 142 (indexed lookup)

But:
- The index itself takes pages (disk space)
- Every time the book is revised, the index must be updated (write overhead)
- A book with an index for every word would have an index bigger than the book itself

When an index helps:
- You frequently search for specific topics (WHERE clause)
- The book is large (many rows)
- The topic appears on few pages (high selectivity)

When an index hurts:
- The book is short (small table — just read it all)
- You want to find "the" (low selectivity — appears on every page)
- The book changes constantly (write-heavy table)

This maps perfectly to database indexes.
</think>

Think of a database index like the **index at the back of a textbook**. It helps you find things fast, but it has costs.

## The Analogy

```
TEXTBOOK (without index):
  "Find everything about recursion"
  → Read every page from start to end
  → 500 pages scanned, found references on pages 142, 203, 378
  → Took a long time

TEXTBOOK (with index):
  → Look up "Recursion" in the index at the back
  → "Recursion: 142, 203, 378"
  → Go directly to those pages
  → Found instantly

DATABASE (without index):
  SELECT * FROM users WHERE email = 'alice@example.com'
  → Scan every row in the table (1 million rows)
  → Took 800ms

DATABASE (with index on email):
  → Look up 'alice@example.com' in the index
  → Found at row 42,391
  → Go directly to that row
  → Took 2ms
```

## When to Add an Index (Add an index entry for this topic)

```
ADD INDEX when:

1. You search for this column frequently
   Book: "recursion" is a key topic students look up often
   DB: WHERE email = ? is in every login query

2. The table is large
   Book: 500-page textbook benefits from an index
   DB: 1 million rows benefits from an index
   (A 5-page pamphlet doesn't need an index — just read it)
   (A 100-row table doesn't need an index — just scan it)

3. The values are selective (appear on few pages)
   Book: "Quantum entanglement" appears on 3 pages → great index entry
   DB: email column has unique values → great index
```

## When NOT to Add an Index (Don't index every word)

```
DON'T INDEX when:

1. The table is small (< 1000 rows)
   Book: a 10-page pamphlet doesn't need an index
   DB: scanning 1000 rows takes < 1ms anyway

2. The column has few unique values
   Book: indexing the word "the" → points to EVERY page → useless
   DB: indexing a boolean is_active column → half the rows match → useless
   (An index that points to 50% of rows doesn't save any work)

3. The table is write-heavy
   Book: if you revise the book every day, you rebuild the index daily
   DB: every INSERT/UPDATE must also update ALL indexes
   Table with 10 indexes: each write does 11 operations (1 data + 10 indexes)

4. You never search by this column
   Book: no point indexing appendix page numbers if nobody looks there
   DB: no point indexing created_by if no query filters on it
```

## The Cost of Over-Indexing

```
TEXTBOOK with index for EVERY WORD:

  Original book: 500 pages
  Index: 800 pages (bigger than the book!)
  Total: 1,300 pages

  Every revision: update 800 pages of index entries
  Publishing takes 3x longer

DATABASE with index on EVERY COLUMN:

  Original table: 500MB
  10 indexes: 800MB (more than the data!)
  Total storage: 1.3GB

  Every INSERT: write to table + update 10 indexes
  Writes are 10x slower than necessary
```

## The Decision Checklist

```sql
-- Before adding an index, ask:
-- 1. Does a query WHERE/JOIN/ORDER BY this column?
SELECT * FROM orders WHERE customer_id = 42;  -- YES → index customer_id

-- 2. Is the table large? (> 10,000 rows)
SELECT count(*) FROM orders;  -- 500,000 rows → YES

-- 3. Is the column selective? (many unique values)
SELECT count(DISTINCT customer_id) FROM orders;  -- 10,000 unique → YES, index
SELECT count(DISTINCT is_active) FROM orders;    -- 2 unique → NO, don't index

-- 4. Is the table write-heavy?
-- If you INSERT 1000 rows/second and SELECT 10/second → be cautious with indexes
-- If you INSERT 10/second and SELECT 1000/second → indexes are great
```

The simple rule: index columns you SEARCH by, on LARGE tables, with MANY UNIQUE values. Don't index everything — an index for every column is like a textbook index for every word.'''
    ),
    (
        "thinking/analogy-race-condition-to-atm-withdrawal",
        "A junior developer on my team doesn't understand race conditions. They think 'it works on my machine' is proof enough. How do I explain why race conditions are dangerous?",
        r'''<think>
Race conditions for someone who hasn't experienced them. I need an analogy that makes the danger visceral and obvious.

**ATM withdrawal analogy:**
This is the classic race condition example because it involves money and is immediately understandable:

You have $100 in your bank account. You and your partner both try to withdraw $80 at different ATMs at the exact same time.

WITHOUT proper synchronization (race condition):
- ATM 1 reads balance: $100 ✓ ($80 available)
- ATM 2 reads balance: $100 ✓ ($80 available)  ← read the OLD value
- ATM 1 dispenses $80, writes balance: $100 - $80 = $20
- ATM 2 dispenses $80, writes balance: $100 - $80 = $20
- Result: $160 dispensed from a $100 account. Bank lost $60.

WITH proper synchronization (lock):
- ATM 1 LOCKS the account, reads balance: $100
- ATM 2 tries to read → WAITS (account locked)
- ATM 1 dispenses $80, writes balance: $20, UNLOCKS
- ATM 2 reads balance: $20 → $80 not available → DECLINED
- Result: $80 dispensed, $20 remaining. Correct.

**Why "it works on my machine" fails:**
On one machine, things run sequentially — one ATM at a time. You never see the race. In production with 100 concurrent users, both ATMs are running simultaneously. The race condition is timing-dependent — it happens unpredictably, and only under load.

This is perfect because it shows:
1. Why the bug is invisible in testing (sequential access)
2. Why it's catastrophic in production (concurrent access)
3. Why the fix is locks/transactions (atomic operations)
</think>

The best way to make race conditions click: imagine **two ATMs accessing the same bank account at the exact same time**.

## The ATM Analogy

```
Your bank account: $100
You and your partner both withdraw $80 simultaneously at different ATMs.

WITHOUT protection (race condition):
  ATM 1: Read balance    → $100 (enough for $80!)
  ATM 2: Read balance    → $100 (enough for $80!)  ← sees OLD value
  ATM 1: Dispense $80    → Write balance: $100 - $80 = $20
  ATM 2: Dispense $80    → Write balance: $100 - $80 = $20 ← overwrites!

  Result: $160 dispensed from $100 account.
  Bank lost $60. Both ATMs thought they were correct.

WITH protection (lock/transaction):
  ATM 1: LOCK account → Read $100 → Dispense $80 → Write $20 → UNLOCK
  ATM 2: Try to read → WAIT (locked) → Read $20 → $80 not available → DECLINE

  Result: $80 dispensed. $20 remaining. Correct.
```

## In Code: The Exact Same Bug

```python
# ❌ RACE CONDITION: same logic as the ATM bug
balance = 100  # Shared state

def withdraw(amount):
    global balance
    if balance >= amount:     # Thread A reads: 100 >= 80 ✓
                              # Thread B reads: 100 >= 80 ✓ (same time!)
        balance -= amount     # Thread A writes: 100 - 80 = 20
                              # Thread B writes: 100 - 80 = 20 (overwrites!)
        return True
    return False

# Run on two threads simultaneously:
# Thread A: withdraw(80) → True
# Thread B: withdraw(80) → True
# balance = 20 (should be -60 or B should fail)
```

```python
# ✅ FIXED: Lock prevents simultaneous access
import threading
lock = threading.Lock()
balance = 100

def withdraw(amount):
    global balance
    with lock:                  # Only one thread at a time
        if balance >= amount:   # Thread A reads: 100 >= 80 ✓
            balance -= amount   # Thread A writes: 20
            return True         # Thread B NOW reads: 20 >= 80 ✗
        return False            # Thread B: returns False (declined)
```

## In Database Code (Where Juniors Actually Hit This)

```python
# ❌ RACE CONDITION: reading and writing aren't atomic
def purchase_item(user_id, item_id):
    item = db.query("SELECT stock FROM items WHERE id = %s", item_id)
    if item.stock > 0:                    # Two requests read stock=1
        db.execute("UPDATE items SET stock = stock - 1 WHERE id = %s", item_id)
        db.execute("INSERT INTO orders (user_id, item_id) VALUES (%s, %s)",
                   user_id, item_id)
        # Both requests create an order for the LAST item
        # stock goes to -1. Oversold.

# ✅ FIXED: Atomic update with condition
def purchase_item(user_id, item_id):
    # UPDATE only succeeds if stock > 0 (atomic check-and-decrement)
    result = db.execute(
        "UPDATE items SET stock = stock - 1 WHERE id = %s AND stock > 0",
        item_id
    )
    if result.rowcount == 0:
        raise OutOfStockError()
    db.execute("INSERT INTO orders (user_id, item_id) VALUES (%s, %s)",
               user_id, item_id)
```

## Why "It Works on My Machine" Is Misleading

```
Local testing:   1 user → requests run sequentially → no race
                 Like testing with ONE ATM → always correct

Production:      100 users → requests run concurrently → race happens
                 Like 100 ATMs at once → eventually two hit the same account

The race condition exists in BOTH environments.
It only MANIFESTS when two things happen at the same time.
The probability increases with concurrent users.

At 1 user:       ~0% chance of race condition
At 10 users:     ~0.1% chance
At 100 users:    ~5% chance
At 1000 users:   ~50% chance → production bug guaranteed
```

Tell your junior: "Your code works with one ATM. Production has a thousand ATMs. The bug is there — it's just waiting for the right timing."'''
    ),
    (
        "thinking/analogy-eventual-consistency-to-post-office",
        "Can you explain eventual consistency in distributed systems? Our team is moving from a monolith with one database to microservices, and they don't understand why data might be temporarily inconsistent.",
        r'''<think>
Eventual consistency for a team used to strong consistency. I need an analogy that shows WHY eventual consistency exists and why it's acceptable.

**Post office / mail analogy:**
Strong consistency (monolith): You update your address at the city hall. Instantly, everyone who looks up your address sees the new one.

Eventual consistency (microservices): You move to a new address. You send change-of-address forms to:
- The post office
- Your bank
- Your insurance company
- Your magazine subscriptions

Each receives the update at DIFFERENT TIMES. For a while:
- The post office knows your new address
- Your bank still has the old address (their mail goes to your old home)
- Your insurance hasn't processed the form yet

Eventually (within days), all systems have your new address. But there's a WINDOW where different systems have different data.

This maps to:
- City hall (single database) = strong consistency
- Multiple organizations = microservices, each with own database
- Change-of-address form = event/message between services
- Window of inconsistency = propagation delay

**Where the analogy works:**
- Natural understanding of propagation delay ✓
- Different systems updating at different rates ✓
- Eventually converging to the correct state ✓
- The world works fine despite temporary inconsistency ✓

**Where it breaks down:**
- Real systems can have conflicting updates (two address changes at once)
- Network partitions can prevent delivery entirely
- Some operations need immediate consistency (bank transfer)
</think>

Think of it like **sending change-of-address forms** to every organization that has your address.

## The Analogy

```
STRONG CONSISTENCY (your monolith today):
  You change your address at City Hall.
  Instantly, EVERYONE who looks up your address sees the new one.
  One source of truth. Always correct.

EVENTUAL CONSISTENCY (microservices):
  You move to a new house. You send change-of-address forms to:
    📮 Post office    → Updated in 1 day
    🏦 Bank           → Updated in 3 days
    🏥 Insurance      → Updated in 5 days
    📰 Magazines      → Updated in 2 weeks

  Day 2: Post office has new address, bank still has old address.
  Day 4: Post office + bank updated, insurance still processing.
  Day 15: Everyone has the new address. EVENTUALLY CONSISTENT.
```

## In Your Microservices

```
STRONG CONSISTENCY (monolith, one database):
  User updates email → ONE database updated → all services see it instantly

  user_service.update_email("new@example.com")
  order_service.get_user_email()  → "new@example.com" ✓ (same DB)

EVENTUAL CONSISTENCY (microservices, separate databases):
  User updates email in User Service
    → Publishes event: "user.email.changed"
    → Order Service receives event (50ms later)
    → Notification Service receives event (200ms later)
    → Analytics Service receives event (2 seconds later)

  Timeline:
    t=0ms:    User Service has new email
    t=50ms:   Order Service still has OLD email (hasn't processed event yet)
    t=200ms:  Order Service updated, Notification Service updating
    t=2s:     All services have new email → EVENTUALLY CONSISTENT
```

## Why It's Acceptable (The Real-World Argument)

```
Your team worries: "But what if Order Service sends an email
                    to the OLD address during those 50ms?"

The answer: this already happens in the real world, and it's fine.

When you change your phone number:
  - Your bank might call the old number for a day
  - Your doctor's office might have the old number for a week
  - Eventually everyone has the new number
  - The world didn't end during the inconsistency window

Same in software:
  - An order confirmation might go to the old email (rare, during the 50ms window)
  - The user can check their order in the app (which has the current email)
  - No data is LOST — it's just temporarily in different states
```

## When Eventual Consistency Is NOT Acceptable

```python
# ❌ CANNOT be eventually consistent: money transfers
# "Deduct from Account A" and "Credit Account B" MUST be atomic
# If only one happens, money is lost or created

# For financial transactions: use the Saga pattern
async def transfer_money(from_id, to_id, amount):
    try:
        await deduct(from_id, amount)      # Step 1
        await credit(to_id, amount)         # Step 2
    except CreditFailed:
        await refund(from_id, amount)       # Compensating action
    # Either both happen or neither happens (eventually)


# ✅ CAN be eventually consistent: most read-heavy operations
# User profile updates, product catalog, notifications, analytics
# Temporary staleness is acceptable
```

## Practical Patterns for Your Team

```python
# Pattern 1: Event-driven updates (post office approach)
# User Service publishes events, other services subscribe

# User Service:
async def update_email(user_id, new_email):
    await db.update_email(user_id, new_email)
    await event_bus.publish("user.email.changed", {
        "user_id": user_id,
        "new_email": new_email,
    })

# Order Service:
@event_bus.subscribe("user.email.changed")
async def handle_email_change(event):
    await order_db.update_customer_email(
        event["user_id"], event["new_email"]
    )


# Pattern 2: Read from source on demand (phone call approach)
# Instead of maintaining a copy, ASK the source when you need it

# Order Service:
async def get_order_with_customer(order_id):
    order = await order_db.get(order_id)
    # Don't maintain a copy of user data — ask User Service directly
    customer = await user_service.get_user(order.customer_id)
    return {**order, "customer": customer}
# Trade-off: always fresh, but adds a network call
```

## Summary for Your Team

| Monolith | Microservices |
|----------|--------------|
| One database, one truth | Multiple databases, eventual truth |
| All reads are current | Some reads may be stale briefly |
| Transactions are easy | Transactions need Saga pattern |
| Simple but doesn't scale independently | Complex but scales per service |

The key message: eventual consistency isn't a bug — it's a trade-off for being able to scale and deploy services independently. The real world runs on eventual consistency, and so can your software.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
