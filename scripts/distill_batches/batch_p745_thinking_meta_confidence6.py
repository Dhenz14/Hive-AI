"""Phase 3D: Metacognition — Confidence Calibration Under Pressure (Part 6)

Additional scenarios for remaining Phase 3D pairs.
"""

PAIRS = [
    (
        "thinking/meta-confidence-debug-flaky-test",
        r'''We have a test that passes locally but fails in CI about 30% of the time. The test checks that a background worker processes a job within 5 seconds. What's wrong?''',
        r'''<think>
I'm fairly confident about the category of bug but uncertain about the specific cause.

What I'm confident about:
- A test that fails 30% of the time in CI is a classic "flaky test"
- "Processes within 5 seconds" is a timing-dependent assertion — the most common source of flaky tests
- CI machines are typically slower and more variable than local development machines
- The 5-second timeout probably works locally (faster machine) but sometimes exceeds in CI (shared, slower resources)

What I'm uncertain about:
- Whether it's a timing issue or a race condition in the application code
- Whether CI has resource contention (other builds using the same machine)
- Whether the worker actually processes the job but the test checks too early
- Whether database/Redis initialization in CI is slower

What I definitely don't know:
- The actual test code
- CI environment specs
- Whether other tests are also flaky
- Whether the worker uses threading, multiprocessing, or Celery
</think>

**Almost certainly a timing issue.** CI machines are slower and more variable than your local machine. I'm fairly confident about this diagnosis.

**The pattern:**
```
Local machine:    Job completes in 1-2 seconds → 5s timeout always passes
CI machine:       Job completes in 3-7 seconds → 5s timeout fails 30% of the time
```

**Why CI is slower:**
- Shared resources (other builds compete for CPU)
- Virtualized/containerized (I/O is slower)
- Cold caches (no warm Redis/DB from previous runs)
- Less CPU/RAM than your development machine

**Fix: Don't use fixed timeouts. Poll with backoff:**

```python
# BAD: Fixed timeout
import time
submit_job(data)
time.sleep(5)
result = get_job_result()  # Might not be done yet in CI
assert result is not None

# GOOD: Poll with increasing waits
import time

submit_job(data)
for attempt in range(20):  # Up to ~30 seconds total
    result = get_job_result()
    if result is not None:
        break
    time.sleep(0.5 * (1.5 ** min(attempt, 5)))  # Exponential backoff
else:
    pytest.fail("Job did not complete within timeout")

assert result.status == 'completed'
```

**Even better — use a callback/event:**
```python
# Best: No sleeping at all
from threading import Event

done = Event()
submit_job(data, on_complete=lambda: done.set())
assert done.wait(timeout=30), "Job did not complete"
result = get_job_result()
assert result.status == 'completed'
```

**What I'm uncertain about:**
- Whether the flakiness is ONLY timing (could be a race condition in the worker)
- Whether CI resource contention varies by time of day
- Whether the test has other non-deterministic elements (random data, network calls)

**To verify:** Add timing logs to the test to see how long the job actually takes in CI vs local.'''
    ),
    (
        "thinking/meta-confidence-underdefined-search",
        r'''I need to add search to my app. What should I use?''',
        r'''<think>
This is extremely vague. "Search" could mean anything from a SQL LIKE query to a full Elasticsearch cluster.

What I definitely don't know:
- What they're searching (products? documents? users? code?)
- How much data (100 items? 10 million?)
- What kind of search (keyword? full-text? fuzzy? faceted?)
- Current tech stack
- Whether they need real-time indexing
- Autocomplete? Typo tolerance? Relevance ranking?

I can't give a recommendation. I need to ask questions.
</think>

**I need more context — "search" means very different things.** The right tool depends on:

1. **What are you searching?** (products, articles, users, logs?)
2. **How much data?** (hundreds → SQL, millions → dedicated search)
3. **What features?** (keyword match? fuzzy/typo tolerance? faceted filters? autocomplete?)
4. **Current stack?** (PostgreSQL? MongoDB? No database?)

**Quick decision tree:**

```
How many items to search?
├── < 10,000 → SQL LIKE or PostgreSQL full-text search
├── 10,000 - 1,000,000 → PostgreSQL FTS or Meilisearch
└── > 1,000,000 → Elasticsearch or Typesense

Need typo tolerance?
├── No → PostgreSQL full-text search
└── Yes → Meilisearch, Typesense, or Elasticsearch

Need autocomplete?
├── No → PostgreSQL or basic search
└── Yes → Meilisearch (easiest), Elasticsearch (most powerful)
```

**Cost comparison:**

| Solution | Setup effort | Infrastructure | Best for |
|----------|-------------|---------------|----------|
| SQL LIKE | 5 minutes | None (existing DB) | Small datasets, simple search |
| PostgreSQL FTS | 1 hour | None (existing DB) | Medium datasets, keyword search |
| Meilisearch | 2 hours | Small service (~256MB) | Typo tolerance, autocomplete |
| Typesense | 2 hours | Small service (~256MB) | Similar to Meilisearch |
| Elasticsearch | 1-2 days | Large cluster (2GB+ RAM) | Complex analytics, huge datasets |

**Tell me your use case and I can give specific advice.**'''
    ),
    (
        "thinking/meta-confidence-no-consensus-typing",
        r'''Should I add type hints to all my Python code? My team is debating whether it's worth the effort.''',
        r'''<think>
There's no universal consensus on this. Let me present both sides honestly.

What I'm confident about:
- Type hints improve IDE support (autocomplete, refactoring)
- Type hints catch some bugs before runtime (with mypy)
- Type hints serve as documentation
- Adding types to an existing codebase is a significant effort
- Types can add visual noise, especially for simple code
- Python's type system is optional and gradual — you don't have to type everything

What I'm uncertain about:
- The ROI of typing for this specific team's codebase
- Whether mypy strictness level matters more than coverage
- Whether the team would actually run mypy in CI
</think>

**The community is split on this.** There's no single right answer. Here's an honest assessment:

**Arguments FOR type hints:**
- Catch bugs before runtime (`mypy` finds ~5-15% of bugs in my observation)
- Better IDE experience (autocomplete, refactoring, go-to-definition)
- Self-documenting (function signatures tell you what types to pass)
- Safer refactoring (type checker catches cascading changes)

**Arguments AGAINST (or for limited typing):**
- Significant effort to add to existing code
- Visual noise for simple functions
- Python's type system has limitations (runtime behavior unchanged)
- Some patterns are hard to type correctly (decorators, metaprogramming)
- Team must learn typing syntax + run mypy in CI

**What I'm confident about — a pragmatic middle ground:**

```python
# ALWAYS type these (high value):
def process_payment(amount: float, currency: str) -> PaymentResult:
    ...  # Public API — types prevent caller mistakes

# Type hints optional here (low value):
x = 42  # Obviously an int
names = ["Alice", "Bob"]  # Obviously a list of strings
for name in names:  # Type is clear from context
    print(name)
```

**My uncertain recommendation:**
1. Type function signatures (parameters + return types) — highest value
2. Don't type local variables unless the type isn't obvious
3. Run mypy in CI on new code, don't backfill everything at once
4. Use `--strict` gradually, not from day one

**What the teams I've seen succeed with:**
```ini
# mypy.ini — start lenient, tighten over time
[mypy]
python_version = 3.11
warn_return_any = True
warn_unused_configs = True
# Don't require types everywhere initially:
disallow_untyped_defs = False
```

The team that types function signatures but not every variable gets 80% of the benefit with 20% of the effort. That's my best guess, not settled science.'''
    ),
    (
        "thinking/meta-confidence-security-env-files",
        r'''Are .env files a secure way to store secrets?''',
        r'''<think>
I'm fairly confident about this topic but need to be nuanced — .env files are a recommended practice but with important caveats.

What I'm confident about:
- .env files are BETTER than hardcoding secrets in source code
- .env files should NEVER be committed to version control
- .env files are NOT encrypted — they're plaintext on disk
- For production, there are more secure alternatives (secret managers)
- .env files are appropriate for development and some deployment scenarios

What I'm uncertain about:
- The specific threat model — "secure enough" depends on what attacks they're defending against
- Whether their deployment platform has a better alternative (Heroku config vars, AWS Secrets Manager)
- Their compliance requirements (PCI, HIPAA, SOC2 may require secret managers)
</think>

**Better than hardcoding, but not the most secure option.** The answer depends on your environment and threat model.

**What I'm confident about:**

**.env files are appropriate when:**
- Local development
- Small projects with trusted deployment environments
- .env is properly gitignored and never committed

**.env files are NOT secure enough when:**
- Multiple people have server access (anyone can read the file)
- Compliance requirements (PCI, HIPAA, SOC2)
- The server might be compromised
- Secrets need rotation/auditing

**Security spectrum (least to most secure):**

| Method | Security | Convenience | When to use |
|--------|----------|------------|-------------|
| Hardcoded in code | Terrible | High | Never |
| .env file (gitignored) | Basic | High | Development |
| Platform env vars (Heroku, Vercel) | Good | High | Simple deployments |
| Cloud secret manager (AWS SM, GCP SM) | Very good | Medium | Production |
| HashiCorp Vault | Excellent | Low | Enterprise, regulated |

**If you use .env files, these are essential:**
```bash
# .gitignore — MUST include:
.env
*.env
.env.*

# File permissions — restrict access:
chmod 600 .env  # Only owner can read
```

**What I'm uncertain about:**
- Whether .env files are "secure enough" for YOUR specific situation
- Whether your deployment platform provides a better alternative

**My recommendation:** Use .env for development, platform-provided env vars or a secret manager for production. The effort to switch to a secret manager is low and the security improvement is significant.'''
    ),
    (
        "thinking/meta-confidence-scale-prediction-websocket",
        r'''Can WebSockets handle 100,000 concurrent connections on a single server?''',
        r'''<think>
I'm somewhat confident about the theoretical answer but uncertain about practical constraints.

What I'm confident about:
- A single server CAN handle 100K concurrent WebSocket connections (it's been demonstrated)
- Each WebSocket connection is a persistent TCP connection
- The C10K problem was solved decades ago — modern OS can handle 100K+ sockets
- The limiting factors are usually memory, file descriptors, and application logic, not the protocol

What I'm uncertain about:
- The specific server hardware (CPU, RAM, network)
- What happens ON each connection (idle connections vs active message flow)
- The framework/runtime being used (Node.js, Go, Python — very different capabilities)
- Whether they need to broadcast to all 100K connections simultaneously

What I can't predict:
- Actual performance without benchmarking
- Memory usage per connection in their specific stack
- The impact of application logic on each connection
</think>

**Theoretically yes, practically it depends.** I can give ranges but not exact numbers without knowing your stack.

**What I'm confident about:**
- The protocol supports it — WebSockets are just TCP connections
- Modern Linux handles 100K+ open sockets easily
- The bottleneck is usually application logic, not the protocol

**Memory math (rough estimates):**
```
Per WebSocket connection:
- TCP socket buffer: ~8-16 KB
- Application state: varies (1 KB for chat, 100 KB for game state)
- Runtime overhead: depends on language

Conservative estimate: ~50 KB per connection
100,000 × 50 KB = ~5 GB RAM just for connections

With 32 GB RAM: feasible for idle/light connections
With 8 GB RAM: probably maxes out at ~50K
```

**What I'm uncertain about — framework differences:**

| Runtime | 100K idle connections | 100K active connections |
|---------|----------------------|----------------------|
| Go | Yes (goroutines are cheap) | Probably (depends on logic) |
| Node.js (ws) | Yes (event loop handles idle well) | Maybe (CPU-bound JS is single-threaded) |
| Python (asyncio) | Maybe (higher per-connection overhead) | Unlikely without multiple processes |
| Java (Netty) | Yes | Probably |

**Critical configuration:**
```bash
# Linux: increase file descriptor limits
ulimit -n 200000  # Default is often 1024!

# /etc/sysctl.conf:
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
fs.file-max = 200000
```

**My honest answer:** 100K idle connections on a beefy server: yes, with proper configuration. 100K connections all actively sending/receiving messages every second: probably needs multiple servers or a very efficient runtime (Go, Rust).

**I'd recommend load testing before committing to this architecture.** Don't trust theoretical numbers — benchmark with your actual application logic.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
