"""Phase 3B: Metacognition — Teaching Through Guided Discovery (Part 6)

Training the model to help users learn concepts through guided exploration
rather than direct instruction, using the Socratic method.
"""

PAIRS = [
    (
        "thinking/meta-socratic-teach-recursion",
        r'''I don't understand recursion. I've read the textbook definition but it doesn't click. Can you explain it?''',
        r'''<think>
The user has already read explanations and they didn't work. Giving another explanation won't help. Instead, I should guide them to discover recursion through experience.

Socratic approach for teaching:
1. Start with something they already understand
2. Ask questions that reveal the recursive structure
3. Let them see the pattern before naming it
4. Build from concrete to abstract

Key insight: most people understand recursion intuitively in non-programming contexts (Russian nesting dolls, mirrors reflecting mirrors, family trees). The gap is connecting intuition to code.

I'll guide them through a concrete example step by step, asking questions at each step so they discover the pattern.
</think>

Let's try a different approach. Instead of me explaining, I'll ask you questions and you'll discover it.

**Start here — no code yet:**

You have a pile of 10 books and you want to count them. But here's the constraint: you can only look at ONE book at a time (the top one). You can't see the whole pile.

How would you count them?

Most people say: "Take the top book off, and count what's left, then add 1."

**Question 1:** If you use that strategy, what happens when you take a book off?
- You now have 1 book in hand, and a pile of... how many books?
- How do you count the remaining pile?

*You'd use the same strategy again.* Take the top book off, count what's left, add 1.

**Question 2:** When do you stop?
- When there are no books left, the count is 0.

You just described recursion. Let me write exactly what you said:

```python
def count_books(pile):
    if pile is empty:        # When do I stop? (base case)
        return 0
    else:
        take top book off    # Handle one item
        return 1 + count_books(remaining_pile)  # Same strategy on the rest
```

**Now let's make it real:**

```python
def count_items(items):
    if len(items) == 0:      # Base case: empty pile
        return 0
    return 1 + count_items(items[1:])  # Count rest, add 1

count_items(["a", "b", "c", "d"])
```

**Question 3 — trace through this yourself:**
```
count_items(["a", "b", "c", "d"])
  = 1 + count_items(["b", "c", "d"])
  = 1 + (1 + count_items(["c", "d"]))
  = 1 + (1 + (1 + count_items(["d"])))
  = 1 + (1 + (1 + (1 + count_items([]))))
  = 1 + (1 + (1 + (1 + 0)))
  = 4
```

**The pattern you just learned:**

Every recursive solution has exactly two parts:
1. **Base case:** When do I stop? (empty pile → 0)
2. **Recursive case:** How do I reduce the problem? (handle one item, recurse on the rest)

**Question 4 — try this yourself:**

Write a function to sum a list of numbers, using the same pattern:
- Base case: empty list → what's the sum?
- Recursive case: take the first number, add it to the sum of the rest

```python
def sum_list(numbers):
    if ___:           # base case
        return ___
    return ___ + sum_list(___)  # first number + sum of rest
```

Fill in the blanks. Once you do, you understand recursion.'''
    ),
    (
        "thinking/meta-socratic-teach-big-o",
        r'''Why is O(n^2) bad? My code works fine and it's fast enough.''',
        r'''<think>
The user doesn't see why algorithmic complexity matters because their current data set is small enough. Rather than lecturing about Big-O, I should guide them to discover the problem themselves through concrete numbers.

Socratic approach:
1. Validate their current experience (it IS fine for small data)
2. Ask them to predict what happens as data grows
3. Let the numbers shock them into understanding
4. Connect it back to real scenarios they might encounter

The key insight: O(n^2) is fine for n=100 (10,000 operations) but devastating for n=100,000 (10,000,000,000 operations). The user needs to FEEL this difference, not just hear about it.
</think>

You're right that it works now. Let me ask you some questions and let's see if you still feel the same way.

**Question 1: How much data do you have right now?**

Let's say it's 1,000 items. Your O(n^2) code does about 1,000,000 operations. On a modern computer, that takes maybe 10 milliseconds. Totally fine.

**Question 2: What happens when your data grows?**

Fill in this table mentally:

```
Items (n)  │ O(n) operations │ O(n^2) operations │ Time at 1B ops/sec
───────────┼─────────────────┼───────────────────┼───────────────────
      100  │            100  │           10,000  │ instant
    1,000  │          1,000  │        1,000,000  │ 1 ms
   10,000  │         10,000  │      100,000,000  │ 100 ms
  100,000  │        100,000  │   10,000,000,000  │ 10 seconds
1,000,000  │      1,000,000  │ 1,000,000,000,000 │ 16 minutes
```

**Question 3: Is it possible your data will ever reach 100K items?**

- User accounts in a growing app?
- Log entries over months?
- Products in a catalog?
- Rows returned from a database query?

If yes, your "fast enough" code becomes a 10-second hang or a 16-minute timeout.

**Question 4: Can you see this in practice?**

Try it yourself:
```python
import time

def find_duplicates_n2(items):
    """O(n^2) — compare every pair"""
    dupes = []
    for i in range(len(items)):
        for j in range(i+1, len(items)):
            if items[i] == items[j]:
                dupes.append(items[i])
    return dupes

def find_duplicates_n(items):
    """O(n) — use a set"""
    seen = set()
    dupes = []
    for item in items:
        if item in seen:
            dupes.append(item)
        seen.add(item)
    return dupes

# Test with increasing sizes
for size in [1000, 10000, 50000, 100000]:
    data = list(range(size)) + [42]  # one duplicate

    start = time.time()
    find_duplicates_n2(data)
    t_n2 = time.time() - start

    start = time.time()
    find_duplicates_n(data)
    t_n = time.time() - start

    print(f"n={size:>7}: O(n^2)={t_n2:.3f}s  O(n)={t_n:.6f}s  ratio={t_n2/t_n:.0f}x")
```

**Run that code.** The numbers will surprise you.

**The takeaway isn't "O(n^2) is always bad."** It's:
- For n < 1000: O(n^2) is almost always fine
- For n > 10,000: O(n^2) starts to hurt
- For n > 100,000: O(n^2) is a production incident waiting to happen
- The question is: **will your n grow?**'''
    ),
    (
        "thinking/meta-socratic-teach-dependency-injection",
        r'''What is dependency injection and why would I use it? I keep hearing about it but it seems like over-engineering.''',
        r'''<think>
The user thinks DI is over-engineering, which means they haven't encountered the problem it solves. Instead of explaining the pattern abstractly, I should show them a problem they'll recognize and let them discover the solution.

Socratic approach:
1. Present code they'd write naturally (without DI)
2. Ask them to test it — reveal the problem
3. Ask them to fix it — they'll invent DI themselves
4. Name what they just invented

The "aha moment" comes when they try to test code that directly creates its dependencies and realize they can't substitute a fake database or API.
</think>

Let me show you some code and ask you a question. Don't think about patterns — just look at it as a developer.

**Here's a function:**
```python
import stripe

class OrderService:
    def process_order(self, order):
        # Calculate total
        total = sum(item.price * item.quantity for item in order.items)

        # Charge the customer's credit card
        stripe.Charge.create(
            amount=int(total * 100),
            currency='usd',
            source=order.payment_token
        )

        # Save to database
        db = psycopg2.connect("postgresql://prod-server/orders")
        cursor = db.cursor()
        cursor.execute("INSERT INTO orders ...", order.data)
        db.commit()

        return {"status": "success", "total": total}
```

**Question 1: How would you write a test for this function?**

Think about it. What happens when your test runs?
- It charges a REAL credit card (Stripe API call)
- It writes to the PRODUCTION database
- You can't test the logic without these side effects

**Question 2: How would you fix this?**

What if, instead of creating the Stripe client and DB connection inside the function, you passed them in?

```python
class OrderService:
    def __init__(self, payment_client, database):
        self.payment = payment_client
        self.db = database

    def process_order(self, order):
        total = sum(item.price * item.quantity for item in order.items)
        self.payment.charge(total, order.payment_token)
        self.db.save_order(order.data)
        return {"status": "success", "total": total}
```

Now you can test it:
```python
def test_process_order():
    fake_payment = FakePaymentClient()  # Doesn't charge real cards
    fake_db = FakeDatabase()            # Doesn't hit real database

    service = OrderService(fake_payment, fake_db)
    result = service.process_order(test_order)

    assert result["total"] == 42.00
    assert fake_payment.charges == [4200]
    assert fake_db.saved_orders == [test_order.data]
```

**Question 3: Do you see what you just did?**

You "injected" the dependencies (payment client, database) from outside instead of creating them inside. That's dependency injection. That's the whole thing.

**It's not about:**
- Complex frameworks
- XML configuration files
- Abstract factory patterns
- Enterprise architecture astronautics

**It IS about:**
- Passing things in instead of creating them inside
- So you can swap them for testing
- So you can change them without modifying the class
- So each piece of code has a single responsibility

**When is it "over-engineering"?**
- Simple scripts that don't need testing: skip it
- Functions with no external dependencies: skip it
- Code that will never be reused or tested: probably skip it

**When is it essential?**
- Code that talks to databases, APIs, file systems
- Code you need to test
- Code that multiple teams work on
- Code that needs different behavior in different environments

You were probably already doing dependency injection without knowing it — every time you pass a database connection to a function instead of creating it inside.'''
    ),
    (
        "thinking/meta-socratic-teach-git-merge",
        r'''I'm confused about git merge vs rebase. Everyone on my team has a different opinion. Which should I use?''',
        r'''<think>
This is a contentious topic where people have strong opinions. Rather than taking a side, I should help the user understand the tradeoffs so they can make their own informed decision.

Socratic approach:
1. Show them what each does visually
2. Ask them what they value (clean history vs accuracy)
3. Help them see when each is appropriate
4. Guide them to a team convention

The key insight: merge and rebase produce the same CODE, but different HISTORY. The choice is about what you want your git log to look like and what tradeoffs you accept.
</think>

Rather than giving you my opinion, let me help you form your own. Answer these questions.

**First, understand what each does:**

```
Your branch:  A → B → C (your commits)
Main branch:  A → D → E (other people's commits)
```

**Merge creates a merge commit:**
```
A → B → C → M  (your branch, M = merge commit)
 \         ↗
  → D → E
```
History shows: "these branches existed and were combined here"

**Rebase replays your commits on top:**
```
A → D → E → B' → C'  (your commits replayed after main)
```
History shows: a straight line, as if you wrote your code after D and E

**Question 1: Do you value accurate history or clean history?**

- **Accurate history (merge):** The git log shows exactly what happened — branches were created, work happened in parallel, branches were merged. Good for understanding "what was the team doing at this point in time?"

- **Clean history (rebase):** The git log reads like a linear story. Easy to follow, easy to bisect, but it rewrites the actual sequence of events. Good for "what changes were made and in what order?"

**Question 2: Try this experiment.**

Look at a project with many merges:
```bash
git log --oneline --graph  # With merges: shows branch structure
```
Is it readable or a tangled mess?

Now look at a project that rebases:
```bash
git log --oneline  # After rebase: clean linear list
```

Which do you prefer reading?

**Question 3: How big are your branches?**

- Small, short-lived branches (1-3 commits, merged within a day): rebase works great — clean, simple
- Large, long-lived branches (weeks of work): rebase can be painful — conflicts at every commit during rebase vs once during merge

**The pragmatic convention most teams adopt:**

```
Pull from main:     git pull --rebase  (keep your local commits on top)
Update feature branch: git rebase main  (before opening PR)
Merge PR to main:   Squash merge or merge commit (team preference)
```

```
Rule of thumb:
- Rebase YOUR unpublished commits (haven't been pushed)
- Never rebase commits others have based work on
- Use merge for integrating shared branches
```

**Question 4: What does your team's PR workflow look like?**

Tell me that, and I'll suggest the specific convention that fits. The "right answer" depends on your team's workflow, not on abstract principles.'''
    ),
    (
        "thinking/meta-socratic-teach-database-indexes",
        r'''My database queries are slow but I don't really understand indexes. How do indexes make queries faster?''',
        r'''<think>
This is a great opportunity for guided discovery. Most people understand the concept of an index in a book — I can use that analogy and then extend it to databases.

Socratic approach:
1. Start with something they already understand (book index)
2. Extend the analogy to databases
3. Let them discover the tradeoffs (write overhead)
4. Show concrete impact with EXPLAIN

The key realization: without an index, the database reads every single row. With an index, it jumps directly to the matching rows. The analogy to a book index is nearly perfect.
</think>

Let me ask you a question first.

**Question 1: You have a 500-page textbook. Find every page that mentions "PostgreSQL."**

How would you do it?

**Option A:** Read every page from 1 to 500, noting which ones mention PostgreSQL.
**Option B:** Flip to the index at the back, look up "PostgreSQL", find "pages 42, 87, 155, 301."

Which is faster? Obviously B. How much faster? Instead of reading 500 pages, you read 1 page (the index) and then go directly to 4 pages. That's 5 reads instead of 500.

**You now understand database indexes.**

```sql
-- Option A: No index (reads every row — "full table scan")
-- Database checks ALL 1,000,000 rows to find matches
SELECT * FROM users WHERE email = 'alice@example.com';
-- Time: 800ms (reads 1,000,000 rows)

-- Option B: With index
CREATE INDEX idx_users_email ON users(email);
-- Now the same query:
SELECT * FROM users WHERE email = 'alice@example.com';
-- Time: 0.5ms (looks up index → jumps to 1 row)
```

**Question 2: If indexes make everything faster, why not index every column?**

Think about the book analogy again. What if your textbook had an index for every single word?
- The index would be bigger than the book itself
- Every time you added a page, you'd need to update every index entry

Same with databases:
```
Trade-off:
  Reads:  Faster (index lookup instead of full scan)
  Writes: Slower (must update the index on every INSERT/UPDATE)
  Space:  More disk usage (index takes space)
```

**Question 3: How do you know which columns to index?**

Ask yourself: "Which columns appear in WHERE clauses, JOIN conditions, and ORDER BY?"

```sql
-- This query needs an index on 'status' and 'created_at':
SELECT * FROM orders
WHERE status = 'pending'
ORDER BY created_at DESC;

CREATE INDEX idx_orders_status_created ON orders(status, created_at DESC);
```

**See it for yourself:**
```sql
-- Before index:
EXPLAIN ANALYZE SELECT * FROM orders WHERE status = 'pending';
-- Look for: "Seq Scan" (reading every row) and execution time

-- After index:
CREATE INDEX idx_orders_status ON orders(status);
EXPLAIN ANALYZE SELECT * FROM orders WHERE status = 'pending';
-- Look for: "Index Scan" (using the index) and execution time
```

**The rules of thumb:**
1. Always index foreign keys (columns used in JOINs)
2. Index columns you filter on frequently (WHERE clauses)
3. Index columns you sort by (ORDER BY)
4. Don't index columns with very few distinct values (boolean columns rarely benefit)
5. Don't index columns on small tables (scanning 100 rows is fast anyway)

**Try this:** Run `EXPLAIN ANALYZE` on your slowest query. Does it show "Seq Scan" on a large table? If yes, that column needs an index.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
