"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 14)

Autonomously detecting over-engineering in suggestions —
how to recognize when advice adds unnecessary complexity
and self-correct toward simpler, more appropriate solutions.
"""

PAIRS = [
    (
        "thinking/auto-autonomous-overeng-detection",
        r'''How can I detect when my technical suggestions are over-engineered? What signals indicate I am recommending unnecessarily complex solutions?''',
        r'''<think>
Over-engineering is one of the most common failure modes in technical advice. It happens when the solution's complexity exceeds what the problem requires. AI assistants are particularly prone to this because:

1. We tend to suggest "best practice" solutions designed for large-scale systems
2. We default to patterns we've seen in large codebases
3. We optimize for flexibility and extensibility even when not needed
4. We confuse "comprehensive" with "appropriate"

Detection requires consciously comparing solution complexity against problem complexity.
</think>

**Over-Engineering Detection Framework**

**Signal 1: Solution complexity exceeds problem complexity**
```
Complexity mismatch indicators:

PROBLEM: "I need to store user preferences"
OVER-ENGINEERED: "Use a separate preferences microservice
  with its own database, event-driven sync, and a caching
  layer with Redis for fast reads."
APPROPRIATE: "Add a JSON column to the users table. Use a
  simple key-value structure. Query it with your existing ORM."

Detection rule: If the solution requires more infrastructure
than the problem requires, it is over-engineered.

SCALE CHECK:
  □ How many users? (10? 1,000? 1,000,000?)
  □ How many developers? (1? 5? 50?)
  □ How often does this change? (daily? monthly? yearly?)
  □ What are the actual performance requirements?

If you do not know the scale, you cannot judge the
appropriate complexity level. Ask before suggesting.
```

**Signal 2: Premature abstraction**
```
OVER-ENGINEERED: Creating abstractions before they are needed.

Examples:
  □ Interface with one implementation
    → Just use the concrete class
  □ Factory pattern for one type of object
    → Just use a constructor
  □ Event system with one publisher and one subscriber
    → Just call the function directly
  □ Plugin architecture when there are no plugins
    → YAGNI — add it when someone actually needs plugins

Detection rule: If an abstraction has fewer than 2 concrete
uses TODAY (not "someday"), it is premature.

Exception: Well-known extension points (authentication,
storage backends) where the abstraction cost is low and
the benefit is well-established.
```

**Signal 3: Technology proliferation**
```
OVER-ENGINEERED: Introducing new technologies for simple tasks.

Examples:
  □ Adding Redis for caching when in-memory dict works
    (for a single-server application)
  □ Adding Kafka for message passing between two functions
    (a simple function call would work)
  □ Adding GraphQL for an API with 3 endpoints and 1 client
    (REST is simpler and sufficient)
  □ Adding Kubernetes for deploying one application
    (a simple VPS with systemd works)

Detection rule: Each new technology in the stack adds:
  - Learning curve for the team
  - Operational complexity (monitoring, upgrades, failures)
  - Infrastructure cost
  - Debugging surface area

The benefit must clearly outweigh these costs.
```

**Signal 4: Future-proofing that may never be needed**
```
OVER-ENGINEERED: Building for hypothetical future requirements.

"What if we need to support multiple databases?"
  → Are you planning to? If no, don't abstract it.

"What if traffic increases 100x?"
  → Is that likely in the next year? If no, optimize then.

"What if we need to add a mobile app?"
  → Are you building one? If no, don't pre-optimize the API.

Detection rule: If the justification starts with "what if"
and the scenario is not on the current roadmap, the
complexity is premature.

EXCEPTION: Security and data integrity. These should be
designed correctly from the start because retrofitting
is much harder than building right.
```

**Self-correction process**
```
When you detect over-engineering in your advice:

1. STRIP: Remove the unnecessary complexity
2. SIMPLIFY: Use the simplest approach that works
3. DOCUMENT: Note what to add WHEN complexity is needed
4. STAGE: Provide a migration path from simple to complex

Example self-correction:

BEFORE (over-engineered):
  "Implement a CQRS pattern with separate read and write
   models, use event sourcing for the write side..."

AFTER (right-sized):
  "Use a single database with your existing ORM. When you
   hit performance issues with reads, add read replicas.
   If you eventually need different read/write models,
   you can introduce CQRS at that point."
```

**The meta-principle:** The best solution is the simplest one that solves the actual problem at the actual scale. Every layer of abstraction, every additional technology, and every design pattern has a cost. Over-engineering is not a sign of skill — it is a sign of not understanding the problem's true constraints. Start simple, measure, and add complexity only when evidence demands it.'''
    ),
    (
        "thinking/auto-autonomous-overeng-patterns",
        r'''What are the most common over-engineering patterns in software architecture advice, and how can I catch myself recommending them inappropriately?''',
        r'''<think>
There are specific patterns that are frequently recommended in contexts where they add more complexity than value. These are legitimate patterns for the right problems, but they become over-engineering when applied to the wrong scale or context. The key is knowing the threshold where each pattern becomes appropriate.
</think>

**Common Over-Engineering Patterns and Their Thresholds**

**Pattern 1: Microservices when a monolith suffices**
```
OVER-ENGINEERING THRESHOLD:
  Microservices are appropriate when:
  - Team size > 20 developers
  - Independent deployment of components is required
  - Different components have different scaling needs
  - Different components use different tech stacks

  Microservices are over-engineering when:
  - Team size < 10
  - The application is a single product
  - All components scale together
  - One tech stack serves all needs

SELF-CHECK:
  "Am I recommending microservices because the problem
   requires them, or because they sound modern?"

SIMPLER ALTERNATIVE:
  Modular monolith with clear internal boundaries.
  Extract to microservices when the monolith causes problems.
```

**Pattern 2: Event-driven architecture for simple workflows**
```
OVER-ENGINEERING THRESHOLD:
  Events are appropriate when:
  - Multiple independent consumers need the same data
  - Components need temporal decoupling (async processing)
  - Audit trail or replay is a requirement
  - Systems span organizational boundaries

  Events are over-engineering when:
  - One producer, one consumer
  - Processing must be synchronous anyway
  - The workflow is a simple request-response
  - Adding a message broker doubles infrastructure complexity

SELF-CHECK:
  "Would a direct function call or HTTP request work here?"

SIMPLER ALTERNATIVE:
  Direct function calls within a process.
  Synchronous HTTP between services.
  Background job queue for async work.
```

**Pattern 3: Abstract factory / strategy pattern for one variant**
```
OVER-ENGINEERING THRESHOLD:
  Abstraction is appropriate when:
  - 3+ implementations exist today
  - New implementations are added regularly
  - The abstraction boundary is well-understood
  - Testing requires swapping implementations

  Abstraction is over-engineering when:
  - Only 1 implementation exists
  - No concrete plan for additional implementations
  - The abstraction adds indirection without flexibility
  - "We might need this someday"

SELF-CHECK:
  "How many implementations exist RIGHT NOW?"
  If 1 → no abstraction needed.
  If 2 → maybe extract an interface.
  If 3+ → abstraction is justified.

SIMPLER ALTERNATIVE:
  Use the concrete implementation directly.
  Extract an interface when the second implementation appears.
  The refactoring cost is low; the over-engineering cost is ongoing.
```

**Pattern 4: Distributed caching for small datasets**
```
OVER-ENGINEERING THRESHOLD:
  Distributed cache (Redis) is appropriate when:
  - Multiple application instances need shared cache
  - Cache data exceeds available memory per instance
  - Cache persistence across deployments is needed
  - Cache invalidation must be coordinated

  Distributed cache is over-engineering when:
  - Single application instance
  - Dataset fits in memory (< 1 GB)
  - Cache can be rebuilt quickly on restart
  - No coordination between instances needed

SELF-CHECK:
  "Does this need to be shared across processes?"

SIMPLER ALTERNATIVE:
  In-memory cache (dict, LRU cache).
  Process-local cache with TTL.
  Add Redis when you add the second application instance.
```

**Pattern 5: Custom DSL or configuration language**
```
OVER-ENGINEERING THRESHOLD:
  Custom DSL is appropriate when:
  - Non-developers need to express complex logic
  - The domain has well-defined, stable semantics
  - The DSL replaces hundreds of similar code files
  - Tooling investment is justified by scale

  Custom DSL is over-engineering when:
  - Only developers will use it
  - The domain is still being discovered
  - Standard config formats (YAML, JSON) suffice
  - Fewer than 50 configurations exist

SELF-CHECK:
  "Could this be expressed in a standard config file?"

SIMPLER ALTERNATIVE:
  YAML/JSON configuration files.
  Python/JavaScript for complex configuration (code as config).
  Only build a DSL when config complexity justifies it.
```

**Universal over-engineering detection**
```
Ask these questions for ANY architectural recommendation:

1. What is the SIMPLEST solution that works?
2. What SPECIFIC problem does the added complexity solve?
3. Does that problem exist TODAY or is it hypothetical?
4. What is the COST of the complexity (learning, ops, debugging)?
5. What is the cost of ADDING this complexity later when needed?

If the cost of adding later is low, start simple.
If the cost of adding later is high (security, data model),
build it right from the start.
```

**The meta-principle:** Every design pattern and architectural style exists to solve a specific category of problems at a specific scale. Applying them outside their intended context is over-engineering. The skill is not knowing many patterns — it is knowing when each pattern's benefits outweigh its costs for the specific situation at hand.'''
    ),
    (
        "thinking/auto-autonomous-overeng-simplification",
        r'''When I detect that my suggestion is over-engineered, what systematic process should I follow to simplify it while still solving the user's actual problem?''',
        r'''<think>
Simplification is not just removing things — it's finding the essential solution buried under unnecessary complexity. The process requires understanding what the user actually needs versus what the "ideal" architecture would look like.

The key steps:
1. Identify the core requirement (what MUST work)
2. Strip everything that doesn't serve the core requirement
3. Use the simplest tool for each remaining requirement
4. Verify the simplified solution still solves the problem
</think>

**Systematic Simplification Process**

**Step 1: Extract the core requirement**
```
Ask: "What is the ONE thing this solution must accomplish?"

User says: "I need a real-time notification system"

Core requirement analysis:
  - Must users see updates immediately? Or within seconds?
  - How many users? (10 concurrent? 10,000?)
  - What types of notifications? (text only? rich media?)
  - What happens if a notification is delayed by 30 seconds?

Often the "real-time" requirement is actually "fast enough":
  - "Real-time" at 10 users → WebSocket is fine
  - "Real-time" at 100 users → Server-Sent Events is fine
  - "Fast enough" at any scale → polling every 5 seconds might work

The core requirement is often simpler than the user's framing.
```

**Step 2: Apply the simplicity ladder**
```
For each component, try the simplest option first:

STORAGE:
  1. In-memory (dict, list) — if data doesn't need persistence
  2. File (JSON, SQLite) — if data needs persistence, single user
  3. PostgreSQL — if data needs persistence, multiple users
  4. Distributed database — if single database is a bottleneck
  Stop at the first level that works.

COMMUNICATION:
  1. Function call — if components are in the same process
  2. HTTP request — if components are in different processes
  3. Message queue — if async processing is genuinely needed
  4. Event streaming — if event replay or multi-consumer is needed
  Stop at the first level that works.

DEPLOYMENT:
  1. Single process on a VPS — if it handles the load
  2. Multiple processes behind a load balancer — if one isn't enough
  3. Container orchestration — if you need automated scaling
  4. Serverless — if the workload is genuinely event-driven and bursty
  Stop at the first level that works.

ARCHITECTURE:
  1. Single module — if the codebase is small
  2. Modular monolith — if the codebase is medium
  3. Service-oriented — if team boundaries require separation
  4. Microservices — if independent deployment is essential
  Stop at the first level that works.
```

**Step 3: Remove speculative components**
```
For each component in the solution, ask:
"Is this needed to solve the problem TODAY?"

Component: Redis cache
  Needed today? The application has 50 users.
  Remove? Yes. Use in-memory caching.
  Add back when? When you add a second server instance.

Component: Message queue
  Needed today? There's one background task.
  Remove? Yes. Use a simple background thread or cron job.
  Add back when? When you need reliable delivery or multiple consumers.

Component: API gateway
  Needed today? There's one backend service.
  Remove? Yes. The web server handles routing directly.
  Add back when? When you have multiple backend services.

Document the "add back when" conditions so the user knows
the trigger for adding complexity.
```

**Step 4: Verify the simplified solution**
```
After simplification, verify:

□ FUNCTIONAL: Does it still solve the core problem?
  Run through the main use cases mentally.

□ ADEQUATE PERFORMANCE: Does it handle the actual load?
  Not theoretical load, ACTUAL current load.

□ MAINTAINABLE: Can the team understand and modify it?
  Simpler solutions are almost always more maintainable.

□ EXTENSIBLE ENOUGH: Can it grow when needed?
  Not "infinitely flexible" — just "not a dead end."
  The simplified solution should have a clear upgrade path.

□ SAFE: Does simplification compromise security or data integrity?
  These are the two areas where simplification can be dangerous.
  Never simplify away security measures or data durability.
```

**Step 5: Present the migration path**
```
Show the user the progression from simple to complex:

TODAY (your actual needs):
  Single server, SQLite, in-memory cache, cron jobs
  Handles: 100 users, 1 developer, simple operations

GROWTH TRIGGER 1 (second server needed):
  Add PostgreSQL (shared database), add Redis (shared cache)
  Handles: 1,000 users, 3 developers

GROWTH TRIGGER 2 (team boundaries form):
  Extract services along team boundaries
  Add message queue for async operations
  Handles: 10,000 users, 10 developers

GROWTH TRIGGER 3 (independent scaling needed):
  Full service-oriented architecture
  Handles: 100,000+ users, 20+ developers

This gives users confidence that starting simple
doesn't mean being stuck simple forever.
```

**The meta-principle:** Simplification is not about building less — it is about building the right amount. The right amount is determined by the actual current requirements, not hypothetical future needs. A solution that perfectly matches today's needs and has a clear upgrade path is better than one that's built for tomorrow's scale but creates today's complexity.'''
    ),
    (
        "thinking/auto-autonomous-overeng-team-context",
        r'''How should I factor team size, experience, and context into my architectural recommendations to avoid suggesting solutions that are too complex for the team?''',
        r'''<think>
Team context is the most commonly overlooked factor in architectural decisions. A pattern that works beautifully for a 50-person team at Google can be disastrous for a 3-person startup. The architecture must fit the team, not just the technical requirements.

Key team factors:
1. Size: How many developers?
2. Experience: Senior vs. junior distribution
3. Operational capacity: Can they run what they build?
4. Cognitive budget: How much complexity can they absorb?
</think>

**Team-Context-Aware Architecture Assessment**

**Factor 1: Team size**
```
SOLO DEVELOPER (1):
  Maximum architecture: Modular monolith
  Maximum infrastructure: One server, one database
  Maximum dependencies: Standard library + 5-10 well-known libraries
  Rationale: One person cannot operate microservices,
  debug distributed systems, or maintain multiple databases.

  Recommended: "Keep everything in one deployable unit.
  Use modules for separation, not services."

SMALL TEAM (2-5):
  Maximum architecture: Monolith with clearly separated modules
  Maximum infrastructure: 2-3 servers, managed database
  Maximum dependencies: Well-maintained, documented libraries
  Rationale: Small teams need simple operations. Every
  additional service is something someone has to debug at 3 AM.

  Recommended: "Use a managed database, simple deployment
  pipeline, and keep the service count under 3."

MEDIUM TEAM (6-20):
  Maximum architecture: Service-oriented (2-5 services)
  Maximum infrastructure: Container orchestration is viable
  Maximum dependencies: Team can evaluate and maintain them
  Rationale: Enough people to specialize, but still need
  to be deliberate about complexity.

  Recommended: "Split along clear team boundaries. Each team
  owns 1-2 services. Use shared infrastructure (database, cache)
  unless there is a specific reason to separate."

LARGE TEAM (20+):
  Architecture: Microservices become viable and often necessary
  Infrastructure: Dedicated DevOps/SRE capacity
  Dependencies: Per-team decisions with governance
  Rationale: The organizational complexity requires
  architectural separation.

  Recommended: "Align services with team boundaries.
  Invest in platform tooling and developer experience."
```

**Factor 2: Experience distribution**
```
MOSTLY JUNIOR TEAM:
  Prefer: Well-known frameworks with large communities
  Avoid: Cutting-edge tools, custom frameworks, complex patterns
  Reason: Juniors need to find answers on Stack Overflow

  BAD recommendation: "Use Effect-TS for type-safe error handling"
  GOOD recommendation: "Use try/catch with custom error classes"

MIXED EXPERIENCE:
  Prefer: Standard patterns with clear documentation
  Avoid: Clever abstractions that only seniors understand
  Reason: The architecture must be readable by everyone

  BAD recommendation: "Implement the visitor pattern for processing"
  GOOD recommendation: "Use a switch statement with clear cases.
  Document each case. Refactor to a pattern if it grows beyond 10 cases."

MOSTLY SENIOR TEAM:
  Prefer: Best-fit tools and patterns for the problem
  Avoid: Unnecessary simplification that creates scaling problems
  Reason: Seniors can handle complexity and appreciate precision

  Appropriate recommendation: "Consider event sourcing for the
  audit trail requirement — it naturally provides the temporal
  queries you need."
```

**Factor 3: Operational capacity**
```
NO DEDICATED OPS (most startups):
  Recommend: Managed services (RDS, Cloud SQL, managed Redis)
  Avoid: Self-hosted databases, Kubernetes, custom monitoring
  Reason: Nobody will maintain the infrastructure

  "Use a managed PostgreSQL instance. The extra cost is
   cheaper than the engineering time to maintain a database."

PART-TIME OPS (one person, some of the time):
  Recommend: Simple container deployment, managed databases
  Avoid: Complex service mesh, custom orchestration
  Reason: Ops person needs to handle everything

DEDICATED OPS/SRE TEAM:
  Recommend: Whatever fits the technical requirements
  More options are available when someone owns operations

SELF-CHECK:
  "Who will be paged when this breaks at 3 AM?
   Can that person debug the architecture I'm recommending?"
```

**Factor 4: Cognitive budget**
```
Every team has a limited cognitive budget:

COGNITIVE COSTS:
  Each new technology: ~10% of cognitive budget
  Each new pattern: ~5% of cognitive budget
  Each operational dependency: ~5% of cognitive budget
  Each integration boundary: ~10% of cognitive budget

BUDGET ESTIMATE:
  5-technology stack: 50% used on technology alone
  + 3 design patterns: 65% used
  + 2 operational dependencies: 75% used
  Remaining: 25% for actual business logic

If the architecture consumes most of the cognitive budget,
the team will write poor business logic — the part that
actually matters to users.

SELF-CHECK:
  "How many new things does my recommendation require
   the team to learn? Is the learning justified by the
   problem being solved?"
```

**The meta-principle:** Architecture should serve the team, not the other way around. The best architecture for a problem is the one that the team can build, understand, operate, and evolve. Recommending a theoretically optimal architecture that exceeds the team's capacity is worse than recommending a simpler architecture that the team can execute well. Always ask about team context before recommending architecture.'''
    ),
    (
        "thinking/auto-autonomous-overeng-language",
        r'''How can I detect over-engineering in my language and communication style when giving technical advice? When am I making things sound more complex than they are?''',
        r'''<think>
Over-engineering in communication is just as damaging as over-engineering in architecture. Complex language makes simple concepts seem hard, intimidates beginners, and obscures the actual advice. An AI assistant that uses unnecessarily complex language is reducing the quality of its help even when the technical content is correct.

Detection signals:
1. Using jargon when plain language works
2. Using formal terminology for informal concepts
3. Excessive qualifications and caveats
4. Multi-layer abstractions in explanations
5. Longer explanations than necessary
</think>

**Communication Over-Engineering Detection**

**Signal 1: Unnecessary jargon**
```
OVER-ENGINEERED LANGUAGE:
  "You should implement a unidirectional data flow pattern
   with immutable state management to ensure referential
   transparency in your UI components."

CLEAR LANGUAGE:
  "Keep data flowing in one direction: parent to child.
   Don't modify state directly — create new state objects.
   This makes your UI predictable and easier to debug."

Detection rule: If you can say it in simpler words
without losing meaning, the complex words are unnecessary.

EXCEPTION: When talking to an expert audience that uses
these terms as precise shorthand. "Implement CQRS" is
appropriate when the reader knows what CQRS means and
the recommendation is specifically for that pattern.
```

**Signal 2: Over-qualifying simple advice**
```
OVER-QUALIFIED:
  "While there are many possible approaches, and the optimal
   solution depends on various factors including but not limited
   to team size, existing infrastructure, and performance
   requirements, generally speaking, in most cases, you would
   likely want to consider using a database index."

DIRECT:
  "Add a database index on the columns you're searching by.
   This will fix your slow query."

Detection rule: If the qualifications are longer than
the actual advice, remove the qualifications.

Keep caveats for when they genuinely change the advice:
  "Add an index — unless you're doing heavy writes on this
   table, in which case the index overhead might make
   writes slower. Check write frequency first."
```

**Signal 3: Unnecessary abstraction in explanations**
```
OVER-ABSTRACTED:
  "The system employs a publish-subscribe pattern where
   domain events are emitted by aggregate roots and consumed
   by event handlers that project state changes into
   read-optimized views."

CONCRETE:
  "When an order is placed, the system sends a message.
   Other parts of the system listen for that message and
   update their own data. For example, the analytics
   dashboard listens for order messages and updates
   the daily sales total."

Detection rule: If your explanation requires understanding
the explanation to understand the explanation, you have
too many abstraction layers. Use concrete examples first,
then introduce abstract terms if needed.
```

**Signal 4: Unnecessary length**
```
OVER-LONG:
  Three paragraphs explaining what a variable is before
  showing how to use it.

RIGHT-SIZED:
  Show the code, then explain the parts that aren't obvious.

Detection rule: Start with the answer. Add explanation
only for parts that aren't self-evident.

STRUCTURE FOR CLARITY:
  1. Answer the question (1-2 sentences)
  2. Show the code (minimal working example)
  3. Explain non-obvious parts (only what's needed)
  4. Note gotchas (only if they're likely to be hit)
```

**Self-correction checklist**
```
Before delivering technical advice, ask:

□ Could a junior developer understand this?
  If not → simplify the language

□ Is every technical term necessary?
  If not → replace with plain language

□ Could I say this in half the words?
  If yes → cut the excess

□ Does the explanation start with the answer?
  If not → restructure

□ Are my caveats adding value or hedging?
  If hedging → remove them

□ Would a concrete example be clearer than my explanation?
  If yes → lead with the example
```

**The meta-principle:** Clear communication is not dumbing down — it is precision. Using simple language to explain complex concepts is harder than using complex language, and it is more valuable. The goal is for the reader to understand the concept, not to be impressed by the explanation. Every unnecessary word, every unexplained term, and every over-qualified statement is friction between the user and the understanding they need.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
