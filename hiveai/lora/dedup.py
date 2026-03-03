"""
hiveai/lora/dedup.py

Tiered deduplication gate for training pairs.

Before any pair enters the training_pairs table:
  1. Embed the instruction text
  2. Tiered cosine-similarity check against all existing pairs
  3. Quality gate: reject below MIN_TRAINING_QUALITY

Dedup tiers (highest similarity first):
  - EXACT (>0.95 instr sim): Always skip — true duplicate
  - PARAPHRASE (0.85-0.95): Skip unless new response is significantly better quality
  - NEAR (0.75-0.85): Allow if responses cover different sub-topics (diversity check)
  - UNIQUE (<0.75): Always allow

This keeps the training set clean while preserving diversity —
two responses about the same concept from different angles both survive.
"""
import json
import logging
import numpy as np

logger = logging.getLogger(__name__)

# Tiered thresholds — loaded from config, calibrated for bge-m3 (1024-dim, L2-normalized)
from hiveai.config import (
    DEDUP_EXACT_THRESHOLD as EXACT_DUPLICATE_THRESHOLD,
    DEDUP_PARAPHRASE_THRESHOLD as PARAPHRASE_THRESHOLD,
    DEDUP_NEAR_THRESHOLD as NEAR_DUPLICATE_THRESHOLD,
    DEDUP_QUALITY_MARGIN as QUALITY_IMPROVEMENT_MARGIN,
    MIN_TRAINING_QUALITY,
)

# In-memory embedding cache — avoids reloading all embeddings from DB on every
# dedup check.  Populated lazily on first call, extended when new pairs are added.
_embedding_cache: list = []
_quality_cache: list = []
_cache_initialized: bool = False


def _cosine_similarity(a: list, b: list) -> float:
    """Cosine similarity between two unit-norm embedding vectors."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    dot = np.dot(va, vb)
    # bge-m3 embeddings are L2-normalized so norms should be ~1.0,
    # but we normalize anyway to be safe
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def _batch_cosine_similarity(new_emb: list, existing_embs: list) -> np.ndarray:
    """
    Vectorized cosine similarity of one embedding against many.
    Returns array of similarities. Much faster than looping for large caches.
    """
    if not existing_embs:
        return np.array([])
    new_vec = np.array(new_emb, dtype=np.float32).reshape(1, -1)
    existing_mat = np.array(existing_embs, dtype=np.float32)
    # Both should be L2-normalized, but normalize to be safe
    new_norm = new_vec / (np.linalg.norm(new_vec) + 1e-8)
    existing_norms = existing_mat / (np.linalg.norm(existing_mat, axis=1, keepdims=True) + 1e-8)
    return (new_norm @ existing_norms.T).flatten()


def _load_existing_embeddings(db) -> tuple:
    """
    Load all embedding_json and quality values from training_pairs.
    Returns (instruction_embeddings, qualities) tuple.
    """
    from hiveai.models import TrainingPair
    rows = db.query(TrainingPair.embedding_json, TrainingPair.quality).filter(
        TrainingPair.embedding_json.isnot(None)
    ).all()

    embeddings = []
    qualities = []
    for emb_json, quality in rows:
        try:
            emb = json.loads(emb_json)
            embeddings.append(emb)
            qualities.append(quality or 0.0)
        except (json.JSONDecodeError, TypeError):
            continue
    return embeddings, qualities


def _get_cached_embeddings(db) -> tuple:
    """
    Return cached embeddings + qualities, loading from DB on first call.
    """
    global _embedding_cache, _quality_cache, _cache_initialized
    if not _cache_initialized:
        _embedding_cache, _quality_cache = _load_existing_embeddings(db)
        _cache_initialized = True
        logger.info(f"Dedup cache initialized with {len(_embedding_cache)} embeddings")
    return _embedding_cache, _quality_cache


def add_to_cache(embedding: list, quality: float = 0.0):
    """Add a newly persisted embedding to the in-memory cache."""
    global _embedding_cache, _quality_cache, _cache_initialized
    if _cache_initialized:
        _embedding_cache.append(embedding)
        _quality_cache.append(quality)


def reset_cache():
    """Force cache reload on next dedup check (e.g. after external DB changes)."""
    global _embedding_cache, _quality_cache, _cache_initialized
    _embedding_cache = []
    _quality_cache = []
    _cache_initialized = False


def is_duplicate(instruction: str, db, quality: float = 0.0) -> bool:
    """
    Tiered deduplication check. Returns True if pair should be skipped.

    Tiers:
      - >0.95 similarity: Always skip (exact duplicate)
      - 0.85-0.95: Skip unless new quality is significantly better
      - 0.75-0.85: Allow (different angle on similar topic)
      - <0.75: Allow (unique instruction)
    """
    from hiveai.llm.client import embed_text

    existing_embs, existing_quals = _get_cached_embeddings(db)
    if not existing_embs:
        return False  # empty DB, nothing to deduplicate against

    try:
        new_emb = embed_text(instruction)
    except Exception as e:
        logger.warning(f"Embedding failed during dedup check: {e} — allowing pair through")
        return False

    # Vectorized similarity check (much faster than looping)
    similarities = _batch_cosine_similarity(new_emb, existing_embs)
    max_sim = float(np.max(similarities)) if len(similarities) > 0 else 0.0
    max_idx = int(np.argmax(similarities)) if len(similarities) > 0 else -1

    # Tier 1: Exact duplicate — always skip
    if max_sim > EXACT_DUPLICATE_THRESHOLD:
        logger.debug(f"Dedup: exact duplicate (sim={max_sim:.3f})")
        return True

    # Tier 2: Paraphrase — skip unless quality is significantly better
    if max_sim > PARAPHRASE_THRESHOLD:
        existing_quality = existing_quals[max_idx] if max_idx < len(existing_quals) else 0.0
        if quality > existing_quality + QUALITY_IMPROVEMENT_MARGIN:
            logger.debug(
                f"Dedup: paraphrase but better quality "
                f"(sim={max_sim:.3f}, new_q={quality:.2f} > old_q={existing_quality:.2f})"
            )
            return False  # Allow — it's a better version
        logger.debug(f"Dedup: paraphrase, not better (sim={max_sim:.3f})")
        return True

    # Tier 3: Near-duplicate (0.75-0.85) — allow (different angle)
    # Tier 4: Unique (<0.75) — always allow
    return False


def passes_quality_gate(quality: float, min_quality: float = None) -> bool:
    """Returns True if the quality score meets the minimum threshold."""
    if min_quality is None:
        min_quality = MIN_TRAINING_QUALITY
    return quality >= min_quality


def filter_new_pairs(pairs: list, db, min_quality: float = None) -> list:
    """
    Filter a list of candidate pairs (dicts with 'instruction' and 'quality' keys)
    through both the quality gate and tiered dedup gate.

    Returns only pairs that pass both gates.
    Pairs that pass are marked is_eligible=True.
    """
    passed = []
    for pair in pairs:
        quality = pair.get("quality", 0.0)
        if not passes_quality_gate(quality, min_quality):
            logger.debug(f"Quality gate: rejected (quality={quality:.2f})")
            continue
        if is_duplicate(pair["instruction"], db, quality=quality):
            logger.debug("Dedup gate: rejected")
            continue
        pair["is_eligible"] = True
        passed.append(pair)
    return passed


def get_dedup_stats(db) -> dict:
    """Return statistics about the dedup cache for monitoring."""
    embs, quals = _get_cached_embeddings(db)
    return {
        "cached_embeddings": len(embs),
        "avg_quality": round(sum(quals) / len(quals), 3) if quals else 0.0,
        "min_quality": round(min(quals), 3) if quals else 0.0,
        "max_quality": round(max(quals), 3) if quals else 0.0,
    }
