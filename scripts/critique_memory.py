"""
GEM 1 — Critique Pattern Memory

Observational ledger for training critique attempts. Stores open/closed lifecycle
of weakness-targeted training cycles so regression_eval can close loops by exact
attempt_id and weakness_hunter can learn which templates work.

Design rules (Phase 2 boundary):
  - embedding = NULL on all critique BookSections (no HNSW pollution)
  - Queried by book_id + metadata only (never semantic similarity)
  - Excluded from ALL chat retrieval paths via exclude_book_ids
  - CRITIQUE_MEMORY_INFLUENCE=false gates any generation behavior change
  - Attribution stored but not acted on until Phase 3

BookSection.keywords_json schema for critique patterns:
{
    "source_type": "critique_pattern",
    "attempt_id": "a3f8b2c1e9d4",
    "attribution": "isolated" | "batched",
    "domain": "cpp",
    "probe_id": "cpp-raii",
    "weakness_type": "keyword_only",
    "weakness_classifier_version": 1,
    "template_used": "implement",
    "pairs_generated": 15,
    "fix_version": "v6-cpp-fix",
    "pre_score": 0.857,
    "pre_keyword_score": 0.82,
    "pre_structure_score": 0.95,
    "post_score": null,
    "post_keyword_score": null,
    "post_structure_score": null,
    "status": "open" | "closed" | "abandoned",
    "fix_succeeded": null,
    "delta": null,
    "opened_at": "2026-03-15T12:00:00Z",
    "closed_at": null,
    "closed_by_attempt_id": null,
    "keywords": ["cpp", "raii", "keyword_only", "implement", "critique_pattern"]
}
"""

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_CRITIQUE_BOOK_TITLE = "Critique Patterns :: Training Outcomes"
_CRITIQUE_BOOK_JOB_ID = -2

# Cached book ID (avoids repeated DB lookups)
_critique_book_id_cache = None

# Auto-abandon open critiques after this many days
_ABANDON_AFTER_DAYS = 7


def _get_or_create_critique_book(db):
    """Get or create the synthetic GoldenBook for critique patterns."""
    from hiveai.models import GoldenBook
    book = db.query(GoldenBook).filter_by(title=_CRITIQUE_BOOK_TITLE).first()
    if book:
        return book
    book = GoldenBook(
        job_id=_CRITIQUE_BOOK_JOB_ID,
        title=_CRITIQUE_BOOK_TITLE,
        content="Synthetic book for critique pattern storage. Not retrievable via search.",
        content_hash="critique_patterns_synthetic",
        status="published",
        quality_score=1.0,
    )
    db.add(book)
    db.flush()
    logger.info(f"Created critique patterns book (id={book.id})")
    return book


def get_critique_book_id(db) -> int:
    """Return the critique book ID, creating the book if needed. Cached after first call."""
    global _critique_book_id_cache
    if _critique_book_id_cache is not None:
        return _critique_book_id_cache
    book = _get_or_create_critique_book(db)
    _critique_book_id_cache = book.id
    return _critique_book_id_cache


def store_critique_pattern(
    db,
    domain: str,
    probe_id: str,
    weakness_type: str,
    template_used: str,
    pairs_generated: int,
    fix_version: str,
    pre_score: float,
    pre_keyword_score: float = None,
    pre_structure_score: float = None,
    weakness_classifier_version: int = 1,
    attribution: str = "batched",
) -> tuple:
    """
    Store a new critique pattern as an open BookSection.

    Returns (section_id, attempt_id).
    """
    from hiveai.models import BookSection

    attempt_id = str(uuid.uuid4())[:12]
    now = datetime.now(timezone.utc).isoformat()

    book = _get_or_create_critique_book(db)

    metadata = {
        "source_type": "critique_pattern",
        "attempt_id": attempt_id,
        "attribution": attribution,
        "domain": domain,
        "probe_id": probe_id,
        "weakness_type": weakness_type,
        "weakness_classifier_version": weakness_classifier_version,
        "template_used": template_used,
        "pairs_generated": pairs_generated,
        "fix_version": fix_version,
        "pre_score": pre_score,
        "pre_keyword_score": pre_keyword_score,
        "pre_structure_score": pre_structure_score,
        "post_score": None,
        "post_keyword_score": None,
        "post_structure_score": None,
        "status": "open",
        "fix_succeeded": None,
        "delta": None,
        "opened_at": now,
        "closed_at": None,
        "closed_by_attempt_id": None,
        "keywords": [domain, probe_id, weakness_type, template_used, "critique_pattern"],
    }

    section = BookSection(
        book_id=book.id,
        header=f"Critique: {probe_id} ({weakness_type}) → {fix_version}",
        content=(
            f"Domain: {domain}\n"
            f"Probe: {probe_id}\n"
            f"Weakness: {weakness_type}\n"
            f"Template: {template_used}\n"
            f"Pairs: {pairs_generated}\n"
            f"Pre-score: {pre_score}\n"
            f"Version: {fix_version}\n"
            f"Attribution: {attribution}"
        ),
        token_count=0,
        keywords_json=json.dumps(metadata),
    )
    # Explicitly set embedding to None (no vector — must not enter HNSW index)
    section.embedding = None

    db.add(section)
    db.flush()

    logger.info(
        f"Stored critique pattern: attempt={attempt_id} probe={probe_id} "
        f"weakness={weakness_type} template={template_used} version={fix_version}"
    )
    return section.id, attempt_id


def close_critique_loop(
    db,
    attempt_id: str,
    post_score: float,
    post_keyword_score: float = None,
    post_structure_score: float = None,
    closed_by_attempt_id: str = None,
) -> bool:
    """
    Close a critique pattern by exact attempt_id.

    Rule: only the exact attempt_id that opened the critique can close it.
    Revised answers create new attempts; old critiques close only when named.

    Returns True if found and closed, False if not found or already closed.
    """
    from hiveai.models import BookSection

    book_id = get_critique_book_id(db)
    sections = db.query(BookSection).filter_by(book_id=book_id).all()

    for section in sections:
        if not section.keywords_json:
            continue
        try:
            meta = json.loads(section.keywords_json)
        except (json.JSONDecodeError, TypeError):
            continue

        if meta.get("source_type") != "critique_pattern":
            continue
        if meta.get("attempt_id") != attempt_id:
            continue
        if meta.get("status") != "open":
            logger.info(f"Critique {attempt_id} already {meta.get('status')}, skipping close")
            return False

        # Close it
        now = datetime.now(timezone.utc).isoformat()
        pre_score = meta.get("pre_score", 0)
        delta = post_score - pre_score if pre_score is not None else None
        # Success threshold: >0.01 (one percentage point). Below that is
        # measurement noise on 60-probe eval (~1.67% per probe per domain).
        # Frozen in docs/phase3_acceptance_gates.md.
        _SUCCESS_THRESHOLD = 0.01
        fix_succeeded = delta is not None and delta > _SUCCESS_THRESHOLD

        meta["post_score"] = post_score
        meta["post_keyword_score"] = post_keyword_score
        meta["post_structure_score"] = post_structure_score
        meta["status"] = "closed"
        meta["fix_succeeded"] = fix_succeeded
        meta["delta"] = round(delta, 4) if delta is not None else None
        meta["closed_at"] = now
        meta["closed_by_attempt_id"] = closed_by_attempt_id

        section.keywords_json = json.dumps(meta)
        db.flush()

        logger.info(
            f"Closed critique {attempt_id}: post_score={post_score} "
            f"delta={meta['delta']} succeeded={fix_succeeded}"
        )
        return True

    logger.warning(f"Critique attempt_id={attempt_id} not found for closing")
    return False


def abandon_stale_critiques(db, max_age_days: int = _ABANDON_AFTER_DAYS) -> int:
    """
    Auto-close critiques that have been open longer than max_age_days.
    Returns count of abandoned critiques.
    """
    from hiveai.models import BookSection

    book_id = get_critique_book_id(db)
    sections = db.query(BookSection).filter_by(book_id=book_id).all()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    abandoned = 0

    for section in sections:
        if not section.keywords_json:
            continue
        try:
            meta = json.loads(section.keywords_json)
        except (json.JSONDecodeError, TypeError):
            continue

        if meta.get("source_type") != "critique_pattern":
            continue
        if meta.get("status") != "open":
            continue

        opened_at = meta.get("opened_at")
        if not opened_at:
            continue

        try:
            opened_dt = datetime.fromisoformat(opened_at)
            if opened_dt.tzinfo is None:
                opened_dt = opened_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        if opened_dt < cutoff:
            now = datetime.now(timezone.utc).isoformat()
            meta["status"] = "abandoned"
            meta["closed_at"] = now
            section.keywords_json = json.dumps(meta)
            abandoned += 1
            logger.info(f"Abandoned stale critique: attempt={meta.get('attempt_id')}")

    if abandoned > 0:
        db.flush()
        logger.info(f"Abandoned {abandoned} stale critique(s) older than {max_age_days} days")

    return abandoned


def retrieve_critique_patterns(
    db, domain: str = None, probe_id: str = None,
    status: str = None, limit: int = 50,
) -> list:
    """
    Retrieve critique patterns by direct DB query (no vector search).

    Filtered by book_id first (fast), then metadata fields.
    """
    from hiveai.models import BookSection

    book_id = get_critique_book_id(db)
    sections = db.query(BookSection).filter_by(book_id=book_id).all()

    results = []
    for section in sections:
        if not section.keywords_json:
            continue
        try:
            meta = json.loads(section.keywords_json)
        except (json.JSONDecodeError, TypeError):
            continue

        if meta.get("source_type") != "critique_pattern":
            continue
        if domain and meta.get("domain") != domain:
            continue
        if probe_id and meta.get("probe_id") != probe_id:
            continue
        if status and meta.get("status") != status:
            continue

        meta["section_id"] = section.id
        results.append(meta)

        if len(results) >= limit:
            break

    return results


def get_effective_templates(db, domain: str) -> dict:
    """
    Compute template effectiveness from closed critique patterns.

    Returns {template_name: {"success_rate": float, "attempts": int, "avg_delta": float}}.
    Attribution weighting: isolated=1.0, batched=0.3.

    NOTE: This returns data only. CRITIQUE_MEMORY_INFLUENCE must be True
    before this data can influence generation behavior.
    """
    patterns = retrieve_critique_patterns(db, domain=domain, status="closed")

    templates = {}
    for p in patterns:
        template = p.get("template_used", "unknown")
        if template not in templates:
            templates[template] = {
                "weighted_successes": 0.0,
                "weighted_total": 0.0,
                "deltas": [],
                "attempts": 0,
            }

        weight = 1.0 if p.get("attribution") == "isolated" else 0.3
        templates[template]["weighted_total"] += weight
        templates[template]["attempts"] += 1
        if p.get("fix_succeeded"):
            templates[template]["weighted_successes"] += weight
        delta = p.get("delta")
        if delta is not None:
            templates[template]["deltas"].append(delta)

    result = {}
    for template, data in templates.items():
        total = data["weighted_total"]
        result[template] = {
            "success_rate": round(data["weighted_successes"] / total, 3) if total > 0 else 0.0,
            "attempts": data["attempts"],
            "avg_delta": round(sum(data["deltas"]) / len(data["deltas"]), 4) if data["deltas"] else 0.0,
        }

    return result


def get_critique_stats(db) -> dict:
    """Summary statistics for all critique patterns."""
    from hiveai.models import BookSection

    book_id = get_critique_book_id(db)
    sections = db.query(BookSection).filter_by(book_id=book_id).all()

    stats = {
        "total": 0,
        "open": 0,
        "closed": 0,
        "abandoned": 0,
        "successes": 0,
        "failures": 0,
        "by_domain": {},
    }

    for section in sections:
        if not section.keywords_json:
            continue
        try:
            meta = json.loads(section.keywords_json)
        except (json.JSONDecodeError, TypeError):
            continue
        if meta.get("source_type") != "critique_pattern":
            continue

        stats["total"] += 1
        status = meta.get("status", "open")
        if status in stats:
            stats[status] += 1

        if status == "closed":
            if meta.get("fix_succeeded"):
                stats["successes"] += 1
            else:
                stats["failures"] += 1

        domain = meta.get("domain", "unknown")
        if domain not in stats["by_domain"]:
            stats["by_domain"][domain] = {"total": 0, "open": 0, "closed": 0, "abandoned": 0}
        stats["by_domain"][domain]["total"] += 1
        if status in stats["by_domain"][domain]:
            stats["by_domain"][domain][status] += 1

    return stats
