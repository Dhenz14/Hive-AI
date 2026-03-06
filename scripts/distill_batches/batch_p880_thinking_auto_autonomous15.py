"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 15)

Autonomously improving debugging guidance — strategies for
detecting when debugging advice is too vague, misses the root
cause, or fails to provide actionable next steps.
"""

PAIRS = [
    (
        "thinking/auto-autonomous-debug-specificity",
        r'''How can I detect when my debugging advice is too vague to be actionable? What makes debugging guidance specific enough to actually help someone find and fix a bug?''',
        r'''<think>
Vague debugging advice is one of the most common failures in technical assistance. "Check your logs" or "it might be a configuration issue" are technically correct but practically useless. Good debugging advice gives the user a specific action to take, tells them what to look for, and explains what the result means.

The problem is that debugging requires context — the same symptom can have very different causes in different environments. Vague advice is often a sign that I'm not gathering enough context to be specific.
</think>

**Debugging Specificity Framework**

**Vague vs. specific debugging advice**
```
VAGUE (unhelpful):
  "Check your database connection settings."

SPECIFIC (actionable):
  "Run this command to test your database connection:
   psql -h localhost -U myuser -d mydb -c 'SELECT 1'
   If it fails with 'connection refused': the database
   isn't running (check: systemctl status postgresql).
   If it fails with 'authentication failed': your password
   is wrong (check: .env file, DATABASE_URL variable).
   If it succeeds: the connection is fine and the problem
   is in your application's connection pooling configuration."

The specific advice includes:
  ✓ Exact command to run
  ✓ Possible outcomes
  ✓ What each outcome means
  ✓ Next step for each outcome
```

**Detection signals for vague advice**
```
Signal 1: NO SPECIFIC COMMAND OR ACTION
  Vague: "Check your logs for errors"
  Test: Can the user execute this without additional research?
  If they need to figure out WHERE the logs are, the advice is vague.
  Specific: "Check the application log at /var/log/myapp/error.log.
  Search for the timestamp of the failure: grep '2025-11' error.log"

Signal 2: NO EXPECTED OUTCOME
  Vague: "Try restarting the service"
  Test: What should happen after they restart?
  Specific: "Restart the service: systemctl restart myapp.
  Wait 10 seconds, then check: curl http://localhost:8080/health.
  If it returns 200, the issue was transient. If it returns 503,
  check the startup logs: journalctl -u myapp --since '1 min ago'"

Signal 3: NO DIAGNOSTIC TREE
  Vague: "It could be a network issue or a code bug"
  Test: How does the user determine which one?
  Specific: "First, test the network: curl -v https://api.example.com.
  If that works, the network is fine — the bug is in your code.
  If that fails, check DNS: nslookup api.example.com.
  If DNS fails, check /etc/resolv.conf."

Signal 4: LAUNDRY LIST OF POSSIBLE CAUSES
  Vague: "It could be X, Y, Z, or W"
  Test: This gives the user 4 things to investigate with no priority.
  Specific: "Most likely cause: X (check by doing A).
  If that's not it: Y (check by doing B).
  Less likely: Z (only check if A and B passed)."
```

**The specificity checklist**
```
Before giving debugging advice, verify:

□ ACTION: Is there a specific command, check, or step?
□ LOCATION: Does the user know WHERE to look?
□ PATTERN: Does the user know WHAT to look for?
□ INTERPRETATION: Does the user know what the result MEANS?
□ NEXT STEP: Does the user know what to do AFTER?

If any of these are missing, the advice is too vague.
```

**Context gathering before debugging**
```
If you cannot be specific, you need more context.

ESSENTIAL QUESTIONS:
  □ What exactly happens? (error message, behavior)
  □ What did you expect to happen?
  □ When did it start? (what changed?)
  □ Is it consistent or intermittent?
  □ What have you already tried?

WITH ANSWERS, you can be specific.
WITHOUT ANSWERS, any advice is a guess.
Better to ask than to give vague advice.
```

**The meta-principle:** Debugging advice should be a decision tree, not a suggestion list. Each step should tell the user exactly what to do, what to expect, and where to go next based on what they find. If your advice requires the user to fill in the details themselves, you have not actually helped them debug — you have given them a topic to research.'''
    ),
    (
        "thinking/auto-autonomous-debug-root-cause",
        r'''How can I improve my ability to guide users toward root causes rather than just addressing symptoms? What patterns indicate I am helping fix a symptom instead of the underlying problem?''',
        r'''<think>
Symptom-fixing is the most common debugging failure. The user says "my query is slow" and we add an index without asking why the query is slow — maybe it's doing a full table scan because of a missing WHERE clause, maybe it's joining too many tables, or maybe the table has grown because old data isn't being cleaned up.

Root cause analysis requires asking "why" repeatedly and resisting the urge to fix the first thing that looks wrong.

Indicators of symptom-fixing:
1. The fix addresses what's happening but not why
2. The problem will recur in a different form
3. The fix introduces a workaround rather than solving the real issue
</think>

**Root Cause vs. Symptom Detection Framework**

**Symptom-fixing patterns to catch**
```
PATTERN 1: Performance band-aids
  Symptom: "The API is slow"
  Symptom fix: "Add caching"
  Root cause questions:
    - WHY is it slow? (N+1 query? Missing index? Large payload?)
    - Which endpoint is slow? (Is it all of them or specific ones?)
    - When did it become slow? (What changed?)
  Possible root causes:
    - N+1 query → Fix the query, not the cache
    - Missing index → Add the index
    - Unoptimized serialization → Fix the serializer
    - Too much data returned → Add pagination
  Caching may still help, but it hides the real problem.

PATTERN 2: Error suppression
  Symptom: "The application throws an error"
  Symptom fix: "Wrap it in try/catch and log the error"
  Root cause questions:
    - WHY is the error happening?
    - Is the error expected or unexpected?
    - What state leads to this error?
  Possible root causes:
    - Invalid data from upstream → Fix validation at the source
    - Race condition → Fix the concurrency issue
    - Missing null check → Fix the data flow
  Catching and logging hides bugs instead of fixing them.

PATTERN 3: Retry as a fix
  Symptom: "The request sometimes fails"
  Symptom fix: "Add retry logic"
  Root cause questions:
    - WHY does it fail intermittently?
    - Is it a timeout? Connection refused? 500 error?
    - Is it happening under load or randomly?
  Possible root causes:
    - Connection pool exhaustion → Increase pool size or fix leaks
    - Timeout from slow dependency → Optimize the dependency
    - Memory pressure causing GC pauses → Fix memory usage
  Retries mask reliability problems.

PATTERN 4: Restart as a fix
  Symptom: "The service degrades over time"
  Symptom fix: "Schedule periodic restarts"
  Root cause questions:
    - WHY does it degrade?
    - What resource is being exhausted? (memory, connections, handles)
    - How fast does it degrade? (hours? days?)
  Possible root causes:
    - Memory leak → Find and fix the leak
    - Connection leak → Ensure connections are properly closed
    - Cache growing unbounded → Add eviction policy
  Periodic restarts are a workaround, not a solution.
```

**The 5 Whys technique for root cause**
```
Apply "why" iteratively:

Problem: Users are seeing 500 errors
  Why? → The database query is timing out
  Why? → The query is doing a full table scan
  Why? → The table grew from 1M to 50M rows last month
  Why? → Old records are never deleted
  Why? → There is no data retention policy

Root cause: Missing data retention policy
Fix: Implement data archival/deletion for records older than X

Note: The root cause is often organizational or process-related,
not purely technical. The 5 Whys often leads beyond code.
```

**Self-check for root cause analysis**
```
After suggesting a fix, ask:

□ RECURRENCE: Will this problem come back in a different form?
  If yes → you are fixing a symptom.

□ WORKAROUND: Is this a workaround or a real fix?
  Workaround: "Restart the service daily"
  Real fix: "Close database connections in the finally block"

□ GROWTH: Will the fix still work if the system grows 10x?
  If no → you may be addressing a current symptom of a
  scaling problem.

□ SIMILAR ISSUES: Are there similar problems elsewhere in
  the codebase that have the same root cause?
  If yes → fix the pattern, not just this instance.
```

**The meta-principle:** A symptom fix makes the current problem go away. A root cause fix prevents the entire category of problems from occurring. Always guide users past the first "fix that works" toward understanding WHY the problem happened. The five minutes spent on root cause analysis saves hours of recurring debugging.'''
    ),
    (
        "thinking/auto-autonomous-debug-methodology",
        r'''How can I improve the systematic methodology I use when guiding users through debugging? What debugging process should I follow to avoid ad-hoc, scattered advice?''',
        r'''<think>
Systematic debugging methodology is about having a repeatable process rather than relying on intuition and pattern matching alone. While experienced developers often debug by intuition, teaching debugging requires a structured approach that works even when intuition fails.

The core methodology:
1. Reproduce: Confirm the problem exists and is consistent
2. Isolate: Narrow down where the problem occurs
3. Identify: Find the root cause
4. Fix: Apply the correct solution
5. Verify: Confirm the fix works and nothing else broke
</think>

**Systematic Debugging Methodology**

**Phase 1: Reproduce**
```
Before debugging anything, confirm the problem:

□ CAN YOU REPRODUCE IT?
  If yes → proceed to isolation
  If no → it might be intermittent (need more data)

□ REPRODUCTION STEPS:
  Document exact steps to trigger the issue:
  1. Start the application with [configuration]
  2. Send [this specific request]
  3. Observe [this specific error/behavior]

  If you can't write reproduction steps,
  you don't understand the problem yet.

□ ENVIRONMENT MATCH:
  Does the problem occur in:
  - Development? Production? Both?
  - Specific OS/browser/version?
  - Under load? With specific data?

  Environment differences often explain
  "works on my machine" issues.

COMMON MISTAKE: Skipping reproduction and jumping to
"I think the problem might be..." This leads to
fixing things that aren't broken.
```

**Phase 2: Isolate**
```
Narrow down WHERE the problem occurs:

BINARY SEARCH APPROACH:
  Split the system in half. Which half contains the bug?

  Full stack: Client → API → Service → Database
  Test at midpoint: Is the API response correct?
    Yes → problem is in the client
    No → problem is in the API or below

  Continue halving until you find the exact boundary
  where correct data becomes incorrect.

ELIMINATION APPROACH:
  Remove components until the bug disappears:
  - Remove middleware → bug gone? (middleware is the cause)
  - Hardcode the data → bug gone? (data processing is the cause)
  - Use a fresh database → bug gone? (data state is the cause)
  - Run on a different machine → bug gone? (environment is the cause)

TIMELINE APPROACH (for regressions):
  When did it last work?
  What changed between then and now?
  - Code changes (git log, git bisect)
  - Dependency updates
  - Configuration changes
  - Data changes
  - Infrastructure changes
```

**Phase 3: Identify the root cause**
```
Once isolated, find the exact cause:

□ READ THE ERROR MESSAGE:
  Error messages contain specific information:
  - File and line number
  - Variable values
  - Stack trace showing the call path
  Most developers don't read error messages carefully enough.

□ ADD TARGETED LOGGING:
  At the boundary you identified in isolation:
  - Log inputs to the failing function
  - Log intermediate values
  - Log the exact point where behavior diverges

□ USE A DEBUGGER:
  Set a breakpoint at the failing line:
  - Inspect variable values
  - Step through the execution
  - Watch for unexpected state

□ CHECK ASSUMPTIONS:
  List your assumptions about the code:
  - "This variable should be a list" → Is it?
  - "This function returns a string" → Does it?
  - "This config value is set" → Is it?
  Often the bug is in a wrong assumption.
```

**Phase 4: Fix correctly**
```
Apply the right fix:

□ FIX THE ROOT CAUSE, not a symptom (see root cause framework)
□ MINIMAL CHANGE: Change as little as possible
  Large fixes introduce new bugs
□ WRITE A TEST: The test should fail before the fix
  and pass after
□ REVIEW SIMILAR CODE: If this bug exists here,
  does it exist elsewhere?
```

**Phase 5: Verify**
```
Confirm the fix is complete:

□ ORIGINAL PROBLEM: Is the original issue resolved?
□ REGRESSION: Did the fix break anything else?
  Run the full test suite.
□ EDGE CASES: Does the fix handle edge cases?
  What about null, empty, large, concurrent?
□ REPRODUCTION: Run the original reproduction steps.
  Does the problem still occur? (It should not.)
```

**Self-check for debugging methodology**
```
After giving debugging advice, verify:

□ Did I help REPRODUCE before suggesting fixes?
□ Did I help ISOLATE before guessing the cause?
□ Did I guide toward the ROOT CAUSE?
□ Did I suggest VERIFICATION after the fix?
□ Did I recommend writing a REGRESSION TEST?

If I skipped steps, I gave ad-hoc advice, not systematic guidance.
```

**The meta-principle:** Debugging is a skill, not intuition. Following a systematic process — reproduce, isolate, identify, fix, verify — produces reliable results even for unfamiliar problems. Ad-hoc debugging works when you're lucky. Systematic debugging works every time.'''
    ),
    (
        "thinking/auto-autonomous-debug-error-messages",
        r'''How can I improve my ability to help users interpret error messages? What framework helps me extract maximum diagnostic information from error output?''',
        r'''<think>
Error messages are the most information-dense artifact in debugging, yet most developers (and AI assistants) don't extract their full value. A good error message tells you:
1. What failed
2. Where it failed
3. Why it failed (often)
4. What the system expected vs. what it got

The skill is teaching users to read error messages systematically rather than panicking at the first line.
</think>

**Error Message Interpretation Framework**

**Anatomy of an error message**
```
Most error messages contain these components:

ERROR TYPE: What category of error
  TypeError, ConnectionRefused, 404 Not Found, OOM Killed
  → Immediately narrows the problem category

ERROR MESSAGE: Human-readable description
  "Cannot read property 'name' of undefined"
  → Tells you WHAT happened (accessing .name on undefined)

LOCATION: Where in the code it happened
  at UserService.getUser (user-service.js:42:15)
  → Tells you the exact file, line, and column

STACK TRACE: How execution reached this point
  at Router.handle → at UserController.show → at UserService.getUser
  → Shows the call chain (read bottom-to-top for causation)

CONTEXT: Additional details
  "Expected string, got number"
  "Connection to localhost:5432 refused"
  → Tells you WHY it happened
```

**Reading strategy: Parse, don't panic**
```
Step 1: Read the ERROR TYPE
  This tells you the category:
  - TypeError/ValueError → wrong data type or value
  - ConnectionError → network or service issue
  - PermissionError → access rights
  - TimeoutError → something took too long
  - OutOfMemory → resource exhaustion

Step 2: Read the ERROR MESSAGE carefully
  Word by word. Every word matters.
  "Cannot read property 'name' of undefined"
  - 'name' → the property being accessed
  - 'undefined' → the object was undefined
  - Question: What was supposed to have 'name'?

Step 3: Find the RELEVANT stack frame
  Not always the top of the stack.
  Look for YOUR code, not library code.
  Skip frames in node_modules, site-packages, stdlib.
  The first frame in YOUR code is usually the culprit.

Step 4: Check the CONTEXT
  Error messages often include the actual vs. expected value:
  "Expected 2 arguments, got 3" → count your arguments
  "Column 'user_id' cannot be null" → your data is missing user_id
  "Invalid JSON at position 42" → character 42 has a syntax error
```

**Common error message patterns**
```
PATTERN: "X is not defined" / "X is undefined"
  Cause: Variable or import is missing
  Check: Is it imported? Is it spelled correctly? Is it in scope?

PATTERN: "Cannot connect to X" / "Connection refused"
  Cause: The service isn't running or isn't accessible
  Check: Is the service running? Is the host/port correct?
  Is a firewall blocking the connection?

PATTERN: "Permission denied"
  Cause: The process lacks rights to access a resource
  Check: File permissions, database user privileges,
  API key scopes, IAM roles

PATTERN: "Timeout" / "deadline exceeded"
  Cause: An operation took longer than allowed
  Check: Is the timeout too short? Is the operation slow?
  Is there a network issue?

PATTERN: "Out of memory" / "OOM Killed"
  Cause: Process exceeded available memory
  Check: Memory leak? Processing too much data at once?
  Need to process in chunks/streams?
```

**Teaching users to read errors**
```
Instead of interpreting the error FOR the user,
teach them the interpretation process:

GOOD:
  "Let's read this error together:
   1. The type is 'KeyError' — that means you're accessing
      a dictionary key that doesn't exist.
   2. The key is 'user_id' — that's what's missing.
   3. Line 42 of app.py — that's where it happens.
   4. Check: What does the dictionary actually contain
      at that point? Add print(data.keys()) on line 41."

BAD:
  "Change line 42 to data.get('user_id', None)"
  (Fixes the symptom without teaching the skill)
```

**The meta-principle:** Error messages are not obstacles — they are the debugging answer key. An error message that says "ConnectionRefusedError: [Errno 111] Connection refused" has already told you the problem (connection was refused), the mechanism (the target isn't accepting connections), and the next step (check if the service is running on the expected host and port). Teaching users to read error messages systematically is more valuable than diagnosing each error for them.'''
    ),
    (
        "thinking/auto-autonomous-debug-context-gathering",
        r'''How can I improve the way I gather context before giving debugging advice? What questions should I always ask, and what context is essential versus nice-to-have?''',
        r'''<think>
Context gathering is the step most often skipped in debugging assistance, and it's the step that most determines the quality of the advice. Without context, debugging advice is just guessing. The challenge is gathering enough context without overwhelming the user with 20 questions.

The strategy is:
1. Ask the essential questions first (3-4 questions)
2. Use the answers to determine what additional context is needed
3. Avoid asking questions whose answers won't change your advice
</think>

**Debugging Context Gathering Framework**

**Essential questions (always ask)**
```
QUESTION 1: What is the exact error or unexpected behavior?
  Not: "It doesn't work"
  Need: The exact error message, screenshot, or precise description
  Why: This determines the entire debugging direction

QUESTION 2: What did you expect to happen?
  This reveals the gap between expectation and reality.
  Sometimes the behavior is correct but unexpected.
  Sometimes the expectation reveals a misunderstanding.

QUESTION 3: What changed recently?
  Most bugs are regressions introduced by a specific change:
  - Code change (git diff)
  - Dependency update
  - Configuration change
  - Data change
  - Environment change
  If nothing changed, the problem might be load-dependent
  or data-dependent.

QUESTION 4: Can you reproduce it consistently?
  Consistent → easier to debug (reproduce and fix)
  Intermittent → likely timing, concurrency, or data-dependent
  One-time → might be resolved, or might need more monitoring
```

**Conditional questions (ask based on the problem type)**
```
IF error involves database:
  - What database and version?
  - What does the query look like?
  - How much data is in the table?
  - Are there recent schema changes?

IF error involves API/network:
  - What does the request look like? (curl or equivalent)
  - What does the response look like? (status code, body)
  - Does it work from a different client?
  - Are there proxy/firewall/VPN involved?

IF error involves deployment:
  - What environment? (local, staging, production)
  - Does it work locally but not in production?
  - What's the deployment method?
  - Are there environment-specific configurations?

IF error involves performance:
  - When did it start being slow?
  - How slow? (specific numbers: 200ms vs 20s)
  - Is it consistently slow or intermittently?
  - Does it get worse over time?
```

**Context that changes your advice**
```
CONTEXT THAT MATTERS:
  □ Technology stack (determines available tools and approaches)
  □ Scale (10 users vs 10,000 — different debugging tools)
  □ Environment (local vs production — different access and risk)
  □ Urgency (learning exercise vs production outage — different advice)

CONTEXT THAT USUALLY DOESN'T MATTER:
  □ Why they chose this technology (irrelevant to the bug)
  □ Complete project history (too much noise)
  □ Team structure (unless it's a process issue)
  □ Business requirements (unless the bug is in requirements)

Don't ask about things that won't change your debugging approach.
```

**Efficient context gathering**
```
STRATEGY 1: Ask for the error first, then ask follow-ups
  "Please share the exact error message and stack trace."
  [Read the error, then ask targeted follow-ups]

STRATEGY 2: Ask for reproduction steps
  "What are the exact steps to reproduce this?"
  [Steps often reveal the context naturally]

STRATEGY 3: Ask what they've already tried
  "What have you already tried to fix it?"
  [This prevents suggesting things they've already ruled out
   and reveals their debugging approach]

STRATEGY 4: Ask for the minimal example
  "Can you share the smallest piece of code that shows the problem?"
  [This forces the user to isolate the issue and often helps
   them find the bug themselves]
```

**Self-check for context gathering**
```
Before giving debugging advice, verify:

□ Do I know the EXACT error or behavior? (not a summary)
□ Do I know the TECHNOLOGY STACK? (language, framework, versions)
□ Do I know what CHANGED recently? (or if anything changed)
□ Do I know the ENVIRONMENT? (local, staging, production)
□ Do I have enough context to give SPECIFIC advice?

If any of these are missing and would change my advice,
ask before advising. It's better to ask one question
than to give five possible solutions.
```

**The meta-principle:** The quality of debugging advice is directly proportional to the quality of context gathered. Five minutes of questions saves thirty minutes of wrong guesses. Always ask for the error message first — it contains more information than most people realize. And always ask what changed — most bugs are caused by a specific recent change.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
