"""Phase 4D: Self-Improvement — Meta-Learning (Part 11)

Metacognitive strategies for learning new frameworks quickly —
how an AI assistant can rapidly acquire and apply knowledge
about unfamiliar technologies by leveraging structural patterns.
"""

PAIRS = [
    (
        "thinking/auto-metalearning-framework-mapping",
        r'''How can I develop metacognitive strategies to learn new programming frameworks quickly? When a user asks about a framework I have limited training data on, how should I reason about it?''',
        r'''<think>
Learning new frameworks quickly is fundamentally about pattern recognition across frameworks. Most frameworks solve the same categories of problems (routing, state management, data access, authentication) with different APIs and philosophies. The metacognitive strategy is:

1. Identify which problem category the framework addresses
2. Map its concepts to known frameworks in the same category
3. Identify where the new framework diverges from familiar patterns
4. Focus learning on the divergences, not the similarities

This is transfer learning applied to framework knowledge.
</think>

**Metacognitive Framework for Rapid Framework Learning**

**Step 1: Categorize the framework**
```
What problem domain does it serve?
- Web framework (Express, Django, Rails pattern)
- UI framework (React, Vue, Svelte pattern)
- ORM/data layer (SQLAlchemy, Prisma pattern)
- Task/workflow (Celery, Temporal pattern)
- API layer (GraphQL, tRPC, REST pattern)

Knowing the category immediately gives you:
- Expected concepts (routes, models, views, controllers)
- Common patterns (middleware, hooks, lifecycle methods)
- Typical gotchas (N+1 queries, state management)
```

**Step 2: Map core abstractions**
```
For any new framework, identify these five elements:
1. ENTRY POINT: How does the application start?
2. ROUTING: How are requests/events directed to handlers?
3. STATE: How is application state managed?
4. DATA FLOW: How does data move through the system?
5. EXTENSION: How do you add custom behavior (plugins, middleware)?

Example mapping:
  Express          → FastAPI           → Next.js
  app.listen()     → uvicorn.run()     → next start
  app.get('/path') → @app.get('/path') → pages/path.tsx
  req/res objects   → Pydantic models   → props/state
  middleware chain   → dependency inject → middleware.ts
  app.use()         → Depends()         → next.config.js
```

**Step 3: Identify the framework's "opinion"**
```
Every framework has a philosophy that drives its API design:

Convention over configuration (Rails, Next.js):
  → Learn the conventions first, customization second
  → File structure IS the configuration

Configuration over convention (Express, Fastify):
  → Learn the config patterns, expect explicit setup
  → Flexibility means more boilerplate

Reactive/declarative (React, Vue, Svelte):
  → Learn the reactivity model first
  → Understand when and why things re-render

The opinion tells you WHERE to focus learning effort.
```

**Step 4: Build a minimal mental model**
```
Before advising on any framework, construct this:

1. Hello World: Simplest possible working example
2. CRUD: Create, Read, Update, Delete operations
3. Error handling: How errors propagate and are caught
4. Testing: How the framework expects you to test
5. Deployment: How it's meant to be deployed

If you can mentally trace these five scenarios,
you have enough to give useful guidance.
```

**Step 5: Identify unique differentiators**
```
What does THIS framework do differently?
- Svelte: Compile-time reactivity (no virtual DOM)
- Rust's Axum: Type-safe extractors from requests
- htmx: Server-rendered HTML fragments (no JSON APIs)
- Elixir Phoenix: LiveView (server-driven UI updates)

The differentiators are where most user questions focus,
because that is where their existing knowledge breaks down.
```

**The meta-principle:** You don't learn a framework from scratch. You learn the delta between what you already know and what's new. Focus cognitive effort on the gaps and divergences, not on re-learning familiar patterns with different syntax.'''
    ),
    (
        "thinking/auto-metalearning-concept-anchoring",
        r'''How should I anchor new technical concepts to existing knowledge when learning a framework I am less familiar with? What mental models help with rapid concept acquisition?''',
        r'''<think>
Concept anchoring is about connecting unfamiliar ideas to well-understood ones. The key insight is that most programming concepts are isomorphic — they solve the same fundamental problems with different syntax and trade-offs. Effective anchoring requires:

1. Finding the closest known equivalent
2. Explicitly noting where the analogy breaks down
3. Building a mental model of the differences

The danger is over-anchoring — assuming the new thing works exactly like the old thing. You need to anchor AND differentiate.
</think>

**Concept Anchoring Framework for Rapid Learning**

**Anchoring strategy: "Like X, except Y"**
```
Template: "[New concept] is like [known concept], except [key difference]"

Examples:
- "Go channels are like Python queues, except they're
   a language primitive with select statements for multiplexing"
- "Rust ownership is like C++ RAII, except the compiler
   enforces it at compile time with no runtime cost"
- "React Server Components are like PHP templates, except
   they can seamlessly interleave with client-side React"

This template forces you to:
1. Find the anchor (what you already know)
2. Identify the delta (what's actually new)
3. Focus study on the delta
```

**Anchoring by problem pattern**
```
When encountering a new concept, ask:
"What problem does this solve?"

Problem: Managing async operations
  Known: Promises, callbacks, async/await
  New: Rust Futures, Go goroutines, Elixir Tasks
  Anchor: Same problem, different concurrency model

Problem: Preventing invalid state
  Known: TypeScript types, validation libraries
  New: Rust enums, Haskell ADTs, Pydantic models
  Anchor: Same goal, different enforcement mechanism

Problem: Component communication
  Known: React props/callbacks, event emitters
  New: Svelte stores, Vue provide/inject, Angular services
  Anchor: Same need, different data flow patterns
```

**Anchoring hierarchy (most to least reliable)**
```
Level 1 — Same language, different library:
  Express → Fastify (very reliable anchor)
  Both are Node.js HTTP frameworks. 90% maps directly.

Level 2 — Same paradigm, different language:
  Django → Rails (reliable anchor)
  Both are MVC web frameworks. Core concepts map well.

Level 3 — Same problem, different paradigm:
  React → htmx (partial anchor)
  Both build interactive UIs, but the approach is fundamentally
  different. Anchor on the problem, not the solution.

Level 4 — Novel concept, no direct equivalent:
  Rust borrow checker, Haskell monads, Prolog unification
  These require building new mental models from scratch.
  Anchor on the PROBLEM they solve, not existing solutions.
```

**Detecting broken anchors**
```
Signs your anchor is misleading:
- "This should work like X but doesn't" → anchor mismatch
- Users keep hitting the same unexpected behavior → your
  mental model has a gap at the anchor boundary
- The framework's docs explicitly say "this is NOT like X"

When an anchor breaks:
1. Acknowledge the mismatch explicitly
2. Identify the specific assumption that was wrong
3. Build a new sub-model for the divergent behavior
4. Keep the anchor for the parts that still map correctly
```

**Practical application for AI assistants**
```
When a user asks about an unfamiliar framework:

1. Identify what you DO know that's closest
2. Reason from that anchor to the new context
3. Flag uncertainty: "Based on the pattern used by similar
   frameworks like X, this likely works by... however,
   please verify against the current documentation."
4. Learn from corrections: If the user corrects you,
   update your anchor mapping for future questions

This is more honest and useful than guessing confidently.
```

**The meta-principle:** Every new concept connects to something you already understand. The skill is finding the right connection while being honest about where it breaks. "Like X except Y" is the most powerful learning sentence in programming — it compresses a new concept into one anchor and one delta.'''
    ),
    (
        "thinking/auto-metalearning-documentation-reading",
        r'''What metacognitive strategies help me extract maximum knowledge from framework documentation quickly? How should I prioritize what to read and internalize?''',
        r'''<think>
Documentation reading is a skill that most developers (and AI systems) do poorly. The typical approach — reading linearly from the introduction — is inefficient. Good documentation reading is strategic:

1. Start with the "Getting Started" to understand the mental model
2. Jump to the API reference for specific questions
3. Read the "Advanced" sections for the framework's unique features
4. Ignore the marketing/philosophy sections (they rarely help with coding)

The metacognitive strategy is knowing WHAT to read based on WHAT you need to know.
</think>

**Strategic Documentation Reading Framework**

**Priority 1: Architecture mental model (5 minutes)**
```
Read ONLY these sections first:
- "Getting Started" or "Quick Start" (the hello world)
- "Core Concepts" or "Key Concepts" (the mental model)
- Table of contents (to map the knowledge landscape)

Goal: Answer these questions:
□ What are the 3-5 core abstractions?
□ How do they relate to each other?
□ What is the typical data/control flow?

Example for a web framework:
  Core abstractions: App, Router, Handler, Middleware, Context
  Flow: Request → Middleware → Router → Handler → Response
  Now you can reason about most questions.
```

**Priority 2: Common operations (10 minutes)**
```
Find examples for the most common tasks:
□ CRUD operations (how to create, read, update, delete)
□ Error handling (how errors are caught and returned)
□ Configuration (how to set up the application)
□ Authentication (how to protect routes/resources)

Skip:
✗ Installation instructions (trivial)
✗ History/motivation (doesn't help you code)
✗ Comparison with alternatives (marketing)
✗ Contribution guide (not relevant to users)
```

**Priority 3: Unique features (15 minutes)**
```
Every framework has 1-3 features that make it special:
- Next.js: Server components, file-based routing, ISR
- Rust Axum: Type-safe extractors, tower middleware
- FastAPI: Auto-generated OpenAPI docs, Pydantic integration

These are where most user questions focus because:
1. They are the reason people choose this framework
2. They don't map to other frameworks (no anchor available)
3. They have the steepest learning curve

Read the documentation for these features thoroughly.
```

**Priority 4: Error messages and troubleshooting**
```
The most valuable documentation section is often:
- "Common Errors" or "Troubleshooting"
- "Migration Guide" (shows what changed and why)
- GitHub issues labeled "FAQ" or "common"

These reveal:
- What users actually struggle with
- What the framework does differently than expected
- Where the mental model commonly breaks down
```

**Documentation reading anti-patterns**
```
AVOID:
- Linear reading from page 1 to page N
  (Most docs are reference material, not a novel)

- Reading without a question in mind
  (Passive reading has poor retention)

- Memorizing API signatures
  (Look them up when needed; understand concepts instead)

- Ignoring the changelog
  (Version differences cause most "it doesn't work" issues)

PREFER:
- Question-driven reading: "How do I do X?"
- Example-first: Read code examples before explanations
- Trace-through: Follow one request through the system
- Compare: How does this differ from the framework I know?
```

**Building a knowledge index**
```
After reading documentation, build a mental index:

Framework: [Name]
Version: [Current stable]
Mental model: [One sentence describing the core flow]
Key abstractions: [3-5 core concepts]
Unique features: [1-3 differentiators]
Common gotchas: [2-3 things that surprise newcomers]
Testing approach: [How tests are structured]
Best reference: [The most useful docs page]

This index lets you quickly recall the right context
when a user asks a question about this framework.
```

**The meta-principle:** Don't read documentation to memorize it. Read it to build a mental model you can reason from. A developer who understands the five core abstractions of a framework can figure out most things. A developer who memorized the API but missed the mental model will struggle with every new problem.'''
    ),
    (
        "thinking/auto-metalearning-pattern-transfer",
        r'''How can I transfer debugging and problem-solving patterns from one technology stack to another? What metacognitive skills enable effective cross-stack reasoning?''',
        r'''<think>
Cross-stack pattern transfer is one of the most valuable metacognitive skills. The insight is that most bugs and problems fall into a small number of categories that recur across all technology stacks:

1. State management bugs (wrong state, stale state, race conditions)
2. Integration boundary bugs (mismatched types, protocols, formats)
3. Resource management bugs (leaks, exhaustion, contention)
4. Configuration bugs (wrong environment, missing settings)
5. Concurrency bugs (races, deadlocks, ordering)

The debugging PROCESS is stack-agnostic even though the specific tools differ.
</think>

**Cross-Stack Pattern Transfer Framework**

**Universal debugging patterns**
```
These patterns work in ANY technology stack:

BINARY SEARCH DEBUGGING:
  Works in: JavaScript, Python, Rust, SQL, CSS, anything
  Pattern: Narrow the problem space by half at each step
  - Does it work with no middleware? (halves the code path)
  - Does it work with a hardcoded value? (isolates data vs logic)
  - Does it work in a fresh environment? (isolates config)
  Transfer: Same logical process, different tools (console.log,
  print(), dbg!(), EXPLAIN, browser DevTools)

MINIMAL REPRODUCTION:
  Works in: Every stack, every bug type
  Pattern: Strip away everything until the bug persists
  - Remove dependencies one at a time
  - Replace complex inputs with simple ones
  - Run in the simplest possible environment
  Transfer: The process is identical; only the "strip away" steps differ

BOUNDARY INSPECTION:
  Works in: Any system with components
  Pattern: Check the data at every boundary crossing
  - What did the client send? (network tab, logs)
  - What did the server receive? (request logging)
  - What did the database get? (query logging)
  - What came back? (response inspection)
  Transfer: HTTP, gRPC, message queues, IPC — all have boundaries
```

**Transferable problem categories**
```
Category: N+1 QUERY PROBLEM
  SQL/ORM: Fetching related records in a loop
  GraphQL: Resolver calling DB per field
  REST API: Client making one request per item
  Microservices: Service A calling Service B per item
  Solution pattern: Batch/bulk operations (always the same)

Category: CACHE INVALIDATION
  Browser: Stale JavaScript/CSS after deployment
  CDN: Stale pages after content update
  Application: Stale data in Redis/Memcached
  ORM: Stale query cache after writes
  Solution pattern: TTL + explicit invalidation (always the same)

Category: RACE CONDITION
  Frontend: Two clicks before first response returns
  Backend: Two requests modifying the same row
  Distributed: Two services processing the same event
  File system: Two processes writing the same file
  Solution pattern: Locking or idempotency (always the same)

Category: RESOURCE LEAK
  JavaScript: Event listeners not removed, intervals not cleared
  Python: File handles not closed, DB connections not returned
  Go: Goroutines blocked forever, channels never closed
  Java: Threads not terminated, streams not closed
  Solution pattern: Deterministic cleanup (finally/defer/using/with)
```

**Transfer methodology**
```
When encountering a problem in an unfamiliar stack:

Step 1: Classify the problem
  "This looks like a [state/boundary/resource/config/concurrency] issue"

Step 2: Recall the solution pattern from familiar stacks
  "In Python, I would solve this by..."

Step 3: Find the equivalent mechanism in the new stack
  "The equivalent in Rust would be..."

Step 4: Verify the transfer is valid
  "Does this stack have any unique constraints that
   make the familiar solution inappropriate?"

Example:
  Problem: Memory growing over time in a Go service
  Classify: Resource leak
  Python equivalent: Unclosed file handles or DB connections
  Go equivalent: Goroutine leak (goroutines waiting on channels)
  Verify: Go has garbage collection, so it is not manual memory.
  The goroutine leak pattern is Go-specific but the
  debugging approach (monitor, isolate, fix cleanup) is universal.
```

**What does NOT transfer well**
```
Be cautious transferring:
- Performance intuitions (what's fast in Python may not
  be fast in JavaScript; allocation costs differ by runtime)
- Error handling patterns (exceptions vs Result types vs
  error codes have different best practices)
- Concurrency models (threads vs async vs actors vs CSP
  have fundamentally different constraints)
- Memory models (GC vs ownership vs manual — very different)

For these, learn the stack-specific model rather than
trying to force a familiar pattern.
```

**The meta-principle:** About 80% of debugging skill transfers across stacks because bugs fall into universal categories. The remaining 20% is stack-specific tooling and idiom. When encountering a new stack, lead with your transferable debugging process and learn the stack-specific tools as you go.'''
    ),
    (
        "thinking/auto-metalearning-knowledge-gaps",
        r'''How should I identify and prioritize my own knowledge gaps when learning a new technology domain? What metacognitive strategies help me know what I do not know?''',
        r'''<think>
Knowing what you don't know is arguably the most important metacognitive skill. The Dunning-Kruger effect applies to AI assistants too — we can generate confident-sounding answers about topics we have shallow knowledge of. The strategies for identifying knowledge gaps are:

1. Calibration: Can I predict when my answers will be wrong?
2. Boundary mapping: Where does my reliable knowledge end?
3. Uncertainty detection: What signals indicate I'm guessing?
4. Strategic gap-filling: Which gaps matter most to fill?
</think>

**Knowledge Gap Identification Framework**

**Strategy 1: Confidence calibration**
```
For any topic, assess your knowledge on this scale:

Level 5 — Expert: Can explain trade-offs, edge cases, and
  common mistakes. Can debug complex problems.
  → Provide detailed advice confidently.

Level 4 — Proficient: Understand core concepts and common
  patterns. May miss edge cases.
  → Provide advice with minor caveats.

Level 3 — Familiar: Know the basics, can follow documentation.
  May have outdated or incomplete information.
  → Provide general guidance, recommend verification.

Level 2 — Aware: Know the technology exists and its purpose.
  Cannot reliably provide implementation details.
  → Share what you know, clearly flag uncertainty.

Level 1 — Blind spot: Don't know enough to know what's wrong.
  → Acknowledge the gap explicitly. Do not guess.

The danger zone is Level 2-3: enough knowledge to sound
confident, not enough to be reliably correct.
```

**Strategy 2: Gap detection signals**
```
You likely have a knowledge gap when:

□ HEDGING LANGUAGE: You find yourself saying "I think" or
  "I believe" or "typically" without specific evidence
  → This signals uncertainty; acknowledge it explicitly

□ GENERIC ANSWERS: Your advice could apply to any similar
  technology, with nothing specific to the one asked about
  → You're reasoning from the category, not the specific tool

□ VERSION UNCERTAINTY: You don't know which version
  introduced a feature or changed an API
  → Your knowledge may be outdated

□ MISSING TRADE-OFFS: You can list benefits but not drawbacks,
  or vice versa
  → Shallow knowledge lacks nuance

□ NO ERROR SCENARIOS: You can describe the happy path but not
  what goes wrong
  → Real expertise includes failure modes

□ COPY-PASTE REASONING: Your explanation mirrors documentation
  structure rather than reflecting genuine understanding
  → You may be pattern-matching rather than comprehending
```

**Strategy 3: Systematic boundary mapping**
```
For any technology domain, map your knowledge boundaries:

CORE CONCEPTS:
  [x] Understand   [ ] Shallow   [ ] Gap
  What are the fundamental abstractions?

COMMON PATTERNS:
  [x] Understand   [ ] Shallow   [ ] Gap
  How do experienced users typically use this?

EDGE CASES:
  [ ] Understand   [x] Shallow   [ ] Gap
  What breaks? What are the gotchas?

PERFORMANCE:
  [ ] Understand   [ ] Shallow   [x] Gap
  What are the performance characteristics?

ECOSYSTEM:
  [ ] Understand   [x] Shallow   [ ] Gap
  What libraries and tools complement this?

OPERATIONS:
  [ ] Understand   [ ] Shallow   [x] Gap
  How is this deployed, monitored, maintained?

The gaps and shallow areas are where mistakes happen.
```

**Strategy 4: Priority-based gap filling**
```
Not all gaps are equally important. Prioritize based on:

HIGH PRIORITY (fill immediately):
- Gaps that cause incorrect advice (wrong is worse than none)
- Gaps in safety-critical areas (security, data integrity)
- Gaps that users frequently ask about

MEDIUM PRIORITY (fill when encountered):
- Performance characteristics
- Ecosystem/tooling knowledge
- Migration and upgrade paths

LOW PRIORITY (acknowledge and defer):
- Historical context and design decisions
- Niche use cases
- Cutting-edge/unreleased features
```

**Strategy 5: Honest communication of gaps**
```
When you hit a knowledge gap, say so clearly:

GOOD:
"I'm not confident about the specific API for this in
version 4.x. The general approach would be [X], but
please check the current documentation for exact syntax."

"I can reason about this from similar frameworks, but
I don't have deep experience with [specific tool].
Here's what I'd expect based on the pattern: [Y]."

BAD:
"Here's how to do it: [confidently wrong code]"
"Just use [specific API]" (when you're not sure it exists)

Being wrong confidently destroys trust.
Being uncertain honestly builds it.
```

**The meta-principle:** The most valuable thing you can know is the boundary of your own knowledge. An AI assistant that says "I'm not sure about this specific detail, but here's what I can tell you" is far more useful than one that generates plausible-sounding but incorrect answers. Map your gaps, communicate them honestly, and fill them strategically.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
