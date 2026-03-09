#!/bin/bash
# Safe WSL Shutdown — checks for active training before shutting down WSL
# Use this instead of raw "wsl --shutdown"
#
# Usage: bash scripts/safe_wsl_shutdown.sh
#        bash scripts/safe_wsl_shutdown.sh --force   (skip guard)

FORCE=${1:-""}

echo "Checking for active training in WSL..."

# Check training guard
RESULT=$(wsl.exe -d Ubuntu-24.04 -- bash -c "
    if [ -f /opt/hiveai/project/.training_active ]; then
        cat /opt/hiveai/project/.training_active
        echo 'TRAINING_ACTIVE'
    elif pgrep -f train_v5.py > /dev/null 2>&1; then
        echo 'train_v5.py running (PID: '$(pgrep -f train_v5.py)')'
        echo 'TRAINING_ACTIVE'
    elif pgrep -f train_grpo.py > /dev/null 2>&1; then
        echo 'train_grpo.py running (PID: '$(pgrep -f train_grpo.py)')'
        echo 'TRAINING_ACTIVE'
    else
        echo 'SAFE'
    fi
" 2>/dev/null)

if echo "$RESULT" | grep -q "TRAINING_ACTIVE"; then
    echo ""
    echo "!! BLOCKED: Training is active in WSL !!"
    echo "$RESULT" | grep -v "TRAINING_ACTIVE"
    echo ""
    if [ "$FORCE" = "--force" ]; then
        echo "WARNING: --force flag used. Proceeding with shutdown anyway!"
        wsl.exe --shutdown
        echo "WSL shut down (training was killed)."
    else
        echo "Use --force to override (WILL KILL TRAINING)."
        echo "Or wait for training to complete."
        exit 1
    fi
else
    echo "No training detected. Shutting down WSL..."
    wsl.exe --shutdown
    echo "WSL shut down safely."
fi
