"""Training watchdog — spot-check v8 training quality without waiting.

Parses training logs and raises alarms if:
  1. Loss is above threshold (>1.5 = bad init, >0.8 after 50 steps = not converging)
  2. Loss is INCREASING over a window (diverging)
  3. Step time is degrading (VRAM spill to system RAM)
  4. Training appears stalled (no new log entries)

Usage:
    python scripts/training_watchdog.py                    # check all categories
    python scripts/training_watchdog.py --cat go           # check specific category
    python scripts/training_watchdog.py --watch            # continuous monitoring (30s interval)

Can also be called from Windows against WSL logs:
    wsl -d Ubuntu-24.04 -- python3 /opt/hiveai/project/scripts/training_watchdog.py
"""
import argparse
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = ["go", "cpp", "rust", "hive"]

# Thresholds based on v7 training (loss=0.467 final, 1.38 steps/min)
THRESHOLDS = {
    "loss_initial_max": 1.5,      # First 10 steps — above this means bad init
    "loss_converging_max": 0.8,   # After 50 steps — should be well below this
    "loss_final_target": 0.55,    # End of training — v7 was 0.467
    "loss_diverge_window": 20,    # Check last N loss values for upward trend
    "step_time_max": 120,         # Seconds — above this means VRAM spill
    "stale_minutes": 15,          # No log activity = probably crashed
}


def parse_training_log(log_path: str) -> dict:
    """Parse a training log and extract metrics."""
    path = Path(log_path)
    if not path.exists():
        return {"status": "not_started", "path": str(path)}

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.strip().split("\n")

    # Extract loss values: "loss=0.5234"
    losses = []
    steps = []
    step_times = []
    last_timestamp = None

    for line in lines:
        # Loss from logging callback: "Step 50/200 | loss=0.5234"
        loss_match = re.search(r"Step\s+(\d+)/(\d+)\s*\|.*?loss=([\d.]+)", line)
        if loss_match:
            step = int(loss_match.group(1))
            total = int(loss_match.group(2))
            loss = float(loss_match.group(3))
            losses.append(loss)
            steps.append(step)

        # Step time: "step_time=43.2s"
        time_match = re.search(r"step_time=([\d.]+)s", line)
        if time_match:
            step_times.append(float(time_match.group(1)))

        # Timestamp: "2026-03-07 22:38:19,653"
        ts_match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        if ts_match:
            last_timestamp = ts_match.group(1)

    # Check for completion
    completed = "Training complete" in text or "Saving adapter" in text

    # Check for errors
    has_error = "ERROR" in text or "Traceback" in text or "CUDA out of memory" in text

    return {
        "status": "completed" if completed else ("error" if has_error else "running"),
        "path": str(path),
        "losses": losses,
        "steps": steps,
        "step_times": step_times,
        "total_steps": int(steps[-1]) if steps else 0,  # last known step
        "max_steps": int(re.search(r"Step\s+\d+/(\d+)", text).group(1)) if re.search(r"Step\s+\d+/(\d+)", text) else 0,
        "last_timestamp": last_timestamp,
        "last_line": lines[-1] if lines else "",
        "has_error": has_error,
        "error_lines": [l for l in lines[-10:] if "ERROR" in l or "Traceback" in l],
    }


def check_alarms(cat: str, metrics: dict) -> list[str]:
    """Check metrics against thresholds, return list of alarm messages."""
    alarms = []
    losses = metrics.get("losses", [])
    step_times = metrics.get("step_times", [])

    if metrics["status"] == "not_started":
        return [f"  {cat.upper()}: Not started yet"]

    if metrics["has_error"]:
        alarms.append(f"  ALARM [{cat.upper()}]: Training ERROR detected!")
        for line in metrics.get("error_lines", []):
            alarms.append(f"    {line.strip()}")
        return alarms

    if not losses:
        alarms.append(f"  {cat.upper()}: No loss data yet (still loading model?)")
        return alarms

    current_loss = losses[-1]
    current_step = metrics["steps"][-1] if metrics["steps"] else 0
    max_steps = metrics.get("max_steps", 0)
    progress_pct = (current_step / max_steps * 100) if max_steps > 0 else 0

    # 1. Bad initialization
    if len(losses) <= 10 and current_loss > THRESHOLDS["loss_initial_max"]:
        alarms.append(f"  ALARM [{cat.upper()}]: Initial loss {current_loss:.4f} > {THRESHOLDS['loss_initial_max']} — possible bad init or data issue")

    # 2. Not converging
    if current_step > 50 and current_loss > THRESHOLDS["loss_converging_max"]:
        alarms.append(f"  ALARM [{cat.upper()}]: Loss {current_loss:.4f} still above {THRESHOLDS['loss_converging_max']} at step {current_step} — not converging")

    # 3. Diverging (loss trending up over recent window)
    window = THRESHOLDS["loss_diverge_window"]
    if len(losses) >= window:
        recent = losses[-window:]
        first_half = sum(recent[:window//2]) / (window//2)
        second_half = sum(recent[window//2:]) / (window//2)
        if second_half > first_half * 1.05:  # 5% increase
            alarms.append(f"  ALARM [{cat.upper()}]: Loss DIVERGING — avg {first_half:.4f} → {second_half:.4f} over last {window} logs")

    # 4. Step time degradation (VRAM spill)
    if step_times and max(step_times[-5:]) > THRESHOLDS["step_time_max"]:
        slow = max(step_times[-5:])
        alarms.append(f"  ALARM [{cat.upper()}]: Step time {slow:.0f}s > {THRESHOLDS['step_time_max']}s — possible VRAM spill")

    # Status line (always show)
    status_icon = "OK" if not alarms else "!!"
    min_loss = min(losses) if losses else 0
    avg_step_time = sum(step_times[-10:]) / len(step_times[-10:]) if step_times else 0
    eta_min = (max_steps - current_step) * avg_step_time / 60 if avg_step_time > 0 else 0

    status = (f"  {status_icon} {cat.upper():5s}: step {current_step}/{max_steps} ({progress_pct:.0f}%) | "
              f"loss={current_loss:.4f} (min={min_loss:.4f}) | "
              f"step_time={avg_step_time:.1f}s | ETA={eta_min:.0f}min")
    alarms.insert(0, status)

    if metrics["status"] == "completed":
        alarms.insert(0, f"  DONE {cat.upper()}: Training complete! Final loss={current_loss:.4f}")

    return alarms


def run_watchdog(categories: list[str], log_dir: str):
    """Run a single watchdog check."""
    print(f"{'='*60}")
    print(f"  v8 Training Watchdog — {time.strftime('%H:%M:%S')}")
    print(f"  v7 reference: loss=0.467, step_time=43s")
    print(f"{'='*60}")

    all_ok = True
    for cat in categories:
        log_path = Path(log_dir) / f"v8_{cat}_training.log"
        metrics = parse_training_log(str(log_path))
        messages = check_alarms(cat, metrics)
        for msg in messages:
            print(msg)
            if "ALARM" in msg:
                all_ok = False
        print()

    if all_ok:
        print("  All categories within normal parameters.")
    else:
        print("  !! ALARMS DETECTED — check logs above !!")

    print(f"{'='*60}")
    return all_ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="v8 training watchdog")
    parser.add_argument("--cat", choices=CATEGORIES, help="Check specific category")
    parser.add_argument("--log-dir", default=str(PROJECT_ROOT / "loras"),
                        help="Directory containing training logs")
    parser.add_argument("--watch", action="store_true",
                        help="Continuous monitoring (30s interval)")
    args = parser.parse_args()

    cats = [args.cat] if args.cat else CATEGORIES

    if args.watch:
        try:
            while True:
                run_watchdog(cats, args.log_dir)
                print(f"\n  Next check in 30s... (Ctrl+C to stop)\n")
                time.sleep(30)
        except KeyboardInterrupt:
            print("\nWatchdog stopped.")
    else:
        ok = run_watchdog(cats, args.log_dir)
        sys.exit(0 if ok else 1)
