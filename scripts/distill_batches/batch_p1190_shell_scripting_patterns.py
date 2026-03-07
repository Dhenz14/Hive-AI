"""
Shell/CLI training pairs - Bash scripting patterns (error handling, argument parsing, logging).
Mix: 2 thinking, 3 direct.
"""

pairs = [
    {
        "instruction": r'''What's the proper way to handle errors in a bash script? I keep having scripts fail silently.''',
        "output": r'''<think>
Silent failures in bash are the default -- commands fail and the script keeps going. The user needs:
1. `set -euo pipefail` -- the holy trinity of bash safety
2. Trap for cleanup on exit
3. Error reporting with line numbers

I should explain each flag and show a practical template. I should also mention the caveats with `set -e` since it has some surprising behaviors (e.g., commands in if conditions, commands with ||).
</think>

Start every script with this header:

```bash
#!/bin/bash
set -euo pipefail

# What each flag does:
# -e  Exit immediately when a command fails
# -u  Treat unset variables as errors
# -o pipefail  A pipeline fails if ANY command in it fails
#              (default: only checks the last command)
```

Add error reporting with a trap:

```bash
#!/bin/bash
set -euo pipefail

cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo "ERROR: Script failed at line $BASH_LINENO with exit code $exit_code" >&2
    fi
    # Clean up temp files, release locks, etc.
    rm -f "${TMPFILE:-}"
}
trap cleanup EXIT

TMPFILE=$(mktemp)
echo "Working..."
# If anything below fails, cleanup runs automatically
```

Caveats with `set -e`:

```bash
# These do NOT trigger exit on failure (by design):
if command_that_fails; then echo "ok"; fi   # in a condition
command_that_fails || true                   # with || fallback
command_that_fails && echo "worked"          # left side of &&

# This DOES trigger exit:
command_that_fails          # bare command
result=$(command_that_fails)  # in command substitution
```

For commands you expect might fail:

```bash
# Option 1: explicit check
if ! grep -q "pattern" file.txt; then
    echo "Pattern not found, continuing anyway"
fi

# Option 2: default value for unset vars
echo "${MY_VAR:-default_value}"
```'''
    },
    {
        "instruction": r'''Show me a solid pattern for parsing command-line arguments in a bash script with flags, options, and a help message.''',
        "output": r'''```bash
#!/bin/bash
set -euo pipefail

# Defaults
VERBOSE=false
OUTPUT_DIR="./output"
FORMAT="json"
DRY_RUN=false
FILES=()

usage() {
    cat << 'EOF'
Usage: process.sh [OPTIONS] FILE [FILE...]

Process data files and generate reports.

Options:
    -h, --help          Show this help message
    -v, --verbose       Enable verbose output
    -o, --output DIR    Output directory (default: ./output)
    -f, --format FMT    Output format: json, csv, xml (default: json)
    -n, --dry-run       Show what would be done without doing it

Examples:
    process.sh -v -f csv data/*.log
    process.sh --output /tmp/reports --format json input.txt
EOF
    exit 0
}

die() {
    echo "Error: $1" >&2
    echo "Try 'process.sh --help' for usage information." >&2
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)    usage ;;
        -v|--verbose) VERBOSE=true; shift ;;
        -n|--dry-run) DRY_RUN=true; shift ;;
        -o|--output)
            [[ $# -lt 2 ]] && die "--output requires a directory argument"
            OUTPUT_DIR="$2"; shift 2 ;;
        -f|--format)
            [[ $# -lt 2 ]] && die "--format requires an argument"
            FORMAT="$2"; shift 2 ;;
        -*)
            die "Unknown option: $1" ;;
        *)
            FILES+=("$1"); shift ;;
    esac
done

# Validate
[[ ${#FILES[@]} -eq 0 ]] && die "No input files specified"
[[ "$FORMAT" =~ ^(json|csv|xml)$ ]] || die "Invalid format: $FORMAT"

# Use the parsed values
$VERBOSE && echo "Processing ${#FILES[@]} files..."
$VERBOSE && echo "Output: $OUTPUT_DIR, Format: $FORMAT"

for file in "${FILES[@]}"; do
    [[ -f "$file" ]] || die "File not found: $file"
    $VERBOSE && echo "Processing: $file"
    # ... actual processing here ...
done
```'''
    },
    {
        "instruction": r'''How do I add logging to a bash script with timestamps and log levels?''',
        "output": r'''```bash
#!/bin/bash
set -euo pipefail

# Configuration
LOG_FILE="/var/log/myapp/script.log"
LOG_LEVEL="${LOG_LEVEL:-INFO}"  # Override with env var

# Log level numbers for comparison
declare -A LOG_LEVELS=([DEBUG]=0 [INFO]=1 [WARN]=2 [ERROR]=3)

log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Check if we should log at this level
    local level_num="${LOG_LEVELS[$level]:-1}"
    local threshold="${LOG_LEVELS[$LOG_LEVEL]:-1}"
    [[ $level_num -lt $threshold ]] && return

    local line="${timestamp} [${level}] ${message}"

    # Write to both stderr and log file
    echo "$line" >&2
    echo "$line" >> "$LOG_FILE"
}

# Convenience functions
debug() { log DEBUG "$@"; }
info()  { log INFO "$@"; }
warn()  { log WARN "$@"; }
error() { log ERROR "$@"; }

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Usage
info "Script started with PID $$"
debug "Working directory: $(pwd)"

if some_command 2>/dev/null; then
    info "Command succeeded"
else
    error "Command failed with exit code $?"
fi

warn "Disk usage above 80%"
info "Script completed"
```

Run with different log levels:

```bash
LOG_LEVEL=DEBUG ./myscript.sh    # show everything
LOG_LEVEL=WARN ./myscript.sh     # only warnings and errors
```

Output looks like:

```
2025-01-15 14:30:22 [INFO] Script started with PID 12345
2025-01-15 14:30:22 [DEBUG] Working directory: /opt/app
2025-01-15 14:30:23 [ERROR] Command failed with exit code 1
```'''
    },
    {
        "instruction": r'''I need to write a bash script that processes items in parallel with a configurable number of workers. What's the pattern for that?''',
        "output": r'''<think>
There are several approaches to parallel processing in bash:
1. Background jobs with a manual job counter
2. xargs -P for simple cases
3. GNU parallel for complex cases
4. Using a FIFO as a semaphore

I will show the background jobs approach since it works everywhere without extra dependencies, and also show xargs -P as the simpler alternative.
</think>

Using background jobs with a worker limit:

```bash
#!/bin/bash
set -euo pipefail

MAX_WORKERS="${1:-4}"
ITEMS=("item1" "item2" "item3" "item4" "item5" "item6" "item7" "item8")

process_item() {
    local item="$1"
    echo "[$$] Processing: $item"
    sleep $((RANDOM % 3 + 1))  # simulate work
    echo "[$$] Done: $item"
}

# Track running jobs
running=0
for item in "${ITEMS[@]}"; do
    process_item "$item" &
    ((running++))

    # Wait if we hit the worker limit
    if [[ $running -ge $MAX_WORKERS ]]; then
        wait -n  # wait for ANY one job to finish
        ((running--))
    fi
done

# Wait for remaining jobs
wait
echo "All items processed"
```

Simpler version using xargs:

```bash
# Process a list with 4 parallel workers
printf '%s\n' "${ITEMS[@]}" | xargs -P 4 -I {} bash -c 'echo "Processing: {}"; sleep 1; echo "Done: {}"'

# Process files in parallel
find ./data -name '*.csv' -print0 | xargs -0 -P 4 -I {} ./process.sh {}
```

With error collection:

```bash
#!/bin/bash
set -uo pipefail

MAX_WORKERS=4
ERRORS=0
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

process_item() {
    local item="$1"
    if ! do_work "$item" 2>"$TMPDIR/$item.err"; then
        echo "FAILED: $item" >&2
        return 1
    fi
}

export -f process_item
printf '%s\n' "${ITEMS[@]}" | xargs -P "$MAX_WORKERS" -I {} bash -c 'process_item "$@"' _ {}

# Check for errors
ERRORS=$(find "$TMPDIR" -name '*.err' -not -empty | wc -l)
echo "Completed with $ERRORS errors"
exit $((ERRORS > 0 ? 1 : 0))
```'''
    },
    {
        "instruction": r'''Show me how to write a bash script that uses a lock file to prevent multiple instances from running simultaneously.''',
        "output": r'''```bash
#!/bin/bash
set -euo pipefail

LOCKFILE="/tmp/myprocess.lock"

# Method 1: Using flock (recommended -- atomic and race-condition-free)
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "Another instance is already running (PID $(cat "$LOCKFILE"))" >&2
    exit 1
fi
echo $$ >&200  # write our PID to the lock file

# Lock is automatically released when the script exits
# (file descriptor 200 closes)

echo "Running with lock acquired..."
# ... your script logic here ...
echo "Done"
```

Method 2 -- using mkdir (portable, works on older systems):

```bash
#!/bin/bash
set -euo pipefail

LOCKDIR="/tmp/myprocess.lock"

cleanup() {
    rm -rf "$LOCKDIR"
}

# mkdir is atomic on all filesystems
if ! mkdir "$LOCKDIR" 2>/dev/null; then
    # Check if the holding process is still alive
    if [ -f "$LOCKDIR/pid" ]; then
        OLD_PID=$(cat "$LOCKDIR/pid")
        if kill -0 "$OLD_PID" 2>/dev/null; then
            echo "Already running (PID $OLD_PID)" >&2
            exit 1
        else
            echo "Stale lock found (PID $OLD_PID is dead), removing"
            rm -rf "$LOCKDIR"
            mkdir "$LOCKDIR"
        fi
    fi
fi

trap cleanup EXIT
echo $$ > "$LOCKDIR/pid"

echo "Running exclusively..."
# ... your script logic here ...
```

The flock approach is preferred because:
- It is atomic (no race conditions)
- The lock is released automatically if the script crashes
- No stale lock cleanup needed
- Works with cron jobs to prevent overlap'''
    },
]
