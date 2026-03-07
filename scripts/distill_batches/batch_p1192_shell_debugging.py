"""
Shell/CLI training pairs - Debugging with strace, lsof, netstat, tcpdump, shell tools.
Mix: 2 thinking, 3 direct.
"""

pairs = [
    {
        "instruction": r'''My application is hanging and I don't know why. It's stuck and not responding. How do I figure out what it's doing using Linux debugging tools?''',
        "output": r'''<think>
A hanging process could be stuck on:
1. A system call (I/O wait, network, disk)
2. A lock/mutex
3. An infinite loop (CPU-bound)
4. Waiting for input

The debugging approach should be:
1. First check if it is using CPU (top/ps) -- if CPU is high, it is in a loop; if low, it is blocked on I/O or waiting
2. Use strace to see what syscall it is stuck on
3. Use lsof to see open files/connections
4. Look at /proc for more details

I should give a step-by-step triage workflow.
</think>

Step-by-step debugging a hanging process:

```bash
# 1. Find the process and check CPU usage
ps aux | grep myapp
# If %CPU is 0 -- blocked on I/O or waiting
# If %CPU is high -- stuck in a loop

# 2. See what syscall it's stuck on right now
sudo strace -p <PID> -f -e trace=all
# Common findings:
#   futex(... FUTEX_WAIT ...) -- waiting on a lock/mutex
#   read(3, ...              -- waiting for data on fd 3
#   poll([{fd=5, ...         -- waiting for network socket
#   epoll_wait(...           -- event loop waiting (normal for servers)

# 3. Check what files/sockets are open
sudo lsof -p <PID>
# Look for: TCP connections stuck in ESTABLISHED, open files, pipes

# 4. Check the thread stacks
sudo cat /proc/<PID>/stack     # kernel stack
sudo cat /proc/<PID>/wchan     # what the process is waiting on

# 5. For multi-threaded apps, check all threads
ls /proc/<PID>/task/
for tid in /proc/<PID>/task/*; do
    echo "Thread $(basename $tid): $(cat $tid/wchan)"
done

# 6. Check if it is in uninterruptible sleep (D state)
ps -o pid,stat,wchan -p <PID>
# D state means waiting on I/O -- check dmesg for disk errors
```

If it is stuck on a network call:

```bash
# Show TCP connections for this process
ss -tnp | grep <PID>

# Check if the remote end is reachable
nc -zv remote-host 5432 -w 3
```'''
    },
    {
        "instruction": r'''How do I use tcpdump to capture and analyze HTTP traffic for debugging API issues?''',
        "output": r'''```bash
# Capture HTTP traffic on port 80
sudo tcpdump -i any port 80 -A -s 0

# Capture HTTPS traffic (encrypted, but see headers)
sudo tcpdump -i any port 443 -w capture.pcap

# Filter by host
sudo tcpdump -i any host api.example.com and port 443

# Capture traffic to/from a specific IP
sudo tcpdump -i any host 10.0.0.5

# Save to file for analysis in Wireshark
sudo tcpdump -i any port 8080 -w debug.pcap -c 1000
# -c 1000 stops after 1000 packets

# Show HTTP request/response bodies (port 8080, ASCII)
sudo tcpdump -i any port 8080 -A -s 0 | grep -E '(GET|POST|PUT|DELETE|HTTP/|Content-|{)'

# Filter by request method
sudo tcpdump -i any port 80 -A -s 0 | grep -A 20 'POST /api'
```

Useful filters:

```bash
# Only SYN packets (new connections)
sudo tcpdump -i any 'tcp[tcpflags] & tcp-syn != 0' and port 80

# Only RST packets (connection resets -- indicates errors)
sudo tcpdump -i any 'tcp[tcpflags] & tcp-rst != 0'

# DNS queries
sudo tcpdump -i any port 53

# Show packet sizes and timing (no content)
sudo tcpdump -i any port 8080 -ttt -q
```

For local debugging, curl is often easier:

```bash
# Verbose output showing headers and timing
curl -v https://api.example.com/endpoint

# With timing breakdown
curl -w "@curl-timing.txt" -o /dev/null -s https://api.example.com/endpoint
# Where curl-timing.txt contains:
# time_namelookup: %{time_namelookup}\ntime_connect: %{time_connect}\ntime_total: %{time_total}\n
```'''
    },
    {
        "instruction": r'''How do I trace which files a process is reading and writing to understand its behavior?''',
        "output": r'''<think>
The user wants to trace file I/O. strace is the primary tool for this on Linux. I should show:
1. How to trace file-related syscalls specifically
2. How to filter by path
3. How to trace a running process vs starting a new one
4. inotifywait as an alternative for watching specific directories
</think>

```bash
# Trace all file operations of a command
strace -e trace=file ./myapp
# Traces: open, stat, access, unlink, rename, etc.

# Trace read/write operations (see actual I/O)
strace -e trace=read,write -e read=3,4 -p <PID>

# Trace only open/openat calls (which files it touches)
strace -e trace=openat -f ./myapp 2>&1 | grep -v ENOENT

# Attach to a running process
sudo strace -p <PID> -e trace=openat,read,write -f

# Save output to file (stderr is where strace writes)
strace -e trace=file -o trace.log ./myapp

# Show timestamps for each syscall
strace -e trace=file -T -t ./myapp
# -t adds wall clock time, -T adds time spent in syscall
```

Filter for specific paths:

```bash
# Only show access to /etc/ files
strace -e trace=openat ./myapp 2>&1 | grep '/etc/'

# Show config file reads
strace -e trace=openat ./myapp 2>&1 | grep -E '\.(conf|cfg|ini|yaml|json)'
```

Alternative: watch a directory for changes:

```bash
# Using inotifywait (inotify-tools package)
inotifywait -m -r /opt/myapp/data -e modify,create,delete

# With timestamps and formatting
inotifywait -m -r /opt/myapp/data --timefmt '%H:%M:%S' --format '%T %w%f %e'
```

Quick summary of a process's file access:

```bash
# Count file opens by path prefix
strace -e trace=openat -f -c ./myapp 2>&1
# Shows a table of syscall counts and time spent
```'''
    },
    {
        "instruction": r'''Show me how to use lsof to debug file descriptor leaks and connection problems.''',
        "output": r'''```bash
# List all open files for a process
lsof -p <PID>

# Count open file descriptors (detect leaks)
lsof -p <PID> | wc -l

# Watch fd count over time (leak detection)
while true; do
    echo "$(date +%H:%M:%S) $(lsof -p <PID> 2>/dev/null | wc -l) fds"
    sleep 5
done

# Show only network connections
lsof -p <PID> -i

# Show TCP connections in specific states
lsof -p <PID> -i TCP -sTCP:ESTABLISHED
lsof -p <PID> -i TCP -sTCP:CLOSE_WAIT
# Many CLOSE_WAIT connections = app not closing connections properly

# Find processes with the most open files
lsof 2>/dev/null | awk '{print $1, $2}' | sort | uniq -c | sort -rn | head -20

# Check system-wide fd limits vs usage
cat /proc/sys/fs/file-nr
# Output: allocated  free  max
# If allocated is near max, you are running out

# Check per-process limits
cat /proc/<PID>/limits | grep "open files"

# Find deleted files still held open (disk space leak)
lsof +L1
# These files are deleted but still consuming disk
# Restarting the process releases the space

# Find who is using a specific file
lsof /var/log/syslog

# Find who is using a specific port
lsof -i :8080
```'''
    },
    {
        "instruction": r'''How do I debug a slow bash script to find which commands are taking the most time?''',
        "output": r'''```bash
# Method 1: Enable trace mode with timestamps
# Add to the top of your script:
PS4='+ $(date "+%s.%N") ${BASH_SOURCE}:${LINENO}: '
set -x

# Run normally -- each command is printed with a timestamp
./slow-script.sh 2>trace.log

# Find the slow parts by looking at time gaps
awk '{print $2, $0}' trace.log | sort -n
```

Method 2: Profile with time markers:

```bash
#!/bin/bash
profile_start() { PROFILE_START=$(date +%s%N); }
profile_end() {
    local elapsed=$(( ($(date +%s%N) - PROFILE_START) / 1000000 ))
    echo "PROFILE: $1 took ${elapsed}ms" >&2
}

profile_start
some_slow_command
profile_end "some_slow_command"

profile_start
another_command
profile_end "another_command"
```

Method 3: Use the `time` builtin on suspect sections:

```bash
time {
    find /var -name '*.log' -mtime +30 -delete
}
# Outputs: real 0m4.321s, user 0m0.012s, sys 0m0.234s
# High real but low user+sys = waiting on I/O
# High user = CPU-intensive
```

Method 4: Analyze the trace log automatically:

```bash
# Parse the trace output to find slowest gaps
PS4='+%s.%N '
set -x
# ... script runs ...
set +x

# Then analyze:
awk '/^\+[0-9]/ {
    t = $1; sub(/^\+/, "", t)
    if (prev) {
        delta = t - prev
        if (delta > 0.1) printf "%.3fs: %s\n", delta, prevline
    }
    prev = t; prevline = $0
}' trace.log | sort -rn | head -10
```

This shows the top 10 slowest commands by the gap between consecutive trace lines.'''
    },
]
