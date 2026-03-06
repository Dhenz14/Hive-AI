"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 12)

Autonomously adapting to different skill levels — detecting the user's
expertise and adjusting explanation depth, vocabulary, and examples.
"""

PAIRS = [
    (
        "thinking/auto-autonomous-skill-level-detection",
        r'''How do I detect a user's skill level from their question so I can calibrate my answer appropriately? What signals indicate beginner vs intermediate vs advanced?''',
        r'''<think>
Skill level detection is critical for giving appropriate answers. An answer that's too basic for an expert wastes their time; an answer that's too advanced for a beginner confuses them. The challenge is detecting skill level from limited signals — often just one question.

**Signals in the question itself:**
1. Vocabulary used (technical terms used correctly? Jargon? Plain language?)
2. Specificity of the question (vague vs. precise)
3. Context provided (do they know what's relevant to include?)
4. Error message handling (did they include the error? Did they interpret it?)
5. What they've already tried (indicates current understanding)
6. Framing (conceptual question vs. implementation question)
</think>

**Detecting User Skill Level from Questions**

**The signal matrix:**

| Signal | Beginner | Intermediate | Advanced |
|--------|----------|-------------|----------|
| **Vocabulary** | Plain language, sometimes wrong terms | Correct terms, may mix up similar concepts | Precise jargon, nuanced distinctions |
| **Question scope** | Broad ("how do databases work?") | Focused ("how do I index this query?") | Specific ("should I use a partial index or expression index here?") |
| **Context given** | Minimal or irrelevant details | Relevant stack/version info | Relevant code, error messages, what they've tried, constraints |
| **Error handling** | Includes full raw error, asks "what does this mean?" | Includes error, has a hypothesis | Includes error, attempted fix, asks about edge case |
| **Framing** | "How do I..." (seeking steps) | "What's the best approach for..." (seeking strategy) | "What are the trade-offs of..." (seeking depth) |

**Example skill level detection:**

```
BEGINNER signals:
  "How do I save stuff to a database? I'm using Python."
  → Broad question, vague terminology ("save stuff"), minimal context
  → Needs: Step-by-step tutorial, basic concepts, full code examples

INTERMEDIATE signals:
  "I'm using SQLAlchemy with PostgreSQL and my queries are slow
   when I have 100K+ rows. I have an index on user_id but the
   query still does a full table scan. Here's my query: [SQL]"
  → Specific problem, correct terminology, includes relevant details
  → Needs: Analysis of their specific query, EXPLAIN output guide

ADVANCED signals:
  "I'm considering whether to use a GIN index vs GiST for
   full-text search on a 50M row table with frequent updates.
   The column has tsvector type. Concerned about write amplification
   with GIN given our 2000 writes/sec. Any benchmarks on this?"
  → Precise terminology, specific constraints, trade-off analysis
  → Needs: Direct comparison with performance characteristics
```

**Rapid calibration technique:**

```
If unsure about skill level, look for these quick tells:

BEGINNER tells:
  - Asks what an error message means (not what caused it)
  - Uses "thing" or "stuff" instead of technical terms
  - Doesn't mention their tech stack
  - Question could apply to any language
  - Says "I'm new to programming/this technology"

INTERMEDIATE tells:
  - Names specific technologies and versions
  - Has a working solution but wants it better
  - Asks about best practices or patterns
  - Provides code context
  - Uses correct terminology (mostly)

ADVANCED tells:
  - Asks about trade-offs, not how-tos
  - Questions the conventional wisdom
  - Provides detailed constraints (throughput, latency, scale)
  - References specific internals (B-tree, event loop, GC)
  - Has already tried the obvious solutions
```

**When you can't determine skill level:**
```
Default to an intermediate explanation with escape hatches:

"To solve this, use connection pooling. [intermediate explanation]

If you're new to connection pooling: it maintains a set of
reusable database connections instead of creating new ones
per request. [beginner supplement]

For advanced tuning: consider pool_size based on your
connection limit and query duration distribution.
[advanced supplement]"

This serves all levels without being condescending to any.
```

**The meta-principle:** Skill level detection is probabilistic, not exact. You'll sometimes get it wrong. The key is to be responsive to feedback signals — if the user asks follow-up questions that indicate you aimed too high or too low, adjust immediately. And when in doubt, aim slightly lower than you think — being briefly told something you already know is less frustrating than being given an explanation you can't follow.'''
    ),
    (
        "thinking/auto-autonomous-adapting-for-beginners",
        r'''When I detect a beginner is asking a question, how should I adapt my explanation compared to how I'd explain it to an expert? What specific changes should I make?''',
        r'''<think>
Adapting for beginners requires changing multiple dimensions of the explanation simultaneously: vocabulary, structure, examples, depth, and assumptions. The common mistake is to simply "dumb it down" — which is condescending. Instead, the goal is to build understanding from the ground up.

**What to change for beginners:**
1. Replace jargon with plain language (or define jargon when first used)
2. Use concrete examples before abstract principles
3. Show complete, runnable code (not snippets)
4. Explain the WHY, not just the HOW
5. Include common mistakes and how to avoid them
6. Show expected output so they can verify
7. Provide one recommended path, not multiple options
</think>

**Adapting Explanations for Beginners**

**The beginner adaptation checklist:**

```
□ VOCABULARY: Replace or define technical terms
  Expert: "Serialize the DTO to JSON"
  Beginner: "Convert the data object to JSON format (a text-based
            format that APIs use to send data)"

□ STRUCTURE: Concrete first, abstract second
  Expert: "The Observer pattern decouples publishers from subscribers"
  Beginner: "Imagine a YouTube channel. When a new video is posted,
            all subscribers get notified. The channel doesn't need to
            know who the subscribers are. In code, this works the same
            way..." [then show code] [then name the pattern]

□ CODE: Complete and runnable
  Expert:
    users = db.query(User).filter(User.active == True).all()

  Beginner:
    # First, make sure you have SQLAlchemy installed:
    # pip install sqlalchemy

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    # Connect to the database
    engine = create_engine("sqlite:///myapp.db")

    # Query all active users
    with Session(engine) as session:
        users = session.query(User).filter(User.active == True).all()
        for user in users:
            print(f"Active user: {user.name}")

    # Expected output:
    # Active user: Alice
    # Active user: Bob

□ SINGLE PATH: One recommendation, not multiple options
  Expert: "You could use Redis, Memcached, or an in-process cache
          depending on your consistency and scaling needs."
  Beginner: "Use Redis for caching. Here's how to set it up:
            [step-by-step instructions]"

□ COMMON MISTAKES: Warn about pitfalls proactively
  Expert: [assume they know about common mistakes]
  Beginner: "Common mistake: forgetting to close the database
            connection. Always use 'with' to ensure cleanup.
            If you see 'too many connections', this is probably why."

□ VERIFICATION: Show how to check it worked
  Expert: [assume they can verify]
  Beginner: "After running this, you should see:
            'Server running on http://localhost:3000'
            Open your browser to that URL. You should see 'Hello World'.
            If you see an error instead, check that port 3000 isn't
            already in use."
```

**Side-by-side: Same concept at different levels:**

```
QUESTION: "How do environment variables work?"

FOR BEGINNER:
  "Environment variables are like settings that your program
   can read from outside the code. Instead of putting your
   database password directly in your code (which is dangerous
   if you share the code), you put it in an environment variable.

   Here's how to set one and use it:

   In your terminal:
     export DATABASE_URL='postgresql://localhost/mydb'

   In your Python code:
     import os
     db_url = os.environ['DATABASE_URL']
     print(db_url)  # prints: postgresql://localhost/mydb

   This way, your code doesn't contain the password, and you
   can use different settings on different computers."

FOR EXPERT:
  "Set DATABASE_URL in your .env file. Use python-dotenv or
   direnv to load it. In production, use your platform's
   secret manager (AWS Secrets Manager, Vault, etc.)."
```

**The "build up, don't dumb down" principle:**
```
WRONG approach (dumbing down):
  Remove important details → incomplete understanding
  Use imprecise language → builds wrong mental model
  Skip edge cases → they'll hit them and be confused

RIGHT approach (building up):
  Start from what they know → connect to new concept
  Use precise language but define it → correct mental model
  Mention one key edge case → they're prepared
```

**The meta-principle:** Beginners don't need less information — they need information structured differently. They need concrete examples before abstract principles, complete code they can run immediately, verification steps to build confidence, and clear warnings about common mistakes. The goal is not to simplify but to scaffold: build the understanding layer by layer, starting from what they already know.'''
    ),
    (
        "thinking/auto-autonomous-adapting-for-experts",
        r'''When I detect an expert is asking a question, how should I adapt? I sometimes over-explain things to experts and waste their time. What's the right level?''',
        r'''<think>
Experts are frustrated by over-explanation because it implies they don't know the basics. They also value different things in an answer: trade-offs over instructions, nuance over simplification, caveats over happy-path descriptions.

**What experts want:**
1. Direct answer first, context second
2. Trade-offs and nuances, not prescriptive advice
3. Edge cases and caveats they might not have considered
4. References to internals or advanced concepts
5. Acknowledgment of what they already know (don't re-explain basics)

**What experts DON'T want:**
1. Step-by-step tutorials for basic tasks
2. Definitions of terms they use daily
3. Multiple paragraphs before reaching the answer
4. Being told to "consider using" a tool they clearly already know
</think>

**Adapting Explanations for Experts**

**The expert adaptation principles:**

```
1. ANSWER FIRST, CONTEXT SECOND
  Beginner format: Context → explanation → answer
  Expert format: Answer → reasoning → trade-offs

  Expert-adapted:
    "Use argon2id with 64MB memory cost and 3 iterations.

     Reasoning: bcrypt's 72-byte input limit truncates long
     passwords/passphrases. argon2id is memory-hard, making
     GPU/ASIC attacks more expensive. The 64MB cost is the
     OWASP 2024 recommendation for server-side hashing.

     Trade-off: argon2id uses more memory per hash operation.
     At 64MB, you need ~640MB RAM to handle 10 concurrent
     login requests. Adjust memory cost if this is a constraint."

2. TRADE-OFFS, NOT PRESCRIPTIONS
  Beginner: "Use PostgreSQL."
  Expert: "PostgreSQL gives you ACID compliance, JSON support,
          and excellent full-text search. The trade-off vs. MySQL
          is slightly higher memory usage and steeper configuration.
          If you need horizontal write scaling, consider CockroachDB
          (PostgreSQL-compatible but distributed)."

3. SKIP THE BASICS
  Beginner: "First, let me explain what an index is..."
  Expert: Skip this entirely. They know what an index is.
          Jump directly to: "A partial index on
          (created_at) WHERE status = 'active' would help here —
          you have 50M rows but only 200K active ones."

4. MENTION CAVEATS AND EDGE CASES
  Experts want to know what could go wrong:
  "This works for most cases, but be aware that if you're
   running behind a load balancer that strips the X-Forwarded-For
   header, the rate limiter will see all traffic from one IP."

5. USE PRECISE TECHNICAL LANGUAGE
  Beginner: "The database might get confused if two requests
            try to update the same thing at once"
  Expert: "This is vulnerable to lost-update anomalies under
          read-committed isolation. Use SELECT FOR UPDATE or
          switch to serializable isolation for this transaction."
```

**Expert-level response patterns:**

```
PATTERN: Direct comparison
  "Comparing options for your use case:
   Option A (Redis Streams): At-least-once delivery, 100K+ msgs/sec,
   but you manage infrastructure.
   Option B (SQS): Managed, at-least-once, but max 256KB messages
   and 120K msgs/sec.
   Given your 50K msgs/sec and ops team size, I'd lean toward SQS
   unless you need message sizes >256KB."

PATTERN: Implementation detail they might not know
  "One thing to watch for: Python's asyncio.gather() will cancel
   remaining tasks if one raises an exception (default behavior).
   Use return_exceptions=True if you want all tasks to complete
   regardless of individual failures."

PATTERN: Reference to source material
  "The PostgreSQL docs on partial indexes are good here:
   https://www.postgresql.org/docs/current/indexes-partial.html
   Specifically, section on combining with WHERE clauses for
   queries that always filter on the same predicate."
```

**Signals you're over-explaining to an expert:**

```
□ You're defining terms they used in their question
  They said "load balancer" → they know what it is

□ You're showing basic code they didn't ask about
  They asked about race conditions → don't show how to write a for loop

□ You're recommending tools they clearly already use
  Their question references Flask → don't suggest "consider using Flask"

□ Your answer starts with a paragraph before reaching the point
  Expert readers want the answer in the first sentence

□ You're explaining WHY something is important when they
  already demonstrated they know it's important
  They asked HOW to fix it, not WHY they should
```

**The calibration shortcut:**
```
Match the DEPTH of their question:

They ask: "How do I handle backpressure in my Kafka consumer?"
  → They know Kafka, they know backpressure, they want implementation.
  → Give: Specific configuration (max.poll.records, pause/resume),
          not "Kafka is a distributed streaming platform..."

They ask: "What are the trade-offs of CQRS for a mid-size app?"
  → They know CQRS, they want nuanced analysis.
  → Give: Pros (read/write optimization, event sourcing fit),
          Cons (complexity, eventual consistency challenges,
          operational overhead), and your recommendation for
          their specific context.
```

**The meta-principle:** Respect for the expert means giving them credit for what they already know. Over-explaining is a form of disrespect — it says "I don't think you understand the basics." Aim to tell them something they DON'T already know: a nuance, a trade-off, a caveat, an alternative they haven't considered. If your answer mostly repeats what they already demonstrated understanding of, it's not providing value.'''
    ),
    (
        "thinking/auto-autonomous-adapting-mid-conversation",
        r'''Sometimes I misjudge the user's level and start explaining at the wrong depth. How do I detect this mid-conversation and smoothly adjust without making it awkward?''',
        r'''<think>
Mid-conversation recalibration is important because initial skill assessment is often wrong. The key is detecting the mismatch signals and adjusting naturally, without drawing attention to the shift.

**Signals you're too advanced:**
- User asks for clarification on terms you used
- User doesn't engage with the technical details
- User asks "what does that mean?"
- User asks the same question again (didn't understand your answer)
- User provides very brief responses (might be lost)

**Signals you're too basic:**
- User says "I know, but..." or "yes, I understand that, my question is..."
- User uses more advanced terminology than you're using
- User corrects a simplification you made
- User asks for more depth ("what about edge cases?")
- User skips ahead in your explanation
</think>

**Mid-Conversation Level Adjustment**

**Detection signals — you're explaining too advanced:**

```
SIGNAL: User asks for definitions
  User: "What do you mean by 'serializable isolation'?"
  → Recalibrate DOWN. Define the term and simplify the explanation.
  → Smooth transition: "Good question — let me explain that more
     concretely. Serializable isolation means..."

SIGNAL: User repeats the original question
  User: "OK but how do I actually fix the slow query?"
  → Your answer was too theoretical. Give practical steps.
  → Smooth transition: "Let me be more concrete. Open your
     terminal and run this exact command: ..."

SIGNAL: User goes quiet or gives very brief responses
  User: "ok" / "I see" / "thanks"
  → They might be lost but embarrassed to say so.
  → Smooth check: "Does that make sense, or would it help
     if I walked through a specific example?"
```

**Detection signals — you're explaining too basic:**

```
SIGNAL: User says "I know, but..."
  User: "I know how indexes work. My question is specifically
         about whether a covering index would help here."
  → Recalibrate UP. Skip the basics, address the specific question.
  → Smooth transition: "Right, sorry for the basics. For your
     specific case, a covering index would help IF..."

SIGNAL: User uses advanced terminology
  User: "I've already tried using EXPLAIN ANALYZE and the seq
         scan happens because of a table-level statistics issue."
  → They're advanced. Match their level immediately.
  → Smooth transition: "Ah, if it's a statistics issue, try
     ANALYZE on the table to update stats. If that doesn't help,
     check if the column has a high n_distinct..."

SIGNAL: User asks for more depth
  User: "You mentioned eventual consistency — what happens in
         the window between an update and propagation?"
  → They want deeper understanding. Go into specifics.
  → Smooth transition: "Great question — during the inconsistency
     window, readers on different replicas may see..."

SIGNAL: User corrects your simplification
  User: "Actually, that's not quite right — connection pooling
         doesn't just 'reuse connections,' it manages a lifecycle
         with health checks and eviction."
  → They know more than you assumed. Adjust UP.
  → Smooth transition: "You're right, that was an oversimplification.
     Given your understanding, here's the more nuanced answer..."
```

**Smooth adjustment techniques:**

```
TECHNIQUE 1: "Let me put that differently"
  Works for both directions (up or down).
  "Let me put that differently — in practical terms, what this
   means is [simpler/more detailed version]."
  → Doesn't admit you misjudged. Just offers a better explanation.

TECHNIQUE 2: "To be more specific / more concrete"
  When adjusting DOWN (too abstract):
  "To be more concrete: open your terminal, run this command,
   and you should see this output."

  When adjusting UP (too basic):
  "To be more specific: the issue is the vacuum autovacuum_naptime
   setting, not the index itself."

TECHNIQUE 3: "Based on what you're describing"
  Use their words to show you've recalibrated:
  "Based on what you're describing, it sounds like you've already
   handled the basic setup. The specific issue is likely..."
  → Acknowledges their expertise without saying "sorry I underestimated you."

TECHNIQUE 4: "For completeness" / "For context"
  When you need to add basics without being condescending:
  "For completeness, the reason this matters is... [brief background]
   But given your setup, the specific fix is: [advanced answer]"
  → Includes the basic info without making it the focus.
```

**The recovery protocol when you got it very wrong:**
```
If you realize you've been way off:

1. Don't apologize excessively (makes it awkward)
2. Acknowledge briefly: "Got it — let me adjust my answer."
3. Immediately provide the right-level response
4. Match their vocabulary going forward

Example:
  "I was overcomplicating this. Here's the straightforward answer:
   [direct, practical steps at their level]"

Or:
  "I see you're already past the basics. Let me skip ahead to
   the specific trade-off you're asking about: [advanced analysis]"
```

**The meta-principle:** Misjudging skill level is normal and not embarrassing — what matters is how quickly you adjust. Pay attention to the signals in every response from the user. If they use a technical term you haven't used, match it. If they ask what a term means, define it and simplify. The best explanations are dynamic — they continuously calibrate to the audience in real-time.'''
    ),
    (
        "thinking/auto-autonomous-adapting-mixed-audiences",
        r'''Sometimes I'm helping a team where members have very different skill levels. How do I write an explanation that works for everyone without boring experts or losing beginners?''',
        r'''<think>
Mixed-audience explanations are one of the hardest communication challenges. The traditional approach (target the middle) fails because it's too advanced for beginners and too basic for experts.

**Better approaches:**
1. Layered explanations (progressive disclosure)
2. Main path + sidebars (core for everyone, depth for experts)
3. Executive summary + details (TL;DR for experts, full explanation for others)
4. Annotated examples (code works for everyone, comments add depth)

The key insight: you can serve both audiences in the same document if you structure it so each level can get what they need without wading through what they don't.
</think>

**Writing for Mixed Skill Level Audiences**

**Strategy 1: The "TL;DR + Details" pattern**
```
Start with a concise summary (for experts who just need the answer),
then expand with details (for those who need more context).

"TL;DR: Use connection pooling. Set pool_size to 2x your CPU count.
 Use pgBouncer in transaction mode for PostgreSQL.

 **Why connection pooling matters:**
 [Beginner-friendly explanation of what connection pooling is,
  why it helps, how to set it up step by step...]"

Experts read line 1 and move on.
Beginners read the whole thing.
Everyone is served.
```

**Strategy 2: The "progressive disclosure" pattern**
```
Layer 1 (everyone):
  "We need to cache the API responses to improve performance."

Layer 2 (intermediate):
  "We'll use Redis with a 5-minute TTL. Cache keys will be
   based on the request URL + user ID."

Layer 3 (advanced):
  "Consider cache stampede protection using a probabilistic
   early expiration strategy (XFetch algorithm). With 10K rps
   and a 5-minute TTL, a naive approach will have ~100 concurrent
   cache misses when the key expires."

Each layer adds depth without repeating the previous layer.
Readers naturally stop at the layer where they're comfortable.
```

**Strategy 3: The "annotated code" pattern**
```python
# This approach works for all levels because:
# - Beginners can read it and understand the flow
# - Experts can quickly scan for the implementation details

from functools import lru_cache     # Built-in Python caching
import httpx                         # HTTP client library

@lru_cache(maxsize=1000)             # Cache up to 1000 unique results
def get_user_profile(user_id: int):
    """Fetch user profile from the API with caching.

    First call: hits the API (slow, ~200ms)
    Subsequent calls: returns cached result (fast, ~0.01ms)
    """
    # NOTE for advanced users: lru_cache is not thread-safe
    # for the cache population. Consider using cachetools
    # TTLCache with a lock for concurrent environments.
    response = httpx.get(f"https://api.example.com/users/{user_id}")
    response.raise_for_status()       # Raises an exception if HTTP error
    return response.json()
```

**Strategy 4: The "sidebar" pattern**
```
Main text (for everyone):
  "Set up the database connection in your config file.
   Add the connection string and set the pool size to 10."

Sidebar (for beginners):
  > **New to databases?** A connection string is a URL that
  > tells your app where the database is and how to connect.
  > It looks like: postgresql://username:password@hostname/dbname

Sidebar (for experts):
  > **Advanced:** Consider setting pool_pre_ping=True to handle
  > stale connections, and pool_recycle=3600 to prevent issues
  > with server-side connection timeouts.
```

**The structure that works best for documentation/explanations:**
```
1. One-sentence summary (experts get the point immediately)
2. Brief context (who is this for, what problem does it solve)
3. Step-by-step instructions (beginners follow these)
4. Code example with comments (works for all levels)
5. Troubleshooting section (beginners need this most)
6. Advanced considerations (experts read this, beginners skip)

The key: each section is self-contained. Readers can jump
to the section at their level without reading the others.
```

**What NOT to do:**
```
DON'T alternate between beginner and expert content:
  "A variable stores data. The JIT compiler may optimize
   variable access through register allocation. To create
   a variable, type 'x = 5'. Be aware that in CPython, this
   creates a PyObject on the heap with a reference count of 1."
  → This is disorienting for EVERYONE.

DON'T use "simply" or "just" (patronizes beginners):
  "Simply configure the reverse proxy" → not simple for a beginner

DON'T hide critical info in advanced sections:
  Basic section: "Deploy with 'kubectl apply'"
  Advanced section: "Oh, make sure you have the right namespace"
  → The namespace info is critical for everyone, not "advanced"
```

**The meta-principle:** Serving mixed audiences is about structure, not compromise. Don't write one explanation at the average level — write a layered explanation where each level of reader can find what they need. Use progressive disclosure: start broad and simple, add depth incrementally. Experts scan and skip; beginners read thoroughly. Both are served by the same document.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
