#!/usr/bin/env python3
"""
Weakness Hunter -- reads eval results, identifies weak categories, generates
targeted training pairs to close the gaps.

    python scripts/weakness_hunter.py                          # analyze latest eval
    python scripts/weakness_hunter.py --eval evals/v6.json     # specific eval file
    python scripts/weakness_hunter.py --generate               # analyze + generate pairs
    python scripts/weakness_hunter.py --generate --pairs 20    # 20 pairs per weak category
    python scripts/weakness_hunter.py --threshold 0.80         # custom weakness threshold

Pipeline:
    1. Load eval results (latest or specified)
    2. Rank categories by score
    3. Identify weak categories (below threshold)
    4. Map categories to distiller topics
    5. Generate targeted training pairs via miner/distiller
    6. Export as JSONL ready for next training round
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("weakness_hunter")

EVALS_DIR = PROJECT_ROOT / "evals"
OUTPUT_DIR = PROJECT_ROOT / "loras" / "training_data" / "weakness_patches"

# Map eval categories to distiller topics for targeted pair generation.
# Each category maps to a list of specific topics the distiller/miner can use.
CATEGORY_TOPICS = {
    "python": [
        "Python decorators and metaprogramming",
        "Python asyncio and concurrent.futures",
        "Python generators and itertools",
        "Python dataclasses and typing",
        "Python context managers and resource cleanup",
        "Python collections module (defaultdict, Counter, deque)",
        "Python pathlib and file I/O patterns",
        "Python exception hierarchies and custom exceptions",
    ],
    "algorithms": [
        "dynamic programming with memoization",
        "graph algorithms (BFS, DFS, Dijkstra)",
        "binary search on answer space",
        "sliding window and two-pointer techniques",
        "tree traversal and construction",
        "sorting algorithm trade-offs",
        "greedy algorithms with proof of correctness",
        "union-find (disjoint set) data structure",
    ],
    "database": [
        "SQL window functions and CTEs",
        "database indexing strategies and query optimization",
        "PostgreSQL JSONB queries and indexing",
        "SQLAlchemy ORM patterns and session management",
        "database migration strategies (Alembic, schema evolution)",
        "connection pooling and transaction isolation levels",
        "Redis data structures and caching patterns",
        "database sharding and partitioning strategies",
    ],
    "javascript": [
        "JavaScript closures and scope chains",
        "JavaScript Promises and async/await error handling",
        "JavaScript event loop and microtask queue",
        "TypeScript generics and conditional types",
        "JavaScript module systems (ESM vs CommonJS)",
        "JavaScript proxy and reflect API",
        "JavaScript WeakMap/WeakRef and memory management",
        "Node.js streams and backpressure handling",
    ],
    "web": [
        "REST API design and HTTP status codes",
        "WebSocket real-time communication patterns",
        "CORS configuration and preflight requests",
        "JWT authentication and refresh token rotation",
        "rate limiting and API throttling implementation",
        "server-sent events vs WebSockets vs long polling",
        "HTTP/2 and HTTP/3 features and migration",
        "API versioning strategies",
    ],
    "systems": [
        "Linux process management and signals",
        "memory-mapped files and shared memory IPC",
        "socket programming (TCP/UDP) in Python",
        "container orchestration with Docker Compose",
        "systemd service files and process supervision",
        "file descriptor management and select/poll/epoll",
        "Linux cgroups and resource limits",
        "distributed consensus (Raft algorithm basics)",
    ],
    "design_patterns": [
        "factory pattern with registry and plugins",
        "observer pattern and event-driven architecture",
        "strategy pattern for runtime algorithm selection",
        "decorator pattern vs Python decorators",
        "repository pattern for data access",
        "CQRS and event sourcing basics",
        "dependency injection without frameworks",
        "builder pattern for complex object construction",
    ],
    "testing": [
        "pytest fixtures and parametrize patterns",
        "mocking external services (unittest.mock, responses)",
        "property-based testing with Hypothesis",
        "integration testing with Docker containers",
        "test coverage analysis and mutation testing",
        "testing async code with pytest-asyncio",
        "snapshot testing for API responses",
        "load testing with locust",
    ],
    "security": [
        "input validation and SQL injection prevention",
        "XSS prevention and Content Security Policy",
        "secure password hashing (argon2, bcrypt)",
        "TLS certificate management and pinning",
        "OAuth2 flows and PKCE implementation",
        "secrets management (environment vs vault)",
        "CSRF protection mechanisms",
        "secure file upload handling",
    ],
    "hive_sdk": [
        "Hive blockchain posting with dhive.js",
        "beem Python library for Hive operations",
        "Hive custom_json operations for dApps",
        "Hive witness operations and node setup",
        "Hive resource credit system and estimation",
        "Hive key management (posting, active, owner, memo)",
        "Hive HBD savings and interest operations",
        "Hive streaming API for real-time block processing",
    ],
    "hive_architecture": [
        "Hive consensus mechanism (DPoS) internals",
        "Hive virtual operations and blockchain events",
        "Hive account authority and multi-sig",
        "Hive Engine sidechain token operations",
        "Hive community moderation system",
        "Hive HAF (Account Framework) for indexing",
        "Hive Layer 2 solutions (VSC, Ragnarok)",
        "Hive witness scheduling and block production",
    ],
    "hive_economics": [
        "Hive reward pool and curation mechanics",
        "Hive Power delegation and APR calculation",
        "HBD stabilizer and conversion mechanics",
        "Hive governance and proposal system (DHF)",
        "Hive inflation schedule and token economics",
        "Hive DeFi liquidity pools and yield",
        "Hive NFT standards and marketplaces",
        "Hive recurrent transfers and subscription patterns",
    ],
    "hive_security": [
        "Hive key hierarchy and security best practices",
        "Hive account recovery process",
        "Hive transaction signing and verification",
        "Hive phishing prevention for dApps",
    ],
    "hive_layer2": [
        "Hive Engine smart contracts",
        "VSC (Virtual Smart Chain) development",
        "Hive sidechain bridge patterns",
        "Hive Layer 2 token standards",
    ],
    "rust": [
        "Rust ownership and borrowing patterns",
        "Rust async with tokio runtime",
        "Rust error handling with thiserror and anyhow",
        "Rust trait objects vs generics",
        "Rust lifetime annotations and elision",
        "Rust unsafe code guidelines and FFI",
    ],
    "go": [
        "Go goroutines and channel patterns",
        "Go interfaces and type assertions",
        "Go error handling idioms",
        "Go context package for cancellation",
        "Go generics (type parameters)",
        "Go testing and benchmarking",
    ],
    "cpp": [
        "C++ smart pointers and RAII",
        "C++ move semantics and perfect forwarding",
        "C++ templates and SFINAE",
        "C++ concurrency with std::thread and mutexes",
        "C++ STL algorithms and ranges",
        "C++ memory model and atomic operations",
    ],
    "devops": [
        "CI/CD pipeline design with GitHub Actions",
        "Infrastructure as Code with Terraform",
        "Kubernetes deployment strategies (rolling, canary, blue-green)",
        "monitoring and alerting with Prometheus/Grafana",
        "log aggregation and structured logging",
        "secret management in CI/CD pipelines",
    ],
}

# Distiller templates best suited for each weakness type
TEMPLATE_STRATEGY = {
    "low_code_validity": ["implement", "test_driven", "debug_fix"],
    "low_test_passing": ["test_driven", "debug_fix", "reflect_and_revise"],
    "low_concept_coverage": ["implement", "compare", "internals"],
    "low_explanation": ["why_exists", "reflect_and_revise", "inverse_instruct"],
    "default": ["implement", "correct_way", "debug_fix", "compare"],
}


def find_latest_eval() -> Path | None:
    """Find the most recent eval JSON file."""
    if not EVALS_DIR.exists():
        return None
    evals = sorted(EVALS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return evals[0] if evals else None


def load_eval(eval_path: Path) -> dict:
    """Load and return eval results."""
    with open(eval_path, encoding="utf-8") as f:
        return json.load(f)


def analyze_weaknesses(eval_data: dict, threshold: float = 0.75) -> list[dict]:
    """Identify weak categories and dimensions from eval results.

    Returns a list of weakness dicts sorted by severity (worst first):
        {category, score, count, weak_dimensions, gap, priority_topics, templates}
    """
    by_cat = eval_data.get("by_category", {})
    dim_scores = eval_data.get("dimension_scores", {})
    overall = eval_data.get("overall_score", 0)

    weaknesses = []
    for cat, data in by_cat.items():
        score = data.get("score", 0)
        if score >= threshold:
            continue

        gap = threshold - score

        # Identify which dimensions are weakest for this category
        weak_dims = []
        if dim_scores.get("code_validity", 1) < 0.85:
            weak_dims.append("low_code_validity")
        if dim_scores.get("test_passing", 1) < 0.75:
            weak_dims.append("low_test_passing")
        if dim_scores.get("concept_coverage", 1) < 0.85:
            weak_dims.append("low_concept_coverage")
        if dim_scores.get("explanation", 1) < 0.50:
            weak_dims.append("low_explanation")

        # Pick templates based on weak dimensions
        templates = set()
        for dim in (weak_dims or ["default"]):
            templates.update(TEMPLATE_STRATEGY.get(dim, TEMPLATE_STRATEGY["default"]))

        weaknesses.append({
            "category": cat,
            "score": score,
            "count": data.get("count", 0),
            "test_pass_rate": data.get("test_pass_rate", 0),
            "gap": gap,
            "weak_dimensions": weak_dims,
            "priority_topics": CATEGORY_TOPICS.get(cat, []),
            "templates": list(templates),
        })

    weaknesses.sort(key=lambda w: w["gap"], reverse=True)
    return weaknesses


def generate_targeted_pairs(weaknesses: list[dict], pairs_per_category: int = 15,
                            use_miner: bool = True) -> list[dict]:
    """Generate training pairs targeting identified weaknesses.

    Uses the miner (multi-provider) if available, falls back to llama-server.
    Returns list of {instruction, input, output, metadata} dicts.
    """
    all_pairs = []

    for weakness in weaknesses:
        cat = weakness["category"]
        topics = weakness["priority_topics"]
        templates = weakness["templates"]

        if not topics:
            logger.warning(f"No topics mapped for category '{cat}' -- skipping")
            continue

        logger.info(f"Generating {pairs_per_category} pairs for '{cat}' "
                    f"(score={weakness['score']:.3f}, gap={weakness['gap']:.3f})")

        pairs_generated = 0

        if use_miner:
            pairs_generated = _generate_via_miner(cat, topics, templates,
                                                   pairs_per_category, all_pairs)

        if pairs_generated < pairs_per_category:
            remaining = pairs_per_category - pairs_generated
            _generate_via_llama_server(cat, topics, templates, remaining, all_pairs)

    return all_pairs


def _generate_via_miner(category: str, topics: list, templates: list,
                        count: int, output: list) -> int:
    """Try generating pairs through the multi-provider miner."""
    try:
        from hiveai.lora.miner import KnowledgeMiner
        miner = KnowledgeMiner()

        generated = 0
        topic_idx = 0
        template_idx = 0

        while generated < count and topic_idx < len(topics) * 2:
            topic = topics[topic_idx % len(topics)]
            template = templates[template_idx % len(templates)]
            topic_idx += 1
            template_idx += 1

            provider = miner.router.next_provider()
            if not provider:
                logger.warning("No miner providers available")
                break

            # Use the miner's internal generation
            from hiveai.lora.distiller import TEMPLATES, O1_TEMPLATES
            all_templates = {k: v for k, v in TEMPLATES + O1_TEMPLATES}

            if template not in all_templates:
                template = "implement"

            template_text = all_templates[template]
            pair = miner._generate_one_pair(provider, topic, template, template_text, "python")

            if pair:
                pair["metadata"] = pair.get("metadata", {})
                pair["metadata"]["source"] = "weakness_hunter"
                pair["metadata"]["target_category"] = category
                pair["metadata"]["template"] = template
                output.append(pair)
                generated += 1
                logger.info(f"  [{category}] {generated}/{count} via {provider.provider.name}")

        return generated
    except Exception as e:
        logger.warning(f"Miner generation failed: {e}")
        return 0


def _generate_via_llama_server(category: str, topics: list, templates: list,
                               count: int, output: list) -> int:
    """Generate pairs using the local llama-server."""
    import urllib.request

    from hiveai.config import LLAMA_SERVER_URL

    generated = 0
    topic_idx = 0

    from hiveai.lora.distiller import TEMPLATES, O1_TEMPLATES
    all_templates = dict(TEMPLATES + O1_TEMPLATES)

    while generated < count and topic_idx < len(topics) * 3:
        topic = topics[topic_idx % len(topics)]
        template_key = templates[topic_idx % len(templates)]
        topic_idx += 1

        template_text = all_templates.get(template_key, all_templates.get("implement", ""))
        instruction = template_text.format(concept=topic)

        data = json.dumps({
            "model": "hiveai",
            "messages": [
                {"role": "system", "content": "You are an expert coding assistant. Write clean, correct, well-documented code with practical examples."},
                {"role": "user", "content": instruction},
            ],
            "max_tokens": 4096,
            "temperature": 0.7,
        }).encode()

        req = urllib.request.Request(
            f"{LLAMA_SERVER_URL}/v1/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
        )

        try:
            resp = urllib.request.urlopen(req, timeout=120)
            result = json.loads(resp.read().decode())
            content = result["choices"][0]["message"]["content"]

            if len(content) < 200:
                continue

            output.append({
                "instruction": instruction,
                "input": "",
                "output": content,
                "metadata": {
                    "source": "weakness_hunter",
                    "target_category": category,
                    "template": template_key,
                    "provider": "llama-server",
                },
            })
            generated += 1
            logger.info(f"  [{category}] {generated}/{count} via llama-server")

        except Exception as e:
            logger.warning(f"  llama-server call failed: {e}")
            continue

    return generated


def export_pairs(pairs: list[dict], eval_model: str) -> Path:
    """Export generated pairs as JSONL for training."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"weakness_patch_{eval_model}_{timestamp}.jsonl"

    with open(output_path, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    logger.info(f"Exported {len(pairs)} pairs to {output_path}")
    return output_path


def print_analysis(eval_data: dict, weaknesses: list[dict], threshold: float):
    """Print weakness analysis report."""
    model = eval_data.get("model", "unknown")
    overall = eval_data.get("overall_score", 0)
    dim = eval_data.get("dimension_scores", {})
    by_cat = eval_data.get("by_category", {})

    print("\n" + "=" * 65)
    print(f"  Weakness Analysis: {model}")
    print(f"  Overall: {overall:.3f} | Threshold: {threshold:.3f}")
    print("=" * 65)

    # Dimension scores
    print(f"\n  Dimensions:")
    for d, s in sorted(dim.items(), key=lambda x: x[1]):
        bar = "#" * int(s * 30)
        flag = " << WEAK" if s < 0.60 else ""
        print(f"    {d:20s} {s:.3f} |{bar}{flag}")

    # All categories ranked
    print(f"\n  Categories (ranked):")
    ranked = sorted(by_cat.items(), key=lambda x: x[1].get("score", 0))
    for cat, data in ranked:
        score = data.get("score", 0)
        count = data.get("count", 0)
        bar = "#" * int(score * 30)
        flag = " << TARGET" if score < threshold else ""
        print(f"    {cat:20s} {score:.3f} (n={count:>3}) |{bar}{flag}")

    # Weakness details
    if weaknesses:
        print(f"\n  Weaknesses Found: {len(weaknesses)}")
        print(f"  {'Category':20s} {'Score':>6} {'Gap':>6} {'Topics':>6}  Templates")
        print(f"  {'-'*60}")
        for w in weaknesses:
            print(f"  {w['category']:20s} {w['score']:6.3f} {w['gap']:+6.3f} "
                  f"{len(w['priority_topics']):>6}  {', '.join(w['templates'][:3])}")
    else:
        print(f"\n  No weaknesses found below threshold {threshold:.3f}")

    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="Weakness Hunter -- targeted training pair generation")
    parser.add_argument("--eval", type=str, help="Path to eval JSON (default: latest)")
    parser.add_argument("--threshold", type=float, default=0.75,
                        help="Score threshold for weakness (default: 0.75)")
    parser.add_argument("--generate", action="store_true",
                        help="Generate targeted training pairs")
    parser.add_argument("--pairs", type=int, default=15,
                        help="Pairs per weak category (default: 15)")
    parser.add_argument("--no-miner", action="store_true",
                        help="Skip miner, use llama-server only")
    args = parser.parse_args()

    # Find eval file
    if args.eval:
        eval_path = Path(args.eval)
        if not eval_path.is_absolute():
            eval_path = PROJECT_ROOT / eval_path
    else:
        eval_path = find_latest_eval()

    if not eval_path or not eval_path.exists():
        logger.error("No eval file found. Run eval first: python scripts/run_eval.py")
        sys.exit(1)

    logger.info(f"Loading eval: {eval_path}")
    eval_data = load_eval(eval_path)

    # Analyze
    weaknesses = analyze_weaknesses(eval_data, threshold=args.threshold)
    print_analysis(eval_data, weaknesses, args.threshold)

    if not weaknesses:
        print("\nAll categories above threshold -- nothing to hunt!")
        return

    # Generate pairs
    if args.generate:
        if not weaknesses:
            return

        total_target = len(weaknesses) * args.pairs
        logger.info(f"\nGenerating {total_target} targeted pairs "
                    f"({args.pairs} x {len(weaknesses)} weak categories)...")

        pairs = generate_targeted_pairs(
            weaknesses,
            pairs_per_category=args.pairs,
            use_miner=not args.no_miner,
        )

        if pairs:
            model_name = eval_data.get("model", "unknown")
            output_path = export_pairs(pairs, model_name)
            print(f"\n  Generated {len(pairs)} targeted pairs")
            print(f"  Exported:  {output_path}")
            print(f"\n  To include in next training run:")
            print(f"    1. Move {output_path.name} to loras/training_data/")
            print(f"    2. Rebuild: python scripts/prepare_v5_data.py --export")
            print(f"    3. Train:   python scripts/train_v5.py")
        else:
            logger.warning("No pairs generated -- check provider availability")
    else:
        print(f"\n  Run with --generate to create targeted training pairs")
        print(f"  Expected: ~{len(weaknesses) * args.pairs} pairs "
              f"({args.pairs} x {len(weaknesses)} categories)")


if __name__ == "__main__":
    main()
