"""
scripts/brain_mine.py

Three-phase knowledge extractor from Qwen3's 2024 brain into training pairs.
Runs independently of Flask. Resumable: already-mined topics are skipped.

PHASE 1 — Fast breadth pass (qwen3:14b, ~18-36h):
    python scripts/brain_mine.py --fast
    All 187 topics × 6 templates using qwen3:14b. Fits fully in 16GB VRAM.
    Produces ~1,100 pairs covering the full coding curriculum.

PHASE 2 — Deep review pass (qwen3:32b, ~3-4 days, run after Phase 1):
    python scripts/brain_mine.py --review
    6 deep templates (production, debug, optimize, reflect, adversarial,
    first-principles) on topics already mined in Phase 1. Uses 32b reasoning
    to find gaps the 14b may have missed. Adds ~500+ high-depth pairs.

PHASE 3 — o1-style reasoning pass (qwen3:32b, ~3-4 days, run after Phase 2):
    python scripts/brain_mine.py --o1
    6 o1-style templates (reflect_and_revise, debug_reasoning, adversarial_review,
    teach_from_first_principles, system_design, confidence_analysis).
    Teaches the model HOW to think, not just WHAT to know.

Other flags:
    --pairs N       Templates per topic (1-6, default 6)
    --dry-run       Show what would be mined without running
    --status        Show DB mining counts and remaining topics

The miner treats Qwen3 as a temporary 2024 teacher. Every pair is permanently
staged in SQLite — independent of which model runs tomorrow.
"""

import sys
import os
import logging
import argparse
import time
from pathlib import Path

# Add project root to sys.path so hiveai imports work standalone
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# ---------------------------------------------------------------------------
# Logging — both console and file
# ---------------------------------------------------------------------------
log_path = PROJECT_ROOT / "logs" / "brain_mine.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_path), encoding="utf-8"),
    ],
)
logger = logging.getLogger("brain_mine")

# ---------------------------------------------------------------------------
# MASTER TOPIC LIST — 150+ topics covering all coding knowledge in Qwen3:32b
# Categories: Python, Algorithms/DS, Design Patterns, Systems, Web/APIs,
#             Testing, Database, JavaScript/TypeScript, Security, DevOps
# ---------------------------------------------------------------------------
ALL_TOPICS = [
    # ===================================================================
    # PYTHON — fundamentals, internals, advanced patterns
    # ===================================================================
    "Python generators and itertools",
    "Python decorators and functools",
    "Python context managers and __enter__/__exit__",
    "Python metaclasses and class creation",
    "Python descriptors and __get__/__set__",
    "Python memory management and garbage collection",
    "Python GIL and threading limitations",
    "Python asyncio event loop",
    "Python async/await patterns",
    "Python dataclasses vs namedtuple vs TypedDict",
    "Python type hints and mypy",
    "Python slots and memory optimization",
    "Python weakref and circular references",
    "Python __dunder__ methods and operator overloading",
    "Python comprehensions and generator expressions",
    "Python Protocol classes and structural subtyping",
    "Python abstract base classes and ABC module",
    "Python concurrent.futures for parallel execution",
    "Python multiprocessing with shared memory",
    "Python pathlib for file system operations",
    "Python logging configuration and best practices",
    "Python enum types and Flag enums",
    "Python contextlib utilities and helpers",
    "Python functools.lru_cache vs functools.cache",
    "Python itertools advanced recipes",
    "Python string formatting f-strings vs Template",
    "Python exception hierarchy and custom exceptions",
    "Python __init__ vs __new__ vs __init_subclass__",
    "Python property decorators and computed attributes",
    "Python class methods vs static methods vs instance methods",
    "Python import system and module loading",
    "Python packaging with pyproject.toml and setuptools",
    "Python virtual environments and dependency isolation",
    "Python profiling with cProfile and line_profiler",
    "Python ctypes and C extension interoperability",
    "Python struct module for binary data",
    "Python regex and re module advanced patterns",
    "Python csv, json, and xml parsing patterns",
    "Python subprocess and shell interaction",
    "Python socket programming and TCP/UDP",

    # ===================================================================
    # ALGORITHMS AND DATA STRUCTURES
    # ===================================================================
    "binary search and its variants",
    "dynamic programming with memoization",
    "depth-first search and breadth-first search",
    "quicksort and mergesort implementation",
    "heap and priority queue operations",
    "hash table collision resolution",
    "trie data structure",
    "union-find / disjoint sets",
    "sliding window technique",
    "two-pointer technique",
    "backtracking algorithms",
    "graph shortest path algorithms (Dijkstra, Bellman-Ford)",
    "tree traversal patterns",
    "time and space complexity analysis (Big O notation)",
    "linked list operations and reversal",
    "stack and queue implementation from scratch",
    "binary tree construction and manipulation",
    "graph cycle detection",
    "topological sort (Kahn's algorithm and DFS)",
    "counting sort and radix sort",
    "string pattern matching (KMP algorithm)",
    "longest common subsequence and edit distance",
    "matrix spiral traversal and rotation",
    "interval merging and sweep line algorithm",
    "monotonic stack problems",
    "segment tree for range queries",
    "bit manipulation techniques and tricks",
    "Floyd-Warshall all-pairs shortest path",
    "A* pathfinding algorithm",
    "bloom filter implementation",
    "skip list data structure",
    "red-black tree properties and operations",
    "suffix array and suffix tree",

    # ===================================================================
    # DESIGN PATTERNS
    # ===================================================================
    "singleton pattern thread safety",
    "factory pattern and abstract factory",
    "observer pattern and event systems",
    "strategy pattern for algorithm selection",
    "decorator pattern vs Python decorators",
    "command pattern for undo/redo",
    "repository pattern for data access",
    "dependency injection patterns",
    "state machine implementation",
    "builder pattern for complex objects",
    "adapter and facade patterns",
    "proxy pattern and lazy loading",
    "flyweight pattern for memory optimization",
    "chain of responsibility pattern",
    "mediator pattern for decoupling",
    "template method pattern",
    "visitor pattern for extensible operations",
    "composite pattern for tree structures",

    # ===================================================================
    # SYSTEMS AND CONCURRENCY
    # ===================================================================
    "thread-safe data structures in Python",
    "multiprocessing vs threading vs asyncio",
    "connection pool implementation",
    "rate limiting algorithms (token bucket, leaky bucket)",
    "LRU cache implementation",
    "producer-consumer pattern",
    "circuit breaker pattern",
    "async queue and worker pool implementation",
    "pub/sub message broker pattern",
    "task scheduler with priority queues",
    "distributed locking patterns (Redis, database)",
    "retry with exponential backoff and jitter",
    "bulkhead pattern for fault isolation",
    "health check and readiness probe patterns",
    "consistent hashing for distributed systems",
    "leader election algorithms",
    "two-phase commit protocol",
    "saga pattern for distributed transactions",

    # ===================================================================
    # WEB AND APIS
    # ===================================================================
    "REST API design principles",
    "JWT authentication implementation",
    "SQL injection prevention",
    "database transaction management",
    "database index optimization",
    "N+1 query problem and eager loading",
    "caching strategies (cache-aside, write-through, write-behind)",
    "GraphQL schema design vs REST",
    "API versioning strategies",
    "cursor-based vs offset-based pagination",
    "WebSocket server implementation",
    "OAuth2 authorization code flow",
    "CSRF and XSS prevention",
    "API rate limiting implementation",
    "idempotent API design",
    "HTTP/2 and HTTP/3 differences",
    "content negotiation in APIs",
    "API gateway patterns",

    # ===================================================================
    # TESTING
    # ===================================================================
    "unit testing with pytest fixtures",
    "mocking and patching in Python tests",
    "property-based testing with hypothesis",
    "integration test patterns",
    "test-driven development (TDD) cycle",
    "parameterized tests and test matrices",
    "snapshot testing patterns",
    "performance benchmarking with pytest-benchmark",
    "contract testing between services",
    "mutation testing concepts",
    "test doubles: mocks vs stubs vs fakes vs spies",
    "testing async code in Python",

    # ===================================================================
    # DATABASE
    # ===================================================================
    "SQL window functions (ROW_NUMBER, LAG, LEAD, PARTITION BY)",
    "database normalization (1NF through BCNF)",
    "optimistic vs pessimistic locking",
    "database migration patterns and versioning",
    "query plan analysis and EXPLAIN",
    "composite indexes and covering indexes",
    "database sharding strategies",
    "ACID properties and isolation levels",
    "database triggers and stored procedures",
    "full-text search in databases",
    "time-series data storage patterns",

    # ===================================================================
    # JAVASCRIPT AND TYPESCRIPT
    # ===================================================================
    "JavaScript event loop and microtask queue",
    "JavaScript closures and lexical scoping",
    "JavaScript prototype chain and inheritance",
    "TypeScript generics and constraints",
    "TypeScript utility types (Partial, Required, Pick, Omit)",
    "TypeScript discriminated unions and exhaustive checks",
    "JavaScript Promise chaining vs async/await",
    "JavaScript module systems (CommonJS vs ESM)",
    "TypeScript decorators and metadata reflection",
    "JavaScript memory leaks and WeakMap/WeakSet",
    "JavaScript event delegation and bubbling",
    "TypeScript mapped types and conditional types",
    "JavaScript generators and async generators",
    "Node.js streams and backpressure",
    "JavaScript proxy and reflect API",

    # ===================================================================
    # SECURITY
    # ===================================================================
    "password hashing with bcrypt and Argon2",
    "cryptographic hash functions and HMAC",
    "secure random number generation",
    "input sanitization and output encoding",
    "secrets management and environment variables",
    "timing attack prevention in comparisons",
    "certificate pinning and TLS validation",
    "JWT security vulnerabilities and mitigations",

    # ===================================================================
    # DEVOPS AND TOOLING
    # ===================================================================
    "Dockerfile multi-stage builds",
    "Docker container health checks and restart policies",
    "environment-based configuration patterns (12-factor app)",
    "structured logging with JSON output",
    "distributed tracing concepts (OpenTelemetry)",
    "feature flag implementation patterns",
    "blue-green and canary deployment strategies",
    "git branching strategies (trunk-based vs gitflow)",

    # ===================================================================
    # DATA / ML CODING PATTERNS
    # ===================================================================
    "cosine similarity and vector operations",
    "inverted index for text search",
    "online algorithms and streaming data processing",
    "embedding similarity search patterns",
    "data pipeline design patterns (ETL vs ELT)",
    "batch vs streaming processing tradeoffs",
]


# ---------------------------------------------------------------------------
# REVIEW TEMPLATES — 3 deeper angles run by qwen3:32b in Phase 2.
# Intentionally different from the 6 base templates so they pass the dedup gate.
# ---------------------------------------------------------------------------
REVIEW_TEMPLATES = [
    (
        "production",
        "Design a production-ready implementation of {concept} in Python for a system "
        "serving 10,000+ requests per day. Address: reliability, error handling, retries, "
        "monitoring/metrics, graceful degradation, and horizontal scaling. "
        "What breaks under load that works fine in development? "
        "Show at least 3 complete code examples: naive implementation, production version, "
        "and the monitoring/observability layer. Explain every design decision.",
    ),
    (
        "debug",
        "You are on-call and {concept} is behaving unexpectedly in production. "
        "Walk through the full debugging process: what symptoms appear, what tools you reach for "
        "(logging, profiling, tracing, debuggers), what the top 5 failure modes are, "
        "and how to distinguish between them. "
        "Show at least 3 code examples: how to instrument the code, how to reproduce failures "
        "in isolation, and the fixes for the most common root causes.",
    ),
    (
        "optimize",
        "Profile and systematically optimize {concept} in Python. "
        "Start with a realistic baseline implementation, measure it with concrete benchmarks, "
        "identify the actual bottlenecks (not assumed ones), then apply optimizations one at a time "
        "showing measured improvement for each step. "
        "Show at least 4 code examples: baseline, profiling harness, each optimization, "
        "and final before/after comparison. What is the theoretical limit and why?",
    ),
    # --- o1-style deep reasoning templates (Phase 2 additions) ---
    (
        "reflect_revise",
        "I need to solve a complex problem involving {concept} in Python.\n\n"
        "Follow this exact reasoning process:\n"
        "**Step 1 — Initial Analysis**: Break down the problem. What are the core challenges?\n"
        "**Step 2 — First Attempt**: Write a complete initial solution with code.\n"
        "**Step 3 — Self-Critique**: Review your own solution critically. What are the flaws? "
        "What edge cases did you miss? What would break under load?\n"
        "**Step 4 — Revised Solution**: Write an improved version addressing every flaw. "
        "Explain each change.\n"
        "**Step 5 — Verification**: Prove correctness with test cases covering normal, edge, "
        "and error conditions.\n\n"
        "Show complete working code at each step.",
    ),
    (
        "adversarial",
        "You are reviewing a pull request that implements {concept} in Python.\n\n"
        "The implementation looks correct at first glance. Find the subtle issues:\n"
        "1. **Subtle bug #1**: The exact scenario where it fails + reproduction test case.\n"
        "2. **Subtle bug #2**: A different failure mode with triggering condition.\n"
        "3. **Performance trap**: Where does it degrade unexpectedly? Show a benchmark.\n"
        "4. **Design alternative**: A fundamentally better approach with complete code.\n\n"
        "Write realistic code — each bug should be something a senior engineer catches.",
    ),
    (
        "first_principles",
        "Explain {concept} by building it from absolute first principles.\n\n"
        "1. **The Problem**: Show a painful code example WITHOUT this concept.\n"
        "2. **The Insight**: The key 'aha moment' — explain with an analogy.\n"
        "3. **Build It**: Implement from scratch in 3-4 progressive examples.\n"
        "4. **Standard Library**: How Python provides this natively.\n"
        "5. **Expert Usage**: Production-quality example with error handling and types.\n"
        "6. **When NOT to Use It**: Show a case where it's the wrong tool.\n\n"
        "Every example must be complete and runnable.",
    ),
]

# ---------------------------------------------------------------------------
# ENHANCED SYSTEM PROMPTS — with chain-of-thought and self-critique
# ---------------------------------------------------------------------------
FAST_SYSTEM_PROMPT = (
    "You are an expert software engineer and computer science educator. "
    "Your answers must include working Python code, clear reasoning, "
    "and concrete examples. Be thorough but precise — no padding or filler.\n\n"
    "When writing code examples:\n"
    "- Every code block must be complete and runnable\n"
    "- Include error handling where appropriate\n"
    "- Show both the 'what' and the 'why'\n"
    "- If there's a common mistake, show it alongside the correct approach\n"
    "- Use type hints in production-quality examples\n\n"
    "Structure your response like this:\n"
    "## Core Concept\n"
    "Brief explanation of what this is and why it matters.\n\n"
    "## Example 1 — Basic Usage\n"
    "```python\n# complete, runnable code\n```\n"
    "Explain what this demonstrates and why it works.\n\n"
    "## Example 2 — Common Pitfall\n"
    "```python\n# the wrong way (with comment explaining the bug)\n```\n"
    "```python\n# the correct way\n```\n"
    "Why this matters in practice.\n\n"
    "## Example 3 — Production Pattern\n"
    "```python\n# production-quality with error handling + types\n```\n"
    "Key takeaway for practitioners."
)

DEEP_SYSTEM_PROMPT = (
    "You are a senior software engineer with 15+ years of production experience. "
    "Your answers go beyond textbook knowledge — address real-world failure modes, "
    "operational concerns, and hard-won lessons.\n\n"
    "Reasoning approach:\n"
    "- Think through the problem step by step before writing code\n"
    "- Consider what could go wrong in production (concurrency, scale, edge cases)\n"
    "- When you make a claim, back it up with code or a benchmark\n"
    "- Explicitly state your confidence level when discussing uncertain topics\n"
    "- After writing a solution, critique it yourself — then improve it\n\n"
    "Include working Python code with type hints and error handling.\n\n"
    "Structure your response with clear sections:\n"
    "## Analysis\n"
    "What's the core problem? What are the constraints?\n\n"
    "## Implementation\n"
    "```python\n# complete production code with types and error handling\n```\n\n"
    "## Why This Works\n"
    "Explain the design decisions — what alternatives were considered and why this approach wins.\n\n"
    "## What Could Go Wrong\n"
    "Edge cases, failure modes, and how to handle them.\n\n"
    "## Testing\n"
    "```python\n# test cases proving correctness\n```"
)

O1_SYSTEM_PROMPT = (
    "You are an expert AI reasoning engine. Your distinguishing capability is "
    "multi-step logical reasoning with explicit self-correction.\n\n"
    "Core principles:\n"
    "- Always show your reasoning chain — explain WHY before WHAT\n"
    "- When you write a solution, immediately critique it and find at least one flaw\n"
    "- After finding a flaw, write an improved version and explain the improvement\n"
    "- Rate your confidence on each claim: HIGH (documented), MEDIUM (generally true), LOW (uncertain)\n"
    "- If you catch yourself making an assumption, flag it explicitly\n"
    "- Every code example must be complete, runnable, and include at least one test case\n"
    "- Show the evolution of your thinking: naive → correct → production-ready\n\n"
    "Your responses should teach the reader HOW to think about problems, "
    "not just provide answers. The process of reasoning is as valuable as the conclusion."
)


def get_mined_topics(db) -> set:
    """Return set of topics already in training_pairs table."""
    from hiveai.models import TrainingPair
    rows = db.query(TrainingPair.topic).distinct().all()
    return {r[0] for r in rows}


def get_topic_pair_counts(db) -> dict:
    """Return {topic: count} for all mined topics."""
    from hiveai.models import TrainingPair
    from sqlalchemy import func
    rows = db.query(TrainingPair.topic, func.count(TrainingPair.id)).group_by(TrainingPair.topic).all()
    return {r[0]: r[1] for r in rows}


def print_status(db):
    """Print current mining status."""
    from hiveai.models import TrainingPair
    total = db.query(TrainingPair).count()
    eligible = db.query(TrainingPair).filter(TrainingPair.is_eligible == True).count()
    mined = get_mined_topics(db)
    remaining = [t for t in ALL_TOPICS if t not in mined]
    counts = get_topic_pair_counts(db)

    print(f"\n{'='*60}")
    print(f"BRAIN MINE STATUS")
    print(f"{'='*60}")
    print(f"Total pairs:    {total}")
    print(f"Eligible:       {eligible}")
    print(f"Topics mined:   {len(mined)} / {len(ALL_TOPICS)}")
    print(f"Topics left:    {len(remaining)}")
    print(f"{'='*60}")
    if mined:
        print("Already mined:")
        for t in sorted(mined):
            print(f"  [{counts.get(t, 0):2d} pairs] {t}")
    if remaining:
        print(f"\nRemaining ({len(remaining)}):")
        for t in remaining[:20]:
            print(f"  - {t}")
        if len(remaining) > 20:
            print(f"  ... and {len(remaining) - 20} more")
    print()


def _make_fast_call(prompt: str, max_tokens: int = 4096) -> str:
    """
    Direct Ollama call using qwen3:14b via NATIVE Ollama API (/api/chat).

    IMPORTANT: Uses "think": false in the request body to disable thinking.
    The /no_think text suffix does NOT work on native API — it silently generates
    thinking tokens that eat the entire token budget, returning empty content.

    - Thinking disabled via think:false — no think chain overhead
    - 600s timeout — native API is fast, generous for long answers
    - 3 retries with exponential backoff for transient failures
    """
    import requests as req
    from hiveai.config import OLLAMA_BASE_URL, OLLAMA_MODEL_FAST

    last_err = None
    for attempt in range(3):
        try:
            resp = req.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL_FAST,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "think": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": 0.2,
                    },
                },
                timeout=600,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            # Strip any residual think blocks just in case
            if "</think>" in content:
                content = content.split("</think>", 1)[1]
            return content.strip()
        except Exception as e:
            last_err = e
            wait = 10 * (attempt + 1)
            logger.warning(f"Fast call attempt {attempt+1}/3 failed: {e} — retrying in {wait}s")
            time.sleep(wait)
    raise last_err


def _make_deep_call(prompt: str, max_tokens: int = 8192, temperature: float = 0.3) -> str:
    """
    Direct Ollama call using qwen3:32b for Phase 2/3 deep review via NATIVE Ollama API.

    - Thinking ENABLED — 32b with thinking produces deep, production-quality answers
    - 7200s timeout (2 hours) — 32b thinking can take 20-40 min per response
    - Higher max_tokens (8192) — deep answers need room
    - 3 retries with exponential backoff for transient failures
    - Temperature: 0.3 for Phase 2 (factual depth), 0.35 for Phase 3 (diverse reasoning)
    """
    import requests as req
    from hiveai.config import OLLAMA_BASE_URL, OLLAMA_MODEL_REASONING

    last_err = None
    for attempt in range(3):
        try:
            resp = req.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL_REASONING,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "think": True,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                    },
                },
                timeout=7200,
            )
            resp.raise_for_status()
            data = resp.json()
            # Native API separates thinking into message.thinking, content is clean
            content = data.get("message", {}).get("content", "")
            # Fallback: strip think blocks if they leak into content
            if "</think>" in content:
                content = content.split("</think>", 1)[1]
            return content.strip()
        except Exception as e:
            last_err = e
            wait = 30 * (attempt + 1)
            logger.warning(f"Deep call attempt {attempt+1}/3 failed: {e} — retrying in {wait}s")
            time.sleep(wait)
    raise last_err


def _log_mining_analytics(template_stats, quality_distribution, total_gen, total_elig, start_time):
    """Log periodic analytics during mining."""
    elapsed = time.time() - start_time
    rate = total_gen / (elapsed / 60) if elapsed > 0 else 0
    elig_pct = (total_elig / total_gen * 100) if total_gen > 0 else 0

    logger.info(f"\n{'='*60}")
    logger.info(f"MINING ANALYTICS (after {elapsed/60:.1f} min)")
    logger.info(f"{'='*60}")
    logger.info(f"Total: {total_gen} generated, {total_elig} eligible ({elig_pct:.0f}%) | {rate:.1f} pairs/min")

    # Template effectiveness
    logger.info(f"\nTemplate effectiveness:")
    for tkey, stats in sorted(template_stats.items()):
        gen = stats["generated"]
        elig = stats["eligible"]
        avg_q = stats["total_quality"] / gen if gen > 0 else 0
        fail = stats["failures"]
        empty = stats["empty"]
        elig_pct = (elig / gen * 100) if gen > 0 else 0
        logger.info(
            f"  {tkey:20s}: {gen:3d} gen, {elig:3d} elig ({elig_pct:4.0f}%), "
            f"avg_q={avg_q:.2f}, {fail} fails, {empty} empty"
        )

    # Quality distribution
    if quality_distribution:
        import statistics
        logger.info(f"\nQuality distribution:")
        logger.info(f"  Mean:   {statistics.mean(quality_distribution):.3f}")
        logger.info(f"  Median: {statistics.median(quality_distribution):.3f}")
        logger.info(f"  Stdev:  {statistics.stdev(quality_distribution):.3f}" if len(quality_distribution) > 1 else "  Stdev:  n/a")
        logger.info(f"  Min:    {min(quality_distribution):.3f}")
        logger.info(f"  Max:    {max(quality_distribution):.3f}")

        # Histogram buckets
        buckets = {"0.0-0.3": 0, "0.3-0.5": 0, "0.5-0.7": 0, "0.7-0.8": 0, "0.8-0.9": 0, "0.9-1.0": 0}
        for q in quality_distribution:
            if q < 0.3: buckets["0.0-0.3"] += 1
            elif q < 0.5: buckets["0.3-0.5"] += 1
            elif q < 0.7: buckets["0.5-0.7"] += 1
            elif q < 0.8: buckets["0.7-0.8"] += 1
            elif q < 0.9: buckets["0.8-0.9"] += 1
            else: buckets["0.9-1.0"] += 1
        logger.info(f"  Histogram: {dict(buckets)}")
    logger.info(f"{'='*60}\n")


def _log_weak_topics(topic_stats):
    """Log topics that produced low-quality or few eligible pairs."""
    weak = [(t, s) for t, s in topic_stats.items() if s["eligible"] < 2 or s["avg_quality"] < 0.5]
    if weak:
        logger.info(f"\nWEAK TOPICS (low eligible or low quality):")
        for topic, stats in sorted(weak, key=lambda x: x[1]["avg_quality"]):
            logger.info(f"  [{stats['eligible']}/{stats['generated']} elig, q={stats['avg_quality']:.2f}] {topic}")
    else:
        logger.info("All topics produced good results!")


def run_mining(pairs_per_topic: int = 6, dry_run: bool = False, fast_mode: bool = False, workers: int = 3):
    """Phase 1 — mine all topics with concurrent template processing. Skips already-mined topics."""
    from hiveai.models import SessionLocal
    from hiveai.lora.distiller import TEMPLATES, _score_quality, _persist_pair
    from hiveai.config import MIN_TRAINING_QUALITY
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from collections import defaultdict

    if fast_mode:
        logger.info(f"FAST MODE: qwen3:14b + native Ollama API + think:false + {workers} workers")
    else:
        logger.info("DEEP MODE: qwen3:32b active")

    db = SessionLocal()
    try:
        mined = get_mined_topics(db)
        remaining = [t for t in ALL_TOPICS if t not in mined]

        logger.info(f"Phase 1 — {len(remaining)} topics remaining / {len(ALL_TOPICS)} total")
        logger.info(f"Templates per topic: {pairs_per_topic} | Workers: {workers}")
        logger.info(f"Estimated calls: {len(remaining) * pairs_per_topic} | ~{len(remaining) * pairs_per_topic * 50 / workers / 60:.0f} min")

        if dry_run:
            print(f"\nDRY RUN — would mine {len(remaining)} topics × {pairs_per_topic} templates")
            for t in remaining:
                print(f"  {t}")
            return

        if not remaining:
            logger.info("All topics already mined! Run --review for the deep pass, or --status to check.")
            return

        system_prompt = FAST_SYSTEM_PROMPT if fast_mode else DEEP_SYSTEM_PROMPT

        # --- Mining Analytics ---
        total_generated = 0
        total_eligible = 0
        start_time = time.time()
        call_fn = _make_fast_call if fast_mode else _make_deep_call

        # Analytics trackers
        template_stats = defaultdict(lambda: {"generated": 0, "eligible": 0, "total_quality": 0.0, "failures": 0, "empty": 0})
        quality_distribution = []
        topic_stats = defaultdict(lambda: {"generated": 0, "eligible": 0, "avg_quality": 0.0})

        for i, topic in enumerate(remaining, 1):
            logger.info(f"[{i}/{len(remaining)}] Mining: {topic}")
            t0 = time.time()

            # Build all template tasks for this topic
            template_cycle = TEMPLATES[:pairs_per_topic]
            tasks = []
            for template_key, template_text in template_cycle:
                instruction = template_text.format(concept=topic)
                full_prompt = f"{system_prompt}\n\n{instruction}"
                tasks.append((template_key, instruction, full_prompt))

            # Fire templates concurrently
            results = []
            try:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = {}
                    for template_key, instruction, full_prompt in tasks:
                        future = executor.submit(call_fn, full_prompt)
                        futures[future] = (template_key, instruction)

                    for future in as_completed(futures):
                        template_key, instruction = futures[future]
                        try:
                            response = future.result()
                            if not response or len(response.strip()) < 50:
                                logger.debug(f"  Empty/short response for {template_key}, skipping")
                                template_stats[template_key]["empty"] += 1
                                continue

                            quality = _score_quality(instruction, response.strip())
                            is_eligible = quality >= MIN_TRAINING_QUALITY

                            # Track analytics
                            template_stats[template_key]["generated"] += 1
                            template_stats[template_key]["total_quality"] += quality
                            if is_eligible:
                                template_stats[template_key]["eligible"] += 1
                            quality_distribution.append(quality)

                            results.append({
                                "source": "self_distill",
                                "topic": topic,
                                "instruction": instruction,
                                "response": response.strip(),
                                "quality": quality,
                                "is_eligible": is_eligible,
                            })
                        except Exception as e:
                            logger.warning(f"  Template '{template_key}' failed: {e}")
                            template_stats[template_key]["failures"] += 1

                # Persist all results (sequential — DB + dedup are not thread-safe)
                for pair in results:
                    _persist_pair(db, pair)

            except KeyboardInterrupt:
                logger.info("Interrupted. Progress saved — resume by running again.")
                break

            elapsed = time.time() - t0
            eligible = sum(1 for r in results if r.get("is_eligible"))
            total_generated += len(results)
            total_eligible += eligible
            rate = total_generated / ((time.time() - start_time) / 60) if time.time() > start_time else 0

            # Track per-topic stats
            topic_qualities = [r["quality"] for r in results]
            topic_stats[topic] = {
                "generated": len(results),
                "eligible": eligible,
                "avg_quality": round(sum(topic_qualities) / len(topic_qualities), 2) if topic_qualities else 0,
            }

            logger.info(
                f"  -> {len(results)} pairs ({eligible} eligible) in {elapsed:.1f}s | "
                f"Total: {total_generated} ({total_eligible} eligible) | {rate:.1f} pairs/min"
            )

            # Periodic analytics report every 10 topics
            if i % 10 == 0:
                _log_mining_analytics(template_stats, quality_distribution, total_generated, total_eligible, start_time)

        # --- Final Analytics Report ---
        elapsed_total = time.time() - start_time
        logger.info(
            f"Phase 1 complete: {total_generated} pairs ({total_eligible} eligible) in {elapsed_total/60:.1f} min. "
            f"Next: run --review for the deep pass."
        )
        _log_mining_analytics(template_stats, quality_distribution, total_generated, total_eligible, start_time)
        _log_weak_topics(topic_stats)

    finally:
        db.close()


def run_review(dry_run: bool = False, workers: int = 1):
    """Phase 2 — run 6 deeper templates with qwen3:32b on topics already mined in Phase 1."""
    from hiveai.models import SessionLocal, TrainingPair
    from hiveai.lora.distiller import _score_quality, _persist_pair
    from concurrent.futures import ThreadPoolExecutor, as_completed

    import random

    # Max total self_distill pairs per topic across ALL phases.
    # Phase 1 adds ~6, Phase 2 adds up to 6 more, Phase 3 up to 3.
    # Cap prevents diminishing returns on over-represented topics.
    MAX_PAIRS_PER_TOPIC = 10

    db = SessionLocal()
    try:
        mined = get_mined_topics(db)
        to_review = [t for t in ALL_TOPICS if t in mined]

        # Count existing pairs per topic (fast single query)
        topic_counts = get_topic_pair_counts(db)

        # Build instruction set for per-template dedup (avoid exact dupes)
        review_instructions = set()
        existing = db.query(TrainingPair.instruction).all()
        for (instr,) in existing:
            review_instructions.add(instr.strip())

        # Skip topics that hit the per-topic cap
        already_reviewed = set()
        for topic in to_review:
            existing_count = topic_counts.get(topic, 0)
            if existing_count >= MAX_PAIRS_PER_TOPIC:
                already_reviewed.add(topic)
                continue
            # Also skip if all review templates already generated
            done_count = sum(
                1 for _, tmpl in REVIEW_TEMPLATES
                if tmpl.format(concept=topic).strip() in review_instructions
            )
            if done_count >= len(REVIEW_TEMPLATES):
                already_reviewed.add(topic)

        remaining_review = [t for t in to_review if t not in already_reviewed]

        # Shuffle to avoid restart bias (early topics always processed first)
        random.shuffle(remaining_review)

        logger.info(f"Phase 2 Review — {len(remaining_review)} topics to deep-review")
        logger.info(f"DEEP MODE: qwen3:32b + thinking enabled | {workers} workers")
        logger.info(f"Using {len(REVIEW_TEMPLATES)} deep templates each (per-topic cap: {MAX_PAIRS_PER_TOPIC})")
        logger.info(f"Estimated calls: {len(remaining_review) * len(REVIEW_TEMPLATES)}")

        if dry_run:
            print(f"\nDRY RUN — would deep-review {len(remaining_review)} topics × {len(REVIEW_TEMPLATES)} templates")
            for t in remaining_review:
                print(f"  {t}")
            return

        if not remaining_review:
            logger.info("All topics already deep-reviewed. Mining is complete!")
            return

        system_prompt = DEEP_SYSTEM_PROMPT
        total_generated = 0
        start_time = time.time()

        for i, topic in enumerate(remaining_review, 1):
            logger.info(f"[Review {i}/{len(remaining_review)}] Deep mining: {topic}")
            t0 = time.time()

            # Build tasks for this topic (skip already-done templates, respect cap)
            current_count = topic_counts.get(topic, 0)
            remaining_slots = MAX_PAIRS_PER_TOPIC - current_count
            tasks = []
            for template_key, template_text in REVIEW_TEMPLATES:
                if len(tasks) >= remaining_slots:
                    break  # Hit per-topic cap
                instruction = template_text.format(concept=topic)
                if instruction.strip() not in review_instructions:
                    tasks.append((template_key, instruction, f"{system_prompt}\n\n{instruction}"))

            if not tasks:
                logger.info(f"  Skipping {topic} — already at cap ({current_count}/{MAX_PAIRS_PER_TOPIC})")
                continue

            # Fire templates concurrently with worker pool
            results = []
            try:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = {}
                    for template_key, instruction, full_prompt in tasks:
                        future = executor.submit(_make_deep_call, full_prompt, 8192, 0.3)
                        futures[future] = (template_key, instruction)

                    for future in as_completed(futures):
                        template_key, instruction = futures[future]
                        try:
                            response = future.result()
                            if not response or len(response.strip()) < 50:
                                logger.info(f"  [{template_key}] Empty/short response, skipping")
                                continue
                            from hiveai.config import MIN_TRAINING_QUALITY
                            quality = _score_quality(instruction, response.strip())
                            logger.info(f"  [{template_key}] q={quality:.3f} len={len(response)} chars")
                            results.append({
                                "source": "self_distill",
                                "topic": topic,
                                "instruction": instruction,
                                "response": response.strip(),
                                "quality": quality,
                                "is_eligible": quality >= MIN_TRAINING_QUALITY,
                            })
                        except Exception as e:
                            logger.warning(f"  Template '{template_key}' failed: {e}")

                # Persist sequentially (DB + dedup not thread-safe)
                elapsed_topic = time.time() - t0
                logger.info(f"  Topic done: {len(results)} pairs in {elapsed_topic:.0f}s")
                for pair in results:
                    try:
                        _persist_pair(db, pair)
                        review_instructions.add(pair["instruction"].strip())
                    except Exception as e:
                        logger.error(f"  Failed to persist pair: {e}")

            except KeyboardInterrupt:
                logger.info("Interrupted. Progress saved — resume with --review.")
                break

            total_generated += len(results)
            elapsed = time.time() - t0
            logger.info(f"  -> {len(results)} review pairs in {elapsed:.1f}s | Total: {total_generated}")

        elapsed_total = time.time() - start_time
        logger.info(
            f"Phase 2 complete: {total_generated} deep pairs in {elapsed_total/60:.1f} min."
        )

    finally:
        db.close()


def run_upgrade(dry_run: bool = False, workers: int = 1, target_quality: float = 0.70):
    """
    Upgrade Mode — re-mine C-grade pairs (<0.70) with qwen3:32b to raise quality.

    Instead of discarding low-quality pairs, regenerate their responses using
    the 32b reasoning model. If the new response scores higher, update the pair
    in-place. This converts C-grade waste into B/A-grade training data.
    """
    from hiveai.models import SessionLocal, TrainingPair
    from hiveai.lora.distiller import _score_quality, _clean_response

    db = SessionLocal()
    try:
        # Find all pairs below target quality, ordered by quality (worst first)
        c_pairs = (
            db.query(TrainingPair)
            .filter(TrainingPair.quality < target_quality)
            .filter(TrainingPair.quality >= 0.40)  # Skip truly broken pairs
            .order_by(TrainingPair.quality.asc())
            .all()
        )

        logger.info(f"Upgrade Mode — {len(c_pairs)} pairs below q={target_quality}")
        logger.info(f"Using qwen3:32b + thinking to regenerate responses")

        if dry_run:
            print(f"\nDRY RUN — would upgrade {len(c_pairs)} pairs:")
            for p in c_pairs[:30]:
                print(f"  [{p.quality:.2f}] {p.topic} | {p.instruction[:80]}...")
            if len(c_pairs) > 30:
                print(f"  ... and {len(c_pairs) - 30} more")
            return

        if not c_pairs:
            logger.info("No pairs below target quality. Nothing to upgrade!")
            return

        system_prompt = DEEP_SYSTEM_PROMPT
        upgraded = 0
        failed = 0
        skipped = 0
        start_time = time.time()

        for i, pair in enumerate(c_pairs, 1):
            logger.info(f"[Upgrade {i}/{len(c_pairs)}] q={pair.quality:.2f} | {pair.topic}")

            full_prompt = f"{system_prompt}\n\n{pair.instruction}"

            try:
                new_response = _make_deep_call(full_prompt, 8192, 0.3)
                if not new_response or len(new_response.strip()) < 50:
                    logger.info(f"  Empty/short response, skipping")
                    skipped += 1
                    continue

                new_quality = _score_quality(pair.instruction, new_response.strip())
                old_quality = pair.quality

                if new_quality > old_quality:
                    # Upgrade the pair in-place
                    pair.response = _clean_response(new_response.strip())
                    pair.quality = new_quality
                    pair.is_eligible = new_quality >= 0.55
                    db.commit()
                    grade = 'A' if new_quality >= 0.85 else 'B' if new_quality >= 0.70 else 'C'
                    logger.info(f"  UPGRADED: {old_quality:.2f} -> {new_quality:.2f} [{grade}]")
                    upgraded += 1
                else:
                    logger.info(f"  No improvement: {old_quality:.2f} -> {new_quality:.2f}, keeping original")
                    skipped += 1

            except KeyboardInterrupt:
                logger.info(f"Interrupted. Upgraded {upgraded} pairs so far.")
                break
            except Exception as e:
                logger.warning(f"  Failed: {e}")
                failed += 1

        elapsed = time.time() - start_time
        logger.info(
            f"Upgrade complete: {upgraded} upgraded, {skipped} skipped, "
            f"{failed} failed in {elapsed/60:.1f} min"
        )

    finally:
        db.close()


def run_o1(dry_run: bool = False, workers: int = 1):
    """
    Phase 3 — run o1-style reasoning templates with qwen3:32b.

    Uses only the 3 UNIQUE o1 templates (debug_reasoning, system_design,
    confidence_analysis). The other 3 (reflect, adversarial, first_principles)
    overlap with Phase 2's REVIEW_TEMPLATES and would be rejected by dedup.
    """
    from hiveai.models import SessionLocal, TrainingPair
    from hiveai.lora.distiller import O1_TEMPLATES, _score_quality, _persist_pair
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Only use o1 templates that DON'T overlap with Phase 2 review templates
    # Phase 2 already covers: reflect_revise, adversarial, first_principles
    # Phase 3 unique: debug_reasoning, system_design, confidence_analysis
    UNIQUE_O1_KEYS = {"debug_reasoning", "system_design", "confidence_analysis"}
    o1_templates = [(k, t) for k, t in O1_TEMPLATES if k in UNIQUE_O1_KEYS]

    import random

    MAX_PAIRS_PER_TOPIC = 10  # Same cap as Phase 2

    db = SessionLocal()
    try:
        mined = get_mined_topics(db)
        to_process = [t for t in ALL_TOPICS if t in mined]

        # Count existing pairs per topic
        topic_counts = get_topic_pair_counts(db)

        already_done = set()
        existing_instructions = set()
        existing = db.query(TrainingPair.instruction).all()
        for (instr,) in existing:
            existing_instructions.add(instr.strip())

        for topic in to_process:
            # Skip if per-topic cap reached
            if topic_counts.get(topic, 0) >= MAX_PAIRS_PER_TOPIC:
                already_done.add(topic)
                continue
            done_count = sum(
                1 for _, tmpl in o1_templates
                if tmpl.format(concept=topic).strip() in existing_instructions
            )
            if done_count >= len(o1_templates):
                already_done.add(topic)

        remaining = [t for t in to_process if t not in already_done]

        # Shuffle to avoid restart bias
        random.shuffle(remaining)

        logger.info(f"Phase 3 o1-Reasoning — {len(remaining)} topics to process")
        logger.info(f"DEEP MODE: qwen3:32b + thinking + o1 prompts | {workers} workers")
        logger.info(f"Using {len(o1_templates)} unique o1 templates (per-topic cap: {MAX_PAIRS_PER_TOPIC})")
        logger.info(f"Estimated calls: {len(remaining) * len(o1_templates)}")

        if dry_run:
            print(f"\nDRY RUN — would o1-mine {len(remaining)} topics x {len(o1_templates)} templates")
            for t in remaining:
                print(f"  {t}")
            return

        if not remaining:
            logger.info("All topics already have o1 pairs. Phase 3 is complete!")
            return

        system_prompt = O1_SYSTEM_PROMPT
        total_generated = 0
        start_time = time.time()

        for i, topic in enumerate(remaining, 1):
            logger.info(f"[o1 {i}/{len(remaining)}] Reasoning mining: {topic}")
            t0 = time.time()

            # Build tasks for this topic
            tasks = []
            for template_key, template_text in o1_templates:
                instruction = template_text.format(concept=topic)
                if instruction.strip() not in existing_instructions:
                    tasks.append((template_key, instruction, f"{system_prompt}\n\n{instruction}"))

            if not tasks:
                continue

            # Fire templates concurrently
            results = []
            try:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = {}
                    for template_key, instruction, full_prompt in tasks:
                        future = executor.submit(_make_deep_call, full_prompt, 8192, 0.35)
                        futures[future] = (template_key, instruction)

                    for future in as_completed(futures):
                        template_key, instruction = futures[future]
                        try:
                            response = future.result()
                            if not response or len(response.strip()) < 50:
                                continue
                            from hiveai.config import MIN_TRAINING_QUALITY
                            quality = _score_quality(instruction, response.strip())
                            results.append({
                                "source": "self_distill",
                                "topic": topic,
                                "instruction": instruction,
                                "response": response.strip(),
                                "quality": quality,
                                "is_eligible": quality >= MIN_TRAINING_QUALITY,
                            })
                        except Exception as e:
                            logger.warning(f"  Template '{template_key}' failed: {e}")

                # Persist sequentially
                for pair in results:
                    _persist_pair(db, pair)
                    existing_instructions.add(pair["instruction"].strip())

            except KeyboardInterrupt:
                logger.info("Interrupted. Progress saved — resume with --o1.")
                break

            total_generated += len(results)
            elapsed = time.time() - t0
            logger.info(f"  -> {len(results)} o1 pairs in {elapsed:.1f}s | Total: {total_generated}")

        elapsed_total = time.time() - start_time
        logger.info(
            f"Phase 3 complete: {total_generated} o1-reasoning pairs in {elapsed_total/60:.1f} min. "
            f"Full brain extraction finished!"
        )

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="HiveAI Brain Miner — extract Qwen3 coding knowledge into training pairs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/brain_mine.py --fast            # Phase 1: qwen3:14b, all topics (~18-36h)
  python scripts/brain_mine.py --review          # Phase 2: qwen3:32b, deep templates (~3-4 days)
  python scripts/brain_mine.py --o1              # Phase 3: qwen3:32b, o1-style reasoning
  python scripts/brain_mine.py --upgrade         # Upgrade C-grade pairs with qwen3:32b
  python scripts/brain_mine.py --status          # Show current progress
  python scripts/brain_mine.py --fast --dry-run  # Preview without running

  # Full pipeline (auto-chains all 3 phases):
  python scripts/brain_mine.py --fast --workers 2 && python scripts/brain_mine.py --review && python scripts/brain_mine.py --o1
        """
    )
    parser.add_argument("--fast", action="store_true",
                        help="Phase 1: use qwen3:14b (4x faster, fits fully in VRAM)")
    parser.add_argument("--review", action="store_true",
                        help="Phase 2: deep review with qwen3:32b using 6 deep templates")
    parser.add_argument("--o1", action="store_true",
                        help="Phase 3: o1-style reasoning with qwen3:32b (teaches HOW to think)")
    parser.add_argument("--upgrade", action="store_true",
                        help="Upgrade C-grade pairs (<0.70) by re-mining with qwen3:32b")
    parser.add_argument("--pairs", type=int, default=6,
                        help="Templates per topic for Phase 1 (1-6, default 6)")
    parser.add_argument("--workers", type=int, default=1,
                        help="Concurrent LLM calls per topic (default 1; set higher with OLLAMA_NUM_PARALLEL)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be mined without running")
    parser.add_argument("--status", action="store_true",
                        help="Show current DB mining status and exit")
    args = parser.parse_args()

    if args.status:
        from hiveai.models import SessionLocal
        db = SessionLocal()
        try:
            print_status(db)
        finally:
            db.close()
        return

    if args.upgrade:
        logger.info("Upgrade Mode — re-mining C-grade pairs with qwen3:32b")
        run_upgrade(dry_run=args.dry_run, workers=args.workers)
    elif args.o1:
        logger.info("Phase 3 — o1-Reasoning | qwen3:32b | 3 unique o1-style reasoning templates")
        run_o1(dry_run=args.dry_run, workers=args.workers)
    elif args.review:
        logger.info("Phase 2 — Deep Review | qwen3:32b | 6 production/debug/optimize/reflect templates")
        run_review(dry_run=args.dry_run, workers=args.workers)
    else:
        pairs = max(1, min(6, args.pairs))
        model_label = "qwen3:14b (fast)" if args.fast else "qwen3:32b (deep)"
        logger.info(f"Phase 1 — Brain Mine | model={model_label} | topics={len(ALL_TOPICS)} | pairs_per_topic={pairs}")
        run_mining(pairs_per_topic=pairs, dry_run=args.dry_run, fast_mode=args.fast, workers=args.workers)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"FATAL: brain_mine.py crashed: {e}", exc_info=True)
        raise
