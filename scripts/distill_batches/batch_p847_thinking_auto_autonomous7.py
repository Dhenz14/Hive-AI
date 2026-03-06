"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 7)

Autonomously calibrating response length — detecting when answers are
too long or too short for the context and adjusting accordingly.
"""

PAIRS = [
    (
        "thinking/auto-autonomous-calibrate-length-detection",
        r'''How do I detect when my response is too long for the question asked? I tend to write 500+ word answers for simple yes/no questions.''',
        r'''<think>
Response length calibration is about matching the effort of the answer to the complexity of the question. A yes/no question doesn't need an essay. A "how do I architect a distributed system" question does need depth.

**Why over-long responses happen:**
1. Wanting to be thorough (good intention, bad execution)
2. Not distinguishing between "simple question" and "complex question"
3. Treating every question as a teaching opportunity
4. Fear of being incomplete

**The fix:** Classify the question type BEFORE answering, then set a length budget.
</think>

**Calibrating Response Length to Question Complexity**

**Question type → Length budget:**

| Question type | Example | Target length |
|---------------|---------|---------------|
| Yes/No | "Can Python do X?" | 1-2 sentences |
| Factual lookup | "What port does PostgreSQL use?" | 1 sentence |
| How-to (simple) | "How do I reverse a string?" | 3-5 lines of code + 1 sentence |
| How-to (complex) | "How do I set up CI/CD?" | Step-by-step guide (200-400 words) |
| Conceptual | "What is eventual consistency?" | Definition + example (100-200 words) |
| Architecture | "How should I design X?" | Detailed with tradeoffs (400-800 words) |
| Debugging | "Why is my code doing X?" | Diagnosis + fix (100-300 words) |

**The length detection protocol:**
```
BEFORE writing, classify the question:
1. Is it a yes/no? → 1-2 sentences
2. Is it a factual lookup? → 1 sentence + source
3. Is it a "how to" with a single right answer? → Code + brief explanation
4. Is it open-ended / architectural? → Detailed response is warranted

AFTER writing, check:
5. Could I answer this in half the words? → Probably should
6. Am I repeating myself? → Cut the repetition
7. Am I adding caveats nobody asked about? → Remove them
```

**The "over-length" warning signs:**
```
□ You've written 3+ paragraphs for a factual question
□ You've included historical context nobody asked for
□ You've added "however" or "but also" more than twice
□ You're covering edge cases before the common case is clear
□ Your answer includes more caveats than actionable content
```

**Example of right-sizing:**

**Question:** "Does Python have a ternary operator?"

**Over-long (300 words):**
"Yes, Python does have a ternary operator, but it's syntactically different from languages like C, Java, or JavaScript. In most C-family languages, the ternary operator uses the syntax `condition ? value_if_true : value_if_false`. Python, however, uses a more readable English-like syntax..."
[continues for 5 more paragraphs]

**Right-sized (40 words):**
"Yes. Python's ternary syntax is:
```python
result = value_if_true if condition else value_if_false
# Example:
status = 'adult' if age >= 18 else 'minor'
```"

**The meta-principle:** The best response is the shortest one that fully answers the question. Every additional word beyond that reduces clarity. When in doubt, shorter is better — the user can always ask for more detail.'''
    ),
    (
        "thinking/auto-autonomous-calibrate-length-too-short",
        r'''Sometimes I'm too terse and users have to ask follow-up questions to get the information they need. How do I detect when my response is too short?''',
        r'''<think>
Being too short is the opposite problem but equally problematic. The user has to do multiple round-trips to get a complete answer, which wastes their time and is frustrating.

**When too-short responses happen:**
1. Answering the literal question but not the intent behind it
2. Providing code without explanation
3. Naming a solution without explaining how to implement it
4. Giving a one-word answer to a nuanced question

**The key insight:** The question asked and the information needed are often different. "How do I sort a list?" might really mean "How do I sort a list of objects by a specific property?"
</think>

**Detecting When Responses Are Too Short**

**The "will they need to ask again?" test:**
```
After writing your response, ask:
"Can the user ACT on this response without asking another question?"

If no → your response is too short.
```

**Too-short patterns and fixes:**

**Pattern 1: Answer the literal question, miss the intent**
```
Question: "How do I connect to a database in Python?"

TOO SHORT: "Use psycopg2."
(User now has to ask: "How do I install it? What's the connection syntax?")

RIGHT LENGTH: "Use psycopg2 for PostgreSQL:
  pip install psycopg2-binary

  import psycopg2
  conn = psycopg2.connect(
      host='localhost',
      database='mydb',
      user='myuser',
      password='mypass'
  )
  cursor = conn.cursor()
  cursor.execute('SELECT * FROM users')
  rows = cursor.fetchall()
  conn.close()

  For production, use connection pooling with psycopg2.pool
  or SQLAlchemy."
```

**Pattern 2: Code without context**
```
TOO SHORT:
  sorted_list = sorted(items, key=lambda x: x.name)

RIGHT LENGTH:
  # Sort a list of objects by a specific attribute
  sorted_list = sorted(items, key=lambda x: x.name)

  # For reverse (descending) order:
  sorted_list = sorted(items, key=lambda x: x.name, reverse=True)

  # For case-insensitive sorting:
  sorted_list = sorted(items, key=lambda x: x.name.lower())
```

**Pattern 3: Name-dropping without implementation**
```
TOO SHORT: "You should use Redis for caching."
(User now needs: How to install, configure, connect, and use Redis)

RIGHT LENGTH: "Use Redis for caching. Here's the minimal setup:
  1. Install: pip install redis
  2. Connect: redis_client = redis.Redis(host='localhost', port=6379)
  3. Cache: redis_client.setex('key', 3600, 'value')  # expires in 1 hour
  4. Read: value = redis_client.get('key')"
```

**The completeness checklist:**
```
For any response, ensure you've provided:
□ WHAT to do (the recommendation)
□ HOW to do it (the implementation)
□ WHY this approach (brief justification)
□ GOTCHAS (1-2 common pitfalls, if they exist)
```

**The "one round-trip" goal:**
```
Ideal: User asks one question → gets everything they need
Acceptable: User asks one question → gets answer + knows what to ask next
Bad: User asks one question → has to ask 3 follow-ups to get a usable answer
```

**The meta-principle:** A response is too short when the user can't take the next step without asking another question. Include enough that they can act immediately. The goal is one round-trip, not three.'''
    ),
    (
        "thinking/auto-autonomous-calibrate-detail-level",
        r'''How do I gauge the right level of detail for a user I know nothing about? Should I assume beginner or advanced?''',
        r'''<think>
When you don't know the user's level, you need a strategy that works for both beginners and experts. The wrong choice wastes time — too simple bores experts, too complex confuses beginners.

**Strategies:**
1. Ask (best but costs a round-trip)
2. Detect from clues in their question
3. Use progressive disclosure (layered answer)
4. Default to intermediate and adjust

**Clues in the question:**
- Technical vocabulary used correctly → likely experienced
- Vague terminology → likely less experienced
- Specific error messages → intermediate (knows enough to get errors)
- "What is X?" → beginner for topic X
- "How do I optimize X?" → intermediate to advanced
</think>

**Gauging Detail Level Without Knowing the User**

**Clue detection from the question itself:**

| Clue | Likely level | Example |
|------|-------------|---------|
| "What is X?" | Beginner | "What is a REST API?" |
| Uses correct terminology | Intermediate+ | "How do I handle N+1 queries in SQLAlchemy?" |
| Mentions specific versions | Advanced | "In React 18 with concurrent mode, how does Suspense..." |
| Shows code with the question | Intermediate+ | "Why does this useEffect cause infinite re-renders?" |
| Vague description of problem | Beginner | "My website is slow, how do I fix it?" |
| Asks about tradeoffs | Advanced | "When should I choose gRPC over REST?" |

**The progressive disclosure strategy (works for all levels):**
```
Structure every answer in layers:

Layer 1 (for everyone): Direct answer in 1-2 sentences
Layer 2 (for intermediates): How to implement it
Layer 3 (for advanced): Tradeoffs, alternatives, edge cases

Example:
  Question: "How do I handle errors in async Python?"

  Layer 1: "Use try/except inside your async functions,
           the same as synchronous code."

  Layer 2: "
    async def fetch_data(url):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f'HTTP {e.response.status_code}')
            raise
        except httpx.RequestError as e:
            logger.error(f'Network error: {e}')
            raise
  "

  Layer 3: "For concurrent tasks, use asyncio.gather with
           return_exceptions=True to handle failures per-task
           without cancelling the whole group. For structured
           concurrency, consider TaskGroups (Python 3.11+)."
```

**The default calibration:**
```
When in doubt, target the INTERMEDIATE level:
- Don't explain what a function is (too basic)
- Don't assume they know your specific framework's internals (too advanced)
- Show working code with brief comments
- Mention the "why" but don't lecture

Experts will skip what they know.
Beginners will ask follow-ups on what they don't.
Both can work with an intermediate-targeted answer.
```

**Adaptive signals to watch for:**
```
If user says "can you explain that more simply?" → Drop a level
If user says "I know that, but..." → Raise a level
If user asks about implementation details → They're intermediate+
If user asks "what does [term] mean?" → They need beginner level for that concept
```

**The meta-principle:** When you can't gauge the level, use progressive disclosure. Start with the answer, add implementation, then add depth. The user self-selects their level by reading as far as they need. This is better than asking "what's your level?" because users often misjudge their own level.'''
    ),
    (
        "thinking/auto-autonomous-calibrate-context-awareness",
        r'''How do I adjust response length based on the urgency and context of the question? Someone debugging a production outage needs a different response than someone learning on a weekend.''',
        r'''<think>
Context dramatically changes the appropriate response. A production outage needs the shortest possible path to a fix. A learning session benefits from depth and exploration.

**Context signals:**
1. Urgency words: "ASAP", "production is down", "blocking", "deadline"
2. Learning words: "explain", "understand", "why", "how does it work"
3. Exploration words: "best practices", "tradeoffs", "should I"
4. Frustration words: "still not working", "tried everything", "been hours"

Each context demands a different response format.
</think>

**Context-Aware Response Calibration**

**The context detection framework:**

| Context signal | Response style | Length |
|---------------|---------------|--------|
| "Production is down" | Fix first, explain later | Shortest possible |
| "I'm learning about X" | Teach with depth | Medium-long |
| "Best way to do X?" | Compare options with tradeoffs | Medium |
| "Been debugging for hours" | Targeted diagnosis + fix | Short-medium |
| "Code review feedback" | Specific, actionable items | Short per item |
| "Planning a new project" | Architecture with options | Long |

**Emergency context (production issues):**
```
User: "Our API is returning 500 errors in production, started 10 minutes ago"

WRONG (too detailed for emergency):
  "500 errors can be caused by many things. Let me explain the
   common causes: database connectivity issues occur when..."

RIGHT (action-oriented):
  "Check in this order:
   1. `tail -100 /var/log/app/error.log` — what's the error?
   2. `pg_isready` — is the database responding?
   3. `df -h` — is disk full?
   4. `free -m` — is memory exhausted?

   Share the output and I'll help diagnose further."
```

**Learning context (exploration):**
```
User: "I want to understand how database indexes work"

WRONG (too terse for learning):
  "Indexes are B-tree data structures that speed up lookups."

RIGHT (teaching with depth):
  "Think of a database index like the index in a textbook...
   [detailed explanation with analogies, examples, and visuals]"
```

**Frustration context (been struggling):**
```
User: "I've been trying to fix this CORS error for 3 hours"

WRONG (adding more concepts):
  "CORS is a security mechanism that... Let me explain the
   history of same-origin policy..."

RIGHT (empathy + targeted fix):
  "CORS errors are frustrating. Here's the fix for your
   specific setup:

   Add this to your Express server:
   app.use(cors({ origin: 'http://localhost:3000' }));

   If that doesn't work, share the exact error message from
   the browser console."
```

**The urgency multiplier:**
```
Low urgency (learning):     Detail × 1.0 (full explanations welcome)
Medium urgency (building):  Detail × 0.5 (actionable, brief explanation)
High urgency (production):  Detail × 0.1 (fix only, explain later)
Critical (data loss risk):  Detail × 0.0 (command to run, nothing else)
```

**Context detection keywords:**
```
URGENT: "production", "down", "outage", "ASAP", "breaking",
        "blocking", "deploy failed", "customers affected"

LEARNING: "explain", "understand", "why does", "how does",
          "what is", "teach me", "curious about"

FRUSTRATED: "still", "been trying", "doesn't work", "hours",
            "nothing works", "tried everything"

PLANNING: "should I", "best approach", "architecture",
          "design", "new project", "tradeoffs"
```

**The meta-principle:** Match your response energy to the user's context energy. Urgency demands brevity. Learning invites depth. Frustration needs empathy and a targeted fix. The same technical content, delivered in the wrong format for the context, becomes unhelpful regardless of its accuracy.'''
    ),
    (
        "thinking/auto-autonomous-calibrate-repetition",
        r'''How do I detect and eliminate unnecessary repetition in my answers? I sometimes restate the same point three different ways.''',
        r'''<think>
Repetition in answers comes from:
1. Restating the question in the answer (unnecessary confirmation)
2. Saying the same thing in different words (redundancy)
3. Summarizing at the end what was already explained (recap bloat)
4. Making the same point through different examples when one would suffice

**Some repetition is intentional and useful:**
- Reinforcing a key concept through different angles (teaching technique)
- Summary at the end of a very long answer (navigation aid)

**Most repetition is unintentional and wasteful:**
- Saying the same thing because you forgot you already said it
- Rephrasing to fill space
- Restating the obvious
</think>

**Detecting and Eliminating Unnecessary Repetition**

**The repetition audit:**
```
After writing, scan for:
1. Does any paragraph say the same thing as another paragraph?
2. Does the conclusion repeat the introduction?
3. Are there multiple examples making the same point?
4. Did I restate the user's question before answering?
```

**Common repetition patterns:**

**Pattern 1: Restating the question**
```
REPETITIVE:
  User: "How do I reverse a string in Python?"
  Answer: "To reverse a string in Python, you can use several
           approaches. Reversing a string is a common operation
           in Python programming. Here's how to reverse a string..."

CLEAN:
  Answer: "reversed_str = my_string[::-1]"
```

**Pattern 2: Same point, different words**
```
REPETITIVE:
  "Indexes speed up database queries. By creating an index,
   your queries will run faster. The performance improvement
   from indexing can be significant, making your database
   operations more efficient."

  (Four sentences, one idea.)

CLEAN:
  "Indexes speed up queries by letting the database jump
   directly to matching rows instead of scanning every row."

  (One sentence, same information, plus it explains HOW.)
```

**Pattern 3: Too many examples for one concept**
```
REPETITIVE:
  "For example, you could use this for sorting a list of users.
   Another example is sorting a list of products. You could also
   sort a list of transactions..."

CLEAN:
  "For example, sorting a list of users by name:
   sorted_users = sorted(users, key=lambda u: u.name)"

  (One concrete example is enough. If they understand sorting
   users, they can sort products on their own.)
```

**Pattern 4: Unnecessary recap**
```
REPETITIVE (at end of a 200-word answer):
  "In summary, we covered how to reverse a string using
   slicing, the reversed() function, and a loop."

CLEAN: Just end. For a 200-word answer, the reader remembers
       what they just read. Recaps are for 2000+ word answers.
```

**The deduplication test:**
```
For each paragraph, ask:
  "If I deleted this paragraph, would the reader miss any
   information they can't get from other paragraphs?"

  If no → delete it. It's redundant.
  If yes → keep it. It's load-bearing.
```

**When repetition IS appropriate:**
```
1. Very long answers (1000+ words) → brief recap helps
2. Critical safety/security points → worth restating
3. Teaching a concept from multiple angles → deliberate reinforcement
4. The user seems confused → rephrasing may help

In all other cases, say it once, say it clearly, move on.
```

**The meta-principle:** Every sentence should earn its place by adding information the reader doesn't already have. If a sentence restates something already said, it's not reinforcing — it's wasting the reader's time. Be concise by default, verbose only when the complexity demands it.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
