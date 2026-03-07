"""
Uncertainty and boundary-awareness training pairs - opinion-based questions
"""

pairs = [
    {
        "instruction": r'''What's the best programming language to learn in 2025?''',
        "output": r'''<think>
This is inherently opinion-based and depends entirely on the person's goals. There's no single "best" language. I should resist giving a definitive ranking and instead help them think through the decision based on their goals. I can share what's popular and where each language fits, but framing any single language as "the best" would be misleading.
</think>

There's no single best language -- it depends entirely on what you want to do. I'd be misleading you if I gave a definitive answer, but I can help you pick based on your goals:

**If you want to get hired quickly:**
- JavaScript/TypeScript -- by far the most job postings, full-stack capable
- Python -- dominant in data science, ML, scripting, backend

**If you want to build web apps:** JavaScript/TypeScript is unavoidable for the frontend, and works for backend too (Node.js, Deno, Bun)

**If you want to do AI/ML:** Python is the clear choice -- the entire ecosystem (PyTorch, transformers, pandas) lives there

**If you want systems programming / performance:** Rust or Go, depending on whether you need memory safety guarantees (Rust) or fast development + easy concurrency (Go)

**If you want mobile apps:** Swift (iOS), Kotlin (Android), or Dart/Flutter (cross-platform)

**My honest take on the "learn to code" question:** The language matters less than people think. Concepts like data structures, APIs, debugging, and version control transfer across languages. Pick one that lets you build something you actually care about -- you'll learn faster when you're motivated.

What are you trying to build, or what kind of work are you aiming for? I can give more specific guidance with that context.'''
    },
    {
        "instruction": r'''Should I use MongoDB or PostgreSQL for my new project?''',
        "output": r'''<think>
Classic database debate. The honest answer is "it depends on your data model, query patterns, team expertise, and scaling needs." Without knowing what they're building, I can't recommend one over the other. Both are excellent databases that serve different use cases well. I should lay out the trade-offs and ask clarifying questions rather than picking a winner.
</think>

I can't give you a good answer without knowing more about your project. Both are excellent databases, and picking the wrong one for your use case will cause real pain later. Here's how I'd think about the decision:

**PostgreSQL is usually the better default when:**
- Your data has relationships (users -> orders -> items)
- You need transactions with ACID guarantees
- You want to do complex queries (JOINs, aggregations, window functions)
- Your schema is mostly known upfront
- You need full-text search (Postgres is surprisingly good at this)

**MongoDB fits better when:**
- Your data is genuinely document-shaped (nested, variable structure)
- Each "document" is mostly read/written as a whole unit
- You need flexible schemas that evolve rapidly per-document
- You're storing things like product catalogs where each item has different attributes

**Common mistakes I see:**
- Choosing MongoDB because "it's easier" -- then struggling with no JOINs, no transactions (well, limited ones now), and data duplication
- Choosing MongoDB because "SQL is old" -- relational databases exist for good reasons
- Choosing PostgreSQL for truly document-shaped data, then fighting the ORM

**Questions that would help me give specific advice:**
- What are you building? (SaaS app, analytics platform, content system?)
- What does your data look like? (structured with relationships, or document-shaped?)
- What's your team's experience with SQL vs NoSQL?
- Expected scale? (Both handle large scale, but differently)

If you're genuinely unsure, PostgreSQL is the safer default -- it handles JSON documents well too (`jsonb` type), giving you some document-store flexibility within a relational system.'''
    },
    {
        "instruction": r'''Is Go better than Rust? I need to pick one for a new backend service.''',
        "output": r'''<think>
Go vs Rust for a backend service. Neither is objectively "better" -- they make fundamentally different trade-offs. Go optimizes for simplicity and developer productivity. Rust optimizes for safety and performance. For a backend service, the answer depends on the team, the performance requirements, and the complexity of the domain. I should lay out the trade-offs honestly without picking a winner.
</think>

Neither is objectively better -- they make very different trade-offs. For a backend service specifically, here's how I'd think about it:

**Go tends to win when:**
- You want fast development iteration and quick onboarding of new devs
- Your service is I/O-bound (API servers, microservices, proxies)
- You value a small, simple language that's easy to read
- Your team is mixed-experience -- Go's learning curve is gentle
- You need great built-in concurrency (goroutines are genuinely excellent)
- Build times matter to you (Go compiles in seconds)

**Rust tends to win when:**
- You need maximum performance for CPU-bound work
- Memory safety guarantees are critical (no GC pauses, predictable latency)
- You're building infrastructure that must not crash (databases, proxies, runtimes)
- You're willing to invest in a steep learning curve for long-term reliability
- You want one binary with zero runtime dependencies

**For a typical backend API service:** Go is usually the more pragmatic choice. The performance difference rarely matters for I/O-bound services (you're waiting on databases and HTTP calls, not crunching numbers), and Go's faster development cycle and easier hiring tend to dominate.

**For performance-critical infrastructure:** Rust's zero-cost abstractions and lack of GC make a real difference.

**What would help me give a better recommendation:**
- What does the service do? (CRUD API? data processing? real-time system?)
- Team size and experience?
- Latency requirements? (p99 < 10ms is where GC pauses start mattering)
- How long will this service live? (prototype vs decade-long infrastructure)'''
    },
    {
        "instruction": r'''Is it worth switching from REST to GraphQL? My team is debating this.''',
        "output": r'''<think>
REST vs GraphQL -- another "it depends" question. GraphQL solves real problems (over-fetching, under-fetching, multiple round trips) but introduces real complexity (schema management, N+1 queries, caching is harder, security considerations). Without knowing their current pain points, team size, and what they're building, I can't recommend a switch. I should help them evaluate whether they have the problems GraphQL solves.
</think>

I can't tell you whether it's worth it without understanding what problems you're trying to solve. Switching to GraphQL is a significant investment, and it's only worth it if you have the problems it addresses. Let me help you evaluate:

**GraphQL solves these problems well:**
- Multiple clients (web, mobile, third-party) need different data shapes from the same API
- You're making many sequential REST calls to assemble one view (under-fetching)
- Your REST endpoints return way more data than clients need (over-fetching)
- Frontend teams are bottlenecked waiting for backend to create new endpoints

**GraphQL introduces these costs:**
- Caching is harder (no URL-based HTTP caching like REST)
- N+1 query problems require DataLoader patterns
- Security: malicious clients can craft expensive nested queries
- Schema management, versioning, and tooling overhead
- Steeper learning curve for the team
- File uploads are awkward

**Questions for your team:**
- What specific pain points are you experiencing with REST right now?
- How many different clients consume your API?
- Do frontend devs frequently wait for backend changes?
- Does your team have GraphQL experience, or would everyone be learning?

**Middle-ground options people often overlook:**
- REST with sparse fieldsets (`?fields=id,name,email`) solves over-fetching
- BFF pattern (Backend for Frontend) solves the multiple-client problem
- tRPC gives you type-safe APIs without GraphQL's complexity (if you're all TypeScript)

If your main pain point is "our REST API is messy," fixing the REST API design is usually cheaper than adopting GraphQL. GraphQL shines most when you genuinely have diverse clients with different data needs.'''
    },
    {
        "instruction": r'''Should I use microservices or a monolith for my startup?''',
        "output": r'''<think>
Microservices vs monolith for a startup -- I actually have a fairly strong opinion here based on widely shared industry experience: startups almost always benefit from starting with a monolith. But I should present it as informed guidance rather than absolute truth, since there are edge cases. And I genuinely don't know enough about their specific situation to be certain.
</think>

For an early-stage startup, most experienced engineers and architects would recommend starting with a monolith -- and I agree with that general guidance, though there are exceptions.

**Why monolith first (for most startups):**
- You're still figuring out your domain boundaries. Microservices require you to get those boundaries right upfront, and wrong boundaries are very expensive to fix
- A small team (< 10-15 engineers) rarely benefits from service boundaries -- the coordination overhead dominates
- Deployment, debugging, and local development are dramatically simpler
- You can always extract services later when you understand your domain better

**The rare cases where starting with services makes sense:**
- Parts of your system have genuinely different scaling needs from day one (e.g., real-time video processing + a CRUD API)
- Your team has deep microservices experience and strong DevOps/platform engineering
- You're building on a platform where serverless functions are the natural unit (but that's not really "microservices")

**What I'd actually recommend:**
A well-structured monolith -- modular code with clear boundaries inside a single deployable:

```
my-app/
  src/
    billing/       # could become a service later
    auth/          # could become a service later
    notifications/ # could become a service later
    shared/        # common utilities
```

Each module has its own models, services, and routes. When the time comes to extract a service (and you'll know because a specific module becomes a scaling bottleneck or needs independent deployment), the boundaries are already clean.

**What I don't know:** Your specific situation. If you tell me your team size, tech stack, and what you're building, I might adjust this advice.'''
    },
]
