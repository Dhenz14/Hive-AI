"""
scripts/distill_supervisor.py

10-hour automated distillation supervisor.
- Mines new training pairs (quality >= 0.75) using qwen3:14b
- Uses 200 extended topics not yet in the DB (beyond Phase 1's 187 topics)
- Every 30 min: full quality report + diminishing-returns check
- Every 10 min: download watcher — auto-launches train_v2.py when ready
- Saves progress and is resume-safe

Run:
    python scripts/distill_supervisor.py

Flags:
    --hours N       Run for N hours (default 10)
    --workers N     Concurrent Ollama workers (default 3)
    --status        Show current DB stats and topic coverage, then exit
"""

import argparse
import json
import logging
import os
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

log_path = PROJECT_ROOT / "logs" / "distill_supervisor.log"
log_path.parent.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_path), encoding="utf-8"),
    ],
)
logger = logging.getLogger("supervisor")

# ---------------------------------------------------------------------------
# Download paths — we watch these for completion
# ---------------------------------------------------------------------------
MODELS_DIR = PROJECT_ROOT / "models" / "qwen3.5-35b-a3b"
HF_DOWNLOAD_DIR = MODELS_DIR / "hf" / ".cache" / "huggingface" / "download"
HF_FINAL_DIR = MODELS_DIR / "hf"
GGUF_DOWNLOAD_DIR = MODELS_DIR / ".cache" / "huggingface" / "download"
GGUF_FINAL_PATTERN = MODELS_DIR / "*.gguf"
TRAIN_SCRIPT = PROJECT_ROOT / "scripts" / "train_v2.py"

# Expected shard count for training model
EXPECTED_SHARDS = 14

# ---------------------------------------------------------------------------
# Extended topic list — ~200 NEW high-value topics beyond Phase 1's 187
# Focus: deeper Python, ML/AI coding, system design, blockchain, performance
# ---------------------------------------------------------------------------
EXTENDED_TOPICS = [
    # ---- Python: advanced internals not in Phase 1 ----
    "Python __slots__ memory layout and descriptor protocol interaction",
    "Python frame objects and code objects internals",
    "Python tracemalloc and memory leak detection",
    "Python reference counting and cyclic garbage collector",
    "Python C extension modules with ctypes vs cffi vs Cython",
    "Python __class_getitem__ and PEP 560 generics",
    "Python ParamSpec and TypeVarTuple for advanced typing",
    "Python Protocols vs ABCs: structural vs nominal subtyping",
    "Python dataclass fields with init=False and post_init",
    "Python __init_subclass__ for plugin registration systems",
    "Python __set_name__ descriptor method and its use cases",
    "Python functools.partial vs lambda vs class-based callables",
    "Python operator module and functional programming patterns",
    "Python heapq for priority queue and top-k problems",
    "Python bisect module for sorted list operations",
    "Python array module vs list vs numpy for numeric data",
    "Python io module: BytesIO, StringIO, BufferedReader internals",
    "Python pickle security vulnerabilities and safe alternatives",
    "Python shelve and dbm for simple persistence",
    "Python mmap for memory-mapped file access",
    "Python signal handling and graceful shutdown patterns",
    "Python atexit handlers and cleanup on exit",
    "Python sys.settrace and coverage tool internals",
    "Python ast module for code analysis and transformation",
    "Python tokenize module for source code lexing",
    "Python importlib for dynamic module loading and reloading",
    "Python zipimport and loading code from zip archives",
    "Python __future__ imports and their effect on compilation",
    "Python compile() eval() exec() and code injection risks",
    "Python __debug__ flag and assert statement removal",

    # ---- Async / Concurrency deep dive ----
    "Python asyncio.gather vs asyncio.TaskGroup vs asyncio.wait",
    "Python asyncio cancellation and CancelledError handling",
    "Python asyncio.Semaphore for rate limiting async tasks",
    "Python asyncio.Queue for producer-consumer async patterns",
    "Python asyncio.Lock vs asyncio.Event vs asyncio.Condition",
    "Python aiofiles for async file I/O",
    "Python asyncio streams for TCP server/client",
    "Python asyncio subprocesses with asyncio.create_subprocess_exec",
    "Python contextvars for async context propagation",
    "Python thread-local storage vs contextvars comparison",
    "Python concurrent.futures ProcessPoolExecutor with shared memory",
    "Python GIL bypass: using multiprocessing.shared_memory",
    "Python numba JIT compilation for numerical code",
    "Python Cython typed memoryviews for zero-copy data",

    # ---- Data structures and algorithms: advanced ----
    "Fibonacci heap and decrease-key operation",
    "van Emde Boas tree for integer key operations",
    "persistent data structures and immutable trees",
    "lock-free data structures with compare-and-swap",
    "probabilistic data structures: HyperLogLog, Count-Min Sketch",
    "rope data structure for efficient string manipulation",
    "wavelet tree for range frequency queries",
    "link-cut tree for dynamic tree connectivity",
    "external memory algorithms for large datasets",
    "cache-oblivious algorithms and B-trees",
    "approximation algorithms: vertex cover, set cover",
    "online learning algorithms: Follow-The-Leader, Hedge",
    "randomized algorithms: reservoir sampling, random projections",
    "geometric algorithms: convex hull, closest pair of points",

    # ---- ML/AI implementation patterns ----
    "implementing attention mechanism from scratch in Python",
    "implementing backpropagation from scratch (no framework)",
    "softmax, cross-entropy, and numerical stability tricks",
    "batch normalization vs layer normalization implementation",
    "implementing dropout and its inference-time behavior",
    "gradient clipping: norm clipping vs value clipping",
    "learning rate schedulers: cosine annealing with warm restarts",
    "implementing Adam optimizer from scratch",
    "weight initialization: Xavier, Kaiming, orthogonal",
    "implementing KV cache for transformer inference",
    "beam search and top-k/top-p sampling for text generation",
    "implementing a tokenizer: BPE from scratch",
    "vector quantization and codebook learning",
    "contrastive learning: SimCLR and InfoNCE loss",
    "knowledge distillation: teacher-student training",
    "LoRA: low-rank adaptation mathematical foundations",
    "quantization: INT8 and INT4 inference techniques",
    "RLHF: reward modeling and PPO training pipeline",
    "RAG: retrieval-augmented generation architecture",
    "embeddings: cosine similarity search with FAISS",
    "semantic chunking strategies for document processing",
    "token budget management in LLM applications",
    "LLM output structured parsing with JSON schema validation",
    "LLM streaming and server-sent events implementation",
    "function calling / tool use implementation patterns",
    "prompt injection attacks and defense strategies",
    "LLM caching: semantic cache with embedding similarity",
    "multi-modal embeddings: CLIP and vision-language models",
    "speculative decoding for faster inference",

    # ---- Blockchain / Web3 coding patterns ----
    "Hive blockchain JSON-RPC API: account history queries",
    "Hive blockchain: VESTS to HP conversion calculations",
    "Hive blockchain: custom_json operation broadcasting",
    "Hive blockchain: streaming blocks with condenser_api",
    "Ethereum EVM: gas estimation and transaction building",
    "Solidity reentrancy attacks and checks-effects-interactions pattern",
    "ERC-20 token contract implementation and safeTransfer",
    "IPFS content addressing and pinning strategies",
    "Merkle tree construction and proof verification",
    "elliptic curve cryptography: secp256k1 key operations",
    "BIP-39 mnemonic generation and HD wallet derivation",
    "zero-knowledge proof concepts: zk-SNARKs introduction",
    "Uniswap v3 concentrated liquidity math",
    "blockchain event log indexing and processing",
    "multi-signature wallet implementation patterns",

    # ---- Database: advanced patterns ----
    "PostgreSQL EXPLAIN ANALYZE output interpretation",
    "PostgreSQL partial indexes and expression indexes",
    "PostgreSQL JSONB operators and GIN index usage",
    "PostgreSQL table partitioning: range, list, hash",
    "PostgreSQL row-level security and policy definitions",
    "PostgreSQL LISTEN/NOTIFY for real-time events",
    "PostgreSQL CTEs (WITH queries): recursive and materialized",
    "PostgreSQL advisory locks for application-level locking",
    "SQLAlchemy Core vs ORM: when to use which",
    "SQLAlchemy relationship loading: lazy, eager, joined, subquery",
    "SQLAlchemy bulk inserts with performance comparison",
    "database connection pooling: PgBouncer configuration",
    "TimescaleDB hypertables for time-series data",
    "pgvector extension for vector similarity search",
    "Redis data structures: sorted sets, streams, HyperLogLog",
    "Redis pub/sub vs Redis Streams for message queue",
    "Redis Lua scripting for atomic operations",
    "MongoDB aggregation pipeline: group, lookup, unwind",
    "ClickHouse columnar storage for analytics queries",

    # ---- Performance engineering ----
    "Python performance profiling: py-spy for production",
    "Python memory profiling: objgraph and memory_profiler",
    "Python benchmarking: timeit vs pytest-benchmark",
    "SIMD operations: using numpy for vectorized computation",
    "cache-line-aware data layout in Python structures",
    "Python string interning and id() for deduplication",
    "lazy evaluation patterns for expensive computations",
    "connection pooling patterns for HTTP clients",
    "HTTP/2 multiplexing with httpx async client",
    "gzip vs zstd vs lz4: compression tradeoffs for APIs",
    "Protocol Buffers vs MessagePack vs JSON performance",
    "zero-copy data transfer with memoryview",
    "profiling async Python: aiomonitor and asyncio debug mode",

    # ---- Cloud-native and DevOps patterns ----
    "Kubernetes pod disruption budgets and rolling updates",
    "Kubernetes resource requests vs limits: QoS classes",
    "Prometheus metrics: counter, gauge, histogram, summary",
    "OpenTelemetry trace propagation across service boundaries",
    "circuit breaker with tenacity library in Python",
    "Kafka consumer groups and partition rebalancing",
    "event-driven architecture: outbox pattern for reliability",
    "CQRS command query responsibility segregation",
    "event sourcing: storing state as event log",
    "graceful shutdown: SIGTERM handling and in-flight requests",
    "12-factor app: configuration via environment variables",
    "secrets injection: Vault vs Kubernetes secrets vs env vars",
    "container image layer caching for faster builds",
    "health check patterns: liveness vs readiness vs startup probes",

    # ---- Security: applied patterns ----
    "Python cryptography library: AES-GCM encryption",
    "Python secrets module: generating cryptographically secure tokens",
    "PBKDF2 vs bcrypt vs Argon2: password hashing comparison",
    "JWT RS256 vs HS256: asymmetric vs symmetric signing",
    "OAuth2 PKCE flow for single-page applications",
    "SSRF prevention: URL validation and DNS rebinding",
    "path traversal attacks and mitigation in file servers",
    "XML external entity (XXE) attacks in Python parsers",
    "deserialization vulnerabilities: pickle, PyYAML safe_load",
    "timing-safe comparison with hmac.compare_digest",
    "rate limiting with sliding window log algorithm",
    "API key rotation patterns and zero-downtime key migration",

    # ---- Real-world system design ----
    "designing a distributed task queue (Celery architecture)",
    "designing a rate limiter service at scale",
    "designing a notification service: fanout patterns",
    "designing a URL shortener: encoding and collision handling",
    "designing a search autocomplete system with tries",
    "designing a news feed algorithm: ranking and personalization",
    "designing a distributed cache invalidation strategy",
    "designing a webhook delivery system with retry logic",
    "designing a file upload service: chunked upload and resumability",
    "designing a real-time leaderboard with Redis sorted sets",
    "designing an API gateway: authentication and routing",
    "designing a distributed ID generator (Snowflake algorithm)",
    "designing a metrics aggregation pipeline",
    "designing a recommendation engine: collaborative filtering",
    "designing a multi-tenant SaaS: data isolation strategies",

    # ---- Testing: advanced ----
    "testing with Docker containers: testcontainers-python",
    "pytest-asyncio: testing async code patterns",
    "pytest fixtures: factory pattern and parametrize advanced usage",
    "chaos engineering: fault injection in Python services",
    "fuzzing Python code with atheris",
    "load testing with locust: scenarios and assertions",
    "database testing: transactional rollback fixtures",
    "contract testing with Pact for microservices",
    "golden file testing for deterministic outputs",
    "test pyramid: unit vs integration vs e2e cost tradeoffs",
]


# ---------------------------------------------------------------------------
# Templates ranked by measured acceptance rate (system_design=100%, reflect_revise=73%).
# Dropped: why_exists (0%), compare (5%), correct_way (10%), internals (10%) — wasted 94% of calls.
# ---------------------------------------------------------------------------
TEMPLATES = [
    ("system_design", "Design a production system that relies heavily on {concept}. Requirements: 10,000 requests/day, must handle failures gracefully, maintained by a team of 3 developers.\n\n1. **Context**: What problem are we solving? What constraints matter?\n2. **Options Considered**: 3 approaches with pros/cons.\n3. **Decision**: Which approach and WHY?\n4. **Implementation**: Complete working code including error handling, retry logic, monitoring hooks, configuration management.\n5. **Testing Strategy**: Unit tests, integration tests, and a load test sketch.\n6. **Operational Runbook**: Common failure modes and diagnosis.\n\nShow at least 5 code examples."),
    ("reflect_revise", "I need to solve a complex problem involving {concept} in Python.\n\n**Step 1 — Initial Analysis**: Break down the problem. What are the core challenges?\n**Step 2 — First Attempt**: Write a complete initial solution with code.\n**Step 3 — Self-Critique**: Review your own solution critically. What are the flaws? What edge cases did you miss? What would break under load?\n**Step 4 — Revised Solution**: Write an improved version addressing every flaw. Explain each change.\n**Step 5 — Verification**: Prove correctness with test cases covering normal, edge, and error conditions.\n\nShow complete working code at each step. The revision must be meaningfully better than the first attempt."),
    ("mistakes", "What are the top 5 mistakes developers make with {concept}? For each mistake: show the wrong code, show the correct code, explain why it matters, and describe what symptom or bug the wrong code causes in production."),
    ("implement", "Implement {concept} in Python. Show the complete approach, explain the reasoning step by step, cover edge cases, and include at least 3 working code examples ranging from basic to production-ready."),
]

SYSTEM_PROMPT = (
    "You are an expert software engineer and computer science educator. "
    "Your answers must include working Python code, clear reasoning, "
    "and concrete examples. Be thorough but precise — no padding or filler.\n\n"
    "When writing code examples:\n"
    "- Every code block must be complete and runnable\n"
    "- Include error handling where appropriate\n"
    "- Show both the 'what' and the 'why'\n"
    "- If there's a common mistake, show it alongside the correct approach\n"
    "- Use type hints in production-quality examples\n\n"
    "Structure your response with clear headers (##), multiple code blocks, "
    "and end with a key takeaway for practitioners."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_fast_call(prompt: str, max_tokens: int = 2048) -> str:
    """Direct Ollama call — qwen3:14b, think:false, 3 retries.
    2048 tokens is plenty — avg response is ~900 tokens, quality doesn't improve past 2k."""
    import requests
    from hiveai.config import OLLAMA_BASE_URL, OLLAMA_MODEL_FAST
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL_FAST,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "think": False,
                    "options": {"num_predict": max_tokens, "temperature": 0.25},
                },
                timeout=300,
            )
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "")
            if "</think>" in content:
                content = content.split("</think>", 1)[1]
            return content.strip()
        except Exception as e:
            last_err = e
            wait = 15 * (attempt + 1)
            logger.warning(f"Ollama attempt {attempt+1}/3 failed: {e} — retry in {wait}s")
            time.sleep(wait)
    raise last_err


def get_existing_topics(db) -> set:
    from hiveai.models import TrainingPair
    rows = db.query(TrainingPair.topic).distinct().all()
    return {r[0] for r in rows if r[0]}


# Template detection prefixes — used to figure out which templates a topic already has
TEMPLATE_PREFIXES = {
    "system_design": "Design a production system that relies heavily on",
    "reflect_revise": "I need to solve a complex problem involving",
    "mistakes": "What are the top 5 mistakes developers make with",
    "implement": "Implement",
}


def get_used_template_combos(db) -> dict[str, set[str]]:
    """Return {topic: {template_key, ...}} for all existing pairs."""
    from hiveai.models import TrainingPair
    rows = db.query(TrainingPair.topic, TrainingPair.instruction).all()
    combos: dict[str, set[str]] = {}
    for topic, instruction in rows:
        if not topic or not instruction:
            continue
        if topic not in combos:
            combos[topic] = set()
        for tkey, prefix in TEMPLATE_PREFIXES.items():
            if instruction.startswith(prefix):
                combos[topic].add(tkey)
                break
    return combos


def get_high_quality_count(db) -> int:
    from hiveai.models import TrainingPair
    return db.query(TrainingPair).filter(
        TrainingPair.quality >= 0.75,
        TrainingPair.is_eligible == True,
    ).count()


# ---------------------------------------------------------------------------
# Download watcher
# ---------------------------------------------------------------------------
def check_downloads() -> dict:
    """Check completion status of both model downloads."""
    status = {"training_ready": False, "gguf_ready": False, "training_shards": 0, "gguf_gb": 0.0}

    # Check training model: look for completed .safetensors in hf/ dir
    safetensors = list(HF_FINAL_DIR.glob("model.safetensors-*.safetensors")) if HF_FINAL_DIR.exists() else []
    status["training_shards"] = len(safetensors)
    status["training_ready"] = len(safetensors) >= EXPECTED_SHARDS

    # Check GGUF: look for completed .gguf file (not .incomplete)
    gguf_files = list(MODELS_DIR.glob("*.gguf")) if MODELS_DIR.exists() else []
    if gguf_files:
        status["gguf_ready"] = True
        status["gguf_gb"] = sum(f.stat().st_size for f in gguf_files) / 1e9
    else:
        # Check download progress
        if GGUF_DOWNLOAD_DIR.exists():
            incomplete = list(GGUF_DOWNLOAD_DIR.glob("*.incomplete"))
            if incomplete:
                status["gguf_gb"] = sum(f.stat().st_size for f in incomplete) / 1e9

    return status


def maybe_launch_training(already_launched: bool) -> bool:
    """If both downloads complete and training hasn't started, launch train_v2.py."""
    if already_launched:
        return True
    status = check_downloads()
    if status["training_ready"] and status["gguf_ready"]:
        logger.info("=" * 60)
        logger.info("ALL DOWNLOADS COMPLETE — LAUNCHING TRAINING!")
        logger.info(f"  Training shards: {status['training_shards']}/{EXPECTED_SHARDS}")
        logger.info(f"  GGUF: {status['gguf_gb']:.1f}GB")
        logger.info("=" * 60)
        subprocess.Popen(
            [sys.executable, str(TRAIN_SCRIPT)],
            stdout=open(PROJECT_ROOT / "logs" / "train_v2.log", "w"),
            stderr=subprocess.STDOUT,
        )
        logger.info(f"Training launched — logs: logs/train_v2.log")
        return True
    return False


# ---------------------------------------------------------------------------
# Quality report (every 30 min)
# ---------------------------------------------------------------------------
def quality_report(session_stats: dict, db, session_start: float):
    """Print comprehensive quality report for this session."""
    from hiveai.models import TrainingPair
    from sqlalchemy import func

    elapsed_min = (time.time() - session_start) / 60
    gen = session_stats["generated"]
    passed = session_stats["passed_080"]
    total_q = session_stats["total_quality"]
    template_stats = session_stats["template_stats"]
    quality_dist = session_stats["quality_dist"]

    avg_q = total_q / gen if gen > 0 else 0.0
    pass_rate = passed / gen * 100 if gen > 0 else 0.0

    logger.info("\n" + "=" * 65)
    logger.info(f"  QUALITY REPORT — {elapsed_min:.0f} min elapsed")
    logger.info("=" * 65)
    logger.info(f"  This session:  {gen} generated | {passed} passed (>= 0.75) | {pass_rate:.0f}% pass rate")
    logger.info(f"  Avg quality:   {avg_q:.3f}")

    if quality_dist:
        median_q = statistics.median(quality_dist)
        stdev_q = statistics.stdev(quality_dist) if len(quality_dist) > 1 else 0
        logger.info(f"  Median:        {median_q:.3f}  Stdev: {stdev_q:.3f}")
        buckets = {"0.3-0.5": 0, "0.5-0.7": 0, "0.7-0.8": 0, "0.8-0.9": 0, "0.9+": 0}
        for q in quality_dist:
            if q < 0.5: buckets["0.3-0.5"] += 1
            elif q < 0.7: buckets["0.5-0.7"] += 1
            elif q < 0.8: buckets["0.7-0.8"] += 1
            elif q < 0.9: buckets["0.8-0.9"] += 1
            else: buckets["0.9+"] += 1
        logger.info(f"  Distribution:  {buckets}")

    # Template breakdown
    logger.info(f"\n  Template effectiveness:")
    for tkey, ts in sorted(template_stats.items(), key=lambda x: -x[1]["eligible"]):
        tgen = ts["generated"]
        telig = ts["eligible"]
        tavg = ts["total_quality"] / tgen if tgen > 0 else 0
        pct = telig / tgen * 100 if tgen > 0 else 0
        logger.info(f"    {tkey:20s}  {tgen:3d} gen  {telig:3d} pass ({pct:.0f}%)  avg_q={tavg:.3f}")

    # DB totals
    total_db = db.query(TrainingPair).count()
    premium_db = get_high_quality_count(db)
    logger.info(f"\n  DB totals:  {total_db} pairs | {premium_db} premium (>= 0.75)")

    # Download status
    dl = check_downloads()
    training_pct = dl["training_shards"] / EXPECTED_SHARDS * 100
    logger.info(f"\n  Downloads:  Training {dl['training_shards']}/{EXPECTED_SHARDS} shards ({training_pct:.0f}%)")
    gguf_status = "READY" if dl["gguf_ready"] else f"{dl['gguf_gb']:.1f}GB / 19.7GB"
    logger.info(f"              GGUF {gguf_status}")

    # Diminishing returns check
    recent = quality_dist[-20:] if len(quality_dist) >= 20 else quality_dist
    recent_avg = sum(recent) / len(recent) if recent else 0
    if recent_avg < 0.72 and len(recent) >= 20:
        logger.warning(f"\n  DIMINISHING RETURNS DETECTED — recent avg quality: {recent_avg:.3f}")
        logger.warning(f"  Last 20 pairs below 0.72 avg. Consider switching templates.")
    else:
        logger.info(f"\n  Recent quality (last {len(recent)}): {recent_avg:.3f} — GOOD")

    logger.info("=" * 65 + "\n")

    return recent_avg  # return for diminishing returns check


# ---------------------------------------------------------------------------
# Main mining loop
# ---------------------------------------------------------------------------
def mine_topic(topic: str, template_key: str, template_text: str, workers_sem) -> dict | None:
    """Generate one pair for a topic/template. Returns None on failure."""
    from hiveai.lora.distiller import _score_quality
    instruction = template_text.format(concept=topic)
    full_prompt = f"{SYSTEM_PROMPT}\n\n{instruction}"
    try:
        response = make_fast_call(full_prompt, max_tokens=4096)
        if not response or len(response.strip()) < 100:
            return None
        quality = _score_quality(instruction, response.strip())
        return {
            "source": "self_distill",
            "topic": topic,
            "instruction": instruction,
            "response": response.strip(),
            "quality": quality,
            "is_eligible": quality >= 0.55,
            "template": template_key,
        }
    except Exception as e:
        logger.warning(f"  [{template_key}] {topic[:40]}... failed: {e}")
        return None


def run_supervisor(hours: float = 10.0, workers: int = 3):
    from hiveai.models import SessionLocal
    from hiveai.lora.distiller import _persist_pair

    end_time = time.time() + hours * 3600
    session_start = time.time()
    last_quality_report = time.time()
    last_download_check = time.time()
    training_launched = False

    QUALITY_REPORT_INTERVAL = 30 * 60  # 30 min
    DOWNLOAD_CHECK_INTERVAL = 10 * 60  # 10 min

    db = SessionLocal()

    # --- Build SMART work queue: find ALL unused (topic, template) combos ---
    existing_topics = get_existing_topics(db)
    used_combos = get_used_template_combos(db)
    template_dict = {tkey: ttext for tkey, ttext in TEMPLATES}

    # Phase A: Unused templates for EXISTING topics (highest value — proven topics)
    remining_items = []
    for topic in existing_topics:
        used_templates = used_combos.get(topic, set())
        for tkey, ttext in TEMPLATES:
            if tkey not in used_templates:
                remining_items.append((topic, tkey, ttext))

    # Phase B: All templates for NEW extended topics + LLM-generated topics
    new_topics = [t for t in EXTENDED_TOPICS if t not in existing_topics]
    # Also load LLM-generated topics if available
    gen_topics_path = PROJECT_ROOT / "scripts" / "generated_topics.json"
    if gen_topics_path.exists():
        import json as _json
        with open(gen_topics_path) as _f:
            gen_topics = _json.load(_f)
        extra = [t for t in gen_topics if t not in existing_topics and t not in set(new_topics)]
        new_topics.extend(extra)
        logger.info(f"Loaded {len(extra)} LLM-generated topics from {gen_topics_path}")
    new_topic_items = []
    for topic in new_topics:
        for tkey, ttext in TEMPLATES:
            new_topic_items.append((topic, tkey, ttext))

    logger.info(f"Extended topics available: {len(EXTENDED_TOPICS)}")
    logger.info(f"Already in DB: {len(existing_topics)} topics")
    logger.info(f"Unused (topic, template) combos for existing topics: {len(remining_items)}")
    logger.info(f"New topic × template combos: {len(new_topic_items)}")
    logger.info(f"Templates: {len(TEMPLATES)}")
    logger.info(f"Workers: {workers} | Hours: {hours}")

    # Combine: re-mine existing first (proven topics), then new topics
    all_items = remining_items + new_topic_items
    logger.info(f"Total work queue: {len(all_items)} tasks")

    # Shuffle for variety (mix templates and topics evenly)
    import random
    random.seed(42)
    random.shuffle(all_items)
    work_items = all_items

    logger.info(f"Work queue: {len(work_items)} tasks (shuffled)")

    # Session stats
    session_stats = {
        "generated": 0,
        "passed_080": 0,
        "total_quality": 0.0,
        "template_stats": defaultdict(lambda: {"generated": 0, "eligible": 0, "total_quality": 0.0}),
        "quality_dist": [],
        "topics_done": set(),
    }

    item_idx = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}

        # Seed initial batch
        def submit_next():
            nonlocal item_idx
            while item_idx < len(work_items) and len(futures) < workers * 2:
                topic, tkey, ttext = work_items[item_idx]
                item_idx += 1
                f = executor.submit(mine_topic, topic, tkey, ttext, None)
                futures[f] = (topic, tkey)

        submit_next()

        while futures and time.time() < end_time:
            done_futures = [f for f in list(futures.keys()) if f.done()]

            for future in done_futures:
                topic, tkey = futures.pop(future)
                result = future.result()

                if result:
                    quality = result["quality"]
                    session_stats["generated"] += 1
                    session_stats["total_quality"] += quality
                    session_stats["quality_dist"].append(quality)
                    session_stats["template_stats"][tkey]["generated"] += 1
                    session_stats["template_stats"][tkey]["total_quality"] += quality

                    if quality >= 0.75:
                        session_stats["passed_080"] += 1
                        session_stats["template_stats"][tkey]["eligible"] += 1
                        _persist_pair(db, result)
                        logger.info(
                            f"  SAVED q={quality:.3f} [{tkey}] {topic[:50]}..."
                        )
                    else:
                        logger.info(
                            f"  SKIP  q={quality:.3f} [{tkey}] {topic[:50]}... (below 0.75)"
                        )

                    session_stats["topics_done"].add(topic)

                # Submit more work
                submit_next()

            # Periodic checks
            now = time.time()

            if now - last_quality_report >= QUALITY_REPORT_INTERVAL:
                last_quality_report = now
                recent_avg = quality_report(session_stats, db, session_start)
                # Diminishing returns: if avg quality of last 20 below 0.72,
                # skip to o1-style templates only
                if recent_avg < 0.72 and session_stats["generated"] > 30:
                    logger.warning("Switching to o1-style templates only for higher quality...")
                    # Filter remaining work to only harder templates
                    o1_templates = {"reflect_revise", "system_design"}
                    remaining = [(t, k, txt) for t, k, txt in work_items[item_idx:]
                                 if k in o1_templates]
                    work_items = work_items[:item_idx] + remaining
                    logger.info(f"Filtered work queue to {len(remaining)} o1-style tasks")

            if now - last_download_check >= DOWNLOAD_CHECK_INTERVAL:
                last_download_check = now
                dl = check_downloads()
                gguf_dl_status = "READY" if dl["gguf_ready"] else f"{dl['gguf_gb']:.1f}GB"
                logger.info(
                    f"Downloads — Training: {dl['training_shards']}/{EXPECTED_SHARDS} shards | "
                    f"GGUF: {gguf_dl_status}"
                )
                training_launched = maybe_launch_training(training_launched)

            time.sleep(0.5)

        # Wait for any remaining futures
        for future in list(futures.keys()):
            topic, tkey = futures[future]
            result = future.result(timeout=120)
            if result and result["quality"] >= 0.80:
                _persist_pair(db, result)

    # Final report
    quality_report(session_stats, db, session_start)

    # Final download check + launch
    training_launched = maybe_launch_training(training_launched)

    # Re-export training data with new pairs
    elapsed_h = (time.time() - session_start) / 3600
    logger.info(f"\nSupervisor complete after {elapsed_h:.1f}h")
    logger.info(f"Session: {session_stats['generated']} generated, {session_stats['passed_080']} saved (>= 0.75)")
    logger.info(f"New premium pairs in DB: {get_high_quality_count(db)}")

    # Auto-export updated training data
    try:
        export_expanded_dataset(db)
    except Exception as e:
        logger.warning(f"Export failed: {e}")

    db.close()


def export_expanded_dataset(db):
    """Re-export v2_expanded.jsonl with all current >= 0.70 pairs."""
    import json
    from hiveai.models import TrainingPair
    pairs = db.query(TrainingPair).filter(
        TrainingPair.is_eligible == True,
        TrainingPair.quality >= 0.70,
    ).order_by(TrainingPair.quality.desc()).all()

    out_path = PROJECT_ROOT / "loras" / "training_data" / "v2_expanded.jsonl"
    count = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps({
                "instruction": p.instruction,
                "input": "",
                "output": p.response,
            }, ensure_ascii=False) + "\n")
            count += 1
    logger.info(f"Exported {count} pairs to {out_path}")
    return count


def show_status():
    """Print DB + download status, then exit."""
    from hiveai.models import SessionLocal, TrainingPair
    from sqlalchemy import func
    db = SessionLocal()
    total = db.query(TrainingPair).count()
    premium = db.query(TrainingPair).filter(TrainingPair.quality >= 0.75).count()
    good = db.query(TrainingPair).filter(TrainingPair.quality >= 0.70, TrainingPair.quality < 0.80).count()
    avg = db.query(func.avg(TrainingPair.quality)).scalar() or 0
    existing = get_existing_topics(db)
    new_topics = [t for t in EXTENDED_TOPICS if t not in existing]
    db.close()

    dl = check_downloads()

    print(f"\n{'='*55}")
    print("  SUPERVISOR STATUS")
    print(f"{'='*55}")
    print(f"  DB total:        {total} pairs")
    print(f"  Premium (>=0.80): {premium}")
    print(f"  Good (0.70-0.79): {good}")
    print(f"  Avg quality:      {avg:.3f}")
    print(f"  Extended topics:  {len(EXTENDED_TOPICS)} total, {len(new_topics)} new")
    print(f"  Max new pairs:    {len(new_topics) * len(TEMPLATES)}")
    print(f"\n  Downloads:")
    print(f"    Training: {dl['training_shards']}/{EXPECTED_SHARDS} shards ({'READY' if dl['training_ready'] else 'in progress'})")
    gguf_show = "READY" if dl["gguf_ready"] else f"{dl['gguf_gb']:.1f}GB / 19.7GB"
    print(f"    GGUF:     {gguf_show}")
    print(f"{'='*55}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HiveAI 10-hour distillation supervisor")
    parser.add_argument("--hours", type=float, default=10.0)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.status:
        show_status()
        sys.exit(0)

    logger.info("=" * 65)
    logger.info("  HIVEAI DISTILLATION SUPERVISOR")
    logger.info(f"  Duration: {args.hours}h | Workers: {args.workers}")
    logger.info(f"  Quality gate: >= 0.75 | Quality reports: every 30 min")
    logger.info(f"  Download watch: every 10 min | Auto-train on completion")
    logger.info("=" * 65)

    run_supervisor(hours=args.hours, workers=args.workers)
