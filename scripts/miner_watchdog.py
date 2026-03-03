"""
Watchdog for brain_mine.py — auto-restarts if it dies.

Usage:
    python scripts/miner_watchdog.py --review --workers 2

Logs to logs/brain_mine.log (appends).
Restarts automatically on crash with 30s cooldown.
"""
import subprocess
import sys
import time
import os
import signal

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    log_path = os.path.join(project_dir, "logs", "brain_mine.log")

    # Forward all args to brain_mine.py
    args = sys.argv[1:]
    cmd = [sys.executable, os.path.join(script_dir, "brain_mine.py")] + args

    os.environ["OLLAMA_NUM_PARALLEL"] = "3"

    restart_count = 0
    max_restarts = 50  # Safety limit

    while restart_count < max_restarts:
        restart_count += 1
        print(f"\n{'='*60}")
        print(f"[WATCHDOG] Starting brain_mine.py (attempt {restart_count})")
        print(f"[WATCHDOG] Command: {' '.join(cmd)}")
        print(f"{'='*60}\n")

        with open(log_path, "a", encoding="utf-8") as log_f:
            log_f.write(f"\n[WATCHDOG] === Start attempt {restart_count} at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            log_f.flush()

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    cwd=project_dir,
                    env=os.environ.copy(),
                )
                exit_code = proc.wait()

                log_f.write(f"\n[WATCHDOG] Process exited with code {exit_code}\n")
                log_f.flush()

                if exit_code == 0:
                    print(f"[WATCHDOG] brain_mine.py completed successfully.")
                    break
                else:
                    print(f"[WATCHDOG] brain_mine.py exited with code {exit_code}")

            except KeyboardInterrupt:
                print(f"\n[WATCHDOG] Interrupted. Killing miner...")
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                break
            except Exception as e:
                with open(log_path, "a") as lf:
                    lf.write(f"\n[WATCHDOG] Exception: {e}\n")
                print(f"[WATCHDOG] Error: {e}")

        # Cooldown before restart
        cooldown = min(30 * restart_count, 120)
        print(f"[WATCHDOG] Restarting in {cooldown}s...")
        time.sleep(cooldown)

    if restart_count >= max_restarts:
        print(f"[WATCHDOG] Max restarts ({max_restarts}) reached. Giving up.")


if __name__ == "__main__":
    main()
