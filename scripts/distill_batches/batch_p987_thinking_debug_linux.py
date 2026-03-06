"""Thinking-trace pairs: Linux debugging."""

PAIRS = [
    (
        "thinking/debugging",
        r'''My Linux server application is running out of file descriptors. I get "Too many open files" errors after running for a few days. The ulimit is set to 65536 but the process is hitting it. How do I find and fix the file descriptor leak?''',
        r'''<think>
The process hits 65536 file descriptors after running for a few days. My first thought is whether the ulimit is just too low -- but 65536 is already generous, and if the process legitimately needed that many concurrent FDs, it would hit the limit much sooner. Since it takes days, this is almost certainly a leak: something is opening FDs without closing them.

But what kind of FDs are leaking? It could be files, sockets, or pipes. I initially assumed it is file handles (like log files being opened repeatedly without closing), but actually socket leaks are more common in server applications. Sockets in CLOSE_WAIT state, for example, indicate the remote end closed the connection but the application never called close() on its side.

Hmm, I should also consider subprocess pipes. If the application spawns child processes with subprocess.Popen and reads stdout but never calls communicate() or closes the pipe handles, those FDs accumulate. Each Popen creates 2-3 pipe FDs.

The diagnostic approach is: first check /proc/PID/fd to count total FDs, then use lsof or ls -la on that directory to categorize them (socket vs file vs pipe). If most are sockets, check ss for CLOSE_WAIT state. If most are files, look for patterns in which files are opened repeatedly. The fix is always the same principle: use context managers (with statements) to guarantee cleanup.
</think>

File descriptor leaks can be systematically diagnosed and fixed. Here is the complete process:

```bash
# ============================================================
# STEP 1: Find the leaking process and its FD count
# ============================================================

# Find processes with highest FD count
for pid in /proc/[0-9]*; do
    fd_count=$(ls -1 "$pid/fd" 2>/dev/null | wc -l)
    if [ "$fd_count" -gt 100 ]; then
        name=$(cat "$pid/comm" 2>/dev/null)
        echo "$fd_count FDs: PID=$(basename $pid) CMD=$name"
    fi
done | sort -rn | head -20

# Or using lsof (more readable):
lsof -p <PID> | wc -l              # Total FD count
lsof -p <PID> | awk '{print $5}' | sort | uniq -c | sort -rn
# Shows breakdown by FD type (REG, IPv4, IPv6, PIPE, etc.)

# ============================================================
# STEP 2: Identify WHAT is being leaked
# ============================================================

# Check FD types for the process
ls -la /proc/<PID>/fd/ | head -50
# symlinks show: socket:[12345], /path/to/file, pipe:[67890]

# Group by type:
ls -la /proc/<PID>/fd/ 2>/dev/null | awk '{print $NF}' | \
    sed 's/\[.*\]//' | sort | uniq -c | sort -rn

# If sockets are leaking, check socket details:
ss -p | grep "pid=<PID>" | head -20
# Shows: tcp ESTAB/CLOSE-WAIT src:port -> dst:port

# Count sockets in CLOSE_WAIT state (not properly closed):
ss -p | grep "pid=<PID>" | grep CLOSE-WAIT | wc -l

# If files are leaking:
lsof -p <PID> | grep REG | awk '{print $9}' | sort | uniq -c | sort -rn

# ============================================================
# STEP 3: Monitor FD growth over time
# ============================================================

# Simple monitoring script:
# watch -n 5 "ls /proc/<PID>/fd | wc -l"

# More detailed monitoring:
while true; do
    fd_count=$(ls /proc/<PID>/fd 2>/dev/null | wc -l)
    sockets=$(ls -la /proc/<PID>/fd 2>/dev/null | grep socket | wc -l)
    echo "$(date '+%H:%M:%S') FDs=$fd_count Sockets=$sockets"
    sleep 10
done
```

```python
# ============================================================
# STEP 4: Fix common FD leak patterns in Python
# ============================================================

import os
import resource

def check_fd_count():
    """Check current process FD count."""
    pid = os.getpid()
    fd_count = len(os.listdir(f"/proc/{pid}/fd"))
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    print(f"Open FDs: {fd_count}, Limit: {soft} (soft) / {hard} (hard)")
    return fd_count

# LEAK PATTERN 1: File opened but not closed
# BAD:
def read_config_bad(path):
    f = open(path, "r")
    data = f.read()
    # f.close() is never called!
    return data

# GOOD: Use context manager
def read_config_good(path):
    with open(path, "r") as f:
        return f.read()

# LEAK PATTERN 2: HTTP connections not closed
# BAD:
import urllib.request
def fetch_bad(url):
    response = urllib.request.urlopen(url)
    return response.read()
    # response is never closed!

# GOOD:
def fetch_good(url):
    with urllib.request.urlopen(url) as response:
        return response.read()

# LEAK PATTERN 3: Database connections not returned to pool
# BAD:
def query_bad(pool):
    conn = pool.getconn()
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    return cursor.fetchall()
    # conn is never returned to pool!

# GOOD:
def query_good(pool):
    conn = pool.getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        return cursor.fetchall()
    finally:
        pool.putconn(conn)

# LEAK PATTERN 4: Subprocess pipes not closed
# BAD:
import subprocess
def run_command_bad(cmd):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
    output = proc.stdout.read()
    # proc.stdout is never closed, proc is never waited on
    return output

# GOOD:
def run_command_good(cmd):
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=30
    )
    return result.stdout

# ============================================================
# STEP 5: FD leak detector for development
# ============================================================

import atexit
import traceback
import io

class FDLeakDetector:
    """Track file descriptor creation to find leaks."""

    def __init__(self):
        self._open_fds = {}
        self._original_open = io.open
        self._patch()
        atexit.register(self.report)

    def _patch(self):
        original = self._original_open
        tracker = self

        def tracked_open(*args, **kwargs):
            f = original(*args, **kwargs)
            if hasattr(f, "fileno"):
                try:
                    fd = f.fileno()
                    tracker._open_fds[fd] = {
                        "path": str(args[0]) if args else "unknown",
                        "stack": traceback.format_stack(),
                    }
                except Exception:
                    pass
            return f

        import builtins
        builtins.open = tracked_open

    def report(self):
        """Report unclosed file descriptors."""
        pid = os.getpid()
        current_fds = set()
        try:
            current_fds = set(int(x) for x in os.listdir(f"/proc/{pid}/fd"))
        except Exception:
            pass

        leaked = set(self._open_fds.keys()) & current_fds
        if leaked:
            print(f"\n=== FD LEAK REPORT: {len(leaked)} leaked FDs ===")
            for fd in leaked:
                info = self._open_fds[fd]
                print(f"  FD {fd}: {info['path']}")
                # Print last 3 stack frames for each leak
                for frame in info["stack"][-3:]:
                    print(f"    {frame.strip()}")

# Enable during development:
# detector = FDLeakDetector()
```

**Diagnosis summary:**
1. Use `ls /proc/PID/fd | wc -l` to get current FD count
2. Use `lsof -p PID` to see what FDs are open
3. Check for CLOSE_WAIT sockets with `ss -p`
4. Always use context managers (`with` statements) for resources
5. Monitor FD count over time to identify gradual leaks''',
    ),
    (
        "thinking/debugging",
        r'''My Linux server has zombie processes accumulating. ps aux shows many processes in Z state. The parent process is still running but not reaping its children. How do I fix this?

$ ps aux | grep Z
user  12345  0.0  0.0  0  0 ?  Z  10:00  0:00 [worker] <defunct>
user  12346  0.0  0.0  0  0 ?  Z  10:01  0:00 [worker] <defunct>
user  12347  0.0  0.0  0  0 ?  Z  10:02  0:00 [worker] <defunct>
... (hundreds more)''',
        r'''<think>
Hundreds of zombie processes in Z state, all children of the same parent PID. My first instinct is to just kill the zombie processes directly -- but wait, you cannot kill a zombie because it is already dead. The process has exited; its entry in the process table is just waiting for the parent to read its exit status via wait()/waitpid().

Could I send SIGCHLD to the parent to remind it to reap? Maybe, but if the parent is coded to ignore SIGCHLD or does not have a handler installed, sending the signal again will not help. The parent might be using os.fork() in a loop without ever calling waitpid().

I considered whether killing the parent would help. Actually yes -- if the parent dies, all its zombie children get reparented to PID 1 (init/systemd), which automatically reaps them. But killing the parent is destructive and not always acceptable.

The proper fix depends on whether we control the parent's code. If we do, the simplest approach is signal.signal(signal.SIGCHLD, signal.SIG_IGN), which tells the kernel to auto-reap children without creating zombies at all. Alternatively, a SIGCHLD handler that calls waitpid(-1, WNOHANG) in a loop can reap children while still getting their exit status. For new code, using subprocess.Popen with communicate() or multiprocessing.Pool handles reaping automatically, so zombies never accumulate in the first place.
</think>

Zombie processes accumulate when the parent does not call `wait()` to reap exited children. Here is how to diagnose and fix:

```bash
# ============================================================
# STEP 1: Find the parent process
# ============================================================

# Find zombies and their parent PID
ps -eo pid,ppid,stat,comm | grep -E "Z|PPID"
# Example output:
# PID    PPID   STAT  COMMAND
# 12345  9999   Z     worker <defunct>
# 12346  9999   Z     worker <defunct>

# The PPID (9999) is the process that needs to reap children

# Get details about the parent:
ps -p 9999 -o pid,ppid,stat,comm,args

# Count zombies per parent:
ps -eo ppid,stat | grep Z | awk '{print $1}' | sort | uniq -c | sort -rn

# ============================================================
# STEP 2: Quick fix -- send SIGCHLD to parent
# ============================================================

# SIGCHLD tells the parent "a child has exited, please reap it"
# Some parents ignore this signal, but it is worth trying:
kill -SIGCHLD 9999

# Check if zombies were reaped:
sleep 2
ps -eo ppid,stat | grep Z | grep 9999 | wc -l

# ============================================================
# STEP 3: Nuclear option -- kill the parent
# ============================================================

# If you kill the parent, zombies are reparented to PID 1
# (init/systemd), which automatically reaps them.
# WARNING: This kills the parent process!
# kill 9999
# sleep 2
# ps aux | grep Z | wc -l   # Should be 0
```

```python
# ============================================================
# STEP 4: Fix the code (the real solution)
# ============================================================

import os
import signal
import subprocess
import sys
import time

# PATTERN 1: Using signal handler to auto-reap children
# This is the simplest fix for a long-running parent process

def reap_children(signum, frame):
    """Signal handler to reap zombie children."""
    while True:
        try:
            # WNOHANG: do not block if no child has exited
            pid, status = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break  # No more children to reap
            print(f"Reaped child PID {pid}, exit status {status}")
        except ChildProcessError:
            break  # No children at all

# Install the signal handler
signal.signal(signal.SIGCHLD, reap_children)


# PATTERN 2: Using SIG_IGN to auto-reap (simplest)
# Setting SIGCHLD to SIG_IGN tells the kernel to automatically
# reap children without creating zombies at all.

signal.signal(signal.SIGCHLD, signal.SIG_IGN)

# Now any child process that exits is immediately cleaned up
# without the parent needing to call wait().


# PATTERN 3: Proper subprocess management
# BAD: Fork without wait
def spawn_workers_bad(count):
    pids = []
    for i in range(count):
        pid = os.fork()
        if pid == 0:
            # Child process
            do_work(i)
            os._exit(0)
        else:
            pids.append(pid)
    # Parent never waits -- zombies accumulate!

# GOOD: Fork with proper reaping
def spawn_workers_good(count):
    pids = []
    for i in range(count):
        pid = os.fork()
        if pid == 0:
            do_work(i)
            os._exit(0)
        else:
            pids.append(pid)

    # Wait for all children
    for pid in pids:
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass  # Already reaped by signal handler


# PATTERN 4: Using subprocess module (handles reaping)
def run_workers_subprocess(count):
    """subprocess.Popen with proper cleanup."""
    procs = []
    for i in range(count):
        proc = subprocess.Popen(
            ["python", "worker.py", str(i)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        procs.append(proc)

    # Wait for all to complete
    for proc in procs:
        stdout, stderr = proc.communicate(timeout=60)
        print(f"Worker {proc.pid} exited with code {proc.returncode}")


# PATTERN 5: Process pool (best for worker patterns)
from multiprocessing import Pool

def do_work(item):
    """Worker function."""
    time.sleep(1)
    return item * 2

def run_pool():
    """multiprocessing.Pool handles reaping automatically."""
    with Pool(processes=4) as pool:
        results = pool.map(do_work, range(100))
    # All workers are properly reaped when pool exits
    return results


# PATTERN 6: Double fork to avoid zombies entirely
def daemonize_child():
    """Double-fork trick: child becomes orphan, reparented to init."""
    pid = os.fork()
    if pid > 0:
        # Parent: wait for first child (which exits immediately)
        os.waitpid(pid, 0)
        return

    # First child: fork again and exit
    pid2 = os.fork()
    if pid2 > 0:
        os._exit(0)  # First child exits, grandchild is orphaned

    # Grandchild: now reparented to init/systemd
    # init will reap this process when it exits
    do_long_running_work()
    os._exit(0)


# ============================================================
# MONITORING: Detect zombie accumulation
# ============================================================

def check_zombies():
    """Alert if zombie count is growing."""
    result = subprocess.run(
        ["ps", "-eo", "stat"],
        capture_output=True, text=True,
    )
    zombie_count = sum(
        1 for line in result.stdout.splitlines() if line.strip().startswith("Z")
    )
    if zombie_count > 0:
        print(f"WARNING: {zombie_count} zombie processes detected")
        # Find parents
        result2 = subprocess.run(
            ["ps", "-eo", "ppid,stat,comm"],
            capture_output=True, text=True,
        )
        for line in result2.stdout.splitlines():
            if " Z " in line:
                print(f"  {line.strip()}")
    return zombie_count
```

**Key takeaways:**
1. Zombies mean the parent is not calling `wait()`/`waitpid()`
2. Quickest code fix: `signal.signal(signal.SIGCHLD, signal.SIG_IGN)` -- auto-reap all children
3. Best practice: use `subprocess` module or `multiprocessing.Pool` which handle reaping
4. Killing the parent reparents zombies to init, which reaps them automatically
5. Monitor zombie count and alert if it exceeds a threshold''',
    ),
    (
        "thinking/debugging",
        r'''My Linux application was killed by the OOM killer. I see in dmesg: "Out of memory: Kill process 12345 (myapp) score 999 or sacrifice child". How do I analyze what happened and prevent it from happening again?''',
        r'''<think>
The OOM killer terminated the process with score 999, which is nearly the maximum of 1000. That means this process was the biggest memory consumer on the system. But why did the system run out of memory?

My first thought was maybe there is a memory leak in the application. That is possible, but the OOM killer does not care about leaks per se -- it just acts when allocation fails. Could it be that the system simply does not have enough RAM for the workload? Or maybe swap was full or not configured?

Wait, I should look at this from both angles. The oom_score of 999 tells me this process was using almost all the available memory. The dmesg output should show the memory state at the time of the kill -- total RAM, free memory, cached memory, swap usage. If swap is zero, adding swap would provide a buffer. If swap is also exhausted, the system genuinely cannot handle the workload.

I considered just setting oom_score_adj to -1000 to make the process unkillable, but that is dangerous -- if the process truly has a memory leak, protecting it means the OOM killer will kill other essential processes (like sshd or the database) instead. The better approach is to set memory limits via systemd/cgroups (MemoryMax) so the process gets killed by its own cgroup before exhausting system-wide memory. That way you protect both the application and the rest of the system. Then investigate the actual memory usage pattern with tools like VmRSS and VmPeak from /proc/PID/status to determine if there is a genuine leak or just insufficient resources.
</think>

The OOM killer is a last resort when Linux cannot allocate memory. Here is how to analyze and prevent it:

```bash
# ============================================================
# STEP 1: Analyze the OOM event from kernel logs
# ============================================================

# Find OOM killer events in kernel log
dmesg | grep -A 30 "Out of memory"

# The output shows:
# - Which process was killed and its oom_score
# - Memory state at time of kill (total, free, cached, swap)
# - Per-process memory breakdown
# - Call stack that triggered the OOM

# Get structured OOM info from journald:
journalctl -k | grep -A 30 "oom-kill"

# Find recent OOM events:
journalctl -k --since "24 hours ago" | grep -i "oom\|out of memory"

# ============================================================
# STEP 2: Analyze current memory usage
# ============================================================

# System-wide memory overview:
free -h
# Note: "available" is more meaningful than "free"
# Linux uses free RAM for disk cache, which is reclaimable

# Per-process memory usage (sorted by RSS):
ps aux --sort=-rss | head -20

# Detailed process memory:
cat /proc/<PID>/status | grep -E "VmSize|VmRSS|VmSwap|VmPeak"
# VmRSS = actual physical memory used
# VmPeak = maximum RSS ever reached
# VmSwap = memory swapped out

# Memory map of a process:
pmap -x <PID> | tail -5
# Shows total mapped, RSS, and dirty memory

# Check swap usage per process:
for pid in $(ls /proc/ | grep '^[0-9]'); do
    swap=$(grep VmSwap /proc/$pid/status 2>/dev/null | awk '{print $2}')
    if [ -n "$swap" ] && [ "$swap" -gt 0 ]; then
        name=$(cat /proc/$pid/comm 2>/dev/null)
        echo "$swap kB: PID=$pid CMD=$name"
    fi
done | sort -rn | head -10

# ============================================================
# STEP 3: Check OOM scores for running processes
# ============================================================

# See which process the OOM killer would choose next:
for pid in $(ls /proc/ | grep '^[0-9]'); do
    score=$(cat /proc/$pid/oom_score 2>/dev/null)
    adj=$(cat /proc/$pid/oom_score_adj 2>/dev/null)
    name=$(cat /proc/$pid/comm 2>/dev/null)
    if [ -n "$score" ] && [ "$score" -gt 100 ]; then
        echo "score=$score adj=$adj PID=$pid CMD=$name"
    fi
done | sort -t= -k2 -rn | head -10
```

```python
# ============================================================
# STEP 4: Protect critical processes from OOM killer
# ============================================================

import os

def protect_from_oom(pid=None, adjustment=-900):
    """Lower OOM score to protect a process from being killed.
    Range: -1000 (never kill) to 1000 (always kill first).
    Only root can set values below 0.
    """
    if pid is None:
        pid = os.getpid()

    try:
        with open(f"/proc/{pid}/oom_score_adj", "w") as f:
            f.write(str(adjustment))
        print(f"Set oom_score_adj={adjustment} for PID {pid}")
    except PermissionError:
        print("Need root to set negative oom_score_adj")

# In systemd service file:
# [Service]
# OOMScoreAdjust=-900    # Protect this service
# MemoryLimit=2G         # But also set a memory limit!

# ============================================================
# STEP 5: Set memory limits with systemd/cgroups
# ============================================================

# In systemd service file:
SYSTEMD_SERVICE = """
[Service]
ExecStart=/usr/bin/python3 /opt/myapp/main.py

# Memory limits (cgroups v2)
MemoryMax=2G              # Hard limit (OOM killer at this point)
MemoryHigh=1.5G           # Soft limit (throttle, not kill)
MemorySwapMax=512M         # Swap limit

# OOM behavior
OOMPolicy=stop             # stop service on OOM instead of killing
OOMScoreAdjust=-100        # Lower priority for OOM killer

# Restart on OOM
Restart=on-failure
RestartSec=5
"""

# Check current cgroup limits:
# systemctl show myapp.service | grep -i memory

# ============================================================
# STEP 6: Monitor memory usage to prevent OOM
# ============================================================

import psutil
import logging

logger = logging.getLogger(__name__)

def monitor_memory(threshold_pct=80):
    """Monitor system memory and warn before OOM."""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    print(f"RAM: {mem.percent}% used "
          f"({mem.used / 1024**3:.1f}G / {mem.total / 1024**3:.1f}G)")
    print(f"Swap: {swap.percent}% used "
          f"({swap.used / 1024**3:.1f}G / {swap.total / 1024**3:.1f}G)")

    if mem.percent > threshold_pct:
        logger.warning(
            "HIGH MEMORY: %.1f%% used (%.1fG available)",
            mem.percent,
            mem.available / 1024**3,
        )

        # Find top memory consumers
        procs = []
        for proc in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                rss = proc.info["memory_info"].rss
                procs.append((rss, proc.info["pid"], proc.info["name"]))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        procs.sort(reverse=True)
        print("\nTop memory consumers:")
        for rss, pid, name in procs[:10]:
            print(f"  PID {pid:>6}: {rss / 1024**2:>8.1f} MB  {name}")

        return True  # Warning state
    return False  # OK

def check_process_memory(max_rss_mb=1024):
    """Check if current process exceeds memory threshold."""
    process = psutil.Process()
    rss_mb = process.memory_info().rss / 1024**2

    if rss_mb > max_rss_mb:
        logger.critical(
            "Process RSS (%.1f MB) exceeds limit (%d MB). "
            "Consider restarting.",
            rss_mb, max_rss_mb,
        )
        return True
    return False

# Run periodically:
# monitor_memory(threshold_pct=85)
# check_process_memory(max_rss_mb=2048)
```

**Prevention strategy:**
1. Set `MemoryMax` in systemd to limit process memory (prevents system-wide OOM)
2. Use `OOMScoreAdjust=-900` to protect critical services
3. Monitor memory usage and alert at 80% before OOM triggers
4. Add swap space as a safety buffer (even 1-2GB helps)
5. Fix the root cause: memory leaks in the application itself''',
    ),
    (
        "thinking/debugging",
        r'''My Linux server has high disk I/O and applications are responding slowly. How do I identify which process is causing the I/O bottleneck and fix it?''',
        r'''<think>
High disk I/O causing slow application response. My first instinct is to check if the disk is full, since writes to a nearly-full filesystem can become extremely slow. But the user says "high disk I/O", implying active reads/writes rather than space exhaustion.

Could this be caused by swap thrashing instead of actual application I/O? If the system is low on RAM, the kernel pages memory in and out constantly, which manifests as high disk I/O but is really a memory problem. I should check vmstat for si/so (swap in/out) columns to rule this out before diving into disk analysis.

Actually, let me think about the diagnostic order more carefully. First, confirm I/O is the bottleneck by checking CPU %wa (I/O wait) in top. If %wa is high, then yes, processes are stalling on I/O. Second, identify which disk is saturated using iostat -xz -- the %util column shows disk utilization, and await shows average wait time. Third, find the culprit process using iotop or pidstat -d. Only then should I dig into what files are being accessed with lsof or strace.

Hmm, I also need to consider whether the I/O pattern matters. Sequential writes (like logging) are handled efficiently by the kernel's I/O scheduler, but random reads (like a database doing index lookups on a spinning disk) are orders of magnitude slower. The fix depends entirely on the pattern: batching and buffering help sequential I/O, while moving to SSDs or adding caching helps random I/O.
</think>

High disk I/O requires identifying the culprit process and the I/O pattern. Here is the diagnostic approach:

```bash
# ============================================================
# STEP 1: Confirm I/O is the bottleneck
# ============================================================

# Check I/O wait percentage in CPU stats
# "wa" column shows % of time CPU is waiting for I/O
top -bn1 | head -5
# If %wa > 20%, I/O is likely the bottleneck

# Alternative: vmstat shows system-wide I/O stats
vmstat 1 5
# bi = blocks in (reads), bo = blocks out (writes)
# wa = I/O wait time

# ============================================================
# STEP 2: Identify which disk is saturated
# ============================================================

# iostat shows per-device I/O stats
iostat -xz 1 5
# Key metrics:
#   %util  - disk utilization (>95% = saturated)
#   r/s    - reads per second
#   w/s    - writes per second
#   await  - average I/O wait time in ms (>20ms = slow for SSD)
#   svctm  - average service time
#   avgqu-sz - average queue size (>1 = requests queuing)

# ============================================================
# STEP 3: Find which PROCESS is causing I/O
# ============================================================

# iotop shows per-process I/O (needs root)
sudo iotop -oP
# -o: only show processes doing I/O
# -P: show per-process (not per-thread)
# Columns: DISK READ, DISK WRITE, SWAPIN, IO>

# Alternative: pidstat for I/O per process
pidstat -d 1 5
# kB_rd/s = KB read per second
# kB_wr/s = KB written per second

# Alternative: check /proc for per-process I/O
for pid in $(ls /proc/ | grep '^[0-9]'); do
    io=$(cat /proc/$pid/io 2>/dev/null)
    if [ -n "$io" ]; then
        read_bytes=$(echo "$io" | grep read_bytes | awk '{print $2}')
        write_bytes=$(echo "$io" | grep write_bytes | awk '{print $2}')
        name=$(cat /proc/$pid/comm 2>/dev/null)
        if [ "$write_bytes" -gt 10000000 ] 2>/dev/null; then
            echo "W=$(($write_bytes/1024/1024))MB R=$(($read_bytes/1024/1024))MB PID=$pid $name"
        fi
    fi
done | sort -t= -k1 -rn | head -10

# ============================================================
# STEP 4: Find WHAT files are being read/written
# ============================================================

# lsof shows open files for a process
lsof -p <PID> | grep -E "REG|DIR" | awk '{print $9}' | sort | uniq -c | sort -rn

# strace shows actual I/O system calls in real-time
sudo strace -p <PID> -e trace=read,write,open,close -c
# -c: show summary (syscall count and time)
# Remove -c to see individual calls

# fatrace shows filesystem activity system-wide
sudo fatrace | head -50
# Shows: PID command action filename

# ============================================================
# STEP 5: Check for common causes
# ============================================================

# Excessive logging:
du -sh /var/log/* | sort -rh | head -10

# Database I/O:
# Check if PostgreSQL/MySQL is doing sequential scans
# EXPLAIN ANALYZE your slow queries

# Swap thrashing (I/O caused by memory pressure):
vmstat 1 5 | awk '{print $7, $8}'  # si, so columns
# si > 0 = swapping in, so > 0 = swapping out
# If both are high, add RAM or reduce memory usage

# Check filesystem for issues:
df -h          # Disk space (full disk = very slow writes)
df -i          # Inode usage (can run out of inodes)
```

```python
# ============================================================
# STEP 6: Fix common I/O problems in application code
# ============================================================

import os
import io

# FIX 1: Buffer writes instead of many small writes
# BAD: Many small writes
def log_events_bad(events, filepath):
    for event in events:
        with open(filepath, "a") as f:
            f.write(str(event) + "\n")
    # Opens/closes file N times, each write is a separate I/O

# GOOD: Batch writes
def log_events_good(events, filepath):
    with open(filepath, "a", buffering=8192) as f:
        for event in events:
            f.write(str(event) + "\n")
    # One open/close, writes buffered

# EVEN BETTER: Write in memory, flush once
def log_events_best(events, filepath):
    buffer = io.StringIO()
    for event in events:
        buffer.write(str(event) + "\n")
    with open(filepath, "a") as f:
        f.write(buffer.getvalue())

# FIX 2: Use async I/O for concurrent operations
import asyncio
import aiofiles

async def process_files_async(filepaths):
    """Process multiple files concurrently."""
    async def read_one(path):
        async with aiofiles.open(path, "r") as f:
            return await f.read()

    results = await asyncio.gather(
        *[read_one(p) for p in filepaths]
    )
    return results

# FIX 3: Reduce fsync calls
# BAD: fsync after every write
def write_with_sync(filepath, data):
    with open(filepath, "w") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())  # Forces disk write

# GOOD: Only fsync when data durability is critical
def write_batched(filepath, items):
    with open(filepath, "a") as f:
        for item in items:
            f.write(str(item) + "\n")
        f.flush()
        # Single fsync for the entire batch
        os.fsync(f.fileno())

# FIX 4: Use mmap for large file random access
import mmap

def search_large_file(filepath, pattern):
    """Memory-mapped file access -- OS handles I/O efficiently."""
    with open(filepath, "r") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        index = mm.find(pattern.encode())
        mm.close()
        return index
```

**I/O optimization checklist:**
1. Use `iostat -xz 1` to find saturated disks
2. Use `iotop -oP` to find the process causing I/O
3. Batch writes and use proper buffering
4. Check for swap thrashing (memory issue causing I/O)
5. Move log files to a separate disk from application data
6. Consider SSD upgrade if using HDD for random I/O workloads''',
    ),
    (
        "thinking/debugging",
        r'''My systemd service keeps failing to start. The status shows "failed" but the error messages in journalctl are not clear. How do I systematically debug systemd service failures?''',
        r'''<think>
Systemd service keeps failing with unclear error messages. Let me think about the most systematic way to debug this, since there are many possible causes.

My first approach would be to check the exit code from systemctl status. If the exit code is 127, that means the binary was not found (wrong ExecStart path). If it is 203, the exec format is wrong (maybe a script without a shebang line). Exit code 217 means a namespace or security setting failed. These exit codes narrow down the problem significantly before I even look at logs.

But wait -- sometimes the exit code is just 1, which is a generic application error. In that case I need journalctl -u service to see what the application actually printed to stderr before it died. I initially thought journalctl -n 50 would be enough, but if the service has been restarting in a loop (Restart=on-failure), the logs from the latest attempt might be mixed in with dozens of previous failed attempts. Using --since or -b to filter to the most recent boot helps.

I considered whether the issue might be environmental rather than a code bug. Common gotchas: the service runs as a different user than when you tested manually (missing HOME, PATH, or other env vars), the WorkingDirectory does not exist, SELinux or AppArmor is blocking access, or a dependency service (like PostgreSQL) is not ready yet because After= is not configured. The best diagnostic step is to actually run the ExecStart command manually as the service user (sudo -u serviceuser /path/to/binary) to see if it reproduces outside of systemd.
</think>

Systemd service failures can be debugged systematically. Here is the complete approach:

```bash
# ============================================================
# STEP 1: Get the service status and error details
# ============================================================

# Full status with recent log output
systemctl status myapp.service

# Key information:
#   Active: failed (exit code, signal)
#   Main PID: the PID that failed
#   Status/Result: exit-code, signal, timeout, etc.

# Detailed properties (all configuration)
systemctl show myapp.service

# Just the important failure info
systemctl show myapp.service -p ActiveState,SubState,Result,ExecMainStatus,ExecMainCode

# ============================================================
# STEP 2: Read the full logs
# ============================================================

# All logs for this service (most recent first)
journalctl -u myapp.service -n 100 --no-pager

# Logs from the most recent start attempt
journalctl -u myapp.service -b --since "10 minutes ago"

# Follow logs in real-time while starting the service
journalctl -u myapp.service -f &
systemctl start myapp.service

# Include kernel messages (for segfaults, OOM)
journalctl -u myapp.service -k

# ============================================================
# STEP 3: Verify the service file
# ============================================================

# Show the service file with path
systemctl cat myapp.service

# Verify syntax (catches common errors)
systemd-analyze verify myapp.service

# Check for configuration errors
systemd-analyze dot myapp.service | head -20

# Show the full resolved configuration (with defaults)
systemctl show myapp.service --all | head -50

# ============================================================
# STEP 4: Test the command manually
# ============================================================

# Run the ExecStart command as the service user
# First, find what user the service runs as:
systemctl show myapp.service -p User,Group

# Test the command as that user:
sudo -u myapp /usr/bin/python3 /opt/myapp/main.py

# If the service uses environment variables:
# Load the env file and test
set -a
source /opt/myapp/.env
set +a
sudo -u myapp /usr/bin/python3 /opt/myapp/main.py

# ============================================================
# STEP 5: Common fixes
# ============================================================

# FIX A: Correct file permissions
# Check ExecStart binary exists and is executable
ls -la /opt/myapp/main.py
# Fix:
chmod +x /opt/myapp/main.py
chown myapp:myapp /opt/myapp/main.py

# FIX B: Correct working directory
# Check WorkingDirectory exists:
ls -la /opt/myapp/

# FIX C: Environment variables
# Add env vars in the service file:
# [Service]
# Environment=DB_HOST=localhost
# Environment=DB_PORT=5432
# EnvironmentFile=/opt/myapp/.env

# FIX D: Dependencies not ready
# If the service needs the network or another service:
# [Unit]
# After=network-online.target postgresql.service
# Wants=network-online.target

# FIX E: Service starts too fast and exits
# If the process daemonizes itself:
# [Service]
# Type=forking  # for traditional daemons
# PIDFile=/run/myapp.pid

# If it is a modern non-forking process:
# Type=exec     # or Type=simple (default)

# FIX F: Service fails on first start but works on restart
# Likely a dependency issue. Add startup delay:
# [Service]
# ExecStartPre=/bin/sleep 2

# Or better, use proper dependency ordering:
# [Unit]
# After=network-online.target
# Wants=network-online.target
```

```python
# ============================================================
# Example: Well-configured systemd service file
# ============================================================

GOOD_SERVICE_FILE = """
[Unit]
Description=My Application Server
Documentation=https://docs.example.com/myapp
After=network-online.target postgresql.service
Wants=network-online.target
Requires=postgresql.service

[Service]
Type=exec
User=myapp
Group=myapp
WorkingDirectory=/opt/myapp

# Environment
EnvironmentFile=/opt/myapp/.env

# Command
ExecStart=/opt/myapp/venv/bin/python -m myapp.server
ExecReload=/bin/kill -HUP $MAINPID

# Restart policy
Restart=on-failure
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/opt/myapp/data /var/log/myapp

# Resource limits
MemoryMax=2G
CPUQuota=200%
LimitNOFILE=65536

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=myapp

[Install]
WantedBy=multi-user.target
"""

# ============================================================
# Debugging script: Comprehensive service check
# ============================================================

import subprocess
import os

def debug_systemd_service(service_name):
    """Run all diagnostic checks for a systemd service."""
    checks = [
        ("Status", f"systemctl status {service_name} --no-pager"),
        ("Is enabled", f"systemctl is-enabled {service_name}"),
        ("Failed reason", f"systemctl show {service_name} -p Result,ExecMainStatus"),
        ("Service file", f"systemctl cat {service_name}"),
        ("Recent logs", f"journalctl -u {service_name} -n 30 --no-pager"),
    ]

    for label, cmd in checks:
        print(f"\n{'=' * 60}")
        print(f"  {label}")
        print(f"{'=' * 60}")
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True
        )
        print(result.stdout)
        if result.stderr:
            print(f"STDERR: {result.stderr}")

# debug_systemd_service("myapp.service")
```

**Debugging checklist:**
1. `systemctl status` -- get the exit code and signal
2. `journalctl -u service -n 100` -- read the full error log
3. `systemd-analyze verify` -- check service file syntax
4. Run ExecStart command manually as the service user
5. Check file permissions, paths, and environment variables
6. Verify `After=` dependencies are correct and running''',
    ),
]
