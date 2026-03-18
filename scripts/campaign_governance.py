#!/usr/bin/env python3
"""
Evidence Campaign v1 — Governance Control Plane

Machine-enforced execution boundary. Every campaign artifact must carry
a governance block stamped by this module. Artifacts without valid stamps
are rejected, not warned.

This module is the SOLE source of governance truth. All other files
(session_protocol.json, operational_gates.json, pre_day4_addendum.md)
are derived/explanatory — they do NOT override constants defined here.

Hard gates:
  - Pre-v2.1 baselines: FAIL in campaign mode (not warn)
  - No-cold-start in campaign mode: FAIL (not bypass)
  - Governance mismatch: FAIL
  - Server identity change mid-session: FAIL
  - Evidence mass mismatch vs emitted manifest: FAIL
"""
import hashlib
import json
import os
import subprocess
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CAMPAIGN_DIR = PROJECT_ROOT / "evidence_campaign"

# ---------------------------------------------------------------------------
# Frozen governance constants
# ---------------------------------------------------------------------------
PROTOCOL_VERSION = "2.1"
ADDENDUM_FILE = "pre_day4_addendum.md"
CAMPAIGN_ID = "evidence_campaign_v1"

# Cold-start envelope
COLD_START_REQUIRED = True

# Dirty-tree policy: campaign mode rejects uncommitted code
DIRTY_TREE_ALLOWED_IN_CAMPAIGN = False

# Gate interpretation wording (frozen, machine-readable)
GATE_INTERPRETATIONS = {
    "gate_2": "PASS: byte-identical output on double-build under frozen inputs and seed.",
    "gate_3_binding": "PASS: no detected leakage under frozen audit logic (>=86% keyword cluster threshold).",
    "gate_3_informational": "No findings under current lens. Residual risk nonzero by construction.",
    "gate_4": "PASS: real training lifecycle proven (B2/seed=1, attempt 9cf93fce48ad). "
              "Behavioral interpretation requires measurement protocol repair: warm/modal "
              "pre-score vs cold/single-pass post-score creates confound up to 0.12 on "
              "keyword-boundary probes. A/A child-path control needed before interpreting deltas.",
}

# Bucket evidence mass (frozen pack sizes from seed=1 build)
BUCKET_EVIDENCE_MASS = {
    "B1": {"domain": "js",     "pack_size": 400, "power_class": "full"},
    "B2": {"domain": "python", "pack_size": 400, "power_class": "full"},
    "B3": {"domain": "rust",   "pack_size": 191, "power_class": "lower"},
    "B4": {"domain": "cpp",    "pack_size": 314, "power_class": "moderate"},
    "B5": {"domain": "rust",   "pack_size": 191, "power_class": "lower"},
}

# Server identity (for no-restart invariant verification)
SERVER_URL = os.environ.get("LLAMA_SERVER_URL", "http://localhost:11435")


# ---------------------------------------------------------------------------
# Atomic file operations
# ---------------------------------------------------------------------------
def atomic_write_json(path: Path, data: dict):
    """Write JSON atomically: temp file -> fsync -> rename.

    Guarantees that `path` either contains valid complete JSON or does
    not exist. No partial writes, no zero-byte files, no crash remnants.
    """
    import tempfile
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False)

    fd, tmp_path = tempfile.mkstemp(dir=str(parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_jsonl(path: Path, lines: list):
    """Write JSONL atomically: temp file -> fsync -> rename."""
    import tempfile
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=str(parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(json.dumps(line, sort_keys=True, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Executable provenance
# ---------------------------------------------------------------------------
def _file_hash(path: Path) -> str:
    """SHA256 of a file, truncated to 16 hex chars."""
    if not path.exists():
        return "MISSING"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _git_sha() -> str:
    """Current git HEAD SHA, or 'unknown' if not in a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=str(PROJECT_ROOT))
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _git_dirty() -> bool:
    """True if working tree has uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "diff", "--quiet", "HEAD"],
            capture_output=True, timeout=5,
            cwd=str(PROJECT_ROOT))
        return result.returncode != 0
    except Exception:
        return True  # assume dirty if can't check


def executable_provenance() -> dict:
    """Capture exact executable state for reproducibility."""
    return {
        "git_sha": _git_sha(),
        "git_dirty": _git_dirty(),
        "governance_hash": _file_hash(Path(__file__)),
        "session_admit_hash": _file_hash(PROJECT_ROOT / "scripts" / "session_admit.py"),
        "pack_builder_hash": _file_hash(PROJECT_ROOT / "scripts" / "campaign_pack_builder.py"),
        "dry_run_hash": _file_hash(PROJECT_ROOT / "scripts" / "campaign_dry_run.py"),
        "probe_library_hash": _file_hash(PROJECT_ROOT / "scripts" / "probe_library.py"),
    }


# ---------------------------------------------------------------------------
# Server identity (runtime no-restart verification)
# ---------------------------------------------------------------------------
def capture_server_identity() -> dict:
    """Capture server process identity for no-restart verification.

    Uses the OS-level PID of the llama-server process as the primary
    identity signal. PID changes on any restart (process, wrapper, tmux,
    host). This is more reliable than hashing /props because:
      - /props content is config-derived and may be stable across restarts
      - PID is assigned by the kernel and guaranteed unique per boot
      - PID tracks the exact property we care about: same process instance

    Falls back to /props hash if PID cannot be determined (e.g., remote server).
    """
    try:
        req = urllib.request.Request(f"{SERVER_URL}/health")
        resp = urllib.request.urlopen(req, timeout=5)
        health = json.loads(resp.read().decode())
    except Exception:
        return {"status": "unreachable", "pid": None, "boot_key": None}

    # Primary: get server PID from OS
    server_pid = None
    try:
        result = subprocess.run(
            ["pgrep", "-f", "llama-server.*--port"],
            capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            pids = result.stdout.strip().split("\n")
            # Take the first (main) process
            server_pid = int(pids[0]) if pids[0] else None
    except Exception:
        pass

    # Secondary: get /props for config fingerprint
    try:
        req = urllib.request.Request(f"{SERVER_URL}/props")
        resp = urllib.request.urlopen(req, timeout=5)
        props = json.loads(resp.read().decode())
    except Exception:
        props = {}

    # Boot key: PID is primary (changes on any restart).
    # Props hash is secondary (stable config fingerprint).
    props_hash = hashlib.sha256(
        json.dumps(props, sort_keys=True).encode()).hexdigest()[:12]

    if server_pid is not None:
        boot_key = f"pid:{server_pid}"
    else:
        boot_key = f"props:{props_hash}"

    # Also capture process start time if available (second factor)
    proc_start = None
    if server_pid:
        try:
            stat_path = Path(f"/proc/{server_pid}/stat")
            if stat_path.exists():
                fields = stat_path.read_text().split()
                # Field 22 is starttime (clock ticks since boot)
                proc_start = int(fields[21]) if len(fields) > 21 else None
        except Exception:
            pass

    return {
        "status": "ok",
        "pid": server_pid,
        "proc_start": proc_start,
        "boot_key": boot_key,
        "props_hash": props_hash,
    }


def verify_server_identity(admission_identity: dict) -> list:
    """Verify server has not restarted since admission.

    Returns list of violations. Empty = server identity unchanged.
    """
    if not admission_identity or admission_identity.get("status") != "ok":
        return ["SERVER_IDENTITY_UNKNOWN: no admission identity to compare"]

    current = capture_server_identity()
    if current.get("status") != "ok":
        return ["SERVER_UNREACHABLE: cannot verify identity"]

    violations = []
    if current.get("boot_key") != admission_identity.get("boot_key"):
        violations.append(
            f"SERVER_RESTART_DETECTED: boot_key changed from "
            f"{admission_identity.get('boot_key')} to {current.get('boot_key')}")

    return violations


# ---------------------------------------------------------------------------
# Governance stamps
# ---------------------------------------------------------------------------
def governance_stamp(
    session_id: str,
    cold_start_confirmed: bool,
    no_restart_confirmed: bool,
    server_identity: dict = None,
    campaign_eligible: bool = True,
) -> dict:
    """Generate the governance block for every campaign artifact.

    Args:
        campaign_eligible: False for exploratory/test artifacts.
            Loaders reject campaign_eligible=False in campaign mode.
    """
    prov = executable_provenance()

    # Dirty-tree auto-downgrades campaign eligibility
    if prov["git_dirty"] and not DIRTY_TREE_ALLOWED_IN_CAMPAIGN:
        campaign_eligible = False

    return {
        "campaign_id": CAMPAIGN_ID,
        "protocol_version": PROTOCOL_VERSION,
        "addendum_file": ADDENDUM_FILE,
        "addendum_hash": _file_hash(CAMPAIGN_DIR / ADDENDUM_FILE),
        "session_id": session_id,
        "cold_start_confirmed": cold_start_confirmed,
        "no_restart_confirmed": no_restart_confirmed,
        "campaign_eligible": campaign_eligible,
        "server_identity": server_identity,
        "provenance": prov,
        "gate_interpretations": GATE_INTERPRETATIONS,
    }


def attempt_stamp(
    session_id: str,
    bucket_id: str,
    attempt_id: str,
    cold_start_confirmed: bool,
    no_restart_confirmed: bool,
    server_identity: dict = None,
    actual_pack_size: int = None,
    campaign_eligible: bool = True,
) -> dict:
    """Generate governance block for a specific training attempt.

    Extends governance_stamp with bucket evidence mass and validates
    actual pack size against declared evidence mass.
    """
    base = governance_stamp(
        session_id, cold_start_confirmed, no_restart_confirmed,
        server_identity, campaign_eligible=campaign_eligible)

    declared = BUCKET_EVIDENCE_MASS.get(bucket_id, {})
    declared_size = declared.get("pack_size", "unknown")

    # Validate evidence mass if actual size provided
    mass_validated = None
    if actual_pack_size is not None:
        mass_validated = actual_pack_size == declared_size
        if not mass_validated:
            # Not a hard fail here — the mismatch is recorded and
            # validate_governance() will catch it downstream
            pass

    base["bucket_id"] = bucket_id
    base["attempt_id"] = attempt_id
    base["effective_pack_size"] = declared_size
    base["actual_pack_size"] = actual_pack_size
    base["pack_size_validated"] = mass_validated
    base["power_class"] = declared.get("power_class", "unknown")

    return base


# ---------------------------------------------------------------------------
# Validation (fail-closed in campaign mode)
# ---------------------------------------------------------------------------
class GovernanceViolation(Exception):
    """Raised when governance validation fails in campaign mode."""
    pass


def validate_governance(artifact: dict, campaign_mode: bool = True) -> list:
    """Validate artifact governance. In campaign mode, violations are fatal.

    Args:
        artifact: dict with a "governance" key.
        campaign_mode: if True, raises GovernanceViolation on any violation.

    Returns:
        list of violation strings. Empty = valid.

    Raises:
        GovernanceViolation: if campaign_mode=True and violations exist.
    """
    violations = []
    gov = artifact.get("governance")
    if not gov:
        violations.append("MISSING: no governance block")
        if campaign_mode:
            raise GovernanceViolation(
                "FATAL: artifact has no governance block. "
                "Cannot proceed in campaign mode.")
        return violations

    if gov.get("protocol_version") != PROTOCOL_VERSION:
        violations.append(
            f"VERSION_MISMATCH: expected {PROTOCOL_VERSION}, "
            f"got {gov.get('protocol_version')}")

    if gov.get("campaign_id") != CAMPAIGN_ID:
        violations.append(
            f"CAMPAIGN_MISMATCH: expected {CAMPAIGN_ID}, "
            f"got {gov.get('campaign_id')}")

    if gov.get("addendum_hash") == "MISSING":
        violations.append("ADDENDUM_MISSING: pre_day4_addendum.md not found")

    if not gov.get("cold_start_confirmed"):
        violations.append("COLD_START: server was not confirmed freshly started")

    if not gov.get("no_restart_confirmed"):
        violations.append("RESTART_VIOLATION: server restart not confirmed")

    if not gov.get("session_id"):
        violations.append("SESSION_MISSING: no session_id attached")

    # Evidence mass validation (attempt-level only)
    if "actual_pack_size" in gov and gov.get("pack_size_validated") is False:
        violations.append(
            f"EVIDENCE_MASS_MISMATCH: declared {gov.get('effective_pack_size')}, "
            f"actual {gov.get('actual_pack_size')}")

    # Campaign eligibility: exploratory artifacts cannot be consumed as evidence
    if gov.get("campaign_eligible") is False:
        violations.append(
            "NOT_CAMPAIGN_ELIGIBLE: artifact was produced in exploratory mode "
            "or from a dirty working tree. Ineligible for campaign evidence.")

    # Dirty-tree check
    prov = gov.get("provenance", {})
    if prov.get("git_dirty") and not DIRTY_TREE_ALLOWED_IN_CAMPAIGN:
        violations.append(
            "DIRTY_TREE: produced from uncommitted code. "
            "Campaign evidence requires clean working tree.")

    if violations and campaign_mode:
        raise GovernanceViolation(
            f"FATAL: {len(violations)} governance violation(s) in campaign mode:\n"
            + "\n".join(f"  - {v}" for v in violations))

    return violations


def require_governed_baseline(baseline_path: str, campaign_mode: bool = True) -> dict:
    """Load and validate a session baseline. Hard-fail if ungoverned in campaign mode.

    Args:
        baseline_path: path to session_baseline_*.json
        campaign_mode: if True, raises GovernanceViolation on invalid baseline.

    Returns:
        parsed baseline dict (only if valid or in exploratory mode).

    Raises:
        GovernanceViolation: if baseline lacks valid governance in campaign mode.
    """
    with open(baseline_path) as f:
        baseline = json.load(f)

    violations = validate_governance(baseline, campaign_mode=False)

    if violations:
        msg = (f"Session baseline {baseline_path} has governance violations:\n"
               + "\n".join(f"  - {v}" for v in violations))
        if campaign_mode:
            raise GovernanceViolation(f"FATAL: {msg}\n"
                "Pre-v2.1 baselines are not valid for campaign evidence production.\n"
                "Re-admit a session under v2.1 to produce a governed baseline.")
        else:
            print(f"  WARNING (exploratory): {msg}")

    return baseline


# ---------------------------------------------------------------------------
# Reporting controls
# ---------------------------------------------------------------------------
def reporting_header(bucket_id: str) -> str:
    """Generate required reporting header for bucket-level results.

    Every bucket-level conclusion must carry this header.
    """
    mass = BUCKET_EVIDENCE_MASS.get(bucket_id, {})
    pack_size = mass.get("pack_size", "?")
    power = mass.get("power_class", "?")
    domain = mass.get("domain", "?")

    lines = [
        f"Bucket {bucket_id} ({domain})",
        f"  Effective pack size: {pack_size}/400",
        f"  Power class: {power}",
    ]
    if power == "lower":
        lines.append("  ** Lower-power bucket: conclusions carry reduced statistical weight **")

    return "\n".join(lines)


def validate_cross_bucket_comparison(bucket_ids: list) -> list:
    """Check whether a set of buckets can be compared at equal weight.

    Returns list of warnings. Empty = safe to compare symmetrically.
    """
    warnings = []
    power_classes = set()
    for bid in bucket_ids:
        mass = BUCKET_EVIDENCE_MASS.get(bid, {})
        power_classes.add(mass.get("power_class", "unknown"))

    if len(power_classes) > 1:
        warnings.append(
            f"UNEQUAL_POWER: buckets {bucket_ids} have mixed power classes "
            f"{power_classes}. Cross-bucket comparison requires normalization "
            f"by evidence mass or explicit disclosure of asymmetry.")

    return warnings
