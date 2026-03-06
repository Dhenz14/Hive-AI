"""Phase 2F: Advanced Reasoning — Uncertainty Calibration (Part 6/6)"""

PAIRS = [
    (
        "thinking/uncertainty-language-choice-new-project",
        "We're starting a new backend service for real-time event processing. The team knows Python well, but someone suggested Go for performance. Another person wants Rust. What should we choose?",
        r'''<think>
Language choice for real-time event processing. Let me reason with calibrated confidence.

**Python:**
- Team already knows it (huge advantage)
- Ecosystem: FastAPI + asyncio is solid for event processing
- Performance: adequate for most use cases, but CPU-bound work is limited by GIL
- Real-time: asyncio handles concurrent I/O well, but not great for CPU-intensive processing
- Confidence: 70% that Python is sufficient for their needs

**Go:**
- Learning curve: 2-4 weeks for Python developers (Go is simple)
- Concurrency model: goroutines are perfect for event processing
- Performance: 10-50x faster than Python for CPU-bound work
- Deployment: single binary, no runtime dependencies
- Ecosystem: good for network services, less rich for data processing
- Confidence: 75% this is the right choice IF they need high throughput

**Rust:**
- Learning curve: 3-6 months for Python developers (significant)
- Performance: fastest option, zero-cost abstractions
- Memory safety: great for systems programming
- Ecosystem: growing but less mature than Go/Python for web services
- Confidence: 85% this is overkill for most event processing services

**What do I not know?**
- How many events per second? 100/s vs 1,000,000/s changes the answer dramatically
- CPU-bound or I/O-bound processing? Python is fine for I/O-bound
- Team size? Small team = stick with what you know
- Latency requirements? p99 latency < 10ms is harder in Python
- How long do they expect to maintain this? Language choice has long-term implications

**My analysis:**
- < 10K events/second, I/O-bound: Python (90% confident)
- 10K-100K events/second: Go (80% confident)
- 100K+ events/second, ultra-low latency: Go or Rust, depends on complexity
- Rust is almost never the right choice for a web service unless you need extreme performance or memory safety guarantees

**The meta-insight:**
Most teams overestimate their performance requirements. "Real-time event processing" sounds like it needs Go, but often it means "process webhook events quickly" which Python handles easily at 1000 req/s.
</think>

The answer depends on your actual throughput requirements, which most teams overestimate. Here's my analysis with confidence levels:

## Decision Framework

| Events/Second | Recommended | Confidence |
|--------------|-------------|------------|
| < 10K (most services) | **Python** | **90%** |
| 10K - 100K | **Go** | **80%** |
| 100K+ or strict latency SLA | **Go or Rust** | **70%** |

## Why Python Is Probably Fine (90% Confident for Most Cases)

```python
# FastAPI + asyncio handles 5-10K concurrent events easily
from fastapi import FastAPI
import asyncio
from collections import defaultdict

app = FastAPI()
handlers = defaultdict(list)

@app.post("/events")
async def process_event(event: dict):
    event_type = event["type"]
    # Async handlers — non-blocking I/O
    tasks = [handler(event) for handler in handlers[event_type]]
    await asyncio.gather(*tasks)
    return {"status": "processed"}

# Benchmark: FastAPI + uvicorn handles ~5,000-10,000 req/s
# on a single machine. Is that enough? Probably yes.
```

**When Python ISN'T enough:**
- CPU-bound processing per event (heavy parsing, ML inference, compression)
- p99 latency requirement < 5ms (Python GC pauses can exceed this)
- Processing 50K+ events/second on a single machine

## When to Choose Go (80% Confident at 10K+ Events/s)

```go
// Go's goroutines are designed for this exact use case
func processEvents(events <-chan Event) {
    for event := range events {
        go func(e Event) {
            // Each event processed concurrently
            // Goroutines are cheap (~2KB stack each)
            // Can run millions concurrently
            handleEvent(e)
        }(event)
    }
}

// Go advantage: one binary, no dependencies, easy deployment
// Learning curve: 2-4 weeks for Python developers
```

**Advantages over Python:**
- 10-50x faster for CPU-bound work
- Real goroutine concurrency (no GIL)
- Predictable latency (smaller GC pauses)
- Single binary deployment (no pip, no virtualenv)

## Why Rust Is Probably Overkill (85% Confident)

Rust is the fastest option, but the cost is real:
- **3-6 month learning curve** for a Python team (ownership, lifetimes, borrow checker)
- **Slower development velocity** — Rust code takes 2-3x longer to write than Go
- **Smaller ecosystem** for web services compared to Go

Rust makes sense for:
- Embedded systems, OS-level code, databases
- When you genuinely need zero-overhead abstractions
- When memory safety guarantees are non-negotiable (security-critical)

**It rarely makes sense for:** web services, event processors, APIs — where Go or even Python is fast enough.

## What I'm Less Sure About (65-70%)

**Your actual throughput needs** (65% confident in my estimate):
- "Real-time event processing" often means "process within 1 second" → Python
- Sometimes it means "process within 1ms" → Go
- Rarely means "process within 1μs" → Rust
- **Verify:** What's your expected events/second? What's your latency SLA?

**Team adaptation to Go** (70% confident):
- Go is syntactically simple, but the idioms are different from Python
- Error handling (`if err != nil`) frustrates Python developers initially
- No generics until recently; no exceptions; different testing patterns
- Most Python teams adapt in 2-4 weeks for productive work, 2-3 months for idiomatic Go

## My Recommendation

```
1. Start with Python (your team already knows it)
2. Benchmark with realistic load
3. If Python can't meet your requirements → switch to Go
   (Don't switch preemptively based on assumptions)

The cost of building in Go when Python suffices:
  → 2-4 weeks of learning + slower development for months

The cost of starting in Python and switching later:
  → Rewrite one service (days-weeks, depending on complexity)
  → But you validated that you ACTUALLY need better performance
```

Most teams that choose Go or Rust "for performance" later discover that their bottleneck was the database, the network, or the external APIs — not the language. Optimize the architecture first, then the language if needed.'''
    ),
    (
        "thinking/uncertainty-monolith-vs-microservices-decision",
        "We're a 6-person startup building a SaaS product. We're debating whether to start with microservices or a monolith. The CTO wants microservices for 'scalability.' I'm skeptical. What's the right call?",
        r'''<think>
6-person startup, microservices vs monolith. This is one of the most important architectural decisions and one where I have strong opinions backed by industry experience.

**Monolith for a 6-person startup:**
- Confidence: 90% this is the right choice
- Reasoning:
  - 6 people can't effectively operate microservices (need dedicated DevOps)
  - Communication overhead between services > communication between teammates in a small team
  - You don't know your domain boundaries yet — microservices lock in wrong boundaries
  - Speed of development is paramount for startups (ship fast, iterate)
  - One database, one deploy, one thing to debug
  - All major tech companies started as monoliths (Shopify, Twitter, Netflix)

**Microservices for a 6-person startup:**
- Confidence: 10% this is right (only if they have very specific reasons)
- When it might be right:
  - Different parts need different technology stacks
  - They have previous microservices experience
  - Regulatory requirements mandate isolation
- But these are rare for a 6-person startup

**The CTO's "scalability" argument:**
- Premature optimization
- A well-structured monolith scales to MILLIONS of users
- Shopify handles billions of dollars in transactions on a monolith
- If you can't handle load with a monolith, you have a different problem (database, caching, not architecture)
- You can ALWAYS extract services later when you KNOW what needs to scale independently

**The modular monolith:**
The middle ground that gives you 90% of microservices' benefits without the costs:
- Single deployment
- Strong module boundaries within the monolith
- Each module could become a service later if needed
- No network calls between modules (function calls instead)

**Uncertainties:**
- I don't know their domain complexity (some domains naturally split)
- I don't know if they have existing microservices infrastructure
- I don't know their hiring plans (growing to 50 in a year changes things)
- I don't know their compliance requirements
</think>

Start with a monolith. I'm **90% confident** this is right for a 6-person startup. Here's why:

## The Scalability Argument Is Wrong

```
"We need microservices for scalability"

Counterexamples:
- Shopify: monolith → handles Black Friday (billions in sales)
- Stack Overflow: serves 1.7 billion pageviews/month from... a monolith
- Basecamp (37signals): monolith → millions of users, small team
- GitHub: started as Rails monolith → millions of developers

These companies scaled to levels your startup won't reach for YEARS.
A monolith doesn't prevent scaling — premature microservices prevent shipping.
```

## Cost Comparison (90% Confident)

| Factor | Monolith | Microservices |
|--------|----------|---------------|
| Deploy complexity | 1 service to deploy | 5-15 services to deploy |
| Debugging | Stack trace in one process | Distributed tracing across services |
| Local development | `make dev` | Docker Compose with 10+ containers |
| Team needed | 6 developers | 6 developers + 2 DevOps minimum |
| Time to first feature | 1 day | 1 week (infra setup first) |
| Network latency | 0ms (function calls) | 1-50ms per service-to-service call |
| Transaction handling | Database transactions | Saga pattern (weeks to implement) |
| Consistency | Strong (one database) | Eventual (distributed data) |

## What You Should Build: Modular Monolith

```python
# A modular monolith gives you clean boundaries WITHOUT the ops overhead

project/
  app/
    users/              # User module — could become a service later
      models.py
      services.py       # All business logic here
      api.py           # Routes
      tests/
    orders/             # Order module
      models.py
      services.py
      api.py
      tests/
    payments/           # Payment module
      models.py
      services.py
      api.py
      tests/
    shared/             # Shared utilities (minimal!)
      auth.py
      email.py

# Rules:
# 1. Modules communicate through services.py (not direct model access)
# 2. No circular imports between modules
# 3. Each module owns its own models
# 4. Shared code is minimal and infrastructure-only
```

```python
# Module boundaries are enforced by convention:

# ✅ CORRECT: orders module calls users module through service interface
# orders/services.py
from users.services import get_user  # Clean dependency

def create_order(user_id, items):
    user = get_user(user_id)  # Function call, not HTTP request
    # ...

# ❌ WRONG: orders module directly queries users' database models
# orders/services.py
from users.models import User  # Breaking module boundary!
user = User.objects.get(id=user_id)
```

## When to Extract a Service (Not Now)

Extract a microservice ONLY when you have a **specific, measured reason**:

```markdown
Extract when:
- [ ] One module needs to scale independently (10x more load than others)
- [ ] Different teams need to deploy independently (you have 15+ engineers)
- [ ] A module needs a different technology (ML model in Python, API in Go)
- [ ] Regulatory isolation required (PCI compliance for payments)

Do NOT extract because:
- [ ] "It might be needed someday" → YAGNI
- [ ] "Microservices are best practice" → for 500-person companies
- [ ] "Our CTO read a blog post" → architectural decisions need data
- [ ] "We want to use Kubernetes" → don't choose architecture for your infra
```

## What I'm Less Sure About (70%)

**Your growth trajectory** matters:
- If you're planning to hire 30 engineers in the next year, a modular monolith's module boundaries will help you extract services when team size justifies it
- If you're staying at 6 people for the foreseeable future, a monolith is unambiguously right

**The CTO's experience** matters:
- If the CTO has successfully built and operated microservices before, they understand the cost — but I'd still argue the startup phase needs speed over architecture
- If this is their first microservices project, the learning cost will consume the team for months

**Bottom line at 90% confidence:** Build a well-structured monolith. Ship your product. Get customers. THEN extract services when you have data about what actually needs to scale. Every month spent on microservices infrastructure before product-market fit is a month your competitors are shipping features.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
