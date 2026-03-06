"""Phase 4D: Self-Improvement — Meta-Learning (Part 12)

Extracting reusable patterns from specific solutions —
how an AI assistant can generalize from individual problem-solving
instances to build transferable solution templates.
"""

PAIRS = [
    (
        "thinking/auto-metalearning-pattern-extraction",
        r'''How can I extract reusable patterns from specific solutions I help users with? When I solve a particular problem, how do I generalize it into a template I can apply to similar future problems?''',
        r'''<think>
Pattern extraction is the process of going from a specific solution to a general template. This is how expertise develops — novices solve each problem from scratch, while experts recognize patterns and apply proven templates.

The extraction process:
1. Solve the specific problem
2. Identify which parts are problem-specific vs. general
3. Abstract the general parts into a template
4. Validate the template against other instances
5. Note the boundary conditions (when does this pattern NOT apply?)
</think>

**Pattern Extraction Framework**

**Step 1: Solve and annotate**
```
After solving a specific problem, annotate each part:

SPECIFIC (tied to this instance):
  - The particular database schema
  - The specific API endpoint names
  - The programming language syntax
  - The exact error message

GENERAL (applies across instances):
  - The problem structure (e.g., "data consistency across services")
  - The solution approach (e.g., "event sourcing with idempotency")
  - The debugging process (e.g., "trace the data at each boundary")
  - The trade-off analysis (e.g., "consistency vs. availability")
```

**Step 2: Extract the template**
```
Template format:

PATTERN NAME: [Descriptive name]
PROBLEM SIGNATURE: [How to recognize this problem]
SOLUTION STRUCTURE: [Steps to solve, language-agnostic]
KEY INSIGHT: [The non-obvious realization that makes it work]
BOUNDARY CONDITIONS: [When this pattern does NOT apply]
VARIATIONS: [Common variants of this pattern]

Example extraction:

Problem: User's API returns stale data after writes
Specific solution: Added cache invalidation after database update

Extracted pattern:
  NAME: Write-Through Cache Invalidation
  SIGNATURE: Data appears stale after successful write operation
  STRUCTURE:
    1. Identify all cache layers between write and read
    2. Invalidate or update cache at write time
    3. Use cache-aside pattern for complex cases
    4. Add TTL as safety net for missed invalidations
  KEY INSIGHT: Cache invalidation must happen in the same
    transaction or event as the write, not as an afterthought
  BOUNDARY: Doesn't work for distributed caches with
    eventual consistency — use event-driven invalidation instead
  VARIATIONS: Write-through, write-behind, cache-aside
```

**Step 3: Validate across instances**
```
Test the extracted pattern against other problems:

Does it apply to:
□ Same problem in a different language? (likely yes)
□ Same problem at a different scale? (check boundaries)
□ Similar but not identical problem? (may need adaptation)
□ Problem in a different domain? (may not apply)

If the pattern fails validation:
- Narrow its scope (it applies to X but not Y)
- Add conditions (it works when A is true)
- Split into sub-patterns (the general version is too broad)
```

**Step 4: Build a pattern library**
```
Organize extracted patterns by problem category:

DATA PATTERNS:
  - Stale data → Cache invalidation strategies
  - Data inconsistency → Transaction boundaries
  - Data loss → Write-ahead logging, event sourcing

PERFORMANCE PATTERNS:
  - Slow queries → Index optimization, query restructuring
  - High latency → Caching, connection pooling, batching
  - Memory growth → Leak detection, pagination, streaming

ARCHITECTURE PATTERNS:
  - Tight coupling → Interface extraction, event-driven
  - Scaling bottleneck → Horizontal scaling, sharding
  - Deployment risk → Blue-green, canary, feature flags

ERROR HANDLING PATTERNS:
  - Silent failures → Explicit error propagation
  - Cascading failures → Circuit breakers, bulkheads
  - Retry storms → Exponential backoff, jitter
```

**The meta-principle:** Every specific solution contains a general pattern waiting to be extracted. The discipline of extraction — solving, annotating, abstracting, validating — is what converts individual problem-solving experiences into reusable expertise. Build the habit of asking "what general pattern did I just apply?" after every solution.'''
    ),
    (
        "thinking/auto-metalearning-solution-decomposition",
        r'''How do I decompose complex solutions into their constituent patterns so I can reuse each component independently? What is the best way to break a solution into reusable parts?''',
        r'''<think>
Complex solutions are usually compositions of simpler patterns. Decomposition is the skill of identifying these constituent patterns so each can be reused independently. This is analogous to how functions decompose complex operations into reusable units.

The challenge is finding the right decomposition boundaries — too fine-grained and the patterns are trivial, too coarse and they are not reusable.
</think>

**Solution Decomposition for Pattern Reuse**

**Decomposition method: Layer analysis**
```
Most solutions operate across multiple layers.
Decompose by identifying what each layer contributes:

EXAMPLE: "Building a rate limiter for an API"

Layer 1 — Algorithm pattern:
  Token bucket, sliding window, fixed window
  → Reusable in: Any rate limiting scenario

Layer 2 — Storage pattern:
  In-memory counter, Redis atomic operations, database
  → Reusable in: Any distributed counting scenario

Layer 3 — Integration pattern:
  Middleware, decorator, proxy
  → Reusable in: Any cross-cutting concern (auth, logging)

Layer 4 — Configuration pattern:
  Per-route limits, per-user limits, dynamic adjustment
  → Reusable in: Any configurable policy scenario

Each layer is an independently reusable pattern.
The specific rate limiter is a composition of all four.
```

**Decomposition method: Decision analysis**
```
Every solution involves decisions. Extract each decision
as an independent pattern:

EXAMPLE: "Designing a notification system"

Decision 1: Sync vs. async delivery
  Pattern: When to use message queues vs. direct calls
  Reusable in: Any operation that can be deferred

Decision 2: Fan-out strategy
  Pattern: How to deliver one event to many recipients
  Reusable in: Event systems, pub/sub, broadcasting

Decision 3: Delivery guarantee
  Pattern: At-most-once vs. at-least-once vs. exactly-once
  Reusable in: Any distributed messaging scenario

Decision 4: User preferences
  Pattern: Per-user configuration with sensible defaults
  Reusable in: Any user-facing feature with settings

Each decision point is a reusable pattern that appears
in many different system designs.
```

**Decomposition method: Failure mode analysis**
```
Decompose by what can go wrong:

EXAMPLE: "File upload handling"

Failure mode 1: Large file handling
  Pattern: Streaming upload, chunked processing
  Reusable in: Any large data ingestion

Failure mode 2: Invalid content
  Pattern: Validation before processing
  Reusable in: Any user input handling

Failure mode 3: Partial failure
  Pattern: Resumable operations, cleanup on failure
  Reusable in: Any multi-step operation

Failure mode 4: Storage exhaustion
  Pattern: Quota management, back-pressure
  Reusable in: Any resource-constrained system

Each failure mode and its solution is independently reusable.
```

**Composition rules**
```
When applying decomposed patterns together:

1. IDENTIFY DEPENDENCIES:
   Which patterns depend on which?
   Rate limit algorithm depends on storage choice.
   Storage choice is independent of integration method.

2. DEFINE INTERFACES:
   Each pattern component should have clear inputs/outputs.
   Algorithm: (request, config) → (allowed: bool, retry_after: int)
   Storage: (key, operation) → (count: int)

3. COMPOSE INCREMENTALLY:
   Start with the simplest version of each pattern.
   Add complexity only when needed.
   A simple in-memory rate limiter is better than
   no rate limiter while you build the distributed version.

4. TEST INDEPENDENTLY:
   Each decomposed pattern should be testable in isolation.
   If you can't test a pattern alone, the decomposition
   boundary is wrong.
```

**The meta-principle:** A complex solution is a composition of simple patterns. By decomposing solutions into their constituent patterns, you build a library of building blocks that can be recombined to solve new problems. The art is finding decomposition boundaries where each component is useful on its own and composable with others.'''
    ),
    (
        "thinking/auto-metalearning-analogy-construction",
        r'''How should I construct useful analogies when explaining technical concepts? When are analogies helpful and when do they mislead?''',
        r'''<think>
Analogies are powerful learning tools but dangerous when overextended. A good analogy illuminates the core mechanism of a concept; a bad analogy creates false mental models that lead to incorrect reasoning.

The key metacognitive skill is knowing:
1. What structural similarity makes the analogy work
2. Where the analogy breaks down
3. When to abandon the analogy and teach the raw concept

The best analogies map STRUCTURE, not surface features.
</think>

**Analogy Construction Framework**

**What makes a good technical analogy**
```
A good analogy maps the CAUSAL STRUCTURE of the concept,
not just surface resemblance.

GOOD ANALOGY (structural mapping):
  "A database index is like a book index. Both create a
   separate data structure that maps search terms to locations.
   Both speed up lookup at the cost of space and write overhead."

  Why it works: The MECHANISM is the same (sorted lookup
  structure trading space for speed). Reasoning about the
  analogy produces correct conclusions about the concept.

BAD ANALOGY (surface mapping):
  "The internet is like a series of tubes."

  Why it fails: Tubes suggest a fixed-capacity physical
  connection, which leads to wrong conclusions about how
  packets are routed and how congestion works.
```

**Analogy construction steps**
```
Step 1: Identify the core mechanism
  What is the fundamental principle at work?
  - For caching: "keeping a copy of expensive-to-fetch
    data close to where it's used"
  - For event-driven architecture: "decoupling producers
    from consumers through an intermediary"

Step 2: Find a familiar domain with the same mechanism
  - Caching → keeping frequently used tools on your desk
    instead of walking to the supply room each time
  - Event-driven → a bulletin board where anyone can post
    and anyone can read, without knowing each other

Step 3: Map the components
  Cache entry → tool on desk
  Cache miss → tool not on desk, must go to supply room
  Cache eviction → desk is full, must remove something
  TTL → tool gets returned after a set time

Step 4: Identify where the analogy breaks
  - Desk analogy doesn't capture cache coherency
  - Desk analogy doesn't capture distributed caching
  - Desk analogy doesn't capture write-through vs write-back

Step 5: Explicitly communicate the boundary
  "This analogy works for understanding basic caching,
   but breaks down when you consider cache invalidation
   in distributed systems. For that, think of it more as..."
```

**When analogies mislead**
```
DANGER SIGNS:

1. The analogy suggests wrong behavior:
   "Threads are like workers in a factory"
   → Suggests threads are independent; misses shared memory
     and race conditions entirely

   Better: "Threads are like cooks sharing one kitchen.
   They can work simultaneously but must coordinate access
   to shared equipment or they'll collide."

2. The analogy is too comforting:
   "Kubernetes is like a thermostat for your servers"
   → Suggests it's simple and automatic; hides massive
     complexity in configuration and debugging

3. The analogy maps the wrong dimension:
   "NoSQL is like a filing cabinet vs. SQL's spreadsheet"
   → Focuses on data shape, misses consistency/availability
     trade-offs which are the actual important difference

4. The analogy prevents deeper understanding:
   If someone keeps reasoning from the analogy instead
   of the actual concept, the analogy has become a crutch
```

**Analogy quality checklist**
```
Before using an analogy, verify:

□ STRUCTURAL MATCH: Does it map the causal mechanism?
□ CORRECT PREDICTIONS: Does reasoning from the analogy
  produce correct conclusions about the real concept?
□ CLEAR BOUNDARIES: Have I stated where it breaks down?
□ APPROPRIATE AUDIENCE: Does the audience know the
  source domain? (Don't use a plumbing analogy with
  someone who doesn't understand plumbing)
□ NOT A CRUTCH: Does the analogy lead toward understanding
  the real concept, not replace it?
```

**Graduated analogy strategy**
```
For complex concepts, use a series of analogies:

Level 1 — Simple analogy for intuition:
  "A load balancer is like a restaurant host seating
   guests at different tables"

Level 2 — Refined analogy for accuracy:
  "But unlike a host, the load balancer can use different
   strategies: round-robin (next available), least-connections
   (least busy), or weighted (some servers handle more)"

Level 3 — Drop the analogy for precision:
  "Specifically, the load balancer maintains a pool of
   backend servers, health-checks each one, and distributes
   incoming TCP connections based on a configured algorithm"

Each level gets closer to the real concept.
The analogy scaffolds understanding, then gets out of the way.
```

**The meta-principle:** Analogies are scaffolding, not foundations. They help build initial understanding but should be explicitly dismantled once the real concept is grasped. Always state where the analogy breaks, and always be prepared to teach the raw concept when the analogy reaches its limits.'''
    ),
    (
        "thinking/auto-metalearning-mistake-analysis",
        r'''How should I analyze my own mistakes to improve future responses? What systematic approach helps me learn from errors in my technical advice?''',
        r'''<think>
Mistake analysis is the most direct path to improvement. Every error contains information about a gap in knowledge, a flawed reasoning process, or a miscalibrated confidence level. The key is having a systematic process for extracting that information rather than just moving on.

Categories of mistakes:
1. Knowledge errors: Wrong facts
2. Reasoning errors: Right facts, wrong conclusions
3. Calibration errors: Right answer with wrong confidence level
4. Scope errors: Correct but not what the user needed
5. Communication errors: Right answer, poorly explained
</think>

**Mistake Analysis Framework**

**Step 1: Classify the mistake**
```
KNOWLEDGE ERROR:
  "I said Python's GIL prevents all parallelism"
  Reality: GIL prevents parallel threads for CPU-bound work,
  but multiprocessing, async I/O, and C extensions bypass it.
  Root cause: Overgeneralized a partial understanding.
  Fix: Learn the specific boundaries of the GIL's effect.

REASONING ERROR:
  "I recommended microservices for a 2-person team"
  The facts were right (microservices have benefits) but the
  conclusion was wrong for the context (small team, early stage).
  Root cause: Failed to weight team size in the trade-off analysis.
  Fix: Always include team/org context in architecture decisions.

CALIBRATION ERROR:
  "I confidently provided a specific API method name that
   was renamed in a recent version"
  Root cause: High confidence on version-sensitive information.
  Fix: Flag version-sensitive details with uncertainty.

SCOPE ERROR:
  "User asked how to fix a slow query; I explained indexing
   theory instead of analyzing their specific query"
  Root cause: Defaulted to general education instead of
  specific problem-solving.
  Fix: Address the specific question first, generalize second.

COMMUNICATION ERROR:
  "My explanation of monads was technically correct but
   incomprehensible to the beginner who asked"
  Root cause: Didn't calibrate to the user's knowledge level.
  Fix: Assess the user's level before choosing explanation depth.
```

**Step 2: Root cause analysis (5 Whys)**
```
Apply the 5 Whys to understand the root cause:

Mistake: Recommended a deprecated library
Why? I didn't check if the library was still maintained.
Why? I relied on training data instead of considering recency.
Why? I didn't have a habit of flagging version-sensitive advice.
Why? I lacked a systematic checklist for library recommendations.
Root cause: Missing quality check for recommendations.

Action: Add "Is this library still actively maintained?"
to the library recommendation checklist.
```

**Step 3: Pattern recognition across mistakes**
```
Track mistakes to find patterns:

If multiple mistakes involve:
- Version-specific APIs → Need systematic version caveats
- Architecture for wrong team size → Need team context checklist
- Overly complex solutions → Need simplicity bias
- Missing edge cases → Need edge case enumeration habit
- Wrong language idioms → Need language-specific review

Patterns reveal SYSTEMATIC issues, not one-off errors.
Fixing the pattern prevents entire classes of mistakes.
```

**Step 4: Counterfactual analysis**
```
Ask: "What would have prevented this mistake?"

Possible preventions:
1. A CHECKLIST: Would a quality checklist have caught this?
   → Add the check to the relevant checklist.

2. A QUESTION: Would asking the user a clarifying question
   have prevented the wrong assumption?
   → Add the question to the intake process.

3. A CAVEAT: Would flagging uncertainty have helped?
   → Lower confidence threshold for this topic.

4. A DIFFERENT APPROACH: Would a different solution strategy
   have avoided the error entirely?
   → Update the default approach for this problem type.

5. MORE CONTEXT: Would knowing more about the situation
   have changed the advice?
   → Ask for this context proactively next time.
```

**Step 5: Integrate the learning**
```
Convert mistake analysis into actionable changes:

BEFORE (old behavior):
  User asks about caching → Recommend Redis
  (No context gathering, default recommendation)

AFTER (improved behavior):
  User asks about caching → Ask about scale, infrastructure,
  existing tech stack → Recommend appropriate solution
  (In-memory for single server, Redis for distributed,
   CDN for static assets)

Document the change:
  TRIGGER: Caching question
  OLD: Default to Redis
  NEW: Context-dependent recommendation
  REASON: Mistake where Redis was recommended for a
  single-server app that only needed functools.lru_cache
```

**The meta-principle:** Mistakes are the highest-signal learning opportunities. A systematic approach to mistake analysis — classify, root-cause, find patterns, prevent — converts individual errors into systematic improvements. The goal is not to avoid all mistakes (impossible) but to never make the same category of mistake twice.'''
    ),
    (
        "thinking/auto-metalearning-skill-assessment",
        r'''How can I accurately assess my own skill level across different technical domains? What frameworks help me understand where I am strong versus where I need improvement?''',
        r'''<think>
Self-assessment is difficult because of inherent biases — we tend to overestimate competence in areas where we know just enough to be dangerous, and underestimate in areas where we know enough to see how much more there is to learn. A structured assessment framework helps counteract these biases.

The approach should be:
1. Define clear competency levels with observable criteria
2. Assess against specific, measurable indicators
3. Validate assessments against actual performance
4. Regularly reassess as knowledge evolves
</think>

**Technical Skill Self-Assessment Framework**

**Competency matrix**
```
For each technical domain, assess across these dimensions:

DIMENSION 1 — Breadth: How many sub-topics can you cover?
  1: Know one aspect (e.g., basic SQL queries)
  2: Know several aspects (queries, joins, indexes)
  3: Cover most areas (optimization, transactions, replication)
  4: Comprehensive coverage including edge cases

DIMENSION 2 — Depth: How deeply do you understand each topic?
  1: Can describe what it is
  2: Can explain how it works
  3: Can explain WHY it works that way and trade-offs
  4: Can debug complex problems and advise on edge cases

DIMENSION 3 — Currency: How up-to-date is your knowledge?
  1: Knowledge may be several versions behind
  2: Know the general current state
  3: Aware of recent changes and their implications
  4: Current with latest releases and emerging patterns

DIMENSION 4 — Practical: Can you produce working solutions?
  1: Can describe the approach conceptually
  2: Can write pseudocode or partial solutions
  3: Can write working code with minor issues
  4: Can write production-quality solutions with error handling
```

**Domain assessment template**
```
Domain: [e.g., PostgreSQL]

Breadth:  [1-4] — Evidence: [what topics you can cover]
Depth:    [1-4] — Evidence: [example of deep knowledge]
Currency: [1-4] — Evidence: [latest version features known]
Practical:[1-4] — Evidence: [quality of solutions provided]

Overall:  [Average or minimum of dimensions]
Confidence in assessment: [High/Medium/Low]

Gaps identified:
  - [Specific topic or skill gap]
  - [Area where mistakes have occurred]

Improvement plan:
  - [Specific action to address gaps]
```

**Validation methods**
```
How to verify your self-assessment is accurate:

METHOD 1 — Error tracking
  Track incorrect advice by domain.
  High error rate in a domain → lower your assessment.
  Low error rate → assessment may be accurate.

METHOD 2 — Question difficulty handling
  Can you handle:
  - Beginner questions? (Level 1-2 competency needed)
  - Intermediate questions? (Level 2-3 needed)
  - Advanced questions? (Level 3-4 needed)
  - Expert/edge-case questions? (Level 4 needed)

  If you struggle with intermediate questions,
  your assessment should not be above Level 2.

METHOD 3 — Explanation depth
  Can you explain:
  - What to do? (Level 1)
  - How to do it? (Level 2)
  - Why this approach over alternatives? (Level 3)
  - When this approach fails and what to do instead? (Level 4)

METHOD 4 — Cross-validation
  Compare your assessment against:
  - User feedback (corrections, follow-up questions)
  - Official documentation (do your answers match?)
  - Expert consensus (does your advice align with best practices?)
```

**Assessment hygiene**
```
COMMON BIASES TO COUNTERACT:

Overconfidence bias:
  "I've answered many Python questions successfully"
  But: Were they all beginner-level? Advanced Python
  (metaclasses, descriptors, async internals) may be weak.

Familiarity bias:
  "I know React well because I see it often"
  But: Frequency of exposure does not equal depth.
  You may know common patterns but miss edge cases.

Recency bias:
  "I just helped with Kubernetes, so I'm good at it"
  But: One successful interaction does not validate
  comprehensive knowledge.

Anchoring bias:
  "I was strong in this area 6 months ago"
  But: Technology changes. Your assessment may be stale.

COUNTERACTION:
  Reassess quarterly. Use error tracking as ground truth.
  Weight recent performance more than historical assessment.
  Always verify against the hardest questions, not the easiest.
```

**The meta-principle:** Accurate self-assessment is the foundation of reliable assistance. Overestimating leads to confidently wrong advice. Underestimating leads to unnecessary hedging on topics you actually know well. The goal is calibration — your confidence should match your actual competence. Track errors, validate regularly, and adjust continuously.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
