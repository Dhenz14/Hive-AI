"""
Cross-Platform Retrain Trigger — coordinate Flask (Windows) → WSL training.

Uses the same pattern as /api/lora/micro-train:
1. Export JSONL to Windows git repo path (datasets/)
2. Call wsl.exe to launch run_full_cycle.sh in a tmux session
3. Monitor via existing /api/lora/training-status endpoint

The full cycle:
  smart target fires → auto_export writes JSONL → retrain_trigger launches WSL →
  run_full_cycle.sh trains + evals → regression_eval.py confirms → score_ledger updated
"""
import logging
import subprocess
import shlex
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def trigger_retrain(domain: str, data_path: str, version: str = None,
                    prev_version: str = None, auto_start: bool = False) -> dict:
    """
    Trigger a retrain cycle for a domain.

    Args:
        domain: Target domain (e.g. "python", "rust", "hive")
        data_path: Path to JSONL training data (Windows path, will be converted)
        version: Version label (e.g. "v3-python"). Auto-generated if None.
        prev_version: Previous version for delta tracking
        auto_start: If True, launch training immediately. If False, just prepare.

    Returns:
        {
            "status": "prepared" | "launched" | "error",
            "domain": str,
            "version": str,
            "data_path": str,
            "wsl_data_path": str,
        }
    """
    if version is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d")
        version = f"auto-{domain}-{ts}"

    # Convert Windows path to WSL path
    wsl_data_path = _windows_to_wsl_path(data_path)
    if not wsl_data_path:
        return {"status": "error", "error": f"Could not convert path: {data_path}"}

    result = {
        "status": "prepared",
        "domain": domain,
        "version": version,
        "data_path": data_path,
        "wsl_data_path": wsl_data_path,
    }

    if not auto_start:
        return result

    # Layer 3 policy guard: v5-think is FROZEN. Auto-training requires ALL 4 conditions:
    # 1. Repeated miss in real use (not one-off)
    # 2. Retrieval is too slow or insufficient (RAG can't cover it)
    # 3. Executable eval exists (compile/test/type-check, not keyword scoring)
    # 4. Big expected gain (>3% domain improvement)
    # auto_start=True from API should NEVER bypass this — log and refuse.
    logger.warning(f"Auto-retrain requested for {domain} but v5-think is FROZEN. "
                   f"Layer 3 requires human approval. Returning prepared-only.")
    result["status"] = "blocked"
    result["blocked_reason"] = "layer3_policy: v5-think frozen, auto_start requires human approval"
    return result

    # Launch training via WSL tmux (same pattern as /api/lora/micro-train)
    try:
        cycle_cmd = (
            f"bash /opt/hiveai/project/scripts/run_full_cycle.sh "
            f"{shlex.quote(domain)} {shlex.quote(wsl_data_path)} {shlex.quote(version)}"
        )
        if prev_version:
            cycle_cmd += f" {shlex.quote(prev_version)}"

        tmux_cmd = f"tmux new-session -d -s hiveai_train '{cycle_cmd}' 2>/dev/null || echo 'tmux session already exists'"
        wsl_cmd = ["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c", tmux_cmd]

        subprocess.Popen(wsl_cmd)
        result["status"] = "launched"
        result["tmux_session"] = "hiveai_train"
        logger.info(f"Auto-retrain launched: {version} ({domain}) from {wsl_data_path}")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        logger.error(f"Auto-retrain failed: {e}")

    return result


def _windows_to_wsl_path(win_path: str) -> str | None:
    """Convert a Windows path to the canonical WSL training path.

    Training data must live at /opt/hiveai/project/datasets/ (WSL canonical).
    Windows git repo datasets/ maps to this path via the sync step in run_full_cycle.sh.
    We return the WSL canonical path directly — training scripts never read from /mnt/c/.
    """
    try:
        path = win_path.replace("\\", "/")
        # Extract just the filename from the full path
        filename = os.path.basename(path)
        if not filename:
            return None
        return f"/opt/hiveai/project/datasets/{filename}"
    except Exception:
        return None


def check_and_trigger(db, auto_start: bool = False) -> dict:
    """
    Evaluate all smart targets, export data for triggered domains,
    and optionally launch retraining.

    Returns:
        {
            "evaluated_domains": int,
            "triggered_domains": [...],
            "blocked_domains": [...],
            "exports": [...],
            "retrains": [...],
        }
    """
    from hiveai.rag.smart_targets import evaluate_smart_targets, record_retrain
    from hiveai.rag.auto_export import export_domain_pairs

    targets = evaluate_smart_targets(db)

    result = {
        "evaluated_domains": len(targets),
        "triggered_domains": [],
        "blocked_domains": [],
        "exports": [],
        "retrains": [],
    }

    for domain, info in targets.items():
        if info.get("blocked_reason"):
            result["blocked_domains"].append({
                "domain": domain,
                "reason": info["blocked_reason"],
            })
            continue

        if not info.get("triggered"):
            continue

        result["triggered_domains"].append({
            "domain": domain,
            "reasons": info["reasons"],
            "available_pairs": info["available_pairs"],
        })

        # Export training data
        export = export_domain_pairs(db, domain)
        result["exports"].append(export)

        if export["pair_count"] == 0:
            continue

        # Trigger retrain
        retrain = trigger_retrain(
            domain=domain,
            data_path=export["path"],
            auto_start=auto_start,
        )
        result["retrains"].append(retrain)

        # Record retrain if launched
        if retrain["status"] == "launched":
            record_retrain(domain, retrain["version"], export["pair_count"])

    return result
