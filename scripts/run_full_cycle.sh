#!/bin/bash
# =============================================================================
# Hive AI Continual Learning Pipeline v1.1 — Full Cycle Orchestrator
#
# Runs the complete merge-then-freeze cycle for one domain:
#   1. Build surprise replay buffer
#   2. Train domain LoRA (rank 8, LoRA+, attn-only)
#   3. Convert LoRA to GGUF
#   4. Safe merge (alpha grid search)
#   5. Consolidation epoch (LR/20, 100% replay)
#   6. Merge consolidation LoRA
#   7. Regression eval (auto-starts llama-server)
#   8. Promote (if eval passes)
#
# v1.1 changes:
#   - Auto llama-server management (no manual restart needed)
#   - Disk space pre-flight check
#   - Step checkpointing for resume after failure
#   - All paths via env vars (no hardcoded user paths)
#   - Timeout protection on eval
#
# Usage:
#   bash scripts/run_full_cycle.sh <domain> <data_path> <version> [prev_version]
#
# Example:
#   bash scripts/run_full_cycle.sh hive datasets/hive_data.jsonl v1-hive v1.0
#   bash scripts/run_full_cycle.sh cpp datasets/cpp_data.jsonl v2-cpp v1-hive
#
# Environment variables (set in .env or export):
#   LLAMA_CPP_DIR       — Path to llama.cpp (default: /tmp/llama.cpp)
#   LLAMA_SERVER_PORT   — Port for llama-server (default: 11435)
#   HIVEAI_PROJECT_ROOT — Override auto-detected project root
#   HF_BASE_CACHE       — HF snapshot path for GGUF conversion
#   TRAINING_BASE_DIR   — Base dir for HF training checkpoints (default: /opt/hiveai/project/models/training)
# =============================================================================
set -euo pipefail

DOMAIN=${1:?Usage: run_full_cycle.sh <domain> <data_path> <version> [prev_version]}
DATA_PATH=${2:?Usage: run_full_cycle.sh <domain> <data_path> <version> [prev_version]}
VERSION=${3:?Usage: run_full_cycle.sh <domain> <data_path> <version> [prev_version]}
PREV_VERSION=${4:-v1.0}

# ---------------------------------------------------------------------------
# Path configuration (all from env vars with sensible defaults)
# ---------------------------------------------------------------------------
PROJECT_ROOT="${HIVEAI_PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LLAMA_CPP="${LLAMA_CPP_DIR:-/tmp/llama.cpp}"
LLAMA_PORT="${LLAMA_SERVER_PORT:-11435}"
TRAINING_DIR="${TRAINING_BASE_DIR:-/opt/hiveai/project/models/training}"
DEPLOY_DIR="$PROJECT_ROOT/models/deploy"
REPLAY_DIR="$PROJECT_ROOT/replay"
LORA_OUTPUT="$PROJECT_ROOT/loras/${VERSION}"
CONSOL_OUTPUT="$PROJECT_ROOT/loras/${VERSION}_consolidation"
LOG_DIR="$PROJECT_ROOT/logs"
CHECKPOINT_FILE="$LOG_DIR/${VERSION}_checkpoint.txt"

# Previous base paths
PREV_GGUF="$DEPLOY_DIR/current_base.gguf"
PREV_HF="$TRAINING_DIR/${PREV_VERSION}/hf"

# HF cache for GGUF conversion (must be set or auto-detected)
HF_BASE_CACHE="${HF_BASE_CACHE:-}"
if [ -z "$HF_BASE_CACHE" ]; then
    # Try to find Unsloth cache automatically
    for cache_dir in "$HOME/.cache/huggingface/hub/models--unsloth--Qwen2.5-Coder-14B-Instruct/snapshots" \
                     "/root/.cache/huggingface/hub/models--unsloth--Qwen2.5-Coder-14B-Instruct/snapshots"; do
        if [ -d "$cache_dir" ]; then
            HF_BASE_CACHE=$(find "$cache_dir" -maxdepth 1 -mindepth 1 -type d | head -1)
            break
        fi
    done
fi

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
log_step() {
    echo ""
    echo "=== Step $1: $2 ==="
}

save_checkpoint() {
    echo "$1" > "$CHECKPOINT_FILE"
}

get_checkpoint() {
    if [ -f "$CHECKPOINT_FILE" ]; then
        cat "$CHECKPOINT_FILE"
    else
        echo "0"
    fi
}

check_disk_space() {
    local path="$1"
    local needed_gb="$2"
    local free_kb
    free_kb=$(df -k "$path" 2>/dev/null | tail -1 | awk '{print $4}')
    if [ -n "$free_kb" ]; then
        local free_gb=$((free_kb / 1024 / 1024))
        if [ "$free_gb" -lt "$needed_gb" ]; then
            echo "ERROR: Need ~${needed_gb}GB free, only ${free_gb}GB available at $path"
            echo "  Free space before continuing."
            exit 1
        fi
        echo "  Disk: ${free_gb}GB free (need ~${needed_gb}GB)"
    fi
}

start_llama_server() {
    local gguf_path="$1"
    local port="$2"

    # Kill existing llama-server on this port
    if lsof -i ":$port" >/dev/null 2>&1; then
        echo "  Stopping existing llama-server on port $port..."
        fuser -k "$port/tcp" 2>/dev/null || true
        sleep 2
    fi

    local server_bin="${LLAMA_CPP}/bin/llama-server"
    if [ ! -f "$server_bin" ]; then
        server_bin="llama-server"  # Try PATH
    fi

    echo "  Starting llama-server with $gguf_path on port $port..."
    $server_bin \
        -m "$gguf_path" \
        --port "$port" \
        --flash-attn on \
        --cache-type-k q8_0 --cache-type-v q4_0 \
        --ctx-size 8192 -ngl 99 \
        > "$LOG_DIR/${VERSION}_server.log" 2>&1 &

    SERVER_PID=$!
    echo "  llama-server PID: $SERVER_PID"

    # Wait for health check (up to 120s for model loading)
    echo "  Waiting for server to be ready..."
    for i in $(seq 1 60); do
        if curl -s "http://localhost:$port/health" >/dev/null 2>&1; then
            echo "  Server ready! (${i}s)"
            return 0
        fi
        sleep 2
    done

    echo "  ERROR: llama-server failed to start within 120s"
    echo "  Check log: $LOG_DIR/${VERSION}_server.log"
    kill "$SERVER_PID" 2>/dev/null || true
    return 1
}

stop_llama_server() {
    if [ -n "${SERVER_PID:-}" ]; then
        echo "  Stopping llama-server (PID $SERVER_PID)..."
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        unset SERVER_PID
    fi
}

# Cleanup on exit (stop server, report status)
trap 'stop_llama_server; echo "  Cycle interrupted at step $(get_checkpoint)"' EXIT

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
echo "============================================================"
echo "  Hive AI Continual Learning — Full Cycle v1.1"
echo "============================================================"
echo "  Domain:       $DOMAIN"
echo "  Data:         $DATA_PATH"
echo "  Version:      $VERSION"
echo "  Prev version: $PREV_VERSION"
echo "  Base GGUF:    $PREV_GGUF"
echo "  Base HF:      $PREV_HF"
echo "  HF cache:     ${HF_BASE_CACHE:-NOT SET}"
echo "  llama.cpp:    $LLAMA_CPP"
echo "============================================================"

# Ensure directories exist
mkdir -p "$DEPLOY_DIR" "$REPLAY_DIR" "$LOG_DIR" "$LORA_OUTPUT"

# Verify prerequisites
if [ ! -f "$PREV_GGUF" ]; then
    echo "ERROR: Base GGUF not found: $PREV_GGUF"
    echo "  Copy your base model: cp models/Qwen2.5-Coder-14B-Instruct-Q5_K_M.gguf $PREV_GGUF"
    exit 1
fi

if [ ! -f "$DATA_PATH" ]; then
    echo "ERROR: Training data not found: $DATA_PATH"
    exit 1
fi

if [ -z "$HF_BASE_CACHE" ] || [ ! -d "$HF_BASE_CACHE" ]; then
    echo "ERROR: HF base cache not found. Set HF_BASE_CACHE env var."
    echo "  Example: export HF_BASE_CACHE=~/.cache/huggingface/hub/models--unsloth--Qwen2.5-Coder-14B-Instruct/snapshots/<hash>"
    exit 1
fi

# Check convert script exists
CONVERT_SCRIPT="${LLAMA_CPP}/convert_lora_to_gguf.py"
if [ ! -f "$CONVERT_SCRIPT" ]; then
    CONVERT_SCRIPT="${LLAMA_CPP}/convert-lora-to-gguf.py"  # Alternate naming
fi
if [ ! -f "$CONVERT_SCRIPT" ]; then
    echo "ERROR: convert_lora_to_gguf.py not found in $LLAMA_CPP"
    echo "  Set LLAMA_CPP_DIR to your llama.cpp directory"
    exit 1
fi

# Disk space check (need ~60GB for full cycle: 4x merged candidates + HF checkpoint)
check_disk_space "$DEPLOY_DIR" 60

LAST_STEP=$(get_checkpoint)
if [ "$LAST_STEP" -gt 0 ]; then
    echo ""
    echo "  RESUMING from step $((LAST_STEP + 1)) (previous run checkpointed at step $LAST_STEP)"
    echo ""
fi

START_TIME=$(date +%s)

# =============================================================================
# Step 1: Build surprise replay buffer
# =============================================================================
if [ "$LAST_STEP" -lt 1 ]; then
    log_step "1/7" "Building SuRe replay buffer"
    python "$PROJECT_ROOT/scripts/replay_sampler.py" \
        --replay-dir "$REPLAY_DIR" \
        --keep 500 \
        --output "$REPLAY_DIR/sampled.jsonl" \
        --fallback-diversity \
        2>&1 | tee "$LOG_DIR/${VERSION}_01_replay.log"
    save_checkpoint 1
fi

# =============================================================================
# Step 2: Train domain LoRA (rank 8, LoRA+, attn-only)
# =============================================================================
if [ "$LAST_STEP" -lt 2 ]; then
    log_step "2/7" "Training ${DOMAIN} LoRA"
    python "$PROJECT_ROOT/scripts/train_v5.py" \
        --base-model-hf "$PREV_HF" \
        --data "$DATA_PATH" \
        --replay-dir "$REPLAY_DIR" \
        --replay-ratio 0.25 \
        --output-dir "$LORA_OUTPUT" \
        --rank 8 \
        --lora-plus \
        --attn-only \
        --no-kl \
        --epochs 2 \
        2>&1 | tee "$LOG_DIR/${VERSION}_02_train.log"
    echo "  LoRA adapter saved to: $LORA_OUTPUT"
    save_checkpoint 2
fi

# =============================================================================
# Step 3: Convert LoRA to GGUF for merge
# =============================================================================
if [ "$LAST_STEP" -lt 3 ]; then
    log_step "3/7" "Converting LoRA to GGUF"
    LORA_GGUF="$PROJECT_ROOT/models/hiveai-${VERSION}-lora-f16.gguf"
    python "$CONVERT_SCRIPT" \
        --base "$HF_BASE_CACHE" \
        "$LORA_OUTPUT" \
        --outfile "$LORA_GGUF" \
        2>&1 | tee "$LOG_DIR/${VERSION}_03_convert.log"
    echo "  LoRA GGUF: $LORA_GGUF"
    save_checkpoint 3
fi

# Set LORA_GGUF for later steps (needed if resuming past step 3)
LORA_GGUF="$PROJECT_ROOT/models/hiveai-${VERSION}-lora-f16.gguf"

# =============================================================================
# Step 4: Safe merge (alpha grid search)
# =============================================================================
if [ "$LAST_STEP" -lt 4 ]; then
    log_step "4/7" "Safe merge with alpha grid search"
    MERGE_OUTPUT="$DEPLOY_DIR/${VERSION}"
    python "$PROJECT_ROOT/scripts/safe_merge.py" \
        --base-gguf "$PREV_GGUF" \
        --lora-gguf "$LORA_GGUF" \
        --output-dir "$MERGE_OUTPUT" \
        --validation-data "$REPLAY_DIR/sampled.jsonl" \
        --alphas "0.75,0.85,0.95,1.0" \
        --version "$VERSION" \
        --base-hf "$PREV_HF" \
        --lora-hf "$LORA_OUTPUT" \
        --output-hf "$TRAINING_DIR/${VERSION}/hf" \
        2>&1 | tee "$LOG_DIR/${VERSION}_04_merge.log"
    save_checkpoint 4
fi

MERGE_OUTPUT="$DEPLOY_DIR/${VERSION}"

# =============================================================================
# Step 5: Consolidation epoch
# =============================================================================
if [ "$LAST_STEP" -lt 5 ]; then
    log_step "5/7" "Consolidation training"
    python "$PROJECT_ROOT/scripts/consolidation_train.py" \
        --base-model-hf "$TRAINING_DIR/${VERSION}/hf" \
        --replay-data "$REPLAY_DIR/sampled.jsonl" \
        --output-dir "$CONSOL_OUTPUT" \
        2>&1 | tee "$LOG_DIR/${VERSION}_05_consolidation.log"

    # Convert consolidation LoRA to GGUF
    CONSOL_GGUF="$PROJECT_ROOT/models/hiveai-${VERSION}-consol-f16.gguf"
    python "$CONVERT_SCRIPT" \
        --base "$HF_BASE_CACHE" \
        "$CONSOL_OUTPUT" \
        --outfile "$CONSOL_GGUF" \
        2>&1 | tee -a "$LOG_DIR/${VERSION}_05_consolidation.log"
    save_checkpoint 5
fi

CONSOL_GGUF="$PROJECT_ROOT/models/hiveai-${VERSION}-consol-f16.gguf"

# =============================================================================
# Step 6: Merge consolidation LoRA (alpha=1.0, no grid search)
# =============================================================================
if [ "$LAST_STEP" -lt 6 ]; then
    log_step "6/7" "Merging consolidation LoRA"
    python "$PROJECT_ROOT/scripts/safe_merge.py" \
        --base-gguf "$MERGE_OUTPUT/merged.gguf" \
        --lora-gguf "$CONSOL_GGUF" \
        --output-dir "$MERGE_OUTPUT" \
        --validation-data "$REPLAY_DIR/sampled.jsonl" \
        --alphas "1.0" \
        --version "${VERSION}-consolidated" \
        --base-hf "$TRAINING_DIR/${VERSION}/hf" \
        --lora-hf "$CONSOL_OUTPUT" \
        --output-hf "$TRAINING_DIR/${VERSION}/hf" \
        2>&1 | tee "$LOG_DIR/${VERSION}_06_consol_merge.log"
    save_checkpoint 6
fi

# =============================================================================
# Step 7: Regression eval (auto-starts llama-server)
# =============================================================================
if [ "$LAST_STEP" -lt 7 ]; then
    log_step "7/7" "Regression evaluation"

    # Auto-start llama-server with the merged GGUF
    if ! start_llama_server "$MERGE_OUTPUT/merged.gguf" "$LLAMA_PORT"; then
        echo "ERROR: Could not start llama-server for eval"
        echo "  You can manually start it and re-run with resume:"
        echo "    llama-server -m $MERGE_OUTPUT/merged.gguf --port $LLAMA_PORT ..."
        echo "  Then: bash scripts/run_full_cycle.sh $DOMAIN $DATA_PATH $VERSION $PREV_VERSION"
        exit 1
    fi

    # Run eval with timeout (30 min max)
    timeout 1800 python "$PROJECT_ROOT/scripts/regression_eval.py" \
        --model-version "$VERSION" \
        --server-url "http://localhost:$LLAMA_PORT" \
        --threshold 0.03 \
        2>&1 | tee "$LOG_DIR/${VERSION}_07_eval.log"

    EVAL_EXIT=$?

    # Stop server after eval
    stop_llama_server
    save_checkpoint 7
fi

# If we're resuming and already past step 7, eval already passed
EVAL_EXIT=${EVAL_EXIT:-0}

# =============================================================================
# Promote or rollback
# =============================================================================
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "============================================================"
if [ $EVAL_EXIT -eq 0 ]; then
    echo "  CYCLE PASSED — Promoting $VERSION as new base"
    cp "$MERGE_OUTPUT/merged.gguf" "$DEPLOY_DIR/current_base.gguf"
    echo "  New base: $DEPLOY_DIR/current_base.gguf"
    echo "  Training HF: $TRAINING_DIR/${VERSION}/hf"
    echo ""
    echo "  Next domain command:"
    echo "    bash scripts/run_full_cycle.sh <next_domain> <data.jsonl> v<N+1> $VERSION"
else
    echo "  CYCLE FAILED — Regression detected!"
    echo "  NOT promoting $VERSION"
    echo "  Current base unchanged: $PREV_GGUF"
    echo ""
    echo "  Troubleshooting:"
    echo "    - Increase replay: --replay-ratio 0.35"
    echo "    - Reduce rank: --rank 4"
    echo "    - Check logs: $LOG_DIR/${VERSION}_*.log"
fi
echo ""
echo "  Total time: ${ELAPSED}s ($((ELAPSED / 3600))h $((ELAPSED % 3600 / 60))m)"
echo "============================================================"

# Cleanup intermediate files
echo ""
echo "Cleaning up intermediate files..."
rm -f "$LORA_GGUF" "$CONSOL_GGUF"
rm -rf "$CONSOL_OUTPUT"
# Remove checkpoint on successful completion
if [ $EVAL_EXIT -eq 0 ]; then
    rm -f "$CHECKPOINT_FILE"
fi
# Keep $LORA_OUTPUT (the trained adapter) for reference
echo "  Kept: $LORA_OUTPUT (trained adapter)"
echo "  Removed: intermediate GGUF files, consolidation adapter"
echo "Done."
