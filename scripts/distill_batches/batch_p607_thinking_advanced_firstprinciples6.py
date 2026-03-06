"""Phase 2H: Advanced Reasoning — First Principles Derivation (Part 6/8)"""

PAIRS = [
    (
        "thinking/firstprinciples-rate-limiting-from-scratch",
        "How does rate limiting actually work? I know I should use it for APIs but I just copy-paste middleware configs without understanding the underlying mechanism.",
        r'''<think>
Rate limiting from first principles. Let me derive it from the core problem.

**The fundamental problem:**
A shared resource (server, API, database) has finite capacity. Without limits, one consumer can exhaust the resource, starving all others. We need a mechanism to fairly distribute access.

**What do we need?**
1. Count requests from each consumer
2. Define a limit (e.g., 100 requests per minute)
3. Reject requests that exceed the limit
4. Reset the count periodically

**Simplest approach: Fixed Window Counter**
Divide time into fixed windows (e.g., each minute). Count requests per window. If count > limit, reject.

```
Window: 14:00-14:01
  User A: 50 requests → allowed (limit: 100)
  User A: 60 more    → first 50 allowed, last 10 rejected (total would be 110)
```

Implementation: Store `{user_id}:{window} → count` in fast storage.

Problem: burst at window boundary. If user sends 100 requests at 14:00:59 and 100 at 14:01:00, they get 200 requests in 2 seconds despite a "100 per minute" limit.

**Fixing the boundary problem: Sliding Window Log**
Store the timestamp of every request. To check if allowed, count requests in the last 60 seconds from NOW.

Problem: memory. If limit is 10,000/min and you have 1M users, you're storing up to 10 billion timestamps.

**Balancing accuracy and memory: Sliding Window Counter**
Combine fixed window counter with proportional weighting.

```
Current window: 14:01 (30 seconds in = 50% through)
Previous window: 14:00 (had 80 requests)
Current window so far: 30 requests

Weighted count = (previous × remaining%) + current
               = (80 × 50%) + 30
               = 40 + 30 = 70
Limit: 100 → allowed
```

This is memory efficient (2 counters per user) and smooths the boundary problem.

**Alternative mental model: Token Bucket**
Instead of counting requests, think of it as a bucket of tokens.

- Bucket holds N tokens (the burst capacity)
- Tokens are added at rate R per second (the sustained rate)
- Each request consumes one token
- If bucket is empty, reject

This naturally handles bursts (bucket starts full) while enforcing sustained rate.

**Alternative: Leaky Bucket**
Requests enter a queue (bucket). Queue processes at fixed rate. If queue is full, reject. This smooths out bursts entirely — output is always at fixed rate.

So the core algorithms are:
1. Fixed window counter (simple, boundary problem)
2. Sliding window log (accurate, memory heavy)
3. Sliding window counter (balanced)
4. Token bucket (allows bursts up to capacity)
5. Leaky bucket (smooth output rate)

Each makes a different trade-off between accuracy, memory, burst handling, and complexity.
</think>

Let me derive rate limiting from the ground up, starting from the core problem.

## The Fundamental Problem

```
Server capacity: 1000 requests/second
10 users, each sending 100 rps → total 1000 rps → fine
1 user runs a script sending 5000 rps → server overloaded → everyone suffers

Rate limiting = fair resource allocation under contention
```

## Algorithm 1: Fixed Window Counter (Simplest)

```
Divide time into windows. Count requests per window.

Timeline:
  |---- 14:00 ----|---- 14:01 ----|---- 14:02 ----|
     User A: 45       User A: 100      User A: 73
     (allowed)        (at limit)       (allowed)

Storage: one counter per user per window
  Key: "ratelimit:user_42:14:00" → 45
  Key: "ratelimit:user_42:14:01" → 100
```

```python
# Fixed Window — derived from first principles
import time

def is_allowed(user_id, limit=100, window_seconds=60):
    # Which window are we in?
    current_window = int(time.time() // window_seconds)
    key = f"ratelimit:{user_id}:{current_window}"

    current_count = cache.get(key) or 0
    if current_count >= limit:
        return False

    cache.incr(key)
    cache.expire(key, window_seconds)  # Auto-cleanup
    return True
```

```
Problem: boundary burst

  |---- 14:00 ----|---- 14:01 ----|
              99 reqs  100 reqs
              ↑ last second  ↑ first second

  199 requests in 2 seconds — but each window sees < 100
  The "100 per minute" limit allowed 199 in 2 seconds!
```

## Algorithm 2: Sliding Window (Fixing the Boundary)

```
Instead of fixed windows, look at the last 60 seconds from NOW.

At time 14:01:30 (30 seconds into new window):
  Previous window (14:00): had 80 requests
  Current window (14:01): has 30 requests so far

  We're 50% through current window, so 50% of previous still counts:
  Weighted = (80 × 0.5) + 30 = 70

  Below limit of 100 → allowed
```

```python
# Sliding Window Counter — balances accuracy and memory
def is_allowed_sliding(user_id, limit=100, window_seconds=60):
    now = time.time()
    current_window = int(now // window_seconds)
    previous_window = current_window - 1

    # How far through current window (0.0 to 1.0)
    elapsed_ratio = (now % window_seconds) / window_seconds

    prev_count = cache.get(f"rl:{user_id}:{previous_window}") or 0
    curr_count = cache.get(f"rl:{user_id}:{current_window}") or 0

    # Weight previous window by remaining portion
    weighted = prev_count * (1 - elapsed_ratio) + curr_count

    if weighted >= limit:
        return False

    cache.incr(f"rl:{user_id}:{current_window}")
    cache.expire(f"rl:{user_id}:{current_window}", window_seconds * 2)
    return True
```

## Algorithm 3: Token Bucket (Allow Controlled Bursts)

```
Mental model: a bucket that fills with tokens at a steady rate.

  Bucket capacity: 10 tokens (max burst)
  Refill rate: 1 token per second (sustained rate)

  t=0:   Bucket has 10 tokens
  t=0:   5 requests arrive → 5 tokens consumed → 5 remaining ✓
  t=0:   6 more requests → only 5 tokens left → 5 allowed, 1 rejected
  t=5:   5 new tokens added (1/sec × 5 sec) → bucket has 10 again
  t=5:   3 requests → 3 tokens consumed → 7 remaining ✓
```

```python
# Token Bucket — derived from physical analogy
def is_allowed_token_bucket(user_id, capacity=10, refill_rate=1.0):
    now = time.time()
    key = f"bucket:{user_id}"

    bucket = cache.get(key) or {"tokens": capacity, "last_refill": now}

    # Refill tokens based on elapsed time
    elapsed = now - bucket["last_refill"]
    new_tokens = elapsed * refill_rate
    bucket["tokens"] = min(capacity, bucket["tokens"] + new_tokens)
    bucket["last_refill"] = now

    if bucket["tokens"] >= 1:
        bucket["tokens"] -= 1
        cache.set(key, bucket)
        return True
    else:
        cache.set(key, bucket)
        return False

# Token bucket is the most common production algorithm because:
# - Allows bursts (good user experience)
# - Enforces sustained rate (protects server)
# - Simple to reason about
# - Used by: AWS API Gateway, Stripe, GitHub API
```

## Algorithm Comparison (First Principles Trade-offs)

```
Algorithm          Memory    Accuracy   Burst Handling   Complexity
─────────────────────────────────────────────────────────────────
Fixed Window       1 counter  Boundary   Allows 2x        Simple
                   per user   problem    at boundary

Sliding Window     2 counters Smooth     Controlled        Moderate
Counter            per user   boundary

Token Bucket       2 values   Good       Allows up to      Moderate
                   per user              bucket capacity

Leaky Bucket       Queue      Perfect    No bursts         Complex
                   per user   smoothing  (constant rate)
```

## What Production Systems Actually Use

```
AWS API Gateway:      Token bucket
Stripe:               Token bucket (with per-second and per-day limits)
GitHub API:           Fixed window (simple, resets on the hour)
Nginx:                Leaky bucket (ngx_http_limit_req_module)
Redis + custom:       Sliding window counter (most flexible)

Most common: Token bucket — because it balances burst tolerance
with sustained rate enforcement, and it's easy to explain to users:
"You get 100 requests per minute, with bursts up to 20 at once."
```

The core insight: every rate limiting algorithm is just a different answer to "how do we count requests over time?" The trade-offs are always between memory usage, boundary accuracy, burst tolerance, and implementation complexity.'''
    ),
    (
        "thinking/firstprinciples-why-utf8-exists",
        "Why does UTF-8 exist? Why can't we just use ASCII for everything? I keep running into encoding errors and I want to understand the root cause, not just fix the symptoms.",
        r'''<think>
UTF-8 from first principles. Start from the root problem: how do computers represent text?

**Step 1: The fundamental constraint**
Computers store numbers (bytes). To represent text, we need a mapping: number → character.

**Step 2: ASCII (1963)**
7 bits = 128 possible characters.
0-31: control characters (newline, tab, bell)
32-126: printable (A-Z, a-z, 0-9, punctuation)
127: delete

This was enough for American English. But the world has thousands of characters.

**Step 3: The problem**
- Chinese: ~50,000+ characters
- Japanese: 2,000+ kanji + kana
- Arabic: 28 letters + contextual forms
- Emoji: 3,000+
- 128 slots is absurdly insufficient

**Step 4: Early attempts**
Extended ASCII (8 bits = 256 characters): Different regions made incompatible standards.
- Latin-1 (ISO 8859-1): Western European
- Latin-2 (ISO 8859-2): Central European
- Shift-JIS: Japanese
- Big5: Traditional Chinese

Problem: the same byte value meant different characters in different encodings. File from Japan opened in Europe → garbage.

**Step 5: Unicode — the universal catalog**
Solution: assign a unique number (code point) to EVERY character in EVERY language.
U+0041 = A, U+4E16 = 世, U+1F600 = 😀

Currently ~150,000 characters across 160+ scripts.

But: how do you store these numbers in bytes? A code point like U+1F600 = 128,512 in decimal. That needs at least 3 bytes. If every character takes 3-4 bytes, ASCII text (English) doubles or quadruples in size.

**Step 6: UTF-8 — the brilliant encoding**
Key insight by Ken Thompson: make the byte length variable.
- ASCII characters (U+0000-007F): 1 byte — IDENTICAL to ASCII
- Latin/Greek/Cyrillic (U+0080-07FF): 2 bytes
- Chinese/Japanese/Korean (U+0800-FFFF): 3 bytes
- Emoji and rare scripts (U+10000-10FFFF): 4 bytes

This means:
- Existing ASCII files are ALREADY valid UTF-8 (backwards compatible!)
- English text is the same size as ASCII
- Other languages use 2-3 bytes per character (reasonable trade-off)
- Every character in every language can be represented

The encoding is self-synchronizing: you can look at any byte and determine:
- Is it a single-byte character (starts with 0)?
- Is it the start of a multi-byte sequence (starts with 11)?
- Is it a continuation byte (starts with 10)?

This is why UTF-8 won. It's backwards compatible, space efficient for common cases, universal, and self-synchronizing.
</think>

Let me trace the path from the root problem to why UTF-8 is the way it is.

## The Root Problem

```
Computers store numbers. Text is not numbers.
We need a mapping: number ↔ character.

The question: how many numbers do we need?
```

## Step 1: ASCII (1963) — English is Enough, Right?

```
7 bits = 128 slots

  0-31:    Control characters (newline, tab, escape)
  32-126:  Printable characters:
           ABCDEFGHIJKLMNOPQRSTUVWXYZ  (26)
           abcdefghijklmnopqrstuvwxyz  (26)
           0123456789                  (10)
           !@#$%^&*()+-=[]{}|;:'",.<>?/`~  (33)
           space                       (1)
  127:     DELETE

  Total printable: 95 characters

  "Hello" = 72 101 108 108 111
  Each character = 1 byte. Simple. Efficient.
```

```
Problem: the world has more than 95 characters.

  Chinese:    50,000+ characters    (汉字)
  Japanese:   2,000+ kanji + kana  (漢字 + ひらがな)
  Korean:     11,000+ syllables     (한글)
  Arabic:     28 + contextual forms (العربية)
  Hindi:      46+ characters        (हिन्दी)
  Emoji:      3,600+                (😀🎉🚀)

  128 slots is absurdly insufficient.
```

## Step 2: Everyone Made Their Own Standard (Chaos)

```
"Just use 8 bits (256 slots) and assign the extra 128 however you want!"

Result — INCOMPATIBLE regional standards:

  Byte value 0xC4:
    Latin-1 (Western Europe): Ä
    Latin-2 (Central Europe): Ä (happened to agree here)
    Windows-1251 (Russian):  Д
    Shift-JIS (Japanese):    (part of a 2-byte sequence)

  Same file, same bytes, different text depending on which
  encoding your computer assumed.

  Japanese email opened in Europe → ÃƒÂ£Ãƒâ€šÃ‚Â³Ãƒâ€šÃ‚Â³  (mojibake)
  Russian webpage in Latin-1    → ÐŸÑ€Ð¸Ð²ÐµÑ‚          (mojibake)
```

## Step 3: Unicode — One Catalog to Rule Them All

```
Solution: assign a UNIQUE number to EVERY character in EVERY language.

  U+0041 = A          (Latin)
  U+0410 = А          (Cyrillic)
  U+4E16 = 世         (Chinese)
  U+AC00 = 가         (Korean)
  U+0905 = अ          (Devanagari)
  U+1F600 = 😀        (Emoji)

  Currently: ~150,000 characters from 160+ scripts
  Capacity: 1,114,112 code points (U+0000 to U+10FFFF)

  Now EVERY character has ONE unambiguous identity.
  But how do we store these numbers in bytes?
```

## Step 4: The Storage Problem

```
U+0041 (A)    = 65        → fits in 1 byte
U+4E16 (世)   = 19,990    → needs 2 bytes
U+1F600 (😀)  = 128,512   → needs 3 bytes

Option A: Fixed width (UTF-32)
  Every character = 4 bytes, always.
  "Hello" = 20 bytes instead of 5 bytes.
  Pure ASCII files become 4x larger. Wasteful.

Option B: Fixed 2-byte width (UTF-16)
  Every character = 2 bytes (mostly).
  "Hello" = 10 bytes. Still 2x larger.
  AND can't represent emoji/rare chars in 2 bytes — needs "surrogate pairs."
  Used by: Windows, Java, JavaScript internally.

Option C: Variable width (UTF-8)        ← THE BREAKTHROUGH
  ASCII characters = 1 byte  (same as before!)
  Other characters = 2-4 bytes (as needed)
  "Hello" = 5 bytes. Same as ASCII!
```

## Step 5: How UTF-8 Actually Encodes (The Clever Bit)

```
The encoding uses prefix bits to signal byte length:

  1 byte:  0xxxxxxx                    → U+0000 to U+007F   (ASCII)
  2 bytes: 110xxxxx 10xxxxxx           → U+0080 to U+07FF
  3 bytes: 1110xxxx 10xxxxxx 10xxxxxx  → U+0800 to U+FFFF
  4 bytes: 11110xxx 10xxxxxx 10xxxxxx 10xxxxxx → U+10000 to U+10FFFF

Example: 世 = U+4E16 = 0100 1110 0001 0110

  Needs 3 bytes (U+0800-FFFF range):
  1110xxxx 10xxxxxx 10xxxxxx

  Fill in the bits:
  1110[0100] 10[111000] 10[010110]
  = E4       B8        96
  = 0xE4B896

  In Python: '世'.encode('utf-8') → b'\xe4\xb8\x96'  (3 bytes)
  Compare:   'A'.encode('utf-8')  → b'\x41'           (1 byte, same as ASCII!)
```

## Why Your Encoding Errors Happen

```python
# THE ROOT CAUSE of most encoding errors:

# 1. Mismatch: file written in one encoding, read as another
data = b'\xe4\xb8\x96'           # UTF-8 bytes for 世
data.decode('latin-1')            # → 'ä¸\x96'  (MOJIBAKE!)
data.decode('utf-8')              # → '世'       (correct)

# 2. Mixing bytes and strings
text = "Hello 世界"
text.encode('ascii')              # UnicodeEncodeError! 世 isn't ASCII

# 3. Database/file doesn't declare encoding
# Python 2 defaulted to ASCII → constant errors
# Python 3 defaults to UTF-8 → mostly works

# THE FIX (always):
# - Encode to UTF-8 when writing: text.encode('utf-8')
# - Decode from UTF-8 when reading: bytes.decode('utf-8')
# - Set UTF-8 everywhere: database, files, HTTP headers
# - Never assume ASCII
```

## Why UTF-8 Won

```
1. BACKWARDS COMPATIBLE: ASCII files are already valid UTF-8
   (no migration needed for existing English text)

2. SPACE EFFICIENT: English text = same size as ASCII
   (no overhead for the most common case on the internet)

3. SELF-SYNCHRONIZING: you can jump to any byte and determine
   if it's a character start or continuation
   (robust against stream corruption)

4. NO BYTE ORDER ISSUES: UTF-16/32 need BOM markers
   (UTF-8 is the same on big-endian and little-endian machines)

5. UNIVERSAL: represents every character ever assigned
   (no more regional encoding chaos)

Today: 98%+ of web pages use UTF-8. It's the default everywhere.
The encoding wars are over. UTF-8 won.
```'''
    ),
    (
        "thinking/firstprinciples-why-databases-need-transactions",
        "Why do databases have transactions? What problem do they actually solve? I use BEGIN/COMMIT but I don't really understand why the database can't just execute my queries one at a time.",
        r'''<think>
Database transactions from first principles. Why can't we just run queries one at a time?

**The fundamental problem:**
A database serves multiple users simultaneously, and operations often involve multiple steps. Without transactions, partial failures and concurrent access create data corruption.

**Scenario 1: Partial failure**
Transfer $100 from Account A to Account B:
1. UPDATE accounts SET balance = balance - 100 WHERE id = 'A';
2. UPDATE accounts SET balance = balance + 100 WHERE id = 'B';

What if the server crashes between step 1 and step 2?
- Account A lost $100
- Account B didn't receive it
- $100 vanished from the system

We need ATOMICITY: either both happen or neither happens.

**Scenario 2: Concurrent access**
Two transfers happening simultaneously:
- Transfer 1: A → B ($100)
- Transfer 2: A → C ($100)
- Account A has $150

Without isolation:
1. T1 reads A: $150 ✓
2. T2 reads A: $150 ✓
3. T1 writes A: $150 - $100 = $50
4. T2 writes A: $150 - $100 = $50 (should be $50 - $100 = -$50 or rejected!)
Both transfers succeed. A now has $50 but should have -$50 or T2 should have been rejected.

We need ISOLATION: transactions shouldn't interfere with each other.

**Scenario 3: What does "saved" mean?**
After a COMMIT, the database must guarantee the data survives crashes, power outages, disk failures. If I deposit money and the database says "done," it must be there when I check later.

We need DURABILITY: committed data survives failures.

**Scenario 4: Maintaining rules**
A banking system has a rule: total money in the system must be constant (no money creation or destruction). Every valid transaction must maintain this invariant.

We need CONSISTENCY: transitions from one valid state to another.

This gives us ACID:
- Atomicity: all or nothing
- Consistency: valid state → valid state
- Isolation: concurrent transactions don't interfere
- Durability: committed = permanent
</think>

Transactions exist because **real operations require multiple steps, and the world is concurrent and failure-prone**. Let me derive this from scenarios.

## The Problem: Multi-Step Operations

```sql
-- Transfer $100 from Alice to Bob
-- This REQUIRES two operations:
UPDATE accounts SET balance = balance - 100 WHERE user = 'Alice';
UPDATE accounts SET balance = balance + 100 WHERE user = 'Bob';

-- "Just execute them one at a time" — what could go wrong?
```

## Problem 1: Crash Between Steps (→ Need Atomicity)

```
Without transaction:
  Step 1: Alice: $500 → $400    ✓ Written to disk
  --- SERVER CRASHES ---
  Step 2: Bob: $300 → ???       ✗ Never executed

  Result: Alice lost $100. Bob didn't get it.
  $100 vanished from the system.

With transaction:
  BEGIN;
  Step 1: Alice: $500 → $400    (written to log, not finalized)
  --- SERVER CRASHES ---
  Database restarts → sees incomplete transaction → ROLLS BACK
  Alice: still $500. Bob: still $300.

  ATOMICITY: "all or nothing" — partial execution is impossible
```

## Problem 2: Simultaneous Access (→ Need Isolation)

```
Alice has $150. Two transfers happen at the same time:
  Transfer 1: Alice → Bob   ($100)
  Transfer 2: Alice → Carol  ($100)

Without isolation:
  T1 reads Alice:  $150         (enough for $100)
  T2 reads Alice:  $150         (enough for $100) ← stale!
  T1 writes Alice: $150 - $100 = $50
  T2 writes Alice: $150 - $100 = $50  ← OVERWRITES T1's result!

  Result: $200 transferred out of a $150 account.
  Alice has $50 (should be -$50 or T2 should fail).
  Bob got $100. Carol got $100. Bank lost $50.

With isolation:
  BEGIN T1;
  T1 LOCKS Alice's row → reads $150 → writes $50 → COMMIT → UNLOCK
  BEGIN T2;
  T2 LOCKS Alice's row (waits for T1) → reads $50 → $100 > $50 → FAILS

  Result: Only valid transfer succeeds.

  ISOLATION: transactions see consistent data, not partial updates
```

## Problem 3: "Did It Really Save?" (→ Need Durability)

```
Without durability guarantee:
  You deposit $1000 at the ATM.
  Screen says: "Deposit successful!"
  Power outage at the bank's data center.
  Power restored. Your $1000 is gone. "No record of that deposit."

With durability:
  COMMIT doesn't return until the data is on durable storage.
  Write-Ahead Log (WAL): changes are written to disk log BEFORE
  the response is sent.

  Power outage → restart → replay the log → data is recovered.

  DURABILITY: once COMMIT returns, the data survives any failure
```

## Problem 4: Maintaining Invariants (→ Need Consistency)

```sql
-- Business rule: account balance must never go below 0
-- Constraint: CHECK (balance >= 0)

BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE user = 'Alice';
-- If Alice has $50, this would make balance = -$50
-- Database checks constraint → VIOLATION → entire transaction ROLLS BACK
COMMIT;  -- Never reached

-- CONSISTENCY: database moves from one valid state to another
-- Invalid intermediate states are never visible to other transactions
```

## These Four Properties = ACID

```
A - Atomicity:    All steps succeed or all are rolled back
C - Consistency:  Constraints and rules are always maintained
I - Isolation:    Concurrent transactions don't see each other's partial work
D - Durability:   Committed data survives crashes

Without ACID:
  Every application would need to handle:
    - Crash recovery logic (retry/undo partial operations)
    - Locking and concurrency control
    - Constraint enforcement
    - Durable storage guarantees

  Transactions push this complexity INTO the database
  so applications don't have to solve it themselves.
```

## What Happens Without Transactions (Real Bugs)

```python
# ❌ No transaction — race condition
def purchase(user_id, item_id):
    stock = db.query("SELECT stock FROM items WHERE id = %s", item_id)
    if stock > 0:
        # Another request might decrement stock between these two queries!
        db.execute("UPDATE items SET stock = stock - 1 WHERE id = %s", item_id)
        db.execute("INSERT INTO orders (user_id, item_id) VALUES (%s, %s)",
                   user_id, item_id)
    # Bug: two users buy the last item → stock goes to -1

# ✅ Transaction — atomic and isolated
def purchase(user_id, item_id):
    with db.transaction():  # BEGIN
        # FOR UPDATE locks the row — other transactions wait
        stock = db.query(
            "SELECT stock FROM items WHERE id = %s FOR UPDATE", item_id
        )
        if stock > 0:
            db.execute("UPDATE items SET stock = stock - 1 WHERE id = %s", item_id)
            db.execute("INSERT INTO orders (user_id, item_id) VALUES (%s, %s)",
                       user_id, item_id)
        else:
            raise OutOfStockError()
    # COMMIT — both updates are atomic, no race condition possible
```

## Summary

```
"Why can't the database just execute queries one at a time?"

It CAN — but YOUR operations aren't one query.
They're multi-step processes that must:
  1. All succeed or all fail        (Atomicity)
  2. Maintain business rules         (Consistency)
  3. Not corrupt each other          (Isolation)
  4. Actually persist                 (Durability)

Transactions are the database saying:
"Give me a group of operations, and I GUARANTEE
they'll execute correctly, completely, and permanently
— even if the server crashes or 1000 users hit it at once."
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
