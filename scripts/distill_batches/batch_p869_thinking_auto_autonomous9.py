"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 9)

Autonomously improving error message quality — detecting when error
messages are confusing and reformulating them for clarity and actionability.
"""

PAIRS = [
    (
        "thinking/auto-autonomous-error-message-diagnosis",
        r'''When I encounter a confusing error message while helping a user, how do I autonomously translate it into something helpful? What framework can I use to decode any error message?''',
        r'''<think>
Error message quality is one of the biggest barriers for developers. A confusing error message wastes hours. A clear error message saves hours. When I encounter a confusing error message, I should:

1. Parse the error into components (what happened, where, why)
2. Translate jargon into plain language
3. Suggest likely causes based on context
4. Provide actionable next steps

**The common failure modes of error messages:**
- Too terse: "Error: EINVAL" (what does that mean?)
- Too verbose: 500-line stack trace (where's the important part?)
- Wrong abstraction level: "Segmentation fault" (the user doesn't care about memory segments)
- Missing context: "Permission denied" (which permission? which resource?)
- Misleading: Error points to line X but the real problem is on line Y
</think>

**Framework for Decoding and Improving Error Messages**

**The 4-part error message translation:**

```
For any error message, extract:

1. WHAT happened (the symptom)
2. WHERE it happened (file, line, function)
3. WHY it likely happened (root cause)
4. WHAT TO DO about it (actionable fix)

Example — raw error:
  "psycopg2.OperationalError: could not connect to server:
   Connection refused. Is the server running on host
   'localhost' and accepting TCP/IP connections on port 5432?"

Translation:
  WHAT: Can't connect to PostgreSQL database
  WHERE: Your database connection code
  WHY: PostgreSQL server isn't running, or it's on a different port
  DO: Run 'pg_isready' to check if PostgreSQL is running.
      If not, start it with 'sudo systemctl start postgresql'.
      If using Docker: 'docker ps' to check if the container is running.
```

**Error message quality tiers:**

```
TIER 1 (Terrible) — Just a code:
  "Error: ECONNREFUSED"
  → User must Google the error code
  → No context, no action

TIER 2 (Poor) — Technical description:
  "TCP connection to 127.0.0.1:5432 refused by remote host"
  → Technically accurate but not actionable
  → Assumes networking knowledge

TIER 3 (Adequate) — Plain language:
  "Cannot connect to database at localhost:5432"
  → Clear what failed
  → Still no guidance on fixing it

TIER 4 (Good) — Includes likely cause:
  "Cannot connect to database at localhost:5432.
   Is PostgreSQL running?"
  → Clear what failed + a hypothesis

TIER 5 (Excellent) — Includes fix:
  "Cannot connect to database at localhost:5432.
   PostgreSQL doesn't appear to be running.
   Try: sudo systemctl start postgresql
   Or check: pg_isready -h localhost -p 5432"
  → What failed + why + how to fix it
```

**Common error families and their translations:**

| Error pattern | Usually means | Suggest |
|--------------|---------------|---------|
| `ECONNREFUSED` / `Connection refused` | Server not running or wrong port | Check if the service is running |
| `ENOTFOUND` / `DNS resolution failed` | Hostname doesn't exist or DNS is down | Check spelling, try the IP directly |
| `ETIMEDOUT` / `Connection timed out` | Firewall blocking or server unreachable | Check firewall rules, try ping |
| `Permission denied` | Wrong user, wrong file permissions | Check `ls -la`, check running user |
| `Module not found` / `ImportError` | Package not installed or wrong env | Check `pip list`, check virtualenv |
| `SyntaxError` near end of file | Missing closing bracket/quote earlier | Look for unmatched brackets above |
| `NullPointerException` | Used a variable that wasn't initialized | Check what's null, trace it back |
| `OOMKilled` | Process used too much memory | Check for memory leaks, increase limits |

**The self-improvement loop:**
```
When I help a user with an error:

1. Did I translate it clearly on the first try?
   → No? Note what I missed for next time.

2. Did the user need follow-up questions?
   → Yes? My initial translation was incomplete.
        Next time, include more context.

3. Was the actual cause what I suggested?
   → No? My mental model of that error was wrong.
        Update my error-to-cause mapping.

4. Could I have provided a more specific fix?
   → Yes? Add that fix to my repertoire for this error.
```

**The meta-principle:** A good error message is a mini debugging guide. It tells you what happened, why it likely happened, and what to do about it. When translating error messages for users, always aim for Tier 5: symptom + likely cause + specific fix. The few extra seconds of explanation save the user hours of Googling.'''
    ),
    (
        "thinking/auto-autonomous-error-message-patterns",
        r'''I want to improve how I help users write better error messages in their own code. What patterns make error messages actually useful versus the typical lazy ones developers write?''',
        r'''<think>
Most developers write error messages as an afterthought. The typical pattern is `throw new Error("something went wrong")` — which is useless for debugging. Teaching developers to write good error messages requires showing them a pattern that's easy to follow and demonstrating the difference in debugging experience.

**Principles of good error messages:**
1. State what was expected vs. what was received
2. Include the specific values that caused the failure
3. Suggest the most likely fix
4. Include context (which operation, which resource)
5. Be specific enough that you can diagnose without a debugger
</think>

**Writing Useful Error Messages: Patterns and Anti-Patterns**

**The error message formula:**
```
[WHAT failed] + [WHY it failed] + [HOW to fix it]
+ [CONTEXT: relevant values]

BAD:  "Invalid input"
GOOD: "Email validation failed: 'not-an-email' is not a valid
       email address. Expected format: user@domain.com"

BAD:  "File not found"
GOOD: "Config file not found at '/etc/myapp/config.yaml'.
       Create it with: cp /etc/myapp/config.example.yaml
       /etc/myapp/config.yaml"

BAD:  "Permission denied"
GOOD: "Cannot write to '/var/log/myapp.log': permission denied.
       Current user: 'www-data'. Required: write permission on
       '/var/log/'. Fix: sudo chown www-data /var/log/myapp.log"
```

**The patterns:**

**Pattern 1: Expected vs. Actual**
```python
# BAD
if not isinstance(value, int):
    raise TypeError("Wrong type")

# GOOD
if not isinstance(value, int):
    raise TypeError(
        f"Expected 'count' to be int, got {type(value).__name__}: {value!r}"
    )
# Output: "Expected 'count' to be int, got str: 'abc'"
```

**Pattern 2: Include the failing value**
```python
# BAD
if user is None:
    raise ValueError("User not found")

# GOOD
if user is None:
    raise ValueError(
        f"User not found with id={user_id}. "
        f"Verify the ID exists in the database."
    )
```

**Pattern 3: Range violations with boundaries**
```python
# BAD
if not (0 <= port <= 65535):
    raise ValueError("Invalid port")

# GOOD
if not (0 <= port <= 65535):
    raise ValueError(
        f"Port must be between 0 and 65535, got {port}. "
        f"Common ports: HTTP=80, HTTPS=443, PostgreSQL=5432"
    )
```

**Pattern 4: Suggest the fix**
```python
# BAD
if "DATABASE_URL" not in os.environ:
    raise EnvironmentError("Missing env var")

# GOOD
if "DATABASE_URL" not in os.environ:
    raise EnvironmentError(
        "Required environment variable 'DATABASE_URL' is not set. "
        "Set it with: export DATABASE_URL='postgresql://user:pass@localhost/dbname' "
        "or add it to your .env file."
    )
```

**Pattern 5: Chain context through layers**
```python
# BAD
try:
    data = json.loads(response.text)
except json.JSONDecodeError:
    raise  # Raw error, no context

# GOOD
try:
    data = json.loads(response.text)
except json.JSONDecodeError as e:
    raise ValueError(
        f"Failed to parse JSON response from {url} "
        f"(status={response.status_code}). "
        f"Response body: {response.text[:200]!r}. "
        f"Parse error: {e}"
    ) from e
```

**The checklist for every error message:**
```
□ Does it name the operation that failed?
  Not "Error" but "Failed to send email"

□ Does it include the specific values?
  Not "invalid input" but "email 'abc' is invalid"

□ Does it explain why it failed?
  Not just what, but "because the format must be user@domain"

□ Does it suggest a fix?
  "Try: ensure the email contains '@' and a domain"

□ Would a developer at 3 AM understand it without context?
  If yes → good error message
  If no → add more context
```

**The meta-principle:** Error messages are read far more often than they're written. A developer writes an error message once but it might be read hundreds of times by dozens of people over years. Spending 30 extra seconds writing a helpful error message saves hundreds of hours of collective debugging time. Treat error messages as documentation for failure states.'''
    ),
    (
        "thinking/auto-autonomous-error-message-stack-traces",
        r'''Users often send me huge stack traces and ask "what does this mean?" How do I systematically extract the useful information from a stack trace and present it clearly?''',
        r'''<think>
Stack traces contain enormous amounts of information, but most of it is noise (framework internals, library code). The challenge is quickly identifying the relevant frames — the user's code where the actual problem is.

**The stack trace reading strategy:**
1. Find the actual error (usually at the bottom in Python, top in Java/JS)
2. Scan for YOUR code (ignore framework/library frames)
3. Identify the frame closest to the error in your code
4. Read the error message in context of that frame
5. Look at 1-2 frames above for additional context
</think>

**Systematic Stack Trace Analysis**

**The anatomy of a stack trace:**
```python
# Python stack trace (most recent call LAST):
Traceback (most recent call last):
  File "app.py", line 45, in main          ← YOUR CODE (entry point)
    result = process_orders(orders)
  File "app.py", line 23, in process_orders ← YOUR CODE (the path)
    total = calculate_total(order)
  File "app.py", line 12, in calculate_total ← YOUR CODE (closest to error)
    price = item.price * item.quantity
AttributeError: 'NoneType' object has no attribute 'price'
                                            ← THE ERROR (read this first)
```

**The 3-step extraction method:**

```
Step 1: READ THE ERROR (bottom of trace in Python, top in Java)
  "AttributeError: 'NoneType' object has no attribute 'price'"
  Translation: "Something is None that shouldn't be.
                You're calling .price on a None value."

Step 2: FIND YOUR CODE (ignore framework frames)
  In a Django stack trace, you might see 20 frames of Django
  internals. Skip them. Find the frames in YOUR files:
    File "app.py", line 12, in calculate_total
      price = item.price * item.quantity
  → This is the line where item is None.

Step 3: TRACE BACKWARDS (where did None come from?)
  File "app.py", line 23, in process_orders
    total = calculate_total(order)
  → Where did 'order' come from? Is one of its items None?
  → Check the data source: database query? API response?
```

**Filtering noise from signal:**

```
IGNORE these frames (framework/library internals):
  File "/usr/lib/python3.11/..." ← standard library
  File "/venv/lib/python3.11/site-packages/django/..." ← framework
  File "/venv/lib/python3.11/site-packages/sqlalchemy/..." ← ORM

FOCUS on these frames (your code):
  File "app/views.py", line 45, in order_view ← YOUR view
  File "app/services.py", line 23, in process_order ← YOUR service
  File "app/models.py", line 12, in calculate_total ← YOUR model

The relevant frame is usually the LAST (most recent) frame
in YOUR code before it enters library code or raises.
```

**Common stack trace patterns and what they mean:**

```
Pattern: Error at the BOTTOM of your code
  Your code → library code → ERROR
  Meaning: You called a library function with wrong arguments
  Fix: Check your function call, not the library code

Pattern: Error in MIDDLE of your code
  Your code → your code → ERROR
  Meaning: Bug in your logic
  Fix: Read the error line and the data flowing into it

Pattern: Error in FRAMEWORK code
  Framework → framework → ERROR
  Meaning: Usually your configuration is wrong, not the framework
  Fix: Check your config files, URL routes, model definitions

Pattern: RecursionError / StackOverflow
  Same function repeated 100+ times
  Meaning: Infinite recursion — function calls itself forever
  Fix: Check base case of recursive function
```

**How to present a stack trace to a user:**
```
WRONG (dump the whole trace):
  "Here's what's happening: [100-line stack trace]"

RIGHT (extract and explain):
  "The error is on line 12 of app.py in calculate_total():
   'item.price' failed because 'item' is None.

   This means one of the items in your order list is None.
   Check where you build the order list — likely a database
   query is returning None for a missing product.

   Quick fix: Add a None check:
     if item is not None:
         price = item.price * item.quantity

   Better fix: Find out WHY item is None (missing product in DB?)."
```

**The meta-principle:** A stack trace is a breadcrumb trail from the symptom to the cause. Most of the trail goes through framework code you don't care about. Your job is to follow the breadcrumbs through YOUR code, identify where things went wrong, and explain it in plain language. The error message tells you WHAT went wrong; your code frames tell you WHERE; tracing the data backwards tells you WHY.'''
    ),
    (
        "thinking/auto-autonomous-error-message-improvement-loop",
        r'''How do I build a systematic process for continuously improving the quality of error messages I help users with? I want each error I decode to make me better at decoding the next one.''',
        r'''<think>
This is about building an error-message-specific learning loop. Each error I encounter is a learning opportunity. I should track:
1. What the error was
2. What the user actually needed to know
3. Whether my initial explanation was helpful
4. What I would do differently next time

The goal is to build an internal "error dictionary" that gets richer over time, so I can instantly provide high-quality translations for common errors.
</think>

**Building a Continuous Error Message Improvement Loop**

**The improvement cycle:**

```
       ┌─── 1. ENCOUNTER error ←──────────────────────┐
       │                                                │
       ↓                                                │
  2. DECODE (translate to plain language)                │
       │                                                │
       ↓                                                │
  3. EVALUATE (was my translation helpful?)             │
       │                                                │
       ↓                                                │
  4. CATALOG (add to error knowledge base)              │
       │                                                │
       ↓                                                │
  5. PATTERN-MATCH (connect to similar errors) ────────┘
```

**Step 1: The error encounter log**
```
For each error I help decode, mentally track:

  ERROR: The raw error message/stack trace
  CONTEXT: What the user was doing when it occurred
  MY TRANSLATION: How I explained it
  ACTUAL CAUSE: What the root cause turned out to be
  ACCURACY: Did my first explanation match the actual cause?
  IMPROVEMENT: What would I say differently next time?
```

**Step 2: Building error families**
```
Group errors by root cause, not by error message.
Different messages can have the same root cause:

  Root cause: "Service not running"
  Error messages:
    - "ECONNREFUSED" (Node.js)
    - "ConnectionRefusedError" (Python)
    - "java.net.ConnectException: Connection refused"
    - "dial tcp 127.0.0.1:5432: connect: connection refused" (Go)
    - "could not connect to server" (psycopg2)

  When I see ANY of these → immediately suggest checking
  if the service is running, without needing to research.

  Root cause: "Trying to use a null/None value"
  Error messages:
    - "AttributeError: 'NoneType' has no attribute..." (Python)
    - "NullPointerException" (Java)
    - "TypeError: Cannot read properties of null" (JavaScript)
    - "attempt to index a nil value" (Lua)

  Same fix pattern: trace back to find where None came from.
```

**Step 3: Quality self-assessment after each error**
```
Rate my translation on these dimensions:

□ SPEED: Did I identify the root cause quickly?
  Fast (< 30 sec) | Medium (1-3 min) | Slow (5+ min)

□ ACCURACY: Was my first suggestion correct?
  Correct | Partially correct | Wrong

□ COMPLETENESS: Did I provide enough to fix it?
  User fixed it immediately | Needed follow-up | Multiple rounds

□ ACTIONABILITY: Did I give specific steps?
  Specific command to run | General direction | Vague suggestion

Score < 3 out of 4 → analyze what I missed and improve.
```

**Step 4: Common improvement areas**

```
PATTERN: I keep missing the same type of error
  → Build a checklist for that error family

PATTERN: My first suggestion is often wrong
  → I'm jumping to conclusions. Slow down, gather more context.
  → Ask "what were you doing when this happened?" before diagnosing.

PATTERN: Users need multiple follow-ups
  → My initial translation is incomplete.
  → Include the fix, not just the diagnosis.

PATTERN: I explain the error but not the fix
  → Force myself to end every error translation with
    "To fix this: [specific action]"
```

**Step 5: Proactive improvement**
```
Don't just wait for errors — anticipate them:

When explaining a setup process:
  "Run this command. If you see 'permission denied',
   prefix with 'sudo'. If you see 'command not found',
   install it with 'brew install X'."

Pre-answering common errors is better than
waiting for the user to hit them.
```

**The meta-principle:** Every error message I decode is training data for my own improvement. By systematically tracking what I got right and wrong, building error families, and pre-loading common translations, I become faster and more accurate over time. The goal is to reach the point where most errors trigger an instant, accurate, actionable response — because I've seen that error family before and cataloged the right translation.'''
    ),
    (
        "thinking/auto-autonomous-error-message-context-sensitivity",
        r'''The same error message can mean completely different things depending on context. How do I get better at using context clues to give the right diagnosis instead of a generic one?''',
        r'''<think>
Context-sensitive error diagnosis is critical because the same error message can have different root causes depending on:
- What the user was doing (deploying vs. developing vs. testing)
- Their tech stack (Python vs. Node vs. Java)
- Their environment (local vs. Docker vs. cloud)
- What changed recently (new dependency, new code, new config)

The key is asking the right clarifying questions and using contextual signals to narrow down the cause.
</think>

**Context-Sensitive Error Diagnosis**

**The same error, different contexts:**

```
Error: "Connection timed out"

Context: Local development
  → Database isn't running
  → Fix: Start PostgreSQL/MySQL

Context: Docker Compose
  → Service name is wrong, or service hasn't started yet
  → Fix: Check docker-compose.yml service names, add depends_on

Context: Production deployment
  → Security group/firewall blocking the port
  → Fix: Check cloud firewall rules, VPC configuration

Context: After a deploy
  → New code has wrong database URL
  → Fix: Check environment variables in the new deployment

Same error, four completely different fixes.
```

**Context signals to look for:**

```
Signal 1: TIMING — When did it start?
  "It was working until 5 minutes ago"
  → Something changed. What was deployed/modified in the last 5 min?

  "It's never worked"
  → Setup/configuration issue, not a regression.

  "It works sometimes"
  → Race condition, intermittent network issue, or load-related.

Signal 2: SCOPE — How widespread is it?
  "Only I have this problem"
  → Local environment issue (missing env var, wrong version)

  "Everyone has this problem"
  → Server-side issue (deployment, infrastructure)

  "Only in production, not locally"
  → Environment difference (env vars, network config, data volume)

Signal 3: STACK — What technology is in use?
  "ModuleNotFoundError" in Python
    + using virtualenv → wrong virtualenv activated
    + using Docker → package not in requirements.txt
    + using Lambda → missing layer or deployment package issue

Signal 4: RECENCY — What changed?
  "Updated dependencies" → version incompatibility
  "Changed nothing" → external factor (expired cert, full disk, DNS)
  "Added a new feature" → new code introduced the bug
```

**The context-gathering protocol:**
```
Before diagnosing, gather:

1. What were you trying to do? (operation context)
2. What exact error do you see? (full error message)
3. When did it start? (timing context)
4. What changed recently? (change context)
5. Does it happen consistently? (reliability context)
6. What environment? (infrastructure context)

With these 6 answers, most errors can be diagnosed
without even seeing the code.
```

**Context-sensitive diagnosis examples:**

```
ERROR: "ENOMEM" / "Out of memory"

  Context: Running a data processing script
    → Script is loading too much data into memory
    → Fix: Process data in chunks/streams

  Context: Docker container
    → Container memory limit is too low
    → Fix: Increase memory limit in docker-compose.yml

  Context: Kubernetes pod
    → Pod resource limits too restrictive, or memory leak
    → Fix: Check resource limits, profile memory usage

  Context: Lambda/serverless function
    → Function memory allocation too small
    → Fix: Increase memory setting in function configuration
```

**Building context-aware diagnosis habits:**
```
WRONG approach (context-free):
  User: "I'm getting a 500 error"
  Me: "500 means internal server error. Check your server logs."
  (Too generic. Not helpful.)

RIGHT approach (context-aware):
  User: "I'm getting a 500 error"
  Me: "When does it happen? On all requests or specific ones?
       Did it start after a recent deploy?"
  User: "Only on the /upload endpoint, started after deploy"
  Me: "Check the upload handler in your latest commit.
       Common causes: file size limit changed, storage
       credentials expired, or new validation rejecting
       previously valid input."
  (Specific. Actionable. Context-driven.)
```

**The meta-principle:** Generic error diagnosis is almost always wrong because it ignores context. The same error can have dozens of causes, but context (timing, scope, environment, recent changes) narrows it to one or two likely causes. Always gather context before diagnosing. Five seconds of questions save five minutes of wrong suggestions.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
