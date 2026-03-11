#!/bin/bash
# auto_queue.sh — Sequential multi-cycle training queue
#
# Usage: bash scripts/auto_queue.sh
#
# Trains v5-agentic, then v6-think3, v7-think4, v8-think5 in sequence.
# Each cycle: train → merge → consolidate → eval → promote → next
#
# Chain:
#   v5-agentic  (datasets/v5_agentic_combined.jsonl)  prev: v4-recovery
#   v6-think3   (datasets/thinking_batch3.jsonl)       prev: v5-agentic
#   v7-think4   (datasets/thinking_batch4.jsonl)       prev: v6-think3
#   v8-think5   (datasets/thinking_batch5.jsonl)       prev: v7-think4
#
# If any cycle FAILS, the queue stops and reports which one failed.

set -eo pipefail
source /opt/hiveai-env/bin/activate
cd /opt/hiveai/project
export HF_HUB_OFFLINE=1

LOGDIR="logs/auto_queue_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOGDIR"

echo "=============================================="
echo "  HiveAI Auto Training Queue"
echo "  Started: $(date)"
echo "  Log dir: $LOGDIR"
echo "=============================================="
echo ""

# Define the queue: name domain data version prev_version
CYCLES=(
    "v5-agentic|agentic|datasets/v5_agentic_combined.jsonl|v5-agentic|v4-recovery"
    "v6-think3|thinking|datasets/thinking_batch3.jsonl|v6-think3|v5-agentic"
    "v7-think4|thinking|datasets/thinking_batch4.jsonl|v7-think4|v6-think3"
    "v8-think5|thinking|datasets/thinking_batch5.jsonl|v8-think5|v7-think4"
)

TOTAL=${#CYCLES[@]}
COMPLETED=0

for entry in "${CYCLES[@]}"; do
    IFS='|' read -r NAME DOMAIN DATA VERSION PREV <<< "$entry"

    echo "=============================================="
    echo "  Cycle $((COMPLETED + 1))/$TOTAL: $NAME"
    echo "  Domain: $DOMAIN"
    echo "  Data:   $DATA"
    echo "  Chain:  $PREV -> $VERSION"
    echo "  Time:   $(date)"
    echo "=============================================="

    # Verify dataset exists
    if [ ! -f "$DATA" ]; then
        echo "FATAL: Dataset not found: $DATA"
        echo "Run 'bash scripts/prep_v5_batch.sh' first for v5-agentic."
        echo ""
        echo "QUEUE STOPPED at cycle $((COMPLETED + 1))/$TOTAL ($NAME)"
        echo "Reason: Missing dataset $DATA"
        exit 1
    fi

    # Run the full cycle, tee to log
    CYCLE_LOG="$LOGDIR/${NAME}.log"
    echo "Logging to: $CYCLE_LOG"
    echo ""

    if bash scripts/run_full_cycle.sh "$DOMAIN" "$DATA" "$VERSION" "$PREV" 2>&1 | tee "$CYCLE_LOG"; then
        COMPLETED=$((COMPLETED + 1))
        echo ""
        echo ">>> $NAME PASSED ($COMPLETED/$TOTAL complete)"
        echo ""
    else
        EXIT_CODE=$?
        echo ""
        echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        echo "  QUEUE STOPPED — $NAME FAILED (exit $EXIT_CODE)"
        echo "  Completed: $COMPLETED/$TOTAL"
        echo "  Failed at: cycle $((COMPLETED + 1)) ($NAME)"
        echo "  Log: $CYCLE_LOG"
        echo "  Time: $(date)"
        echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        exit 1
    fi
done

echo ""
echo "=============================================="
echo "  ALL $TOTAL CYCLES COMPLETE"
echo "  Final model: $VERSION"
echo "  Finished: $(date)"
echo "  Logs: $LOGDIR/"
echo "=============================================="
