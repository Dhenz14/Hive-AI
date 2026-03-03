"""
Anchor Validation System for HiveAI DBC.

Anchors are hand-verified reference answers that catch "confident but wrong"
model outputs — cases where the deterministic scorer gives a high score but
the answer is semantically dangerous (e.g., recommending f-strings for SQL).

Each anchor has:
  - instruction: the question/task to match against
  - must_contain: phrases the response MUST include
  - must_not_contain: phrases the response MUST NOT include
  - rationale: why this matters (for human auditing)

Usage:
    from evals.anchors import load_anchors, validate_against_anchors

    anchors = load_anchors()  # loads all domains
    result = validate_against_anchors(instruction, response, anchors)
    if not result["passed"]:
        print(f"Anchor violation: {result['violations']}")
"""

import json
import os
from pathlib import Path
from typing import Optional


ANCHORS_DIR = Path(__file__).parent


def load_anchors(domain: Optional[str] = None) -> list[dict]:
    """Load anchor definitions from JSON files.

    Args:
        domain: Optional domain filter (e.g., "security", "python").
                If None, loads ALL anchors from all domains.

    Returns:
        List of anchor dicts with id, domain, severity, instruction,
        must_contain, must_not_contain, rationale.
    """
    anchors = []
    for json_file in sorted(ANCHORS_DIR.glob("*.json")):
        file_domain = json_file.stem
        if domain and file_domain != domain:
            continue
        with open(json_file, "r", encoding="utf-8") as f:
            file_anchors = json.load(f)
            anchors.extend(file_anchors)
    return anchors


def find_matching_anchors(
    instruction: str,
    anchors: list[dict],
    similarity_threshold: float = 0.80,
    embedding_fn=None,
) -> list[dict]:
    """Find anchors whose instruction is similar to the given instruction.

    Two matching strategies:
    1. Exact substring match (fast, no dependencies)
    2. Cosine similarity via embedding_fn (accurate, requires model)

    Args:
        instruction: The instruction/question to check.
        anchors: List of anchor dicts from load_anchors().
        similarity_threshold: Cosine similarity threshold for embedding match.
        embedding_fn: Optional callable(text) -> list[float] for embeddings.
                      If None, falls back to keyword overlap matching.

    Returns:
        List of matching anchor dicts.
    """
    instruction_lower = instruction.lower()
    matches = []

    for anchor in anchors:
        anchor_instruction_lower = anchor["instruction"].lower()

        # Strategy 1: Substring containment (either direction)
        if (
            anchor_instruction_lower in instruction_lower
            or instruction_lower in anchor_instruction_lower
        ):
            matches.append(anchor)
            continue

        # Strategy 2: Keyword overlap (>= 60% of anchor keywords in instruction)
        anchor_words = set(anchor_instruction_lower.split())
        instruction_words = set(instruction_lower.split())
        # Remove common stop words
        stop_words = {
            "how", "do", "you", "what", "is", "the", "a", "an", "in", "to",
            "and", "or", "of", "for", "with", "on", "at", "by", "are", "when",
            "should", "does", "can", "why",
        }
        anchor_keywords = anchor_words - stop_words
        instruction_keywords = instruction_words - stop_words

        if anchor_keywords and instruction_keywords:
            overlap = len(anchor_keywords & instruction_keywords)
            ratio = overlap / len(anchor_keywords)
            if ratio >= 0.60:
                matches.append(anchor)
                continue

        # Strategy 3: Embedding similarity (if available)
        if embedding_fn is not None:
            try:
                emb_a = embedding_fn(instruction)
                emb_b = embedding_fn(anchor["instruction"])
                sim = _cosine_similarity(emb_a, emb_b)
                if sim >= similarity_threshold:
                    matches.append(anchor)
            except Exception:
                pass  # Embedding failures shouldn't block validation

    return matches


def validate_against_anchors(
    instruction: str,
    response: str,
    anchors: list[dict],
    embedding_fn=None,
    similarity_threshold: float = 0.80,
) -> dict:
    """Validate a response against matching anchors.

    Args:
        instruction: The instruction/question that was asked.
        response: The model's response to validate.
        anchors: List of anchor dicts from load_anchors().
        embedding_fn: Optional embedding function for similarity matching.
        similarity_threshold: Threshold for cosine similarity matching.

    Returns:
        dict with:
            passed: bool — True if no violations found
            matched_anchors: list of anchor IDs that matched the instruction
            violations: list of dicts describing each violation
            details: list of per-anchor check results
    """
    matching = find_matching_anchors(
        instruction, anchors, similarity_threshold, embedding_fn
    )

    if not matching:
        return {
            "passed": True,
            "matched_anchors": [],
            "violations": [],
            "details": [],
        }

    response_lower = response.lower()
    violations = []
    details = []

    for anchor in matching:
        anchor_result = {
            "id": anchor["id"],
            "domain": anchor["domain"],
            "severity": anchor["severity"],
            "missing": [],
            "forbidden_found": [],
            "passed": True,
        }

        # Check must_contain
        for phrase in anchor.get("must_contain", []):
            if phrase.lower() not in response_lower:
                anchor_result["missing"].append(phrase)
                anchor_result["passed"] = False

        # Check must_not_contain
        for phrase in anchor.get("must_not_contain", []):
            if phrase.lower() in response_lower:
                anchor_result["forbidden_found"].append(phrase)
                anchor_result["passed"] = False

        details.append(anchor_result)

        if not anchor_result["passed"]:
            violations.append(
                {
                    "anchor_id": anchor["id"],
                    "domain": anchor["domain"],
                    "severity": anchor["severity"],
                    "rationale": anchor.get("rationale", ""),
                    "missing_phrases": anchor_result["missing"],
                    "forbidden_phrases": anchor_result["forbidden_found"],
                }
            )

    return {
        "passed": len(violations) == 0,
        "matched_anchors": [a["id"] for a in matching],
        "violations": violations,
        "details": details,
    }


def get_anchor_stats() -> dict:
    """Get summary statistics about the anchor collection.

    Returns:
        dict with total count, per-domain counts, severity breakdown.
    """
    anchors = load_anchors()
    domains = {}
    severities = {}

    for a in anchors:
        d = a.get("domain", "unknown")
        s = a.get("severity", "unknown")
        domains[d] = domains.get(d, 0) + 1
        severities[s] = severities.get(s, 0) + 1

    return {
        "total": len(anchors),
        "by_domain": dict(sorted(domains.items())),
        "by_severity": dict(sorted(severities.items())),
    }


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
