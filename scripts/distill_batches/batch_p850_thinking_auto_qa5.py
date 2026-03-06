"""Phase 4F: Self-Improvement — Quality Assurance (Part 5)

Quality checklists for debugging assistance — ensuring debugging advice
is systematic, safe, and leads to root cause resolution.
"""

PAIRS = [
    (
        "thinking/auto-qa-debugging-systematic-checklist",
        r'''What quality checklist should I run before giving debugging advice to ensure I'm helping the user find the root cause, not just treating symptoms?''',
        r'''<think>
Debugging advice quality is about ensuring we find the ROOT CAUSE, not just a workaround. Common failure modes:

1. Suggesting fixes without understanding the problem
2. Treating symptoms instead of causes
3. Assuming the user's diagnosis is correct
4. Suggesting changes that mask the bug instead of fixing it
5. Not verifying that the fix actually addresses the root cause

**Quality checklist needs:**
- Verify we understand the problem before suggesting fixes
- Ensure we're addressing root cause, not symptoms
- Verify the fix doesn't introduce new problems
- Ensure the user can verify the fix worked
</think>

**Debugging Assistance Quality Checklist**

**Before giving ANY debugging advice, verify:**

**Phase 1: Understanding the Problem**
```
□ REPRODUCTION: Can the user reproduce the problem?
  If not reproducible → gathering more data is the first step,
  not suggesting fixes.

□ ACTUAL vs. EXPECTED: Do I know both?
  "What happens?" AND "What should happen?"
  If either is unclear, ask before diagnosing.

□ CONTEXT: Do I know the environment?
  - Language and version
  - Framework and version
  - Operating system
  - Recent changes (deploys, config changes, dependency updates)

□ ISOLATION: Is the problem isolated?
  - Does it happen in all environments or just one?
  - Does it happen for all users or just some?
  - Does it happen always or intermittently?
```

**Phase 2: Diagnosis Quality**
```
□ ROOT CAUSE vs. SYMPTOM: Am I addressing the cause?
  Symptom: "The API returns 500"
  Root cause: "The database connection pool is exhausted because
              connections aren't being returned after errors"

  Fix for symptom: Add a retry (WRONG — makes it worse)
  Fix for root cause: Add connection cleanup in error handlers

□ MULTIPLE HYPOTHESES: Have I considered more than one cause?
  Never commit to the first hypothesis. Generate at least 3
  possible causes before investigating.

□ EVIDENCE-BASED: Is my diagnosis based on evidence or assumption?
  BAD: "It's probably a race condition" (assumption)
  GOOD: "The logs show request A writing to DB at T1 and
         request B reading at T1+2ms, suggesting a race condition"
         (evidence)

□ NOT ASSUMING USER'S DIAGNOSIS: Have I verified their hypothesis?
  User: "I think it's a memory leak"
  Me: Don't jump to memory leak fixes. Verify first:
      "What makes you think it's a memory leak? What symptoms
       are you seeing?"
```

**Phase 3: Fix Quality**
```
□ FIX ADDRESSES ROOT CAUSE: Not a workaround?
  Workaround: "Add a try/except to catch the error"
  Fix: "The error happens because X is null when Y expects
       a value. Initialize X before calling Y."

□ FIX DOESN'T INTRODUCE NEW BUGS:
  - Does the fix change behavior for other code paths?
  - Does the fix have performance implications?
  - Does the fix handle the error case properly?

□ FIX IS VERIFIABLE:
  - How does the user confirm the fix works?
  - Is there a test they can write?
  - Is there a log message or metric that changes?

□ FIX IS MINIMAL:
  - Does the fix change only what's necessary?
  - Could a simpler fix work?
```

**Phase 4: Prevention**
```
□ PREVENTION MENTIONED: How to prevent this class of bug?
  "Add a test that covers this edge case"
  "Add input validation to reject null values"
  "Add monitoring to alert on connection pool exhaustion"

□ UNDERSTANDING SHARED: Does the user understand WHY it broke?
  Not just "change line 42" but "line 42 fails because
  the function assumes X, which isn't true when Y happens"
```

**The meta-principle:** Good debugging advice helps the user understand the problem, not just fix it. If the user can't explain WHY the fix works, they'll hit the same class of bug again. Always share the reasoning, not just the fix.'''
    ),
    (
        "thinking/auto-qa-debugging-error-message-analysis",
        r'''What quality checks should I apply when helping someone interpret an error message? How do I ensure I'm reading the error correctly?''',
        r'''<think>
Error message analysis is where many debugging sessions go wrong. Common mistakes:

1. Reading only the top-level error, missing the root cause in the stack trace
2. Googling the error message and applying the first Stack Overflow answer
3. Misinterpreting the error type (e.g., TypeError might mean None was passed, not a type mismatch)
4. Not reading the full stack trace to find WHERE the error originated
5. Confusing the symptom error with the cause error

**Quality checks needed:**
- Read the FULL error, not just the first line
- Identify the originating frame, not just the failing frame
- Understand what the error TYPE means
- Verify the error matches the user's description
</think>

**Error Message Analysis Quality Checklist**

**When a user shares an error message, systematically check:**

**Step 1: Read the complete error**
```
□ FULL STACK TRACE: Did I read the entire trace, not just the last line?
  The root cause is often in the MIDDLE of the stack trace,
  not at the top or bottom.

□ ERROR TYPE: Do I understand what this error type means?
  TypeError: An operation received the wrong type
  ValueError: Right type, wrong value
  KeyError: Dictionary key doesn't exist
  AttributeError: Object doesn't have that attribute
  ImportError: Module not found or has issues
  ConnectionError: Network/database connection failed

□ ERROR MESSAGE: Does the message text match my interpretation?
  "NoneType has no attribute 'split'"
  → Something returned None that was expected to return a string
  → WHERE did the None come from? (That's the real bug)
```

**Step 2: Locate the origin**
```
□ USER CODE vs. LIBRARY CODE: Where does the trace transition
  from library/framework code to the user's code?
  The bug is usually at that boundary.

  Example stack trace:
    File "flask/app.py", line 2551          ← framework
    File "app/routes.py", line 45           ← USER CODE (likely bug)
    File "app/models.py", line 12           ← USER CODE (root cause)
    File "sqlalchemy/orm/query.py", line 3  ← library

  Focus on: app/routes.py:45 and app/models.py:12

□ FIRST ERROR vs. CASCADING ERROR:
  Sometimes the first error causes a chain of failures.
  The FIRST error in the log is usually the root cause.
  Subsequent errors are symptoms.
```

**Step 3: Context verification**
```
□ DOES THE ERROR MATCH THE USER'S DESCRIPTION?
  User says: "My API returns 500"
  Error shows: "FileNotFoundError: config.yaml"
  → The 500 is a symptom. The missing file is the cause.
  → Don't debug the 500. Fix the missing file.

□ IS THE ERROR DETERMINISTIC?
  - Happens every time → Logic error
  - Happens intermittently → Race condition, resource exhaustion,
    or external dependency issue

□ WHEN DID THE ERROR START?
  - After a deploy → Check the diff
  - After a dependency update → Check compatibility
  - Randomly → External factor (load, resource exhaustion)
```

**Step 4: Verify my interpretation**
```
□ REPRODUCE: Can I explain how to trigger this exact error?
  If I can't, I might be misinterpreting it.

□ LINE NUMBERS: Do the line numbers match the code the user shared?
  (Line numbers can drift if the user modified code between
   the error and sharing it)

□ VERSION: Is this error message from the version they're running?
  Error messages change between versions.
```

**Common misinterpretation traps:**
```
TRAP: "TypeError: 'NoneType' object is not subscriptable"
  WRONG interpretation: "The type is wrong"
  RIGHT interpretation: "Something returned None unexpectedly.
                        Find WHERE None came from."

TRAP: "RecursionError: maximum recursion depth exceeded"
  WRONG interpretation: "Increase the recursion limit"
  RIGHT interpretation: "There's an infinite recursion. Find
                        the missing or incorrect base case."

TRAP: "ImportError: cannot import name 'X' from 'Y'"
  WRONG interpretation: "X doesn't exist in Y"
  POSSIBLE: Circular import, not a missing function
```

**The meta-principle:** Error messages are written for the person who wrote the code that throws them, not for the person debugging it. Always translate the error into what it means for the USER'S code, not what it literally says. The error is a clue, not the answer.'''
    ),
    (
        "thinking/auto-qa-debugging-concurrency-issues",
        r'''What quality checks should I apply when helping someone debug concurrency issues like race conditions, deadlocks, or thread-safety problems?''',
        r'''<think>
Concurrency bugs are among the hardest to debug because they're non-deterministic and hard to reproduce. My quality checklist needs to account for this difficulty.

**Special challenges with concurrency debugging:**
1. The bug may not reproduce in development
2. Adding logging/debugging can change timing and hide the bug (Heisenbug)
3. The user may not realize it's a concurrency issue
4. Fixes can introduce new concurrency bugs
5. Testing concurrency fixes is extremely hard

**Quality checks needed:**
- Verify it's actually a concurrency issue (not logic)
- Identify the shared mutable state
- Identify the critical section
- Verify the fix doesn't create deadlocks
- Verify the fix doesn't destroy performance
</think>

**Concurrency Debugging Quality Checklist**

**Before advising on any concurrency issue:**

**Step 1: Confirm it IS a concurrency issue**
```
□ INTERMITTENT: Does the bug happen inconsistently?
  Concurrency bugs are usually non-deterministic.
  If it happens every time, it might be a logic bug.

□ LOAD-DEPENDENT: Does it happen more under heavy load?
  More threads/requests → more chances for race conditions.

□ TIMING-SENSITIVE: Does adding logging/delays change behavior?
  If adding a print statement "fixes" the bug → classic Heisenbug.
  The timing change masks the race condition.

□ IMPOSSIBLE STATE: Does the system reach a state that
  shouldn't be possible sequentially?
  "User balance is -$50 but minimum is $0"
  → Two withdrawals checked balance simultaneously.
```

**Step 2: Identify the shared mutable state**
```
□ WHAT is being shared between threads/processes?
  - Global variables
  - Class attributes
  - Database rows
  - File system
  - Cache entries

□ WHO is reading/writing it?
  - Which code paths access this state?
  - Can they overlap in time?

□ WHAT operations are not atomic?
  "Check then act" patterns are the most common source:
    if balance >= amount:      ← Thread A reads balance
        balance -= amount      ← Thread A writes balance
  But thread B can read balance between these two lines.
```

**Step 3: Evaluate the fix**
```
□ CORRECT: Does the fix protect ALL access to shared state?
  Common mistake: Locking the write but not the read.
  Both reads and writes to shared state need protection.

□ NO DEADLOCK: Does the fix acquire locks in a consistent order?
  Thread A: lock1 → lock2
  Thread B: lock2 → lock1
  → DEADLOCK. Both threads wait for the other's lock.

  Fix: All threads acquire locks in the same order.

□ NO STARVATION: Can all threads make progress?
  If one thread holds a lock too long, others starve.

□ PERFORMANCE: Does the lock granularity make sense?
  - Too coarse (one global lock) → no parallelism
  - Too fine (lock per field) → complex, deadlock risk
  - Right size (lock per logical operation) → balanced

□ ALTERNATIVE TO LOCKS: Would a different approach be simpler?
  - Immutable data structures (no shared mutable state)
  - Message passing (actors, channels)
  - Atomic operations (CAS, atomic counters)
  - Database-level locking (SELECT FOR UPDATE)
```

**Step 4: Verify the fix**
```
□ STRESS TEST: Can the fix be tested under high concurrency?
  Run the operation with 100 concurrent threads.
  If it passes 1000 iterations, it's probably correct.

□ EDGE CASES:
  - What happens if a thread crashes while holding a lock?
  - What happens under extreme load?
  - What happens if the operation takes longer than expected?

□ MONITORING: How will you detect if this bug recurs?
  Add logging/metrics that would reveal the impossible state.
```

**Red flags in concurrency debugging advice:**
```
DANGEROUS:
  - "Just add a sleep(1) to fix the timing" (masks the bug)
  - "Make it single-threaded" (destroys performance without fixing the design)
  - "Just add a lock around everything" (creates performance bottleneck)
  - "It works on my machine" (different timing hides the bug)

BETTER:
  - "Identify the shared mutable state and protect it with [specific mechanism]"
  - "Use an atomic operation instead of check-then-act"
  - "Redesign to avoid shared state entirely using [pattern]"
```

**The meta-principle:** Concurrency bugs are symptoms of shared mutable state. The best fix eliminates the sharing or the mutability, not just the timing window. If you can make the data immutable or eliminate sharing between threads, you eliminate the entire class of bugs, not just the one instance.'''
    ),
    (
        "thinking/auto-qa-debugging-performance-issues",
        r'''What quality checks should I apply when helping someone debug performance problems? How do I ensure I'm identifying the real bottleneck?''',
        r'''<think>
Performance debugging has a critical pitfall: optimizing the wrong thing. If you optimize code that takes 1% of execution time, even a 100x improvement gives <1% total speedup. The quality checklist must ensure we measure before optimizing.

**Key principles:**
1. Measure before optimizing (don't guess)
2. Optimize the bottleneck, not the easy thing
3. Verify the optimization actually helped
4. Don't make the code worse for negligible gain
</think>

**Performance Debugging Quality Checklist**

**Before giving ANY performance advice:**

**Step 1: Measure first (CRITICAL)**
```
□ PROFILED: Has the user actually profiled the code?
  If not → "Profile first, optimize second"
  Don't guess what's slow. Measure it.

□ RIGHT TOOL: Are they using the right profiling tool?
  CPU-bound: cProfile (Python), perf (Linux), flamegraph
  Memory: tracemalloc (Python), valgrind, heaptrack
  I/O-bound: strace, network profiler, DB query analyzer
  Web: Browser DevTools, Lighthouse, WebPageTest

□ BOTTLENECK IDENTIFIED: Do we know WHERE time is spent?
  "The app is slow" → Not actionable
  "Function X takes 800ms of a 1000ms request" → Actionable

□ BASELINE ESTABLISHED: What's the current performance?
  Before optimizing, record: "P95 latency is 1200ms"
  After optimizing, measure: "P95 latency is 340ms"
  Without a baseline, you can't prove the optimization helped.
```

**Step 2: Identify the real bottleneck**
```
□ AMDAHL'S LAW: Is the bottleneck worth optimizing?
  If function X takes 5% of total time:
    Even making it infinitely fast saves only 5%.
    Focus on the function taking 60% of time instead.

□ BOTTLENECK TYPE: What kind of bottleneck is it?
  - CPU-bound: Function doing heavy computation
  - I/O-bound: Waiting for disk, network, or database
  - Memory-bound: Excessive allocation/GC pressure
  - Contention: Threads waiting for locks

  Each type needs a DIFFERENT optimization strategy.
  CPU optimizations don't help I/O-bound code.

□ SYSTEM vs. APPLICATION: Is the bottleneck in the code
  or in the infrastructure?
  - Code: Inefficient algorithm, N+1 queries
  - Infrastructure: Undersized database, network latency, disk IOPS
  Optimizing code won't help if the database server needs more RAM.
```

**Step 3: Evaluate the optimization**
```
□ MEASURED IMPROVEMENT: Did profiling confirm the improvement?
  "I think it's faster" is not evidence.
  "P95 dropped from 1200ms to 340ms" is evidence.

□ COMPLEXITY TRADEOFF: Is the optimization worth the code complexity?
  Saving 2ms by making code 3x harder to read → probably not worth it.
  Saving 500ms by adding a cache → probably worth it.

□ CORRECTNESS: Does the optimized code produce the same results?
  Optimizations that change behavior are bugs, not improvements.
  Especially watch: floating point, ordering, edge cases.

□ SCALABILITY: Does the optimization hold at higher load?
  Some optimizations work at 100 requests/sec but fail at 10,000.
  (e.g., in-memory caching that uses too much RAM at scale)
```

**Step 4: Common performance advice mistakes**
```
RED FLAGS in performance advice:
  "Optimize this loop" (without profiling evidence it matters)
  "Use a faster language" (before optimizing the algorithm)
  "Add caching" (without understanding what to cache or invalidate)
  "Use async" (for CPU-bound work — async doesn't help)

GOOD performance advice:
  "Profile shows 70% of time is in query X. The query
   scans 1M rows because there's no index on column Y.
   Adding an index should reduce query time from 800ms to 5ms.
   Here's how to verify: EXPLAIN ANALYZE [query]"
```

**The optimization hierarchy:**
```
1. Algorithm improvement (O(n^2) → O(n log n)) → 100-1000x
2. Eliminate unnecessary work (remove N+1 queries) → 10-100x
3. Add caching (avoid recomputation) → 2-10x
4. Optimize data structures (list → set for lookups) → 2-10x
5. Low-level optimization (bit tricks, SIMD) → 1.1-2x

Always start from the top. Most performance problems are
solved at levels 1-3. Level 5 is almost never necessary.
```

**The meta-principle:** Premature optimization is the root of all evil, but measured optimization of proven bottlenecks is engineering. The difference is MEASUREMENT. Never optimize without profiling data. Never claim improvement without before/after metrics.'''
    ),
    (
        "thinking/auto-qa-debugging-advice-completeness",
        r'''How do I ensure my debugging advice is complete — that I'm not leaving the user with a partial diagnosis or a fix that only works in some cases?''',
        r'''<think>
Incomplete debugging advice is when you help the user fix one instance of a problem but leave them vulnerable to the same class of problem, or when your fix works for the specific case shown but breaks in other cases.

**Completeness dimensions:**
1. Does the fix handle all variants of the problem?
2. Does the user understand WHY it works?
3. Can the user detect if the problem recurs?
4. Is the fix tested and verifiable?
5. Are related issues addressed?
</think>

**Debugging Advice Completeness Checklist**

**After formulating debugging advice, verify completeness:**

**1. Fix completeness**
```
□ ALL CODE PATHS: Does the fix handle all ways the buggy code
  can be reached?
  If the bug is "null check missing," is null possible from
  ALL callers, or just one?

□ EDGE CASES: Does the fix handle:
  - Empty input
  - Null/undefined values
  - Very large input
  - Concurrent access
  - Error conditions

□ RELATED CODE: Is the same bug pattern present elsewhere?
  "You have the same null-check missing on lines 45, 89, and 112.
   Fix all three, not just the one that's currently crashing."
```

**2. Understanding completeness**
```
□ ROOT CAUSE EXPLAINED: Does the user know WHY the bug exists?
  Not just: "Change line 45 to add a null check"
  But: "Line 45 crashes because function X can return null
       when the database query finds no results. The fix is
       to handle the no-results case."

□ MENTAL MODEL UPDATED: Does the user's understanding of
  the system change?
  "The key insight is that database queries can return null
   even when you expect data to exist. Always handle the
   empty-result case."

□ SIMILAR BUGS PREVENTABLE: Can the user prevent this class
  of bug in future code?
  "Whenever you call a database query, check for null/empty
   results before accessing properties."
```

**3. Verification completeness**
```
□ HOW TO VERIFY: Can the user confirm the fix works?
  "After applying the fix, run: [specific command]
   You should see [expected output].
   If you still see [error], the issue is elsewhere."

□ TEST PROVIDED: Is there a test they can add?
  "Add this test to prevent regression:
   def test_handles_missing_user():
       result = get_user(nonexistent_id)
       assert result is None  # should not raise"

□ MONITORING: How will they know if it recurs?
  "Add a metric for null-result queries so you can track
   how often this edge case actually occurs."
```

**4. Side-effect completeness**
```
□ NO NEW BUGS: Does the fix introduce new problems?
  Adding a null check that returns a default value →
  Does the calling code handle the default correctly?

□ NO PERFORMANCE IMPACT: Does the fix slow things down?
  Adding error handling in a hot loop → measurable impact?

□ BACKWARD COMPATIBLE: Does the fix change the API/behavior
  for other callers?
  If function X now returns null instead of throwing,
  do all callers handle null?
```

**The completeness self-test:**
```
After writing debugging advice, imagine:
1. The user applies the fix
2. It works for their specific case
3. A week later, a SLIGHTLY DIFFERENT version of the bug appears
4. Would your advice have helped them handle this variant too?

If no → your advice solved one instance but not the class of bugs.
Add guidance that addresses the pattern, not just the instance.
```

**Example of incomplete vs. complete advice:**

**INCOMPLETE:**
```
"Add `if user is not None:` before line 45."
(Fixes this crash but user doesn't know why or how to prevent it)
```

**COMPLETE:**
```
"The crash happens because `get_user(id)` returns None when the
user doesn't exist in the database, but line 45 assumes it always
returns a User object.

Fix: Add null handling:
  user = get_user(id)
  if user is None:
      return {'error': 'User not found'}, 404

Prevention: Check all other places where get_user() is called
(lines 89, 112, 156) — they likely have the same bug.

Test: Add a test with a nonexistent user ID to catch this.

Pattern: Any function that queries the database can return None.
Always handle the not-found case."
```

**The meta-principle:** Complete debugging advice addresses four questions: What is the fix? Why does it work? How do I verify it? How do I prevent it from recurring? If any of these is missing, the advice is incomplete.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
