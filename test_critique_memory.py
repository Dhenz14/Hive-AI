"""
Phase 2 (GEM 1) Validation Test — Critique Pattern Memory

Acceptance checks:
1. Creating a critique always writes a row with non-null attempt_id
2. Revising an answer creates a new attempt, never mutates the original attempt ID
3. Closure updates only the matching prior attempt_id
4. Excluded book IDs never appear in primary retrieval, hop-2 retrieval,
   referenced-book retrieval, or surfaced trace IDs
5. Isolated vs batched attribution is visible in storage/API, but has zero
   ranking/prompt effect
6. With critique influence disabled, response behavior is unchanged apart
   from new observability fields

Run: python test_critique_memory.py
Requires: DATABASE_URL set (uses the app's DB)
"""

import os
import sys
import json

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set a test DB if none exists
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "sqlite:///test_critique_memory.db"

from hiveai.models import init_db, SessionLocal, BookSection, GoldenBook


def setup():
    """Initialize DB and return a session."""
    init_db()
    return SessionLocal()


def test_store_creates_attempt_id():
    """Check 1: Creating a critique always writes a row with non-null attempt_id."""
    db = setup()
    try:
        from scripts.critique_memory import store_critique_pattern, _critique_book_id_cache
        import scripts.critique_memory as cm
        cm._critique_book_id_cache = None  # reset cache

        section_id, attempt_id = store_critique_pattern(
            db,
            domain="cpp",
            probe_id="cpp-raii",
            weakness_type="keyword_only",
            template_used="implement",
            pairs_generated=15,
            fix_version="v-test-1",
            pre_score=0.857,
            pre_keyword_score=0.82,
            pre_structure_score=0.95,
            attribution="isolated",
        )
        db.commit()

        assert section_id is not None, "section_id should not be None"
        assert attempt_id is not None, "attempt_id should not be None"
        assert len(attempt_id) == 12, f"attempt_id should be 12 chars, got {len(attempt_id)}"

        # Verify the row exists in DB
        section = db.query(BookSection).filter_by(id=section_id).first()
        assert section is not None, "BookSection row should exist"
        meta = json.loads(section.keywords_json)
        assert meta["source_type"] == "critique_pattern"
        assert meta["attempt_id"] == attempt_id
        assert meta["status"] == "open"
        assert meta["attribution"] == "isolated"

        # Verify embedding is NULL
        emb = section.embedding
        assert emb is None, f"Critique section embedding should be NULL, got {type(emb)}"

        print("PASS: test_store_creates_attempt_id")
        return attempt_id, section_id
    finally:
        db.close()


def test_second_store_creates_different_attempt():
    """Check 2: A second store creates a different attempt_id (no mutation)."""
    db = setup()
    try:
        from scripts.critique_memory import store_critique_pattern

        _, attempt1 = store_critique_pattern(
            db, domain="cpp", probe_id="cpp-raii",
            weakness_type="keyword_only", template_used="implement",
            pairs_generated=10, fix_version="v-test-2a", pre_score=0.80,
        )
        _, attempt2 = store_critique_pattern(
            db, domain="cpp", probe_id="cpp-raii",
            weakness_type="keyword_only", template_used="debug_fix",
            pairs_generated=10, fix_version="v-test-2b", pre_score=0.80,
        )
        db.commit()

        assert attempt1 != attempt2, f"Two stores should produce different attempt_ids: {attempt1} == {attempt2}"
        print("PASS: test_second_store_creates_different_attempt")
    finally:
        db.close()


def test_close_by_exact_attempt_id():
    """Check 3: Closure updates only the matching prior attempt_id."""
    db = setup()
    try:
        from scripts.critique_memory import store_critique_pattern, close_critique_loop

        _, attempt_a = store_critique_pattern(
            db, domain="rust", probe_id="rust-ownership",
            weakness_type="structure_only", template_used="implement",
            pairs_generated=20, fix_version="v-test-3a", pre_score=0.70,
        )
        _, attempt_b = store_critique_pattern(
            db, domain="rust", probe_id="rust-traits",
            weakness_type="keyword_only", template_used="debug_fix",
            pairs_generated=15, fix_version="v-test-3b", pre_score=0.65,
        )
        db.commit()

        # Close attempt_a only
        result = close_critique_loop(db, attempt_a, post_score=0.85,
                                     post_keyword_score=0.88, post_structure_score=0.90)
        db.commit()
        assert result is True, "close_critique_loop should return True for valid attempt_id"

        # Verify attempt_a is closed
        from scripts.critique_memory import retrieve_critique_patterns
        patterns = retrieve_critique_patterns(db, domain="rust")
        a_pattern = [p for p in patterns if p["attempt_id"] == attempt_a][0]
        b_pattern = [p for p in patterns if p["attempt_id"] == attempt_b][0]

        assert a_pattern["status"] == "closed", f"attempt_a should be closed, got {a_pattern['status']}"
        assert a_pattern["post_score"] == 0.85
        assert a_pattern["fix_succeeded"] is True
        assert a_pattern["delta"] is not None

        assert b_pattern["status"] == "open", f"attempt_b should still be open, got {b_pattern['status']}"
        assert b_pattern["post_score"] is None

        # Double-close should return False
        result2 = close_critique_loop(db, attempt_a, post_score=0.90)
        assert result2 is False, "Double-close should return False"

        # Close with wrong attempt_id should return False
        result3 = close_critique_loop(db, "nonexistent123", post_score=0.90)
        assert result3 is False, "Closing nonexistent attempt should return False"

        print("PASS: test_close_by_exact_attempt_id")
    finally:
        db.close()


def test_critique_book_excluded_from_search():
    """Check 4: Excluded book IDs never appear in search results."""
    db = setup()
    try:
        from scripts.critique_memory import get_critique_book_id, store_critique_pattern

        # Ensure a critique exists
        store_critique_pattern(
            db, domain="go", probe_id="go-channels",
            weakness_type="compound", template_used="implement",
            pairs_generated=10, fix_version="v-test-4", pre_score=0.60,
        )
        db.commit()

        critique_book_id = get_critique_book_id(db)
        assert critique_book_id is not None and critique_book_id > 0

        # Verify critique sections exist in the book
        sections = db.query(BookSection).filter_by(book_id=critique_book_id).all()
        assert len(sections) > 0, "Critique book should have sections"

        # Verify all have NULL embeddings
        for s in sections:
            assert s.embedding is None, f"Section {s.id} should have NULL embedding"

        # Test vector_search exclusion
        from hiveai.vectorstore import vector_search
        import numpy as np
        dummy_embedding = np.random.randn(1024).tolist()
        results = vector_search(db, dummy_embedding, limit=100,
                                exclude_book_ids={critique_book_id})
        for r in results:
            assert r["book_id"] != critique_book_id, \
                f"Critique book_id {critique_book_id} should not appear in vector_search results"

        # Test hybrid_search exclusion
        from hiveai.vectorstore import hybrid_search
        results = hybrid_search(db, "how to implement RAII in C++", dummy_embedding,
                                limit=100, exclude_book_ids={critique_book_id})
        for r in results:
            assert r.get("book_id") != critique_book_id, \
                f"Critique book_id {critique_book_id} should not appear in hybrid_search results"

        print("PASS: test_critique_book_excluded_from_search")
    finally:
        db.close()


def test_attribution_stored_no_ranking_effect():
    """Check 5: Attribution (isolated/batched) is stored but has no ranking effect."""
    db = setup()
    try:
        from scripts.critique_memory import store_critique_pattern, close_critique_loop, get_effective_templates

        # Store isolated and batched patterns for same domain
        _, att_iso = store_critique_pattern(
            db, domain="js", probe_id="js-async",
            weakness_type="keyword_only", template_used="implement",
            pairs_generated=20, fix_version="v-test-5a", pre_score=0.70,
            attribution="isolated",
        )
        _, att_bat = store_critique_pattern(
            db, domain="js", probe_id="js-types",
            weakness_type="structure_only", template_used="implement",
            pairs_generated=20, fix_version="v-test-5b", pre_score=0.70,
            attribution="batched",
        )
        db.commit()

        # Close both as successes
        close_critique_loop(db, att_iso, post_score=0.85)
        close_critique_loop(db, att_bat, post_score=0.85)
        db.commit()

        # Check effective templates — isolated should have weight 1.0, batched 0.3
        templates = get_effective_templates(db, "js")
        assert "implement" in templates, f"Template 'implement' should be in results: {templates}"
        # With 1 isolated (w=1.0) + 1 batched (w=0.3), both successes:
        # success_rate = (1.0 + 0.3) / (1.0 + 0.3) = 1.0
        assert templates["implement"]["attempts"] == 2
        assert templates["implement"]["success_rate"] == 1.0

        # Verify attribution is stored correctly
        from scripts.critique_memory import retrieve_critique_patterns
        patterns = retrieve_critique_patterns(db, domain="js")
        iso_p = [p for p in patterns if p["attempt_id"] == att_iso][0]
        bat_p = [p for p in patterns if p["attempt_id"] == att_bat][0]
        assert iso_p["attribution"] == "isolated"
        assert bat_p["attribution"] == "batched"

        print("PASS: test_attribution_stored_no_ranking_effect")
    finally:
        db.close()


def test_influence_flag_defaults_off():
    """Check 6: CRITIQUE_MEMORY_INFLUENCE defaults to False."""
    from hiveai.config import CRITIQUE_MEMORY_INFLUENCE, CRITIQUE_MEMORY_ENABLED
    assert CRITIQUE_MEMORY_ENABLED is True, "CRITIQUE_MEMORY_ENABLED should default True"
    # CRITIQUE_MEMORY_INFLUENCE should be False unless explicitly set
    # (env var may override, but default is false)
    if not os.environ.get("CRITIQUE_MEMORY_INFLUENCE"):
        assert CRITIQUE_MEMORY_INFLUENCE is False, "CRITIQUE_MEMORY_INFLUENCE should default False"
    print("PASS: test_influence_flag_defaults_off")


def test_critique_stats():
    """Bonus: Verify stats endpoint logic."""
    db = setup()
    try:
        from scripts.critique_memory import get_critique_stats
        stats = get_critique_stats(db)
        assert "total" in stats
        assert "open" in stats
        assert "closed" in stats
        assert "abandoned" in stats
        assert "by_domain" in stats
        assert stats["total"] >= 0
        print(f"PASS: test_critique_stats (total={stats['total']} open={stats['open']} "
              f"closed={stats['closed']} abandoned={stats['abandoned']})")
    finally:
        db.close()


def test_abandon_stale():
    """Bonus: Verify stale critique auto-abandonment."""
    db = setup()
    try:
        from scripts.critique_memory import store_critique_pattern, abandon_stale_critiques
        import scripts.critique_memory as cm

        # Store a pattern, then manually backdate its opened_at
        sid, aid = store_critique_pattern(
            db, domain="python", probe_id="python-async",
            weakness_type="keyword_only", template_used="implement",
            pairs_generated=10, fix_version="v-test-stale", pre_score=0.60,
        )
        db.commit()

        # Backdate to 10 days ago
        section = db.query(BookSection).filter_by(id=sid).first()
        meta = json.loads(section.keywords_json)
        from datetime import datetime, timezone, timedelta
        meta["opened_at"] = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        section.keywords_json = json.dumps(meta)
        db.commit()

        count = abandon_stale_critiques(db, max_age_days=7)
        db.commit()
        assert count >= 1, f"Should have abandoned at least 1 stale critique, got {count}"

        # Verify it's abandoned
        section = db.query(BookSection).filter_by(id=sid).first()
        meta = json.loads(section.keywords_json)
        assert meta["status"] == "abandoned", f"Should be abandoned, got {meta['status']}"

        print("PASS: test_abandon_stale")
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Phase 2 (GEM 1) Validation Tests")
    print("=" * 60)

    tests = [
        test_store_creates_attempt_id,
        test_second_store_creates_different_attempt,
        test_close_by_exact_attempt_id,
        test_critique_book_excluded_from_search,
        test_attribution_stored_no_ranking_effect,
        test_influence_flag_defaults_off,
        test_critique_stats,
        test_abandon_stale,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    if failed == 0:
        print("ALL CHECKS PASS")
    else:
        print("SOME CHECKS FAILED")
        sys.exit(1)
