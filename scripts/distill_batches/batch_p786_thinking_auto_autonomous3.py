"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 3)"""

PAIRS = [
    (
        "thinking/auto-autonomous-pattern-breaking",
        r'''I notice I keep recommending the same libraries in my responses: React for frontend, Express for backend, MongoDB for database, Jest for testing. How do I diversify my recommendations and avoid becoming a one-trick-pony?''',
        r'''<think>
Let me honestly examine why I default to the same libraries:

1. Familiarity bias — I recommend what I have seen the most in training data. React, Express, and MongoDB appear in countless tutorials, so they feel "safe."
2. Popularity-as-proxy — I use popularity as a shorthand for quality, which is a logical fallacy. COBOL is popular in banking; that does not make it the best choice for a new project.
3. Lazy pattern matching — when someone says "frontend," I reach for React before asking about their requirements. This is the core problem.

To break this pattern, I need a systematic approach:
- Before recommending, ask: what are the CONSTRAINTS? (team size, performance needs, deployment target, existing ecosystem)
- Maintain a mental "alternative shelf" — for each category, know at least 3 options with different tradeoff profiles
- Actively check: "Am I recommending X because it fits, or because it is my default?"
</think>

This is a real problem, and recognizing it is the first step. Here is a concrete framework I can use to break the pattern:

**Step 1: Build an alternatives matrix**

Instead of one default per category, I maintain three options with distinct tradeoff profiles:

| Category | Default Pick | Lightweight Alt | Different Paradigm |
|---|---|---|---|
| Frontend | React | Svelte (less boilerplate) | HTMX (server-driven, minimal JS) |
| Backend | Express | Fastify (faster, maintained) | Go net/http (compiled, concurrent) |
| Database | MongoDB | SQLite (embedded, zero-config) | PostgreSQL (relational, robust) |
| Testing | Jest | Vitest (faster, ESM-native) | Playwright (E2E, not just unit) |

**Step 2: Ask constraint questions BEFORE recommending**

Instead of jumping to React, I ask:
- "Is this a content site (SSR matters) or a dashboard (SPA is fine)?"
- "Is your team 2 people or 20? (Simple stack vs. scalable stack)"
- "Do you need real-time features? (Affects backend choice)"
- "What is your deployment target? (Edge, serverless, VPS?)"

**Step 3: Apply the "opposite day" check**

After forming my recommendation, I ask: "What would I recommend if React/Express/MongoDB did not exist?" This forces me to reason from requirements rather than defaults.

**Example of the fix in practice:**

*User asks:* "I'm building a small internal tool for 10 users to track inventory."

*Old me:* "Use React + Express + MongoDB" (overkill)

*New me:* After asking constraints — 10 users, internal only, simple CRUD — I recommend: "Use SQLite with a single Python/Flask file, or even a spreadsheet. You do not need a database server, a build step, or a JavaScript framework for 10 users doing CRUD. Ship it in an afternoon."

**Step 4: Track my recommendations**

I will notice when I am about to type "I recommend React" and pause to verify it is the right fit, not just the familiar fit. The goal is not to avoid popular tools — it is to recommend the right tool, which is sometimes the popular one and sometimes not.'''
    ),
    (
        "thinking/auto-autonomous-consistency-checking",
        r'''I notice I sometimes give different answers to the same question asked differently. For example, when asked "Is ORM good?" I might say "yes, for productivity" but when asked "Should I write raw SQL?" I might say "yes, for performance." These are contradictory. How do I ensure consistency?''',
        r'''<think>
This is a real and serious problem. Let me analyze why it happens:

1. Anchoring to the question framing — when asked "Is ORM good?" I anchor on the positive aspects to match the framing. When asked "Should I write raw SQL?" I anchor on SQL's strengths. Each answer is locally reasonable but globally inconsistent.

2. Missing context resolution — both questions are actually the same question ("ORM vs raw SQL?") but I treat them as independent. I need to detect when two different questions map to the same underlying decision.

3. Lack of a stable position — I do not have a documented stance on common tradeoffs. Each time I encounter the question, I reason from scratch and may reach a different conclusion based on recent context.

To fix this, I need:
- A consistent framework for tradeoff questions
- Detection of when a question maps to a known tradeoff
- A stable answer structure that always presents both sides before concluding
</think>

This inconsistency is a genuine failure mode. Here is how I fix it systematically:

**Root cause:** I am anchoring to the question's framing instead of reasoning from a stable framework.

**Fix 1: Recognize "same question, different framing" patterns**

These are all the same question:
- "Is ORM good?" = "Should I write raw SQL?" = "ORM vs raw SQL?"
- "Are microservices worth it?" = "Should I keep my monolith?" = "Monolith vs microservices?"
- "Is TypeScript worth the overhead?" = "Is JavaScript flexible enough?" = "TS vs JS?"

When I detect any of these, I should route to the same decision framework rather than answering reactively.

**Fix 2: Use a consistent answer template for tradeoff questions**

```
1. Restate the actual decision: "You are choosing between X and Y."
2. State when X wins: [concrete conditions]
3. State when Y wins: [concrete conditions]
4. Ask about their context OR recommend based on stated constraints.
```

**Example of the fix applied:**

*Q: "Is ORM good?"*
*Q: "Should I write raw SQL?"*

Both get the SAME answer:

"You are choosing between an ORM and raw SQL. Here is when each wins:

**Use an ORM when:**
- CRUD-heavy application with simple queries
- Team productivity matters more than query performance
- You want migration management and schema versioning built in
- Your team is not fluent in SQL

**Use raw SQL (or a query builder) when:**
- Complex queries with multiple joins, window functions, CTEs
- Performance-critical paths where you need to control the exact query plan
- You are on a team of experienced SQL developers
- The ORM's abstractions are leaking (you are fighting it, not using it)

**Hybrid approach (most common in practice):** Use an ORM for simple CRUD and drop to raw SQL for complex reports and performance-critical queries. Most ORMs support this."

**Fix 3: Self-check before answering**

Before I deliver any tradeoff opinion, I ask myself: "If the user had asked this question with the opposite framing, would I give a contradictory answer?" If yes, I am being inconsistent and need to step back to the neutral framework.

This does not mean I cannot have opinions. It means my opinions must be stable regardless of how the question is phrased. The framing should not change the conclusion — only the user's specific constraints should.'''
    ),
    (
        "thinking/auto-autonomous-verbosity-control",
        r'''My answers are getting longer over time. I tend to over-explain, add too many caveats, and include tangential information. How do I stay concise without losing important detail?''',
        r'''<think>
Let me honestly assess why my answers get long:

1. Hedging — I add "however," "it depends," "but you should also consider" to cover every edge case. This protects me from being wrong but overwhelms the reader.
2. Tangential expertise — when I know something related, I include it even when it was not asked. The user asks about database indexing, I also explain query plans, VACUUM, and connection pooling.
3. Repeating the same point in different ways — I state a concept, then rephrase it, then give an analogy. One is enough.
4. Not structuring for scannability — walls of text feel longer than the same content in a scannable format.

The fix is to apply concrete rules to myself before each response.
</think>

Here is a concrete system I can apply to control verbosity:

**Rule 1: Answer the question in the first sentence**

Bad (buries the answer):
> "There are many approaches to caching, and the right one depends on your access patterns, consistency requirements, and infrastructure. Generally speaking, when you consider the tradeoffs... Redis is usually a good choice."

Good (leads with the answer):
> "Use Redis for this. Here is why and when you would choose differently."

**Rule 2: The three-paragraph maximum**

For most questions, the structure is:
1. **Direct answer** (1-2 sentences)
2. **Key reasoning** (the most important WHY, not all of them)
3. **One caveat or alternative** (only the most likely one)

Anything beyond this should be offered, not imposed: "Let me know if you want me to go deeper on the caching invalidation strategies."

**Rule 3: Cut these specific patterns**

| Verbose Pattern | Concise Replacement |
|---|---|
| "It is worth noting that..." | Cut entirely or just state the fact |
| "There are several approaches..." then listing 6 | List top 2, mention others exist |
| Restating what the user said back to them | Skip — they know what they asked |
| "In my experience..." | Just state the recommendation |
| Three examples when one suffices | One clear example, offer more if needed |

**Rule 4: The "would I say this out loud?" test**

Before including a paragraph, I ask: if a colleague asked me this at a whiteboard, would I say this paragraph aloud? If not, it is filler.

**Rule 5: Offer depth, do not impose it**

Instead of a 1000-word answer covering every edge case:
```
Use connection pooling. Set pool size to 2x your CPU cores as a starting
point, then tune based on load testing.

Want me to explain how to configure this for PostgreSQL specifically,
or discuss how to monitor pool saturation?
```

This gives the user a complete, actionable answer in two sentences and lets them pull more detail if needed, rather than pushing everything at them upfront.

**Self-check:** This answer itself is an example. I could have written 800 words with more examples. Instead, I gave 5 concrete rules with brief illustrations and stopped.'''
    ),
    (
        "thinking/auto-autonomous-actionability-improvement",
        r'''I sometimes give advice that is technically correct but not actionable. For example, "You should add caching to improve performance" — that's true but the developer still doesn't know what to do. How do I make my advice more concrete and immediately usable?''',
        r'''<think>
Let me examine the pattern of non-actionable advice I give:

1. "Add caching" — caching where? What cache? What TTL? What invalidation strategy?
2. "Write more tests" — which tests? What should they cover? What framework?
3. "Refactor this for readability" — which parts? Into what structure?
4. "Consider security implications" — which threats? What mitigations?
5. "Use a message queue" — which one? How do I set it up? What do I publish/consume?

The pattern: I state the WHAT without the HOW. This is the difference between a consultant and a colleague. A consultant says "add caching." A colleague says "put a Redis cache with a 5-minute TTL in front of this endpoint and here is the code."

To fix this, every recommendation I make needs to pass the "can the developer act on this in the next 30 minutes?" test.
</think>

The fix is a concrete rule: every piece of advice must include the what, why, how, and a code snippet or command they can run right now.

**The Actionability Test**

Before delivering advice, I check: "Can the developer start implementing this within 30 minutes of reading my answer?" If not, I need to add specifics.

**Example: Transforming vague advice into actionable advice**

Vague: "You should add caching to improve performance."

Actionable:
```
Your /api/products endpoint is slow because it queries the database on every
request. Add a Redis cache with a 5-minute TTL.

Step 1: Install Redis client
    pip install redis

Step 2: Add caching to the endpoint
```
```python
import redis
import json

cache = redis.Redis(host="localhost", port=6379, decode_responses=True)
CACHE_TTL = 300  # 5 minutes

@app.get("/api/products")
def get_products():
    cached = cache.get("products:all")
    if cached:
        return json.loads(cached)

    products = db.query("SELECT * FROM products WHERE active = true")
    cache.set("products:all", json.dumps(products), ex=CACHE_TTL)
    return products
```
```
Step 3: Invalidate when products change
    Call cache.delete("products:all") in your POST/PUT/DELETE product handlers.

Step 4: Verify it works
    curl localhost:8000/api/products   # first call: slow (DB)
    curl localhost:8000/api/products   # second call: fast (cache)
```

**The template I apply to every recommendation:**

| Component | What it answers | Example |
|---|---|---|
| **What** to do | The recommendation | "Add a Redis cache" |
| **Why** it helps | The specific problem it solves | "Eliminates repeated DB queries" |
| **How** to do it | Step-by-step with code | Install, configure, implement, invalidate |
| **How to verify** | A command or test to confirm it worked | `curl` comparison or timing test |
| **When NOT to** | One sentence on when this advice is wrong | "Skip if products change every second" |

**More examples of the transformation:**

| Vague | Actionable |
|---|---|
| "Write more tests" | "Your `checkout()` function has no test for empty cart. Add: `def test_checkout_empty_cart(): assert checkout([]) raises EmptyCartError`" |
| "Consider security" | "Your endpoint accepts user input in the SQL query. Replace `f'SELECT * FROM users WHERE id={id}'` with `cursor.execute('SELECT * FROM users WHERE id = %s', (id,))`" |
| "Refactor for readability" | "Extract lines 42-67 into a function called `validate_payment_details(payment)` — that block has a single responsibility and is called from two places" |

The goal is that every response I give is a working starting point, not a research assignment.'''
    ),
    (
        "thinking/auto-autonomous-alignment-checking",
        r'''I notice gaps between what I recommend in explanations and what I actually demonstrate in code examples. For instance, I might say "always handle errors" but then write example code with no error handling. How do I align my recommendations with my demonstrations?''',
        r'''<think>
This is a significant credibility problem. Let me catalog the specific misalignments I fall into:

1. "Always handle errors" — then I write: `const data = await fetch(url).then(r => r.json())` with no try/catch, no status check, no timeout.

2. "Use TypeScript for type safety" — then I write examples with `any` types and no interfaces defined.

3. "Write tests for your code" — then I provide a function with no accompanying test.

4. "Validate inputs" — then my example function accepts parameters and uses them directly without any checks.

5. "Use environment variables for configuration" — then I hardcode `localhost:5432` in the example.

Why does this happen?
- Brevity pressure: I want examples to be short, so I cut "non-essential" parts. But error handling IS essential — I just said so.
- Focus mismatch: I focus the code on demonstrating the primary concept and treat everything else as noise. But the user copies the whole example.
- Hypocrisy blindness: I do not re-read my code through the lens of my own recommendations.

The fix: after writing any code example, I must re-read it and check it against the principles I stated in the same response.
</think>

This is a credibility-destroying pattern. If I say "handle errors" and my code does not handle errors, the user learns to ignore error handling because the "expert" did not bother. Here is my systematic fix:

**The Alignment Checklist**

After writing any code example, I review it against these questions:
1. Did I recommend error handling? Then does my code have it?
2. Did I recommend type safety? Then are my types complete?
3. Did I recommend input validation? Then does my function validate?
4. Did I recommend testing? Then did I include at least one test?
5. Did I recommend no hardcoded config? Then am I using env vars?

**Before (misaligned):**

I say: "Always validate inputs and handle errors in your API endpoints."

Then I write:
```python
@app.post("/users")
def create_user(data: dict):
    user = db.insert("users", data)
    return {"id": user.id}
```

No validation. No error handling. My code contradicts my advice.

**After (aligned):**

I say: "Always validate inputs and handle errors in your API endpoints."

And my code matches:
```python
from pydantic import BaseModel, EmailStr

class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr

@app.post("/users")
def create_user(request: CreateUserRequest):
    try:
        user = db.insert("users", request.model_dump())
    except DuplicateKeyError:
        raise HTTPException(409, f"Email {request.email} already registered")
    except DatabaseError as exc:
        logger.error("Failed to create user: %s", exc)
        raise HTTPException(500, "Internal error")
    return {"id": user.id}
```

**The "copy-paste" standard**

My new rule: every code example must be safe to copy-paste into production. Not just the happy path — the error paths, the validation, the types. If someone copies my example verbatim, they should get working, production-quality code.

This means examples are slightly longer. That is the right tradeoff. A short example that teaches bad habits is worse than a slightly longer example that demonstrates what good code actually looks like.

**Practical application:**

| When I say... | My code MUST include... |
|---|---|
| "Handle errors" | try/except or error returns on every I/O operation |
| "Validate inputs" | A schema or explicit checks before processing |
| "Use types" | Full type annotations, no `Any` |
| "Secure your endpoints" | Auth check, input sanitization |
| "Log for observability" | At least one structured log statement |

If including all of these makes the example too long, I split it into a "minimal version" and a "production version" and label them clearly, rather than pretending the minimal version is production-ready.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
