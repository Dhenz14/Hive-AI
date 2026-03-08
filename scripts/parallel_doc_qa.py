#!/usr/bin/env python3
"""Parallel Document QA — Qwen-Agent pattern §9.

Chunks relevant documents, queries each chunk in parallel via ThreadPoolExecutor,
then synthesizes a final answer with source citations.

Usage:
    python scripts/parallel_doc_qa.py --question "How does hybrid search work?"
    python scripts/parallel_doc_qa.py --question "Compare BM25 vs vector search" --max-chunks 8 --workers 4 --json
"""

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

LLM_URL = "http://localhost:11435/v1/chat/completions"
LLM_MODEL = "qwen"
EMBED_URL = "http://localhost:11435/v1/embeddings"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ChunkResult:
    chunk_id: int
    source: str
    header: str
    excerpt: str
    answer: str
    confidence: float
    latency_ms: float


@dataclass
class QAResult:
    question: str
    final_answer: str
    citations: list[dict]
    chunks_queried: int
    chunks_useful: int
    total_latency_ms: float
    per_chunk: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _llm_chat(messages: list[dict], max_tokens: int = 1024, temperature: float = 0.2) -> str:
    """Call local llama-server chat completions endpoint."""
    resp = requests.post(LLM_URL, json={
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _embed(text: str) -> list[float]:
    """Get embedding from local server."""
    resp = requests.post(EMBED_URL, json={
        "model": LLM_MODEL,
        "input": text,
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


# ---------------------------------------------------------------------------
# Retrieval via HiveAI vectorstore
# ---------------------------------------------------------------------------

def retrieve_chunks(question: str, max_chunks: int = 5) -> list[dict]:
    """Retrieve relevant document chunks using hiveai hybrid search."""
    try:
        sys.path.insert(0, ".")
        from hiveai.models import SessionLocal, BookSection
        from hiveai.vectorstore import hybrid_search, vector_search
        from hiveai.llm.client import embed_text

        db = SessionLocal()
        try:
            query_embedding = embed_text(question)
            results = hybrid_search(db, question, query_embedding,
                                    limit=max_chunks, max_distance=0.85)
            chunks = []
            for r in results:
                chunks.append({
                    "id": r.get("id", 0),
                    "header": r.get("header", "Unknown"),
                    "content": r.get("content", ""),
                    "book_title": r.get("book_title", "Unknown"),
                    "distance": r.get("distance", 0.0),
                })
            return chunks
        finally:
            db.close()
    except ImportError as e:
        log.warning(f"HiveAI vectorstore not available ({e}), using direct LLM")
        return []


# ---------------------------------------------------------------------------
# Per-chunk worker
# ---------------------------------------------------------------------------

CHUNK_PROMPT = """You are analyzing a document chunk to answer a question.

**Question:** {question}

**Document chunk (from "{source}" — section "{header}"):**
{content}

Instructions:
1. Answer the question ONLY using information from this chunk.
2. If the chunk doesn't contain relevant information, say "NOT_RELEVANT".
3. Rate your confidence 0.0-1.0 that this chunk answers the question.
4. Be concise — 2-4 sentences max.

Format your response as:
CONFIDENCE: <0.0-1.0>
ANSWER: <your answer or NOT_RELEVANT>"""


def query_chunk(chunk: dict, question: str, chunk_id: int) -> ChunkResult:
    """Query a single chunk — designed to run in a thread."""
    t0 = time.perf_counter()
    source = chunk.get("book_title", "Unknown")
    header = chunk.get("header", "Unknown")
    content = chunk.get("content", "")[:3000]  # Cap chunk size

    prompt = CHUNK_PROMPT.format(
        question=question, source=source, header=header, content=content
    )

    try:
        response = _llm_chat([
            {"role": "system", "content": "You are a precise document analyst."},
            {"role": "user", "content": prompt},
        ], max_tokens=512)

        # Parse confidence + answer
        confidence = 0.5
        answer = response
        for line in response.split("\n"):
            line_s = line.strip()
            if line_s.upper().startswith("CONFIDENCE:"):
                try:
                    confidence = float(line_s.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line_s.upper().startswith("ANSWER:"):
                answer = line_s.split(":", 1)[1].strip()

        latency = (time.perf_counter() - t0) * 1000
        return ChunkResult(
            chunk_id=chunk_id, source=source, header=header,
            excerpt=content[:200], answer=answer,
            confidence=confidence, latency_ms=round(latency, 1),
        )
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        log.error(f"Chunk {chunk_id} failed: {e}")
        return ChunkResult(
            chunk_id=chunk_id, source=source, header=header,
            excerpt=content[:200], answer=f"ERROR: {e}",
            confidence=0.0, latency_ms=round(latency, 1),
        )


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------

SYNTHESIS_PROMPT = """You are synthesizing answers from multiple document chunks to answer a question.

**Question:** {question}

**Chunk answers (with confidence scores):**
{chunk_answers}

Instructions:
1. Combine the chunk answers into a coherent, comprehensive final answer.
2. Prioritize high-confidence chunks.
3. Resolve any contradictions by noting them.
4. Cite sources using [Source: title — section] format.
5. If no chunks were relevant, say so clearly.
"""


def synthesize(question: str, results: list[ChunkResult]) -> str:
    """Synthesize per-chunk answers into a final response."""
    useful = [r for r in results if r.confidence >= 0.3 and "NOT_RELEVANT" not in r.answer.upper()]

    if not useful:
        return "No relevant information found in the retrieved documents."

    chunk_text = "\n\n".join(
        f"[Chunk {r.chunk_id}] (confidence={r.confidence:.2f}, source=\"{r.source}\" — \"{r.header}\"):\n{r.answer}"
        for r in sorted(useful, key=lambda x: x.confidence, reverse=True)
    )

    prompt = SYNTHESIS_PROMPT.format(question=question, chunk_answers=chunk_text)
    return _llm_chat([
        {"role": "system", "content": "You are a research synthesizer. Produce clear, cited answers."},
        {"role": "user", "content": prompt},
    ], max_tokens=1024, temperature=0.3)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def parallel_doc_qa(question: str, max_chunks: int = 5, workers: int = 3) -> QAResult:
    """Run the full parallel document QA pipeline."""
    t0 = time.perf_counter()

    # 1. Retrieve chunks
    log.info(f"Retrieving up to {max_chunks} chunks for: {question[:80]}...")
    chunks = retrieve_chunks(question, max_chunks=max_chunks)

    if not chunks:
        return QAResult(
            question=question,
            final_answer="No documents retrieved. Ensure the knowledge base is populated.",
            citations=[], chunks_queried=0, chunks_useful=0,
            total_latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        )

    log.info(f"Retrieved {len(chunks)} chunks, querying with {workers} workers...")

    # 2. Query chunks in parallel
    results: list[ChunkResult] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(query_chunk, chunk, question, i): i
            for i, chunk in enumerate(chunks)
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            log.info(f"  Chunk {result.chunk_id}: conf={result.confidence:.2f} "
                     f"({result.latency_ms:.0f}ms) — {result.source}")

    # 3. Synthesize
    log.info("Synthesizing final answer...")
    final_answer = synthesize(question, results)

    # 4. Build citations
    useful = [r for r in results if r.confidence >= 0.3 and "NOT_RELEVANT" not in r.answer.upper()]
    citations = [
        {"source": r.source, "section": r.header, "confidence": r.confidence}
        for r in sorted(useful, key=lambda x: x.confidence, reverse=True)
    ]

    total_ms = round((time.perf_counter() - t0) * 1000, 1)
    log.info(f"Done in {total_ms:.0f}ms — {len(useful)}/{len(chunks)} chunks useful")

    return QAResult(
        question=question,
        final_answer=final_answer,
        citations=citations,
        chunks_queried=len(chunks),
        chunks_useful=len(useful),
        total_latency_ms=total_ms,
        per_chunk=[{
            "chunk_id": r.chunk_id, "source": r.source, "header": r.header,
            "confidence": r.confidence, "latency_ms": r.latency_ms,
            "answer_preview": r.answer[:150],
        } for r in results],
    )


def main():
    parser = argparse.ArgumentParser(description="Parallel Document QA")
    parser.add_argument("--question", required=True, help="Question to answer")
    parser.add_argument("--max-chunks", type=int, default=5, help="Max chunks to retrieve")
    parser.add_argument("--workers", type=int, default=3, help="Parallel worker threads")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    result = parallel_doc_qa(args.question, max_chunks=args.max_chunks, workers=args.workers)

    if args.json:
        out = {
            "question": result.question,
            "answer": result.final_answer,
            "citations": result.citations,
            "chunks_queried": result.chunks_queried,
            "chunks_useful": result.chunks_useful,
            "total_latency_ms": result.total_latency_ms,
            "per_chunk": result.per_chunk,
        }
        print(json.dumps(out, indent=2))
    else:
        print(f"\n{'='*70}")
        print(f"Question: {result.question}")
        print(f"{'='*70}")
        print(f"\n{result.final_answer}\n")
        if result.citations:
            print("Sources:")
            for c in result.citations:
                print(f"  - {c['source']} — {c['section']} (confidence: {c['confidence']:.2f})")
        print(f"\nStats: {result.chunks_useful}/{result.chunks_queried} chunks useful, "
              f"{result.total_latency_ms:.0f}ms total")


if __name__ == "__main__":
    main()
