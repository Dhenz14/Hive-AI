"""Burn-in checklist: real traces through telemetry code paths."""
import json
import os
import uuid

os.environ["DATABASE_URL"] = "sqlite://"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from hiveai.models import Base, TelemetryEvent
from hiveai.telemetry import (
    assign_experiment_group, generate_request_id, generate_answer_id, generate_attempt_id,
    should_inject_memory, should_show_surface,
    classify_workflow, detect_language, best_confidence_band,
    record_client_event, aggregate_product_review, _DropCounter,
)

engine = create_engine("sqlite://")
Base.metadata.create_all(engine)
TestSession = sessionmaker(bind=engine)


def direct_log(db, **kwargs):
    evt = TelemetryEvent(**kwargs)
    db.add(evt)
    db.commit()
    return evt


def find_session_for_group(target, prefix="s"):
    for i in range(500):
        sid = f"{prefix}-{i}"
        if assign_experiment_group(sid, 15, 15) == target:
            return sid
    raise RuntimeError(f"Could not find session for {target}")


def main():
    db = TestSession()

    # --- TRACE 1: Treatment ---
    print("=== TRACE 1: Treatment ===")
    sid_t = find_session_for_group("treatment", "t")
    g = assign_experiment_group(sid_t, 15, 15)
    assert g == "treatment"
    assert should_inject_memory(g) and should_show_surface(g)

    ans1 = generate_answer_id()
    direct_log(db,
        request_id=generate_request_id(), answer_id=ans1, attempt_id=generate_attempt_id(),
        session_id=sid_t, experiment_group=g,
        memory_available=True, memory_context_injected=True, memory_surface_emitted=True,
        solved_example_count=2, confidence_band="high",
        workflow_class="utility", language_detected="python",
        verification_passed=1, verification_failed=0, verification_total=1,
        is_terminal_attempt=True, latency_total_ms=1234.5,
        workflow_classifier_version="v1", language_detector_version="v1",
        model_id="hiveai", git_sha="abc1234",
        verifier_mode="generated_assertions", frontend_build="v2.1.0",
    )
    print(f"  group={g}, inject=True, surface=True, logged OK")

    # --- TRACE 2: Holdout Surface ---
    print("\n=== TRACE 2: Holdout Surface ===")
    sid_hs = find_session_for_group("holdout_surface", "hs")
    g_hs = assign_experiment_group(sid_hs, 15, 15)
    assert g_hs == "holdout_surface"
    assert should_inject_memory(g_hs) and not should_show_surface(g_hs)

    ans2 = generate_answer_id()
    direct_log(db,
        request_id=generate_request_id(), answer_id=ans2, attempt_id=generate_attempt_id(),
        session_id=sid_hs, experiment_group=g_hs,
        memory_available=True, memory_context_injected=True, memory_surface_emitted=False,
        solved_example_count=1, confidence_band="good",
        workflow_class="algorithm", language_detected="rust",
        verification_passed=1, verification_failed=0, verification_total=1,
        is_terminal_attempt=True, latency_total_ms=987.3,
        workflow_classifier_version="v1", language_detector_version="v1",
        model_id="hiveai", git_sha="abc1234",
    )
    print(f"  group={g_hs}, inject=True, surface=False, logged OK")

    # --- TRACE 3: No Injection ---
    print("\n=== TRACE 3: No Injection ===")
    sid_ni = find_session_for_group("no_injection", "ni")
    g_ni = assign_experiment_group(sid_ni, 15, 15)
    assert g_ni == "no_injection"
    assert not should_inject_memory(g_ni) and not should_show_surface(g_ni)

    ans3 = generate_answer_id()
    direct_log(db,
        request_id=generate_request_id(), answer_id=ans3, attempt_id=generate_attempt_id(),
        session_id=sid_ni, experiment_group=g_ni,
        memory_available=True, memory_context_injected=False, memory_surface_emitted=False,
        solved_example_count=1, confidence_band="high",
        workflow_class="hive", language_detected="python",
        verification_passed=0, verification_failed=1, verification_total=1,
        is_terminal_attempt=True, latency_total_ms=876.1,
        workflow_classifier_version="v1", language_detector_version="v1",
        model_id="hiveai", git_sha="abc1234",
    )
    print(f"  group={g_ni}, inject=False, surface=False")
    print("  memory_available=True but memory_context_injected=False, logged OK")

    # --- TRACE 4: Revision Lineage ---
    print("\n=== TRACE 4: Revision Lineage ===")
    req4 = generate_request_id()
    ans4a = generate_answer_id()
    ans4b = generate_answer_id()

    direct_log(db,
        request_id=req4, answer_id=ans4a, attempt_id=generate_attempt_id(),
        session_id=sid_t, experiment_group="treatment",
        memory_available=True, memory_context_injected=True, memory_surface_emitted=True,
        verification_passed=0, verification_failed=1, verification_total=1,
        is_terminal_attempt=False, final_answer_id=ans4b,
        latency_total_ms=1100.0,
        workflow_classifier_version="v1", language_detector_version="v1",
        model_id="hiveai", git_sha="abc1234",
    )
    direct_log(db,
        request_id=req4, answer_id=ans4b, attempt_id=generate_attempt_id(),
        session_id=sid_t, experiment_group="treatment",
        memory_available=True, memory_context_injected=True, memory_surface_emitted=True,
        verification_passed=1, verification_failed=0, verification_total=1,
        was_revised=True, is_terminal_attempt=True, parent_answer_id=ans4a,
        latency_total_ms=2200.0,
        workflow_classifier_version="v1", language_detector_version="v1",
        model_id="hiveai", git_sha="abc1234",
    )

    e4a = db.query(TelemetryEvent).filter(TelemetryEvent.answer_id == ans4a).first()
    e4b = db.query(TelemetryEvent).filter(TelemetryEvent.answer_id == ans4b).first()
    assert e4a.is_terminal_attempt is False
    assert e4a.final_answer_id == ans4b
    assert e4b.is_terminal_attempt is True
    assert e4b.parent_answer_id == ans4a
    assert e4b.was_revised is True
    print(f"  attempt1: terminal=False, final_answer={ans4b[:12]}...")
    print(f"  attempt2: terminal=True, parent={ans4a[:12]}..., revised=True")
    print("  Lineage: OK")

    # --- TRACE 5: Outcome State Machine ---
    print("\n=== TRACE 5: Outcome State Machine ===")
    r = record_client_event(db, ans1, "retry")
    assert r["status"] == "ok"
    evt = db.query(TelemetryEvent).filter(TelemetryEvent.answer_id == ans1).first()
    assert evt.user_retried is True
    assert evt.explicit_accept is None
    print(f"  retry: user_retried=True, explicit_accept=None")

    r = record_client_event(db, ans1, "explicit_accept")
    assert r["status"] == "ok"
    db.refresh(evt)
    assert evt.explicit_accept is True
    print(f"  accept after retry: explicit_accept=True (transition allowed)")

    r = record_client_event(db, ans1, "thumbs_down")
    assert r["status"] == "ok"
    db.refresh(evt)
    assert evt.explicit_accept is False
    seq = json.loads(evt.outcome_sequence_json)
    assert len(seq) == 3
    assert [s["event"] for s in seq] == ["retry", "explicit_accept", "thumbs_down"]
    print(f"  reject after accept: explicit_accept=False (transition allowed)")
    print(f"  sequence: {[s['event'] for s in seq]}")
    print("  State machine: OK")

    # --- TRACE 6: Engagement Idempotency ---
    print("\n=== TRACE 6: Engagement Events ===")
    r = record_client_event(db, ans1, "details_expand")
    assert r["status"] == "ok"
    r = record_client_event(db, ans1, "details_expand")
    assert r["status"] == "already_recorded"
    r = record_client_event(db, ans1, "pattern_click")
    assert r["status"] == "ok"
    db.refresh(evt)
    assert evt.details_expanded is True
    assert evt.pattern_clicked is True
    print("  expand: True (duplicate correctly blocked)")
    print("  click: True")
    print("  Idempotency: OK")

    # --- TRACE 7: Drop Simulation ---
    print("\n=== TRACE 7: Drop Simulation ===")
    dc = _DropCounter()
    # Small count: contamination flag requires >10 total drops (avoids noise)
    for _ in range(4):
        dc.record_drop("treatment")
    dc.record_drop("no_injection")
    snap_small = dc.snapshot()
    assert snap_small["total_dropped"] == 5
    assert snap_small["arm_contaminated"]["treatment"] is False  # under threshold (total<=10)
    print(f"  Small drops ({snap_small['total_dropped']}): no contamination flag (correct, too few)")

    # Large count: trigger contamination
    for _ in range(10):
        dc.record_drop("treatment")
    snap_large = dc.snapshot()
    assert snap_large["total_dropped"] == 15
    assert snap_large["arm_contaminated"]["treatment"] is True   # 14/15=93% > 60%, total>10
    assert snap_large["arm_contaminated"]["no_injection"] is False
    print(f"  Large drops ({snap_large['total_dropped']}): treatment contaminated=True")
    print(f"  Policy: {snap_large['invalidation_policy']['arm_rule']}")
    print("  Drop tracking: OK")

    # --- TRACE 8: Full Aggregation ---
    print("\n=== TRACE 8: Aggregation ===")
    review = aggregate_product_review(db)
    assert review["total_events"] == 5
    assert review["treatment"]["count"] == 3
    assert review["holdout_surface"]["count"] == 1
    assert review["no_injection"]["count"] == 1
    assert "srm_checks" in review
    assert "drop_analysis" in review
    assert "reproducibility" in review
    assert review["treatment"]["user_outcomes"]["retried"] == 1
    assert review["treatment"]["user_outcomes"]["details_expanded"] == 1
    print(f"  total_events: {review['total_events']}")
    print(f"  treatment: {review['treatment']['count']}")
    print(f"  holdout_surface: {review['holdout_surface']['count']}")
    print(f"  no_injection: {review['no_injection']['count']}")
    print(f"  SRM: {review['srm_checks']['global']['status']}")
    print("  Aggregation: OK")

    db.close()

    print("\n" + "=" * 60)
    print("ALL BURN-IN TRACES PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
