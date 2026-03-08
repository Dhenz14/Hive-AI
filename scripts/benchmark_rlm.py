#!/usr/bin/env python3
"""
Benchmark: Standard RAG vs RLM-style recursive decomposition.

Compares single-retrieval RAG against recursive sub-query decomposition
on complex multi-hop questions from the knowledge base.

Usage:
    python scripts/benchmark_rlm.py
    python scripts/benchmark_rlm.py --questions 5 --json
    python scripts/benchmark_rlm.py --dry-run
"""

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LLM_URL = "http://localhost:11435"
LLM_COMPLETIONS = f"{LLM_URL}/v1/chat/completions"
LLM_MODEL = "qwen"

BENCHMARK_QUESTIONS = [
    {
        "question": "How would I build a custom Hive indexer that tracks token transfers and serves them via a REST API?",
        "expected_topics": ["HAF", "custom_json", "REST", "indexer", "operations"],
    },
    {
        "question": "Compare Hive DPoS consensus with traditional PoS for building decentralized applications",
        "expected_topics": ["DPoS", "witness", "consensus", "stake", "finality"],
    },
    {
        "question": "How do I optimize a Hive API server for high throughput with caching and connection pooling?",
        "expected_topics": ["cache", "pool", "throughput", "API", "latency"],
    },
    {
        "question": "Explain how resource credits work on Hive and how they affect smart contract design patterns",
        "expected_topics": ["RC", "resource", "mana", "operations", "bandwidth"],
    },
    {
        "question": "What are the security considerations when building a Hive signing service with key hierarchy?",
        "expected_topics": ["posting", "active", "owner", "key", "authority", "signing"],
    },
    {
        "question": "How does Hivemind process social operations and how can I extend it for custom social features?",
        "expected_topics": ["Hivemind", "social", "follow", "reblog", "community"],
    },
    {
        "question": "Design a monitoring system for a Hive witness node that tracks missed blocks and alerts on issues",
        "expected_topics": ["witness", "missed", "block", "monitor", "alert", "node"],
    },
    {
        "question": "How do I implement a Hive-based voting system with custom_json and verify vote integrity?",
        "expected_topics": ["custom_json", "vote", "verify", "broadcast", "transaction"],
    },
    {
        "question": "Explain the Hive block production pipeline from transaction broadcast to irreversibility",
        "expected_topics": ["broadcast", "block", "irreversible", "witness", "transaction"],
    },
    {
        "question": "How would I migrate a centralized user database to Hive accounts with encrypted profile data?",
        "expected_topics": ["account", "create", "encrypt", "profile", "memo", "key"],
    },
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MethodResult:
    method: str
    question: str
    answer: str = ""
    quality_score: float = 0.0
    topic_coverage: float = 0.0
    tokens_used: int = 0
    latency_ms: float = 0.0
    retrieval_calls: int = 0


@dataclass
class BenchmarkResult:
    rag_results: list = field(default_factory=list)
    rlm_results: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def llm_chat(messages: list[dict], max_tokens: int = 1024) -> tuple[str, int]:
    """Send chat completion request. Returns (response_text, tokens_used)."""
    resp = requests.post(LLM_COMPLETIONS, json={
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    tokens = data.get("usage", {}).get("total_tokens", 0)
    return text, tokens


def retrieve_chunks(query: str, limit: int = 6) -> list[dict]:
    """Retrieve knowledge chunks via the HiveAI vectorstore."""
    try:
        from hiveai.vectorstore import hybrid_search, get_embedding
        from hiveai.models import SessionLocal
        db = SessionLocal()
        embedding = get_embedding(query)
        results = hybrid_search(db, query, embedding, limit=limit, max_distance=0.8)
        db.close()
        return results
    except Exception as e:
        print(f"  [!] Retrieval error: {e}", file=sys.stderr)
        return []


def format_context(chunks: list[dict], max_tokens: int = 4900) -> str:
    """Format retrieved chunks into a context string within token budget."""
    chunks.sort(key=lambda c: c.get("score", c.get("distance", 1.0)),
                reverse=True if "score" in (chunks[0] if chunks else {}) else False)
    lines, total = [], 0
    for c in chunks:
        content = c.get("content", c.get("text", ""))
        est_tokens = len(content.split()) * 4 // 3
        if total + est_tokens > max_tokens:
            continue
        lines.append(content.strip())
        total += est_tokens
    return "\n\n---\n\n".join(lines)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_quality(question: str, answer: str) -> float:
    """Lightweight quality scorer adapted from distiller._score_quality."""
    if not answer or len(answer.strip()) < 50:
        return 0.0
    score = 0.3  # base for having content
    words = answer.split()
    # Length bonus
    if len(words) >= 200:
        score += 0.20
    elif len(words) >= 100:
        score += 0.12
    elif len(words) >= 50:
        score += 0.06
    # Structure bonus
    if re.search(r"^#{1,3}\s", answer, re.MULTILINE):
        score += 0.05
    if "```" in answer:
        score += 0.10
    if re.search(r"^\d+\.", answer, re.MULTILINE):
        score += 0.05
    # Reasoning markers
    reasoning = ["because", "therefore", "however", "specifically", "in contrast"]
    score += min(0.10, sum(0.02 for r in reasoning if r in answer.lower()))
    return min(1.0, score)


def score_topic_coverage(answer: str, expected_topics: list[str]) -> float:
    """Fraction of expected topics mentioned in the answer."""
    if not expected_topics:
        return 0.0
    answer_lower = answer.lower()
    hits = sum(1 for t in expected_topics if t.lower() in answer_lower)
    return hits / len(expected_topics)


# ---------------------------------------------------------------------------
# Benchmark methods
# ---------------------------------------------------------------------------

def run_standard_rag(question: str, expected_topics: list[str],
                     dry_run: bool = False) -> MethodResult:
    """Standard RAG: single retrieval + single generation."""
    result = MethodResult(method="standard_rag", question=question)
    start = time.time()

    chunks = retrieve_chunks(question, limit=6)
    result.retrieval_calls = 1
    context = format_context(chunks)

    if dry_run:
        result.answer = f"[DRY RUN] Would query LLM with {len(chunks)} chunks"
        result.latency_ms = (time.time() - start) * 1000
        return result

    messages = [
        {"role": "system", "content": "You are a Hive blockchain expert. Answer using the provided context."},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]
    result.answer, result.tokens_used = llm_chat(messages, max_tokens=1024)
    result.latency_ms = (time.time() - start) * 1000
    result.quality_score = score_quality(question, result.answer)
    result.topic_coverage = score_topic_coverage(result.answer, expected_topics)
    return result


def run_rlm_decomposition(question: str, expected_topics: list[str],
                          dry_run: bool = False) -> MethodResult:
    """RLM-style: decompose -> retrieve per sub-query -> synthesize."""
    result = MethodResult(method="rlm_decomposition", question=question)
    start = time.time()
    total_tokens = 0

    # Step 1: Decompose
    if dry_run:
        sub_questions = [f"[sub-q {i+1}]" for i in range(3)]
    else:
        decompose_msg = [
            {"role": "system", "content": "Break this complex question into 2-4 independent sub-questions. Output ONLY a JSON array of strings."},
            {"role": "user", "content": question},
        ]
        raw, tokens = llm_chat(decompose_msg, max_tokens=256)
        total_tokens += tokens
        try:
            # Extract JSON array from response
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            sub_questions = json.loads(match.group()) if match else [question]
        except (json.JSONDecodeError, AttributeError):
            sub_questions = [question]

    # Step 2: Retrieve + answer each sub-question
    sub_answers = []
    per_sub_budget = 4900 // max(len(sub_questions), 1)

    for sq in sub_questions:
        chunks = retrieve_chunks(sq, limit=4)
        result.retrieval_calls += 1
        context = format_context(chunks, max_tokens=per_sub_budget)

        if dry_run:
            sub_answers.append(f"[DRY RUN] Sub-answer for: {sq}")
            continue

        msg = [
            {"role": "system", "content": "Answer concisely using the provided context. 100-200 words max."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {sq}"},
        ]
        ans, tokens = llm_chat(msg, max_tokens=512)
        total_tokens += tokens
        sub_answers.append(ans)

    # Step 3: Synthesize
    if dry_run:
        result.answer = f"[DRY RUN] Would synthesize {len(sub_questions)} sub-answers"
        result.tokens_used = 0
        result.latency_ms = (time.time() - start) * 1000
        return result

    synthesis_input = "\n\n".join(
        f"### Sub-question {i+1}: {sq}\n{sa}"
        for i, (sq, sa) in enumerate(zip(sub_questions, sub_answers))
    )
    synth_msg = [
        {"role": "system", "content": "Synthesize these sub-answers into a coherent, comprehensive response to the original question."},
        {"role": "user", "content": f"Original question: {question}\n\n{synthesis_input}"},
    ]
    result.answer, tokens = llm_chat(synth_msg, max_tokens=1024)
    total_tokens += tokens

    result.tokens_used = total_tokens
    result.latency_ms = (time.time() - start) * 1000
    result.quality_score = score_quality(question, result.answer)
    result.topic_coverage = score_topic_coverage(result.answer, expected_topics)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Benchmark RLM decomposition vs standard RAG")
    parser.add_argument("--questions", type=int, default=10, help="Number of questions to test (max 10)")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls, test pipeline only")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    n = min(args.questions, len(BENCHMARK_QUESTIONS))
    questions = BENCHMARK_QUESTIONS[:n]

    if not args.dry_run:
        try:
            requests.get(f"{LLM_URL}/health", timeout=5)
        except requests.ConnectionError:
            print(f"Error: LLM server not reachable at {LLM_URL}", file=sys.stderr)
            sys.exit(1)

    bench = BenchmarkResult()
    for i, q in enumerate(questions):
        label = q["question"][:60]
        print(f"\n[{i+1}/{n}] {label}...")

        rag = run_standard_rag(q["question"], q["expected_topics"], dry_run=args.dry_run)
        bench.rag_results.append(rag)
        print(f"  RAG:  quality={rag.quality_score:.2f}  topics={rag.topic_coverage:.2f}  "
              f"tokens={rag.tokens_used}  latency={rag.latency_ms:.0f}ms")

        rlm = run_rlm_decomposition(q["question"], q["expected_topics"], dry_run=args.dry_run)
        bench.rlm_results.append(rlm)
        print(f"  RLM:  quality={rlm.quality_score:.2f}  topics={rlm.topic_coverage:.2f}  "
              f"tokens={rlm.tokens_used}  latency={rlm.latency_ms:.0f}ms  "
              f"retrievals={rlm.retrieval_calls}")

    # Summary
    def avg(vals):
        return sum(vals) / len(vals) if vals else 0.0

    rag_quality = avg([r.quality_score for r in bench.rag_results])
    rlm_quality = avg([r.quality_score for r in bench.rlm_results])
    rag_topics = avg([r.topic_coverage for r in bench.rag_results])
    rlm_topics = avg([r.topic_coverage for r in bench.rlm_results])
    rag_tokens = avg([r.tokens_used for r in bench.rag_results])
    rlm_tokens = avg([r.tokens_used for r in bench.rlm_results])
    rag_latency = avg([r.latency_ms for r in bench.rag_results])
    rlm_latency = avg([r.latency_ms for r in bench.rlm_results])

    summary = {
        "questions": n,
        "dry_run": args.dry_run,
        "standard_rag": {
            "avg_quality": round(rag_quality, 3),
            "avg_topic_coverage": round(rag_topics, 3),
            "avg_tokens": round(rag_tokens),
            "avg_latency_ms": round(rag_latency),
        },
        "rlm_decomposition": {
            "avg_quality": round(rlm_quality, 3),
            "avg_topic_coverage": round(rlm_topics, 3),
            "avg_tokens": round(rlm_tokens),
            "avg_latency_ms": round(rlm_latency),
        },
        "delta": {
            "quality": round(rlm_quality - rag_quality, 3),
            "topic_coverage": round(rlm_topics - rag_topics, 3),
            "token_overhead": round(rlm_tokens - rag_tokens),
            "latency_overhead_ms": round(rlm_latency - rag_latency),
        },
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("\n" + "=" * 60)
        print("BENCHMARK SUMMARY")
        print("=" * 60)
        print(f"  Questions tested:   {n}")
        print(f"  {'Metric':<22} {'RAG':>10} {'RLM':>10} {'Delta':>10}")
        print(f"  {'-'*22} {'-'*10} {'-'*10} {'-'*10}")
        print(f"  {'Quality':<22} {rag_quality:>10.3f} {rlm_quality:>10.3f} {rlm_quality-rag_quality:>+10.3f}")
        print(f"  {'Topic Coverage':<22} {rag_topics:>10.3f} {rlm_topics:>10.3f} {rlm_topics-rag_topics:>+10.3f}")
        print(f"  {'Avg Tokens':<22} {rag_tokens:>10.0f} {rlm_tokens:>10.0f} {rlm_tokens-rag_tokens:>+10.0f}")
        print(f"  {'Avg Latency (ms)':<22} {rag_latency:>10.0f} {rlm_latency:>10.0f} {rlm_latency-rag_latency:>+10.0f}")
        print("=" * 60)

        if rlm_quality > rag_quality:
            print(f"  RLM wins on quality by +{rlm_quality-rag_quality:.3f}")
        else:
            print(f"  Standard RAG wins on quality by +{rag_quality-rlm_quality:.3f}")

        efficiency = (rlm_quality - rag_quality) / max(rlm_tokens - rag_tokens, 1) * 1000
        print(f"  Token efficiency: {efficiency:+.4f} quality/1K tokens overhead")


if __name__ == "__main__":
    main()
