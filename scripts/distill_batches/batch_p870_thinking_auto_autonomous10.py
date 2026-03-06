"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 10)

Autonomously detecting and fixing explanation gaps — identifying when
an explanation is incomplete, assumes too much, or skips critical steps.
"""

PAIRS = [
    (
        "thinking/auto-autonomous-detecting-explanation-gaps",
        r'''How do I detect when my explanation of a technical concept has gaps that will leave the user confused or unable to implement what I described?''',
        r'''<think>
Explanation gaps are invisible to the explainer because we have the full mental model in our head — we unconsciously fill in the gaps ourselves. To the learner, gaps create confusion that they often can't articulate ("I followed every step but it doesn't work").

**Common types of explanation gaps:**
1. Missing prerequisites ("Install X" — but what version? From where?)
2. Implicit assumptions ("Open your terminal" — which terminal? Where?)
3. Skipped intermediate steps ("Configure the database" — how exactly?)
4. Missing error handling ("Run this command" — what if it fails?)
5. Environment assumptions ("This works on..." — but which OS/version?)

**Detection strategy:**
- Read the explanation as if you know NOTHING beyond what's explicitly stated
- Check: can each step be completed without additional knowledge?
- Look for verbs without specifics ("configure," "set up," "install")
</think>

**Detecting Explanation Gaps: A Self-Review Framework**

**The "alien test" — read your explanation as a competent but uninformed person:**

```
For each step in your explanation, ask:

1. "Could someone follow this step with ONLY the information
    I've provided so far?"
   → No? You have a gap.

2. "What would someone need to ALREADY KNOW to follow this step?"
   → If that knowledge isn't common, you need to explain it or link to it.

3. "What could go WRONG at this step?"
   → If you don't mention it, the user will hit it and get stuck.

4. "What does 'success' look like at this step?"
   → If the user can't verify they did it right, they'll doubt themselves.
```

**Gap detection checklist:**

```
□ PREREQUISITES: Did I state what needs to be installed/configured first?
  GAP: "Run 'docker compose up'"
  FIX: "First, install Docker Desktop (https://...).
        Then, in the project directory, run 'docker compose up'"

□ VERSIONS: Did I specify which versions this applies to?
  GAP: "Install Python and run the script"
  FIX: "Install Python 3.10 or later. Check with: python --version"

□ EXACT COMMANDS: Did I give copy-pasteable commands, not descriptions?
  GAP: "Add the dependency to your project"
  FIX: "Run: pip install requests==2.31.0"

□ EXPECTED OUTPUT: Did I show what the user should see?
  GAP: "Run the migration"
  FIX: "Run: python manage.py migrate
        You should see: 'Applying myapp.0001_initial... OK'"

□ ERROR CASES: Did I cover what happens if a step fails?
  GAP: "Start the server"
  FIX: "Start the server: python manage.py runserver
        If you see 'Port already in use', run: kill -9 $(lsof -ti:8000)"

□ NAVIGATION: Did I say WHERE to run commands or edit files?
  GAP: "Edit the config file"
  FIX: "Edit config/settings.py (in the project root directory)"

□ TRANSITIONS: Did I connect each step to the next?
  GAP: Step 3 is about database setup. Step 4 is about API routes.
  FIX: "Now that the database is configured, let's create the
        API routes that will read from it."
```

**The most common gap patterns:**

| Pattern | Example of gap | How to fix |
|---------|---------------|------------|
| "Install X" | Which version? From where? With which package manager? | "Install X v2.3: `pip install x==2.3`" |
| "Configure Y" | What settings? In which file? What values? | "In `config.yaml`, set `database.host: localhost`" |
| "Run the tests" | Which test command? From which directory? | "From the project root: `pytest tests/ -v`" |
| "Deploy to production" | Which platform? Which commands? Which credentials? | Step-by-step deployment commands |
| "Set up the database" | Which database? How to install? How to create the DB? | Full setup sequence with commands |

**Self-review process:**
```
After writing any explanation:

1. Read each step and ask: "What would happen if I
   literally typed only what's written here?"

2. Check for "magic words" that hide complexity:
   - "simply" (probably not simple)
   - "just" (might require steps you're not mentioning)
   - "configure" (configure WHAT, HOW?)
   - "set up" (extremely vague)
   - "properly" (what does "properly" mean specifically?)

3. Check for assumed knowledge:
   - Did I assume they know what a terminal is?
   - Did I assume they know which directory to be in?
   - Did I assume they know how environment variables work?
```

**The meta-principle:** The curse of knowledge is that you can't unsee what you know. After you understand something, it becomes invisible how many things you're assuming. The antidote is to mechanically check each step for implicit prerequisites, missing commands, assumed knowledge, and unmentioned failure cases. Treat every explanation as if the reader is competent but has never seen your specific technology stack before.'''
    ),
    (
        "thinking/auto-autonomous-fixing-explanation-gaps-code",
        r'''When I explain a code concept and provide an example, I sometimes realize later that the example doesn't actually demonstrate what I was explaining. How do I ensure my code examples accurately illustrate the concept?''',
        r'''<think>
Code examples fail when they:
1. Are too complex (the concept is buried in boilerplate)
2. Are too simple (don't show the actual challenge)
3. Don't compile/run (syntax errors, missing imports)
4. Show the pattern but not the value (why is this better?)
5. Miss the edge case that makes the concept important
6. Use domain-specific context the user doesn't have

The goal of a code example is to be the MINIMAL code that demonstrates the concept and nothing else. Every line should serve the explanation.
</think>

**Ensuring Code Examples Match the Concept**

**The code example quality checklist:**

```
□ DOES IT RUN? (The #1 failure)
  Test your code example mentally or actually.
  Missing imports, typos, and syntax errors destroy credibility.

  BAD:
    result = map(items, lambda x: x.name)  # map args are reversed
  GOOD:
    result = list(map(lambda x: x.name, items))  # correct arg order

□ DOES IT DEMONSTRATE THE CONCEPT? (Not just related code)
  If explaining "dependency injection":
  BAD: A complete Flask app that happens to use DI somewhere
  GOOD: A minimal before/after showing DI vs. hard-coded dependency

□ IS IT MINIMAL? (No unnecessary complexity)
  Remove everything that doesn't serve the explanation:
  - No complex business logic
  - No real-world variable names that add confusion
  - No error handling (unless that's the topic)
  - No imports (unless they're the point)

□ DOES IT SHOW BEFORE AND AFTER? (Most effective pattern)
  Show the BAD way first, then the GOOD way:
    # Without the concept (problematic):
    [bad code that shows the problem]

    # With the concept (improved):
    [good code that shows the solution]

  This makes the VALUE of the concept visible.
```

**Example: Teaching closures**

```python
# BAD example (too complex, concept buried):
def create_tax_calculator(country):
    tax_rates = {"US": 0.08, "UK": 0.20, "DE": 0.19}
    rate = tax_rates.get(country, 0)
    def calculate(amount):
        return amount * (1 + rate)
    return calculate

us_calc = create_tax_calculator("US")
print(us_calc(100))  # What's a closure here? Hard to see.

# GOOD example (minimal, concept clear):
def make_multiplier(factor):
    def multiply(x):
        return x * factor  # 'factor' is captured from outer scope
    return multiply

double = make_multiplier(2)
triple = make_multiplier(3)

print(double(5))   # 10 — 'factor' is 2, remembered from creation
print(triple(5))   # 15 — 'factor' is 3, remembered from creation

# The closure is 'multiply' capturing 'factor' from its
# enclosing scope. Even after make_multiplier returns,
# 'factor' is still available inside 'multiply'.
```

**The "highlight the concept" technique:**
```
Add comments that point directly to the concept:

def make_counter():
    count = 0                          # outer variable
    def increment():
        nonlocal count                 # ← closure captures 'count'
        count += 1                     # ← modifies the captured variable
        return count
    return increment

counter = increment()
counter()  # 1  ← 'count' persists between calls
counter()  # 2  ← same 'count', still alive in the closure

# Without comments pointing to the concept, the reader
# has to figure out WHICH part demonstrates a closure.
```

**Testing your example against the explanation:**
```
After writing the example, re-read your prose explanation.

For each claim in the prose, check:
  "Does my code example show this?"

Prose: "Closures capture variables from the enclosing scope."
Code: Does my example have an enclosing scope with a variable?
      Does the inner function use that variable? ✓
      Does it show the variable persisting after the outer function returns? ✓

If any claim in the prose isn't demonstrated in the code,
either add it to the code or remove the claim from the prose.
```

**The meta-principle:** A code example is not decoration — it's the primary teaching tool. The prose explains what the concept IS; the code shows what it DOES. If there's a mismatch between the two, the reader will trust the code and be confused by the prose. Write the code example first, verify it works, then write the prose to match what the code demonstrates.'''
    ),
    (
        "thinking/auto-autonomous-fixing-gaps-prerequisites",
        r'''I often get feedback that my explanations assume prerequisite knowledge the user doesn't have. How do I calibrate what prerequisites to include versus what's safe to assume?''',
        r'''<think>
The prerequisite calibration problem is fundamentally about audience modeling. Different users have different knowledge bases, and what's obvious to one person is completely unknown to another.

**The challenge:**
- Include too many prerequisites → explanation is padded with basics, experts feel patronized
- Include too few prerequisites → beginners get lost, can't follow the explanation
- You can't know exactly what each user knows

**Solution approaches:**
1. Explicitly state the assumed knowledge level at the start
2. Use "layered" explanations (main path for target audience, footnotes for others)
3. Link to prerequisite explanations rather than inlining them
4. When unsure, briefly define a concept the first time you use it
</think>

**Calibrating Prerequisites in Explanations**

**The prerequisite detection checklist:**

```
For every technical term or concept in your explanation, ask:

  "Would my TARGET audience know this term?"

  If yes → use it without explanation
  If no → either explain it briefly or link to a resource
  If unsure → add a one-sentence definition the first time

Example:
  Target: Junior developer learning REST APIs

  "Use a GET request" → they probably know what GET is ✓
  "Set the Content-Type header" → maybe? Brief explanation:
    "Set the Content-Type header (which tells the server
     what format your data is in) to application/json"
  "Serialize the response DTO" → they probably don't know DTO
    "Convert the response object to JSON"
```

**The audience level matrix:**

```
For the most common audiences:

BEGINNER (0-1 years):
  Safe to assume: Basic programming (variables, loops, functions)
  Must explain: HTTP, REST, databases, terminal, git, deployment
  Must define: API, endpoint, middleware, ORM, dependency injection

INTERMEDIATE (1-3 years):
  Safe to assume: HTTP basics, REST, one framework, git, SQL basics
  Must explain: Advanced patterns, system design, distributed systems
  Must define: Idempotency, eventual consistency, back-pressure

SENIOR (3+ years):
  Safe to assume: All of the above plus design patterns, testing
  Must explain: Niche topics, cutting-edge approaches
  Can use jargon freely: CQRS, saga pattern, CAP theorem
```

**Techniques for handling mixed audiences:**

**1. The "if you're unfamiliar" parenthetical:**
```
"Use a message broker (if you're unfamiliar: a message broker
 is software that sits between services and routes messages,
 like RabbitMQ or Kafka) to decouple the services."

This doesn't slow down experts (they skip the parenthetical)
but saves beginners from getting stuck.
```

**2. The "prerequisite check" at the start:**
```
"This guide assumes you:
  - Can write basic Python (functions, classes)
  - Have used pip to install packages
  - Have a running PostgreSQL database

  If you need to set up PostgreSQL first, see [link]."

This sets expectations and provides escape hatches.
```

**3. The "first-mention definition" technique:**
```
First time using a term, define it inline:
  "We'll use an ORM (Object-Relational Mapper — a library
   that lets you interact with databases using Python objects
   instead of writing raw SQL) called SQLAlchemy."

After the first mention, use the term freely:
  "The ORM will handle the SQL generation..."
```

**4. The "progressive disclosure" pattern:**
```
Start simple, add complexity in layers:

Layer 1 (everyone): "An API endpoint is a URL that accepts
  requests and returns data."

Layer 2 (intermediate): "Endpoints should be designed around
  resources (nouns, not verbs): /users, not /getUsers."

Layer 3 (advanced): "Consider HATEOAS — include links in
  responses so clients can discover available actions."

Each layer is optional. Stop at the appropriate depth.
```

**Common prerequisite blind spots:**

| I assume they know... | But beginners might not know... |
|----------------------|-------------------------------|
| How to open a terminal | What a terminal is or where to find it |
| What localhost:3000 means | What localhost is, what ports are |
| How to set environment variables | Where env vars go, how they persist |
| That they need to save the file | That some editors don't auto-save |
| How to read a stack trace | What a stack trace is or where to start reading |
| That npm/pip is a package manager | What a package manager is |

**Self-check protocol:**
```
After writing an explanation:

1. Identify every technical term used
2. For each, mark: [assumed] or [explained]
3. For each [assumed] term, verify it's appropriate
   for your target audience
4. Add brief definitions for any that are borderline

This takes 2 minutes and prevents 30 minutes of
confused follow-up questions.
```

**The meta-principle:** When in doubt, include the prerequisite with a brief definition. Nobody was ever confused by a clear one-sentence definition of something they already knew. But many people have been completely lost by unexplained jargon. The cost of over-explaining is a sentence; the cost of under-explaining is the user giving up entirely.'''
    ),
    (
        "thinking/auto-autonomous-fixing-gaps-step-ordering",
        r'''Sometimes my explanations are technically correct but the steps are in a confusing order. How do I detect and fix ordering problems in my explanations?''',
        r'''<think>
Step ordering problems happen when the explanation follows the author's thought process rather than the user's implementation process. The author might think "here's the architecture, then the database, then the API, then the frontend." But the user needs to implement in dependency order: database first (because the API depends on it), then API, then frontend.

**Common ordering problems:**
1. Conceptual order vs. implementation order (explaining WHY before explaining WHAT)
2. Forward references (mentioning something that hasn't been defined yet)
3. Optional steps mixed with required steps
4. Context introduced too late (explaining what you're building after showing the code)

**The fix:** Order by dependency — each step should only use things that have been defined in previous steps.
</think>

**Detecting and Fixing Step Ordering in Explanations**

**The dependency-order rule:**
```
Every step should only reference things that have been
introduced in PREVIOUS steps.

WRONG ORDER (forward reference):
  Step 1: "Call the validate() function"  ← What validate function?
  Step 2: "Define the validate() function"

RIGHT ORDER (dependency respected):
  Step 1: "Define the validate() function"
  Step 2: "Call the validate() function"
```

**Common ordering anti-patterns:**

**1. Architecture before implementation (too abstract too early):**
```
WRONG:
  "Our system uses event-driven architecture with a message
   broker for inter-service communication, implementing the
   saga pattern for distributed transactions."
  → (User has no idea what any of this means yet)
  → Then: "Let's start by creating a simple endpoint..."

RIGHT:
  "Let's build a simple order processing system. We'll start
   with a single API endpoint, then add a message broker to
   handle notifications separately."
  → Show the simple thing FIRST, add complexity LATER
```

**2. Configuration before context (what are we configuring?):**
```
WRONG:
  Step 1: "Add this to your docker-compose.yml:
           services:
             db:
               image: postgres:15..."
  Step 2: "We're building a web app that needs a database."

RIGHT:
  Step 1: "We need a PostgreSQL database for our app.
           We'll use Docker to run it locally."
  Step 2: "Create a docker-compose.yml with this content:..."
```

**3. Error handling before happy path:**
```
WRONG:
  "First, handle the case where the database is unavailable.
   Then, handle validation errors. Then, handle auth failures.
   Oh, and here's how to process a successful request."

RIGHT:
  "Here's how to process a successful request:
   [happy path code]
   Now let's add error handling:
   [validation errors]
   [database errors]
   [auth errors]"
```

**The step ordering verification protocol:**

```
After writing steps, verify:

1. DEPENDENCY CHECK: For each step, list what it depends on.
   Does every dependency appear in an earlier step?

   Step 1: Create the database     (depends on: nothing ✓)
   Step 2: Create the data model   (depends on: database ✓)
   Step 3: Create API endpoints    (depends on: data model ✓)
   Step 4: Add authentication      (depends on: endpoints ✓)

2. FORWARD REFERENCE CHECK: Read linearly. Is any term or
   concept used before it's introduced?

   "The middleware will check the JWT token..."
   ← Has "middleware" been explained? Has "JWT" been defined?
   If not → either reorder or add a brief definition.

3. MOTIVATION CHECK: Does the user know WHY before they do WHAT?

   WRONG: "Run: npm install express cors helmet"
   RIGHT: "We need three packages: express (web framework),
           cors (cross-origin requests), and helmet (security
           headers). Install them: npm install express cors helmet"
```

**The optimal explanation structure:**
```
1. CONTEXT: What are we building? Why?
2. PREREQUISITES: What do we need before starting?
3. STEPS (in dependency order):
   For each step:
     a. WHY: Brief motivation for this step
     b. WHAT: The specific action to take
     c. VERIFY: How to check it worked
4. RESULT: What the complete thing looks like
5. NEXT STEPS: Where to go from here
```

**The meta-principle:** Explanations should follow implementation order, not discovery order. You might have discovered the architecture pattern first and then figured out the implementation details. But your reader should implement the details first and discover the architecture pattern emerging from them. Order for the reader's workflow, not for your thought process.'''
    ),
    (
        "thinking/auto-autonomous-fixing-gaps-completeness-check",
        r'''How do I do a final completeness check on an explanation to make sure nothing essential is missing before sharing it?''',
        r'''<think>
A final completeness check is like a pre-flight checklist — it catches the things you forgot because you were focused on the main content. The check should be quick (2-3 minutes) but systematic, covering all the common gaps.

**The checklist should cover:**
1. Can the user START? (prerequisites, setup)
2. Can the user DO each step? (specific commands, not vague instructions)
3. Can the user VERIFY each step? (expected output, success criteria)
4. Can the user TROUBLESHOOT? (common errors, debugging tips)
5. Can the user understand the BIG PICTURE? (context, why this matters)
</think>

**Final Completeness Check for Explanations**

**The 60-second completeness scan:**

```
Run through these questions quickly after writing any explanation:

□ ENTRY: Can the user start?
  - Are all prerequisites listed?
  - Are installation/setup steps included?
  - Is the starting state clear? ("You should have...")

□ ACTION: Can the user do each step?
  - Are commands exact (copy-pasteable)?
  - Are file paths specific (not "the config file")?
  - Are values specified (not "your database URL")?

□ VERIFICATION: Can the user confirm each step worked?
  - Is expected output shown for key commands?
  - Are success criteria stated? ("You should see...")
  - Are screenshots or output examples included for visual steps?

□ FAILURE: Can the user recover from errors?
  - Are common errors mentioned? ("If you see X, try Y")
  - Is there a way to undo/restart if something goes wrong?
  - Is the troubleshooting section contextual (not just "check the logs")?

□ CONTEXT: Does the user understand WHY?
  - Is there a brief overview at the start?
  - Do they know what the end result will be?
  - Are they motivated to complete the steps?

□ EXIT: Does the user know what's next?
  - Are next steps or further reading mentioned?
  - Is the user left in a usable state (not mid-setup)?
  - Can they extend or modify the result?
```

**The "missing middle" test:**
```
Read only the FIRST step and the LAST step.
Is there a logical path from one to the other?

First step: "Create a new directory for your project"
Last step: "Your API is now deployed and accessible at https://..."

Can someone get from an empty directory to a deployed API
with only your intermediate steps? Or is there a "missing
middle" — a gap where several steps are assumed?

Common missing middles:
  - How to go from local development to deployment
  - How to go from sample data to real data
  - How to go from working code to production-ready code
  - How to go from single-user testing to multi-user support
```

**The "fresh eyes" technique:**
```
After writing, wait 5 minutes (or at least take a breath),
then re-read as if you're seeing it for the first time:

Read each step and literally imagine doing ONLY what's written:
  "Install the dependencies" → Which ones? With which command?
  "Create the database" → How? What type? What name?
  "Add the route" → In which file? What code exactly?

If you find yourself thinking "well, they'd obviously..." → gap.
Nothing is obvious. Make it explicit.
```

**Completeness example — finding gaps:**

```
DRAFT explanation:
  1. Install Flask
  2. Create the app
  3. Add a database
  4. Deploy

GAP ANALYSIS:
  Step 1: "Install Flask" → pip install flask? What Python version?
          In a virtualenv? Which one?
  Step 2: "Create the app" → What files? What code? Where?
  Step 3: "Add a database" → Which database? How to install it?
          How to connect? What schema?
  Step 4: "Deploy" → Where? How? What configuration?

IMPROVED:
  1. Set up the environment:
     - Install Python 3.10+: python --version to verify
     - Create virtualenv: python -m venv venv
     - Activate: source venv/bin/activate (Mac/Linux) or
       venv\Scripts\activate (Windows)
     - Install Flask: pip install flask==3.0
  2. Create the app:
     - Create app.py with this content: [full code]
     - Test: python app.py → should see "Running on http://127.0.0.1:5000"
     - Verify: Open browser to localhost:5000 → should see "Hello World"
  ...and so on with the same level of detail.
```

**The meta-principle:** Completeness is not about length — it's about leaving no step to guesswork. A 10-step explanation where each step is unambiguous and verifiable is better than a 50-step explanation where half the steps are vague. After every explanation, do the 60-second scan. It catches 90% of gaps and takes almost no time.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
