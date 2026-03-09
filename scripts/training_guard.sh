#!/bin/bash
# Training Guard — prevents accidental WSL shutdown during training
# Source this before any destructive WSL operation:
#   bash scripts/training_guard.sh
#
# Also used by run_full_cycle.sh to create/remove lock files.

LOCK_FILE="/opt/hiveai/project/.training_active"
LOG_DIR="/opt/hiveai/project/logs"

check_training() {
    # Method 1: Check lock file
    if [ -f "$LOCK_FILE" ]; then
        local info
        info=$(cat "$LOCK_FILE")
        echo "!! TRAINING ACTIVE — DO NOT SHUTDOWN WSL !!"
        echo "   $info"
        echo "   Lock file: $LOCK_FILE"
        return 0  # training IS running
    fi

    # Method 2: Check for active train_v5.py process
    if pgrep -f "train_v5.py" > /dev/null 2>&1; then
        echo "!! TRAINING PROCESS DETECTED (train_v5.py) !!"
        echo "   PID: $(pgrep -f train_v5.py)"
        return 0
    fi

    # Method 3: Check for active train_grpo.py process
    if pgrep -f "train_grpo.py" > /dev/null 2>&1; then
        echo "!! GRPO TRAINING DETECTED (train_grpo.py) !!"
        echo "   PID: $(pgrep -f train_grpo.py)"
        return 0
    fi

    # Method 4: Check tmux sessions with training
    if tmux list-sessions 2>/dev/null | grep -qi "train"; then
        echo "!! TMUX TRAINING SESSION DETECTED !!"
        tmux list-sessions 2>/dev/null
        return 0
    fi

    echo "No active training detected. Safe to proceed."
    return 1  # no training
}

create_lock() {
    local version="${1:-unknown}"
    local step_info="${2:-starting}"
    echo "Version: $version | Started: $(date -Iseconds) | $step_info" > "$LOCK_FILE"
    echo "Training lock created: $LOCK_FILE"
}

remove_lock() {
    rm -f "$LOCK_FILE"
    echo "Training lock removed."
}

# If run directly (not sourced), just check
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    check_training
    exit $?
fi
