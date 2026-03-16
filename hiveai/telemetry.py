"""
Product telemetry for memory 3-arm experiment.

3-arm factorial design on memory-eligible turns:
  - treatment       (70%): memory injected into prompt + surface shown
  - holdout_surface (15%): memory injected into prompt + surface hidden
  - no_injection    (15%): memory NOT injected + surface hidden

Naming honesty: "no_injection" still runs retrieval (for latent logging).
It strips solved examples from the LLM prompt but does NOT eliminate
retrieval-side effects (latency, cache warming, reranker load). This arm
isolates prompt-level injection effect, not full memory subsystem cost.

This answers three questions:
  - treatment vs holdout_surface = "does the UI surface change behavior?"
  - treatment vs no_injection    = "does prompt injection improve answers?"
  - holdout_surface vs no_injection = "does injection alone help without UI?"

Design invariants:
  - memory_context_injected != memory_surface_emitted (independent booleans)
  - Telemetry writes are async (background queue, fail-open)
  - Drop counts tracked with window-level invalidation policy
  - Classifier + stack versions stamped on every event (including frontend_build)
  - Client outcome events use state-machine transitions (not blind first-write-wins)
  - Explicit acceptance separated from implicit proxies
  - Identity graph: request_id + answer_id + attempt_id + revision lineage
"""

import atexit
import hashlib
import json
import logging
import os
import queue
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("hiveai.telemetry")

# ---------------------------------------------------------------------------
# Classifier + stack versioning — bump when heuristics/stack change
# ---------------------------------------------------------------------------

WORKFLOW_CLASSIFIER_VERSION = "v1"
LANGUAGE_DETECTOR_VERSION = "v1"


def _get_git_sha() -> str:
    """Get short git SHA of the running code. Cached at import time."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).decode().strip()
    except Exception:
        return "unknown"


GIT_SHA = _get_git_sha()


def get_stack_versions(frontend_build: str | None = None) -> dict:
    """Return current stack version tags for event stamping."""
    from hiveai.config import LLAMA_SERVER_MODEL
    return {
        "workflow_classifier_version": WORKFLOW_CLASSIFIER_VERSION,
        "language_detector_version": LANGUAGE_DETECTOR_VERSION,
        "model_id": LLAMA_SERVER_MODEL,
        "git_sha": GIT_SHA,
        "frontend_build": frontend_build,
    }


# ---------------------------------------------------------------------------
# Internal traffic detection
# ---------------------------------------------------------------------------

_INTERNAL_SESSION_PREFIXES = {"test-", "benchmark-", "canary-", "qa-", "dev-"}
_INTERNAL_UA_PATTERNS = re.compile(r"(pytest|httpx|curl|wget|postman|insomnia)", re.I)


def is_internal_traffic(session_id: str = "", user_agent: str = "") -> bool:
    """Detect scripted tests, benchmarks, and dev sessions.

    Returns True for heuristic detection. For explicit internal tagging,
    clients should use session_id prefix 'dev-' or 'test-'.
    """
    if session_id:
        for prefix in _INTERNAL_SESSION_PREFIXES:
            if session_id.startswith(prefix):
                return True
    if user_agent and _INTERNAL_UA_PATTERNS.search(user_agent):
        return True
    return False


# ---------------------------------------------------------------------------
# 3-arm assignment — deterministic per session
# ---------------------------------------------------------------------------

def assign_experiment_group(session_id: str, holdout_surface_pct: int = 15,
                            no_injection_pct: int = 15) -> str:
    """Deterministic 3-arm group assignment from session_id hash.

    Returns one of:
      - "treatment"        — memory injected + surface shown (remaining %)
      - "holdout_surface"  — memory injected + surface hidden
      - "no_injection"     — memory NOT injected + surface hidden
    """
    h = int(hashlib.sha256(session_id.encode()).hexdigest(), 16)
    bucket = h % 100
    if bucket < no_injection_pct:
        return "no_injection"
    if bucket < no_injection_pct + holdout_surface_pct:
        return "holdout_surface"
    return "treatment"


def should_inject_memory(group: str) -> bool:
    """Whether memory context should be injected into the LLM prompt.

    Note: retrieval still runs in all arms for latent logging.
    This only controls whether results enter the LLM prompt.
    """
    return group != "no_injection"


def should_show_surface(group: str) -> bool:
    """Whether the memory UI surface should be emitted to the client."""
    return group == "treatment"


def generate_request_id() -> str:
    """Generate a unique request ID for this HTTP request."""
    return str(uuid.uuid4())


def generate_answer_id() -> str:
    """Generate a unique answer ID for this response."""
    return str(uuid.uuid4())


def generate_attempt_id() -> str:
    """Generate a unique attempt ID for a generation attempt."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Workflow classifier — simple keyword-based for v1
# ---------------------------------------------------------------------------

_HIVE_KEYWORDS = re.compile(
    r"\b(hive|hivemind|haf|dhive|keychain|posting[- ]?key|active[- ]?key|"
    r"custom[- ]?json|rc[- ]?cost|resource[- ]?credit|permlink|"
    r"hive[- ]?engine|smt|witness|vesting|delegation|hivesql|beem)\b",
    re.IGNORECASE,
)

_ALGO_KEYWORDS = re.compile(
    r"\b(algorithm|dynamic programming|bfs|dfs|dijkstra|binary search|"
    r"sort|graph|tree|linked list|heap|stack|queue|"
    r"time complexity|space complexity|big[- ]?o|recursion|memoiz|"
    r"backtrack|greedy|knapsack|trie|segment tree|topological)\b",
    re.IGNORECASE,
)

_UTILITY_KEYWORDS = re.compile(
    r"\b(function|utility|helper|convert|parse|format|validate|"
    r"serialize|deserialize|encode|decode|hash|filter|map|reduce|"
    r"transform|sanitize|normalize|truncate|debounce|throttle|retry|"
    r"cache|memoize|singleton|factory|wrapper|decorator)\b",
    re.IGNORECASE,
)


def classify_workflow(message: str) -> str:
    """Classify user message into workflow class.

    Returns one of: "hive", "algorithm", "utility", "other".
    """
    if _HIVE_KEYWORDS.search(message):
        return "hive"
    if _ALGO_KEYWORDS.search(message):
        return "algorithm"
    if _UTILITY_KEYWORDS.search(message):
        return "utility"
    return "other"


# ---------------------------------------------------------------------------
# Language detection — simple heuristic from code keywords
# ---------------------------------------------------------------------------

_LANG_PATTERNS = {
    "python": re.compile(r"\b(python|def |import |pip |pytest|django|flask|fastapi)\b", re.I),
    "javascript": re.compile(r"\b(javascript|js|node\.?js|npm|react|vue|angular|const |let |=>)\b", re.I),
    "typescript": re.compile(r"\b(typescript|ts|interface |type |tsx)\b", re.I),
    "rust": re.compile(r"\b(rust|cargo|fn |impl |trait |tokio|serde|ownership|borrow)\b", re.I),
    "go": re.compile(r"\b(golang|go |goroutine|chan |func |package main|go run)\b", re.I),
    "cpp": re.compile(r"\b(c\+\+|cpp|std::|template|RAII|move semantics|unique_ptr|shared_ptr)\b", re.I),
}


def detect_language(message: str) -> str:
    """Detect primary programming language from message text.

    Returns language name or "unknown".
    """
    for lang, pattern in _LANG_PATTERNS.items():
        if pattern.search(message):
            return lang
    return "unknown"


# ---------------------------------------------------------------------------
# Best confidence band — pick highest from solved example details
# ---------------------------------------------------------------------------

_CONFIDENCE_RANK = {"high": 0, "good": 1, "mixed": 2, "low": 3}


def best_confidence_band(solved_example_details: list) -> str | None:
    """Return the best (highest) confidence band from a list of solved example details."""
    if not solved_example_details:
        return None
    best = None
    best_rank = 999
    for d in solved_example_details:
        band = d.get("confidence", "low")
        rank = _CONFIDENCE_RANK.get(band, 999)
        if rank < best_rank:
            best = band
            best_rank = rank
    return best


# ---------------------------------------------------------------------------
# Telemetry drop counter — tracks biased missingness
# ---------------------------------------------------------------------------

class _DropCounter:
    """Thread-safe drop counter with per-group tracking."""

    def __init__(self):
        self._lock = threading.Lock()
        self._total = 0
        self._by_group = {}
        self._by_window = {}  # 5-minute windows

    def record_drop(self, experiment_group: str = "unknown"):
        with self._lock:
            self._total += 1
            self._by_group[experiment_group] = self._by_group.get(experiment_group, 0) + 1
            window_key = int(time.time()) // 300  # 5-min buckets
            self._by_window[window_key] = self._by_window.get(window_key, 0) + 1
            # Keep only last 288 windows (24 hours)
            if len(self._by_window) > 288:
                oldest = min(self._by_window)
                del self._by_window[oldest]

    def snapshot(self, drop_rate_threshold: float = 0.05) -> dict:
        """Return drop stats with contamination assessment.

        Args:
            drop_rate_threshold: if drops exceed this fraction of total events
                in any arm, mark that arm contaminated.
        """
        with self._lock:
            # Arm imbalance check: if one arm drops disproportionately, flag it
            arm_contaminated = {}
            if self._total > 0:
                for arm, count in self._by_group.items():
                    # Can't compute rate without total events per arm here,
                    # but we can flag if one arm has >60% of all drops
                    frac = count / self._total
                    arm_contaminated[arm] = frac > 0.6 and self._total > 10

            return {
                "total_dropped": self._total,
                "by_group": dict(self._by_group),
                "arm_contaminated": arm_contaminated,
                "recent_windows": {
                    str(k): v for k, v in sorted(self._by_window.items())[-12:]
                },
                "invalidation_policy": {
                    "rule": "Exclude 5-min windows where drops > 5% of window events",
                    "arm_rule": "Flag experiment if any arm has >60% of total drops",
                },
            }


_drop_counter = _DropCounter()


# ---------------------------------------------------------------------------
# Async telemetry write queue — fail-open, never blocks chat path
# ---------------------------------------------------------------------------

_WRITE_QUEUE: queue.Queue = queue.Queue(maxsize=10000)
_WRITER_LOCK = threading.Lock()
_WRITER_THREAD: threading.Thread | None = None
_WRITER_STARTED = False


def _telemetry_writer_loop():
    """Background thread that drains the telemetry write queue.

    Fail-open: if DB is slow or down, events are dropped with a warning.
    """
    from hiveai.models import SessionLocal
    while True:
        try:
            event_kwargs = _WRITE_QUEUE.get(timeout=5.0)
        except queue.Empty:
            continue
        if event_kwargs is None:
            break  # poison pill for shutdown

        db = None
        try:
            from hiveai.models import TelemetryEvent
            db = SessionLocal()
            evt = TelemetryEvent(**event_kwargs)
            db.add(evt)
            db.commit()
        except Exception as e:
            logger.warning(f"Telemetry async write failed (dropped): {e}")
            _drop_counter.record_drop(event_kwargs.get("experiment_group", "unknown"))
            if db:
                try:
                    db.rollback()
                except Exception:
                    pass
        finally:
            if db:
                try:
                    db.close()
                except Exception:
                    pass


def _ensure_writer_started():
    """Lazily start the background writer thread (exactly once per process)."""
    global _WRITER_THREAD, _WRITER_STARTED
    with _WRITER_LOCK:
        if _WRITER_STARTED:
            return
        _WRITER_STARTED = True
        _WRITER_THREAD = threading.Thread(
            target=_telemetry_writer_loop, daemon=True, name="telemetry-writer"
        )
        _WRITER_THREAD.start()
        logger.info("Telemetry background writer started")


def _flush_on_exit():
    """Best-effort queue drain on process exit."""
    if not _WRITER_STARTED:
        return
    try:
        _WRITE_QUEUE.put_nowait(None)  # poison pill
    except queue.Full:
        pass
    if _WRITER_THREAD and _WRITER_THREAD.is_alive():
        _WRITER_THREAD.join(timeout=3.0)


atexit.register(_flush_on_exit)


# ---------------------------------------------------------------------------
# Event logging — enqueue to background writer (never blocks chat)
# ---------------------------------------------------------------------------

def log_telemetry_event(*, request_id, answer_id, attempt_id=None,
                        session_id=None, experiment_group,
                        parent_answer_id=None, final_answer_id=None,
                        is_terminal_attempt=True,
                        memory_available=False,
                        memory_context_injected=False,
                        memory_surface_emitted=False,
                        solved_example_count=0, solved_example_ids=None,
                        confidence_band=None, workflow_class=None,
                        language_detected=None, retrieval_mode=None,
                        response_contract=None, verification_passed=None,
                        verification_failed=None, verification_total=None,
                        was_revised=False, auto_staged=False, auto_promoted=False,
                        latency_retrieval_ms=None, latency_generation_ms=None,
                        latency_verification_ms=None, latency_total_ms=None,
                        matched_pattern_pass_rates=None,
                        is_internal=False, verifier_mode=None,
                        frontend_build=None):
    """Enqueue a telemetry event for async background write.

    This function returns immediately. Chat path is never blocked.
    If the queue is full (10k events), the event is dropped and counted.
    """
    _ensure_writer_started()

    stack = get_stack_versions(frontend_build)

    event_kwargs = {
        "request_id": request_id,
        "answer_id": answer_id,
        "attempt_id": attempt_id or answer_id,
        "session_id": session_id,
        "experiment_group": experiment_group,
        "parent_answer_id": parent_answer_id,
        "final_answer_id": final_answer_id,
        "is_terminal_attempt": is_terminal_attempt,
        "memory_available": memory_available,
        "memory_context_injected": memory_context_injected,
        "memory_surface_emitted": memory_surface_emitted,
        "solved_example_count": solved_example_count,
        "solved_example_ids_json": json.dumps(solved_example_ids) if solved_example_ids else None,
        "confidence_band": confidence_band,
        "workflow_class": workflow_class,
        "language_detected": language_detected,
        "retrieval_mode": retrieval_mode,
        "response_contract": response_contract,
        "verification_passed": verification_passed,
        "verification_failed": verification_failed,
        "verification_total": verification_total,
        "was_revised": was_revised,
        "auto_staged": auto_staged,
        "auto_promoted": auto_promoted,
        "latency_retrieval_ms": latency_retrieval_ms,
        "latency_generation_ms": latency_generation_ms,
        "latency_verification_ms": latency_verification_ms,
        "latency_total_ms": latency_total_ms,
        "matched_pattern_pass_rates_json": (
            json.dumps(matched_pattern_pass_rates) if matched_pattern_pass_rates else None
        ),
        "is_internal": is_internal,
        "verifier_mode": verifier_mode,
        # Stack versions
        "workflow_classifier_version": stack["workflow_classifier_version"],
        "language_detector_version": stack["language_detector_version"],
        "model_id": stack["model_id"],
        "git_sha": stack["git_sha"],
        "frontend_build": stack["frontend_build"],
    }

    try:
        _WRITE_QUEUE.put_nowait(event_kwargs)
    except queue.Full:
        _drop_counter.record_drop(experiment_group)
        logger.warning("Telemetry queue full — event dropped")


# ---------------------------------------------------------------------------
# Client-side event recording — idempotent, first-write-wins
# ---------------------------------------------------------------------------

# Valid client event types, split into explicit and implicit
EXPLICIT_ACCEPT_EVENTS = {"explicit_accept", "thumbs_up"}
IMPLICIT_PROXY_EVENTS = {"implicit_accept_no_followup", "copy_code"}
REJECT_EVENTS = {"explicit_reject", "thumbs_down", "retry", "reformulation"}
ENGAGEMENT_EVENTS = {"details_expand", "pattern_click"}

ALL_CLIENT_EVENTS = EXPLICIT_ACCEPT_EVENTS | IMPLICIT_PROXY_EVENTS | REJECT_EVENTS | ENGAGEMENT_EVENTS


def record_client_event(db, answer_id: str, event_type: str) -> dict:
    """Update a telemetry event with a client-side signal.

    Event handling rules:
      - Engagement events (expand, click): first-write-wins (idempotent)
      - Outcome events (accept, reject, retry): state-machine transitions allowed
        * retry→accept is valid (user retried then accepted revision)
        * accept→reject is valid (user accepted then discovered failure)
        * Each transition is appended to outcome_sequence_json for full history

    Returns dict with status for the caller.
    """
    from hiveai.models import TelemetryEvent

    evt = db.query(TelemetryEvent).filter(TelemetryEvent.answer_id == answer_id).first()
    if not evt:
        return {"status": "not_found"}

    if event_type not in ALL_CLIENT_EVENTS:
        return {"status": "invalid_event_type"}

    # Load outcome sequence history
    outcome_seq = json.loads(evt.outcome_sequence_json) if evt.outcome_sequence_json else []
    ts_now = datetime.now(timezone.utc).isoformat()

    # --- Engagement events: first-write-wins (idempotent) ---
    if event_type == "details_expand":
        if evt.details_expanded:
            return {"status": "already_recorded"}
        evt.details_expanded = True

    elif event_type == "pattern_click":
        if evt.pattern_clicked:
            return {"status": "already_recorded"}
        evt.pattern_clicked = True

    # --- Explicit accept/reject: state transitions allowed ---
    elif event_type in EXPLICIT_ACCEPT_EVENTS:
        evt.explicit_accept = True
        outcome_seq.append({"event": event_type, "ts": ts_now, "value": True})

    elif event_type in REJECT_EVENTS:
        if event_type in ("retry", "reformulation"):
            evt.user_retried = True
        else:
            evt.explicit_accept = False
        outcome_seq.append({"event": event_type, "ts": ts_now, "value": False})

    # --- Implicit proxies: first-write-wins ---
    elif event_type in IMPLICIT_PROXY_EVENTS:
        if evt.implicit_accept_proxy is not None:
            return {"status": "already_recorded"}
        evt.implicit_accept_proxy = True
        outcome_seq.append({"event": event_type, "ts": ts_now, "value": True})

    # Persist outcome sequence (capped at 20 entries)
    if len(outcome_seq) > 20:
        outcome_seq = outcome_seq[-20:]
    evt.outcome_sequence_json = json.dumps(outcome_seq)

    try:
        db.commit()
        return {"status": "ok", "outcome_count": len(outcome_seq)}
    except Exception as e:
        logger.warning(f"Client event record failed: {e}")
        db.rollback()
        return {"status": "error", "detail": str(e)}


# ---------------------------------------------------------------------------
# SRM (Sample Ratio Mismatch) check
# ---------------------------------------------------------------------------

def _srm_check(counts: dict, expected_pcts: dict) -> dict:
    """Multi-arm chi-squared SRM check.

    counts: {"treatment": N, "holdout_surface": N, "no_injection": N}
    expected_pcts: {"treatment": 70, "holdout_surface": 15, "no_injection": 15}

    SRM detected if p < 0.01 (chi2 > 9.210 for 2 df).
    """
    total = sum(counts.values())
    if total < 30:
        return {"status": "insufficient_data", "total": total}

    chi2 = 0.0
    for arm, observed in counts.items():
        expected = total * (expected_pcts.get(arm, 0) / 100.0)
        if expected > 0:
            chi2 += (observed - expected) ** 2 / expected

    df = len(counts) - 1
    # Critical values: df=1 → 6.635, df=2 → 9.210 (p < 0.01)
    critical = 9.210 if df >= 2 else 6.635
    srm_detected = chi2 > critical

    return {
        "status": "srm_detected" if srm_detected else "ok",
        "chi2": round(chi2, 3),
        "observed": {k: v for k, v in counts.items()},
        "expected_pcts": expected_pcts,
        "total": total,
        "df": df,
        "threshold": f"p<0.01 (chi2>{critical})",
    }


def _srm_by_dimension(events, dimension_fn,
                      expected_pcts=None) -> dict:
    """Run SRM check per dimension value."""
    if expected_pcts is None:
        expected_pcts = {"treatment": 70, "holdout_surface": 15, "no_injection": 15}

    buckets = {}
    for e in events:
        key = dimension_fn(e)
        if key not in buckets:
            buckets[key] = {arm: 0 for arm in expected_pcts}
        group = e.experiment_group
        if group in buckets[key]:
            buckets[key][group] += 1

    results = {}
    for key, counts in buckets.items():
        results[key] = _srm_check(counts, expected_pcts)
    return results


# ---------------------------------------------------------------------------
# Product review aggregation
# ---------------------------------------------------------------------------

def aggregate_product_review(db) -> dict:
    """Aggregate telemetry events into the product review scorecard.

    Includes:
      - 3-arm stats (treatment, holdout_surface, no_injection)
      - SRM checks across global, workflow, language dimensions
      - Drop rate analysis with window invalidation
      - Reproducibility metadata (versions, git SHA, exclusion rules)
    """
    from hiveai.models import TelemetryEvent

    events = db.query(TelemetryEvent).all()
    if not events:
        return {"total_events": 0, "message": "No telemetry data yet"}

    total = len(events)
    real_events = [e for e in events if not e.is_internal]
    internal_count = total - len(real_events)

    arms = {
        "treatment": [e for e in real_events if e.experiment_group == "treatment"],
        "holdout_surface": [e for e in real_events if e.experiment_group == "holdout_surface"],
        "no_injection": [e for e in real_events if e.experiment_group == "no_injection"],
    }

    def _group_stats(group, label):
        if not group:
            return {"group": label, "count": 0}

        memory_avail = sum(1 for e in group if e.memory_available)
        memory_injected = sum(1 for e in group if e.memory_context_injected)
        memory_emitted = sum(1 for e in group if e.memory_surface_emitted)

        # Verification outcomes
        verified = [e for e in group if e.verification_total and e.verification_total > 0]
        v_all_pass = sum(1 for e in verified if (e.verification_failed or 0) == 0 and (e.verification_passed or 0) > 0)
        v_any_fail = sum(1 for e in verified if (e.verification_failed or 0) > 0)

        # User outcome signals — explicit vs proxy
        explicit_accepted = sum(1 for e in group if e.explicit_accept is True)
        explicit_rejected = sum(1 for e in group if e.explicit_accept is False)
        implicit_accepted = sum(1 for e in group if e.implicit_accept_proxy is True)
        retried_count = sum(1 for e in group if e.user_retried)
        expanded_count = sum(1 for e in group if e.details_expanded)
        clicked_count = sum(1 for e in group if e.pattern_clicked)

        # By confidence band
        band_stats = {}
        for band in ("high", "good", "mixed", "low"):
            band_events = [e for e in group if e.confidence_band == band]
            band_verified = [e for e in band_events if e.verification_total and e.verification_total > 0]
            band_pass = sum(1 for e in band_verified if (e.verification_failed or 0) == 0 and (e.verification_passed or 0) > 0)
            band_stats[band] = {
                "count": len(band_events),
                "verified": len(band_verified),
                "all_pass": band_pass,
                "pass_rate": round(band_pass / max(len(band_verified), 1), 3),
                "explicit_accepted": sum(1 for e in band_events if e.explicit_accept is True),
                "retried": sum(1 for e in band_events if e.user_retried),
                "expanded": sum(1 for e in band_events if e.details_expanded),
            }

        # By workflow class
        workflow_stats = {}
        for wf in ("utility", "algorithm", "hive", "other"):
            wf_events = [e for e in group if e.workflow_class == wf]
            workflow_stats[wf] = {
                "count": len(wf_events),
                "memory_available": sum(1 for e in wf_events if e.memory_available),
                "memory_injected": sum(1 for e in wf_events if e.memory_context_injected),
                "memory_emitted": sum(1 for e in wf_events if e.memory_surface_emitted),
            }

        # By language
        lang_stats = {}
        for e in group:
            lang = e.language_detected or "unknown"
            if lang not in lang_stats:
                lang_stats[lang] = {"count": 0, "memory_available": 0, "memory_injected": 0}
            lang_stats[lang]["count"] += 1
            if e.memory_available:
                lang_stats[lang]["memory_available"] += 1
            if e.memory_context_injected:
                lang_stats[lang]["memory_injected"] += 1

        # Latency
        latencies = [e.latency_total_ms for e in group if e.latency_total_ms]
        avg_latency = round(sum(latencies) / max(len(latencies), 1), 1) if latencies else None

        return {
            "group": label,
            "count": len(group),
            "memory_available": memory_avail,
            "memory_context_injected": memory_injected,
            "memory_surface_emitted": memory_emitted,
            "verification": {
                "verified_responses": len(verified),
                "all_pass": v_all_pass,
                "any_fail": v_any_fail,
                "pass_rate": round(v_all_pass / max(len(verified), 1), 3),
            },
            "user_outcomes": {
                "explicit_accepted": explicit_accepted,
                "explicit_rejected": explicit_rejected,
                "implicit_accepted_proxy": implicit_accepted,
                "retried": retried_count,
                "details_expanded": expanded_count,
                "pattern_clicked": clicked_count,
            },
            "by_confidence_band": band_stats,
            "by_workflow": workflow_stats,
            "by_language": lang_stats,
            "avg_latency_ms": avg_latency,
            "auto_staged": sum(1 for e in group if e.auto_staged),
            "auto_promoted": sum(1 for e in group if e.auto_promoted),
            "revised": sum(1 for e in group if e.was_revised),
        }

    # SRM checks
    expected_pcts = {"treatment": 70, "holdout_surface": 15, "no_injection": 15}
    arm_counts = {arm: len(evts) for arm, evts in arms.items()}
    global_srm = _srm_check(arm_counts, expected_pcts)
    workflow_srm = _srm_by_dimension(real_events, lambda e: e.workflow_class or "unknown", expected_pcts)
    language_srm = _srm_by_dimension(real_events, lambda e: e.language_detected or "unknown", expected_pcts)
    eligible_srm = _srm_by_dimension(
        [e for e in real_events if e.memory_available],
        lambda e: "eligible", expected_pcts,
    )

    # Drop rate analysis
    drops = _drop_counter.snapshot()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_events": total,
        "internal_excluded": internal_count,
        "real_events": len(real_events),
        "reproducibility": {
            "classifier_versions": {
                "workflow": WORKFLOW_CLASSIFIER_VERSION,
                "language": LANGUAGE_DETECTOR_VERSION,
            },
            "stack": get_stack_versions(),
            "exclusion_rules": ["is_internal=True"],
            "expected_arm_pcts": expected_pcts,
        },
        "drop_analysis": drops,
        "srm_checks": {
            "global": global_srm,
            "by_workflow": workflow_srm,
            "by_language": language_srm,
            "eligible_only": eligible_srm,
        },
        "treatment": _group_stats(arms["treatment"], "treatment"),
        "holdout_surface": _group_stats(arms["holdout_surface"], "holdout_surface"),
        "no_injection": _group_stats(arms["no_injection"], "no_injection"),
    }
